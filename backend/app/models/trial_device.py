# models/trial_device.py - Aparelho que ja consumiu o teste gratis
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TrialDevice(Base):
    """Vinculo entre um aparelho e o teste gratis que ele ja consumiu.

    O teste era concedido por **conta**: a mesma pessoa criava outra conta no
    mesmo celular e ganhava mais 7 dias, indefinidamente. O ``device_id`` do
    app sobrevive a reinstalacao (deriva do ANDROID_ID), entao serve de chave:

    - um aparelho so ativa teste uma vez;
    - o vinculo permanece mesmo depois de cancelar/expirar;
    - e checado tanto na verificacao de e-mail (app) quanto no primeiro
      ``/player/playlist`` (fecha o caminho de quem confirma pelo navegador).
    """

    __tablename__ = "trial_devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return f"<TrialDevice(device_id={self.device_id}, user_id={self.user_id})>"
