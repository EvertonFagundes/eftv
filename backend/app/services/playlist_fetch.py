# services/playlist_fetch.py - Download da playlist licenciada
"""Baixa a M3U do provedor com fallbacks seguros para o Render.

O provedor usa geo-DNS/CDN: dependendo do resolver, o mesmo dominio entrega a
playlist ou uma pagina padrao do nginx. O Render pode cair no segundo caso.
Este servico tenta, em ordem:

1. a URL original (http ou https);
2. o outro esquema (https quando a URL e http, e vice-versa);
3. os IPs que o DNS do Render devolveu, preservando Host/SNI;
4. o host/porta informado pela API Xtream (``player_api.php``);
5. IPs de resolvers DoH (Cloudflare/Google), preservando Host/SNI;
6. IPs extras configurados em ``IPTV_PLAYLIST_FALLBACK_IPS``.

Nenhuma URL com usuario/senha aparece em log, resposta de erro ou no /health.
O modulo guarda apenas hashes das URLs e rotulos das tentativas.
"""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import logging
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import httpx

from app.config import settings
from app.services.playlist_expiry import build_player_api_url

logger = logging.getLogger(__name__)

HEAD_BYTES = 8 * 1024
FIRST_LINE_CHARS = 80
DOH_CACHE_SECONDS = 600
ROUTE_CACHE_SECONDS = 600

# cache de IPs por host e de rota vencedora por playlist (hash)
_ip_cache: dict[str, tuple[float, list[str]]] = {}
_doh_cache: dict[str, tuple[float, list[str]]] = {}
_route_cache: dict[str, tuple[float, Candidate]] = {}
# Depois de uma falha completa, evita repetir a sequencia lenta em cada
# request. O probe do /health chama fetch_playlist direto e continua testando.
_failure_cache: dict[str, float] = {}
FAILURE_COOLDOWN_SECONDS = 10 * 60


class PlaylistFetchError(ValueError):
    """Falha segura: a mensagem nao contem URL, host ou credenciais."""


@dataclass(frozen=True)
class Candidate:
    """Uma forma de chegar a playlist, sem expor a URL no resultado."""

    label: str
    url: str
    scheme: str
    host_header: str | None = None
    sni_hostname: str | None = None
    ip: str | None = None


@dataclass
class Attempt:
    label: str
    scheme: str
    ip: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    bytes_read: int = 0
    looks_m3u: bool = False
    error: str | None = None
    first_line: str = ""
    server: str | None = None
    cf_ray: str | None = None
    via: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "scheme": self.scheme,
            "ip": self.ip,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "content_length": self.content_length,
            "bytes_read": self.bytes_read,
            "looks_m3u": self.looks_m3u,
            "error": self.error,
            "first_line": self.first_line,
            "server": self.server,
            "cf_ray": self.cf_ray,
            "via": self.via,
            "duration_ms": self.duration_ms,
        }


@dataclass
class FetchResult:
    content: bytes = b""
    strategy: str | None = None
    attempts: list[Attempt] = field(default_factory=list)
    resolved_ips: list[str] = field(default_factory=list)
    truncated: bool = False
    status_code: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return bool(self.content)

    def error_summary(self) -> str:
        """Resumo seguro das tentativas, sem URL/host/credenciais."""
        details: list[str] = []
        for attempt in self.attempts:
            if attempt.error:
                details.append(f"{attempt.label}: {attempt.error}")
            else:
                details.append(
                    f"{attempt.label}: HTTP {attempt.status_code or '?'} "
                    f"({attempt.bytes_read} bytes)"
                )
        return "; ".join(details) or "nenhuma fonte respondeu"


def looks_like_m3u(content: bytes) -> bool:
    """Reconhece M3U pelo cabecalho, sem confiar no Content-Type."""
    start = content[:HEAD_BYTES]
    if start.startswith(b"\xef\xbb\xbf"):
        start = start[3:]
    start = start.lstrip()
    if not start:
        return False
    first = start.splitlines()[0].strip().upper()
    return first.startswith(b"#EXTM3U") or first.startswith(b"#EXTINF")


def safe_first_line(content: bytes) -> str:
    text = content[:FIRST_LINE_CHARS].decode("utf-8", errors="replace")
    text = text.replace("\r", " ").replace("\n", " ")
    printable = "".join(ch if ch.isprintable() else " " for ch in text)
    return printable.strip()[:FIRST_LINE_CHARS]


