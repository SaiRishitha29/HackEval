from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class FinalistOut(BaseModel):
    id: int
    team_id: int
    team_name: str
    preliminary_rank: int
    preliminary_accuracy: float
    is_eligible: bool
    disqualification_reason: Optional[str] = None
    endpoint_url: str
    deployment_version: str
    selected_at: datetime

    class Config:
        from_attributes = True


class FinalistVerificationOut(BaseModel):
    id: int
    finalist_id: int
    team_name: str
    reachability_passed: bool
    version_matched: bool
    reported_version: Optional[str] = None
    total_test_cases: int
    valid_responses_count: int
    failed_responses_count: int
    timeouts_count: int
    malformed_responses_count: int
    retries_count: int
    avg_latency_ms: float
    performance_score_p: Optional[float] = None
    reliability_score_r: Optional[float] = None
    final_score: Optional[float] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class FinalScoreBreakdown(BaseModel):
    team_id: int
    team_name: str
    performance_p: float
    performance_weight: float
    weighted_performance: float
    reliability_r: float
    reliability_weight: float
    weighted_reliability: float
    final_score: float
    tie_breaker_rank: int
