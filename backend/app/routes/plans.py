# routes/plans.py - Rotas de planos (públicas e autenticadas)
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.plan import Plan
from app.schemas.plan import PlanCreate, PlanUpdate, PlanResponse, PlanListResponse
from app.security.dependencies import get_current_user, require_admin

router = APIRouter(prefix="/plans", tags=["Planos"])


@router.get("", response_model=PlanListResponse)
async def list_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """Lista planos públicos (para página de vendas)."""
    query = select(Plan)
    if active_only:
        query = query.where(Plan.is_active == True)
    query = query.order_by(Plan.sort_order, Plan.price_cents)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    plans = result.scalars().all()

    return PlanListResponse(
        plans=[PlanResponse.model_validate(p) for p in plans],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    """Obtém detalhes de um plano específico."""
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plano não encontrado")

    return plan


# Admin routes
@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    data: PlanCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Cria novo plano (admin)."""
    plan = Plan(**data.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


@router.patch("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: UUID,
    data: PlanUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Atualiza plano (admin)."""
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plano não encontrado")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)

    await db.commit()
    await db.refresh(plan)
    return plan


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Desativa plano (soft delete - admin)."""
    result = await db.execute(select(Plan).where(Plan.id == plan_id))
    plan = result.scalar_one_or_none()

    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plano não encontrado")

    plan.is_active = False
    await db.commit()