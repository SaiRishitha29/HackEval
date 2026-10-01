import os
import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import Field
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_YAML_PATH = PROJECT_ROOT / "competition_config.yaml"


class Settings(BaseSettings):
    APP_ENV: str = Field(default="development", description="Environment mode: development or production")
    APP_SECRET_KEY: str = Field(default="hackeval-secret-development-key-32bytes-secure-random-val!", description="Secret key for JWT")
    APP_PORT: int = Field(default=8000)
    APP_HOST: str = Field(default="0.0.0.0")

    DATABASE_URL: str = Field(default="sqlite:///./hackeval.db")
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/1")

    STORAGE_BACKEND: str = Field(default="local")
    LOCAL_STORAGE_DIR: str = Field(default=str(PROJECT_ROOT / "data" / "storage"))
    PRIVATE_GROUND_TRUTH_DIR: str = Field(default=str(PROJECT_ROOT / "data" / "ground_truth"))

    ALLOW_HTTP_MOCK_ENDPOINTS_IN_DEV: bool = Field(default=True)
    MAX_SUBMISSION_FILE_SIZE_BYTES: int = Field(default=10 * 1024 * 1024)  # 10MB
    MAX_RESPONSE_BYTES: int = Field(default=1024 * 1024)  # 1MB

    INITIAL_ADMIN_USERNAME: str = Field(default="admin")
    INITIAL_ADMIN_EMAIL: str = Field(default="admin@hackeval.local")
    INITIAL_ADMIN_PASSWORD: str = Field(default="HackEvalAdmin2026!")
    MCP_ADMIN_API_KEY: str = Field(default="mcp_secret_admintoken_7f8a9b2c3d4e5f6a")

    # Organizer overrides / decisions provided via environment
    DEADLINE_UTC: Optional[str] = None
    LABEL_SET: Optional[str] = None  # Comma-separated in env
    EXPECTED_CASE_COUNT: Optional[int] = None
    PRELIMINARY_DATASET_VERSION: Optional[str] = None
    FINALIST_TEST_SET_VERSION: Optional[str] = None
    FINALIST_BATCH_SIZE: Optional[int] = None
    VERIFICATION_DEADLINE_SECONDS: Optional[int] = None
    FINAL_TIEBREAKER: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


