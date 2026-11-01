# tasks/subscription_checker.py - Verifica vencimentos e renovações
from datetime import datetime, timezone
from sqlalchemy import select
from app.database import get_db_context
from app.models.subscription import Subscription
from app.services.mercadopago import get_preapproval


async def check_expired_subscriptions() -> int:
    """
    Verifica assinaturas expiradas e atualiza status.
    Deve rodar periodicamente (ex: a cada hora via APScheduler).
    Returns: número de assinaturas atualizadas.
    """
    updated = 0
    async with get_db_context() as db:
        now = datetime.now(timezone.utc)

        # Busca assinaturas ativas que expiraram
        result = await db.execute(
            select(Subscription).where(
                Subscription.status == "active",
                Subscription.current_period_end < now,
            )
        )
        expired = result.scalars().all()

        for sub in expired:
            # Tenta buscar status no Mercado Pago
            if sub.mercadopago_subscription_id:
                try:
                    mp_data = await get_preapproval(sub.mercadopago_subscription_id)
                    mp_status = mp_data.get("status")

                    if mp_status == "authorized":
                        # Renovada automaticamente
                        sub.current_period_start = now
                        # next_billing_date vem do MP
                        next_billing = mp_data.get("next_billing_date")
                        if next_billing:
                            sub.current_period_end = datetime.fromisoformat(
                                next_billing.replace("Z", "+00:00")
                            )
                        sub.status = "active"
                    elif mp_status in ["cancelled", "paused"]:
                        sub.status = "cancelled"
                        sub.cancelled_at = now
                    else:
                        sub.status = "past_due"
                except Exception:
                    # Se falhou ao consultar MP, marca como past_due
                    sub.status = "past_due"
            else:
                sub.status = "expired"

            updated += 1

    return updated


async def check_past_due_subscriptions() -> int:
    """
    Verifica assinaturas em past_due e tenta recuperar.
    Returns: número de assinaturas processadas.
    """
    processed = 0
    async with get_db_context() as db:
        result = await db.execute(
            select(Subscription).where(Subscription.status == "past_due")
        )
        past_due = result.scalars().all()

        for sub in past_due:
            if sub.mercadopago_subscription_id:
                try:
                    mp_data = await get_preapproval(sub.mercadopago_subscription_id)
                    mp_status = mp_data.get("status")

                    if mp_status == "authorized":
                        # Pagamento recuperado
                        sub.status = "active"
                        sub.current_period_start = datetime.now(timezone.utc)
                        next_billing = mp_data.get("next_billing_date")
                        if next_billing:
                            sub.current_period_end = datetime.fromisoformat(
                                next_billing.replace("Z", "+00:00")
                            )
                        processed += 1
                except Exception:
                    pass

    return processed


async def cleanup_stale_playback_sessions(max_age_hours: int = 24) -> int:
    """
    Limpa sessões de playback travadas (sem heartbeat por muito tempo).
    Returns: número de sessões encerradas.
    """
    from datetime import timedelta
    from sqlalchemy import update
    from app.models.playback_session import PlaybackSession

    cleaned = 0
    async with get_db_context() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        result = await db.execute(
            select(PlaybackSession).where(
                PlaybackSession.ended_at.is_(None),
                PlaybackSession.last_heartbeat < cutoff,
            )
        )
        stale = result.scalars().all()

        for session in stale:
            session.ended_at = datetime.now(timezone.utc)
            cleaned += 1

    return cleaned