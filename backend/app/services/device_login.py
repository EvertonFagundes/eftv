# services/device_login.py - Login por codigo na TV (sem senha no controle)
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.device_login_code import DeviceLoginCode
from app.services import sessions
from app.services.auth_service import create_token_pair

logger = logging.getLogger(__name__)

# Sem O/0 e I/1: o cliente le o codigo na TV e digita no celular.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
MAX_DEVICE_NAME = 120


def normalize_code(raw: str | None) -> str:
    """Aceita "abcd efgh", "ABCD-EFGH" ou "abcdefgh" e devolve sempre igual."""
    cleaned = "".join(ch for ch in (raw or "").upper() if ch.isalnum())
    return cleaned


def format_code(code: str) -> str:
    """Mostra em dois blocos: mais facil de ler na TV e de digitar."""
    return f"{code[:4]}-{code[4:]}"


def _generate_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))


async def create_code(db: AsyncSession, device_name: str | None = None) -> DeviceLoginCode:
    """Cria o codigo que a TV exibe. Tambem limpa os vencidos."""
    now = datetime.now(UTC)
    await db.execute(
        delete(DeviceLoginCode).where(
            DeviceLoginCode.expires_at < now - timedelta(hours=1),
            DeviceLoginCode.status.in_(("expired", "consumed")),
        )
    )

    code = _generate_code()
    # Colisao e improvavel (32^8), mas o indice unico nao pode estourar.
    for _ in range(5):
        exists = await db.execute(select(DeviceLoginCode.id).where(DeviceLoginCode.code == code))
        if exists.first() is None:
            break
        code = _generate_code()

    entry = DeviceLoginCode(
        code=code,
        status="pending",
        device_name=(device_name or "").strip()[:MAX_DEVICE_NAME] or None,
        created_at=now,
        expires_at=now + timedelta(minutes=settings.DEVICE_CODE_TTL_MINUTES),
    )
    db.add(entry)
    await db.commit()
    return entry


def _is_expired(entry: DeviceLoginCode, now: datetime | None = None) -> bool:
    reference = now or datetime.now(UTC)
    expires = entry.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= reference


async def approve_code(db: AsyncSession, *, code: str, user_id, email: str | None = None) -> DeviceLoginCode:
    """Celular aprova o pedido da TV e gera a sessao que ela vai receber."""
    result = await db.execute(
        select(DeviceLoginCode).where(DeviceLoginCode.code == normalize_code(code))
    )
    entry = result.scalar_one_or_none()
    if entry is None or entry.status != "pending":
        raise ValueError("invalid")
    if _is_expired(entry):
        entry.status = "expired"
        await db.commit()
        raise ValueError("expired")

    access_token, _access_jti, refresh_token, refresh_jti = create_token_pair(str(user_id))
    # Registra o refresh para que o logout/rotacao consigam revogar a sessao
    # criada na TV (antes ela ficava valida mesmo depois do logout).
    await sessions.register(
        db,
        user_id=user_id,
        jti=refresh_jti,
        expires_at=datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        commit=False,
    )
    entry.user_id = user_id
    entry.email = email
    entry.access_token = access_token
    entry.refresh_token = refresh_token
    entry.status = "approved"
    entry.approved_at = datetime.now(UTC)
    await db.commit()
    logger.info("TV autorizada pelo celular: codigo=%s", format_code(entry.code))
    return entry


async def poll_code(db: AsyncSession, code: str) -> tuple[str, DeviceLoginCode | None]:
    """A TV pergunta o estado. Quando aprovado, entrega os tokens UMA vez."""
    normalized = normalize_code(code)
    if len(normalized) != CODE_LENGTH:
        return "invalid", None

    result = await db.execute(select(DeviceLoginCode).where(DeviceLoginCode.code == normalized))
    entry = result.scalar_one_or_none()
    if entry is None:
        return "invalid", None

    if entry.status == "pending" and _is_expired(entry):
        entry.status = "expired"
        await db.commit()
        return "expired", None

    if entry.status == "approved":
        # Consome agora: um codigo vazado depois nao vira sessao.
        entry.status = "consumed"
        await db.commit()
        return "approved", entry

    return entry.status, None
