# main.py - FastAPI app, middleware, lifespan, routers
import logging
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
    app_router,
    auth_router,
    categories_router,
    channels_router,
    plans_router,
    player_router,
    subscriptions_router,
)
from app.routes.app_client import apk_download
from app.security.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.services.mercadopago import sync_pending_subscriptions
from app.tasks.lifecycle_emails import send_lifecycle_emails
from app.tasks.subscription_checker import (
    check_expired_subscriptions,
    cleanup_stale_playback_sessions,
)

scheduler = AsyncIOScheduler()
logger = logging.getLogger(__name__)


async def self_ping() -> None:
    """Pinga o /ping publico para manter a instancia do Render acordada.

    O ping interno e apenas um reforco: quando o Render desliga o processo, o
    agendador morre junto e nao ha como se acordar sozinho. Por isso a linha
    principal e o keepalive externo (GitHub Actions). Usar a URL publica faz a
    requisicao passar pela borda (Cloudflare/Render), que e o trafego que conta
    como atividade; falhas ficam registradas para diagnostico.
    """
    url = f"{settings.API_BASE_URL.rstrip('/')}/ping"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
        if response.status_code != 200:
            logger.warning("self-ping respondeu HTTP %s", response.status_code)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha no self-ping (%s): %s", url, exc)


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
    # Avisos por email: teste acabando e cartao recusado.
    scheduler.add_job(send_lifecycle_emails, "interval", hours=6, id="lifecycle_emails")
    # Self-ping: mantem a instancia acordada (backup do keepalive externo).
    scheduler.add_job(self_ping, "interval", minutes=5, id="self_ping")
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

# GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Corpo maximo antes de qualquer parsing (webhook/JSON). Fica dentro do CORS
# para a resposta 413 tambem sair com os cabecalhos de origem.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.MAX_REQUEST_BODY_BYTES)

# CORS. Wildcard com credenciais e proibido pelo navegador e permitiria
# qualquer site ler a resposta autenticada; nesse caso desliga credentials.
_origins = settings.cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Por ultimo = mais externo: ate as respostas de erro/413 saem com os
# cabecalhos de seguranca.
app.add_middleware(SecurityHeadersMiddleware)


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


@app.get("/ping")
async def ping() -> dict:
    # Endpoint leve (sem banco/MP) para keepalive e self-ping.
    return {"status": "ok"}


@app.get("/health")
async def health_check(request: Request):
    # Diagnostico publico: so o que ajuda monitoramento, sem expor IP do
    # chamador, URLs internas ou id da conta do Mercado Pago.
    account = await mercadopago_account_info()
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "mercadopago_configured": bool(settings.MERCADOPAGO_ACCESS_TOKEN),
        "mercadopago_token_kind": mercadopago_token_kind(),
        "mercadopago_sandbox": settings.MERCADOPAGO_SANDBOX,
        "mercadopago_test_account": bool(account and account.get("is_test_user")),
        # Diagnostico do limite comercial (nao e segredo): plano de 2 aparelhos.
        "max_devices_per_subscription": settings.MAX_DEVICES_PER_SUBSCRIPTION,
        "max_streams_per_subscription": settings.MAX_STREAMS_PER_SUBSCRIPTION,
        # Versao publicada do app (atualizacao por APK).
        "app_version_code": settings.APP_LATEST_VERSION_CODE,
        "app_version_name": settings.APP_LATEST_VERSION_NAME,
        "app_update_configured": bool(settings.APP_APK_URL),
    }


# API Routes
app.include_router(auth_router)
app.include_router(plans_router)
app.include_router(channels_router)
app.include_router(categories_router)
app.include_router(subscriptions_router)
app.include_router(player_router)
app.include_router(admin_router)
app.include_router(app_router)

# Alias curto (`/tv`) para digitar no controle remoto: mesma resposta de
# /app/tv, o 302 que entrega o APK.
app.add_api_route("/tv", apk_download, include_in_schema=False)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
