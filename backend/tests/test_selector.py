import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.db.session import Base
from backend.app.db.models import Team, Submission, Finalist, LeaderboardSnapshot
from backend.app.services.selector import selector_service


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


def test_official_selection_best_accuracy(db_session):
    team = Team(name="Team Beta", contact_email="beta@test.com")
    db_session.add(team)
    db_session.commit()

    now = datetime.now(timezone.utc)

    # Sub 1: accuracy 0.70
    s1 = Submission(
        team_id=team.id, attempt_number=1, excel_filename="sub1.xlsx", excel_storage_path="path1",
        excel_sha256="hash1", endpoint_url="https://beta.com/predict", deployment_version="v1",
        endpoint_freeze_declared=True, is_valid=True, preliminary_accuracy=0.70, submitted_at=now - timedelta(hours=3)
    )
    # Sub 2: accuracy 0.92 (Best)
    s2 = Submission(
        team_id=team.id, attempt_number=2, excel_filename="sub2.xlsx", excel_storage_path="path2",
        excel_sha256="hash2", endpoint_url="https://beta.com/predict", deployment_version="v2",
        endpoint_freeze_declared=True, is_valid=True, preliminary_accuracy=0.92, submitted_at=now - timedelta(hours=2)
    )
    # Sub 3: accuracy 0.85
    s3 = Submission(
        team_id=team.id, attempt_number=3, excel_filename="sub3.xlsx", excel_storage_path="path3",
        excel_sha256="hash3", endpoint_url="https://beta.com/predict", deployment_version="v3",
        endpoint_freeze_declared=True, is_valid=True, preliminary_accuracy=0.85, submitted_at=now - timedelta(hours=1)
    )
    # Sub 4: invalid sub (accuracy 0.99 but invalid)
    s4 = Submission(
        team_id=team.id, attempt_number=4, excel_filename="sub4.xlsx", excel_storage_path="path4",
        excel_sha256="hash4", endpoint_url="https://beta.com/predict", deployment_version="v4",
        endpoint_freeze_declared=True, is_valid=False, preliminary_accuracy=0.99, submitted_at=now
    )

    db_session.add_all([s1, s2, s3, s4])
    db_session.commit()

    res = selector_service.freeze_and_select_official_submissions(db_session)
    assert res["status"] == "success"

    db_session.refresh(s1)
    db_session.refresh(s2)
    db_session.refresh(s3)
    db_session.refresh(s4)

    assert s2.is_official is True
    assert s1.is_official is False
    assert s3.is_official is False
    assert s4.is_official is False


def test_official_selection_timestamp_tiebreaker(db_session):
    team = Team(name="Team Gamma", contact_email="gamma@test.com")
    db_session.add(team)
    db_session.commit()

    base_time = datetime.now(timezone.utc)

    # Identical accuracy (0.88), but s2 is submitted later
    s1 = Submission(
        team_id=team.id, attempt_number=1, excel_filename="sub1.xlsx", excel_storage_path="p1",
        excel_sha256="h1", endpoint_url="https://gamma.com", deployment_version="v1",
        endpoint_freeze_declared=True, is_valid=True, preliminary_accuracy=0.88,
        submitted_at=base_time - timedelta(minutes=30)
    )
    s2 = Submission(
        team_id=team.id, attempt_number=2, excel_filename="sub2.xlsx", excel_storage_path="p2",
        excel_sha256="h2", endpoint_url="https://gamma.com", deployment_version="v2",
        endpoint_freeze_declared=True, is_valid=True, preliminary_accuracy=0.88,
        submitted_at=base_time - timedelta(minutes=10)
    )

    db_session.add_all([s1, s2])
    db_session.commit()

    selector_service.freeze_and_select_official_submissions(db_session)

    db_session.refresh(s1)
    db_session.refresh(s2)

    assert s2.is_official is True
    assert s1.is_official is False


def test_official_selection_top_20_finalists(db_session):
    # Create 25 teams
    now = datetime.now(timezone.utc)
    for i in range(1, 26):
        team = Team(name=f"Team_{i:02d}", contact_email=f"team{i}@test.com")
        db_session.add(team)
        db_session.flush()

        acc = 0.50 + (i * 0.015)  # Team 25 has highest acc (0.875)
        sub = Submission(
            team_id=team.id, attempt_number=1, excel_filename="f.xlsx", excel_storage_path="p",
            excel_sha256=f"hash_{i}", endpoint_url=f"https://team{i}.com", deployment_version="v1.0",
            endpoint_freeze_declared=True, is_valid=True, preliminary_accuracy=acc, submitted_at=now
        )
        db_session.add(sub)

    db_session.commit()

    res = selector_service.freeze_and_select_official_submissions(db_session)
    assert res["finalists_selected"] == 20

    finalists = db_session.query(Finalist).order_by(Finalist.preliminary_rank.asc()).all()
    assert len(finalists) == 20
    assert finalists[0].preliminary_rank == 1
    # Team 25 should be rank 1
    assert finalists[0].team.name == "Team_25"
