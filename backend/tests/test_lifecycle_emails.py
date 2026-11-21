# tests/test_lifecycle_emails.py - Avisos de teste acabando e cartao recusado
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.models.subscription import Subscription
from app.tasks import lifecycle_emails


class FakeResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    """Devolve as linhas na ordem: primeiro trial, depois past_due."""

    def __init__(self, *result_sets) -> None:
        self.result_sets = list(result_sets)
        self.commits = 0

    async def execute(self, *args, **kwargs):
        return FakeResult(self.result_sets.pop(0) if self.result_sets else [])

    async def commit(self) -> None:
        self.commits += 1


class FakeDbContext:
    def __init__(self, session) -> None:
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args) -> bool:
        return False


class FakeEmails:
    def __init__(self, success: bool = True) -> None:
        self.success = success
        self.trial = []
        self.expired = []
        self.failed = []

    async def send_trial_ending_email(self, to_email, trial_end, full_name=None):
        self.trial.append((to_email, trial_end, full_name))
        return self.success

    async def send_trial_expired_email(self, to_email, full_name=None):
        self.expired.append((to_email, full_name))
        return self.success

    async def send_payment_failed_email(self, to_email, full_name=None):
        self.failed.append((to_email, full_name))
        return self.success


def make_trial_subscription() -> Subscription:
    now = datetime.now(UTC)
    return Subscription(
        id=uuid4(),
        user_id=uuid4(),
        plan_id=uuid4(),
        status="trial",
        current_period_start=now,
        current_period_end=now + timedelta(days=1),
        trial_end=now + timedelta(hours=12),
    )


def make_past_due() -> Subscription:
    now = datetime.now(UTC)
    return Subscription(
        id=uuid4(),
        user_id=uuid4(),
        plan_id=uuid4(),
        status="past_due",
        current_period_start=now - timedelta(days=31),
        current_period_end=now - timedelta(days=1),
    )


def make_user() -> SimpleNamespace:
    return SimpleNamespace(email="cliente@example.com", full_name="Cliente")


async def test_trial_ending_email_is_sent_and_marked(monkeypatch):
    subscription = make_trial_subscription()
    session = FakeSession([(subscription, make_user())], [], [])
    emails = FakeEmails()

    monkeypatch.setattr(lifecycle_emails, "get_db_context", FakeDbContext(session))
    monkeypatch.setattr(lifecycle_emails, "email_service", emails)

    sent = await lifecycle_emails.send_lifecycle_emails()

    assert sent["trial_ending"] == 1
    assert emails.trial[0][0] == "cliente@example.com"
    # A data vai no formato brasileiro no corpo do email.
    assert "/" in emails.trial[0][1]
    assert subscription.trial_reminder_sent_at is not None
    assert session.commits == 1


async def test_trial_email_not_marked_when_send_fails(monkeypatch):
    """Falha do provedor nao pode marcar como avisado (o cliente ficaria sem aviso)."""
    subscription = make_trial_subscription()
    session = FakeSession([(subscription, make_user())], [], [])
    emails = FakeEmails(success=False)

    monkeypatch.setattr(lifecycle_emails, "get_db_context", FakeDbContext(session))
    monkeypatch.setattr(lifecycle_emails, "email_service", emails)

    sent = await lifecycle_emails.send_lifecycle_emails()

    assert sent["trial_ending"] == 0
    assert subscription.trial_reminder_sent_at is None


async def test_payment_failed_email_is_sent_and_marked(monkeypatch):
    subscription = make_past_due()
    session = FakeSession([], [], [(subscription, make_user())])
    emails = FakeEmails()

    monkeypatch.setattr(lifecycle_emails, "get_db_context", FakeDbContext(session))
    monkeypatch.setattr(lifecycle_emails, "email_service", emails)

    sent = await lifecycle_emails.send_lifecycle_emails()

    assert sent["payment_failed"] == 1
    assert emails.failed[0][0] == "cliente@example.com"
    assert subscription.payment_failed_notified_at is not None


async def test_nothing_to_notify(monkeypatch):
    session = FakeSession([], [], [])
    emails = FakeEmails()

    monkeypatch.setattr(lifecycle_emails, "get_db_context", FakeDbContext(session))
    monkeypatch.setattr(lifecycle_emails, "email_service", emails)

    sent = await lifecycle_emails.send_lifecycle_emails()

    assert sent == {"trial_ending": 0, "trial_expired": 0, "payment_failed": 0}
    assert emails.trial == []
