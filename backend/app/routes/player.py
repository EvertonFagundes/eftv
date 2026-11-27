# routes/player.py - Acesso do app nativo ao catalogo e a playlist
import hashlib
import logging
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.subscription import Subscription
from app.security.dependencies import get_current_active_subscription, get_device_id
from app.services import trials
from app.services.devices import (
    DeviceLimitError,
    active_devices,
    bind_device,
    device_limit,
    revoke_all_devices,
    revoke_device,
)
from app.services.playlist_cache import (
    CacheInfo,
    PlaylistCacheError,
    load_cached_playlist,
)
from app.services.playlist_fetch import (
    PlaylistFetchError,
    fetch_playlist,
    looks_like_m3u,
    playlist_headers,
    recently_failed,
    url_publica,
)
from app.services.streams import (
    StreamLimitError,
    active_sessions,
    heartbeat,
    start_session,
    stop_session,
    stream_limit,
)

router = APIRouter(prefix="/player", tags=["Player"])

logger = logging.getLogger(__name__)

# Mantidos como aliases para compatibilidade com testes/chamadas antigas.
PLAYLIST_MAX_BYTES = settings.IPTV_PLAYLIST_MAX_BYTES
PLAYLIST_HEAD_BYTES = 8 * 1024
_parece_playlist_m3u = looks_like_m3u
_url_publica = url_publica


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


def _provider_url(subscription: Subscription | None) -> str | None:
    """Linha propria do assinante, quando existe e nao foi revogada.

    Sem ela o app cai na playlist compartilhada de ``IPTV_PLAYLIST_URL``.
    A linha propria e o unico jeito de revogar um cliente sem trocar a
    credencial de todos.
    """
    if subscription is None:
        return None
    if not subscription.provider_playlist_url or subscription.provider_revoked_at is not None:
        return None
    return subscription.provider_playlist_url.strip() or None


def _playlist_sources(subscription: Subscription | None) -> list[tuple[str, str]]:
    """Fontes para o fallback do backend, na ordem de preferencia.

    A linha propria vem primeiro, mas uma resposta HTML/erro dela nao pode
    impedir o uso da playlist compartilhada: era o que deixava o 4G sem
    catalogo quando o cadastro do assinante apontava para uma pagina do nginx.
    """
    fontes: list[tuple[str, str]] = []
    propria = _provider_url(subscription)
    if propria:
        fontes.append(("linha do assinante", propria))
    compartilhada = (settings.IPTV_PLAYLIST_URL or "").strip()
    if compartilhada and all(compartilhada != url for _, url in fontes):
        fontes.append(("playlist compartilhada", compartilhada))
    return fontes


