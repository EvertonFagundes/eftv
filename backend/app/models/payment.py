# models/payment.py - Modelo de pagamento
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True
    )
    mercadopago_payment_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    mercadopago_preference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )  # pending, approved, rejected, refunded, cancelled
    payment_method: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # pix, credit_card, boleto, saldo_mp
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "metadata" e reservado no SQLAlchemy Declarative; a coluna mantem o nome.
    extra_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )  # Dados brutos do webhook
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # Relacionamentos
    user: Mapped["User | None"] = relationship("User", back_populates="payments", lazy="selectin")

    __table_args__ = (
        Index("idx_payments_user", "user_id"),
        Index("idx_payments_mp_id", "mercadopago_payment_id"),
        Index("idx_payments_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, amount={self.amount_cents/100:.2f} {self.currency}, status={self.status})>"

    @property
    def amount_formatted(self) -> str:
        return f"{self.amount_cents / 100:.2f} {self.currency}"
