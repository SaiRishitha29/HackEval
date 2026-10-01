import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from backend.app.db.models import LeaderboardSnapshot, Finalist, Team
from backend.app.services.scorer import final_scorer
from backend.app.services.audit import record_audit

logger = logging.getLogger(__name__)


class LeaderboardService:
    def get_preliminary_leaderboard(self, db: Session, user_role: str = "participant") -> Dict[str, Any]:
        """
        Fetches the current or frozen preliminary leaderboard.
        Clearly tags results as provisional.
        """
        snapshot = (
            db.query(LeaderboardSnapshot)
            .filter(LeaderboardSnapshot.stage.in_(["preliminary_provisional", "preliminary_frozen"]))
            .order_by(LeaderboardSnapshot.id.desc())
            .first()
        )

        if not snapshot:
            return {
                "stage": "preliminary_provisional",
                "version": 1,
                "is_provisional": True,
                "is_published": False,
                "is_frozen": False,
                "entries": [],
            }

        entries = snapshot.entries or []

        # If user is participant and submissions are still open, do not reveal accuracy!
        # (Though official preliminary freeze snapshot only occurs at deadline)
        return {
            "stage": snapshot.stage,
            "version": snapshot.version,
            "is_provisional": True,
            "is_published": False,
            "is_frozen": snapshot.is_frozen,
            "frozen_at": snapshot.approved_at.isoformat() if snapshot.approved_at else None,
            "approved_by": snapshot.approved_by_admin,
            "entries": entries,
        }

    def get_final_leaderboard(self, db: Session) -> Dict[str, Any]:
        """
        Fetches the official published final leaderboard if published.
        If unpublished, returns provisional final state for admins or empty for participants.
        """
        published_snapshot = (
            db.query(LeaderboardSnapshot)
            .filter(LeaderboardSnapshot.stage == "final_published")
            .order_by(LeaderboardSnapshot.id.desc())
            .first()
        )

        if published_snapshot:
            return {
                "stage": "final_published",
                "version": published_snapshot.version,
                "is_provisional": False,
                "is_published": True,
                "is_frozen": True,
                "is_immutable": True,
                "approved_by": published_snapshot.approved_by_admin,
                "approved_at": published_snapshot.approved_at.isoformat() if published_snapshot.approved_at else None,
                "approval_notes": published_snapshot.approval_notes,
                "entries": published_snapshot.entries,
            }

        # If not published yet, generate provisional live preview
        provisional_entries = final_scorer.generate_final_ranking(db)
        return {
            "stage": "final_provisional",
            "version": 0,
            "is_provisional": True,
            "is_published": False,
            "is_frozen": False,
            "is_immutable": False,
            "approved_by": None,
            "approved_at": None,
            "entries": provisional_entries,
        }

    def publish_final_leaderboard(
        self, db: Session, admin_username: str, approval_notes: str = "Authorized administrative publication"
    ) -> LeaderboardSnapshot:
        """
        Administrative action: Permanently publishes and freezes the final leaderboard.
        Results become strictly immutable.
        """
        # Ensure that no previous final publication is overwritten carelessly
        existing_published = (
            db.query(LeaderboardSnapshot)
            .filter(LeaderboardSnapshot.stage == "final_published", LeaderboardSnapshot.is_immutable == True)
            .first()
        )
        if existing_published:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Final leaderboard version {existing_published.version} has already been published and is immutable."
            )

        final_ranking = final_scorer.generate_final_ranking(db)
        if not final_ranking:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot publish leaderboard: No verified finalists found."
            )

        now = datetime.now(timezone.utc)
        snapshot = LeaderboardSnapshot(
            stage="final_published",
            version=1,
            entries=final_ranking,
            is_frozen=True,
            is_immutable=True,
            approved_by_admin=admin_username,
            approval_notes=approval_notes,
            approved_at=now,
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        record_audit(
            db=db,
            actor_type="admin",
            actor_id=admin_username,
            action="publish_final_leaderboard",
            resource_type="leaderboard",
            resource_id=str(snapshot.id),
            details={
                "snapshot_version": snapshot.version,
                "entries_count": len(final_ranking),
                "approval_notes": approval_notes,
            },
        )

        return snapshot


leaderboard_service = LeaderboardService()
