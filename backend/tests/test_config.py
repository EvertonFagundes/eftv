import pytest

from app.config import Settings, is_pooler_url
from app.database import build_connect_args


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "postgres://user:pass@host:5432/db",
            "postgresql+asyncpg://user:pass@host:5432/db",
        ),
        (
            "postgresql://user:pass@host/db",
            "postgresql+asyncpg://user:pass@host/db",
        ),
        (
            "postgresql+asyncpg://user:pass@host/db",
            "postgresql+asyncpg://user:pass@host/db",
        ),
        (
            "postgresql://user:pass@host/db?sslmode=require",
            "postgresql+asyncpg://user:pass@host/db?ssl=require",
        ),
    ],
)
def test_database_url_is_normalized_for_asyncpg(raw, expected):
    assert Settings.normalize_database_url(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # o pooler do Supabase manda channel_binding, que o asyncpg recusa
        (
            "postgresql://user:pass@aws-0-us-west-1.pooler.supabase.com:6543/postgres"
            "?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://user:pass@aws-0-us-west-1.pooler.supabase.com:6543/postgres"
            "?ssl=require",
        ),
        # pgbouncer=true tambem sai da URL (o modo e detectado pela porta/host)
        (
            "postgresql://user:pass@host:6543/db?pgbouncer=true&sslmode=require",
            "postgresql+asyncpg://user:pass@host:6543/db?ssl=require",
        ),
        # parametros desconhecidos e validos sao preservados
        (
            "postgresql://user:pass@host/db?application_name=eftv&sslmode=require",
            "postgresql+asyncpg://user:pass@host/db?application_name=eftv&ssl=require",
        ),
        # sem query string a URL passa intacta
        (
            "postgresql://user:pass@host/db",
            "postgresql+asyncpg://user:pass@host/db",
        ),
    ],
)
def test_database_url_drops_unsupported_libpq_params(raw, expected):
    assert Settings.normalize_database_url(raw) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql+asyncpg://u:p@aws-0-us-west-1.pooler.supabase.com:6543/postgres", True),
        ("postgresql+asyncpg://u:p@aws-0-us-west-1.pooler.supabase.com:5432/postgres", True),
        ("postgresql+asyncpg://u:p@db.abcdefgh.supabase.co:5432/postgres", False),
        ("postgresql+asyncpg://u:p@localhost:5432/eftv", False),
        ("postgresql+asyncpg://u:p@dpg-xyz.oregon-postgres.render.com:5432/db", False),
        ("nao-e-uma-url", False),
    ],
)
def test_is_pooler_url(url, expected):
    assert is_pooler_url(url) is expected


def test_connect_args_disabled_without_pooler():
    assert build_connect_args("postgresql+asyncpg://u:p@localhost:5432/eftv") == {}


def test_connect_args_disable_statement_caches_on_pooler():
    args = build_connect_args(
        "postgresql+asyncpg://u:p@aws-0-us-west-1.pooler.supabase.com:6543/postgres"
    )
    assert args == {"statement_cache_size": 0, "prepared_statement_cache_size": 0}


def test_connect_args_can_be_forced():
    url = "postgresql+asyncpg://u:p@localhost:5432/eftv"
    assert build_connect_args(url, use_pooler=True) == {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }
    pooler = "postgresql+asyncpg://u:p@aws-0-us-west-1.pooler.supabase.com:6543/postgres"
    assert build_connect_args(pooler, use_pooler=False) == {}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://evertonfagundes.github.io",
            ["https://evertonfagundes.github.io"],
        ),
        (
            "http://localhost:3000, http://localhost:5173 , ",
            ["http://localhost:3000", "http://localhost:5173"],
        ),
        (
            '["http://localhost:3000","https://app.eftv.com.br"]',
            ["http://localhost:3000", "https://app.eftv.com.br"],
        ),
        (
            "https://evertonfagundes.github.io/eftv/",
            ["https://evertonfagundes.github.io"],
        ),
        (
            "https://a.example.com/,https://a.example.com",
            ["https://a.example.com"],
        ),
        ("", []),
    ],
)
def test_cors_origins_accepts_csv_and_json(raw, expected):
    settings = Settings(SECRET_KEY="x" * 40, CORS_ORIGINS=raw)
    assert settings.cors_origins == expected


def test_default_cors_allows_github_pages(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings(SECRET_KEY="x" * 40, _env_file=None)
    assert "https://evertonfagundes.github.io" in settings.cors_origins
