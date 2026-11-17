# tests/test_cancellation.py - Cancelamento corta a cobranca, nao o acesso pago
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.models.subscription import Subscription
from app.routes import subscriptions as subscriptions_routes
from app.services import mercadopago
from app.tasks import subscription_checker as checker


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


class FakeSession:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.committed = False

    async def execute(self, *args, **kwargs):
        if self.results:
            return FakeResult(self.results.pop(0))
        return FakeResult(None)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, obj) -> None:
        return None

    def add(self, obj) -> None:
        return None


class FakeDbContext:
    def __init__(self, session) -> None:
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args) -> bool:
        return False


def make_subscription(**kwargs) -> Subscription:
    now = datetime.now(UTC)
    data = {
        "id": uuid4(),
        "user_id": uuid4(),
        "plan_id": uuid4(),
        "status": "active",
        "current_period_start": now - timedelta(days=10),
        "current_period_end": now + timedelta(days=20),
        "auto_renew": True,
        "cancel_at_period_end": False,
    }
    data.update(kwargs)
    return Subscription(**data)


async def test_cancelled_preapproval_keeps_access_until_period_end(monkeypatch):
    """Cancelou no meio do ciclo: paga o mes todo, assiste o mes todo."""
    subscription = make_subscription(mercadopago_subscription_id="pre-1")
    session = FakeSession(subscription)

    async def fake_get(preapproval_id: str) -> dict:
        return {"id": preapproval_id, "status": "cancelled"}

    monkeypatch.setattr(mercadopago, "get_preapproval", fake_get)

    await mercadopago._handle_preapproval("pre-1", session)

    assert subscription.auto_renew is False
    assert subscription.cancel_at_period_end is True
    assert subscription.status == "active"
    assert subscription.has_access is True


async def test_cancelled_preapproval_without_paid_period_blocks(monkeypatch):
    """Periodo ja vencido + cancelada: sem acesso, sem cobranca."""
    subscription = make_subscription(
        mercadopago_subscription_id="pre-1",
        current_period_end=datetime.now(UTC) - timedelta(hours=1),
    )
    session = FakeSession(subscription)

    async def fake_get(preapproval_id: str) -> dict:
        return {"id": preapproval_id, "status": "cancelled"}

    monkeypatch.setattr(mercadopago, "get_preapproval", fake_get)

    await mercadopago._handle_preapproval("pre-1", session)

    assert subscription.status == "cancelled"
    assert subscription.cancelled_at is not None
    assert subscription.has_access is False


async def test_cancel_route_also_cancels_at_mercadopago(monkeypatch):
    """Sem esta chamada, o cartao continuaria sendo cobrado todo mes."""
    subscription = make_subscription(mercadopago_subscription_id="pre-1")
    plan = SimpleNamespace(id=subscription.plan_id, name="Mensal", price_cents=1990)
    session = FakeSession(subscription, plan)
    called = {}

    async def fake_cancel(preapproval_id: str) -> dict:
        called["preapproval_id"] = preapproval_id
        return {"status": "cancelled"}

    monkeypatch.setattr(subscriptions_routes, "cancel_preapproval", fake_cancel)

    response = await subscriptions_routes.cancel_subscription(
        subscription.id,
        user=SimpleNamespace(id=subscription.user_id),
        db=session,
    )

    assert called["preapproval_id"] == "pre-1"
    assert response.cancel_at_period_end is True
    assert response.auto_renew is False
    assert session.committed is True


async def test_cancel_route_survives_mercadopago_failure(monkeypatch):
    """Cancelar no app precisa funcionar mesmo com o MP fora."""
    subscription = make_subscription(mercadopago_subscription_id="pre-1")
    plan = SimpleNamespace(id=subscription.plan_id, name="Mensal", price_cents=1990)
    session = FakeSession(subscription, plan)

    async def boom(preapproval_id: str) -> dict:
        raise RuntimeError("Mercado Pago fora do ar")

    monkeypatch.setattr(subscriptions_routes, "cancel_preapproval", boom)

    response = await subscriptions_routes.cancel_subscription(
        subscription.id,
        user=SimpleNamespace(id=subscription.user_id),
        db=session,
    )

    assert response.cancel_at_period_end is True
    assert subscription.auto_renew is False


async def test_expired_cancelled_subscription_is_not_renovada(monkeypatch):
    """Regressao: o verificador via "authorized" no MP e reativava a conta."""
    subscription = make_subscription(
        mercadopago_subscription_id="pre-1",
        cancel_at_period_end=True,
        auto_renew=False,
        current_period_end=datetime.now(UTC) - timedelta(hours=1),
    )
    session = FakeSession([subscription])
    monkeypatch.setattr("app.tasks.subscription_checker.get_db_context", FakeDbContext(session))

    cancel_calls = {}
    renew_calls = {"count": 0}

    async def fake_cancel(preapproval_id: str) -> dict:
        cancel_calls["preapproval_id"] = preapproval_id
        return {"status": "cancelled"}

    async def fake_get(preapproval_id: str) -> dict:
        renew_calls["count"] += 1
        return {"id": preapproval_id, "status": "authorized"}

    monkeypatch.setattr(checker, "cancel_preapproval", fake_cancel)
    monkeypatch.setattr(checker, "get_preapproval", fake_get)

    updated = await checker.check_expired_subscriptions()

    assert updated == 1
    assert subscription.status == "cancelled"
    assert subscription.auto_renew is False
    assert cancel_calls["preapproval_id"] == "pre-1"
    # Nao consultou a renovacao: quem cancelou nao volta.
    assert renew_calls["count"] == 0


async def test_expired_active_subscription_still_renews(monkeypatch):
    """O caminho normal de renovacao continua funcionando."""
    subscription = make_subscription(
        mercadopago_subscription_id="pre-1",
        current_period_end=datetime.now(UTC) - timedelta(hours=1),
    )
    session = FakeSession([subscription])
    monkeypatch.setattr("app.tasks.subscription_checker.get_db_context", FakeDbContext(session))
    next_billing = datetime.now(UTC) + timedelta(days=30)

    async def fake_get(preapproval_id: str) -> dict:
        return {"id": preapproval_id, "status": "authorized", "next_billing_date": next_billing.isoformat()}

    async def fake_payments(preapproval_id: str, db) -> int:
        return 1

    monkeypatch.setattr(checker, "get_preapproval", fake_get)
    monkeypatch.setattr(checker, "sync_payments_for_subscription", fake_payments)

    updated = await checker.check_expired_subscriptions()

    assert updated == 1
    assert subscription.status == "active"
    assert subscription.current_period_end == next_billing