def url_publica(url: str) -> bool:
    """Bloqueia SSRF: so aceita hosts que resolvem para IPs publicos."""
    host = (urlsplit(url).hostname or "").strip().lower()
    if not host or host in {"localhost"} or host.endswith((".local", ".internal")):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def _public_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.HTTPError):
        return "falha de conexao"
    if isinstance(exc, PlaylistFetchError):
        return str(exc)
    return "erro de rede"


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def recently_failed(url: str) -> bool:
    """True quando a ultima tentativa completa falhou ha pouco."""
    until = _failure_cache.get(_hash_url(url))
    return until is not None and time.monotonic() < until


def mark_ok(url: str) -> None:
    _failure_cache.pop(_hash_url(url), None)


def mark_failure(url: str) -> None:
    _failure_cache[_hash_url(url)] = time.monotonic() + FAILURE_COOLDOWN_SECONDS


def clear_failure_cache() -> None:
    """Limpa o cooldown (testes/consulta manual)."""
    _failure_cache.clear()


def _netloc(host: str, port: int | None, scheme: str) -> str:
    if port and port not in {80, 443}:
        return f"{host}:{port}"
    return host


def _port_from_netloc(netloc: str, scheme: str) -> int | None:
    try:
        parsed = urlsplit(f"{scheme}://{netloc}")
        return parsed.port
    except ValueError:
        return None


def _build_candidate(
    base_url: str,
    *,
    scheme: str,
    netloc: str,
    label: str,
    ip: str | None = None,
    host_header: str | None = None,
    sni_hostname: str | None = None,
) -> Candidate:
    parsed = urlsplit(base_url)
    url = urlunsplit((scheme, netloc, parsed.path or "/", parsed.query, ""))
    return Candidate(
        label=label,
        url=url,
        scheme=scheme,
        host_header=host_header,
        sni_hostname=sni_hostname,
        ip=ip,
    )


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    seen: set[tuple[str, str, str | None, str | None]] = set()
    result: list[Candidate] = []
    for candidate in candidates:
        key = (
            candidate.scheme,
            candidate.url,
            candidate.host_header,
            candidate.sni_hostname,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _direct_candidates(url: str) -> list[Candidate]:
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        return []
    other = "https" if scheme == "http" else "http"
    candidates = [_build_candidate(url, scheme=scheme, netloc=parsed.netloc, label="direto")]

    port = parsed.port
    if port in {80, 443}:
        port = None
    host = parsed.hostname or ""
    candidates.append(
        _build_candidate(
            url,
            scheme=other,
            netloc=_netloc(host, port, other),
            label=f"{other} alternativo",
        )
    )
    return candidates


def _variant_candidates(url: str) -> list[Candidate]:
    """Tenta ``type=m3u``/``m3u_plus`` quando o tipo atual nao entrega M3U."""
    parsed = urlsplit(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    current = next((value for key, value in query if key.lower() == "type"), "").lower()
    if not query:
        return []
    if current == "m3u_plus":
        variants = ["m3u"]
    elif current == "m3u":
        variants = ["m3u_plus"]
    else:
        variants = ["m3u", "m3u_plus"]
    candidates: list[Candidate] = []
    for variant in variants:
        if variant == current:
            continue
        new_query = urlencode(
            [
                (key, variant if key.lower() == "type" else value)
                for key, value in query
            ]
        )
        variant_url = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path or "/", new_query, "")
        )
        candidates.append(
            _build_candidate(
                variant_url,
                scheme=parsed.scheme,
                netloc=parsed.netloc,
                label=f"tipo {variant}",
            )
        )
    return candidates


def _ip_candidates(url: str, ips: list[str], *, label: str) -> list[Candidate]:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    port = parsed.port
    if not host:
        return []
    candidates: list[Candidate] = []
    schemes = [parsed.scheme.lower()]
    other = "https" if parsed.scheme.lower() == "http" else "http"
    if other not in schemes:
        schemes.append(other)
    host_header = parsed.netloc
    for ip in ips:
        if not _public_ip(ip):
            continue
        for scheme in schemes:
            effective_port = port
            if effective_port in {80, 443}:
                effective_port = None
            netloc = _netloc(ip, effective_port, scheme)
            candidates.append(
                _build_candidate(
                    url,
                    scheme=scheme,
                    netloc=netloc,
                    label=f"{label} ({scheme} por IP)",
                    ip=ip,
                    host_header=host_header,
                    sni_hostname=host if scheme == "https" else None,
                )
            )
    return candidates


