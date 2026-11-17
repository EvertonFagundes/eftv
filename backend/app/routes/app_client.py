# routes/app_client.py - Servicos do proprio aplicativo
#
# Duas necessidades de produto que nao existiam:
#  - o app distribuido por APK precisa saber que existe versao nova;
#  - sem telemetria, todo problema chegava por WhatsApp. O app envia o
#    travamento para ca e o painel admin lista.
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.client_error import ClientError

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
    configured = bool(settings.APP_APK_URL and settings.APP_LATEST_VERSION_CODE > 0)
    return AppVersionResponse(
        version_code=settings.APP_LATEST_VERSION_CODE,
        version_name=settings.APP_LATEST_VERSION_NAME,
        apk_url=settings.APP_APK_URL,
        notes=settings.APP_UPDATE_NOTES,
        mandatory=settings.APP_UPDATE_MANDATORY,
        update_available_from=configured,
    )


@router.post("/crashes", status_code=status.HTTP_202_ACCEPTED)
async def report_crash(
    payload: CrashReportRequest,
    db: AsyncSession = Depends(get_db),
):
    """Recebe o relato de travamento/erro do app.

    Endpoint publico de proposito: o app pode quebrar antes do login. O volume
    e limitado pelo tamanho dos campos e o conteudo vai direto para o log.
    """
    if not settings.CLIENT_ERRORS_ENABLED:
        return {"accepted": False}

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
