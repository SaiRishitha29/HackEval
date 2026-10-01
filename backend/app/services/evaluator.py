import logging
import openpyxl
import pandas as pd
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Set
from backend.app.config import competition_config

logger = logging.getLogger(__name__)

EVALUATOR_VERSION = "hackeval-evaluator-v1.0.0"


class PreliminaryEvaluator:
    def __init__(self):
        self.case_id_col = competition_config.case_id_column
        self.pred_col = competition_config.prediction_column
        self.expected_type = competition_config.expected_prediction_type
        self.label_set: Optional[Set[str]] = (
            set(competition_config.label_set) if competition_config.label_set else None
        )
        self.scoring_policy_version = competition_config.scoring_policy_version
        self.dataset_version = competition_config.preliminary_dataset_version or "synthetic-prelim-v1.0"

    def validate_and_parse_excel(
        self, file_path: Path, expected_case_ids: Optional[Set[str]] = None
    ) -> Tuple[bool, Dict[str, Any], Optional[Dict[str, str]]]:
        """
        Parses the submitted Excel workbook and checks schema rules.
        Enforces:
        - Exactly matches case_id column and prediction column.
        - No duplicate case_ids.
        - No missing predictions (NaN/empty).
        - If expected_case_ids provided:
            - No missing case_ids.
            - No unexpected case_ids.
        - If label_set is configured:
            - All predictions must be in the approved label_set.
        Returns: (is_valid, validation_findings, parsed_predictions_map)
        """
        errors: List[str] = []
        warnings: List[str] = []
        findings: Dict[str, Any] = {
            "is_valid": False,
            "errors": errors,
            "warnings": warnings,
            "total_rows": 0,
            "columns_detected": [],
            "valid_predictions_count": 0,
        }

        if not file_path.exists():
            errors.append(f"Submission file does not exist at {file_path}")
            return False, findings, None

        try:
            # Read first worksheet using pandas with openpyxl engine
            df = pd.read_excel(file_path, engine="openpyxl")
        except Exception as e:
            errors.append(f"Malformed Excel file: unable to parse workbook. Error: {str(e)}")
            return False, findings, None

        findings["columns_detected"] = [str(c) for c in df.columns]
        findings["total_rows"] = len(df)

        # Check required columns
        if self.case_id_col not in df.columns:
            errors.append(f"Missing required column: '{self.case_id_col}'")
        if self.pred_col not in df.columns:
            errors.append(f"Missing required column: '{self.pred_col}'")

        if errors:
            return False, findings, None

        # Extract predictions map: case_id -> prediction
        predictions_map: Dict[str, str] = {}
        seen_case_ids: Set[str] = set()
        duplicate_case_ids: List[str] = []
        missing_prediction_cases: List[str] = []
        invalid_label_cases: List[str] = []

        for idx, row in df.iterrows():
            raw_cid = row[self.case_id_col]
            raw_pred = row[self.pred_col]

            if pd.isna(raw_cid) or str(raw_cid).strip() == "":
                errors.append(f"Row {idx + 2} has empty or missing '{self.case_id_col}'")
                continue

            case_id = str(raw_cid).strip()

            if case_id in seen_case_ids:
                duplicate_case_ids.append(case_id)
            seen_case_ids.add(case_id)

            if pd.isna(raw_pred) or str(raw_pred).strip() == "":
                missing_prediction_cases.append(case_id)
                continue

            pred_val = str(raw_pred).strip()

            # Label set enforcement
            if self.label_set is not None:
                if pred_val not in self.label_set:
                    invalid_label_cases.append(f"{case_id} (value: '{pred_val}')")

            predictions_map[case_id] = pred_val

        # Duplicate case_id policy
        if duplicate_case_ids:
            unique_dups = list(set(duplicate_case_ids))[:10]
            errors.append(
                f"Duplicate {self.case_id_col} detected ({len(duplicate_case_ids)} occurrences). Examples: {unique_dups}"
            )

        # Missing prediction policy
        if missing_prediction_cases:
            errors.append(
                f"Missing predictions for {len(missing_prediction_cases)} cases. Examples: {missing_prediction_cases[:10]}"
            )

        # Invalid label set policy
        if invalid_label_cases:
            errors.append(
                f"Invalid prediction labels found in {len(invalid_label_cases)} cases. Allowed labels: {sorted(list(self.label_set))}. Examples: {invalid_label_cases[:5]}"
            )

        # Check against expected case IDs if ground truth is supplied
        if expected_case_ids is not None:
            submitted_ids = set(predictions_map.keys())
            missing_ids = expected_case_ids - submitted_ids
            if missing_ids:
                errors.append(
                    f"Submission is missing {len(missing_ids)} required case IDs. Examples: {list(missing_ids)[:10]}"
                )

            unexpected_ids = submitted_ids - expected_case_ids
            if unexpected_ids:
                errors.append(
                    f"Submission contains {len(unexpected_ids)} unexpected case IDs not in evaluation dataset. Examples: {list(unexpected_ids)[:10]}"
                )

        if errors:
            findings["is_valid"] = False
            return False, findings, None

        findings["is_valid"] = True
        findings["valid_predictions_count"] = len(predictions_map)
        return True, findings, predictions_map

    def evaluate_predictions(
        self,
        predictions_map: Dict[str, str],
        ground_truth_map: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Deterministically evaluates predictions against ground truth.
        Matches ONLY by case_id, NEVER by row order.
        """
        total_cases = len(ground_truth_map)
        if total_cases == 0:
            raise ValueError("Ground truth dataset contains 0 cases.")

        correct_count = 0
        evaluated_cases = 0

        # Evaluate strictly against ground truth keys
        for case_id, true_label in ground_truth_map.items():
            if case_id in predictions_map:
                evaluated_cases += 1
                pred_label = predictions_map[case_id]
                if pred_label == true_label:
                    correct_count += 1

        accuracy = float(correct_count) / float(total_cases)

        return {
            "total_cases": total_cases,
            "evaluated_cases": evaluated_cases,
            "correct_predictions": correct_count,
            "accuracy": round(accuracy, 6),
            "accuracy_percent": round(accuracy * 100.0, 4),
            "dataset_version": self.dataset_version,
            "scoring_policy_version": self.scoring_policy_version,
            "evaluator_version": EVALUATOR_VERSION,
        }


evaluator = PreliminaryEvaluator()
