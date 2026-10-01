import json
import logging
import uuid
import threading
from typing import Optional, List, Dict, Any
from mcp.server.mcpserver import MCPServer
from backend.app.config import settings, competition_config
from backend.app.db.session import SessionLocal
from backend.app.db.models import Team, Submission, Finalist, FinalistVerification, LeaderboardSnapshot, AuditLog
from backend.app.services.auth import verify_mcp_admin_token
from backend.app.services.selector import selector_service
from backend.app.services.verification_worker import verification_worker
from backend.app.services.scorer import final_scorer
from backend.app.services.leaderboard import leaderboard_service
from backend.app.services.audit import record_audit

logger = logging.getLogger(__name__)

# Initialize official Python MCP server
mcp = MCPServer("hackeval-evaluator-mcp")

# In-memory async job tracking for MCP operations
mcp_jobs: Dict[str, Dict[str, Any]] = {}


def _authenticate(admin_token: str, db) -> str:
    """Validates admin token or API key; returns admin username."""
    admin_user = verify_mcp_admin_token(admin_token, db)
    return admin_user.username


@mcp.tool()
def get_competition_status(admin_token: str) -> str:
    """
    Retrieves current competition lifecycle status, submission count, and configuration state.
    Requires administrative authorization token.
    """
    db = SessionLocal()
    try:
        username = _authenticate(admin_token, db)
        total_teams = db.query(Team).count()
        total_subs = db.query(Submission).count()
        valid_subs = db.query(Submission).filter(Submission.is_valid == True).count()
        finalists_count = db.query(Finalist).count()
        published = db.query(LeaderboardSnapshot).filter(LeaderboardSnapshot.stage == "final_published").first()

        record_audit(
            db=db,
            actor_type="mcp",
            actor_id=username,
            action="mcp_get_competition_status",
            resource_type="competition",
        )

        return json.dumps({
            "competition": competition_config.name,
            "timezone": competition_config.timezone,
            "is_production_ready": competition_config.is_production_ready,
            "unresolved_todos": competition_config.unresolved_todos,
            "stats": {
                "total_teams": total_teams,
                "total_submissions": total_subs,
                "valid_submissions": valid_subs,
                "finalists_selected": finalists_count,
                "final_leaderboard_published": published is not None,
            },
            "weights": {
                "verified_performance_weight": competition_config.verified_performance_weight,
                "reliability_weight": competition_config.reliability_weight,
            },
        }, indent=2)
    finally:
        db.close()


@mcp.tool()
def freeze_and_select_official(admin_token: str, deadline_override_iso: Optional[str] = None) -> str:
    """
    Freezes open submissions, deterministically selects official attempts per team,
    and freezes the provisional preliminary leaderboard.
    """
    db = SessionLocal()
    try:
        username = _authenticate(admin_token, db)
        res = selector_service.freeze_and_select_official_submissions(
            db=db, admin_username=username, deadline_override_iso=deadline_override_iso
        )
        record_audit(
            db=db,
            actor_type="mcp",
            actor_id=username,
            action="mcp_freeze_and_select_official",
            resource_type="competition",
            details=res,
        )
        return json.dumps(res, indent=2)
    finally:
        db.close()


@mcp.tool()
def get_preliminary_leaderboard(admin_token: str, limit: int = 20) -> str:
    """
    Fetches the provisional preliminary leaderboard with rank and qualification status.
    """
    db = SessionLocal()
    try:
        username = _authenticate(admin_token, db)
        data = leaderboard_service.get_preliminary_leaderboard(db, user_role="admin")
        if "entries" in data and isinstance(data["entries"], list):
            data["entries"] = data["entries"][:limit]
        return json.dumps(data, indent=2)
    finally:
        db.close()


def _run_verification_task(job_id: str, finalist_ids: Optional[List[int]] = None):
    db = SessionLocal()
    try:
        mcp_jobs[job_id]["status"] = "running"
        if finalist_ids:
            for fid in finalist_ids:
                verification_worker.verify_finalist(db, fid)
        else:
            verification_worker.verify_all_finalists(db)
        mcp_jobs[job_id]["status"] = "completed"
        mcp_jobs[job_id]["completed_at"] = str(uuid.uuid4())
    except Exception as e:
        logger.exception("Error in background verification task")
        mcp_jobs[job_id]["status"] = "failed"
        mcp_jobs[job_id]["error"] = str(e)
    finally:
        db.close()


