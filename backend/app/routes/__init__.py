# routes/__init__.py - Exporta todos os routers
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.categories import router as categories_router
from app.routes.channels import router as channels_router
from app.routes.plans import router as plans_router
from app.routes.subscriptions import router as subscriptions_router

__all__ = [
    "auth_router",
    "plans_router",
    "channels_router",
    "categories_router",
    "subscriptions_router",
    "admin_router",
]
