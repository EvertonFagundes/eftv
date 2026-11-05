# routes/player.py - Acesso do app nativo ao catalogo e a playlist
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.subscription import Subscription
from app.security.dependencies import get_current_active_subscription, get_device_id
from app.services.devices import (
    DeviceLimitError,
    active_devices,
    bind_device,
    device_limit,
    revoke_device,
)

router = APIRouter(prefix="/player", tags=["Player"])


class SubscriptionInfo(BaseModel):
    status: str
    current_period_end: datetime
    days_remaining: int


class PlaylistAccessResponse(BaseModel):
    playlist_url: str
    user_agent: str
    referer: str | None = None
    # Segundos ate o app revalidar o acesso com o servidor
    refresh_in: int
    # Segundos de tolerancia usando o catalogo salvo quando estiver offline
    offline_grace_seconds: int
    server_time: datetime
    subscription: SubscriptionInfo


class DeviceInfo(BaseModel):
    device_id: str
    device_name: str | None = None
    bound_at: datetime
    last_seen_at: datetime
    current: bool


class DeviceAccessResponse(BaseModel):
    limit: int
    bound: int
    devices: list[DeviceInfo]


class MessageResponse(BaseModel):
    message: str


@router.get("/playlist", response_model=PlaylistAccessResponse)
async def get_playlist_access(
    subscription: Subscription = Depends(get_current_active_subscription),
    device_id: str = Depends(get_device_id),
    device_name: str | None = Header(default=None, alias="X-Device-Name"),
    db: AsyncSession = Depends(get_db),
):
    """
    Entrega a URL da playlist licenciada apenas para assinantes ativos.

    A URL fica no servidor (variavel IPTV_PLAYLIST_URL), nunca dentro do APK,
    e pode ser trocada ou revogada sem recompilar o aplicativo. O aparelho e
    vinculado automaticamente na primeira consulta, respeitando o limite do
    plano.
    """
    if not settings.IPTV_PLAYLIST_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Playlist ainda nao configurada no servidor",
        )

    try:
        await bind_device(db, subscription, device_id, device_name)
    except DeviceLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "device_limit",
                "message": (
                    "Esta assinatura ja esta vinculada ao numero maximo de "
                    "aparelhos. Desvincule um aparelho para continuar."
                ),
            },
        ) from exc

    now = datetime.now(UTC)
    period_end = subscription.current_period_end
    if period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=UTC)
    days_remaining = max((period_end - now).days, 0)

    return PlaylistAccessResponse(
        playlist_url=settings.IPTV_PLAYLIST_URL,
        user_agent=settings.IPTV_PLAYLIST_USER_AGENT,
        referer=settings.IPTV_PLAYLIST_REFERER,
        refresh_in=settings.IPTV_PLAYLIST_REFRESH_SECONDS,
        offline_grace_seconds=settings.OFFLINE_GRACE_MINUTES * 60,
        server_time=now,
        subscription=SubscriptionInfo(
            status=subscription.status,
            current_period_end=period_end,
            days_remaining=days_remaining,
        ),
    )


@router.get("/device", response_model=DeviceAccessResponse)
async def get_device_access(
    subscription: Subscription = Depends(get_current_active_subscription),
    device_id: str = Depends(get_device_id),
    db: AsyncSession = Depends(get_db),
):
    """Mostra os aparelhos vinculados e qual deles esta consultando agora."""
    devices = await active_devices(db, subscription.id)
    return DeviceAccessResponse(
        limit=device_limit(subscription),
        bound=len(devices),
        devices=[
            DeviceInfo(
                device_id=device.device_id,
                device_name=device.device_name,
                bound_at=device.created_at,
                last_seen_at=device.last_seen_at,
                current=device.device_id == device_id,
            )
            for device in devices
        ],
    )


@router.post("/device/revoke", response_model=MessageResponse)
async def revoke_current_device(
    subscription: Subscription = Depends(get_current_active_subscription),
    device_id: str = Depends(get_device_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Desvincula o aparelho atual, liberando a vaga para outro aparelho.

    A proxima consulta da playlist pode vincular este aparelho novamente,
    entao use antes de trocar de aparelho.
    """
    removed = await revoke_device(db, subscription, device_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este aparelho nao esta vinculado a assinatura",
        )
    return MessageResponse(message="Aparelho desvinculado com sucesso")
