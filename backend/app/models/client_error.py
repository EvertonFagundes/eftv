# models/client_error.py - Erros e travamentos relatados pelo app
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ClientError(Base):
    """Relato de falha enviado pelo aplicativo.

    Existe porque, sem telemetria, o suporte descobre os problemas pelo
    WhatsApp. Guarda o minimo para reproduzir: versao, aparelho e stacktrace.
    Nada de dados pessoais alem do que o Android ja expoe no erro.
    """

    __tablename__ = "client_errors"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    app_version: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    device: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    android: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stacktrace: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    __table_args__ = (Index("idx_client_errors_created", "created_at"),)

    def __repr__(self) -> str:
        return f"<ClientError(id={self.id}, version={self.app_version}, message={self.message[:40]!r})>"
