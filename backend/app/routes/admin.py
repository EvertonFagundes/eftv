# routes/admin.py - Rotas administrativas
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.category import Category
from app.models.channel import Channel
from app.models.device import SubscriptionDevice
from app.models.subscription import Subscription
from app.models.user import User
from app.security.dependencies import require_admin
from app.services.devices import revoke_all_devices

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    """Estatísticas gerais para dashboard admin."""
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    active_users = (
        await db.execute(select(func.count(User.id)).where(User.is_active))
    ).scalar_one()
    total_subscriptions = (await db.execute(select(func.count(Subscription.id)))).scalar_one()
    active_subscriptions = (
        await db.execute(select(func.count(Subscription.id)).where(Subscription.status == "active"))
    ).scalar_one()
    total_channels = (await db.execute(select(func.count(Channel.id)))).scalar_one()
    active_channels = (
        await db.execute(select(func.count(Channel.id)).where(Channel.is_active))
    ).scalar_one()
    total_categories = (await db.execute(select(func.count(Category.id)))).scalar_one()

    return {
        "users": {"total": total_users, "active": active_users},
        "subscriptions": {"total": total_subscriptions, "active": active_subscriptions},
        "channels": {"total": total_channels, "active": active_channels},
        "categories": total_categories,
    }


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Lista usuários (admin)."""
    query = select(User).order_by(User.created_at.desc())
    if search:
        search_term = f"%{search.lower()}%"
        query = query.where((User.email.ilike(search_term)) | (User.full_name.ilike(search_term)))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    users = result.scalars().all()

    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "is_active": u.is_active,
                "is_admin": u.is_admin,
                "email_verified": u.email_verified,
                "created_at": u.created_at,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    """Obtém detalhes de usuário + assinaturas (admin)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subscriptions = sub_result.scalars().all()

    devices_result = await db.execute(
        select(SubscriptionDevice)
        .where(SubscriptionDevice.subscription_id.in_([s.id for s in subscriptions]))
        .where(SubscriptionDevice.revoked_at.is_(None))
        .order_by(SubscriptionDevice.last_seen_at.desc())
    )
    devices = devices_result.scalars().all() if subscriptions else []

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "is_active": user.is_active,
            "is_admin": user.is_admin,
            "email_verified": user.email_verified,
            "created_at": user.created_at,
        },
        "subscriptions": [
            {
                "id": s.id,
                "plan_id": s.plan_id,
                "status": s.status,
                "current_period_end": s.current_period_end,
                "cancel_at_period_end": s.cancel_at_period_end,
            }
            for s in subscriptions
        ],
        "devices": [
            {
                "device_id": d.device_id,
                "device_name": d.device_name,
                "bound_at": d.created_at,
                "last_seen_at": d.last_seen_at,
            }
            for d in devices
        ],
    }


@router.post("/users/{user_id}/devices/revoke")
async def revoke_user_devices(
    user_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    """Desvincula todos os aparelhos do usuario (suporte ao cliente)."""
    result = await db.execute(select(User).where(User.id == user_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    ids_result = await db.execute(select(Subscription.id).where(Subscription.user_id == user_id))
    subscription_ids = list(ids_result.scalars().all())
    revoked = await revoke_all_devices(db, subscription_ids)
    return {"revoked": revoked}


@router.patch("/users/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    """Alterna status admin do usuário."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    user.is_admin = not user.is_admin
    await db.commit()
    return {"id": user.id, "is_admin": user.is_admin}


@router.patch("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    """Ativa/desativa usuário."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    user.is_active = not user.is_active
    await db.commit()
    return {"id": user.id, "is_active": user.is_active}
