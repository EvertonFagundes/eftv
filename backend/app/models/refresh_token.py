# models/refresh_token.py - Sessoes de renovacao emitidas (revogaveis)
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RefreshToken(Base):
    """Refresh token emitido para um aparelho.

    O token em si continua sendo um JWT (o cliente nao precisa consultar o
    banco a cada renovacao), mas o ``jti`` fica registrado aqui. Assim:

    - o logout consegue revogar de verdade (antes so apagava o cookie);
    - a rotacao invalida o token anterior, que deixa de renovar mesmo se
      alguem tiver copiado;
    - o painel/admin pode derrubar todas as sessoes de uma conta.
    """

    __tablename__ = "refresh_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_refresh_tokens_user_active", "user_id", "revoked_at"),
        Index("idx_refresh_tokens_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<RefreshToken(jti={self.jti}, user_id={self.user_id})>"
