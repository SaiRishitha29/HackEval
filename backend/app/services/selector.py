import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc
from backend.app.config import competition_config
from backend.app.db.models import Submission, Team, Finalist, LeaderboardSnapshot
from backend.app.services.audit import record_audit

logger = logging.getLogger(__name__)


class OfficialSelectorService:
    def freeze_and_select_official_submissions(
        self, db: Session, admin_username: str = "admin", deadline_override_iso: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes the official selection rule:
        1. Freezes open submissions.
        2. Filters valid submissions received before the deadline for each team.
        3. Deterministically selects the official submission with:
           - Highest preliminary accuracy.
           - Tie-breaker 1: Latest submission timestamp (submitted_at desc).
           - Tie-breaker 2: Submission ID (lexicographical string desc).
        4. Freezes the provisional preliminary leaderboard.
        5. Selects top-20 eligible finalists.
        """
        now = datetime.now(timezone.utc)
        deadline_str = deadline_override_iso or competition_config.deadline_utc

        cutoff_time = now
        if deadline_str:
            try:
                cutoff_time = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
            except ValueError:
                cutoff_time = now

        # Reset any previous official flags to ensure clean idempotency
        teams = db.query(Team).all()
        selected_count = 0
        official_submissions_by_team: Dict[int, Submission] = {}

        for team in teams:
            # Query all valid submissions by this team submitted before deadline
            query = (
                db.query(Submission)
                .filter(
                    Submission.team_id == team.id,
                    Submission.is_valid == True,
                    Submission.submitted_at <= cutoff_time,
                )
            )
            valid_subs = query.all()

            if not valid_subs:
                continue

            # Deterministic sort:
            # 1. preliminary_accuracy desc (None treated as -1)
            # 2. submitted_at desc
            # 3. id desc
            sorted_subs = sorted(
                valid_subs,
                key=lambda s: (
                    s.preliminary_accuracy if s.preliminary_accuracy is not None else -1.0,
                    s.submitted_at.timestamp() if s.submitted_at else 0.0,
                    str(s.id),
                ),
                reverse=True,
            )

            best_sub = sorted_subs[0]

            # Mark all team's submissions official = False, best = True
            for s in team.submissions:
                s.is_official = (s.id == best_sub.id)
                if s.is_official:
                    s.status = "official_frozen"

            official_submissions_by_team[team.id] = best_sub
            selected_count += 1

        db.commit()

        # Build preliminary ranking
        # Rank teams by their official submission's preliminary accuracy
        ranked_teams: List[Tuple[Team, Submission]] = []
        for team in teams:
            if team.id in official_submissions_by_team:
                ranked_teams.append((team, official_submissions_by_team[team.id]))

        ranked_teams.sort(
            key=lambda item: (
                item[1].preliminary_accuracy if item[1].preliminary_accuracy is not None else -1.0,
                item[1].submitted_at.timestamp() if item[1].submitted_at else 0.0,
                str(item[1].id),
            ),
            reverse=True,
        )

        # Clear existing finalists and populate fresh top 20
        db.query(Finalist).delete()
        finalists_created = []

        leaderboard_entries = []
        finalist_cutoff = competition_config.finalist_count  # 20

        for rank_idx, (team, sub) in enumerate(ranked_teams, start=1):
            is_finalist = rank_idx <= finalist_cutoff
            leaderboard_entries.append({
                "rank": rank_idx,
                "team_id": team.id,
                "team_name": team.name,
                "submission_id": sub.id,
                "preliminary_accuracy": sub.preliminary_accuracy,
                "submission_timestamp": sub.submitted_at.isoformat() if sub.submitted_at else None,
                "is_finalist": is_finalist,
                "endpoint_url": sub.endpoint_url,
                "deployment_version": sub.deployment_version,
            })

            if is_finalist:
                finalist_record = Finalist(
                    team_id=team.id,
                    official_submission_id=sub.id,
                    preliminary_rank=rank_idx,
                    preliminary_accuracy=sub.preliminary_accuracy or 0.0,
                    is_eligible=True,
                )
                db.add(finalist_record)
                finalists_created.append(finalist_record)

        # Create frozen preliminary leaderboard snapshot
        snapshot = LeaderboardSnapshot(
            stage="preliminary_frozen",
            version=1,
            entries=leaderboard_entries,
            is_frozen=True,
            is_immutable=False,
            approved_by_admin=admin_username,
            approval_notes="Provisional preliminary leaderboard frozen at deadline",
            approved_at=now,
        )
        db.add(snapshot)
        db.commit()

        record_audit(
            db=db,
            actor_type="admin",
            actor_id=admin_username,
            action="freeze_and_select_official",
            resource_type="competition",
            resource_id="preliminary",
            details={
                "teams_evaluated": len(teams),
                "official_selected_count": selected_count,
                "finalists_count": len(finalists_created),
                "cutoff_time": cutoff_time.isoformat(),
            },
        )

        return {
            "status": "success",
            "message": f"Successfully selected official submissions for {selected_count} teams and identified top {len(finalists_created)} finalists.",
            "teams_with_official_submission": selected_count,
            "finalists_selected": len(finalists_created),
            "snapshot_id": snapshot.id,
        }


selector_service = OfficialSelectorService()
