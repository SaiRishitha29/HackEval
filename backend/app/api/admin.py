from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from backend.app.db.session import get_db
from backend.app.db.models import User, Submission, Finalist, FinalistVerification, AuditLog, Team
from backend.app.schemas.submission import AdminSubmissionOut
from backend.app.schemas.evaluation import FinalistOut, FinalistVerificationOut
from backend.app.schemas.leaderboard import LeaderboardPublishRequest, LeaderboardResponse
from backend.app.services.auth import require_admin
from backend.app.services.selector import selector_service
from backend.app.services.verification_worker import verification_worker
from backend.app.services.scorer import final_scorer
from backend.app.services.leaderboard import leaderboard_service
from backend.app.config import competition_config, settings

router = APIRouter(prefix="/api/admin", tags=["Admin Operations"], dependencies=[Depends(require_admin)])


@router.get("/competition-status")
def get_competition_status(db: Session = Depends(get_db)):
    total_teams = db.query(Team).count()
    total_submissions = db.query(Submission).count()
    valid_submissions = db.query(Submission).filter(Submission.is_valid == True).count()
    finalists_count = db.query(Finalist).count()
    verifications_count = db.query(FinalistVerification).filter(FinalistVerification.status == "completed").count()

    return {
        "competition_name": competition_config.name,
        "timezone": competition_config.timezone,
        "is_production_ready": competition_config.is_production_ready,
        "unresolved_todos": competition_config.unresolved_todos,
        "weights": {
            "verified_performance_weight": competition_config.verified_performance_weight,
            "reliability_weight": competition_config.reliability_weight,
        },
        "stats": {
            "total_teams": total_teams,
            "total_submissions": total_submissions,
            "valid_submissions": valid_submissions,
            "finalists_selected": finalists_count,
            "verifications_completed": verifications_count,
        },
    }


@router.get("/submissions", response_model=List[AdminSubmissionOut])
def list_all_submissions(
    team_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(Submission)
    if team_id:
        query = query.filter(Submission.team_id == team_id)
    subs = query.order_by(Submission.submitted_at.desc()).all()
    return [AdminSubmissionOut.model_validate(s) for s in subs]


@router.post("/freeze-deadline")
def freeze_and_select(
    deadline_override_iso: Optional[str] = Query(None),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    result = selector_service.freeze_and_select_official_submissions(
        db=db,
        admin_username=admin_user.username,
        deadline_override_iso=deadline_override_iso,
    )
    return result


@router.get("/finalists", response_model=List[FinalistOut])
def get_finalists(db: Session = Depends(get_db)):
    finalists = db.query(Finalist).order_by(Finalist.preliminary_rank.asc()).all()
    out = []
    for f in finalists:
        sub = f.official_submission
        out.append(
            FinalistOut(
                id=f.id,
                team_id=f.team_id,
                team_name=f.team.name,
                preliminary_rank=f.preliminary_rank,
                preliminary_accuracy=f.preliminary_accuracy,
                is_eligible=f.is_eligible,
                disqualification_reason=f.disqualification_reason,
                endpoint_url=sub.endpoint_url if sub else "N/A",
                deployment_version=sub.deployment_version if sub else "N/A",
                selected_at=f.selected_at,
            )
        )
    return out


@router.post("/verify")
def run_verification(
    finalist_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    if finalist_id:
        res = verification_worker.verify_finalist(db, finalist_id)
        return {"status": "success", "verified_count": 1, "finalist_id": finalist_id}
    else:
        results = verification_worker.verify_all_finalists(db)
        return {"status": "success", "verified_count": len(results)}


@router.get("/verification-status", response_model=List[FinalistVerificationOut])
def get_verifications(db: Session = Depends(get_db)):
    verifications = db.query(FinalistVerification).all()
    out = []
    for v in verifications:
        f = v.finalist
        out.append(
            FinalistVerificationOut(
                id=v.id,
                finalist_id=v.finalist_id,
                team_name=f.team.name if f and f.team else f"Team {v.finalist_id}",
                reachability_passed=v.reachability_passed,
                version_matched=v.version_matched,
                reported_version=v.reported_version,
                total_test_cases=v.total_test_cases,
                valid_responses_count=v.valid_responses_count,
                failed_responses_count=v.failed_responses_count,
                timeouts_count=v.timeouts_count,
                malformed_responses_count=v.malformed_responses_count,
                retries_count=v.retries_count,
                avg_latency_ms=v.avg_latency_ms,
                performance_score_p=v.performance_score_p,
                reliability_score_r=v.reliability_score_r,
                final_score=v.final_score,
                status=v.status,
                started_at=v.started_at,
                completed_at=v.completed_at,
                error_message=v.error_message,
            )
        )
    return out


@router.get("/final-scores")
def calculate_final_scores(db: Session = Depends(get_db)):
    ranking = final_scorer.generate_final_ranking(db)
    return {"ranking": ranking}


@router.post("/publish", response_model=LeaderboardResponse)
def publish_final_leaderboard(
    payload: LeaderboardPublishRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    snapshot = leaderboard_service.publish_final_leaderboard(
        db=db,
        admin_username=admin_user.username,
        approval_notes=payload.approval_notes,
    )
    return LeaderboardResponse(
        stage=snapshot.stage,
        version=snapshot.version,
        is_provisional=False,
        is_published=True,
        is_frozen=True,
        is_immutable=True,
        frozen_at=snapshot.approved_at,
        approved_by=snapshot.approved_by_admin,
        approved_at=snapshot.approved_at,
        approval_notes=snapshot.approval_notes,
        entries=snapshot.entries,
    )


@router.get("/audit-logs")
def get_audit_logs(
    limit: int = 50,
    action: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
    return logs
