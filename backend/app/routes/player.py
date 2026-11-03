# routes/player.py - Acesso do app nativo ao catalogo e a playlist
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.config import settings
from app.models.subscription import Subscription
from app.security.dependencies import get_current_active_subscription

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


@router.get("/playlist", response_model=PlaylistAccessResponse)
async def get_playlist_access(
    subscription: Subscription = Depends(get_current_active_subscription),
):
    """
    Entrega a URL da playlist licenciada apenas para assinantes ativos.

    A URL fica no servidor (variavel IPTV_PLAYLIST_URL), nunca dentro do APK,
    e pode ser trocada ou revogada sem recompilar o aplicativo.
    """
    if not settings.IPTV_PLAYLIST_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Playlist ainda nao configurada no servidor",
        )

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
