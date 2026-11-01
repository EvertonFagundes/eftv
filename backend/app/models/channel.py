# models/channel.py - Modelo de canal (catálogo centralizado)
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.playback_session import PlaybackSession


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)  # URL amigável: "sportv", "globonews"
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True, index=True
    )
    group_title: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Grupo original da playlist (para admin)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_live: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # true = ao vivo, false = sob demanda (VOD)
    is_adult: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Metadados de streaming (preenchidos pelo admin)
    stream_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # URL principal (HLS/DASH)
    stream_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # hls, dash, ts, mp4
    backup_stream_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # Fallback
    backup_stream_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    drm_protected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Widevine/PlayReady
    drm_license_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # EPG básico
    current_program_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_program_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_program_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_program_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_program_title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Metadados extras
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # Dados extras (origem, qualidade, etc.)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relacionamentos
    category: Mapped["Category | None"] = relationship("Category", back_populates="channels", lazy="selectin")
    playback_sessions: Mapped[list["PlaybackSession"]] = relationship(
        "PlaybackSession", back_populates="channel", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_channels_category_active", "category_id", "is_active"),
        Index("idx_channels_slug", "slug"),
        Index("idx_channels_active_live", "is_active", "is_live"),
    )

    def __repr__(self) -> str:
        return f"<Channel(id={self.id}, slug={self.slug}, name={self.name}, live={self.is_live})>"

    @property
    def is_playing_now(self) -> bool:
        """Verifica se há programa atual no ar (para canais ao vivo com EPG)."""
        if not self.is_live:
            return False
        now = datetime.now(timezone.utc)
        if self.current_program_start and self.current_program_end:
            return self.current_program_start <= now < self.current_program_end
        return True  # Se não tem EPG, assume que está no ar

    def get_stream_sources(self) -> list[dict]:
        """Retorna lista de fontes de stream ordenadas (principal + backup)."""
        sources = []
        if self.stream_url:
            sources.append({"url": self.stream_url, "type": self.stream_type or "hls", "primary": True})
        if self.backup_stream_url:
            sources.append({"url": self.backup_stream_url, "type": self.backup_stream_type or "hls", "primary": False})
        return sources