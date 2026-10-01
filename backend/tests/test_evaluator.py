import pytest
import pandas as pd
from pathlib import Path
from backend.app.services.evaluator import evaluator


@pytest.fixture
def sample_ground_truth():
    return {
        "CASE_0001": "category_a",
        "CASE_0002": "category_b",
        "CASE_0003": "category_c",
        "CASE_0004": "category_a",
        "CASE_0005": "category_b",
    }


def test_evaluator_valid_excel_matches_by_case_id_not_row_order(tmp_path, sample_ground_truth):
    # Reverse row order
    reversed_rows = [
        {"case_id": "CASE_0005", "prediction": "category_b"},
        {"case_id": "CASE_0004", "prediction": "category_a"},
        {"case_id": "CASE_0003", "prediction": "category_c"},
        {"case_id": "CASE_0002", "prediction": "category_b"},
        {"case_id": "CASE_0001", "prediction": "category_a"},
    ]
    file_path = tmp_path / "reversed.xlsx"
    pd.DataFrame(reversed_rows).to_excel(file_path, index=False, engine="openpyxl")

    is_valid, findings, preds = evaluator.validate_and_parse_excel(
        file_path, expected_case_ids=set(sample_ground_truth.keys())
    )
    assert is_valid is True
    assert len(findings["errors"]) == 0

    metrics = evaluator.evaluate_predictions(preds, sample_ground_truth)
    assert metrics["accuracy"] == 1.0
    assert metrics["correct_predictions"] == 5
    assert metrics["total_cases"] == 5


def test_evaluator_duplicate_case_id(tmp_path, sample_ground_truth):
    rows = [
        {"case_id": "CASE_0001", "prediction": "category_a"},
        {"case_id": "CASE_0001", "prediction": "category_b"},  # Duplicate!
        {"case_id": "CASE_0002", "prediction": "category_b"},
    ]
    file_path = tmp_path / "dups.xlsx"
    pd.DataFrame(rows).to_excel(file_path, index=False, engine="openpyxl")

    is_valid, findings, preds = evaluator.validate_and_parse_excel(
        file_path, expected_case_ids=set(sample_ground_truth.keys())
    )
    assert is_valid is False
    assert any("Duplicate" in e for e in findings["errors"])


def test_evaluator_missing_predictions(tmp_path, sample_ground_truth):
    rows = [
        {"case_id": "CASE_0001", "prediction": "category_a"},
        {"case_id": "CASE_0002", "prediction": None},  # Missing
        {"case_id": "CASE_0003", "prediction": ""},    # Empty
    ]
    file_path = tmp_path / "missing_preds.xlsx"
    pd.DataFrame(rows).to_excel(file_path, index=False, engine="openpyxl")

    is_valid, findings, preds = evaluator.validate_and_parse_excel(
        file_path, expected_case_ids=set(sample_ground_truth.keys())
    )
    assert is_valid is False
    assert any("Missing predictions" in e for e in findings["errors"])


def test_evaluator_missing_and_unexpected_case_ids(tmp_path, sample_ground_truth):
    rows = [
        {"case_id": "CASE_0001", "prediction": "category_a"},
        {"case_id": "CASE_9999", "prediction": "category_b"},  # Unexpected!
    ]
    file_path = tmp_path / "unexpected.xlsx"
    pd.DataFrame(rows).to_excel(file_path, index=False, engine="openpyxl")

    is_valid, findings, preds = evaluator.validate_and_parse_excel(
        file_path, expected_case_ids=set(sample_ground_truth.keys())
    )
    assert is_valid is False
    assert any("missing" in e for e in findings["errors"])
    assert any("unexpected" in e for e in findings["errors"])


def test_evaluator_invalid_label(tmp_path, sample_ground_truth):
    rows = [
        {"case_id": f"CASE_000{i}", "prediction": "invalid_alien_category"}
        for i in range(1, 6)
    ]
    file_path = tmp_path / "invalid_label.xlsx"
    pd.DataFrame(rows).to_excel(file_path, index=False, engine="openpyxl")

    is_valid, findings, preds = evaluator.validate_and_parse_excel(
        file_path, expected_case_ids=set(sample_ground_truth.keys())
    )
    assert is_valid is False
    assert any("Invalid prediction labels" in e for e in findings["errors"])


def test_evaluator_malformed_file(tmp_path):
    file_path = tmp_path / "corrupted.xlsx"
    file_path.write_bytes(b"This is not a zip or excel file at all!")

    is_valid, findings, preds = evaluator.validate_and_parse_excel(file_path)
    assert is_valid is False
    assert any("Malformed Excel file" in e for e in findings["errors"])
