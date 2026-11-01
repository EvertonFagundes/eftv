# services/catalog.py - Lógica de catálogo/canais
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.channel import Channel


async def get_channels_with_categories(
    db: AsyncSession,
    category_id: UUID | None = None,
    search: str | None = None,
    is_live: bool | None = None,
    include_adult: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Channel], int]:
    """Busca canais paginados com filtros."""
    query = select(Channel).where(Channel.is_active)

    if category_id:
        query = query.where(Channel.category_id == category_id)
    if search:
        search_term = f"%{search.lower()}%"
        query = query.where(
            or_(
                Channel.name.ilike(search_term),
                Channel.group_title.ilike(search_term),
            )
        )
    if is_live is not None:
        query = query.where(Channel.is_live == is_live)
    if not include_adult:
        query = query.where(not Channel.is_adult)

    query = query.order_by(Channel.sort_order, Channel.name)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    channels = result.scalars().all()

    return list(channels), total


async def get_channel_by_slug(db: AsyncSession, slug: str) -> Channel | None:
    """Busca canal por slug."""
    result = await db.execute(select(Channel).where(Channel.slug == slug))
    return result.scalar_one_or_none()


async def get_active_categories(db: AsyncSession, include_adult: bool = False) -> list[Category]:
    """Lista categorias ativas ordenadas."""
    query = select(Category).where(Category.is_active)
    if not include_adult:
        query = query.where(not Category.is_adult)
    query = query.order_by(Category.sort_order, Category.name)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_category_by_slug(db: AsyncSession, slug: str) -> Category | None:
    """Busca categoria por slug."""
    result = await db.execute(select(Category).where(Category.slug == slug))
    return result.scalar_one_or_none()


async def increment_channel_view(channel_id: UUID, db: AsyncSession) -> None:
    """Incrementa contador de visualizações do canal (para analytics)."""
    # TODO: Implementar com Redis para performance
    pass


async def search_channels(db: AsyncSession, query: str, limit: int = 8) -> list[Channel]:
    """Busca rápida para autocomplete (mínimo 2 chars)."""
    if len(query) < 2:
        return []

    search_term = f"%{query.lower()}%"
    result = await db.execute(
        select(Channel)
        .where(Channel.is_active)
        .where(not Channel.is_adult)
        .where(
            or_(
                Channel.name.ilike(search_term),
                Channel.group_title.ilike(search_term),
            )
        )
        .limit(limit)
    )
    return list(result.scalars().all())
