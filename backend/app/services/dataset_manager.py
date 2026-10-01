import json
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
from backend.app.config import settings, competition_config
from backend.app.services.storage import storage_service

DEFAULT_PRELIMINARY_FILE = "preliminary_ground_truth.json"
DEFAULT_HIDDEN_TEST_FILE = "hidden_test_cases.json"


class DatasetManager:
    def __init__(self):
        self._ensure_synthetic_datasets()

    def _ensure_synthetic_datasets(self):
        """Initializes synthetic ground truth datasets if not already present."""
        gt_dir = Path(settings.PRIVATE_GROUND_TRUTH_DIR)
        gt_dir.mkdir(parents=True, exist_ok=True)

        prelim_path = gt_dir / DEFAULT_PRELIMINARY_FILE
        hidden_path = gt_dir / DEFAULT_HIDDEN_TEST_FILE

        labels = competition_config.label_set or ["category_a", "category_b", "category_c"]

        if not prelim_path.exists():
            # Generate 500 cases
            case_count = competition_config.expected_case_count or 500
            prelim_data = {}
            for i in range(1, case_count + 1):
                case_id = f"CASE_{i:04d}"
                # Deterministic assignment
                assigned_label = labels[i % len(labels)]
                prelim_data[case_id] = assigned_label

            with open(prelim_path, "w", encoding="utf-8") as f:
                json.dump(prelim_data, f, indent=2)

        if not hidden_path.exists():
            # Generate 100 hidden cases for finalist verification
            hidden_cases = []
            for i in range(1, 101):
                case_id = f"HIDDEN_TEST_{i:04d}"
                true_label = labels[(i * 3 + 1) % len(labels)]
                hidden_cases.append({
                    "case_id": case_id,
                    "input_features": {
                        "text": f"Classification test feature sequence {i}",
                        "signal_strength": round((i * 1.37) % 10.0, 3)
                    },
                    "ground_truth_label": true_label
                })

            with open(hidden_path, "w", encoding="utf-8") as f:
                json.dump(hidden_cases, f, indent=2)

    def get_preliminary_ground_truth(self) -> Dict[str, str]:
        path = Path(settings.PRIVATE_GROUND_TRUTH_DIR) / DEFAULT_PRELIMINARY_FILE
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_hidden_test_cases(self) -> List[Dict[str, Any]]:
        path = Path(settings.PRIVATE_GROUND_TRUTH_DIR) / DEFAULT_HIDDEN_TEST_FILE
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def generate_sample_submission_excel(self, output_path: Path, accuracy_target: float = 0.85):
        """Utility for creating synthetic participant submissions for tests or demos."""
        gt = self.get_preliminary_ground_truth()
        labels = competition_config.label_set or ["category_a", "category_b", "category_c"]

        rows = []
        total = len(gt)
        correct_target = int(total * accuracy_target)
        count = 0

        for case_id, true_label in gt.items():
            if count < correct_target:
                pred = true_label
            else:
                # Pick a wrong label
                wrong_labels = [l for l in labels if l != true_label]
                pred = wrong_labels[0] if wrong_labels else true_label
            rows.append({"case_id": case_id, "prediction": pred})
            count += 1

        df = pd.DataFrame(rows)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_excel(output_path, index=False, engine="openpyxl")
        return output_path


dataset_manager = DatasetManager()
