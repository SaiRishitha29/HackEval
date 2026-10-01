import os
import hashlib
from pathlib import Path
from typing import Tuple, Dict, Any
from backend.app.config import settings


class StorageService:
    def __init__(self):
        self.storage_dir = Path(settings.LOCAL_STORAGE_DIR).resolve()
        self.ground_truth_dir = Path(settings.PRIVATE_GROUND_TRUTH_DIR).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.ground_truth_dir.mkdir(parents=True, exist_ok=True)

    def save_submission_file(self, team_id: int, attempt: int, filename: str, content: bytes) -> Tuple[str, str, int]:
        """
        Saves a submitted Excel file to private object storage.
        Returns: (relative_storage_path, sha256_hash, file_size)
        """
        # Security: sanitize filename and prevent directory traversal
        clean_filename = Path(filename).name
        sha256 = hashlib.sha256(content).hexdigest()

        # Destination subdirectory by team
        team_dir = self.storage_dir / f"team_{team_id}"
        team_dir.mkdir(parents=True, exist_ok=True)

        target_filename = f"attempt_{attempt}_{sha256[:12]}_{clean_filename}"
        target_path = team_dir / target_filename

        with open(target_path, "wb") as f:
            f.write(content)

        rel_path = str(target_path.relative_to(self.storage_dir))
        return rel_path, sha256, len(content)

    def get_submission_path(self, relative_path: str) -> Path:
        """
        Resolves a storage path securely, ensuring it resides inside storage_dir.
        """
        target = (self.storage_dir / relative_path).resolve()
        if not target.is_relative_to(self.storage_dir):
            raise PermissionError("Access denied: Path traversal detected")
        if not target.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")
        return target

    def save_ground_truth(self, dataset_name: str, content: bytes) -> Path:
        """
        Saves private ground truth into isolated ground_truth_dir.
        """
        clean_name = Path(dataset_name).name
        target = self.ground_truth_dir / clean_name
        with open(target, "wb") as f:
            f.write(content)
        return target

    def get_ground_truth_path(self, dataset_name: str) -> Path:
        target = (self.ground_truth_dir / Path(dataset_name).name).resolve()
        if not target.is_relative_to(self.ground_truth_dir):
            raise PermissionError("Access denied: Path traversal detected in ground truth access")
        if not target.exists():
            raise FileNotFoundError(f"Ground truth dataset not found: {dataset_name}")
        return target

    def save_evidence(self, finalist_id: int, evidence_data: str) -> str:
        """
        Saves verification logs / evidence JSON to disk.
        """
        evidence_dir = self.storage_dir / "evidence" / f"finalist_{finalist_id}"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        import time
        target = evidence_dir / f"verification_{int(time.time())}.json"
        with open(target, "w", encoding="utf-8") as f:
            f.write(evidence_data)
        return str(target.relative_to(self.storage_dir))


storage_service = StorageService()
