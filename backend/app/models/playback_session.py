# models/playback_session.py - Controle de sessões simultâneas
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.channel import Channel
    from app.models.subscription import Subscription
    from app.models.user import User


class PlaybackSession(Base):
    __tablename__ = "playback_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
    device_fingerprint: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Hash do device (user-agent + IP + etc)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_jti: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )  # JWT ID do token de acesso ao stream
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "metadata" e reservado no SQLAlchemy Declarative; a coluna mantem o nome.
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # Relacionamentos
    user: Mapped["User"] = relationship("User", back_populates="playback_sessions", lazy="selectin")
    subscription: Mapped["Subscription"] = relationship("Subscription", lazy="selectin")
    channel: Mapped["Channel | None"] = relationship(
        "Channel", back_populates="playback_sessions", lazy="selectin"
    )

    __table_args__ = (
        Index(
            "idx_playback_sessions_user_active",
            "user_id",
            "ended_at",
            postgresql_where="ended_at IS NULL",
        ),
        Index("idx_playback_sessions_token", "token_jti"),
        Index(
            "idx_playback_sessions_channel_active",
            "channel_id",
            "ended_at",
            postgresql_where="ended_at IS NULL",
        ),
    )

    def __repr__(self) -> str:
        return f"<PlaybackSession(id={self.id}, user_id={self.user_id}, channel_id={self.channel_id}, active={self.ended_at is None})>"

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def duration_seconds(self) -> int:
        end = self.ended_at or datetime.now(UTC)
        return int((end - self.started_at).total_seconds())

    def end_session(self) -> None:
        """Marca sessão como encerrada."""
        self.ended_at = datetime.now(UTC)

    def heartbeat(self) -> None:
        """Atualiza último heartbeat."""
        self.last_heartbeat = datetime.now(UTC)