def _descricao_erro(exc: Exception) -> str:
    """Motivo seguro para log/resposta: nunca inclui a URL com credenciais."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPError):
        return "falha de conexao"
    return str(exc) or exc.__class__.__name__


async def _baixar_playlist(url: str, headers: dict[str, str]) -> bytes:
    """Baixa a M3U usando o servico de fallbacks (HTTPS/IP/API/DoH)."""
    if recently_failed(url):
        raise PlaylistFetchError("provedor bloqueado recentemente")
    result = await fetch_playlist(
        url,
        headers,
        max_bytes=PLAYLIST_MAX_BYTES,
    )
    for attempt in result.attempts:
        if attempt.error:
            logger.warning("Playlist %s: %s", attempt.label, attempt.error)
        else:
            logger.info(
                "Playlist %s: HTTP %s, %s bytes, m3u=%s",
                attempt.label,
                attempt.status_code,
                attempt.bytes_read,
                attempt.looks_m3u,
            )
    if not result.ok:
        raise PlaylistFetchError(result.error_summary())
    return result.content


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
    if not settings.IPTV_PLAYLIST_URL and not _provider_url(subscription):
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

    # Teste gratis por APARELHO: se este device_id ja consumiu trial em outra
    # conta, o trial e revogado na hora. Este e o ponto que fecha o caminho de
    # quem confirma o e-mail pelo navegador (sem X-Device-Id no verify-email).
    if subscription.status == "trial":
        if await trials.device_already_used(db, device_id, subscription.user_id):
            trials.revoke_trial(subscription)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "trial_device_used",
                    "message": (
                        "Este aparelho ja usou o teste gratis. " "Assine para continuar assistindo."
                    ),
                },
            )
        await trials.claim(
            db,
            device_id=device_id,
            user_id=subscription.user_id,
            subscription_id=subscription.id,
        )

    now = datetime.now(UTC)
    period_end = subscription.current_period_end
    if period_end.tzinfo is None:
        period_end = period_end.replace(tzinfo=UTC)
    days_remaining = max((period_end - now).days, 0)

    playlist_url = (_provider_url(subscription) or settings.IPTV_PLAYLIST_URL or "").strip()
    if not playlist_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Playlist ainda nao configurada no servidor",
        )

    return PlaylistAccessResponse(
        playlist_url=playlist_url,
        user_agent=settings.IPTV_PLAYLIST_USER_AGENT,
        referer=(settings.IPTV_PLAYLIST_REFERER or "").strip() or None,
        refresh_in=settings.IPTV_PLAYLIST_REFRESH_SECONDS,
        offline_grace_seconds=settings.OFFLINE_GRACE_MINUTES * 60,
        server_time=now,
        subscription=SubscriptionInfo(
            status=subscription.status,
            current_period_end=period_end,
            days_remaining=days_remaining,
        ),
    )


def _playlist_response(conteudo: bytes, cache: CacheInfo | None = None) -> Response:
    """Resposta M3U; o cache leva cabecalhos para o app/web saberem da copia."""
    headers = {
        "Cache-Control": "no-store",
        "X-Playlist-Source": "cache" if cache is not None else "provider",
    }
    if cache is not None:
        headers["X-Playlist-Cache-Age"] = str(cache.age_seconds)
        if cache.stale:
            headers["Warning"] = '110 - "Response is stale"'
    return Response(
        content=conteudo,
        media_type="audio/x-mpegurl; charset=utf-8",
        headers=headers,
    )


@router.get("/playlist-text", response_class=Response)
async def get_playlist_text(
    subscription: Subscription = Depends(get_current_active_subscription),
    device_id: str = Depends(get_device_id),
    db: AsyncSession = Depends(get_db),
):
    """Entrega o texto da playlist buscado pelo backend.

    Em algumas operadoras o celular nao resolve o dominio do provedor nem
    consegue chegar aos servidores de DoH. O backend (em Render) tem DNS
    livre e tops HTTPS com o app, entao serve como ultimo recurso. A URL e
    sempre a configurada no painel: o cliente nao pode escolher o destino.

    Quando o provedor bloqueia o Render (geobloqueio), usa a ultima copia
    valida enviada por um admin a partir de uma rede autorizada.
    """
    del device_id  # O dependency ja vincula o aparelho.
    fontes = _playlist_sources(subscription)
    if not fontes:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Playlist nao configurada.")

    headers = playlist_headers()

    falhas: list[str] = []
    for rotulo, url in fontes:
        try:
            conteudo = await _baixar_playlist(url, headers)
        except (httpx.HTTPError, ValueError) as exc:
            motivo = _descricao_erro(exc)
            logger.warning("Playlist %s indisponivel: %s", rotulo, motivo)
            falhas.append(f"{rotulo}: {motivo}")
            continue
        if not _parece_playlist_m3u(conteudo):
            # 200 com HTML (nginx, login do provedor) nao e playlist. Sem esta
            # checagem o app recebia "nenhum canal" e apagava a experiencia.
            logger.warning(
                "Playlist %s nao parece M3U (%s bytes)",
                rotulo,
                len(conteudo),
            )
            falhas.append(f"{rotulo}: resposta nao e uma playlist M3U ({len(conteudo)} bytes)")
            continue

        logger.info("Playlist %s OK (%s bytes)", rotulo, len(conteudo))
        return _playlist_response(conteudo)

    # Provedor indisponivel/bloqueado: a copia local mantem o catalogo vivo.
    try:
        cached = await load_cached_playlist(db)
    except PlaylistCacheError as exc:
        logger.warning("Cache da playlist invalido: %s", exc)
        cached = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cache da playlist indisponivel: %s", exc.__class__.__name__)
        cached = None
    if cached is not None:
        conteudo, info = cached
        logger.warning(
            "Usando cache da playlist de %s (%s bytes, idade=%ss)",
            info.updated_at.isoformat(),
            len(conteudo),
            info.age_seconds,
        )
        return _playlist_response(conteudo, cache=info)

    raise HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        "Nao foi possivel obter uma playlist valida. " + "; ".join(falhas),
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


@router.post("/device/revoke-all", response_model=MessageResponse)
async def revoke_all_my_devices(
    subscription: Subscription = Depends(get_current_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """Desvincula todos os aparelhos da assinatura do proprio usuario.

    Serve para quem trocou/reinstalou o aparelho e ficou sem vaga: o app
    mostra "Assinatura em uso" e o usuario mesmo libera os aparelhos antigos,
    sem precisar de suporte.
    """
    removed = await revoke_all_devices(db, [subscription.id])
    return MessageResponse(
        message=f"{removed} aparelho(s) desvinculado(s). O proximo acesso vincula este."
    )


# ----------------------------------------------------------------------
# Limite de telas simultaneas
# ----------------------------------------------------------------------


class StreamPlayRequest(BaseModel):
    channel_url: str
    channel_name: str | None = None


class StreamPlayResponse(BaseModel):
    session_id: uuid.UUID
    limit: int
    active: int
    heartbeat_in: int


class StreamHeartbeatRequest(BaseModel):
    session_id: uuid.UUID


def _channel_ref(url: str) -> str:
    """Identifica o canal sem guardar a URL do provedor (que tem credenciais)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