def load_competition_yaml() -> Dict[str, Any]:
    if not CONFIG_YAML_PATH.exists():
        raise FileNotFoundError(f"Configuration file not found at {CONFIG_YAML_PATH}")
    with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class CompetitionConfig:
    def __init__(self, raw_config: Dict[str, Any], settings: Settings):
        self.raw = raw_config
        self.settings = settings
        comp = raw_config.get("competition", {})
        sub = comp.get("submission", {})
        eval_cfg = comp.get("evaluation", {})
        fs = comp.get("final_scoring", {})
        fv = comp.get("finalist_verification", {})
        qr = comp.get("qualitative_review", {})
        pub = comp.get("publication", {})

        # Competition Metadata
        self.name: str = comp.get("name", "HackEval Classification Challenge")
        self.timezone: str = comp.get("timezone", "Asia/Kolkata")
        self.problem_type: str = comp.get("problem_type", "single_label_classification")

        # Submission rules
        self.max_attempts_per_team: int = sub.get("max_attempts_per_team", 5)
        self.selection_policy: str = sub.get("selection_policy", "best_valid_preliminary_score")
        self.reject_submissions_after_deadline: bool = sub.get("reject_submissions_after_deadline", True)
        self.freeze_official_submission: bool = sub.get("freeze_official_submission", True)
        self.reveal_preliminary_scores_before_deadline: bool = sub.get("reveal_preliminary_scores_before_deadline", False)
        self.require_excel_file: bool = sub.get("require_excel_file", True)
        self.accepted_extensions: List[str] = sub.get("accepted_extensions", [".xlsx"])
        self.require_https_endpoint: bool = sub.get("require_https_endpoint", True)
        self.require_deployment_version: bool = sub.get("require_deployment_version", True)
        self.require_endpoint_freeze_declaration: bool = sub.get("require_endpoint_freeze_declaration", True)

        # Evaluation rules
        self.case_id_column: str = eval_cfg.get("case_id_column", "case_id")
        self.prediction_column: str = eval_cfg.get("prediction_column", "prediction")
        self.expected_prediction_type: str = eval_cfg.get("expected_prediction_type", "string")
        self.scoring_policy_version: str = eval_cfg.get("scoring_policy_version", "classification-v1")
        self.invalid_submission_policy: str = eval_cfg.get("invalid_submission_policy", "ineligible")
        self.preliminary_metric: str = eval_cfg.get("preliminary_metric", "accuracy")
        self.final_predictive_metric: str = eval_cfg.get("final_predictive_metric", "accuracy")
        self.finalist_count: int = eval_cfg.get("finalist_count", 20)
        self.verification_uses_fresh_hidden_cases: bool = eval_cfg.get("verification_uses_fresh_hidden_cases", True)
        self.equal_test_protocol_for_all_finalists: bool = eval_cfg.get("equal_test_protocol_for_all_finalists", True)

        # Final Scoring rules
        self.qualitative_review_enabled: bool = qr.get("enabled", False)
        if self.qualitative_review_enabled:
            raise ValueError("Qualitative review must be disabled per official competition decisions.")

        self.verified_performance_weight: float = float(fs.get("verified_performance_weight", 0.823529))
        self.reliability_weight: float = float(fs.get("reliability_weight", 0.176471))
        weight_sum = self.verified_performance_weight + self.reliability_weight
        if abs(weight_sum - 1.0) > 1e-4:
            raise ValueError(f"Final scoring weights must sum to 1.0 (current sum: {weight_sum})")

        self.score_range_min: float = float(fs.get("score_range_min", 0))
        self.score_range_max: float = float(fs.get("score_range_max", 100))
        self.performance_metric_name: str = fs.get("performance_metric", "hidden_test_accuracy")
        self.reliability_metric_name: str = fs.get("reliability_metric", "valid_response_rate")
        self.tie_breakers: List[str] = fs.get("tie_breakers", ["verified_performance", "reliability_score"])

        # Finalist verification rules
        self.hosting_model: str = fv.get("hosting_model", "participant_managed")
        self.concurrency_limit: int = fv.get("concurrency_limit", 5)
        self.connect_timeout_seconds: float = float(fv.get("connect_timeout_seconds", 5))
        self.read_timeout_seconds: float = float(fv.get("read_timeout_seconds", 20))
        self.max_retries: int = fv.get("max_retries", 1)
        self.max_response_bytes: int = fv.get("max_response_bytes", 1048576)
        self.retry_policy_version: str = fv.get("retry_policy_version", "verification-v1")
        self.endpoint_safety_policy_version: str = fv.get("endpoint_safety_policy_version", "ssrf-policy-v1")
        self.deployment_version_must_match: bool = fv.get("deployment_version_must_match", True)

        # Publication rules
        self.preliminary_leaderboard_is_provisional: bool = pub.get("preliminary_leaderboard_is_provisional", True)
        self.final_publication_requires_admin_approval: bool = pub.get("final_publication_requires_admin_approval", True)
        self.published_results_are_immutable: bool = pub.get("published_results_are_immutable", True)

        # Unresolved TODOs check
        self.unresolved_todos: List[str] = []
        self._resolve_decision_values(sub, eval_cfg, fv, fs)

    def _resolve_decision_values(self, sub: Dict[str, Any], eval_cfg: Dict[str, Any], fv: Dict[str, Any], fs: Dict[str, Any]):
        # Deadline
        raw_deadline = sub.get("deadline_utc")
        if raw_deadline == "TODO" or not raw_deadline:
            if self.settings.DEADLINE_UTC:
                self.deadline_utc = self.settings.DEADLINE_UTC
            else:
                self.deadline_utc = None
                self.unresolved_todos.append("deadline_utc")
        else:
            self.deadline_utc = str(raw_deadline)

        # Label set
        raw_labels = eval_cfg.get("label_set")
        if raw_labels == "TODO" or not raw_labels:
            if self.settings.LABEL_SET:
                self.label_set = [l.strip() for l in self.settings.LABEL_SET.split(",") if l.strip()]
            else:
                self.label_set = None
                self.unresolved_todos.append("label_set")
        elif isinstance(raw_labels, list):
            self.label_set = [str(l).strip() for l in raw_labels]
        else:
            self.label_set = [l.strip() for l in str(raw_labels).split(",") if l.strip()]

        # Expected case count
        raw_ecc = eval_cfg.get("expected_case_count")
        if raw_ecc == "TODO" or raw_ecc is None:
            if self.settings.EXPECTED_CASE_COUNT:
                self.expected_case_count = int(self.settings.EXPECTED_CASE_COUNT)
            else:
                self.expected_case_count = None
                self.unresolved_todos.append("expected_case_count")
        else:
            self.expected_case_count = int(raw_ecc)

        # Dataset versions
        raw_pdv = eval_cfg.get("preliminary_dataset_version")
        if raw_pdv == "TODO" or not raw_pdv:
            if self.settings.PRELIMINARY_DATASET_VERSION:
                self.preliminary_dataset_version = self.settings.PRELIMINARY_DATASET_VERSION
            else:
                self.preliminary_dataset_version = None
                self.unresolved_todos.append("preliminary_dataset_version")
        else:
            self.preliminary_dataset_version = str(raw_pdv)

        raw_ftsv = eval_cfg.get("finalist_test_set_version")
        if raw_ftsv == "TODO" or not raw_ftsv:
            if self.settings.FINALIST_TEST_SET_VERSION:
                self.finalist_test_set_version = self.settings.FINALIST_TEST_SET_VERSION
            else:
                self.finalist_test_set_version = None
                self.unresolved_todos.append("finalist_test_set_version")
        else:
            self.finalist_test_set_version = str(raw_ftsv)

        # Max batch size
        raw_mbs = fv.get("max_batch_size")
        if raw_mbs == "TODO" or raw_mbs is None:
            if self.settings.FINALIST_BATCH_SIZE:
                self.max_batch_size = int(self.settings.FINALIST_BATCH_SIZE)
            else:
                self.max_batch_size = None
                self.unresolved_todos.append("max_batch_size")
        else:
            self.max_batch_size = int(raw_mbs)

        # Total verification deadline seconds
        raw_tvds = fv.get("total_verification_deadline_seconds")
        if raw_tvds == "TODO" or raw_tvds is None:
            if self.settings.VERIFICATION_DEADLINE_SECONDS:
                self.total_verification_deadline_seconds = int(self.settings.VERIFICATION_DEADLINE_SECONDS)
            else:
                self.total_verification_deadline_seconds = None
                self.unresolved_todos.append("total_verification_deadline_seconds")
        else:
            self.total_verification_deadline_seconds = int(raw_tvds)

        # Final tie breaker
        if any("TODO" in str(tb) for tb in self.tie_breakers):
            if self.settings.FINAL_TIEBREAKER:
                self.tie_breakers = [
                    self.settings.FINAL_TIEBREAKER if "TODO" in str(tb) else tb
                    for tb in self.tie_breakers
                ]
            else:
                self.unresolved_todos.append("final_tie_breaker")

    @property
    def is_production_ready(self) -> bool:
        return len(self.unresolved_todos) == 0

    def assert_production_ready(self):
        if not self.is_production_ready:
            raise RuntimeError(
                f"Production launch blocked! Unresolved competition decisions: {', '.join(self.unresolved_todos)}"
            )


# Global instances
settings = Settings()
raw_yaml = load_competition_yaml()
competition_config = CompetitionConfig(raw_yaml, settings)
