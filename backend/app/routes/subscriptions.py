# routes/subscriptions.py - Rotas de assinaturas e webhooks
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.payment import (
    CheckoutRequest,
    CheckoutResponse,
    SubscriptionOverview,
    SubscriptionResponse,
)
from app.security.dependencies import get_current_user
from app.services.mercadopago import (
    create_checkout_preference,
    process_webhook,
    sync_preapproval,
    validate_webhook_signature,
)
from app.services.plans import get_or_create_plan

router = APIRouter(prefix="/subscriptions", tags=["Assinaturas"])

logger = logging.getLogger(__name__)


@router.get("", response_model=list[SubscriptionResponse])
async def list_my_subscriptions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista assinaturas do usuário logado."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    subscriptions = result.scalars().all()

    response = []
    for sub in subscriptions:
        plan_result = await db.execute(select(Plan).where(Plan.id == sub.plan_id))
        plan = plan_result.scalar_one()
        response.append(
            SubscriptionResponse(
                id=sub.id,
                plan_id=sub.plan_id,
                plan_name=plan.name,
                status=sub.status,
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                trial_end=sub.trial_end,
                cancel_at_period_end=sub.cancel_at_period_end,
                auto_renew=sub.auto_renew,
                days_remaining=sub.days_remaining,
                is_active=sub.is_active,
                is_trial=sub.is_trial,
            )
        )
    return response


@router.get("/current", response_model=SubscriptionOverview)
async def current_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resumo da assinatura do usuário para a tela "Minha assinatura".

    Antes de responder, tenta sincronizar um checkout pendente direto no
    Mercado Pago. Assim o botão "Atualizar status" do app resolve mesmo se o
    webhook atrasar ou falhar, sem depender de suporte.
    """
    plan = await get_or_create_plan(db)

    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    subscriptions = list(result.scalars().all())

    subscription = next(
        (sub for sub in subscriptions if sub.has_access),
        subscriptions[0] if subscriptions else None,
    )

    if subscription is not None:
        plan_result = await db.execute(select(Plan).where(Plan.id == subscription.plan_id))
        subscription_plan = plan_result.scalar_one_or_none()
        if subscription_plan is not None:
            plan = subscription_plan

        # Pendente: o pagamento pode ter sido aprovado sem o webhook chegar.
        if subscription.status == "pending" and subscription.mercadopago_subscription_id:
            if await sync_preapproval(subscription.id):
                await db.refresh(subscription)

    return SubscriptionOverview(
        subscription_id=subscription.id if subscription is not None else None,
        plan_id=plan.id,
        plan_name=plan.name,
        plan_description=plan.description,
        price_cents=plan.price_cents,
        currency=plan.currency,
        interval=plan.interval,
        max_devices=plan.max_devices,
        max_streams=plan.max_simultaneous_streams,
        status=subscription.status if subscription is not None else "none",
        days_remaining=subscription.days_remaining if subscription is not None else 0,
        current_period_end=subscription.current_period_end if subscription is not None else None,
        trial_end=subscription.trial_end if subscription is not None else None,
        cancel_at_period_end=(
            subscription.cancel_at_period_end if subscription is not None else False
        ),
        auto_renew=subscription.auto_renew if subscription is not None else False,
        has_access=subscription.has_access if subscription is not None else False,
    )


@router.get("/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Obtém detalhes de uma assinatura específica."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.id == subscription_id)
        .where(Subscription.user_id == user.id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada"
        )

    plan_result = await db.execute(select(Plan).where(Plan.id == subscription.plan_id))
    plan = plan_result.scalar_one()

    return SubscriptionResponse(
        id=subscription.id,
        plan_id=subscription.plan_id,
        plan_name=plan.name,
        status=subscription.status,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        trial_end=subscription.trial_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        auto_renew=subscription.auto_renew,
        days_remaining=subscription.days_remaining,
        is_active=subscription.is_active,
        is_trial=subscription.is_trial,
    )


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    data: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Cria preferência de checkout no Mercado Pago.
    Retorna URL para redirecionar usuário ao pagamento.
    """
    # Verifica plano
    plan_result = await db.execute(select(Plan).where(Plan.id == data.plan_id))
    plan = plan_result.scalar_one_or_none()

    if not plan or not plan.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plano não encontrado")

    # Um usuario pode ter o trial antigo e a assinatura paga ao mesmo tempo.
    # Nao abre outro checkout para quem ja tem assinatura paga valida.
    existing_result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    existing_subscriptions = existing_result.scalars().all()
    paid_active = next(
        (sub for sub in existing_subscriptions if sub.status == "active" and sub.has_access),
        None,
    )
    if paid_active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "already_active",
                "message": "Sua assinatura já está ativa.",
            },
        )

    # Cria preferência no Mercado Pago
    try:
        preference = await create_checkout_preference(
            user=user,
            plan=plan,
            payer_email=data.payer_email or user.email,
            payer_name=data.payer_name or user.full_name,
            payer_phone=data.payer_phone or user.phone,
            payer_cpf=data.payer_cpf,
            back_urls=data.back_urls,
        )
    except RuntimeError as exc:
        # Antes o cliente via "erro interno" e o suporte nao sabia o motivo.
        # A mensagem do Mercado Pago e de validacao, nao tem segredo, e evita
        # ida e volta para descobrir o que recusou a assinatura.
        logger.error("Mercado Pago recusou o checkout: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "code": "checkout_failed",
                "message": "Nao foi possivel iniciar o pagamento agora. "
                f"Detalhe tecnico: {str(exc)[:280]}",
            },
        ) from exc

    # Reaproveita um checkout pendente em vez de acumular linhas.
    now = datetime.now(UTC)
    subscription = next((sub for sub in existing_subscriptions if sub.status == "pending"), None)
    if subscription is not None:
        subscription.plan_id = plan.id
        subscription.mercadopago_subscription_id = preference["id"]
        subscription.current_period_start = now
        subscription.current_period_end = now
    else:
        subscription = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status="pending",
            mercadopago_subscription_id=preference["id"],
            current_period_start=now,
            current_period_end=now,
        )
        db.add(subscription)
    await db.commit()

    return CheckoutResponse(
        preference_id=preference["id"],
        init_point=preference["init_point"],
        sandbox_init_point=preference.get("sandbox_init_point"),
        # O preapproval pendente nao informa validade; 24h e um teto pratico.
        expires_at=now + timedelta(days=1),
    )


