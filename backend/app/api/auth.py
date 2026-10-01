from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from backend.app.db.session import get_db
from backend.app.db.models import User, Team
from backend.app.schemas.auth import UserCreate, UserOut, Token, UserLogin
from backend.app.services.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
)
from backend.app.services.audit import record_audit

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserOut)
def register_user(payload: UserCreate, db: Session = Depends(get_db)):
    # Check if username or email exists
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already registered")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    team_id = None
    if payload.team_name:
        existing_team = db.query(Team).filter(Team.name == payload.team_name).first()
        if existing_team:
            team_id = existing_team.id
        else:
            new_team = Team(name=payload.team_name, contact_email=payload.email)
            db.add(new_team)
            db.flush()
            team_id = new_team.id

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        role="participant",
        team_id=team_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    record_audit(
        db=db,
        actor_type="user",
        actor_id=user.username,
        action="user_registered",
        resource_type="user",
        resource_id=str(user.id),
        details={"team_id": team_id},
    )

    return user


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "team_id": user.team_id}
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        username=user.username,
        team_id=user.team_id,
    )


@router.post("/login-json", response_model=Token)
def login_json(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "team_id": user.team_id}
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        username=user.username,
        team_id=user.team_id,
    )


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
