# models/device.py - Aparelhos vinculados a uma assinatura
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.subscription import Subscription


class SubscriptionDevice(Base):
    """
    Aparelho autorizado a usar uma assinatura.

    O identificador e gerado pelo app na primeira execucao (UUID aleatorio,
    sem dados de hardware). Revogar mantem o historico via ``revoked_at``.
    """

    __tablename__ = "subscription_devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    device_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subscription: Mapped["Subscription"] = relationship("Subscription", back_populates="devices")

    __table_args__ = (
        UniqueConstraint("subscription_id", "device_id", name="uq_subscription_device"),
        Index("idx_subscription_devices_active", "subscription_id", "revoked_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<SubscriptionDevice(subscription_id={self.subscription_id}, "
            f"device_id={self.device_id})>"
        )
