import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.config import settings
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.services import mercadopago


class FakeResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def first(self):
        return self.value


class FakeSession:
    """Entrega resultados na ordem e guarda os objetos adicionados."""

    def __init__(self, *results) -> None:
        self.results = list(results)
        self.added = []

    async def execute(self, *args, **kwargs):
        if self.results:
            return FakeResult(self.results.pop(0))
        return FakeResult(None)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def make_subscription(**kwargs) -> Subscription:
    now = datetime.now(UTC)
    data = {
        "user_id": uuid4(),
        "plan_id": uuid4(),
        "status": "trial",
        "current_period_start": now,
        "current_period_end": now + timedelta(days=7),
        "auto_renew": False,
        "cancel_at_period_end": False,
    }
    data.update(kwargs)
    return Subscription(**data)


def sign(secret: str, data_id: str, request_id: str, ts: str) -> str:
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    digest = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={digest}"


def test_signature_accepts_valid_header(monkeypatch):
    monkeypatch.setattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "segredo")
    headers = {
        "x-signature": sign("segredo", "123", "req-1", "1700000000"),
        "x-request-id": "req-1",
    }

    assert mercadopago.validate_webhook_signature(headers, "123") is True


def test_signature_rejects_tampered_id(monkeypatch):
    monkeypatch.setattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "segredo")
    headers = {
        "x-signature": sign("segredo", "123", "req-1", "1700000000"),
        "x-request-id": "req-1",
    }

    assert mercadopago.validate_webhook_signature(headers, "999") is False


def test_signature_rejects_missing_header(monkeypatch):
    monkeypatch.setattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "segredo")

    assert mercadopago.validate_webhook_signature({}, "123") is False


def test_signature_omits_absent_request_id(monkeypatch):
    monkeypatch.setattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", "segredo")
    ts = "1700000000"
    manifest = f"id:123;ts:{ts};"
    digest = hmac.new(b"segredo", manifest.encode(), hashlib.sha256).hexdigest()
    headers = {"x-signature": f"ts={ts},v1={digest}"}

    assert mercadopago.validate_webhook_signature(headers, "123") is True


def test_signature_is_skipped_without_secret(monkeypatch):
    monkeypatch.setattr(settings, "MERCADOPAGO_WEBHOOK_SECRET", None)

    assert mercadopago.validate_webhook_signature({}, "123") is True


async def test_preapproval_authorized_activates_subscription(monkeypatch):
    subscription = make_subscription()
    session = FakeSession(subscription)
    next_payment = (datetime.now(UTC) + timedelta(days=30)).isoformat()

    async def fake_get_preapproval(preapproval_id: str) -> dict:
        return {
            "id": preapproval_id,
            "status": "authorized",
            "external_reference": str(subscription.user_id),
            "date_created": datetime.now(UTC).isoformat(),
            "next_payment_date": next_payment,
        }

    monkeypatch.setattr(mercadopago, "get_preapproval", fake_get_preapproval)

    await mercadopago.process_webhook(
        {"type": "subscription_preapproval", "data": {"id": "pre-1"}}, session
    )

    assert subscription.status == "active"
    assert subscription.mercadopago_subscription_id == "pre-1"
    assert subscription.auto_renew is True
    assert subscription.current_period_end == datetime.fromisoformat(next_payment)


async def test_preapproval_cancelled_blocks_access(monkeypatch):
    subscription = make_subscription(status="active", mercadopago_subscription_id="pre-1")
    session = FakeSession(subscription)

    async def fake_get_preapproval(preapproval_id: str) -> dict:
        return {"id": preapproval_id, "status": "cancelled"}

    monkeypatch.setattr(mercadopago, "get_preapproval", fake_get_preapproval)

    await mercadopago.process_webhook(
        {"type": "subscription_preapproval", "data": {"id": "pre-1"}}, session
    )

    assert subscription.status == "cancelled"
    assert subscription.auto_renew is False
    assert subscription.cancelled_at is not None


