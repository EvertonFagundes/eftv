# config.py - Configurações da aplicação (pydantic-settings)
import json
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Parametros de URL que o asyncpg nao entende e que o pooler costuma mandar.
# `channel_binding` vem do libpq; `pgbouncer` sinaliza o modo de compatibilidade.
_DROPPED_QUERY_PARAMS = {"channel_binding", "pgbouncer"}


def normalize_origin(value: str) -> str:
    """Reduz uma URL a origem CORS (esquema + host + porta).

    Aceita ``https://site.com/eftv/`` e devolve ``https://site.com``; tambem
    preserva valores especiais como ``*``.
    """
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return value


def _clean_origins(values: list[str]) -> list[str]:
    """Normaliza, remove vazios e repete sem duplicatas (mantendo a ordem)."""
    cleaned = [normalize_origin(item) for item in values if item.strip()]
    return list(dict.fromkeys(cleaned))


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
    APP_VERSION: str = "1.2.2"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development, staging, production
    # URL publica da API. O webhook de Assinaturas e configurado no proprio
    # payload da preapproval (o painel nao oferece a secao Webhooks).
    API_BASE_URL: str = "https://eftv.onrender.com"

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
    SECRET_KEY: str = Field(
        ..., min_length=32, description="Chave secreta para JWT - DEVE ser definida no .env"
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    BCRYPT_ROUNDS: int = 12
    # Teto do corpo das requisicoes (webhook/JSON). Sem isso um POST gigante
    # consome memoria do processo antes de qualquer validacao.
    MAX_REQUEST_BODY_BYTES: int = 1_048_576

    # CORS (lista separada por virgula ou JSON, ver cors_origins)
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,"
        "https://app.eftv.com.br,https://evertonfagundes.github.io"
    )

    # Rate limiting (por identidade, ver services/rate_limit.py)
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    # Tentativas de login por conta (blindagem contra brute force). Por
    # conta, nao por IP: atras do proxy todos os clientes vem do mesmo IP.
    RATE_LIMIT_LOGIN_FAILURES: int = 10
    RATE_LIMIT_LOGIN_FAILURE_WINDOW_SECONDS: int = 300
    # Cadastro e emails por conta: cada criacao de conta nova custa um e-mail.
    RATE_LIMIT_REGISTER_PER_HOUR: int = 5
    RATE_LIMIT_EMAIL_PER_HOUR: int = 3
    # Codigo de recuperacao de senha: 6 digitos so sao seguros com limite de
    # tentativas por conta.
    RATE_LIMIT_PASSWORD_RESET_ATTEMPTS: int = 5
    RATE_LIMIT_PASSWORD_RESET_WINDOW_SECONDS: int = 900
    # Telemetria de travamento do app (endpoint publico).
    RATE_LIMIT_CRASHES_PER_MINUTE: int = 60

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
    # Consulta do vencimento da playlist no provedor (painel admin). Restrita
    # as contas abaixo: e dado do contrato, nao do assinante. Lista separada
    # por virgula.
    PLAYLIST_EXPIRY_EMAILS: str = "evertonfagundes1510@gmail.com"
    PLAYLIST_EXPIRY_CACHE_SECONDS: int = 6 * 60 * 60
    PLAYLIST_EXPIRY_TIMEOUT_SECONDS: float = 20.0
    # Tolerancia offline: usa o catalogo salvo mesmo sem falar com o servidor
    OFFLINE_GRACE_MINUTES: int = 720
    # Limite de aparelhos quando o plano nao define um valor proprio
    MAX_DEVICES_PER_SUBSCRIPTION: int = 2
    # Teto operacional de telas simultaneas (o plano nao pode prometer mais)
    MAX_STREAMS_PER_SUBSCRIPTION: int = 2
    # Limite de telas simultaneas: heartbeat do app enquanto assiste. A sessao
    # expira sozinha se o aparelho sumir (rede caiu, app fechado a forca).
    STREAM_SESSION_TIMEOUT_SECONDS: int = 120
    STREAM_HEARTBEAT_SECONDS: int = 45

    # Login na TV por codigo (sem digitar senha no controle remoto)
    DEVICE_CODE_TTL_MINUTES: int = 10

    # Atualizacao do app distribuido por APK (fora da Play Store)
    APP_LATEST_VERSION_CODE: int = 0
    APP_LATEST_VERSION_NAME: str = ""
    APP_APK_URL: str = ""
    APP_UPDATE_NOTES: str = ""
    APP_UPDATE_MANDATORY: bool = False

    # Recebimento de erros/travamentos do app (telemetria propria)
    CLIENT_ERRORS_ENABLED: bool = True

    # Email (Brevo em producao; Resend como alternativa)
    EMAIL_PROVIDER: str = "auto"  # auto, brevo, resend, dev
    BREVO_API_KEY: str | None = None
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

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        """Recusa chave curta/placeholder: ela assina JWT e codigos de reset."""
        cleaned = value.strip()
        if len(cleaned) < 32:
            raise ValueError(
                "SECRET_KEY deve ter pelo menos 32 caracteres. "
                "No Render use 'Generate Value' (nao digite o texto) ou rode "
                "`openssl rand -hex 32` e cole o resultado."
            )
        # Placeholders que aparecem quando alguem digita o texto do botao do
        # painel em vez de deixar o Render gerar, ou copia exemplo do .env.
        placeholders = {
            "changeme",
            "change-me",
            "secret",
            "secret-key",
            "your-secret-key",
            "troque-esta-chave",
            "generate value",
            "generate-value",
            "your secret key here",
            "minha-chave-secreta",
        }
        if cleaned.lower() in placeholders or "generate value" in cleaned.lower():
            raise ValueError(
                "SECRET_KEY ainda e um placeholder ('Generate Value' etc.). "
                "No Render abra a variavel SECRET_KEY, clique em 'Generate Value' "
                "para o Render criar uma chave aleatoria, ou rode "
                "`openssl rand -hex 32` e cole o valor."
            )
        return cleaned

    @field_validator("ALGORITHM")
    @classmethod
    def validate_algorithm(cls, value: str) -> str:
        """Somente HMAC: impede configurar ``none`` ou algoritmo assimetrico."""
        allowed = {"HS256", "HS384", "HS512"}
        cleaned = value.strip().upper()
        if cleaned not in allowed:
            raise ValueError(f"ALGORITHM deve ser um de {sorted(allowed)}")
        return cleaned

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
                    return _clean_origins([str(item) for item in values])

        return _clean_origins(raw.split(","))

    @property
    def playlist_expiry_emails(self) -> set[str]:
        """Contas autorizadas a ver o vencimento da playlist licenciada."""
        return {
            item.strip().lower() for item in self.PLAYLIST_EXPIRY_EMAILS.split(",") if item.strip()
        }


@lru_cache
def get_settings() -> Settings:
    # Os campos obrigatorios vem do ambiente/.env; o mypy nao executa o
    # carregamento dinamico do pydantic-settings.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
