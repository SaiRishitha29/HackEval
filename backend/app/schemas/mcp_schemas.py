from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class MCPAuthInput(BaseModel):
    admin_token: str = Field(..., description="Administrative API key or JWT token")


class MCPFreezeAndSelectInput(MCPAuthInput):
    deadline_override_iso: Optional[str] = Field(None, description="Optional ISO 8601 deadline timestamp override")


class MCPLeaderboardInput(MCPAuthInput):
    limit: Optional[int] = Field(20, description="Max entries to return")


class MCPFinalistVerificationInput(MCPAuthInput):
    finalist_ids: Optional[List[int]] = Field(None, description="Optional list of specific finalist IDs to verify. If omitted, all top-20 are verified.")


class MCPVerificationStatusInput(MCPAuthInput):
    job_id: Optional[str] = Field(None, description="Specific verification job ID or check overall progress")


class MCPPublishInput(MCPAuthInput):
    notes: str = Field("Authorized final leaderboard publication via MCP", description="Administrative approval notes")


class MCPAuditInput(MCPAuthInput):
    action: Optional[str] = Field(None, description="Filter by action name")
    limit: Optional[int] = Field(50, description="Max audit logs to return")