@router.post("/play", response_model=StreamPlayResponse)
async def start_playback(
    payload: StreamPlayRequest,
    subscription: Subscription = Depends(get_current_active_subscription),
    device_id: str = Depends(get_device_id),
    db: AsyncSession = Depends(get_db),
):
    """Autoriza o inicio da reproducao e aplica o limite de telas do plano.

    O app chama ao abrir o player e repete o heartbeat enquanto assiste. Sem
    isso o plano de 1 tela era apenas texto no contrato: a mesma conta podia
    ser vista em quantos aparelhos quisesse ao mesmo tempo.
    """
    limit = stream_limit(subscription)
    try:
        session = await start_session(
            db,
            user_id=subscription.user_id,
            subscription_id=subscription.id,
            device_id=device_id,
            channel_ref=_channel_ref(payload.channel_url),
            channel_name=(payload.channel_name or "").strip()[:255] or None,
            limit=limit,
        )
    except StreamLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "stream_limit",
                "message": (
                    f"Sua assinatura permite {limit} tela por vez. "
                    "Feche o EFTV no outro aparelho para assistir aqui."
                ),
            },
        ) from exc

    active = await active_sessions(db, subscription.user_id)
    return StreamPlayResponse(
        session_id=session.id,
        limit=limit,
        active=len(active),
        heartbeat_in=settings.STREAM_HEARTBEAT_SECONDS,
    )


@router.post("/heartbeat", response_model=MessageResponse)
async def stream_heartbeat(
    payload: StreamHeartbeatRequest,
    subscription: Subscription = Depends(get_current_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """Mantem a sessao viva enquanto o video toca."""
    session = await heartbeat(
        db,
        user_id=subscription.user_id,
        session_id=payload.session_id,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "session_closed",
                "message": "Sessao encerrada. Abra o canal novamente.",
            },
        )
    return MessageResponse(message="ok")


@router.post("/stop", response_model=MessageResponse)
async def stop_playback(
    payload: StreamHeartbeatRequest,
    subscription: Subscription = Depends(get_current_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """Fecha a sessao na hora em que o app sai do player (libera a vaga)."""
    await stop_session(
        db,
        user_id=subscription.user_id,
        session_id=payload.session_id,
    )
    return MessageResponse(message="ok")
