# models/device_login_code.py - Login na TV sem digitar senha no controle
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeviceLoginCode(Base):
    """Codigo curto que a TV mostra e o celular confirma.

    Digitar e-mail e senha com o D-pad do controle remoto e o motivo numero um
    de desistencia na TV. O fluxo e o mesmo das grandes plataformas: a TV pede
    um codigo, o assinante ja logado digita esse codigo no celular e a TV recebe
    a sessao.

    Os tokens ficam guardados aqui ate a TV buscar (uma vez) e sao apagados
    depois: o codigo so vale uma vez e expira em minutos.
    """

    __tablename__ = "device_login_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Codigo sem caracteres ambiguos (sem O/0, I/1), em maiusculas: "ABCD-EFGH".
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True, index=True)
    # pending -> approved -> consumed | expired
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    device_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_device_login_codes_expires", "expires_at"),)

    def __repr__(self) -> str:
        return f"<DeviceLoginCode(code={self.code}, status={self.status})>"
