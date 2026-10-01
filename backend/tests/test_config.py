import pytest
from backend.app.config import CompetitionConfig, Settings, raw_yaml, competition_config


def test_config_weights_and_constraints():
    assert competition_config.problem_type == "single_label_classification"
    assert competition_config.max_attempts_per_team == 5
    assert competition_config.qualitative_review_enabled is False

    # Check weights sum to 1.0 within float tolerance
    weight_sum = competition_config.verified_performance_weight + competition_config.reliability_weight
    assert abs(weight_sum - 1.0) < 1e-4
    assert pytest.approx(competition_config.verified_performance_weight, 0.0001) == 0.823529
    assert pytest.approx(competition_config.reliability_weight, 0.0001) == 0.176471


def test_unresolved_todos_detection():
    # In raw yaml, multiple fields are marked TODO
    cfg = CompetitionConfig(raw_yaml, Settings(DEADLINE_UTC=None))
    assert len(cfg.unresolved_todos) > 0
    assert "deadline_utc" in cfg.unresolved_todos or "final_tie_breaker" in cfg.unresolved_todos

    # Production readiness assertion should fail when TODOs exist
    with pytest.raises(RuntimeError) as exc_info:
        cfg.assert_production_ready()
    assert "Production launch blocked" in str(exc_info.value)
