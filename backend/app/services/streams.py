# services/streams.py - Limite de telas simultaneas (heartbeat do app)
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.stream_session import StreamSession
from app.models.subscription import Subscription

logger = logging.getLogger(__name__)


class StreamLimitError(Exception):
    """A conta ja esta com todas as telas do plano em uso."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"Limite de {limit} tela(s) simultanea(s) atingido")


def stream_limit(subscription: Subscription) -> int:
    """Quantas telas o plano permite ao mesmo tempo.

    O plano diz o que o produto promete; ``MAX_STREAMS_PER_SUBSCRIPTION`` e o
    teto operacional. Sem ele, um plano criado por engano com 10 telas furaria
    a regra comercial (mesmo padrao ja usado no limite de aparelhos).
    """
    cap = max(1, settings.MAX_STREAMS_PER_SUBSCRIPTION)
    plan = getattr(subscription, "plan", None)
    limit = getattr(plan, "max_simultaneous_streams", None)
    try:
        value = int(limit or 1)
    except (TypeError, ValueError):
        value = 1
    return max(1, min(value, cap))


def _cutoff(now: datetime | None = None) -> datetime:
    reference = now or datetime.now(UTC)
    return reference - timedelta(seconds=settings.STREAM_SESSION_TIMEOUT_SECONDS)


async def active_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> list[StreamSession]:
    """Sessoes consideradas ativas: abertas e com heartbeat recente.

    O timeout curto e proposital: se o app for fechado ou o aparelho perder a
    rede sem avisar, a vaga volta sozinha em poucos minutos em vez de ficar
    presa (era o que acontecia com o controle antigo de aparelhos).
    """
    reference = now or datetime.now(UTC)
    result = await db.execute(
        select(StreamSession)
        .where(
            StreamSession.user_id == user_id,
            StreamSession.ended_at.is_(None),
            StreamSession.last_heartbeat >= _cutoff(reference),
        )
        .order_by(StreamSession.last_heartbeat.desc())
    )
    return list(result.scalars().all())


async def start_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    subscription_id: uuid.UUID,
    device_id: str,
    channel_ref: str,
    channel_name: str | None,
    limit: int,
) -> StreamSession:
    """Abre (ou reaproveita) a sessao de reproducao do aparelho.

    Reaproveitar a sessao do mesmo aparelho e o que permite trocar de canal
    quantas vezes quiser sem consumir vaga: o plano limita telas, nao zaps.
    """
    now = datetime.now(UTC)
    sessions = await active_sessions(db, user_id, now)

    for session in sessions:
        if session.device_id == device_id:
            session.channel_ref = channel_ref
            session.channel_name = channel_name
            session.last_heartbeat = now
            await db.commit()
            return session

    if len(sessions) >= max(limit, 1):
        raise StreamLimitError(max(limit, 1))

    session = StreamSession(
        user_id=user_id,
        subscription_id=subscription_id,
        device_id=device_id,
        channel_ref=channel_ref,
        channel_name=channel_name,
        started_at=now,
        last_heartbeat=now,
    )
    db.add(session)
    await db.commit()
    logger.info(
        "Sessao de stream aberta: user=%s device=%s canal=%s",
        user_id,
        device_id,
        channel_name or channel_ref,
    )
    return session


async def heartbeat(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> StreamSession | None:
    """Renova a sessao. Retorna None se ela foi encerrada ou expirou."""
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id,
            StreamSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None or session.ended_at is not None:
        return None

    session.last_heartbeat = datetime.now(UTC)
    await db.commit()
    return session


async def stop_session(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
) -> bool:
    """Fecha a sessao na hora em que o app sai do player."""
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id,
            StreamSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None or session.ended_at is not None:
        return False

    session.ended_at = datetime.now(UTC)
    await db.commit()
    return True


async def close_stale_sessions(db: AsyncSession) -> int:
    """Fecha sessoes abandonadas (sem heartbeat) para nao acumular lixo."""
    cutoff = _cutoff()
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.ended_at.is_(None),
            StreamSession.last_heartbeat < cutoff,
        )
    )
    stale = list(result.scalars().all())
    now = datetime.now(UTC)
    for session in stale:
        session.ended_at = now
    if stale:
        await db.commit()
        logger.info("Sessoes de stream abandonadas encerradas: %d", len(stale))
    return len(stale)
