# schemas/payment.py - Schemas de pagamentos e checkout
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PaymentBase(BaseModel):
    amount_cents: int = Field(..., ge=0)
    currency: str = Field(default="BRL", pattern="^[A-Z]{3}$")
    payment_method: str | None = Field(None, pattern="^(pix|credit_card|boleto|saldo_mp)$")


class PaymentCreate(PaymentBase):
    user_id: UUID
    subscription_id: UUID | None = None
    plan_id: UUID | None = None
    mercadopago_payment_id: str | None = Field(None, max_length=100)
    mercadopago_preference_id: str | None = Field(None, max_length=100)
    status: str = Field(
        default="pending", pattern="^(pending|approved|rejected|refunded|cancelled)$"
    )
    paid_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class PaymentResponse(PaymentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    subscription_id: UUID | None
    plan_id: UUID | None
    mercadopago_payment_id: str | None
    mercadopago_preference_id: str | None
    status: str
    paid_at: datetime | None
    metadata: dict
    created_at: datetime

    @property
    def amount_formatted(self) -> str:
        return f"{self.amount_cents / 100:.2f} {self.currency}"


class PaymentWebhook(BaseModel):
    """Schema para webhook do Mercado Pago (dados brutos)."""

    action: str
    api_version: str
    data: dict
    date_created: str
    id: int
    live_mode: bool
    type: str
    user_id: str


class CheckoutRequest(BaseModel):
    """Request para criar checkout no Mercado Pago."""

    plan_id: UUID
    payment_method: str | None = Field(None, pattern="^(pix|credit_card|boleto)$")
    # Campos opcionais para preencher dados do pagador
    payer_email: EmailStr | None = None
    payer_name: str | None = Field(None, max_length=255)
    payer_phone: str | None = Field(None, max_length=20)
    payer_cpf: str | None = Field(None, pattern=r"^\d{11}$")
    # URL de retorno (sucesso/falha/pendente)
    back_urls: dict | None = None  # {"success": "...", "failure": "...", "pending": "..."}


class CheckoutResponse(BaseModel):
    """Response com URL de checkout do Mercado Pago."""

    preference_id: str
    init_point: str  # URL para redirecionar o usuário
    sandbox_init_point: str | None = None
    expires_at: datetime


class SubscriptionResponse(BaseModel):
    """Response de assinatura do usuário logado."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plan_id: UUID
    plan_name: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    trial_end: datetime | None
    cancel_at_period_end: bool
    auto_renew: bool
    days_remaining: int
    is_active: bool
    is_trial: bool