async def test_authorized_payment_approves_and_records_payment(monkeypatch):
    subscription = make_subscription(status="past_due", mercadopago_subscription_id="pre-1")
    session = FakeSession(subscription, None)

    async def fake_get_authorized_payment(payment_id: str) -> dict:
        return {
            "id": payment_id,
            "preapproval_id": "pre-1",
            "status": "processed",
            "transaction_amount": 19.9,
            "currency_id": "BRL",
            "payment": {"id": 555, "payment_method_id": "pix"},
        }

    monkeypatch.setattr(mercadopago, "get_authorized_payment", fake_get_authorized_payment)

    await mercadopago.process_webhook(
        {"type": "subscription_authorized_payment", "data": {"id": "auth-1"}}, session
    )

    assert subscription.status == "active"
    payment = session.added[0]
    assert isinstance(payment, Payment)
    assert payment.mercadopago_payment_id == "555"
    assert payment.amount_cents == 1990
    assert payment.status == "approved"


async def test_authorized_payment_rejected_marks_past_due(monkeypatch):
    subscription = make_subscription(status="active", mercadopago_subscription_id="pre-1")
    session = FakeSession(subscription, None)

    async def fake_get_authorized_payment(payment_id: str) -> dict:
        return {
            "id": payment_id,
            "preapproval_id": "pre-1",
            "status": "rejected",
            "transaction_amount": 19.9,
            "payment": {"id": 556},
        }

    monkeypatch.setattr(mercadopago, "get_authorized_payment", fake_get_authorized_payment)

    await mercadopago.process_webhook(
        {"type": "subscription_authorized_payment", "data": {"id": "auth-2"}}, session
    )

    assert subscription.status == "past_due"
    assert session.added[0].status == "rejected"


async def test_authorized_payment_is_idempotent(monkeypatch):
    subscription = make_subscription(status="active", mercadopago_subscription_id="pre-1")
    existing_payment = SimpleNamespace(mercadopago_payment_id="557")
    session = FakeSession(subscription, existing_payment)

    async def fake_get_authorized_payment(payment_id: str) -> dict:
        return {
            "id": payment_id,
            "preapproval_id": "pre-1",
            "status": "processed",
            "transaction_amount": 19.9,
            "payment": {"id": 557},
        }

    monkeypatch.setattr(mercadopago, "get_authorized_payment", fake_get_authorized_payment)

    await mercadopago.process_webhook(
        {"type": "subscription_authorized_payment", "data": {"id": "auth-3"}}, session
    )

    assert session.added == []


async def test_unknown_event_is_ignored():
    session = FakeSession()

    await mercadopago.process_webhook({"type": "merchant_order", "data": {"id": "123"}}, session)

    assert session.added == []


async def test_checkout_creates_pending_preapproval_with_static_back_url(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id": "pref-1", "init_point": "https://mp/checkout"}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(mercadopago.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "token")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://site.eftv.test")
    monkeypatch.setattr(settings, "API_BASE_URL", "https://api.eftv.test")

    user = SimpleNamespace(id=uuid4())
    plan = SimpleNamespace(name="Mensal", price_cents=1990, currency="BRL")

    result = await mercadopago.create_checkout_preference(
        user=user, plan=plan, payer_email="cliente@example.com"
    )

    assert result["id"] == "pref-1"
    assert captured["url"].endswith("/preapproval")
    payload = captured["json"]
    assert payload["external_reference"] == str(user.id)
    assert payload["payer_email"] == "cliente@example.com"
    assert payload["status"] == "pending"
    assert payload["back_url"] == "https://site.eftv.test/checkout.html"
    assert (
        payload["notification_url"]
        == "https://api.eftv.test/subscriptions/webhook/mercadopago?source_news=webhooks"
    )
    assert payload["auto_recurring"] == {
        "frequency": 1,
        "frequency_type": "months",
        "transaction_amount": 19.9,
        "currency_id": "BRL",
    }
    # Campos do Checkout Pro nao existem no /preapproval.
    assert "back_urls" not in payload
    assert "payer" not in payload
