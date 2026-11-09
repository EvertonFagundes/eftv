# services/mercadopago.py - Integração Mercado Pago
import hashlib
import hmac
import logging
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import httpx
from sqlalchemy import select

from app.config import settings
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User

MERCADOPAGO_BASE_URL = "https://api.mercadopago.com"
if settings.MERCADOPAGO_SANDBOX:
    MERCADOPAGO_BASE_URL = (
        "https://api.mercadopago.com"  # Sandbox usa mesma URL, headers diferentes
    )

logger = logging.getLogger(__name__)

# Estados da preapproval no Mercado Pago que liberam o acesso.
_ACTIVE_PREAPPROVAL_STATUSES = {"authorized"}


def validate_webhook_signature(headers, data_id: str | None) -> bool:
    """Valida o header ``x-signature`` enviado pelo Mercado Pago.

    O Mercado Pago assina ``id:<data.id>;request-id:<x-request-id>;ts:<ts>;``
    com HMAC-SHA256 usando o segredo configurado no painel. Sem o segredo
    configurado a validacao e ignorada (ambiente de desenvolvimento).

    Retorna ``False`` quando o segredo existe e a assinatura nao confere.
    """
    secret = settings.MERCADOPAGO_WEBHOOK_SECRET
    if not secret:
        logger.warning(
            "MERCADOPAGO_WEBHOOK_SECRET nao configurado: webhook aceito sem validar assinatura"
        )
        return True

    signature = headers.get("x-signature")
    if not signature:
        return False

    parts = {}
    for chunk in signature.split(","):
        key, _, value = chunk.partition("=")
        parts[key.strip()] = value.strip()

    ts = parts.get("ts")
    received = parts.get("v1")
    if not ts or not received:
        return False

    request_id = headers.get("x-request-id") or ""
    manifest = f"id:{data_id if data_id is not None else ''};request-id:{request_id};ts:{ts};"
    expected = hmac.new(
        secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, received)


def _get_headers(idempotency_key: str | None = None) -> dict:
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
    payer_name: str | None = None,
    payer_phone: str | None = None,
    payer_cpf: str | None = None,
    back_urls: dict | None = None,
) -> dict:
    """
    Cria preferência de checkout no Mercado Pago para assinatura (preapproval).
    Retorna dict com id, init_point, sandbox_init_point.
    """
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado")

    # O endpoint /preapproval aceita apenas os campos da assinatura. Campos do
    # Checkout Pro (back_urls, auto_return, notification_url, payer) nao
    # existem aqui: o webhook e configurado no painel da aplicacao no Mercado
    # Pago e o retorno e uma unica back_url.
    frontend = settings.FRONTEND_URL.rstrip("/")
    back_url = f"{frontend}/checkout.html"
    if back_urls:
        back_url = back_urls.get("success", back_url)

    preapproval_data = {
        "reason": f"EFTV - {plan.name}",
        "external_reference": str(user.id),
        "payer_email": payer_email,
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": round(plan.price_cents / 100, 2),
            "currency_id": plan.currency or "BRL",
        },
        "back_url": back_url,
        # Sem cartao tokenizado no app: o cliente escolhe o meio de pagamento
        # no checkout do Mercado Pago. O acesso so e liberado pelo webhook.
        "status": "pending",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MERCADOPAGO_BASE_URL}/preapproval",
            json=preapproval_data,
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Erro ao criar assinatura MP: {response.status_code} - {response.text}")

    return cast(dict, response.json())


async def get_preapproval(preapproval_id: str) -> dict:
    """Busca detalhes de uma preapproval (assinatura)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{MERCADOPAGO_BASE_URL}/preapproval/{preapproval_id}",
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Erro ao buscar preapproval: {response.status_code} - {response.text}")

    return cast(dict, response.json())


async def cancel_preapproval(preapproval_id: str) -> dict:
    """Cancela uma preapproval (assinatura)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.put(
            f"{MERCADOPAGO_BASE_URL}/preapproval/{preapproval_id}",
            json={"status": "cancelled"},
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Erro ao cancelar preapproval: {response.status_code} - {response.text}"
        )

    return cast(dict, response.json())


async def get_payment(payment_id: str) -> dict:
    """Busca detalhes de um pagamento."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{MERCADOPAGO_BASE_URL}/v1/payments/{payment_id}",
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Erro ao buscar pagamento: {response.status_code} - {response.text}")

    return cast(dict, response.json())


async def get_authorized_payment(authorized_payment_id: str) -> dict:
    """Busca um pagamento autorizado (cobranca recorrente da assinatura)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{MERCADOPAGO_BASE_URL}/authorized_payments/{authorized_payment_id}",
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Erro ao buscar pagamento autorizado: {response.status_code} - {response.text}"
        )

    return cast(dict, response.json())


