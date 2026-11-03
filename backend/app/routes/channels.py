# routes/channels.py - Rotas de catálogo e playback
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.channel import Channel
from app.models.playback_session import PlaybackSession
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.channel import (
    ChannelCreate,
    ChannelListResponse,
    ChannelPlayResponse,
    ChannelResponse,
    ChannelUpdate,
)
from app.security.dependencies import (
    get_current_active_subscription,
    get_current_user,
    get_current_user_optional,
    get_device_fingerprint,
    require_admin,
)
from app.services.auth_service import create_stream_token
from app.services.streaming import generate_stream_url

router = APIRouter(prefix="/channels", tags=["Canais"])


@router.get("", response_model=ChannelListResponse)
async def list_channels(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: UUID | None = None,
    search: str | None = None,
    is_live: bool | None = None,
    include_adult: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user_optional),
):
    """Lista canais do catálogo (público para logados, com filtro 18+)."""
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
        # Se não logado ou usuário não tem permissão 18+, oculta adulto
        query = query.where(Channel.is_adult.is_(False))

    query = query.order_by(Channel.sort_order, Channel.name)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()

    # Paginate
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    channels = result.scalars().all()

    return ChannelListResponse(
        channels=[ChannelResponse.model_validate(c) for c in channels],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{slug}", response_model=ChannelResponse)
async def get_channel(slug: str, db: AsyncSession = Depends(get_db)):
    """Obtém detalhes de um canal pelo slug."""
    result = await db.execute(select(Channel).where(Channel.slug == slug))
    channel = result.scalar_one_or_none()

    if not channel or not channel.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal não encontrado")

    return channel


@router.get("/{slug}/play", response_model=ChannelPlayResponse)
async def play_channel(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    subscription: Subscription = Depends(get_current_active_subscription),
    device_fingerprint: str = Depends(get_device_fingerprint),
):
    """
    Autoriza playback do canal.
    Verifica: usuário autenticado, assinatura ativa, limite de streams simultâneos.
    Retorna URL do stream + token JWT assinado para validação no CDN.
    """
    # Busca canal
    result = await db.execute(select(Channel).where(Channel.slug == slug))
    channel = result.scalar_one_or_none()

    if not channel or not channel.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal não encontrado")

    if channel.is_adult and not user.is_admin:
        # TODO: Verificar se usuário tem permissão 18+ (idade verificada)
        pass

    # Verifica limite de streams simultâneos
    active_sessions = await db.execute(
        select(PlaybackSession)
        .where(PlaybackSession.user_id == user.id)
        .where(PlaybackSession.ended_at.is_(None))
    )
    active_count = len(active_sessions.scalars().all())

    max_streams = subscription.plan.max_simultaneous_streams
    if active_count >= max_streams:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Limite de {max_streams} stream(s) simultâneo(s) atingido",
        )

    # Verifica se canal tem stream configurado
    if not channel.stream_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canal sem fonte de stream configurada",
        )

    # Gera token de stream (curta duração)
    stream_token, token_jti, expires_at = create_stream_token(
        user_id=str(user.id),
        channel_id=str(channel.id),
        max_streams=max_streams,
        quality="auto",
    )

    # Registra sessão de playback
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    session = PlaybackSession(
        user_id=user.id,
        subscription_id=subscription.id,
        channel_id=channel.id,
        device_fingerprint=device_fingerprint,
        ip_address=ip,
        user_agent=ua,
        token_jti=token_jti,
    )
    db.add(session)

    # Gera URL final do stream (pode ser URL assinada do Cloudflare Stream, etc.)
    final_stream_url = await generate_stream_url(channel.stream_url, stream_token)

    await db.commit()

    response = ChannelPlayResponse(
        stream_url=final_stream_url,
        stream_type=channel.stream_type or "hls",
        token=stream_token,
        expires_at=expires_at,
        drm_license_url=channel.drm_license_url,
        backup_stream_url=channel.backup_stream_url,
        backup_stream_type=channel.backup_stream_type,
    )

    return response


# Admin routes
@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    data: ChannelCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Cria novo canal (admin)."""
    # Verifica slug único
    result = await db.execute(select(Channel).where(Channel.slug == data.slug))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug já em uso")

    channel = Channel(**data.model_dump())
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel


@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: UUID,
    data: ChannelUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Atualiza canal (admin)."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal não encontrado")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(channel, field, value)

    await db.commit()
    await db.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Desativa canal (soft delete - admin)."""
    result = await db.execute(select(Channel).where(Channel.id == channel_id))
    channel = result.scalar_one_or_none()

    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal não encontrado")

    channel.is_active = False
    await db.commit()