@mcp.tool()
def trigger_finalist_verification(admin_token: str, finalist_ids: Optional[List[int]] = None) -> str:
    """
    Enqueues verification runs for top-20 finalists using isolated worker and SSRF defenses.
    Returns an immediate job ID without blocking the MCP connection.
    """
    db = SessionLocal()
    try:
        username = _authenticate(admin_token, db)
        job_id = f"job_verify_{uuid.uuid4().hex[:8]}"
        mcp_jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "finalist_ids": finalist_ids,
            "initiated_by": username,
        }

        # Spawn worker thread
        t = threading.Thread(target=_run_verification_task, args=(job_id, finalist_ids), daemon=True)
        t.start()

        record_audit(
            db=db,
            actor_type="mcp",
            actor_id=username,
            action="mcp_trigger_verification",
            resource_type="verification_job",
            resource_id=job_id,
        )

        return json.dumps({
            "status": "queued",
            "job_id": job_id,
            "message": "Finalist verification job successfully enqueued in background worker.",
        }, indent=2)
    finally:
        db.close()


@mcp.tool()
def get_verification_status(admin_token: str, job_id: Optional[str] = None) -> str:
    """
    Checks verification progress, latency metrics, and reliability results for finalists.
    """
    db = SessionLocal()
    try:
        _authenticate(admin_token, db)
        job_info = mcp_jobs.get(job_id) if job_id else None

        verifications = db.query(FinalistVerification).all()
        summary = []
        for v in verifications:
            summary.append({
                "finalist_id": v.finalist_id,
                "team_name": v.finalist.team.name if v.finalist and v.finalist.team else "N/A",
                "reachability_passed": v.reachability_passed,
                "version_matched": v.version_matched,
                "performance_score_p": v.performance_score_p,
                "reliability_score_r": v.reliability_score_r,
                "final_score": v.final_score,
                "status": v.status,
                "avg_latency_ms": v.avg_latency_ms,
            })

        return json.dumps({
            "job_info": job_info,
            "total_verifications": len(verifications),
            "verifications": summary,
        }, indent=2)
    finally:
        db.close()


@mcp.tool()
def calculate_final_scores(admin_token: str) -> str:
    """
    Deterministically calculates final scores using the approved formula:
    S_final = 0.823529*P + 0.176471*R
    """
    db = SessionLocal()
    try:
        username = _authenticate(admin_token, db)
        ranking = final_scorer.generate_final_ranking(db)
        record_audit(
            db=db,
            actor_type="mcp",
            actor_id=username,
            action="mcp_calculate_final_scores",
            resource_type="scoring",
            details={"ranked_teams_count": len(ranking)},
        )
        return json.dumps({
            "formula": "S_final = 0.823529 * P + 0.176471 * R",
            "weights": {
                "verified_performance_weight": competition_config.verified_performance_weight,
                "reliability_weight": competition_config.reliability_weight,
            },
            "ranking": ranking,
        }, indent=2)
    finally:
        db.close()


@mcp.tool()
def publish_final_leaderboard(admin_token: str, notes: str = "Authorized via MCP") -> str:
    """
    Permanently freezes and officially publishes the final immutable leaderboard.
    Requires administrative approval.
    """
    db = SessionLocal()
    try:
        username = _authenticate(admin_token, db)
        snapshot = leaderboard_service.publish_final_leaderboard(
            db=db, admin_username=f"mcp:{username}", approval_notes=notes
        )
        return json.dumps({
            "status": "published",
            "snapshot_id": snapshot.id,
            "version": snapshot.version,
            "approved_by": snapshot.approved_by_admin,
            "approved_at": snapshot.approved_at.isoformat() if snapshot.approved_at else None,
            "is_immutable": snapshot.is_immutable,
            "entries_count": len(snapshot.entries),
        }, indent=2)
    finally:
        db.close()


@mcp.tool()
def get_audit_trail(admin_token: str, action: Optional[str] = None, limit: int = 50) -> str:
    """
    Retrieves immutable audit logs for evaluation and administrative decisions.
    """
    db = SessionLocal()
    try:
        _authenticate(admin_token, db)
        query = db.query(AuditLog)
        if action:
            query = query.filter(AuditLog.action == action)
        logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

        out = []
        for l in logs:
            out.append({
                "id": l.id,
                "actor_type": l.actor_type,
                "actor_id": l.actor_id,
                "action": l.action,
                "resource_type": l.resource_type,
                "resource_id": l.resource_id,
                "details": l.details,
                "timestamp": l.timestamp.isoformat() if l.timestamp else None,
            })
        return json.dumps(out, indent=2)
    finally:
        db.close()


if __name__ == "__main__":
    # Run the MCP server over standard I/O
    mcp.run()
