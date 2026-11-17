# services/playlist_expiry.py - Vencimento da playlist licenciada
"""Descobre quando a playlist do provedor vence.

A lista ``.m3u`` em si nao carrega validade: ela e so uma lista de canais. A
data vive na conta do provedor. Quando o link e do tipo Xtream Codes
(``get.php?username=...&password=...``) o mesmo servidor expoe
``player_api.php`` com ``user_info.exp_date``, ``status`` e
``max_connections`` -- e essa a fonte confiavel.

Se a API de conta nao responder, o servico tenta ler o proprio ``.m3u``
procurando textos como "VENCIMENTO 20/12/2026". Serve como ultimo recurso: a
maioria dos provedores nao publica a data no arquivo.

Nada aqui devolve usuario/senha: o resultado expoe apenas o host do provedor.
"""

from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# A conta do provedor muda no maximo algumas vezes por dia; 6 h evita bater na
# API a cada abertura do painel e ainda acusa renovacao no mesmo dia.
DEFAULT_CACHE_SECONDS = 6 * 60 * 60
# Falha de rede nao pode virar cache de 6 h: em 5 min tenta de novo.
FAILURE_CACHE_SECONDS = 5 * 60
# O .m3u pode ter milhares de canais; a data, se existir, esta no cabecalho.
MAX_PLAYLIST_BYTES = 2 * 1024 * 1024

_EXPIRY_PATTERN = re.compile(
    r"(?:vencimento|venc\.?|expira(?:cao|ção)?|expira\w*|validade|"
    r"v[aá]lido\s+(?:at[eé]|ate))\D{0,30}"
    r"(\d{2}[/-]\d{2}[/-]\d{4}(?:\s+\d{2}:\d{2}(?::\d{2})?)?|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)

_DATE_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)

# playlist_url -> (expira_em_monotonic, resultado)
_cache: dict[str, tuple[float, PlaylistExpiry]] = {}


