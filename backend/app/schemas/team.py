from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


class TeamCreate(BaseModel):
    name: str
    contact_email: EmailStr


class TeamMemberOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str

    class Config:
        from_attributes = True


class TeamOut(BaseModel):
    id: int
    name: str
    contact_email: EmailStr
    token: str
    created_at: datetime
    submissions_count: int = 0
    remaining_attempts: int = 5
    members: List[TeamMemberOut] = []

    class Config:
        from_attributes = True
