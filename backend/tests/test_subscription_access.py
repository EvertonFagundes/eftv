from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.subscription import Subscription
from app.security.dependencies import get_current_active_subscription


def make_subscription(
    status: str = "trial",
    days: int = 7,
    trial_days: int | None = 7,
    cancelled_at: datetime | None = None,
) -> Subscription:
    now = datetime.now(UTC)
    return Subscription(
        status=status,
        current_period_start=now,
        current_period_end=now + timedelta(days=days),
        trial_end=None if trial_days is None else now + timedelta(days=trial_days),
        cancelled_at=cancelled_at,
        cancel_at_period_end=False,
        auto_renew=False,
    )


class FakeResult:
    def __init__(self, subscription: Subscription | None) -> None:
        self.subscription = subscription

    def scalar_one_or_none(self) -> Subscription | None:
        return self.subscription


class FakeSession:
    def __init__(self, subscription: Subscription | None) -> None:
        self.subscription = subscription

    async def execute(self, *args, **kwargs) -> FakeResult:
        return FakeResult(self.subscription)


def test_trial_gives_access_even_though_it_is_not_active_period():
    subscription = make_subscription(status="trial")

    assert subscription.is_trial is True
    assert subscription.is_active is False
    assert subscription.has_access is True


def test_expired_trial_loses_access():
    subscription = make_subscription(status="trial", days=-1, trial_days=-1)

    assert subscription.has_access is False


def test_trial_without_trial_end_uses_period_end():
    subscription = make_subscription(status="trial", trial_days=None)

    assert subscription.has_access is True


def test_paid_subscription_gives_access():
    subscription = make_subscription(status="active", trial_days=None)

    assert subscription.has_access is True


def test_expired_paid_subscription_loses_access():
    subscription = make_subscription(status="active", days=-1, trial_days=None)

    assert subscription.has_access is False


def test_cancelled_paid_subscription_loses_access():
    subscription = make_subscription(
        status="active",
        trial_days=None,
        cancelled_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    assert subscription.has_access is False


def test_cancelled_status_loses_access():
    subscription = make_subscription(status="cancelled", days=10, trial_days=None)

    assert subscription.has_access is False


@pytest.mark.asyncio
async def test_dependency_accepts_trial_account():
    subscription = make_subscription(status="trial")
    user = SimpleNamespace(id="user-id", email_verified=True)

    result = await get_current_active_subscription(user=user, db=FakeSession(subscription))

    assert result is subscription


@pytest.mark.asyncio
async def test_dependency_rejects_expired_trial():
    subscription = make_subscription(status="trial", days=-1, trial_days=-1)
    user = SimpleNamespace(id="user-id", email_verified=True)

    with pytest.raises(HTTPException) as excinfo:
        await get_current_active_subscription(user=user, db=FakeSession(subscription))

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail["code"] == "subscription_expired"
