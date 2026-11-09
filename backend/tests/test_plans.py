from types import SimpleNamespace

import pytest

from app.services.plans import get_or_create_plan


class FakeResult:
    def __init__(self, plan):
        self.plan = plan

    def scalars(self):
        return self

    def first(self):
        return self.plan


class FakeSession:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.added = []

    async def execute(self, *args, **kwargs):
        return FakeResult(self.existing)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_returns_existing_plan_without_overwriting():
    existing = SimpleNamespace(name="Plano do cliente", price_cents=999)
    session = FakeSession(existing)

    plan = await get_or_create_plan(session)

    assert plan is existing
    assert session.added == []


@pytest.mark.asyncio
async def test_creates_monthly_plan_when_database_is_empty():
    session = FakeSession()

    plan = await get_or_create_plan(session)

    assert session.added == [plan]
    assert plan.name == "Mensal"
    assert plan.price_cents == 1990
    assert plan.currency == "BRL"
    assert plan.interval == "month"
    assert plan.max_devices == 1
    assert plan.max_simultaneous_streams == 1
    assert plan.features == {"hd": True, "full_hd": True, "4k": False}
