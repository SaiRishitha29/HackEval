from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    team_id: Optional[int] = None


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    team_id: Optional[int] = None


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    team_name: Optional[str] = None  # If participant, can register team concurrently


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    role: str
    team_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
