import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Text,
)
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="participant", nullable=False)  # "participant", "admin"
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    team = relationship("Team", back_populates="members")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), unique=True, index=True, nullable=False)
    contact_email = Column(String(255), nullable=False)
    token = Column(String(100), unique=True, index=True, default=lambda: uuid.uuid4().hex)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    members = relationship("User", back_populates="team")
    submissions = relationship("Submission", back_populates="team", cascade="all, delete-orphan")
    finalist_entry = relationship("Finalist", back_populates="team", uselist=False)


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)  # 1..5

    excel_filename = Column(String(255), nullable=False)
    excel_storage_path = Column(String(512), nullable=False)
    excel_sha256 = Column(String(64), nullable=False, index=True)

    endpoint_url = Column(String(1024), nullable=False)
    deployment_version = Column(String(100), nullable=False)
    endpoint_freeze_declared = Column(Boolean, default=False, nullable=False)

    status = Column(String(50), default="received", nullable=False, index=True)
    # Statuses: "received", "validated", "invalid", "evaluated", "official_selected", "official_frozen", "failed"

    validation_findings = Column(JSON, default=dict)
    is_valid = Column(Boolean, default=False, nullable=False, index=True)
    is_official = Column(Boolean, default=False, nullable=False, index=True)

    preliminary_accuracy = Column(Float, nullable=True)  # Accuracy (0.0 to 1.0 or 0 to 100)
    total_cases = Column(Integer, nullable=True)
    correct_predictions = Column(Integer, nullable=True)

    dataset_version = Column(String(100), nullable=True)
    scoring_policy_version = Column(String(100), nullable=True)
    evaluator_version = Column(String(100), nullable=True)

    submitted_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    evaluated_at = Column(DateTime(timezone=True), nullable=True)
    client_ip = Column(String(64), nullable=True)
    idempotency_key = Column(String(128), nullable=True, index=True)

    team = relationship("Team", back_populates="submissions")
    finalist_entry = relationship("Finalist", back_populates="official_submission", uselist=False)


class Finalist(Base):
    __tablename__ = "finalists"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), unique=True, nullable=False)
    official_submission_id = Column(String(36), ForeignKey("submissions.id"), unique=True, nullable=False)
    preliminary_rank = Column(Integer, nullable=False, index=True)
    preliminary_accuracy = Column(Float, nullable=False)
    is_eligible = Column(Boolean, default=True, nullable=False)
    disqualification_reason = Column(String(512), nullable=True)
    selected_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    team = relationship("Team", back_populates="finalist_entry")
    official_submission = relationship("Submission", back_populates="finalist_entry")
    verifications = relationship("FinalistVerification", back_populates="finalist", cascade="all, delete-orphan")


class FinalistVerification(Base):
    __tablename__ = "finalist_verifications"

    id = Column(Integer, primary_key=True, index=True)
    finalist_id = Column(Integer, ForeignKey("finalists.id", ondelete="CASCADE"), nullable=False)
    submission_id = Column(String(36), ForeignKey("submissions.id"), nullable=False)

    reachability_passed = Column(Boolean, default=False, nullable=False)
    version_matched = Column(Boolean, default=False, nullable=False)
    reported_version = Column(String(100), nullable=True)

    total_test_cases = Column(Integer, default=0, nullable=False)
    valid_responses_count = Column(Integer, default=0, nullable=False)
    failed_responses_count = Column(Integer, default=0, nullable=False)
    timeouts_count = Column(Integer, default=0, nullable=False)
    malformed_responses_count = Column(Integer, default=0, nullable=False)
    retries_count = Column(Integer, default=0, nullable=False)
    avg_latency_ms = Column(Float, default=0.0, nullable=False)

    performance_score_p = Column(Float, nullable=True)  # Normalized 0..100
    reliability_score_r = Column(Float, nullable=True)  # Normalized 0..100
    final_score = Column(Float, nullable=True)          # 0.823529*P + 0.176471*R

    status = Column(String(50), default="queued", nullable=False)  # "queued", "running", "completed", "failed"
    evidence_storage_path = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)

    started_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    finalist = relationship("Finalist", back_populates="verifications")


class LeaderboardSnapshot(Base):
    __tablename__ = "leaderboard_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    stage = Column(String(50), nullable=False, index=True)  # "preliminary_provisional", "preliminary_frozen", "final_provisional", "final_published"
    version = Column(Integer, nullable=False, default=1)
    entries = Column(JSON, nullable=False)  # List of ranked team items
    is_frozen = Column(Boolean, default=False, nullable=False)
    is_immutable = Column(Boolean, default=False, nullable=False)
    approved_by_admin = Column(String(100), nullable=True)
    approval_notes = Column(Text, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    actor_type = Column(String(50), nullable=False)  # "user", "admin", "system", "mcp"
    actor_id = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(String(100), nullable=True)
    details = Column(JSON, default=dict)
    ip_address = Column(String(64), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
