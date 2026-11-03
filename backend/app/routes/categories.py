# routes/categories.py - Rotas de categorias
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.category import Category
from app.models.user import User
from app.security.dependencies import require_admin

router = APIRouter(prefix="/categories", tags=["Categorias"])


@router.get("")
async def list_categories(
    active_only: bool = True,
    include_adult: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Lista categorias (público)."""
    query = select(Category)
    if active_only:
        query = query.where(Category.is_active.is_(True))
    if not include_adult:
        query = query.where(Category.is_adult.is_(False))
    query = query.order_by(Category.sort_order, Category.name)

    result = await db.execute(query)
    categories = result.scalars().all()

    return [
        {
            "id": c.id,
            "slug": c.slug,
            "name": c.name,
            "icon": c.icon,
            "color": c.color,
            "description": c.description,
            "is_adult": c.is_adult,
        }
        for c in categories
    ]


@router.get("/{category_id}")
async def get_category(category_id: UUID, db: AsyncSession = Depends(get_db)):
    """Obtém categoria por ID."""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoria não encontrada"
        )

    return {
        "id": category.id,
        "slug": category.slug,
        "name": category.name,
        "icon": category.icon,
        "color": category.color,
        "description": category.description,
        "is_adult": category.is_adult,
    }


# Admin routes
@router.post("", status_code=status.HTTP_201_CREATED)
async def create_category(
    slug: str,
    name: str,
    icon: str | None = None,
    color: str | None = None,
    description: str | None = None,
    sort_order: int = 0,
    is_adult: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Cria categoria (admin)."""
    from app.models.category import Category

    result = await db.execute(select(Category).where(Category.slug == slug))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug já em uso")

    category = Category(
        slug=slug,
        name=name,
        icon=icon,
        color=color,
        description=description,
        sort_order=sort_order,
        is_adult=is_adult,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return {"id": category.id, "slug": category.slug, "name": category.name}


@router.patch("/{category_id}")
async def update_category(
    category_id: UUID,
    name: str | None = None,
    icon: str | None = None,
    color: str | None = None,
    description: str | None = None,
    sort_order: int | None = None,
    is_adult: bool | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Atualiza categoria (admin)."""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoria não encontrada"
        )

    if name is not None:
        category.name = name
    if icon is not None:
        category.icon = icon
    if color is not None:
        category.color = color
    if description is not None:
        category.description = description
    if sort_order is not None:
        category.sort_order = sort_order
    if is_adult is not None:
        category.is_adult = is_adult
    if is_active is not None:
        category.is_active = is_active

    await db.commit()
    await db.refresh(category)
    return {"id": category.id, "slug": category.slug, "name": category.name}


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Desativa categoria (admin)."""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoria não encontrada"
        )

    category.is_active = False
    await db.commit()
