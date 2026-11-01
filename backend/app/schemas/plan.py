# schemas/plan.py - Schemas de planos
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID


class PlanBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    price_cents: int = Field(..., ge=0)
    currency: str = Field(default="BRL", pattern="^[A-Z]{3}$")
    interval: str = Field(default="month", pattern="^(month|year)$")
    max_simultaneous_streams: int = Field(default=1, ge=1, le=10)
    max_devices: int = Field(default=3, ge=1, le=20)
    features: dict = Field(default_factory=dict)
    sort_order: int = Field(default=0, ge=0)


class PlanCreate(PlanBase):
    mercadopago_plan_id: Optional[str] = Field(None, max_length=100)


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    price_cents: Optional[int] = Field(None, ge=0)
    currency: Optional[str] = Field(None, pattern="^[A-Z]{3}$")
    interval: Optional[str] = Field(None, pattern="^(month|year)$")
    max_simultaneous_streams: Optional[int] = Field(None, ge=1, le=10)
    max_devices: Optional[int] = Field(None, ge=1, le=20)
    features: Optional[dict] = None
    mercadopago_plan_id: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0)


class PlanResponse(PlanBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mercadopago_plan_id: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @property
    def price_formatted(self) -> str:
        return f"{self.price_cents / 100:.2f} {self.currency}"


class PlanListResponse(BaseModel):
    plans: list[PlanResponse]
    total: int