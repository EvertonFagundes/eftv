# main.py - FastAPI app, middleware, lifespan, routers
import time
from contextlib import asynccontextmanager

import httpx
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


_mp_account_cache: dict = {"at": 0.0, "data": None}


async def mercadopago_account_info() -> dict | None:
    """Diz se a conta que recebe os pagamentos e de teste.

    Conta de teste so aceita pagador de teste ("Both payer and collector must
    be real or test users"). O resultado fica em cache por 10 minutos para o
    health check nao depender do Mercado Pago a cada acesso.
    """
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        return None

    now = time.monotonic()
    if _mp_account_cache["data"] is not None and now - _mp_account_cache["at"] < 600:
        return _mp_account_cache["data"]

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(
                "https://api.mercadopago.com/users/me",
                headers={"Authorization": f"Bearer {settings.MERCADOPAGO_ACCESS_TOKEN}"},
            )
        if response.status_code >= 400:
            return None
        data = response.json()
    except Exception:  # noqa: BLE001
        return None

    email = str(data.get("email") or "")
    nickname = str(data.get("nickname") or "")
    info = {
        "is_test_user": "test_user" in (data.get("tags") or [])
        or email.endswith("@testuser.com")
        or nickname.startswith("TESTUSER"),
        "site_id": data.get("site_id"),
        "country_id": data.get("country_id"),
    }
    _mp_account_cache.update(at=now, data=info)
    return info


@app.get("/health")
async def health_check():
    # Diagnostico seguro: nada de segredo, so a configuracao que afeta o
    # checkout (a back_url precisa ser HTTPS e valida).
    account = await mercadopago_account_info()
    return {
        "status": "ok",
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
