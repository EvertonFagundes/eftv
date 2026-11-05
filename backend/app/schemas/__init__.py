# schemas/__init__.py - Exporta todos os schemas
from app.schemas.auth import (
    RefreshTokenRequest,
    Token,
    TokenPayload,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from app.schemas.channel import (
    ChannelCreate,
    ChannelListResponse,
    ChannelPlayResponse,
    ChannelResponse,
    ChannelUpdate,
)
from app.schemas.payment import (
    CheckoutRequest,
    CheckoutResponse,
    PaymentCreate,
    PaymentResponse,
    PaymentWebhook,
)
from app.schemas.plan import PlanCreate, PlanListResponse, PlanResponse, PlanUpdate

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
