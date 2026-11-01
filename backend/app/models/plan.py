# models/plan.py - Modelo de plano de assinatura
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

if TYPE_CHECKING:
    from app.models.subscription import Subscription


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Básico", "Premium", "Família"
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # Preço em centavos (ex: 2990 = R$ 29,90)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    interval: Mapped[str] = mapped_column(String(20), default="month", nullable=False)  # month, year
    max_simultaneous_streams: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_devices: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    features: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False
    )  # {"hd": true, "full_hd": false, "4k": false}
    mercadopago_plan_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="plan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_plans_active_sort", "is_active", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<Plan(id={self.id}, name={self.name}, price={self.price_cents/100:.2f} {self.currency})>"

    @property
    def price_formatted(self) -> str:
        return f"{self.price_cents / 100:.2f} {self.currency}"