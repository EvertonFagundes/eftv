# models/category.py - Modelo de categoria de canais
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

if TYPE_CHECKING:
    from app.models.channel import Channel


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)  # "esportes", "filmes", "infantil"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(10), nullable=True)  # Emoji ou código do ícone
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # Hex color
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_adult: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Para categoria 18+
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relacionamentos
    channels: Mapped[list["Channel"]] = relationship(
        "Channel", back_populates="category", lazy="selectin"
    )

    __table_args__ = (
        Index("idx_categories_active_sort", "is_active", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<Category(id={self.id}, slug={self.slug}, name={self.name})>"