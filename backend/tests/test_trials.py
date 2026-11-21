# tests/test_trials.py - Teste gratis amarrado ao aparelho
from datetime import UTC, datetime
from types import SimpleNamespace

from app.models.trial_device import TrialDevice
from app.services import trials


class FakeResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, entry=None) -> None:
        self.entry = entry
        self.added = []
        self.commits = 0

    async def execute(self, *args, **kwargs):
        return FakeResult(self.entry)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


def make_entry(user_id, subscription_id=None) -> TrialDevice:
    return TrialDevice(
        device_id="aparelho-1",
        user_id=user_id,
        subscription_id=subscription_id,
    )


async def test_device_never_used_is_allowed():
    """Aparelho novo: pode ganhar o teste."""
    db = FakeSession(entry=None)

    assert await trials.device_already_used(db, "aparelho-1", "user-1") is False


async def test_same_device_in_another_account_is_blocked():
    """O furo: criar outra conta no mesmo celular dava outro teste."""
    db = FakeSession(entry=make_entry("user-antigo"))

    assert await trials.device_already_used(db, "aparelho-1", "user-novo") is True


async def test_same_device_same_account_is_not_blocked():
    """Reentrar depois de cancelar nao pode ser tratado como abuso."""
    db = FakeSession(entry=make_entry("user-1"))

    assert await trials.device_already_used(db, "aparelho-1", "user-1") is False


async def test_claim_creates_the_binding_once():
    db = FakeSession(entry=None)
    subscription_id = "sub-1"

    entry = await trials.claim(
        db,
        device_id="aparelho-1",
        user_id="user-1",
        subscription_id=subscription_id,
    )

    assert entry.device_id == "aparelho-1"
    assert entry.user_id == "user-1"
    assert entry.subscription_id == subscription_id
    assert db.added == [entry]
    assert db.commits == 1


async def test_claim_is_idempotent_and_links_the_subscription():
    """Chamado de novo (verify-email e player) nao duplica o vinculo."""
    existing = make_entry("user-1")
    db = FakeSession(entry=existing)

    entry = await trials.claim(
        db,
        device_id="aparelho-1",
        user_id="user-1",
        subscription_id="sub-1",
    )

    assert entry is existing
    assert entry.subscription_id == "sub-1"
    assert db.added == []


async def test_revoke_trial_cuts_access():
    now = datetime.now(UTC)
    subscription = SimpleNamespace(
        status="trial",
        cancelled_at=None,
        cancel_at_period_end=False,
        auto_renew=True,
    )

    trials.revoke_trial(subscription, now=now)

    assert subscription.status == "cancelled"
    assert subscription.cancelled_at == now
    assert subscription.cancel_at_period_end is True
    assert subscription.auto_renew is False
