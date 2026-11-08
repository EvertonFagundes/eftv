# config.py - Configurações da aplicação (pydantic-settings)
import json
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Parametros de URL que o asyncpg nao entende e que o pooler costuma mandar.
# `channel_binding` vem do libpq; `pgbouncer` sinaliza o modo de compatibilidade.
_DROPPED_QUERY_PARAMS = {"channel_binding", "pgbouncer"}


def is_pooler_url(url: str) -> bool:
    """Detecta conexao via pooler (Supavisor/PgBouncer).

    Em pooler os prepared statements nao sobrevivem entre requisicoes: a
    conexao fisica pode ser reaproveitada por outro cliente. Nesse caso e
    obrigatorio desligar os caches de statement (ver ``app.database``).
    """
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:  # URL malformada: deixa o engine reportar o erro real
        return False

    if port == 6543:
        return True
    return host.endswith("pooler.supabase.com") or host.endswith("pooler.supabase.co")


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
    # None = detecta pela URL; force True/False se o provedor mudar de padrao.
    DATABASE_POOLER: bool | None = None

    # Security
    SECRET_KEY: str = Field(..., description="Chave secreta para JWT - DEVE ser definida no .env")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    BCRYPT_ROUNDS: int = 12

    # CORS (lista separada por virgula ou JSON, ver cors_origins)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,https://app.eftv.com.br"

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

        Tambem limpa parametros do libpq que o asyncpg recusa:
        ``sslmode`` vira ``ssl``; ``channel_binding`` e ``pgbouncer`` saem
        (o modo pooler e detectado pela porta/host, nao pelo parametro).
        """
        if value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value[len("postgres://") :]
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value[len("postgresql://") :]

        base, separator, query = value.partition("?")
        if not separator:
            return value

        kept: list[str] = []
        for pair in query.split("&"):
            if not pair:
                continue
            key = pair.split("=", 1)[0]
            if key in _DROPPED_QUERY_PARAMS:
                continue
            if key == "sslmode":
                # asyncpg espera ssl=require, nao o sslmode= do libpq.
                pair = "ssl" + pair[len("sslmode") :]
            kept.append(pair)

        return f"{base}?{'&'.join(kept)}" if kept else base

    @property
    def cors_origins(self) -> list[str]:
        """Origens liberadas no CORS.

        Aceita JSON (formato antigo) e lista separada por virgula, que e o
        formato pratico de colar no painel do Render.
        """
        raw = self.CORS_ORIGINS.strip()
        if not raw:
            return []

        if raw.startswith("["):
            try:
                values = json.loads(raw)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(values, list):
                    return [str(item).strip() for item in values if str(item).strip()]

        return [item.strip() for item in raw.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    # Os campos obrigatorios vem do ambiente/.env; o mypy nao executa o
    # carregamento dinamico do pydantic-settings.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
