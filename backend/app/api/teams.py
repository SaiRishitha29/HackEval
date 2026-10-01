from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.app.db.session import get_db
from backend.app.db.models import User, Team, Submission
from backend.app.schemas.team import TeamCreate, TeamOut
from backend.app.services.auth import get_current_user
from backend.app.config import competition_config

router = APIRouter(prefix="/api/teams", tags=["Teams"])


@router.post("/register", response_model=TeamOut)
def register_team(
    payload: TeamCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = db.query(Team).filter(Team.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Team name already taken")

    team = Team(name=payload.name, contact_email=payload.contact_email)
    db.add(team)
    db.flush()

    # Assign current user to team if not assigned
    if not current_user.team_id:
        current_user.team_id = team.id

    db.commit()
    db.refresh(team)

    return TeamOut(
        id=team.id,
        name=team.name,
        contact_email=team.contact_email,
        token=team.token,
        created_at=team.created_at,
        submissions_count=0,
        remaining_attempts=competition_config.max_attempts_per_team,
        members=[current_user],
    )


@router.get("/my-team", response_model=TeamOut)
def get_my_team(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.team_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User is not part of any team")

    team = db.query(Team).filter(Team.id == current_user.team_id).first()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    sub_count = db.query(Submission).filter(Submission.team_id == team.id).count()
    remaining = max(0, competition_config.max_attempts_per_team - sub_count)

    return TeamOut(
        id=team.id,
        name=team.name,
        contact_email=team.contact_email,
        token=team.token,
        created_at=team.created_at,
        submissions_count=sub_count,
        remaining_attempts=remaining,
        members=team.members,
    )
