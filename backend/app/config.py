# config.py - Configurações da aplicação (pydantic-settings)
from functools import lru_cache

from pydantic import Field, field_validator
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
    # Limite de aparelhos quando o plano nao define um valor proprio
    MAX_DEVICES_PER_SUBSCRIPTION: int = 1

    # Email (Resend)
    RESEND_API_KEY: str | None = None
    EMAIL_FROM: str = "EFTV <noreply@eftv.com.br>"

    # Verificacao de email
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    # Dias de trial gratuito apos verificacao de email
    FREE_TRIAL_DAYS: int = 7

    # Frontend URL (para links em emails, redirects)
    FRONTEND_URL: str = "http://localhost:3000"

    # Logging
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str | None = None

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """
        Aceita a URL como os provedores entregam (Render/Heroku usam
        ``postgresql://``) e converte para o driver async do SQLAlchemy.
        """
        if value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value[len("postgres://") :]
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value[len("postgresql://") :]

        # asyncpg espera ssl=require, nao o sslmode= do libpq.
        return value.replace("sslmode=require", "ssl=require")


@lru_cache
def get_settings() -> Settings:
    # Os campos obrigatorios vem do ambiente/.env; o mypy nao executa o
    # carregamento dinamico do pydantic-settings.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
