# services/rate_limit.py - Limites de uso compartilhados no banco
"""Rate limit por identidade, gravado no banco.

Motivo da troca (antes era um ``dict`` em memoria):

* reiniciar o servico zerava o contador (brute force recomecava);
* cada worker tinha o seu contador;
* o limite era por IP e, atras do proxy do Render, **todos** os clientes
  aparecem com o mesmo IP -- o balde virava um limite da base inteira: um
  abusador derrubava o cadastro/recuperacao de senha de todo mundo.

Agora a chave e a identidade (e-mail normalizado, conta) e o estado fica na
tabela ``rate_limit_counters``. A janela e fixa e reinicia quando expira.
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rate_limit import RateLimitCounter

DEFAULT_DETAIL = "Muitas tentativas. Aguarde alguns minutos e tente de novo."


def identity(value: str | None) -> str:
    """Normaliza a identidade usada na chave (e-mail sem caixa/espacos)."""
    return (value or "").strip().lower()[:150]


def scoped_key(scope: str, value: str | None) -> str:
    return f"{scope}:{identity(value) or 'anon'}"[:200]


async def hit(
    db: AsyncSession,
    *,
    key: str,
    limit: int,
    window_seconds: int,
    detail: str = DEFAULT_DETAIL,
    now: datetime | None = None,
) -> int:
    """Conta mais um acesso. Levanta 429 quando o limite da janela estoura.

    Devolve quantas tentativas restam (0 quando a proxima ja sera bloqueada).
    O incremento e persistido mesmo quando estoura, para que tentativas
    repetidas continuem dentro da mesma janela.
    """
    reference = now or datetime.now(UTC)
    threshold = reference - timedelta(seconds=max(1, window_seconds))

    result = await db.execute(select(RateLimitCounter).where(RateLimitCounter.key == key))
    counter = result.scalar_one_or_none()

    if counter is None:
        counter = RateLimitCounter(key=key, window_start=reference, count=1)
        db.add(counter)
    else:
        start = counter.window_start
        if start is not None and start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if start is None or start <= threshold:
            counter.window_start = reference
            counter.count = 1
        else:
            counter.count += 1

    await db.commit()

    if counter.count > max(1, limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )
    return max(0, max(1, limit) - counter.count)


async def reset(db: AsyncSession, *, key: str) -> None:
    """Zera uma chave (ex.: login com sucesso)."""
    await db.execute(delete(RateLimitCounter).where(RateLimitCounter.key == key))
    await db.commit()
