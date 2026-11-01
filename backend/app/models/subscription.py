# models/subscription.py - Modelo de assinatura
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.plan import Plan
    from app.models.user import User


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )  # active, past_due, cancelled, expired, trial
    mercadopago_subscription_id: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    trial_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
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
    user: Mapped["User"] = relationship("User", back_populates="subscriptions", lazy="selectin")
    plan: Mapped["Plan"] = relationship("Plan", back_populates="subscriptions", lazy="selectin")

    __table_args__ = (
        Index("idx_subscriptions_user_status", "user_id", "status"),
        Index("idx_subscriptions_mp_id", "mercadopago_subscription_id"),
    )

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, user_id={self.user_id}, status={self.status})>"

    @property
    def is_active(self) -> bool:
        now = datetime.now(UTC)
        return (
            self.status == "active"
            and self.current_period_end > now
            and (self.cancelled_at is None or self.cancelled_at > now)
        )

    @property
    def is_trial(self) -> bool:
        if not self.trial_end:
            return False
        return datetime.now(UTC) < self.trial_end

    @property
    def days_remaining(self) -> int:
        now = datetime.now(UTC)
        if self.current_period_end <= now:
            return 0
        return (self.current_period_end - now).days
