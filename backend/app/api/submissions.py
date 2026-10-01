from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from typing import List, Optional
from sqlalchemy.orm import Session
from backend.app.db.session import get_db
from backend.app.db.models import User, Submission, Team
from backend.app.schemas.submission import ParticipantSubmissionOut, AdminSubmissionOut
from backend.app.services.auth import get_current_user, require_participant_team
from backend.app.services.submission import submission_service
from backend.app.config import competition_config

router = APIRouter(prefix="/api/submissions", tags=["Submissions"])


@router.post("/upload", response_model=ParticipantSubmissionOut)
def upload_submission(
    request: Request,
    file: UploadFile = File(...),
    endpoint_url: str = Form(...),
    deployment_version: str = Form(...),
    endpoint_freeze_declared: bool = Form(...),
    idempotency_key: Optional[str] = Form(None),
    current_user: User = Depends(require_participant_team),
    db: Session = Depends(get_db),
):
    team_id = current_user.team_id
    if not team_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You must belong to a team to submit.")

    client_ip = request.client.host if request.client else None

    sub = submission_service.create_submission(
        db=db,
        team_id=team_id,
        file=file,
        endpoint_url=endpoint_url,
        deployment_version=deployment_version,
        endpoint_freeze_declared=endpoint_freeze_declared,
        client_ip=client_ip,
        idempotency_key=idempotency_key,
    )

    # Participant response masking: do not reveal preliminary scores while open
    resp = ParticipantSubmissionOut.model_validate(sub)
    if not competition_config.reveal_preliminary_scores_before_deadline:
        resp.preliminary_accuracy = None
        resp.preliminary_evaluated = sub.preliminary_accuracy is not None

    return resp


@router.get("/my-submissions", response_model=List[ParticipantSubmissionOut])
def get_my_submissions(
    current_user: User = Depends(require_participant_team),
    db: Session = Depends(get_db),
):
    team_id = current_user.team_id
    if not team_id:
        return []

    subs = (
        db.query(Submission)
        .filter(Submission.team_id == team_id)
        .order_by(Submission.attempt_number.asc())
        .all()
    )

    out = []
    for s in subs:
        p_out = ParticipantSubmissionOut.model_validate(s)
        # Check score reveal policy
        if not competition_config.reveal_preliminary_scores_before_deadline:
            p_out.preliminary_accuracy = None
            p_out.preliminary_evaluated = s.preliminary_accuracy is not None
        out.append(p_out)

    return out


@router.get("/{submission_id}", response_model=ParticipantSubmissionOut)
def get_submission_details(
    submission_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sub = db.query(Submission).filter(Submission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    if current_user.role != "admin" and sub.team_id != current_user.team_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if current_user.role == "admin":
        return AdminSubmissionOut.model_validate(sub)

    p_out = ParticipantSubmissionOut.model_validate(sub)
    if not competition_config.reveal_preliminary_scores_before_deadline:
        p_out.preliminary_accuracy = None
        p_out.preliminary_evaluated = sub.preliminary_accuracy is not None
    return p_out
