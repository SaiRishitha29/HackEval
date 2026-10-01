import pytest
from backend.app.services.scorer import final_scorer


def test_final_scoring_formula():
    # Performance = 100, Reliability = 100 -> Score = 100.0
    score_perfect = final_scorer.calculate_score(performance_p=100.0, reliability_r=100.0)
    assert score_perfect == 100.0

    # Performance = 0, Reliability = 0 -> Score = 0.0
    score_zero = final_scorer.calculate_score(performance_p=0.0, reliability_r=0.0)
    assert score_zero == 0.0

    # P = 80.0, R = 90.0
    # S = 0.823529 * 80 + 0.176471 * 90 = 65.88232 + 15.88239 = 81.7647
    score_mixed = final_scorer.calculate_score(performance_p=80.0, reliability_r=90.0)
    assert score_mixed == pytest.approx(81.7647, 0.001)


def test_final_scoring_clamping():
    # Ensure inputs > 100 are clamped to 100, and < 0 to 0
    score_over = final_scorer.calculate_score(performance_p=150.0, reliability_r=120.0)
    assert score_over == 100.0

    score_under = final_scorer.calculate_score(performance_p=-20.0, reliability_r=-10.0)
    assert score_under == 0.0
