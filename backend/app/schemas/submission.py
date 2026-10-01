from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class SubmissionCreate(BaseModel):
    endpoint_url: str = Field(..., description="Participant-hosted HTTPS endpoint URL")
    deployment_version: str = Field(..., description="Declared deployment version string (e.g. v1.0.0 or git commit)")
    endpoint_freeze_declared: bool = Field(..., description="Declaration that the endpoint is frozen and ready")
    idempotency_key: Optional[str] = Field(None, description="Client idempotency key")


class SubmissionValidationFinding(BaseModel):
    is_valid: bool
    status: str
    errors: List[str] = []
    warnings: List[str] = []
    total_rows: int = 0
    valid_predictions_count: int = 0
    columns_detected: List[str] = []


class ParticipantSubmissionOut(BaseModel):
    id: str
    attempt_number: int
    excel_filename: str
    excel_sha256: str
    endpoint_url: str
    deployment_version: str
    endpoint_freeze_declared: bool
    status: str
    is_valid: bool
    is_official: bool
    submitted_at: datetime
    validation_findings: Dict[str, Any] = {}

    # Preliminary scores are hidden before deadline per policy:
    preliminary_accuracy: Optional[float] = None
    preliminary_evaluated: bool = False

    class Config:
        from_attributes = True


class AdminSubmissionOut(ParticipantSubmissionOut):
    # Admins can see raw preliminary metrics and dataset details
    preliminary_accuracy: Optional[float] = None
    total_cases: Optional[int] = None
    correct_predictions: Optional[int] = None
    dataset_version: Optional[str] = None
    scoring_policy_version: Optional[str] = None
    evaluator_version: Optional[str] = None
    client_ip: Optional[str] = None

    class Config:
        from_attributes = True
