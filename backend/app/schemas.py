from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=4)


class RefreshRequest(BaseModel):
    refresh_token: str


class PlaylistAccess(BaseModel):
    playlist_url: str
    user_agent: str = ""
    referer: Optional[str] = None
    refresh_in: int = 300
    offline_grace_seconds: int = 0
    subscription_status: str = "active"
    days_remaining: int = 30


class DeviceBinding(BaseModel):
    device_id: str
    device_name: Optional[str] = None
    current: bool = False


class DeviceAccess(BaseModel):
    limit: int = 1
    bound: int = 0
    devices: list[DeviceBinding] = []


class RevokeResponse(BaseModel):
    message: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=4)
    full_name: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    is_active: bool
    subscription_status: str
    subscription_expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True