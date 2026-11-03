# config.py - Configurações da aplicação (pydantic-settings)
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "EFTV API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development, staging, production

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/eftv"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Security
    SECRET_KEY: str = Field(..., description="Chave secreta para JWT - DEVE ser definida no .env")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    BCRYPT_ROUNDS: int = 12

    # CORS
    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "https://app.eftv.com.br",
        ]
    )

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Redis (para rate limiting, cache, sessões)
    REDIS_URL: str | None = None

    # Mercado Pago
    MERCADOPAGO_ACCESS_TOKEN: str | None = None
    MERCADOPAGO_PUBLIC_KEY: str | None = None
    MERCADOPAGO_WEBHOOK_SECRET: str | None = None
    MERCADOPAGO_SANDBOX: bool = True

    # Streaming (Cloudflare Stream)
    STREAM_PROVIDER: str = "cloudflare"  # cloudflare, mux, custom
    CLOUDFLARE_ACCOUNT_ID: str | None = None
    CLOUDFLARE_API_TOKEN: str | None = None
    STREAM_TOKEN_TTL_SECONDS: int = 900  # 15 min
    STREAM_TOKEN_ISSUER: str = "eftv-api"

    # Playlist IPTV (provedor licenciado) entregue apenas a assinantes ativos
    IPTV_PLAYLIST_URL: str = ""
    IPTV_PLAYLIST_USER_AGENT: str = "VLC/3.0.20 LibVLC/3.0.20"
    IPTV_PLAYLIST_REFERER: str | None = None
    # De quanto em quanto tempo o app deve revalidar o acesso
    IPTV_PLAYLIST_REFRESH_SECONDS: int = 300
    # Tolerancia offline: usa o catalogo salvo mesmo sem falar com o servidor
    OFFLINE_GRACE_MINUTES: int = 720

    # Email (Resend)
    RESEND_API_KEY: str | None = None
    EMAIL_FROM: str = "EFTV <noreply@eftv.com.br>"

    # Frontend URL (para links em emails, redirects)
    FRONTEND_URL: str = "http://localhost:3000"

    # Logging
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str | None = None


@lru_cache
def get_settings() -> Settings:
    # Os campos obrigatorios vem do ambiente/.env; o mypy nao executa o
    # carregamento dinamico do pydantic-settings.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