async def _system_ips(host: str, port: int | None) -> list[str]:
    cached = _ip_cache.get(host)
    now = time.monotonic()
    if cached and now - cached[0] < DOH_CACHE_SECONDS:
        return list(cached[1])

    def resolve() -> list[str]:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError:
            return []
        result: list[str] = []
        for info in infos:
            ip = str(info[4][0])
            if _public_ip(ip) and ip not in result:
                result.append(ip)
        return result

    ips = await asyncio.to_thread(resolve)
    _ip_cache[host] = (now, ips)
    return ips


async def _doh_ips(host: str) -> list[str]:
    cached = _doh_cache.get(host)
    now = time.monotonic()
    if cached and now - cached[0] < DOH_CACHE_SECONDS:
        return list(cached[1])

    providers = (
        ("cloudflare", "https://cloudflare-dns.com/dns-query", {"name": host, "type": "A"}),
        ("google", "https://dns.google/resolve", {"name": host, "type": "A"}),
    )
    found: list[str] = []
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        for _, endpoint, params in providers:
            try:
                response = await client.get(
                    endpoint,
                    params=params,
                    headers={"Accept": "application/dns-json"},
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError):
                continue
            for answer in payload.get("Answer") or []:
                if answer.get("type") != 1:
                    continue
                ip = str(answer.get("data") or "").strip()
                if _public_ip(ip) and ip not in found:
                    found.append(ip)
    _doh_cache[host] = (now, found)
    return found


