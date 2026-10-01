from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class PreliminaryLeaderboardEntry(BaseModel):
    rank: int
    team_id: int
    team_name: str
    preliminary_accuracy: Optional[float] = None
    is_official_selected: bool = False
    submission_timestamp: Optional[datetime] = None
    submission_id: Optional[str] = None
    is_finalist: bool = False


class FinalLeaderboardEntry(BaseModel):
    rank: int
    team_id: int
    team_name: str
    performance_score_p: float
    reliability_score_r: float
    final_score: float
    deployment_version: str
    avg_latency_ms: float
    status: str


class LeaderboardResponse(BaseModel):
    stage: str  # "preliminary_provisional", "preliminary_frozen", "final_provisional", "final_published"
    version: int
    is_provisional: bool
    is_published: bool
    is_frozen: bool
    is_immutable: bool = False
    frozen_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    approval_notes: Optional[str] = None
    entries: List[Dict[str, Any]] = []


class LeaderboardPublishRequest(BaseModel):
    approval_notes: str = "Authorized administrative publication"
