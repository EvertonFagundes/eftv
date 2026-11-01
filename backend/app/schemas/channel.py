# schemas/channel.py - Schemas de canais
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, HttpUrl
from uuid import UUID


class ChannelBase(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    name: str = Field(..., min_length=1, max_length=255)
    category_id: Optional[UUID] = None
    group_title: Optional[str] = Field(None, max_length=255)
    logo_url: Optional[HttpUrl] = None
    is_live: bool = True
    is_adult: bool = False
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0)
    stream_url: Optional[HttpUrl] = None
    stream_type: Optional[str] = Field(None, pattern="^(hls|dash|ts|mp4)$")
    backup_stream_url: Optional[HttpUrl] = None
    backup_stream_type: Optional[str] = Field(None, pattern="^(hls|dash|ts|mp4)$")
    drm_protected: bool = False
    drm_license_url: Optional[HttpUrl] = None
    current_program_title: Optional[str] = Field(None, max_length=255)
    current_program_start: Optional[datetime] = None
    current_program_end: Optional[datetime] = None
    current_program_description: Optional[str] = None
    next_program_title: Optional[str] = Field(None, max_length=255)
    metadata: dict = Field(default_factory=dict)


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    slug: Optional[str] = Field(None, min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category_id: Optional[UUID] = None
    group_title: Optional[str] = Field(None, max_length=255)
    logo_url: Optional[HttpUrl] = None
    is_live: Optional[bool] = None
    is_adult: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0)
    stream_url: Optional[HttpUrl] = None
    stream_type: Optional[str] = Field(None, pattern="^(hls|dash|ts|mp4)$")
    backup_stream_url: Optional[HttpUrl] = None
    backup_stream_type: Optional[str] = Field(None, pattern="^(hls|dash|ts|mp4)$")
    drm_protected: Optional[bool] = None
    drm_license_url: Optional[HttpUrl] = None
    current_program_title: Optional[str] = Field(None, max_length=255)
    current_program_start: Optional[datetime] = None
    current_program_end: Optional[datetime] = None
    current_program_description: Optional[str] = None
    next_program_title: Optional[str] = Field(None, max_length=255)
    metadata: Optional[dict] = None


class ChannelResponse(ChannelBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class ChannelListResponse(BaseModel):
    channels: list[ChannelResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ChannelPlayResponse(BaseModel):
    """Resposta do endpoint /channels/{slug}/play - retorna URL do stream + token."""
    stream_url: str
    stream_type: str
    token: str  # JWT assinado para autorização no CDN
    expires_at: datetime
    drm_license_url: Optional[str] = None
    backup_stream_url: Optional[str] = None
    backup_stream_type: Optional[str] = None