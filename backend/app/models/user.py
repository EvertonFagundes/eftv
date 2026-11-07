# models/user.py - Modelo de usuário
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.database import Base

if TYPE_CHECKING:
    from app.models.payment import Payment
    from app.models.playback_session import PlaybackSession
    from app.models.subscription import Subscription


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)  # Para PIX/WhatsApp
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Token de verificacao de email (enviado por email ao registrar)
    email_verification_token: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relacionamentos
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="user", lazy="selectin"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="user", lazy="selectin"
    )
    playback_sessions: Mapped[list["PlaybackSession"]] = relationship(
        "PlaybackSession", back_populates="user", lazy="selectin"
    )

    __table_args__ = (Index("ix_users_email_active", "email", "is_active"),)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, active={self.is_active})>"

    def generate_email_verification_token(self) -> str:
        """Gera e armazena um token de verificacao de email valido por 24h."""
        import secrets

        token = secrets.token_urlsafe(32)
        self.email_verification_token = token
        self.email_verification_expires_at = datetime.now(UTC) + timedelta(
            hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS
        )
        return token

    def is_email_verification_token_valid(self, token: str) -> bool:
        """Verifica se o token corresponde e nao expirou."""
        if not self.email_verification_token or not self.email_verification_expires_at:
            return False
        if not hmac.compare_digest(self.email_verification_token, token):
            return False
        return datetime.now(UTC) < self.email_verification_expires_at
