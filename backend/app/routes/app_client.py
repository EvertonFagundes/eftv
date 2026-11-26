# routes/app_client.py - Servicos do proprio aplicativo
#
# Duas necessidades de produto que nao existiam:
#  - o app distribuido por APK precisa saber que existe versao nova;
#  - sem telemetria, todo problema chegava por WhatsApp. O app envia o
#    travamento para ca e o painel admin lista.
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.client_error import ClientError
from app.security.dependencies import client_ip
from app.services import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app", tags=["App"])

MAX_MESSAGE = 500
MAX_STACKTRACE = 8000


class AppVersionResponse(BaseModel):
    version_code: int
    version_name: str
    apk_url: str
    notes: str
    mandatory: bool
    # False quando o servidor ainda nao tem APK publicado: o app nao pergunta
    # nada ao usuario nesse caso.
    update_available_from: bool


class CrashReportRequest(BaseModel):
    message: str = Field(default="", max_length=MAX_MESSAGE)
    stacktrace: str = Field(default="", max_length=MAX_STACKTRACE)
    app_version: str = Field(default="", max_length=32)
    device: str = Field(default="", max_length=120)
    android: str = Field(default="", max_length=32)


@router.get("/version", response_model=AppVersionResponse)
async def app_version():
    """Ultima versao do app (consulta feita na abertura, uma vez por dia)."""
    # O painel do Render aceita colar o valor com quebra de linha/espaços; sem
    # o strip o app recebia uma URL de APK inválida ("...apk\n").
    apk_url = settings.APP_APK_URL.strip()
    configured = bool(apk_url and settings.APP_LATEST_VERSION_CODE > 0)
    return AppVersionResponse(
        version_code=settings.APP_LATEST_VERSION_CODE,
        version_name=settings.APP_LATEST_VERSION_NAME.strip(),
        apk_url=apk_url,
        notes=settings.APP_UPDATE_NOTES.strip(),
        mandatory=settings.APP_UPDATE_MANDATORY,
        update_available_from=configured,
    )


@router.get("/tv", include_in_schema=False)
async def apk_download():
    """URL curta para instalar o APK na TV.

    A TV nao tem como abrir uma pagina bonita com botao: apps de download
    (Downloader do Fire TV, navegador do box) precisam de um link que entregue
    o arquivo. Por isso este endpoint responde com 302 direto para o APK, em
    vez de HTML - HTML faria a TV salvar uma pagina em vez do app.

    Tambem montado em `/tv` (sem prefixo) para ser digitavel no controle.
    """
    url = settings.APP_APK_URL.strip()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="APK ainda nao publicado",
        )
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


@router.post("/crashes", status_code=status.HTTP_202_ACCEPTED)
async def report_crash(
    payload: CrashReportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Recebe o relato de travamento/erro do app.

    Endpoint publico de proposito: o app pode quebrar antes do login. O volume
    e limitado pelo tamanho dos campos, pela janela por IP e o conteudo vai
    direto para o log.
    """
    if not settings.CLIENT_ERRORS_ENABLED:
        return {"accepted": False}

    # Sem isso o endpoint publico aceitava spam infinito no banco. O balde e
    # por aparelho quando o app manda o header (o proxy do Render entrega o
    # mesmo IP para todos); sem header, cai no IP.
    reporter = (request.headers.get("x-device-id") or "").strip() or client_ip(request)
    await rate_limit.hit(
        db,
        key=rate_limit.scoped_key("crashes", reporter),
        limit=settings.RATE_LIMIT_CRASHES_PER_MINUTE,
        window_seconds=60,
        detail="Muitos relatos de erro. Tente novamente em instantes.",
    )

    error = ClientError(
        app_version=payload.app_version,
        device=payload.device,
        android=payload.android,
        message=(payload.message or "").strip()[:MAX_MESSAGE],
        stacktrace=(payload.stacktrace or "").strip()[:MAX_STACKTRACE],
        created_at=datetime.now(UTC),
    )
    db.add(error)
    await db.commit()

    logger.warning(
        "Erro do app %s (%s, Android %s): %s | %s",
        payload.app_version or "?",
        payload.device or "?",
        payload.android or "?",
        payload.message[:200],
        (payload.stacktrace.splitlines() or [""])[0][:200],
    )
    return {"accepted": True}
