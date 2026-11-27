# models/playlist_cache.py - Ultima playlist valida guardada no banco
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlaylistCache(Base):
    """Copia comprimida da ultima M3U valida.

    O provedor bloqueia o Render por regiao/IP. Quando o download falha, o
    backend serve esta copia em vez de devolver 502. A linha e unica (id=1);
    o upload e feito por um admin a partir de uma rede que alcanca o provedor.
    """

    __tablename__ = "playlist_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_gzip: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    compressed_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
