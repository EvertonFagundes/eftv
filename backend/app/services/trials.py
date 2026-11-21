# services/trials.py - Teste gratis amarrado ao aparelho
"""Um aparelho so consome o teste gratis uma vez.

O trial era concedido no ``verify-email``, sem saber de qual aparelho se
tratava. Bastava criar outra conta no mesmo celular para ganhar mais 7 dias,
indefinidamente. O ``device_id`` do app deriva do ANDROID_ID (sobrevive a
reinstalacao), entao identifica o aparelho sem usar dado sensivel de hardware.

Dois pontos de controle, de proposito:

1. ``verify-email``: quando o app envia ``X-Device-Id``, o trial nasce ja
   vinculado e a segunda conta nem recebe teste;
2. ``/player/playlist``: se a assinatura e ``trial`` e o aparelho ja pertence
   a outra conta, o trial e revogado na hora. Isso fecha o caminho de quem
   confirma o e-mail pelo navegador (sem header de aparelho).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription
from app.models.trial_device import TrialDevice


async def owner_of(db: AsyncSession, device_id: str) -> TrialDevice | None:
    result = await db.execute(select(TrialDevice).where(TrialDevice.device_id == device_id))
    return result.scalar_one_or_none()


async def device_already_used(db: AsyncSession, device_id: str, user_id) -> bool:
    """True quando o aparelho ja consumiu trial em OUTRA conta."""
    entry = await owner_of(db, device_id)
    return entry is not None and entry.user_id != user_id


async def claim(
    db: AsyncSession,
    *,
    device_id: str,
    user_id,
    subscription_id=None,
    commit: bool = True,
) -> TrialDevice:
    """Reserva o aparelho para este trial (idempotente para o mesmo usuario)."""
    entry = await owner_of(db, device_id)
    if entry is None:
        entry = TrialDevice(
            device_id=device_id,
            user_id=user_id,
            subscription_id=subscription_id,
        )
        db.add(entry)
    elif entry.subscription_id is None and subscription_id is not None:
        entry.subscription_id = subscription_id
    if commit:
        await db.commit()
    return entry


def revoke_trial(subscription: Subscription, now: datetime | None = None) -> None:
    """Corta o trial (aparelho ja usado em outra conta)."""
    reference = now or datetime.now(UTC)
    subscription.status = "cancelled"
    subscription.cancelled_at = reference
    subscription.cancel_at_period_end = True
    subscription.auto_renew = False
