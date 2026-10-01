import pytest
import json
from backend.app.config import settings
from backend.app.db.init_db import init_database
from backend.app.mcp_server import (
    get_competition_status,
    freeze_and_select_official,
    calculate_final_scores,
    get_audit_trail,
    trigger_finalist_verification,
)
from fastapi import HTTPException


@pytest.fixture(autouse=True)
def setup_mcp_db():
    init_database()


def test_mcp_unauthorized_access():
    with pytest.raises(HTTPException) as exc_info:
        get_competition_status("invalid_token_123")
    assert exc_info.value.status_code == 403


def test_mcp_authorized_tools():
    admin_token = settings.MCP_ADMIN_API_KEY

    # 1. Status tool
    status_str = get_competition_status(admin_token)
    status_json = json.loads(status_str)
    assert "competition" in status_json
    assert "stats" in status_json

    # 2. Freeze and select tool
    freeze_str = freeze_and_select_official(admin_token)
    freeze_json = json.loads(freeze_str)
    assert freeze_json["status"] == "success"

    # 3. Final scores tool
    scores_str = calculate_final_scores(admin_token)
    scores_json = json.loads(scores_str)
    assert "formula" in scores_json
    assert "ranking" in scores_json

    # 4. Audit trail tool
    audit_str = get_audit_trail(admin_token, limit=10)
    audit_json = json.loads(audit_str)
    assert isinstance(audit_json, list)
