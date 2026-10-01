import pytest
from pathlib import Path
from backend.app.services.storage import storage_service


def test_storage_save_and_sha256(tmp_path):
    data = b"Sample Excel binary mock content"
    rel_path, sha256, size = storage_service.save_submission_file(
        team_id=99, attempt=1, filename="test_predictions.xlsx", content=data
    )
    assert rel_path.startswith("team_99")
    assert len(sha256) == 64
    assert size == len(data)

    resolved = storage_service.get_submission_path(rel_path)
    assert resolved.exists()
    assert resolved.read_bytes() == data


def test_storage_path_traversal_prevention():
    with pytest.raises(PermissionError):
        storage_service.get_submission_path("../../etc/passwd")

    with pytest.raises(PermissionError):
        storage_service.get_submission_path("..\\..\\Windows\\System32\\calc.exe")