@router.post("/webhook/mercadopago", status_code=status.HTTP_200_OK)
async def mercadopago_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook do Mercado Pago para eventos de assinatura/pagamento.
    Processa: assinatura autorizada/cancelada e cobranças recorrentes.
    """
    payload = await request.json()

    # O id do recurso pode vir na query (?data.id=...) ou no corpo.
    data_id = request.query_params.get("data.id") or request.query_params.get("id")
    if not data_id:
        data = payload.get("data") or {}
        data_id = data.get("id") or payload.get("id")
    data_id = str(data_id) if data_id else None

    # Valida o HMAC do header x-signature (quando o segredo esta configurado).
    if not validate_webhook_signature(request.headers, data_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Assinatura do webhook inválida",
        )

    await process_webhook(payload, db, data_id=data_id)

    return {"status": "ok"}


@router.post("/{subscription_id}/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    subscription_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancela assinatura do usuário (cancela no próximo ciclo)."""
    result = await db.execute(
        select(Subscription)
        .where(Subscription.id == subscription_id)
        .where(Subscription.user_id == user.id)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assinatura não encontrada"
        )

    if subscription.status not in ["active", "trial"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Assinatura não pode ser cancelada"
        )

    subscription.cancel_at_period_end = True
    subscription.auto_renew = False
    await db.commit()
    await db.refresh(subscription)

    plan_result = await db.execute(select(Plan).where(Plan.id == subscription.plan_id))
    plan = plan_result.scalar_one()

    return SubscriptionResponse(
        id=subscription.id,
        plan_id=subscription.plan_id,
        plan_name=plan.name,
        status=subscription.status,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        trial_end=subscription.trial_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        auto_renew=subscription.auto_renew,
        days_remaining=subscription.days_remaining,
        is_active=subscription.is_active,
        is_trial=subscription.is_trial,
    )
