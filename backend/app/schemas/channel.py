# schemas/channel.py - Schemas de canais
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ChannelBase(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    name: str = Field(..., min_length=1, max_length=255)
    category_id: UUID | None = None
    group_title: str | None = Field(None, max_length=255)
    logo_url: HttpUrl | None = None
    is_live: bool = True
    is_adult: bool = False
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0)
    stream_url: HttpUrl | None = None
    stream_type: str | None = Field(None, pattern="^(hls|dash|ts|mp4)$")
    backup_stream_url: HttpUrl | None = None
    backup_stream_type: str | None = Field(None, pattern="^(hls|dash|ts|mp4)$")
    drm_protected: bool = False
    drm_license_url: HttpUrl | None = None
    current_program_title: str | None = Field(None, max_length=255)
    current_program_start: datetime | None = None
    current_program_end: datetime | None = None
    current_program_description: str | None = None
    next_program_title: str | None = Field(None, max_length=255)
    metadata: dict = Field(default_factory=dict)


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(BaseModel):
    slug: str | None = Field(None, min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    name: str | None = Field(None, min_length=1, max_length=255)
    category_id: UUID | None = None
    group_title: str | None = Field(None, max_length=255)
    logo_url: HttpUrl | None = None
    is_live: bool | None = None
    is_adult: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(None, ge=0)
    stream_url: HttpUrl | None = None
    stream_type: str | None = Field(None, pattern="^(hls|dash|ts|mp4)$")
    backup_stream_url: HttpUrl | None = None
    backup_stream_type: str | None = Field(None, pattern="^(hls|dash|ts|mp4)$")
    drm_protected: bool | None = None
    drm_license_url: HttpUrl | None = None
    current_program_title: str | None = Field(None, max_length=255)
    current_program_start: datetime | None = None
    current_program_end: datetime | None = None
    current_program_description: str | None = None
    next_program_title: str | None = Field(None, max_length=255)
    metadata: dict | None = None


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
    drm_license_url: str | None = None
    backup_stream_url: str | None = None
    backup_stream_type: str | None = None
