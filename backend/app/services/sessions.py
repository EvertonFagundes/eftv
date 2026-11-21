# services/sessions.py - Registro dos refresh tokens emitidos
"""Controla quais refresh tokens existem, para poder revogar de verdade.

Antes o refresh token era um JWT sem estado: o logout so apagava o cookie e a
rotacao nao invalidava o token antigo. Quem copiasse a sessao (TV box
compartilhada, backup, aparelho com root) continuava renovando o acesso.

Agora cada token emitido tem uma linha em ``refresh_tokens``. O token continua
sendo JWT -- o banco so responde "esta revogado?" na hora de renovar.
"""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


async def register(
    db: AsyncSession,
    *,
    user_id,
    jti: str,
    expires_at: datetime,
    device_id: str | None = None,
    commit: bool = True,
) -> RefreshToken:
    """Grava o refresh token recem-emitido."""
    token = RefreshToken(
        jti=jti,
        user_id=user_id,
        device_id=(device_id or None),
        expires_at=expires_at,
    )
    db.add(token)
    if commit:
        await db.commit()
    return token


async def get(db: AsyncSession, jti: str) -> RefreshToken | None:
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    return result.scalar_one_or_none()


def is_usable(token: RefreshToken | None, now: datetime | None = None) -> bool:
    """True quando o token existe, nao foi revogado e ainda nao venceu."""
    if token is None or token.revoked_at is not None:
        return False
    reference = now or datetime.now(UTC)
    expires = token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires > reference


async def revoke(db: AsyncSession, jti: str) -> bool:
    """Revoga um token. Devolve False se ele nem existia."""
    token = await get(db, jti)
    if token is None:
        return False
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        await db.commit()
    return True


async def revoke_all(db: AsyncSession, user_id, *, commit: bool = True) -> int:
    """Derruba todas as sessoes de uma conta (logout global / suporte)."""
    result = await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .where(RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    if commit:
        await db.commit()
    return int(result.rowcount or 0)
