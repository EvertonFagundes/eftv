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
    allow_origins=settings.CORS_ORIGINS,
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
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}


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
