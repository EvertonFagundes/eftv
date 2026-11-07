# database.py - SQLAlchemy async engine e session
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


# Engine assíncrono
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency para injetar sessão DB nas routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager para usar DB fora de requests (tasks, scripts)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Cria tabelas e garante colunas novas (dev/testes e fallback de deploy).

    Em producao as migrations do Alembic rodam no deploy. Se o servico subir
    sem elas, o SELECT em users falha porque o modelo tem colunas que ainda
    nao existem no banco. Este bloco aplica essas colunas de forma idempotente.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        if conn.dialect.name != "postgresql":
            return

        exists = await conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'users' "
                "AND column_name = 'email_verification_token'"
            )
        )
        if exists.first() is not None:
            return

        # Rollout do recurso de verificacao de email: cria as colunas e marca
        # as contas existentes como verificadas (foram criadas antes do fluxo).
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "email_verification_token VARCHAR(255)"
            )
        )
        await conn.execute(
            text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "email_verification_expires_at TIMESTAMPTZ"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_users_email_verification_token "
                "ON users (email_verification_token)"
            )
        )
        await conn.execute(text("UPDATE users SET email_verified = true"))


async def close_db() -> None:
    """Fecha conexões do pool."""
    await engine.dispose()
