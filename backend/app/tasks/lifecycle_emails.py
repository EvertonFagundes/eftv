# tasks/lifecycle_emails.py - Avisos que evitam churn silencioso
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.database import get_db_context
from app.models.subscription import Subscription
from app.models.user import User
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


def _format_date(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%d/%m/%Y")


async def send_lifecycle_emails() -> dict[str, int]:
    """Envia os avisos que o cliente precisa receber (uma vez cada).

    - teste gratis terminando em ate 24h: sem isso o acesso simplesmente
      acaba e o cliente descobre no app;
    - cartao recusado: o Mercado Pago para de cobrar e a conta expira em
      silencio se ninguem avisar.
    """
    sent = {"trial_ending": 0, "trial_expired": 0, "payment_failed": 0}
    now = datetime.now(UTC)

    async with get_db_context() as db:
        trial_result = await db.execute(
            select(Subscription, User)
            .join(User, User.id == Subscription.user_id)
            .where(
                Subscription.status == "trial",
                Subscription.trial_end.is_not(None),
                Subscription.trial_end > now,
                Subscription.trial_end <= now + timedelta(hours=24),
                Subscription.trial_reminder_sent_at.is_(None),
            )
        )
        for subscription, user in trial_result.all():
            try:
                ok = await email_service.send_trial_ending_email(
                    user.email,
                    _format_date(subscription.trial_end),
                    user.full_name,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Falha ao avisar o fim do teste da assinatura %s",
                    subscription.id,
                    exc_info=True,
                )
                continue
            if ok:
                subscription.trial_reminder_sent_at = now
                sent["trial_ending"] += 1

        # Teste vencido: avisa uma vez, so para quem venceu nos ultimos 7 dias
        # (sem isso, toda conta antiga receberia um e-mail na primeira rodada).
        expired_result = await db.execute(
            select(Subscription, User)
            .join(User, User.id == Subscription.user_id)
            .where(
                Subscription.status == "expired",
                Subscription.trial_end.is_not(None),
                Subscription.trial_end <= now,
                Subscription.trial_end >= now - timedelta(days=7),
                Subscription.trial_expired_notified_at.is_(None),
            )
        )
        for subscription, user in expired_result.all():
            try:
                ok = await email_service.send_trial_expired_email(user.email, user.full_name)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Falha ao avisar o fim do teste vencido da assinatura %s",
                    subscription.id,
                    exc_info=True,
                )
                continue
            if ok:
                subscription.trial_expired_notified_at = now
                sent["trial_expired"] += 1

        failed_result = await db.execute(
            select(Subscription, User)
            .join(User, User.id == Subscription.user_id)
            .where(
                Subscription.status == "past_due",
                Subscription.payment_failed_notified_at.is_(None),
            )
        )
        for subscription, user in failed_result.all():
            try:
                ok = await email_service.send_payment_failed_email(user.email, user.full_name)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Falha ao avisar cartao recusado da assinatura %s",
                    subscription.id,
                    exc_info=True,
                )
                continue
            if ok:
                subscription.payment_failed_notified_at = now
                sent["payment_failed"] += 1

        await db.commit()

    if sent["trial_ending"] or sent["trial_expired"] or sent["payment_failed"]:
        logger.info("Avisos de assinatura enviados: %s", sent)
    return sent
