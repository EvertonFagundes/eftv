# tests/test_account.py - Exportacao e exclusao de conta (LGPD / Play Store)
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.routes import auth as auth_routes
from app.services import devices, mercadopago, sessions


class FakeResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, *result_sets) -> None:
        self.result_sets = list(result_sets)
        self.commits = 0

    async def execute(self, *args, **kwargs):
        return FakeResult(self.result_sets.pop(0) if self.result_sets else [])

    async def commit(self) -> None:
        self.commits += 1


def make_user():
    return SimpleNamespace(
        id=uuid4(),
        email="cliente@example.com",
        full_name="Cliente",
        phone="11999999999",
        email_verified=True,
        is_active=True,
        is_admin=False,
        password_hash="hash-antigo",
        created_at=datetime.now(UTC),
        email_verification_token="tok",
        password_reset_token="reset",
    )


def make_subscription(**kwargs):
    now = datetime.now(UTC)
    data = {
        "id": uuid4(),
        "status": "active",
        "current_period_start": now,
        "current_period_end": now,
        "trial_end": None,
        "auto_renew": True,
        "cancel_at_period_end": False,
        "cancelled_at": None,
        "mercadopago_subscription_id": "pre-1",
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


def make_payment():
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        amount_cents=1990,
        currency="BRL",
        status="approved",
        payment_method="credit_card",
        paid_at=now,
        created_at=now,
    )


async def test_export_returns_the_account_data():
    user = make_user()
    subscription = make_subscription()
    payment = make_payment()
    db = FakeSession([subscription], [payment])

    data = await auth_routes.export_me(user=user, db=db)

    assert data["user"]["email"] == "cliente@example.com"
    assert data["subscriptions"][0]["status"] == "active"
    assert data["payments"][0]["amount_cents"] == 1990
    # Nada de senha/hash no pacote exportado.
    serialized = str(data)
    assert "hash-antigo" not in serialized
    assert "password" not in serialized.lower()


async def test_delete_anonymizes_and_cancels_everything(monkeypatch):
    user = make_user()
    subscription = make_subscription()
    db = FakeSession([subscription])
    calls = {"cancel": [], "devices": 0, "sessions": 0}

    async def fake_cancel(preapproval_id: str) -> dict:
        calls["cancel"].append(preapproval_id)
        return {"status": "cancelled"}

    async def fake_revoke_devices(db, subscription_ids) -> None:
        calls["devices"] += 1

    async def fake_revoke_all(db, user_id, **kwargs) -> int:
        calls["sessions"] += 1
        return 1

    monkeypatch.setattr(mercadopago, "cancel_preapproval", fake_cancel)
    monkeypatch.setattr(devices, "revoke_all_devices", fake_revoke_devices)
    monkeypatch.setattr(sessions, "revoke_all", fake_revoke_all)

    response = await auth_routes.delete_me(user=user, db=db)

    assert "excluida" in response.message
    assert user.email.startswith("deleted-")
    assert user.full_name is None
    assert user.phone is None
    assert user.is_active is False
    assert user.is_admin is False
    assert user.password_hash != "hash-antigo"
    assert subscription.status == "cancelled"
    assert subscription.auto_renew is False
    assert subscription.cancel_at_period_end is True
    assert calls["cancel"] == ["pre-1"]
    assert calls["devices"] == 1
    assert calls["sessions"] == 1
    assert db.commits == 1


async def test_delete_survives_mercadopago_failure(monkeypatch):
    """A conta sai mesmo com o Mercado Pago fora do ar."""
    user = make_user()
    subscription = make_subscription()
    db = FakeSession([subscription])

    async def boom(preapproval_id: str) -> dict:
        raise RuntimeError("Mercado Pago fora do ar")

    async def noop(*args, **kwargs) -> None:
        return None

    monkeypatch.setattr(mercadopago, "cancel_preapproval", boom)
    monkeypatch.setattr(devices, "revoke_all_devices", noop)
    monkeypatch.setattr(sessions, "revoke_all", noop)

    await auth_routes.delete_me(user=user, db=db)

    assert user.is_active is False
    assert subscription.status == "cancelled"
