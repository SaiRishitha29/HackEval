from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.app.db.session import get_db
from backend.app.schemas.leaderboard import LeaderboardResponse
from backend.app.services.leaderboard import leaderboard_service
from backend.app.services.auth import get_current_user
from backend.app.db.models import User
from typing import Optional

router = APIRouter(prefix="/api/leaderboard", tags=["Leaderboard"])


@router.get("/preliminary", response_model=LeaderboardResponse)
def get_preliminary_leaderboard(
    db: Session = Depends(get_db),
):
    data = leaderboard_service.get_preliminary_leaderboard(db)
    return LeaderboardResponse(**data)


@router.get("/final", response_model=LeaderboardResponse)
def get_final_leaderboard(
    db: Session = Depends(get_db),
):
    data = leaderboard_service.get_final_leaderboard(db)
    return LeaderboardResponse(**data)
