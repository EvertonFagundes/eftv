# routes/admin.py - Rotas administrativas
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.category import Category
from app.models.channel import Channel
from app.models.client_error import ClientError
from app.models.device import SubscriptionDevice
from app.models.payment import Payment
from app.models.stream_session import StreamSession
from app.models.subscription import Subscription
from app.models.user import User
from app.security.dependencies import get_current_user, require_admin
from app.services.devices import revoke_all_devices
from app.services.mercadopago import sync_preapproval
from app.services.plans import get_or_create_plan
from app.services.playlist_expiry import check_playlist_expiry

router = APIRouter(prefix="/admin", tags=["Admin"])

logger = logging.getLogger(__name__)


async def _active_admin_count(db: AsyncSession) -> int:
    """Quantos administradores ativos existem (para nao deixar o painel sem dono)."""
    result = await db.execute(
        select(func.count(User.id)).where(User.is_admin.is_(True), User.is_active.is_(True))
    )
    return int(result.scalar_one() or 0)


@router.post("/claim-ownership")
async def claim_ownership(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Permite que a conta ativa mais antiga assuma o painel quando nao existe
    nenhum administrador (instalacao nova ou recuperacao).

    A checagem nao e so "esta logado": um cadastro recente nao pode tomar o
    painel caso o ultimo admin seja removido.
    """
    try:
        if await _active_admin_count(db) > 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ja existe um administrador cadastrado.",
            )

        if not current_user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Confirme seu email antes de assumir a administracao.",
            )

        oldest_result = await db.execute(
            select(User.id)
            .where(User.is_active.is_(True))
            .order_by(User.created_at.asc(), User.id.asc())
            .limit(1)
        )
        oldest_id = oldest_result.scalar_one_or_none()
        if oldest_id is None or str(oldest_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas a conta ativa mais antiga pode assumir a administracao.",
            )

        current_user.is_admin = True

        # Garante o plano comercial (trial e assinatura usam o mesmo)
        plan = await get_or_create_plan(db)

        # Ativa ou cria subscription
        sub_result = await db.execute(
            select(Subscription).where(Subscription.user_id == current_user.id)
        )
        subscription = sub_result.scalar_one_or_none()
        now = datetime.now(UTC)
        period_end = now + timedelta(days=365)
        if subscription is None:
            subscription = Subscription(
                user_id=current_user.id,
                plan_id=plan.id,
                status="active",
                current_period_start=now,
                current_period_end=period_end,
                auto_renew=True,
            )
            db.add(subscription)
        else:
            subscription.plan_id = plan.id
            subscription.status = "active"
            subscription.current_period_start = now
            subscription.current_period_end = period_end
            subscription.auto_renew = True
            subscription.cancelled_at = None

        await db.commit()
        await db.refresh(current_user)
        return {
            "id": current_user.id,
            "email": current_user.email,
            "is_admin": current_user.is_admin,
            "is_active": current_user.is_active,
            "message": "VocÃª Ã© agora o dono do app. Tudo liberado.",
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Erro ao processar solicitacao administrativa")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar a solicitacao.",
        ) from None


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    """EstatÃ­sticas gerais para dashboard admin."""
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


@router.get("/playlist/expiry")
async def get_playlist_expiry(
    refresh: bool = Query(False, description="Ignora o cache e consulta o provedor agora"),
    user: User = Depends(require_admin),
):
    """Vencimento da playlist licenciada no provedor.

    Restrito de proposito: a data e a quantidade de conexoes fazem parte do
    contrato do EFTV com o provedor, nao do painel do assinante. Para as
    demais contas admin a rota responde 403. A URL da playlist (com usuario e
    senha) nunca aparece na resposta.
    """
    email = (user.email or "").strip().lower()
    if email not in settings.playlist_expiry_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vencimento da playlist restrito ao responsavel pela conta",
        )
    if not settings.IPTV_PLAYLIST_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Playlist ainda nao configurada no servidor",
        )

    result = await check_playlist_expiry(
        settings.IPTV_PLAYLIST_URL,
        user_agent=settings.IPTV_PLAYLIST_USER_AGENT,
        referer=settings.IPTV_PLAYLIST_REFERER,
        force=refresh,
    )
    payload = result.to_dict()
    payload["cache_seconds"] = settings.PLAYLIST_EXPIRY_CACHE_SECONDS
    return payload


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Lista usuÃ¡rios (admin)."""
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
    """ObtÃ©m detalhes de usuÃ¡rio + assinaturas (admin)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="UsuÃ¡rio nÃ£o encontrado")

    sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subscriptions = sub_result.scalars().all()

    devices_result = await db.execute(
        select(SubscriptionDevice)
        .where(SubscriptionDevice.subscription_id.in_([s.id for s in subscriptions]))
        .where(SubscriptionDevice.revoked_at.is_(None))
        .order_by(SubscriptionDevice.last_seen_at.desc())
    )
    devices = devices_result.scalars().all() if subscriptions else []

    payments_result = await db.execute(
        select(Payment)
        .where(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc())
        .limit(20)
    )
    payments = payments_result.scalars().all()

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
        "payments": [
            {
                "id": p.id,
                "amount_cents": p.amount_cents,
                "currency": p.currency,
                "status": p.status,
                "payment_method": p.payment_method,
                "mercadopago_payment_id": p.mercadopago_payment_id,
                "paid_at": p.paid_at,
                "created_at": p.created_at,
            }
            for p in payments
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


@router.get("/payments")
async def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    payment_status: str | None = Query(None, alias="status"),
    email: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Cobrancas registradas (suporte: "o cliente pagou?")."""
    query = (
        select(Payment, User.email)
        .join(User, User.id == Payment.user_id, isouter=True)
        .order_by(Payment.created_at.desc())
    )
    if payment_status:
        query = query.where(Payment.status == payment_status)
    if email:
        query = query.where(User.email.ilike(f"%{email.lower()}%"))

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    rows = (
        await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    ).all()

    return {
        "payments": [
            {
                "id": payment.id,
                "user_id": payment.user_id,
                "email": payer_email,
                "subscription_id": payment.subscription_id,
                "amount_cents": payment.amount_cents,
                "currency": payment.currency,
                "status": payment.status,
                "payment_method": payment.payment_method,
                "mercadopago_payment_id": payment.mercadopago_payment_id,
                "paid_at": payment.paid_at,
                "created_at": payment.created_at,
            }
            for payment, payer_email in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/crashes")
async def list_client_errors(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Erros e travamentos relatados pelo app ("o app fechou sozinho")."""
    total = (await db.execute(select(func.count()).select_from(ClientError))).scalar_one()
    rows = (
        await db.execute(
            select(ClientError)
            .order_by(ClientError.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return {
        "errors": [
            {
                "id": error.id,
                "app_version": error.app_version,
                "device": error.device,
                "android": error.android,
                "message": error.message,
                "stacktrace": error.stacktrace,
                "created_at": error.created_at,
            }
            for error in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/streams")
async def list_stream_sessions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Quem esta assistindo agora (limite de telas).

    Suporte usa para responder "esta dizendo que o plano e de 1 tela" sem
    adivinhar: mostra a conta, o aparelho e o canal de cada sessao ativa.
    """
    now = datetime.now(UTC)
    rows = (
        await db.execute(
            select(StreamSession, User)
            .join(User, User.id == StreamSession.user_id)
            .where(StreamSession.ended_at.is_(None))
            .order_by(StreamSession.last_heartbeat.desc())
            .limit(200)
        )
    ).all()

    active = []
    for session, user in rows:
        last_heartbeat = session.last_heartbeat
        if last_heartbeat.tzinfo is None:
            last_heartbeat = last_heartbeat.replace(tzinfo=UTC)
        alive = (now - last_heartbeat).total_seconds() <= settings.STREAM_SESSION_TIMEOUT_SECONDS
        active.append(
            {
                "session_id": session.id,
                "user_id": user.id,
                "email": user.email,
                "device_id": session.device_id,
                "channel": session.channel_name,
                "channel_ref": session.channel_ref,
                "started_at": session.started_at,
                "last_heartbeat": session.last_heartbeat,
                # True = contando para o limite de telas agora.
                "active": alive,
            }
        )

    return {
        "sessions": active,
        "active_count": sum(1 for item in active if item["active"]),
        "limit_seconds": settings.STREAM_SESSION_TIMEOUT_SECONDS,
    }


@router.post("/subscriptions/{subscription_id}/sync")
async def sync_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Concilia uma assinatura com o Mercado Pago na hora (suporte).

    Caminho de emergencia quando o cliente pagou e o acesso nao liberou:
    busca a assinatura na fonte, grava a cobranca e atualiza o periodo.
    """
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada"
        )

    synced = await sync_preapproval(subscription_id)

    await db.refresh(subscription)
    return {
        "synced": synced,
        "id": subscription.id,
        "status": subscription.status,
        "current_period_end": subscription.current_period_end,
        "mercadopago_subscription_id": subscription.mercadopago_subscription_id,
        "has_access": subscription.has_access,
    }


@router.post("/users/{user_id}/devices/revoke")
async def revoke_user_devices(
    user_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    """Desvincula todos os aparelhos do usuario (suporte ao cliente)."""
    result = await db.execute(select(User).where(User.id == user_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="UsuÃ¡rio nÃ£o encontrado")

    ids_result = await db.execute(select(Subscription.id).where(Subscription.user_id == user_id))
    subscription_ids = list(ids_result.scalars().all())
    revoked = await revoke_all_devices(db, subscription_ids)
    return {"revoked": revoked}


@router.patch("/users/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    """Alterna status admin do usuÃ¡rio."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    if user.is_admin and user.is_active and await _active_admin_count(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nao e possivel remover o ultimo administrador ativo.",
        )

    user.is_admin = not user.is_admin
    await db.commit()
    return {"id": user.id, "is_admin": user.is_admin}


@router.patch("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    """Ativa/desativa usuÃ¡rio."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    if user.is_admin and user.is_active and await _active_admin_count(db) <= 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nao e possivel desativar o ultimo administrador ativo.",
        )

    user.is_active = not user.is_active
    await db.commit()
    return {"id": user.id, "is_active": user.is_active}


@router.post("/users/{user_id}/make-owner")
async def make_user_owner(
    user_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    """
    Promove um usuÃ¡rio a dono do app (admin) e ativa sua subscription.
    Ãštil para configurar o proprietÃ¡rio apÃ³s o cadastro.
    """
    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="UsuÃ¡rio nÃ£o encontrado"
            )

        user.is_admin = True
        user.is_active = True

        # Garante o plano comercial (trial e assinatura usam o mesmo)
        plan = await get_or_create_plan(db)

        # Ativa ou cria subscription
        sub_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
        subscription = sub_result.scalar_one_or_none()
        now = datetime.now(UTC)
        period_end = now + timedelta(days=365)
        if subscription is None:
            subscription = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status="active",
                current_period_start=now,
                current_period_end=period_end,
                auto_renew=True,
            )
            db.add(subscription)
        else:
            subscription.plan_id = plan.id
            subscription.status = "active"
            subscription.current_period_start = now
            subscription.current_period_end = period_end
            subscription.auto_renew = True
            subscription.cancelled_at = None

        await db.commit()
        await db.refresh(user)
        return {
            "id": user.id,
            "email": user.email,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "subscription_status": subscription.status,
        }
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        logger.exception("Erro ao processar solicitacao administrativa")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao processar a solicitacao.",
        ) from None

# ----------------------------------------------------------------------
# Linha propria do provedor de IPTV (revogacao por assinante)
#
# Sem isso todos os assinantes usam a MESMA URL (IPTV_PLAYLIST_URL) e um
# vazamento nao pode ser revogado sem trocar a credencial de todos. Quando o
# provedor permite subconta, o admin grava aqui a URL da linha do cliente; o
# /player/playlist passa a entrega-la no lugar da compartilhada.
# ----------------------------------------------------------------------


class ProviderLineRequest(BaseModel):
    playlist_url: str
    note: str | None = None


@router.post("/subscriptions/{subscription_id}/line")
async def set_provider_line(
    subscription_id: UUID,
    payload: ProviderLineRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Vincula a linha propria (credencial do provedor) a uma assinatura."""
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura nao encontrada")

    url = payload.playlist_url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A URL da linha precisa ser http(s)",
        )

    subscription.provider_playlist_url = url[:2000]
    subscription.provider_revoked_at = None
    await db.commit()
    logger.info(
        "Linha propria vinculada: subscription=%s por admin=%s", subscription.id, admin.email
    )
    return {
        "subscription_id": str(subscription.id),
        "configured": True,
        "note": payload.note,
    }


@router.delete("/subscriptions/{subscription_id}/line")
async def revoke_provider_line(
    subscription_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Revoga a linha propria (cliente volta para a playlist compartilhada)."""
    result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura nao encontrada")

    subscription.provider_revoked_at = datetime.now(UTC)
    subscription.provider_playlist_url = None
    await db.commit()
    logger.info("Linha propria revogada: subscription=%s por admin=%s", subscription.id, admin.email)
    return {"subscription_id": str(subscription.id), "configured": False}
