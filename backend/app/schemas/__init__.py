# schemas/__init__.py - Exporta todos os schemas
from app.schemas.auth import (
    Token,
    TokenPayload,
    UserRegister,
    UserLogin,
    UserResponse,
    UserUpdate,
    RefreshTokenRequest,
)
from app.schemas.plan import PlanCreate, PlanUpdate, PlanResponse, PlanListResponse
from app.schemas.channel import ChannelCreate, ChannelUpdate, ChannelResponse, ChannelListResponse, ChannelPlayResponse
from app.schemas.payment import PaymentCreate, PaymentResponse, PaymentWebhook, CheckoutRequest, CheckoutResponse

__all__ = [
    # Auth
    "Token",
    "TokenPayload",
    "UserRegister",
    "UserLogin",
    "UserResponse",
    "UserUpdate",
    "RefreshTokenRequest",
    # Plans
    "PlanCreate",
    "PlanUpdate",
    "PlanResponse",
    "PlanListResponse",
    # Channels
    "ChannelCreate",
    "ChannelUpdate",
    "ChannelResponse",
    "ChannelListResponse",
    "ChannelPlayResponse",
    # Payments
    "PaymentCreate",
    "PaymentResponse",
    "PaymentWebhook",
    "CheckoutRequest",
    "CheckoutResponse",
]