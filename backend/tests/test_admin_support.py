# tests/test_admin_support.py - Suporte de pagamentos no painel admin
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.payment import Payment
from app.models.subscription import Subscription
from app.routes import admin


class FakeResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value

    def first(self):
        return self.value


class FakeSession:
    """Entrega resultados na ordem, como as consultas chegam no rota."""

    def __init__(self, *results) -> None:
        self.results = list(results)
        self.refreshed = []

    async def execute(self, *args, **kwargs):
        if self.results:
            return FakeResult(self.results.pop(0))
        return FakeResult(None)

    async def refresh(self, obj) -> None:
        self.refreshed.append(obj)

    async def commit(self) -> None:
        return None


def make_payment(**kwargs) -> Payment:
    data = {
        "user_id": uuid4(),
        "amount_cents": 1990,
        "currency": "BRL",
        "status": "approved",
        "payment_method": "visa",
        "mercadopago_payment_id": "777",
        "paid_at": datetime.now(UTC),
        "extra_metadata": {"payment": {"card": {"last_four_digits": "4242"}}},
    }
    data.update(kwargs)
    return Payment(**data)


async def test_list_payments_returns_email_and_filters_by_status():
    payment = make_payment()
    session = FakeSession(1, [(payment, "cliente@example.com")])

    payload = await admin.list_payments(
        page=1,
        page_size=20,
        payment_status="approved",
        email="cliente",
        db=session,
        _=None,
    )

    assert payload["total"] == 1
    entry = payload["payments"][0]
    assert entry["email"] == "cliente@example.com"
    assert entry["amount_cents"] == 1990
    assert entry["payment_method"] == "visa"
    assert entry["mercadopago_payment_id"] == "777"


async def test_list_payments_without_filters():
    session = FakeSession(0, [])

    payload = await admin.list_payments(
        page=1,
        page_size=20,
        payment_status=None,
        email=None,
        db=session,
        _=None,
    )

    assert payload["payments"] == []
    assert payload["total"] == 0


async def test_user_detail_includes_payments():
    user = SimpleNamespace(
        id=uuid4(),
        email="cliente@example.com",
        full_name="Cliente",
        phone=None,
        is_active=True,
        is_admin=False,
        email_verified=True,
        created_at=datetime.now(UTC),
    )
    subscription = Subscription(
        user_id=user.id,
        plan_id=uuid4(),
        status="active",
        current_period_start=datetime.now(UTC),
        current_period_end=datetime.now(UTC) + timedelta(days=30),
    )
    payment = make_payment(user_id=user.id)
    # user -> assinaturas -> aparelhos -> pagamentos
    session = FakeSession(user, [subscription], [], [payment])

    payload = await admin.get_user(user.id, db=session, _=None)

    assert payload["user"]["email"] == "cliente@example.com"
    assert payload["subscriptions"][0]["status"] == "active"
    assert payload["payments"][0]["mercadopago_payment_id"] == "777"


async def test_sync_subscription_forces_reconciliation(monkeypatch):
    """Suporte: "paguei e nao liberou" resolve por aqui, sem esperar o cron."""
    subscription = Subscription(
        id=uuid4(),
        user_id=uuid4(),
        plan_id=uuid4(),
        status="pending",
        current_period_start=datetime.now(UTC),
        current_period_end=datetime.now(UTC),
    )
    session = FakeSession(subscription)
    seen = {}

    async def fake_sync(subscription_id):
        seen["id"] = subscription_id
        subscription.status = "active"
        subscription.mercadopago_subscription_id = "pre-1"
        return True

    monkeypatch.setattr(admin, "sync_preapproval", fake_sync)

    payload = await admin.sync_subscription(subscription.id, db=session, _=None)

    assert seen["id"] == subscription.id
    assert payload["synced"] is True
    assert payload["status"] == "active"
    assert payload["mercadopago_subscription_id"] == "pre-1"
    assert session.refreshed == [subscription]


async def test_sync_subscription_unknown_id_is_404():
    session = FakeSession(None)

    with pytest.raises(HTTPException) as exc:
        await admin.sync_subscription(uuid4(), db=session, _=None)

    assert exc.value.status_code == 404
