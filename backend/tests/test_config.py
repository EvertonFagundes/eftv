import pytest

from app.config import Settings


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
