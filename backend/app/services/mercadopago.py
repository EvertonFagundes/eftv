# services/mercadopago.py - Integração Mercado Pago
import httpx
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from app.config import settings
from app.models.user import User
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.payment import Payment


MERCADOPAGO_BASE_URL = "https://api.mercadopago.com"
if settings.MERCADOPAGO_SANDBOX:
    MERCADOPAGO_BASE_URL = "https://api.mercadopago.com"  # Sandbox usa mesma URL, headers diferentes


def _get_headers(idempotency_key: Optional[str] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {settings.MERCADOPAGO_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return headers


async def create_checkout_preference(
    user: User,
    plan: Plan,
    payer_email: str,
    payer_name: Optional[str] = None,
    payer_phone: Optional[str] = None,
    payer_cpf: Optional[str] = None,
    back_urls: Optional[dict] = None,
) -> dict:
    """
    Cria preferência de checkout no Mercado Pago para assinatura (preapproval).
    Retorna dict com id, init_point, sandbox_init_point.
    """
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado")

    # Dados do pagador
    payer = {"email": payer_email}
    if payer_name:
        payer["name"] = payer_name.split()[0]
        payer["surname"] = " ".join(payer_name.split()[1:]) if len(payer_name.split()) > 1 else ""
    if payer_phone:
        # Formato: {"area_code": "11", "number": "999999999"}
        phone_clean = payer_phone.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
        if len(phone_clean) >= 10:
            payer["phone"] = {"area_code": phone_clean[:2], "number": phone_clean[2:]}
    if payer_cpf:
        payer["identification"] = {"type": "CPF", "number": payer_cpf}

    # URLs de retorno
    default_back_urls = {
        "success": f"{settings.FRONTEND_URL}/account?checkout=success",
        "failure": f"{settings.FRONTEND_URL}/account?checkout=failure",
        "pending": f"{settings.FRONTEND_URL}/account?checkout=pending",
    }
    if back_urls:
        default_back_urls.update(back_urls)

    # Preference data para preapproval (assinatura recorrente)
    preference_data = {
        "preapproval_plan_id": plan.mercadopago_plan_id,
        "payer": payer,
        "back_urls": default_back_urls,
        "auto_return": "approved",
        "external_reference": str(user.id),
        "notification_url": f"{settings.FRONTEND_URL.replace('app.', 'api.')}/subscriptions/webhook/mercadopago",
    }

    # Remove None values
    preference_data = {k: v for k, v in preference_data.items() if v is not None}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MERCADOPAGO_BASE_URL}/preapproval",
            json=preference_data,
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Erro ao criar preferência MP: {response.status_code} - {response.text}")

    return response.json()


async def get_preapproval(preapproval_id: str) -> dict:
    """Busca detalhes de uma preapproval (assinatura)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{MERCADOPAGO_BASE_URL}/preapproval/{preapproval_id}",
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Erro ao buscar preapproval: {response.status_code} - {response.text}")

    return response.json()


async def cancel_preapproval(preapproval_id: str) -> dict:
    """Cancela uma preapproval (assinatura)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.put(
            f"{MERCADOPAGO_BASE_URL}/preapproval/{preapproval_id}",
            json={"status": "cancelled"},
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Erro ao cancelar preapproval: {response.status_code} - {response.text}")

    return response.json()


async def get_payment(payment_id: str) -> dict:
    """Busca detalhes de um pagamento."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{MERCADOPAGO_BASE_URL}/v1/payments/{payment_id}",
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Erro ao buscar pagamento: {response.status_code} - {response.text}")

    return response.json()


async def process_webhook(payload: dict, db) -> None:
    """
    Processa webhook do Mercado Pago.
    Tipos de evento:
    - subscription_preapproval_payment_created: pagamento de assinatura criado
    - subscription_preapproval_payment_rejected: pagamento rejeitado
    - subscription_preapproval_cancelled: assinatura cancelada
    - subscription_authorized_payment_rejected: pagamento autorizado rejeitado
    - chargeback: chargeback
    """
    from sqlalchemy import select

    event_type = payload.get("type")
    data = payload.get("data", {})
    resource_id = data.get("id")

    if not resource_id:
        return

    # Idempotência: verifica se já processou este evento
    existing = await db.execute(
        select(Payment).where(Payment.mercadopago_payment_id == str(resource_id))
    )
    if existing.scalar_one_or_none():
        return  # Já processado

    if event_type == "subscription_preapproval_payment_created":
        await _handle_payment_approved(resource_id, db)
    elif event_type == "subscription_preapproval_cancelled":
        await _handle_subscription_cancelled(resource_id, db)
    elif event_type in ["subscription_preapproval_payment_rejected", "subscription_authorized_payment_rejected"]:
        await _handle_payment_rejected(resource_id, db)
    elif event_type == "chargeback":
        await _handle_chargeback(resource_id, db)


async def _handle_payment_approved(payment_id: str, db) -> None:
    """Processa pagamento aprovado - ativa/renova assinatura."""
    payment_data = await get_payment(payment_id)
    external_ref = payment_data.get("external_reference")
    preapproval_id = payment_data.get("preapproval_id")

    if not external_ref:
        return

    # Busca subscription pelo preapproval_id
    sub_result = await db.execute(
        select(Subscription).where(Subscription.mercadopago_subscription_id == preapproval_id)
    )
    subscription = sub_result.scalar_one_or_none()

    if not subscription:
        return

    # Atualiza subscription
    subscription.status = "active"
    subscription.current_period_start = datetime.now(timezone.utc)
    # next_period_end vem do Mercado Pago
    next_period = payment_data.get("date_of_expiration")
    if next_period:
        subscription.current_period_end = datetime.fromisoformat(next_period.replace("Z", "+00:00"))

    # Registra payment
    payment = Payment(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        plan_id=subscription.plan_id,
        mercadopago_payment_id=payment_id,
        amount_cents=int(float(payment_data.get("transaction_amount", 0)) * 100),
        currency=payment_data.get("currency_id", "BRL"),
        status="approved",
        payment_method=payment_data.get("payment_method_id"),
        paid_at=datetime.now(timezone.utc),
        metadata=payment_data,
    )
    db.add(payment)


async def _handle_subscription_cancelled(preapproval_id: str, db) -> None:
    """Processa cancelamento de assinatura."""
    sub_result = await db.execute(
        select(Subscription).where(Subscription.mercadopago_subscription_id == preapproval_id)
    )
    subscription = sub_result.scalar_one_or_none()

    if subscription:
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.now(timezone.utc)
        subscription.auto_renew = False


async def _handle_payment_rejected(payment_id: str, db) -> None:
    """Processa pagamento rejeitado - marca subscription como past_due."""
    payment_data = await get_payment(payment_id)
    preapproval_id = payment_data.get("preapproval_id")

    sub_result = await db.execute(
        select(Subscription).where(Subscription.mercadopago_subscription_id == preapproval_id)
    )
    subscription = sub_result.scalar_one_or_none()

    if subscription:
        subscription.status = "past_due"

    # Registra payment rejeitado
    if subscription:
        payment = Payment(
            user_id=subscription.user_id,
            subscription_id=subscription.id,
            plan_id=subscription.plan_id,
            mercadopago_payment_id=payment_id,
            amount_cents=int(float(payment_data.get("transaction_amount", 0)) * 100),
            currency=payment_data.get("currency_id", "BRL"),
            status="rejected",
            payment_method=payment_data.get("payment_method_id"),
            metadata=payment_data,
        )
        db.add(payment)


async def _handle_chargeback(payment_id: str, db) -> None:
    """Processa chargeback - cancela assinatura e marca payment."""
    payment_data = await get_payment(payment_id)
    preapproval_id = payment_data.get("preapproval_id")

    sub_result = await db.execute(
        select(Subscription).where(Subscription.mercadopago_subscription_id == preapproval_id)
    )
    subscription = sub_result.scalar_one_or_none()

    if subscription:
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.now(timezone.utc)

    if subscription:
        payment = Payment(
            user_id=subscription.user_id,
            subscription_id=subscription.id,
            plan_id=subscription.plan_id,
            mercadopago_payment_id=payment_id,
            amount_cents=int(float(payment_data.get("transaction_amount", 0)) * 100),
            currency=payment_data.get("currency_id", "BRL"),
            status="refunded",
            payment_method=payment_data.get("payment_method_id"),
            paid_at=datetime.now(timezone.utc),
            metadata=payment_data,
        )
        db.add(payment)