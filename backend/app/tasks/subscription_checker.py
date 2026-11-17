# tasks/subscription_checker.py - Verifica vencimentos e renovações
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.database import get_db_context
from app.models.subscription import Subscription
from app.services.mercadopago import (
    cancel_preapproval,
    get_preapproval,
    sync_payments_for_subscription,
)

logger = logging.getLogger(__name__)


async def check_expired_subscriptions() -> int:
    """
    Verifica assinaturas expiradas e atualiza status.
    Deve rodar periodicamente (ex: a cada hora via APScheduler).
    Returns: número de assinaturas atualizadas.
    """
    updated = 0
    async with get_db_context() as db:
        now = datetime.now(UTC)

        # Busca assinaturas ativas que expiraram
        result = await db.execute(
            select(Subscription).where(
                Subscription.status == "active",
                Subscription.current_period_end < now,
            )
        )
        expired = result.scalars().all()

        for sub in expired:
            # Quem pediu cancelamento nao renova, mesmo que o Mercado Pago
            # ainda diga "authorized": sem isso o cancelamento local seria
            # desfeito aqui e o cartao continuaria sendo cobrado.
            if sub.cancel_at_period_end:
                sub.status = "cancelled"
                sub.cancelled_at = now
                sub.auto_renew = False
                # Rede de seguranca: corta a recorrencia no Mercado Pago caso
                # o cancelamento enviado na hora do pedido tenha falhado.
                if sub.mercadopago_subscription_id:
                    try:
                        await cancel_preapproval(str(sub.mercadopago_subscription_id))
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "Cancelamento no Mercado Pago da assinatura %s falhou de novo",
                            sub.id,
                            exc_info=True,
                        )
                updated += 1
                continue

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
                        # Grava a cobranca da renovacao: sem ela, o cartao
                        # usado ficaria desatualizado na tela de assinatura.
                        try:
                            await sync_payments_for_subscription(
                                str(sub.mercadopago_subscription_id), db
                            )
                        except Exception:  # noqa: BLE001
                            logger.warning(
                                "Renovacao da assinatura %s sem cobranca registrada",
                                sub.id,
                                exc_info=True,
                            )
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
        result = await db.execute(select(Subscription).where(Subscription.status == "past_due"))
        past_due = result.scalars().all()

        for sub in past_due:
            if sub.mercadopago_subscription_id:
                try:
                    mp_data = await get_preapproval(sub.mercadopago_subscription_id)
                    mp_status = mp_data.get("status")

                    if mp_status == "authorized":
                        # Pagamento recuperado
                        sub.status = "active"
                        sub.current_period_start = datetime.now(UTC)
                        next_billing = mp_data.get("next_billing_date")
                        if next_billing:
                            sub.current_period_end = datetime.fromisoformat(
                                next_billing.replace("Z", "+00:00")
                            )
                        try:
                            await sync_payments_for_subscription(
                                str(sub.mercadopago_subscription_id), db
                            )
                        except Exception:  # noqa: BLE001
                            logger.warning(
                                "Cobranca de recuperacao da assinatura %s nao registrada",
                                sub.id,
                                exc_info=True,
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

    from app.models.playback_session import PlaybackSession

    cleaned = 0
    async with get_db_context() as db:
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)

        result = await db.execute(
            select(PlaybackSession).where(
                PlaybackSession.ended_at.is_(None),
                PlaybackSession.last_heartbeat < cutoff,
            )
        )
        stale = result.scalars().all()

        for session in stale:
            session.ended_at = datetime.now(UTC)
            cleaned += 1

    return cleaned