def _parse_datetime(value: str | None) -> datetime | None:
    """Converte as datas ISO do Mercado Pago em ``datetime`` com timezone."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _find_subscription(
    db, preapproval_id: str | None, external_reference: str | None = None
) -> Subscription | None:
    """Localiza a assinatura pelo id da preapproval ou pelo usuario."""
    if preapproval_id:
        result = await db.execute(
            select(Subscription).where(Subscription.mercadopago_subscription_id == preapproval_id)
        )
        subscription = result.scalar_one_or_none()
        if subscription is not None:
            return cast(Subscription | None, subscription)

    if external_reference:
        try:
            user_id = UUID(str(external_reference))
        except ValueError:
            return None
        result = await db.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
        )
        subscription = result.scalars().first()
        if subscription is not None and preapproval_id:
            subscription.mercadopago_subscription_id = preapproval_id
        return cast(Subscription | None, subscription)

    return None


async def process_webhook(payload: dict, db, data_id: str | None = None) -> None:
    """
    Processa webhook do Mercado Pago.

    Os eventos reais de assinatura enviados pelo Mercado Pago sao:
    - ``subscription_preapproval``: criacao/atualizacao da assinatura;
    - ``subscription_authorized_payment``: cobranca recorrente aprovada ou
      rejeitada.
    """
    event_type = payload.get("type") or payload.get("topic")
    data = payload.get("data") or {}
    resource_id = data.get("id") or payload.get("id") or data_id

    if not resource_id:
        logger.warning("Webhook do Mercado Pago sem id de recurso: %s", payload)
        return

    resource_id = str(resource_id)

    if event_type in ("subscription_preapproval", "preapproval"):
        await _handle_preapproval(resource_id, db)
    elif event_type in ("subscription_authorized_payment", "authorized_payment"):
        await _handle_authorized_payment(resource_id, db)
    else:
        logger.info("Webhook do Mercado Pago ignorado: %s", event_type)


async def _handle_preapproval(preapproval_id: str, db) -> None:
    """Sincroniza status e periodo da assinatura com a preapproval."""
    data = await get_preapproval(preapproval_id)
    subscription = await _find_subscription(db, preapproval_id, data.get("external_reference"))

    if subscription is None:
        logger.warning("Preapproval %s sem assinatura correspondente", preapproval_id)
        return

    subscription.mercadopago_subscription_id = preapproval_id
    preapproval_status = data.get("status")

    if preapproval_status in _ACTIVE_PREAPPROVAL_STATUSES:
        subscription.status = "active"
        subscription.auto_renew = True
        subscription.cancelled_at = None
        subscription.cancel_at_period_end = False
    elif preapproval_status == "pending":
        # Nao rebaixa quem ja tem acesso (trial ou assinatura ativa).
        if subscription.status not in ("active", "trial"):
            subscription.status = "pending"
    elif preapproval_status == "paused":
        subscription.status = "past_due"
    elif preapproval_status == "cancelled":
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.now(UTC)
        subscription.auto_renew = False

    start = _parse_datetime(data.get("date_created"))
    end = _parse_datetime(data.get("next_payment_date"))
    if start is not None:
        subscription.current_period_start = start
    if end is not None:
        subscription.current_period_end = end


async def _handle_authorized_payment(authorized_payment_id: str, db) -> None:
    """Registra a cobranca recorrente e atualiza o acesso do assinante."""
    data = await get_authorized_payment(authorized_payment_id)
    preapproval_id = data.get("preapproval_id")
    subscription = await _find_subscription(db, preapproval_id, data.get("external_reference"))

    if subscription is None:
        logger.warning(
            "Pagamento autorizado %s sem assinatura correspondente", authorized_payment_id
        )
        return

    payment_info = data.get("payment") or {}
    mp_payment_id = str(payment_info.get("id") or authorized_payment_id)
    payment_status = data.get("status")

    # Idempotencia: o Mercado Pago reenvia o mesmo evento se nao receber 200.
    existing = await db.execute(
        select(Payment).where(Payment.mercadopago_payment_id == mp_payment_id)
    )
    if existing.scalar_one_or_none() is not None:
        return

    approved = payment_status in ("processed", "approved")
    if approved:
        status_label = "approved"
    elif payment_status == "refunded":
        status_label = "refunded"
    else:
        status_label = "rejected"

    amount = data.get("transaction_amount")
    if amount is None:
        amount = payment_info.get("transaction_amount") or 0

    payment = Payment(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        plan_id=subscription.plan_id,
        mercadopago_payment_id=mp_payment_id,
        amount_cents=int(round(float(amount) * 100)),
        currency=data.get("currency_id", "BRL"),
        status=status_label,
        payment_method=payment_info.get("payment_method_id"),
        paid_at=datetime.now(UTC) if approved else None,
        metadata=data,
    )
    db.add(payment)

    if approved:
        subscription.status = "active"
        subscription.auto_renew = True
        subscription.current_period_start = datetime.now(UTC)
        end = _parse_datetime(data.get("next_payment_date"))
        if end is not None:
            subscription.current_period_end = end
    elif status_label == "refunded":
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.now(UTC)
        subscription.auto_renew = False
    else:
        subscription.status = "past_due"