async def _alternate_api_hosts(
    url: str,
    headers: dict[str, str],
    *,
    transport: httpx.AsyncBaseTransport | None,
) -> tuple[list[Candidate], Attempt | None]:
    """Pergunta ao player_api.php qual host/porta o provedor usa."""
    api_url = build_player_api_url(url)
    if not api_url:
        return [], None

    started = time.monotonic()
    attempt = Attempt(label="api do provedor", scheme=urlsplit(api_url).scheme)
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            transport=transport,
        ) as client:
            response = await client.get(api_url, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:  # noqa: BLE001
        attempt.error = _safe_error(exc)
        attempt.duration_ms = int((time.monotonic() - started) * 1000)
        return [], attempt

    attempt.status_code = response.status_code
    attempt.content_type = response.headers.get("content-type")
    attempt.server = response.headers.get("server")
    attempt.cf_ray = response.headers.get("cf-ray")
    attempt.via = response.headers.get("via")
    attempt.duration_ms = int((time.monotonic() - started) * 1000)

    server = payload.get("server_info") if isinstance(payload, dict) else None
    if not isinstance(server, dict):
        attempt.error = "API sem server_info"
        return [], attempt

    raw_host = str(server.get("url") or server.get("host") or "").strip()
    if "://" in raw_host:
        raw_host = urlsplit(raw_host).hostname or ""
    if not raw_host:
        attempt.error = "API sem host"
        return [], attempt

    original = urlsplit(url)
    if raw_host.lower() == (original.hostname or "").lower():
        attempt.error = "API repete o host original"
        return [], attempt

    ports: list[int] = []
    for key in ("port", "https_port"):
        try:
            value = int(str(server.get(key) or "").strip())
        except ValueError:
            continue
        if value > 0 and value not in ports:
            ports.append(value)
    if not ports:
        ports = [80, 443]

    candidates: list[Candidate] = []
    for port in ports:
        scheme = "https" if port in {443, 8443} else "http"
        netloc = _netloc(raw_host, port, scheme)
        candidates.append(
            _build_candidate(
                url,
                scheme=scheme,
                netloc=netloc,
                label="host alternativo do provedor",
            )
        )
    return candidates, attempt


def _headers_with_host(
    headers: dict[str, str], candidate: Candidate
) -> tuple[dict[str, str], dict[str, str]]:
    request_headers = dict(headers)
    if candidate.host_header:
        request_headers["Host"] = candidate.host_header
    extensions: dict[str, str] = {}
    if candidate.sni_hostname:
        extensions["sni_hostname"] = candidate.sni_hostname
    return request_headers, extensions


async def _read_candidate(
    client: httpx.AsyncClient,
    candidate: Candidate,
    headers: dict[str, str],
    *,
    max_bytes: int,
    probe: bool,
) -> tuple[Attempt, bytes, bool]:
    started = time.monotonic()
    attempt = Attempt(label=candidate.label, scheme=candidate.scheme, ip=candidate.ip)
    request_headers, extensions = _headers_with_host(headers, candidate)
    url = candidate.url
    response: httpx.Response | None = None

    try:
        for _ in range(6):
            request = client.build_request(
                "GET",
                url,
                headers=request_headers,
                extensions=extensions,
            )
            response = await client.send(request, stream=True)
            if response.status_code not in range(300, 400):
                break
            location = response.headers.get("location")
            await response.aclose()
            response = None
            if not location:
                raise PlaylistFetchError("redirecionamento sem Location")
            next_url = urljoin(url, location)
            if not next_url.startswith(("http://", "https://")) or not url_publica(next_url):
                raise PlaylistFetchError("redirecionamento inseguro")
            # O destino do redirect nao herda Host/SNI do IP: resolve normal.
            url = next_url
            request_headers = dict(headers)
            extensions = {}
        if response is None:
            raise PlaylistFetchError("redirecionamento sem resposta")

        attempt.status_code = response.status_code
        attempt.content_type = response.headers.get("content-type")
        attempt.server = response.headers.get("server")
        attempt.cf_ray = response.headers.get("cf-ray")
        attempt.via = response.headers.get("via")
        raw_length = response.headers.get("content-length")
        if raw_length and raw_length.isdigit():
            attempt.content_length = int(raw_length)
        if not 200 <= response.status_code < 300:
            attempt.error = f"HTTP {response.status_code}"
            return attempt, b"", False
        if (
            attempt.content_length is not None
            and attempt.content_length > max_bytes
            and not probe
        ):
            attempt.error = "playlist muito grande"
            return attempt, b"", False

        buffer = bytearray()
        looks_decided = False
        looks = False
        truncated = False
        async for chunk in response.aiter_bytes():
            buffer.extend(chunk)
            if not looks_decided and len(buffer) >= HEAD_BYTES:
                looks = looks_like_m3u(buffer)
                looks_decided = True
                attempt.first_line = safe_first_line(buffer)
                if not looks:
                    break
            if len(buffer) >= max_bytes:
                if probe:
                    del buffer[max_bytes:]
                    truncated = True
                else:
                    attempt.error = "playlist muito grande"
                    return attempt, b"", False
                break

        if not looks_decided:
            looks = looks_like_m3u(buffer)
            attempt.first_line = safe_first_line(buffer)
        attempt.bytes_read = len(buffer)
        attempt.looks_m3u = looks
        if not looks:
            attempt.error = "resposta nao e uma playlist M3U"
            return attempt, b"", False
        if not attempt.error:
            return attempt, bytes(buffer), truncated
        return attempt, b"", False
    except Exception as exc:  # noqa: BLE001
        attempt.error = _safe_error(exc)
        return attempt, b"", False
    finally:
        if response is not None:
            await response.aclose()
        attempt.duration_ms = int((time.monotonic() - started) * 1000)


async def fetch_playlist(
    url: str,
    headers: dict[str, str],
    *,
    max_bytes: int | None = None,
    probe_bytes: int | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    allow_helpers: bool = True,
) -> FetchResult:
    """Baixa a playlist, tentando rotas alternativas ate achar uma M3U."""
    source = (url or "").strip()
    limit = max_bytes or settings.IPTV_PLAYLIST_MAX_BYTES
    probe_limit = probe_bytes or 0
    effective_limit = probe_limit or limit
    started = time.monotonic()
    result = FetchResult()

    if not source.startswith(("http://", "https://")):
        result.attempts.append(
            Attempt(label="configuracao", scheme="", error="URL invalida")
        )
        return result
    if not url_publica(source):
        result.attempts.append(
            Attempt(label="configuracao", scheme="", error="destino nao permitido")
        )
        return result

    parsed = urlsplit(source)
    host = parsed.hostname or ""
    port = parsed.port
    key = _hash_url(source)

    candidates: list[Candidate] = []
    cached = _route_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < ROUTE_CACHE_SECONDS:
        candidates.append(cached[1])
    candidates.extend(_direct_candidates(source))
    candidates.extend(_variant_candidates(source))
    candidates = _dedupe(candidates)

    timeout = httpx.Timeout(
        connect=settings.IPTV_PLAYLIST_CONNECT_TIMEOUT_SECONDS,
        read=settings.IPTV_PLAYLIST_READ_TIMEOUT_SECONDS,
        write=30.0,
        pool=30.0,
    )

    async def try_candidates(
        client: httpx.AsyncClient,
        items: list[Candidate],
    ) -> FetchResult | None:
        for candidate in items:
            attempt, content, truncated = await _read_candidate(
                client,
                candidate,
                headers,
                max_bytes=effective_limit,
                probe=bool(probe_limit),
            )
            result.attempts.append(attempt)
            if content:
                result.content = content
                result.strategy = candidate.label
                result.truncated = truncated
                result.status_code = attempt.status_code
                result.content_type = attempt.content_type
                result.content_length = attempt.content_length
                _route_cache[key] = (time.monotonic(), candidate)
                mark_ok(source)
                logger.info(
                    "Playlist OK via %s (%s bytes, total=%s)",
                    candidate.label,
                    len(content),
                    attempt.content_length,
                )
                return result
        return None

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
        ) as client:
            found = await try_candidates(client, candidates)
            if found:
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return found

            if not allow_helpers:
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return result

            system_ips = await _system_ips(host, port)
            _append_unique(result.resolved_ips, system_ips)
            found = await try_candidates(client, _ip_candidates(source, system_ips, label="DNS do Render"))
            if found:
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return found

            alt_candidates, api_attempt = await _alternate_api_hosts(
                source, headers, transport=transport
            )
            if api_attempt:
                result.attempts.append(api_attempt)
            found = await try_candidates(client, _dedupe(alt_candidates))
            if found:
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return found

            doh_ips = await _doh_ips(host)
            _append_unique(result.resolved_ips, doh_ips)
            found = await try_candidates(client, _ip_candidates(source, doh_ips, label="DoH"))
            if found:
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return found

            fallback_ips = [
                item.strip()
                for item in (settings.IPTV_PLAYLIST_FALLBACK_IPS or "").split(",")
                if item.strip()
            ]
            _append_unique(result.resolved_ips, [ip for ip in fallback_ips if _public_ip(ip)])
            found = await try_candidates(
                client,
                _ip_candidates(source, fallback_ips, label="IP extra"),
            )
            if found:
                result.duration_ms = int((time.monotonic() - started) * 1000)
                return found
    except Exception as exc:  # noqa: BLE001
        result.attempts.append(Attempt(label="geral", scheme="", error=_safe_error(exc)))

    mark_failure(source)
    result.duration_ms = int((time.monotonic() - started) * 1000)
    return result


