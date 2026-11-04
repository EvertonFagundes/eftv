# services/devices.py - Vinculo de aparelhos por assinatura
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.device import SubscriptionDevice
from app.models.subscription import Subscription

DEVICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,64}$")
MAX_DEVICE_NAME = 120


class DeviceLimitError(Exception):
    """A assinatura ja atingiu o numero maximo de aparelhos."""


class InvalidDeviceError(Exception):
    """Identificador de aparelho ausente ou invalido."""


def normalize_device_id(raw: str | None) -> str:
    """Valida o identificador enviado pelo app (UUID ou token opaco)."""
    value = (raw or "").strip()
    if not DEVICE_ID_PATTERN.fullmatch(value):
        raise InvalidDeviceError("Identificador do aparelho ausente ou invalido (X-Device-Id).")
    return value


def normalize_device_name(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    return value[:MAX_DEVICE_NAME]


def device_limit(subscription: Subscription) -> int:
    """Limite de aparelhos do plano, com fallback configuravel."""
    plan = getattr(subscription, "plan", None)
    if plan is not None and plan.max_devices and plan.max_devices > 0:
        return int(plan.max_devices)
    return max(1, settings.MAX_DEVICES_PER_SUBSCRIPTION)


def decide_binding(existing: bool, active_count: int, limit: int) -> str:
    """
    Decide o que fazer com o aparelho.

    - ``allow``: aparelho ja vinculado ou ainda ha vaga;
    - ``denied``: limite atingido.
    """
    if existing:
        return "allow"
    return "allow" if active_count < limit else "denied"


async def active_devices(db: AsyncSession, subscription_id: UUID) -> list[SubscriptionDevice]:
    result = await db.execute(
        select(SubscriptionDevice)
        .where(SubscriptionDevice.subscription_id == subscription_id)
        .where(SubscriptionDevice.revoked_at.is_(None))
        .order_by(SubscriptionDevice.created_at.asc())
    )
    return list(result.scalars().all())


async def bind_device(
    db: AsyncSession,
    subscription: Subscription,
    device_id: str,
    device_name: str | None = None,
) -> SubscriptionDevice:
    """
    Garante que o aparelho pode usar a assinatura.

    O primeiro aparelho e vinculado automaticamente. Se o limite do plano for
    atingido, levanta ``DeviceLimitError`` (o app mostra como desvincular).
    """
    devices = await active_devices(db, subscription.id)
    current = next((d for d in devices if d.device_id == device_id), None)

    if current is None:
        decision = decide_binding(
            existing=False,
            active_count=len(devices),
            limit=device_limit(subscription),
        )
        if decision == "denied":
            raise DeviceLimitError()

        # Um aparelho revogado continua no historico (revoked_at preenchido) e
        # ocupa a chave unica. Nesse caso reativamos a linha em vez de inserir.
        result = await db.execute(
            select(SubscriptionDevice)
            .where(SubscriptionDevice.subscription_id == subscription.id)
            .where(SubscriptionDevice.device_id == device_id)
        )
        current = result.scalar_one_or_none()

        if current is None:
            current = SubscriptionDevice(
                subscription_id=subscription.id,
                device_id=device_id,
                device_name=normalize_device_name(device_name),
            )
            db.add(current)
        else:
            current.revoked_at = None
            current.created_at = datetime.now(UTC)
            if device_name:
                current.device_name = normalize_device_name(device_name)
    elif device_name:
        current.device_name = normalize_device_name(device_name)

    current.last_seen_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(current)
    return current


async def revoke_device(db: AsyncSession, subscription: Subscription, device_id: str) -> bool:
    """Desvincula um aparelho; devolve False se ele nao estava vinculado."""
    result = await db.execute(
        select(SubscriptionDevice)
        .where(SubscriptionDevice.subscription_id == subscription.id)
        .where(SubscriptionDevice.device_id == device_id)
        .where(SubscriptionDevice.revoked_at.is_(None))
    )
    device = result.scalar_one_or_none()
    if device is None:
        return False

    device.revoked_at = datetime.now(UTC)
    await db.commit()
    return True


async def revoke_all_devices(db: AsyncSession, subscription_ids: list[UUID]) -> int:
    """Revoga todos os aparelhos das assinaturas indicadas (suporte/admin)."""
    if not subscription_ids:
        return 0

    result = await db.execute(
        select(SubscriptionDevice)
        .where(SubscriptionDevice.subscription_id.in_(subscription_ids))
        .where(SubscriptionDevice.revoked_at.is_(None))
    )
    devices = list(result.scalars().all())
    now = datetime.now(UTC)
    for device in devices:
        device.revoked_at = now
    await db.commit()
    return len(devices)
