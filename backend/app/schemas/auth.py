# schemas/auth.py - Schemas de autenticação
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


class TokenPayload(BaseModel):
    sub: UUID  # user_id
    exp: int
    iat: int
    type: str  # "access" ou "refresh"
    jti: str  # JWT ID único


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=20)
    plan_id: UUID | None = None  # Para registrar já vinculando a um plano


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str | None
    phone: str | None
    is_active: bool
    is_admin: bool
    email_verified: bool
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=20)
    password: str | None = Field(None, min_length=8, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=1, max_length=255)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class MessageResponse(BaseModel):
    message: str


class EmailVerificationResponse(BaseModel):
    message: str
    email_verified: bool
