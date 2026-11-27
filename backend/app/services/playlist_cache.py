# services/playlist_cache.py - Cache persistente da playlist licenciada
"""Guarda a ultima M3U valida para sobreviver ao bloqueio do provedor.

O provedor entrega a lista para IPs brasileiros, mas responde a pagina padrao
do nginx para o Render (EUA). O admin baixa a lista em uma rede autorizada e
envia comprimida para o backend; o `/player/playlist-text` usa essa copia
quando o provedor falha.

O conteudo tem credenciais do provedor (nas URLs dos canais), por isso:
- o upload exige admin;
- nada da lista aparece em log ou no /health;
- o cache e servido apenas para assinantes ativos, pelo mesmo endpoint.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import logging
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.playlist_cache import PlaylistCache
from app.services.playlist_fetch import looks_like_m3u

logger = logging.getLogger(__name__)

CACHE_ID = 1
_GZIP_MAGIC = b"\x1f\x8b"


class PlaylistCacheError(ValueError):
    """Falha segura: a mensagem nao contem conteudo nem credenciais."""


@dataclass(frozen=True)
class CacheInfo:
    updated_at: datetime
    size_bytes: int
    compressed_bytes: int
    sha256: str
    source: str | None

    @property
    def age_seconds(self) -> int:
        updated = self.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
        return max(0, int((datetime.now(UTC) - updated).total_seconds()))

    @property
    def stale(self) -> bool:
        return self.age_seconds > max(1, int(settings.PLAYLIST_CACHE_STALE_HOURS)) * 3600

    def to_dict(self) -> dict[str, object]:
        return {
            "updated_at": self.updated_at.isoformat(),
            "age_seconds": self.age_seconds,
            "stale": self.stale,
            "size_bytes": self.size_bytes,
            "compressed_bytes": self.compressed_bytes,
            "sha256": self.sha256[:12],
            "source": self.source,
        }


# Copia em memoria para nao buscar 20 MB no Postgres a cada request.
_lock = asyncio.Lock()
_cached_raw: bytes | None = None
_cached_sha: str | None = None


def _info_from_meta(
    *,
    updated_at: datetime,
    size_bytes: int,
    compressed_bytes: int,
    sha256: str,
    source: str | None,
) -> CacheInfo:
    return CacheInfo(
        updated_at=updated_at,
        size_bytes=size_bytes,
        compressed_bytes=compressed_bytes,
        sha256=sha256,
        source=source,
    )


def _validate(raw: bytes) -> None:
    if not raw:
        raise PlaylistCacheError("Playlist vazia")
    if len(raw) > max(1, int(settings.PLAYLIST_CACHE_MAX_BYTES)):
        raise PlaylistCacheError("Playlist maior que o limite do cache")
    if not looks_like_m3u(raw):
        raise PlaylistCacheError("Conteudo nao e uma playlist M3U")


def decode_upload(body: bytes) -> bytes:
    """Descomprime o upload com limite, sem confiar no tamanho declarado."""
    if not body:
        raise PlaylistCacheError("Corpo vazio")
    max_bytes = max(1, int(settings.PLAYLIST_CACHE_MAX_BYTES))
    if body.startswith(_GZIP_MAGIC):
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            raw = decompressor.decompress(body, max_bytes + 1)
            raw += decompressor.flush()
        except zlib.error as exc:
            raise PlaylistCacheError("Gzip invalido") from exc
        if (
            len(raw) > max_bytes
            or decompressor.unconsumed_tail
            or decompressor.unused_data
            or not decompressor.eof
        ):
            raise PlaylistCacheError("Playlist maior que o limite do cache")
        return raw
    if len(body) > max_bytes:
        raise PlaylistCacheError("Playlist maior que o limite do cache")
    return body


async def save_playlist(
    db: AsyncSession,
    raw: bytes,
    *,
    source: str = "upload",
) -> CacheInfo:
    """Valida, comprime e grava a playlist (linha unica)."""
    _validate(raw)
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    sha256 = hashlib.sha256(raw).hexdigest()
    now = datetime.now(UTC)
    info = _info_from_meta(
        updated_at=now,
        size_bytes=len(raw),
        compressed_bytes=len(compressed),
        sha256=sha256,
        source=source[:40] or None,
    )

    async with _lock:
        row = await db.get(PlaylistCache, CACHE_ID)
        if row is None:
            row = PlaylistCache(
                id=CACHE_ID,
                content_gzip=compressed,
                sha256=sha256,
                size_bytes=len(raw),
                compressed_bytes=len(compressed),
                source=info.source,
                updated_at=now,
            )
            db.add(row)
        else:
            row.content_gzip = compressed
            row.sha256 = sha256
            row.size_bytes = len(raw)
            row.compressed_bytes = len(compressed)
            row.source = info.source
            row.updated_at = now
        await db.commit()
        # Nao mantem os 84 MB descomprimidos na memoria depois do upload: o
        # proximo request carrega do banco e deixa a copia pronta para servir.
        global _cached_raw, _cached_sha
        _cached_raw = None
        _cached_sha = None

    logger.info(
        "Cache da playlist atualizado (%s bytes, %s comprimido, fonte=%s)",
        len(raw),
        len(compressed),
        info.source,
    )
    return info


async def cache_metadata(db: AsyncSession) -> CacheInfo | None:
    """Metadados sem carregar o blob (para o painel admin)."""
    result = await db.execute(
        select(
            PlaylistCache.updated_at,
            PlaylistCache.size_bytes,
            PlaylistCache.compressed_bytes,
            PlaylistCache.sha256,
            PlaylistCache.source,
        ).where(PlaylistCache.id == CACHE_ID)
    )
    row = result.first()
    if row is None:
        return None
    return _info_from_meta(
        updated_at=row.updated_at,
        size_bytes=row.size_bytes,
        compressed_bytes=row.compressed_bytes,
        sha256=row.sha256,
        source=row.source,
    )


async def load_cached_playlist(db: AsyncSession) -> tuple[bytes, CacheInfo] | None:
    """Devolve a ultima playlist valida, usando a copia em memoria quando pode."""
    global _cached_raw, _cached_sha
    info = await cache_metadata(db)
    if info is None:
        return None
    if _cached_raw is not None and _cached_sha == info.sha256:
        return _cached_raw, info

    result = await db.execute(select(PlaylistCache).where(PlaylistCache.id == CACHE_ID))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    try:
        raw = gzip.decompress(row.content_gzip)
    except OSError as exc:
        logger.error("Cache da playlist corrompido: %s", exc.__class__.__name__)
        return None
    if hashlib.sha256(raw).hexdigest() != row.sha256 or not looks_like_m3u(raw):
        logger.error("Cache da playlist invalido (hash/M3U)")
        return None

    _cached_raw = raw
    _cached_sha = row.sha256
    return raw, info


async def clear_playlist(db: AsyncSession) -> None:
    """Remove o cache (admin)."""
    async with _lock:
        await db.execute(delete(PlaylistCache).where(PlaylistCache.id == CACHE_ID))
        await db.commit()
        global _cached_raw, _cached_sha
        _cached_raw = None
        _cached_sha = None
    logger.info("Cache da playlist removido")


def clear_memory_cache() -> None:
    """Limpa apenas a copia em memoria (testes)."""
    global _cached_raw, _cached_sha
    _cached_raw = None
    _cached_sha = None