def _append_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value not in target:
            target.append(value)


def playlist_headers() -> dict[str, str]:
    headers = {
        "User-Agent": settings.IPTV_PLAYLIST_USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    }
    if settings.IPTV_PLAYLIST_REFERER:
        headers["Referer"] = settings.IPTV_PLAYLIST_REFERER
    return headers


def _as_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _configured_meta(url: str) -> dict[str, object]:
    """Fingerprint seguro da URL configurada, sem host/usuario/senha."""
    parsed = urlsplit(url)
    query_keys = sorted({key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)})
    return {
        "scheme": parsed.scheme,
        "port": parsed.port,
        "xtream_get": "get.php" in (parsed.path or "").lower(),
        "query_keys": query_keys,
        "host_fingerprint": hashlib.sha256((parsed.hostname or "").encode()).hexdigest()[:12],
        "url_fingerprint": _hash_url(url)[:12],
    }


async def probe_account(
    url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    """Consulta ``player_api.php`` por rotas alternativas, sem expor a conta.

    Serve para separar conta vencida/recusada de bloqueio de rede: devolve
    apenas ``auth``, ``status``, limites e os cabecalhos do servidor.
    """
    api_url = build_player_api_url(url)
    if not api_url:
        return {"state": "not_xtream"}

    parsed = urlsplit(api_url)
    host = parsed.hostname or ""
    attempts: list[Attempt] = []
    candidates = _direct_candidates(api_url)
    system_ips = await _system_ips(host, parsed.port)
    candidates.extend(_ip_candidates(api_url, system_ips, label="DNS do Render"))
    doh_ips = await _doh_ips(host)
    candidates.extend(_ip_candidates(api_url, doh_ips, label="DoH"))
    fallback_ips = [
        item.strip()
        for item in (settings.IPTV_PLAYLIST_FALLBACK_IPS or "").split(",")
        if item.strip()
    ]
    candidates.extend(_ip_candidates(api_url, fallback_ips, label="IP extra"))
    candidates = _dedupe(candidates)

    headers = {
        "User-Agent": settings.IPTV_PLAYLIST_USER_AGENT,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    }
    if settings.IPTV_PLAYLIST_REFERER:
        headers["Referer"] = settings.IPTV_PLAYLIST_REFERER

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=15.0),
        follow_redirects=True,
        transport=transport,
    ) as client:
        for candidate in candidates:
            started = time.monotonic()
            attempt = Attempt(
                label=candidate.label,
                scheme=candidate.scheme,
                ip=candidate.ip,
            )
            request_headers, extensions = _headers_with_host(headers, candidate)
            try:
                response = await client.get(
                    candidate.url,
                    headers=request_headers,
                    extensions=extensions,
                )
            except Exception as exc:  # noqa: BLE001
                attempt.error = _safe_error(exc)
                attempt.duration_ms = int((time.monotonic() - started) * 1000)
                attempts.append(attempt)
                continue

            attempt.status_code = response.status_code
            attempt.content_type = response.headers.get("content-type")
            attempt.server = response.headers.get("server")
            attempt.cf_ray = response.headers.get("cf-ray")
            attempt.via = response.headers.get("via")
            attempt.duration_ms = int((time.monotonic() - started) * 1000)
            attempts.append(attempt)

            if not 200 <= response.status_code < 300:
                attempt.error = f"HTTP {response.status_code}"
                continue
            try:
                payload = response.json()
            except ValueError:
                attempt.error = "resposta nao e JSON"
                continue
            info = payload.get("user_info") if isinstance(payload, dict) else None
            if not isinstance(info, dict):
                attempt.error = "JSON sem user_info"
                continue

            return {
                "state": "ok",
                "auth": info.get("auth"),
                "status": info.get("status"),
                "max_connections": _as_int(info.get("max_connections")),
                "active_cons": _as_int(info.get("active_cons")),
                "is_trial": info.get("is_trial"),
                "server": attempt.server,
                "cf_ray": attempt.cf_ray,
                "attempts": [item.to_dict() for item in attempts],
            }

    return {
        "state": "error",
        "attempts": [item.to_dict() for item in attempts],
    }


