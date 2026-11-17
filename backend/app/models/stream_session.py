# models/stream_session.py - Quem esta assistindo agora (limite de telas)
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StreamSession(Base):
    """Sessao de reproducao aberta pelo app.

    O catalogo vem da playlist licenciada, nao da tabela ``channels``: por isso
    a sessao guarda a URL do stream em vez de uma chave estrangeira. Serve para
    aplicar o limite de telas simultaneas do plano (hoje 1).
    """

    __tablename__ = "stream_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Hash do endereco do stream: identifica o canal para o suporte (e denuncia
    # uso compartilhado) sem guardar a URL do provedor, que carrega usuario e
    # senha do licenciamento.
    channel_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_stream_sessions_user_active", "user_id", "ended_at"),
        Index("idx_stream_sessions_heartbeat", "last_heartbeat"),
    )

    def __repr__(self) -> str:
        return (
            f"<StreamSession(id={self.id}, user_id={self.user_id}, "
            f"device_id={self.device_id}, active={self.ended_at is None})>"
        )
