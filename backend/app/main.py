# main.py - FastAPI app, middleware, lifespan, routers
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import close_db, init_db
from app.routes import (
    admin_router,
    auth_router,
    categories_router,
    channels_router,
    plans_router,
    player_router,
    subscriptions_router,
)
from app.security.dependencies import client_ip
from app.services.mercadopago import sync_pending_subscriptions
from app.tasks.subscription_checker import (
    check_expired_subscriptions,
    cleanup_stale_playback_sessions,
)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()

    # Agenda tasks periódicas
    scheduler.add_job(check_expired_subscriptions, "interval", minutes=30, id="check_expired")
    scheduler.add_job(cleanup_stale_playback_sessions, "interval", hours=1, id="cleanup_sessions")
    # Conciliacao do Mercado Pago: libera assinatura paga mesmo se o webhook
    # atrasar ou nao estiver cadastrado no painel.
    scheduler.add_job(sync_pending_subscriptions, "interval", minutes=5, id="sync_pending")
    scheduler.start()

    yield

    # Shutdown
    scheduler.shutdown()
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="EFTV - Plataforma de Streaming por Assinatura",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if settings.DEBUG:
        import traceback

        traceback.print_exc()

    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor"},
    )


# Health check
def mercadopago_token_kind() -> str:
    """Classifica o token do Mercado Pago sem expor o segredo.

    O preapproval de teste (``TEST-...``) so aceita pagador que tambem seja
    usuario de teste. Saber isso no /health evita horas de diagnostico.
    """
    token = settings.MERCADOPAGO_ACCESS_TOKEN or ""
    if not token:
        return "missing"
    if token.startswith("TEST-"):
        return "test"
    if token.startswith("APP_USR-"):
        return "production"
    return "unknown"


async def mercadopago_account_info() -> dict | None:
    """Identidade da conta coletora (com cache) para o /health."""
    from app.services.mercadopago import get_account_info

    info = await get_account_info()
    return info


@app.get("/health")
async def health_check(request: Request):
    # Diagnostico seguro: nada de segredo, so a configuracao que afeta o
    # checkout (a back_url precisa ser HTTPS e valida). "client_ip" mostra
    # qual IP o rate limit enxerga atras do proxy (o proprio chamador).
    account = await mercadopago_account_info()
    return {
        "status": "ok",
        "client_ip": client_ip(request),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "frontend_url": settings.FRONTEND_URL,
        "checkout_back_url": f"{settings.FRONTEND_URL.rstrip('/')}/checkout.html",
        "api_base_url": settings.API_BASE_URL,
        "mercadopago_configured": bool(settings.MERCADOPAGO_ACCESS_TOKEN),
        "mercadopago_token_kind": mercadopago_token_kind(),
        "mercadopago_sandbox": settings.MERCADOPAGO_SANDBOX,
        # Conta de teste nao consegue cobrar cliente real: precisa das
        # credenciais de producao da conta Mercado Pago de verdade.
        "mercadopago_account": account,
        # Diagnostico do limite comercial (nao e segredo): plano de 2 aparelhos.
        "max_devices_per_subscription": settings.MAX_DEVICES_PER_SUBSCRIPTION,
    }


# API Routes
app.include_router(auth_router)
app.include_router(plans_router)
app.include_router(channels_router)
app.include_router(categories_router)
app.include_router(subscriptions_router)
app.include_router(player_router)
app.include_router(admin_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
