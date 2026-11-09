# routes/subscriptions.py - Rotas de assinaturas e webhooks
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.payment import CheckoutRequest, CheckoutResponse, SubscriptionResponse
from app.security.dependencies import get_current_user
from app.services.mercadopago import (
    create_checkout_preference,
    process_webhook,
    validate_webhook_signature,
)

router = APIRouter(prefix="/subscriptions", tags=["Assinaturas"])


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

    # Cria preferência no Mercado Pago
    preference = await create_checkout_preference(
        user=user,
        plan=plan,
        payer_email=data.payer_email or user.email,
        payer_name=data.payer_name or user.full_name,
        payer_phone=data.payer_phone or user.phone,
        payer_cpf=data.payer_cpf,
        back_urls=data.back_urls,
    )

    # Salva subscription pendente
    subscription = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status="pending",
        mercadopago_subscription_id=preference["id"],
        current_period_start=datetime.now(UTC),
        current_period_end=datetime.now(UTC),
    )
    db.add(subscription)
    await db.commit()

    return CheckoutResponse(
        preference_id=preference["id"],
        init_point=preference["init_point"],
        sandbox_init_point=preference.get("sandbox_init_point"),
        expires_at=datetime.now(UTC),  # TODO: calcular expiração real
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
