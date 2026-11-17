# tests/test_subscription_sync.py - Compra sem webhook (fluxo por plano)
#
# O checkout real cai no fluxo por plano e, nesse caminho, o webhook nao chega.
# Aqui ficam protegidos: a sincronizacao por busca, a gravacao da cobranca e o
# link de checkout gerado quando o Mercado Pago recusa a preapproval direta.
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.config import settings
from app.models.payment import Payment
from app.models.subscription import Subscription
from app.routes.subscriptions import _card_last_four
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
    """Entrega resultados na ordem e guarda o que foi adicionado."""

    def __init__(self, *results) -> None:
        self.results = list(results)
        self.added = []
        self.committed = False

    async def execute(self, *args, **kwargs):
        if self.results:
            return FakeResult(self.results.pop(0))
        return FakeResult(None)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class FakeDbContext:
    """Substitui ``get_db_context`` dentro da sincronizacao."""

    def __init__(self, session) -> None:
        self.session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self.session

    def __exit__(self, *args) -> bool:
        return False

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args) -> bool:
        return False


def make_subscription(**kwargs) -> Subscription:
    now = datetime.now(UTC)
    data = {
        "user_id": uuid4(),
        "plan_id": uuid4(),
        "status": "pending",
        "current_period_start": now,
        "current_period_end": now + timedelta(days=7),
        "auto_renew": True,
        "cancel_at_period_end": False,
    }
    data.update(kwargs)
    return Subscription(**data)


async def test_plan_flow_sync_passes_db_to_preapproval_search(monkeypatch):
    """Regressao: a chamada vinha sem o ``db`` e morria em TypeError.

    O erro era engolido pelo except da sincronizacao, entao o botao
    "Atualizar status" e a conciliacao de 5 min nunca ativavam a compra
    feita pelo link de plano.
    """
    subscription = make_subscription()
    session = FakeSession(subscription)
    monkeypatch.setattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "token")
    monkeypatch.setattr("app.database.get_db_context", FakeDbContext(session))

    seen = {}

    async def fake_find(db, user_id):
        seen["db"] = db
        seen["user_id"] = user_id
        return {"id": "pre-9"}

    async def fake_handle(preapproval_id, db):
        subscription.mercadopago_subscription_id = preapproval_id
        subscription.status = "active"

    async def fake_payments(preapproval_id, db):
        seen["payments"] = (preapproval_id, db)
        return 1

    monkeypatch.setattr(mercadopago, "find_preapproval_for_user", fake_find)
    monkeypatch.setattr(mercadopago, "_handle_preapproval", fake_handle)
    monkeypatch.setattr(mercadopago, "sync_payments_for_subscription", fake_payments)

    assert await mercadopago.sync_preapproval(subscription.id) is True

    assert seen["db"] is session
    assert seen["user_id"] == subscription.user_id
    assert seen["payments"] == ("pre-9", session)
    assert session.committed is True


async def test_sync_payments_records_processed_invoice(monkeypatch):
    """Sem webhook, a fatura aprovada vira Payment e libera o acesso."""
    subscription = make_subscription(
        status="active", mercadopago_subscription_id="pre-1"
    )
    session = FakeSession(subscription, None)
    next_charge = (datetime.now(UTC) + timedelta(days=31)).isoformat()

    async def fake_search(preapproval_id: str) -> list[dict]:
        assert preapproval_id == "pre-1"
        return [
            # Fatura futura: nao pode rebaixar a assinatura.
            {"id": 900, "preapproval_id": "pre-1", "status": "scheduled"},
            {
                "id": 901,
                "preapproval_id": "pre-1",
                "status": "processed",
                "transaction_amount": 19.9,
                "currency_id": "BRL",
                "payment": {"id": 555, "payment_method_id": "visa"},
                "next_payment_date": next_charge,
            },
        ]

    monkeypatch.setattr(mercadopago, "search_authorized_payments", fake_search)

    recorded = await mercadopago.sync_payments_for_subscription("pre-1", session)

    assert recorded == 1
    assert len(session.added) == 1
    payment = session.added[0]
    assert isinstance(payment, Payment)
    assert payment.status == "approved"
    assert payment.payment_method == "visa"
    assert payment.amount_cents == 1990
    assert payment.mercadopago_payment_id == "555"
    assert subscription.status == "active"


