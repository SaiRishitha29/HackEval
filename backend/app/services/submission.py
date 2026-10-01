import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, UploadFile
from backend.app.config import competition_config, settings
from backend.app.db.models import Submission, Team, AuditLog
from backend.app.services.storage import storage_service
from backend.app.services.evaluator import evaluator
from backend.app.services.dataset_manager import dataset_manager
from backend.app.services.audit import record_audit

logger = logging.getLogger(__name__)


class SubmissionService:
    def create_submission(
        self,
        db: Session,
        team_id: int,
        file: UploadFile,
        endpoint_url: str,
        deployment_version: str,
        endpoint_freeze_declared: bool,
        client_ip: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> Submission:
        # Check team existence
        team = db.query(Team).filter(Team.id == team_id).first()
        if not team:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

        # Check deadline
        now = datetime.now(timezone.utc)
        if competition_config.deadline_utc:
            try:
                deadline = datetime.fromisoformat(competition_config.deadline_utc.replace("Z", "+00:00"))
                if now > deadline and competition_config.reject_submissions_after_deadline:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Submissions are closed! Deadline has passed."
                    )
            except ValueError:
                pass

        # Check idempotency
        if idempotency_key:
            existing = (
                db.query(Submission)
                .filter(Submission.team_id == team_id, Submission.idempotency_key == idempotency_key)
                .first()
            )
            if existing:
                logger.info("Idempotent request matched for submission %s", existing.id)
                return existing

        # Check submission attempt limit (max 5)
        current_attempts = (
            db.query(Submission)
            .filter(Submission.team_id == team_id)
            .count()
        )
        if current_attempts >= competition_config.max_attempts_per_team:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum submission limit reached ({competition_config.max_attempts_per_team} attempts per team)."
            )

        attempt_number = current_attempts + 1

        # Check file extension
        filename = file.filename or "predictions.xlsx"
        ext = Path(filename).suffix.lower()
        if ext not in competition_config.accepted_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file extension '{ext}'. Accepted extensions: {competition_config.accepted_extensions}"
            )

        # Read and check file content length
        content = file.file.read()
        if len(content) > settings.MAX_SUBMISSION_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of {settings.MAX_SUBMISSION_FILE_SIZE_BYTES // (1024 * 1024)}MB"
            )

        # Check endpoint scheme: must be https (allow http in dev mode if configured)
        clean_endpoint = endpoint_url.strip()
        if not clean_endpoint.startswith("https://"):
            if not (settings.ALLOW_HTTP_MOCK_ENDPOINTS_IN_DEV and clean_endpoint.startswith("http://")):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Endpoint URL must use secure HTTPS scheme (https://...)"
                )

        if not deployment_version.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Deployment version must be specified"
            )

        if not endpoint_freeze_declared:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must declare that your endpoint deployment is frozen and ready for evaluation"
            )

        # Save file to private object storage
        rel_storage_path, sha256_hash, file_size = storage_service.save_submission_file(
            team_id=team_id,
            attempt=attempt_number,
            filename=filename,
            content=content
        )

        full_file_path = storage_service.get_submission_path(rel_storage_path)

        # Deterministic Excel validation & evaluation
        ground_truth = dataset_manager.get_preliminary_ground_truth()
        expected_cids = set(ground_truth.keys())

        is_valid, findings, parsed_predictions = evaluator.validate_and_parse_excel(
            full_file_path, expected_case_ids=expected_cids
        )

        accuracy = None
        total_cases = None
        correct_cases = None
        eval_status = "validated" if is_valid else "invalid"

        if is_valid and parsed_predictions:
            eval_metrics = evaluator.evaluate_predictions(
                predictions_map=parsed_predictions,
                ground_truth_map=ground_truth
            )
            accuracy = eval_metrics["accuracy"]
            total_cases = eval_metrics["total_cases"]
            correct_cases = eval_metrics["correct_predictions"]
            eval_status = "evaluated"

        # Create submission record
        sub = Submission(
            team_id=team_id,
            attempt_number=attempt_number,
            excel_filename=filename,
            excel_storage_path=rel_storage_path,
            excel_sha256=sha256_hash,
            endpoint_url=clean_endpoint,
            deployment_version=deployment_version.strip(),
            endpoint_freeze_declared=endpoint_freeze_declared,
            status=eval_status,
            validation_findings=findings,
            is_valid=is_valid,
            is_official=False,
            preliminary_accuracy=accuracy,
            total_cases=total_cases,
            correct_predictions=correct_cases,
            dataset_version=competition_config.preliminary_dataset_version or "synthetic-prelim-v1.0",
            scoring_policy_version=competition_config.scoring_policy_version,
            evaluator_version=evaluator.scoring_policy_version,
            client_ip=client_ip,
            idempotency_key=idempotency_key,
            evaluated_at=datetime.now(timezone.utc) if is_valid else None
        )

        db.add(sub)
        db.commit()
        db.refresh(sub)

        # Audit log
        record_audit(
            db=db,
            actor_type="team",
            actor_id=str(team_id),
            action="submit_attempt",
            resource_type="submission",
            resource_id=sub.id,
            details={
                "attempt_number": attempt_number,
                "is_valid": is_valid,
                "sha256": sha256_hash,
                "endpoint_url": clean_endpoint,
                "deployment_version": deployment_version,
            },
            ip_address=client_ip
        )

        return sub


submission_service = SubmissionService()