async def probe_playlist(
    url: str | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    """Diagnostico seguro para o /health: cabecalho + 2 MiB, sem URL."""
    source = (url if url is not None else settings.IPTV_PLAYLIST_URL or "").strip()
    checked_at = datetime.now(UTC).isoformat()
    if not source:
        return {"state": "not_configured", "checked_at": checked_at}

    result = await fetch_playlist(
        source,
        playlist_headers(),
        max_bytes=settings.IPTV_PLAYLIST_PROBE_BYTES,
        probe_bytes=settings.IPTV_PLAYLIST_PROBE_BYTES,
        transport=transport,
        allow_helpers=True,
    )
    first_line = ""
    if result.content:
        first_line = safe_first_line(result.content)
    elif result.attempts:
        first_line = result.attempts[0].first_line
    try:
        account = await probe_account(source, transport=transport)
    except Exception as exc:  # noqa: BLE001
        account = {"state": "error", "error": _safe_error(exc)}
    return {
        "state": "ok" if result.ok else "error",
        "checked_at": checked_at,
        "ok": result.ok,
        "configured": _configured_meta(source),
        "source": result.strategy,
        "status_code": result.status_code,
        "content_type": result.content_type,
        "content_length": result.content_length,
        "bytes_read": len(result.content),
        "truncated": result.truncated,
        "first_line": first_line,
        "resolved_ips": result.resolved_ips,
        "attempts": [attempt.to_dict() for attempt in result.attempts],
        "account": account,
        "duration_ms": result.duration_ms,
    }
