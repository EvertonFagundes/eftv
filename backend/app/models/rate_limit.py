# models/rate_limit.py - Contadores de rate limit compartilhados
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RateLimitCounter(Base):
    """Janela deslizante simples gravada no banco.

    Antes o contador vivia na memoria do processo: zerava a cada deploy e cada
    worker tinha o seu. Como o app roda atras de um proxy que entrega o mesmo
    IP para todos (Render), um balde em memoria por IP acabava sendo um balde
    **da base inteira** -- um abusador derrubava o cadastro de todo mundo.

    Aqui a chave e a identidade (e-mail/conta), nao o IP, e o estado sobrevive
    a reinicios.
    """

    __tablename__ = "rate_limit_counters"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
