import pytest

from app.services.devices import (
    DEVICE_ID_PATTERN,
    InvalidDeviceError,
    decide_binding,
    device_limit,
    normalize_device_id,
    normalize_device_name,
)


def test_valid_device_ids_are_accepted():
    for value in ("abc12345", "550e8400-e29b-41d4-a716-446655440000", "device:1234_ab"):
        assert DEVICE_ID_PATTERN.fullmatch(normalize_device_id(value))


@pytest.mark.parametrize("value", ["", "   ", "curto", "tem espaco aqui", "x" * 65, "inválido"])
def test_invalid_device_ids_are_rejected(value):
    with pytest.raises(InvalidDeviceError):
        normalize_device_id(value)


def test_device_name_is_trimmed_and_limited():
    assert normalize_device_name("  Galaxy S23  ") == "Galaxy S23"
    assert normalize_device_name("") is None
    assert len(normalize_device_name("x" * 200) or "") == 120


def test_binding_decision():
    assert decide_binding(existing=True, active_count=5, limit=1) == "allow"
    assert decide_binding(existing=False, active_count=0, limit=1) == "allow"
    assert decide_binding(existing=False, active_count=1, limit=1) == "denied"
    assert decide_binding(existing=False, active_count=1, limit=2) == "allow"
    assert decide_binding(existing=False, active_count=2, limit=2) == "denied"


class FakePlan:
    max_devices = 2


class FakeSubscription:
    plan = FakePlan()
    id = "11111111-1111-1111-1111-111111111111"


class FakeSubscriptionWithoutPlan:
    plan = None


def test_device_limit_uses_plan():
    assert device_limit(FakeSubscription()) == 2
    assert device_limit(FakeSubscriptionWithoutPlan()) >= 1


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return [self._value] if self._value is not None else []


class FakeSession:
    """Sessao minima para exercitar o vinculo sem banco real."""

    def __init__(self, revoked_device=None):
        self._revoked = revoked_device
        self.committed = False
        self.added = []

    async def execute(self, _query):
        return FakeResult(self._revoked)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True

    async def refresh(self, _value):
        return None


class FakeDevice:
    def __init__(self, device_id="device-abc-123", revoked_at=None):
        self.device_id = device_id
        self.device_name = "Antigo"
        self.revoked_at = revoked_at
        self.created_at = None
        self.last_seen_at = None


async def test_rebinding_reactivates_revoked_row(monkeypatch):
    from app.services import devices as devices_service

    async def no_active(*args, **kwargs):
        return []

    monkeypatch.setattr(devices_service, "active_devices", no_active)
    revoked = FakeDevice(revoked_at="2026-01-01T00:00:00Z")
    db = FakeSession(revoked_device=revoked)

    device = await devices_service.bind_device(
        db, FakeSubscription(), "device-abc-123", "Novo nome"
    )

    assert device is revoked
    assert revoked.revoked_at is None
    assert revoked.device_name == "Novo nome"
    assert revoked.created_at is not None
    assert revoked.last_seen_at is not None
    assert db.committed
    assert db.added == []


async def test_new_device_is_inserted(monkeypatch):
    from app.services import devices as devices_service

    async def no_active(*args, **kwargs):
        return []

    monkeypatch.setattr(devices_service, "active_devices", no_active)
    db = FakeSession(revoked_device=None)

    device = await devices_service.bind_device(db, FakeSubscription(), "device-new-999", "Aparelho")

    assert device in db.added
    assert db.committed
