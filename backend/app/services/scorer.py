import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.app.config import competition_config
from backend.app.db.models import Finalist, FinalistVerification, Team

logger = logging.getLogger(__name__)


class FinalScoringService:
    def __init__(self):
        self.perf_weight = competition_config.verified_performance_weight
        self.rel_weight = competition_config.reliability_weight
        self._validate_weights()

    def _validate_weights(self):
        w_sum = self.perf_weight + self.rel_weight
        if abs(w_sum - 1.0) > 1e-4:
            raise ValueError(f"Final scoring weights must sum to 1.0. Current sum: {w_sum}")

    def calculate_score(self, performance_p: float, reliability_r: float) -> float:
        """
        Calculates S_final = 0.823529 * P + 0.176471 * R
        P and R are normalized between 0.0 and 100.0.
        """
        p_clamped = max(0.0, min(100.0, performance_p))
        r_clamped = max(0.0, min(100.0, reliability_r))
        score = (self.perf_weight * p_clamped) + (self.rel_weight * r_clamped)
        return round(score, 4)

    def generate_final_ranking(self, db: Session) -> List[Dict[str, Any]]:
        """
        Ranks all verified finalists according to approved tie-breakers:
        1. S_final desc
        2. Verified performance (P) desc
        3. Reliability score (R) desc
        4. Lowest average latency asc
        5. Team ID asc
        """
        finalists = db.query(Finalist).filter(Finalist.is_eligible == True).all()

        ranking_candidates = []
        for finalist in finalists:
            ver = (
                db.query(FinalistVerification)
                .filter(FinalistVerification.finalist_id == finalist.id)
                .order_by(FinalistVerification.id.desc())
                .first()
            )
            p = ver.performance_score_p if ver and ver.performance_score_p is not None else 0.0
            r = ver.reliability_score_r if ver and ver.reliability_score_r is not None else 0.0
            avg_lat = ver.avg_latency_ms if ver else 99999.0
            final_s = self.calculate_score(p, r) if ver and ver.status == "completed" else 0.0

            ranking_candidates.append({
                "team_id": finalist.team_id,
                "team_name": finalist.team.name,
                "finalist_id": finalist.id,
                "deployment_version": finalist.official_submission.deployment_version if finalist.official_submission else "unknown",
                "performance_score_p": p,
                "reliability_score_r": r,
                "avg_latency_ms": avg_lat,
                "final_score": final_s,
                "status": ver.status if ver else "unverified",
                "reported_version": ver.reported_version if ver else None,
                "version_matched": ver.version_matched if ver else False,
            })

        # Deterministic sorting
        ranking_candidates.sort(
            key=lambda item: (
                item["final_score"],
                item["performance_score_p"],
                item["reliability_score_r"],
                -item["avg_latency_ms"],  # Lower latency is better
                -item["team_id"],
            ),
            reverse=True,
        )

        for rank_idx, item in enumerate(ranking_candidates, start=1):
            item["rank"] = rank_idx

        return ranking_candidates


final_scorer = FinalScoringService()
