import io
import uuid
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.config import settings, competition_config
from backend.app.db.init_db import init_database
from backend.app.db.session import SessionLocal
from backend.app.db.models import LeaderboardSnapshot, FinalistVerification, Finalist, Submission
from backend.app.services.dataset_manager import dataset_manager
from backend.app.services.ssrf_defense import ssrf_defender


def test_complete_evaluation_workflow(tmp_path, monkeypatch):
    init_database()
    dataset_manager._ensure_synthetic_datasets()

    # Clean previous snapshots for test repeatability
    db = SessionLocal()
    db.query(LeaderboardSnapshot).delete()
    db.query(FinalistVerification).delete()
    db.query(Finalist).delete()
    db.commit()
    db.close()

    # Mock outbound finalist verification requests to return valid predictions instantly
    labels = competition_config.label_set or ["category_a", "category_b", "category_c"]

    def mock_safe_post(client, url, json_payload):
        req_action = json_payload.get("action")
        if req_action == "health_check":
            return 200, {"status": "ok", "version": "v1.1.0"}, 12.5

        cases = json_payload.get("cases", [])
        predictions = []
        for idx, c in enumerate(cases):
            cid = c.get("case_id")
            # Predict deterministically
            pred = labels[idx % len(labels)]
            predictions.append({"case_id": cid, "prediction": pred})

        return 200, {
            "request_id": json_payload.get("request_id"),
            "version": "v1.1.0",
            "predictions": predictions,
        }, 15.0

    monkeypatch.setattr(ssrf_defender, "execute_safe_post", mock_safe_post)

    with TestClient(app) as client:
        # 1. Login as default Admin
        login_resp = client.post(
            "/api/auth/login",
            data={"username": settings.INITIAL_ADMIN_USERNAME, "password": settings.INITIAL_ADMIN_PASSWORD},
        )
        assert login_resp.status_code == 200
        admin_token = login_resp.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 2. Register 3 participant teams with unique names
        run_id = uuid.uuid4().hex[:6]
        teams_tokens = []
        for i in range(1, 4):
            uname = f"e2e_{run_id}_user_{i}"
            email = f"e2e_{run_id}_{i}@hackeval.com"
            tname = f"E2E_{run_id}_Team_{i}"

            reg_resp = client.post(
                "/api/auth/register",
                json={
                    "username": uname,
                    "email": email,
                    "password": "Password123!",
                    "team_name": tname,
                },
            )
            assert reg_resp.status_code == 200, reg_resp.text

            # Login participant
            p_login = client.post(
                "/api/auth/login",
                data={"username": uname, "password": "Password123!"},
            )
            assert p_login.status_code == 200
            teams_tokens.append(p_login.json()["access_token"])

        # 3. Create submissions for teams
        # Team 1 submits 2 attempts: attempt 1 with 70% acc, attempt 2 with 90% acc
        t1_headers = {"Authorization": f"Bearer {teams_tokens[0]}"}

        file1_path = tmp_path / "t1_sub1.xlsx"
        dataset_manager.generate_sample_submission_excel(file1_path, accuracy_target=0.70)
        with open(file1_path, "rb") as f1:
            sub1_resp = client.post(
                "/api/submissions/upload",
                headers=t1_headers,
                data={
                    "endpoint_url": "https://agent.e2eteam1.com/predict",
                    "deployment_version": "v1.0.0",
                    "endpoint_freeze_declared": True,
                },
                files={"file": ("t1_sub1.xlsx", f1, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert sub1_resp.status_code == 200
        assert sub1_resp.json()["attempt_number"] == 1
        # Privacy check: preliminary_accuracy should be masked (None) for participant
        assert sub1_resp.json()["preliminary_accuracy"] is None
        assert sub1_resp.json()["preliminary_evaluated"] is True

        # Team 1 Attempt 2 (Higher accuracy 90%)
        file2_path = tmp_path / "t1_sub2.xlsx"
        dataset_manager.generate_sample_submission_excel(file2_path, accuracy_target=0.90)
        with open(file2_path, "rb") as f2:
            sub2_resp = client.post(
                "/api/submissions/upload",
                headers=t1_headers,
                data={
                    "endpoint_url": "https://agent.e2eteam1.com/predict",
                    "deployment_version": "v1.1.0",
                    "endpoint_freeze_declared": True,
                },
                files={"file": ("t1_sub2.xlsx", f2, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert sub2_resp.status_code == 200
        assert sub2_resp.json()["attempt_number"] == 2

        # Team 2 submits 1 attempt (80% accuracy)
        t2_headers = {"Authorization": f"Bearer {teams_tokens[1]}"}
        file3_path = tmp_path / "t2_sub1.xlsx"
        dataset_manager.generate_sample_submission_excel(file3_path, accuracy_target=0.80)
        with open(file3_path, "rb") as f3:
            sub3_resp = client.post(
                "/api/submissions/upload",
                headers=t2_headers,
                data={
                    "endpoint_url": "https://agent.e2eteam2.com/predict",
                    "deployment_version": "v2.0.0",
                    "endpoint_freeze_declared": True,
                },
                files={"file": ("t2_sub1.xlsx", f3, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert sub3_resp.status_code == 200

        # 4. Trigger deadline freeze & official selection
        freeze_resp = client.post("/api/admin/freeze-deadline", headers=admin_headers)
        assert freeze_resp.status_code == 200
        assert freeze_resp.json()["status"] == "success"

        # 5. Check preliminary leaderboard
        prelim_resp = client.get("/api/leaderboard/preliminary")
        assert prelim_resp.status_code == 200
        prelim_data = prelim_resp.json()
        assert prelim_data["is_provisional"] is True
        assert len(prelim_data["entries"]) >= 2
        # Team 1 with 90% should be rank 1
        assert prelim_data["entries"][0]["team_name"] == f"E2E_{run_id}_Team_1"

        # 6. Verify finalists via admin verify endpoint
        verify_resp = client.post("/api/admin/verify", headers=admin_headers)
        assert verify_resp.status_code == 200
        assert verify_resp.json()["status"] == "success"

        # Check verifications status
        v_status_resp = client.get("/api/admin/verification-status", headers=admin_headers)
        assert v_status_resp.status_code == 200
        verifications = v_status_resp.json()
        assert len(verifications) > 0
        assert verifications[0]["final_score"] is not None

        # 7. Check final scores preview
        scores_resp = client.get("/api/admin/final-scores", headers=admin_headers)
        assert scores_resp.status_code == 200
        ranking = scores_resp.json()["ranking"]
        assert len(ranking) > 0
        assert ranking[0]["rank"] == 1
        assert "final_score" in ranking[0]

        # 8. Approve and Publish final leaderboard
        pub_resp = client.post(
            "/api/admin/publish",
            headers=admin_headers,
            json={"approval_notes": "Official organizer sign-off and publication"},
        )
        assert pub_resp.status_code == 200
        pub_data = pub_resp.json()
        assert pub_data["is_published"] is True
        assert pub_data["is_immutable"] is True
        assert pub_data["stage"] == "final_published"

        # 9. Verify public final leaderboard reflects published snapshot
        final_pub_resp = client.get("/api/leaderboard/final")
        assert final_pub_resp.status_code == 200
        assert final_pub_resp.json()["is_published"] is True
        assert final_pub_resp.json()["is_immutable"] is True

        # 10. Audit log check
        audit_resp = client.get("/api/admin/audit-logs", headers=admin_headers)
        assert audit_resp.status_code == 200
        logs = audit_resp.json()
        actions = [l["action"] for l in logs]
        assert "publish_final_leaderboard" in actions