@dataclass(frozen=True)
class PlaylistExpiry:
    """Resultado de uma consulta de vencimento."""

    checked_at: datetime
    expires_at: datetime | None = None
    status: str | None = None
    max_connections: int | None = None
    is_trial: bool | None = None
    # player_api | m3u | unavailable
    source: str = "unavailable"
    error: str | None = None
    provider_host: str | None = None
    from_cache: bool = False

    @property
    def days_remaining(self) -> int | None:
        if self.expires_at is None:
            return None
        seconds = (self.expires_at - self.checked_at).total_seconds()
        if seconds < 0:
            return -1
        return int(seconds // 86400)

    @property
    def expired(self) -> bool | None:
        if self.expires_at is None:
            return None
        return self.expires_at <= self.checked_at

    @property
    def active(self) -> bool | None:
        """Conta utilizavel agora, juntando o status do provedor e a data."""
        status = (self.status or "").strip().lower()
        if status in {"expired", "banned", "disabled", "inactive"}:
            return False
        if self.expired:
            return False
        if self.status is None and self.expires_at is None:
            return None
        return True

    def to_dict(self) -> dict[str, object]:
        return {
            "checked_at": self.checked_at,
            "expires_at": self.expires_at,
            "days_remaining": self.days_remaining,
            "expired": self.expired,
            "active": self.active,
            "status": self.status,
            "max_connections": self.max_connections,
            "is_trial": self.is_trial,
            "source": self.source,
            "provider_host": self.provider_host,
            "error": self.error,
            "from_cache": self.from_cache,
        }


def clear_cache() -> None:
    """Limpa o cache em memoria (testes e consulta manual)."""
    _cache.clear()


def build_player_api_url(playlist_url: str) -> str | None:
    """Troca ``get.php`` por ``player_api.php`` mantendo usuario e senha.

    Devolve ``None`` quando o link nao tem cara de Xtream Codes (sem
    ``username`` e ``password``), porque nesse caso a API de conta nao existe.
    """
    parsed = urlparse((playlist_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    params = parse_qs(parsed.query, keep_blank_values=True)
    username = (params.get("username") or [""])[0].strip()
    password = (params.get("password") or [""])[0].strip()
    if not username or not password:
        return None

    path = parsed.path or "/"
    if re.search(r"get\.php", path, flags=re.IGNORECASE):
        path = re.sub(r"get\.php", "player_api.php", path, flags=re.IGNORECASE)
    else:
        path = path.rstrip("/") + "/player_api.php"

    # ``type=m3u_plus`` e do download da lista, nao da API de conta.
    query = urlencode(
        [
            (key, value)
            for key, values in params.items()
            if key.lower() != "type"
            for value in values
        ]
    )
    return urlunparse((parsed.scheme, parsed.netloc, path, "", query, ""))


def parse_expiry(value: object) -> datetime | None:
    """Converte ``exp_date``/texto de vencimento em ``datetime`` UTC.

    Aceita Unix em segundos (formato do Xtream), Unix em milissegundos,
    ``dd/mm/aaaa`` e ISO. Valores vazios, ``null``, ``0`` e ``-1`` significam
    "sem prazo" e viram ``None``.
    """
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int | float):
        return _from_unix(float(value))

    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "nan", "0", "-1", ""}:
        return None

    if re.fullmatch(r"\d{9,14}", text):
        return _from_unix(float(text))

    iso = text.replace("Z", "+00:00")
    try:
        parsed_iso = datetime.fromisoformat(iso)
    except ValueError:
        pass
    else:
        return _ensure_utc(parsed_iso)

    for fmt in _DATE_FORMATS:
        try:
            return _ensure_utc(datetime.strptime(text, fmt))
        except ValueError:
            continue
    return None


def extract_m3u_expiry(text: str) -> datetime | None:
    """Procura "vencimento/expira/valido ate <data>" dentro do .m3u."""
    match = _EXPIRY_PATTERN.search(text or "")
    if not match:
        return None
    return parse_expiry(match.group(1))


async def fetch_account_info(
    player_api_url: str,
    *,
    user_agent: str | None,
    referer: str | None,
    timeout: float,
) -> dict:
    """GET no ``player_api.php`` e devolve o JSON bruto."""
    headers = _headers(user_agent, referer)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        response = await client.get(player_api_url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("resposta da API de conta nao e um objeto JSON")
    return payload


async def fetch_playlist_text(
    playlist_url: str,
    *,
    user_agent: str | None,
    referer: str | None,
    timeout: float,
) -> str:
    """Baixa o inicio do .m3u (limite de tamanho) para procurar a data."""
    headers = _headers(user_agent, referer)
    chunks = bytearray()
    async with (
        httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client,
        client.stream("GET", playlist_url, headers=headers) as response,
    ):
        response.raise_for_status()
        async for chunk in response.aiter_bytes():
            chunks.extend(chunk)
            if len(chunks) >= MAX_PLAYLIST_BYTES:
                break
    return chunks.decode("utf-8", errors="replace")


async def check_playlist_expiry(
    playlist_url: str,
    *,
    user_agent: str | None = None,
    referer: str | None = None,
    force: bool = False,
    now: datetime | None = None,
) -> PlaylistExpiry:
    """Consulta o vencimento, usando cache de ~6 h por URL."""
    url = (playlist_url or "").strip()
    if not url:
        return PlaylistExpiry(
            checked_at=now or datetime.now(UTC),
            error="Playlist nao configurada no servidor",
        )

    cache_key = url
    cached = _cache.get(cache_key)
    if cached is not None and not force:
        expires_monotonic, result = cached
        if time.monotonic() < expires_monotonic:
            return replace(result, from_cache=True)

    checked_at = now or datetime.now(UTC)
    host = urlparse(url).hostname
    timeout = max(1.0, float(settings.PLAYLIST_EXPIRY_TIMEOUT_SECONDS))

    result = await _query_provider(
        url,
        checked_at=checked_at,
        user_agent=user_agent or settings.IPTV_PLAYLIST_USER_AGENT,
        referer=referer if referer is not None else settings.IPTV_PLAYLIST_REFERER,
        timeout=timeout,
        provider_host=host,
    )

    ttl = (
        max(1, int(settings.PLAYLIST_EXPIRY_CACHE_SECONDS))
        if result.source != "unavailable"
        else min(FAILURE_CACHE_SECONDS, max(1, int(settings.PLAYLIST_EXPIRY_CACHE_SECONDS)))
    )
    _cache[cache_key] = (time.monotonic() + ttl, result)
    if result.source == "unavailable":
        logger.warning("Vencimento da playlist indisponivel: %s", result.error)
    else:
        logger.info(
            "Vencimento da playlist (%s): %s, status=%s",
            result.source,
            result.expires_at.isoformat() if result.expires_at else "sem data",
            result.status,
        )
    return result


async def _query_provider(
    url: str,
    *,
    checked_at: datetime,
    user_agent: str | None,
    referer: str | None,
    timeout: float,
    provider_host: str | None,
) -> PlaylistExpiry:
    """Tenta a API de conta; se falhar, tenta o arquivo .m3u."""
    api_error: str | None = None
    player_api_url = build_player_api_url(url)

    if player_api_url:
        try:
            payload = await fetch_account_info(
                player_api_url,
                user_agent=user_agent,
                referer=referer,
                timeout=timeout,
            )
            info = payload.get("user_info")
            if isinstance(info, dict):
                auth = info.get("auth")
                if auth in {0, "0", False}:
                    api_error = "O provedor recusou usuario/senha da playlist"
                else:
                    return PlaylistExpiry(
                        checked_at=checked_at,
                        expires_at=parse_expiry(info.get("exp_date")),
                        status=_text_or_none(info.get("status")),
                        max_connections=_int_or_none(info.get("max_connections")),
                        is_trial=_bool_or_none(info.get("is_trial")),
                        source="player_api",
                        provider_host=provider_host,
                    )
            else:
                api_error = "A API de conta nao trouxe user_info"
        except Exception as exc:  # noqa: BLE001 - provedor externo pode falhar de tudo
            api_error = _friendly_error(exc)
    else:
        api_error = "Link da playlist nao parece Xtream Codes (sem usuario/senha)"

    # Ultimo recurso: a data as vezes esta publicada como um canal do .m3u.
    try:
        text = await fetch_playlist_text(
            url,
            user_agent=user_agent,
            referer=referer,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        archive_error = _friendly_error(exc)
        return PlaylistExpiry(
            checked_at=checked_at,
            source="unavailable",
            error=f"{api_error or 'API de conta indisponivel'}; {archive_error}",
            provider_host=provider_host,
        )

    expires_at = extract_m3u_expiry(text)
    if expires_at is None:
        return PlaylistExpiry(
            checked_at=checked_at,
            source="unavailable",
            error=f"{api_error or 'API de conta indisponivel'}; o .m3u nao traz data de vencimento",
            provider_host=provider_host,
        )

    return PlaylistExpiry(
        checked_at=checked_at,
        expires_at=expires_at,
        source="m3u",
        error=api_error,
        provider_host=provider_host,
    )


def _headers(user_agent: str | None, referer: str | None) -> dict[str, str]:
    headers = {"User-Agent": user_agent or "VLC/3.0.20 LibVLC/3.0.20"}
    if referer:
        headers["Referer"] = referer
    return headers


def _from_unix(value: float) -> datetime | None:
    if not math.isfinite(value) or value <= 0:
        return None
    # Provedores as vezes mandam milissegundos (13 digitos).
    if value > 10_000_000_000:
        value /= 1000
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: object) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "sim"}:
        return True
    if text in {"0", "false", "no", "nao", "não"}:
        return False
    return None


def _friendly_error(exc: Exception) -> str:
    """Mensagem sem URL/credenciais para poder ir ao painel e ao log."""
    if isinstance(exc, httpx.TimeoutException):
        return "Provedor nao respondeu a tempo"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"Provedor respondeu HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.HTTPError):
        return "Nao foi possivel falar com o provedor"
    if isinstance(exc, ValueError):
        return "Resposta inesperada do provedor"
    return "Falha ao consultar o provedor"