async def test_sync_payments_skips_invoice_already_recorded(monkeypatch):
    """Webhook e conciliacao rodando juntos nao podem duplicar a cobranca."""
    subscription = make_subscription(
        status="active", mercadopago_subscription_id="pre-1"
    )
    already_there = SimpleNamespace(mercadopago_payment_id="901")
    session = FakeSession(subscription, already_there)

    async def fake_search(preapproval_id: str) -> list[dict]:
        return [
            {
                "id": 901,
                "preapproval_id": "pre-1",
                "status": "processed",
                "transaction_amount": 19.9,
                "payment": {"id": 555},
            }
        ]

    monkeypatch.setattr(mercadopago, "search_authorized_payments", fake_search)

    recorded = await mercadopago.sync_payments_for_subscription("pre-1", session)

    assert recorded == 0
    assert session.added == []


async def test_sync_payments_survives_search_failure(monkeypatch):
    """Falha de rede no Mercado Pago nao pode derrubar a sincronizacao."""
    subscription = make_subscription(
        status="active", mercadopago_subscription_id="pre-1"
    )
    session = FakeSession(subscription)

    async def boom(preapproval_id: str) -> list[dict]:
        raise RuntimeError("Mercado Pago fora do ar")

    monkeypatch.setattr(mercadopago, "search_authorized_payments", boom)

    assert await mercadopago.sync_payments_for_subscription("pre-1", session) == 0
    assert session.added == []


def test_card_last_four_reads_nested_card_object():
    """O MP entrega os digitos dentro de ``payment.card``."""
    payment = Payment(
        user_id=uuid4(),
        amount_cents=1990,
        status="approved",
        extra_metadata={"payment": {"card": {"last_four_digits": "4242"}}},
    )

    assert _card_last_four(payment) == "4242"


def test_card_last_four_is_none_without_data():
    payment = Payment(user_id=uuid4(), amount_cents=1990, status="approved")

    assert _card_last_four(payment) is None


async def test_checkout_falls_back_to_plan_link_when_preapproval_refused(monkeypatch):
    """Caminho de producao: preapproval recusada -> link por plano."""
    captured = {}
    monkeypatch.setattr(settings, "MERCADOPAGO_ACCESS_TOKEN", "token")
    monkeypatch.setattr(settings, "FRONTEND_URL", "https://site.eftv.test")
    monkeypatch.setattr(settings, "API_BASE_URL", "https://api.eftv.test")

    class FakeResponse:
        def __init__(self, status_code: int, payload: dict) -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = repr(payload)

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url, json=None, headers=None):
            if url.endswith("/preapproval_plan"):
                captured["plan_payload"] = json
                return FakeResponse(200, {"id": "plan-1"})
            return FakeResponse(400, {"error": "recusado"})

    monkeypatch.setattr(mercadopago.httpx, "AsyncClient", FakeClient)

    user = SimpleNamespace(id=uuid4())
    plan = SimpleNamespace(
        mercadopago_plan_id=None,
        name="Mensal",
        price_cents=1990,
        currency="BRL",
    )
    session = FakeSession()

    result = await mercadopago.create_checkout_preference(
        user=user,
        plan=plan,
        payer_email="cliente@example.com",
        db=session,
    )

    assert result["mode"] == "plan"
    assert result["id"] == "plan-1"
    assert "preapproval_plan_id=plan-1" in result["init_point"]
    assert str(user.id) in result["init_point"]
    # Somente cartao de credito e permitido no checkout do plano.
    assert captured["plan_payload"]["payment_methods_allowed"] == {
        "payment_types": [{"id": "credit_card"}]
    }
    assert plan.mercadopago_plan_id == "plan-1"
