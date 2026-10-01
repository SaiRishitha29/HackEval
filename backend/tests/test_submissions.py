import pytest
import io
import pandas as pd
from datetime import datetime, timezone, timedelta
from fastapi import UploadFile, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.db.session import Base
from backend.app.db.models import User, Team, Submission
from backend.app.services.submission import submission_service
from backend.app.services.dataset_manager import dataset_manager
from backend.app.config import competition_config


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_team(db_session):
    team = Team(name="Alpha Innovators", contact_email="alpha@test.com")
    db_session.add(team)
    db_session.commit()
    db_session.refresh(team)
    return team


def make_upload_file(filename: str, content: bytes) -> UploadFile:
    file_obj = io.BytesIO(content)
    return UploadFile(filename=filename, file=file_obj)


def test_submission_5_attempt_limit(db_session, test_team, tmp_path):
    # Create sample valid excel
    excel_path = tmp_path / "valid.xlsx"
    dataset_manager.generate_sample_submission_excel(excel_path, accuracy_target=0.9)
    excel_bytes = excel_path.read_bytes()

    for attempt in range(1, 6):
        file = make_upload_file(f"attempt_{attempt}.xlsx", excel_bytes)
        sub = submission_service.create_submission(
            db=db_session,
            team_id=test_team.id,
            file=file,
            endpoint_url="https://agent.alphateam.com/predict",
            deployment_version=f"v1.{attempt}.0",
            endpoint_freeze_declared=True,
        )
        assert sub.attempt_number == attempt
        assert sub.is_valid is True

    # 6th attempt must be rejected
    with pytest.raises(HTTPException) as exc_info:
        file = make_upload_file("attempt_6.xlsx", excel_bytes)
        submission_service.create_submission(
            db=db_session,
            team_id=test_team.id,
            file=file,
            endpoint_url="https://agent.alphateam.com/predict",
            deployment_version="v1.6.0",
            endpoint_freeze_declared=True,
        )
    assert exc_info.value.status_code == 400
    assert "Maximum submission limit reached" in exc_info.value.detail


def test_submission_rejects_non_xlsx(db_session, test_team):
    file = make_upload_file("predictions.csv", b"case_id,prediction\nCASE_0001,category_a")
    with pytest.raises(HTTPException) as exc_info:
        submission_service.create_submission(
            db=db_session,
            team_id=test_team.id,
            file=file,
            endpoint_url="https://agent.alphateam.com/predict",
            deployment_version="v1.0.0",
            endpoint_freeze_declared=True,
        )
    assert exc_info.value.status_code == 400
    assert "Invalid file extension" in exc_info.value.detail


def test_submission_rejects_insecure_http_when_disallowed(db_session, test_team, tmp_path, monkeypatch):
    import backend.app.config
    monkeypatch.setattr(backend.app.config.settings, "ALLOW_HTTP_MOCK_ENDPOINTS_IN_DEV", False)

    excel_path = tmp_path / "valid.xlsx"
    dataset_manager.generate_sample_submission_excel(excel_path, accuracy_target=0.8)
    file = make_upload_file("valid.xlsx", excel_path.read_bytes())

    with pytest.raises(HTTPException) as exc_info:
        submission_service.create_submission(
            db=db_session,
            team_id=test_team.id,
            file=file,
            endpoint_url="http://insecure-agent.alphateam.com/predict",
            deployment_version="v1.0.0",
            endpoint_freeze_declared=True,
        )
    assert exc_info.value.status_code == 400
    assert "HTTPS" in exc_info.value.detail


def test_submission_idempotency(db_session, test_team, tmp_path):
    excel_path = tmp_path / "valid.xlsx"
    dataset_manager.generate_sample_submission_excel(excel_path, accuracy_target=0.85)
    file_bytes = excel_path.read_bytes()

    sub1 = submission_service.create_submission(
        db=db_session,
        team_id=test_team.id,
        file=make_upload_file("valid.xlsx", file_bytes),
        endpoint_url="https://agent.alphateam.com/predict",
        deployment_version="v1.0.0",
        endpoint_freeze_declared=True,
        idempotency_key="unique-req-key-12345",
    )

    sub2 = submission_service.create_submission(
        db=db_session,
        team_id=test_team.id,
        file=make_upload_file("valid.xlsx", file_bytes),
        endpoint_url="https://agent.alphateam.com/predict",
        deployment_version="v1.0.0",
        endpoint_freeze_declared=True,
        idempotency_key="unique-req-key-12345",
    )

    assert sub1.id == sub2.id
    assert sub2.attempt_number == 1
