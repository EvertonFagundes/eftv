# security/middleware.py - Limites e cabecalhos HTTP de defesa
"""Middlewares de endurecimento que nao dependem do framework de rotas.

O FastAPI nao limita o tamanho do corpo por padrao: um POST com centenas de
megabytes e lido inteiro antes de qualquer validacao. Tambem nao envia os
cabecalhos basicos de seguranca. Os dois middlewares abaixo cobrem isso sem
depender de configuracao do proxy.
"""

from collections.abc import Awaitable, Callable

Scope = dict
Message = dict
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]

_413_BODY = b'{"detail":"Corpo da requisicao muito grande"}'

_SECURITY_HEADERS = (
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("referrer-policy", "no-referrer"),
    ("permissions-policy", "camera=(), microphone=(), geolocation=()"),
    ("cross-origin-opener-policy", "same-origin"),
    ("x-permitted-cross-domain-policies", "none"),
)


class BodyTooLargeError(Exception):
    """Sinaliza que o corpo passou do limite durante a leitura em streaming."""


async def _send_too_large(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(_413_BODY)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _413_BODY})


class BodySizeLimitMiddleware:
    """Recusa corpos maiores que ``max_bytes`` (Content-Length ou streaming).

    O Content-Length e checado antes de ler qualquer byte. Quando o cliente
    usa chunked (sem Content-Length), a leitura e contada e interrompida no
    limite.
    """

    def __init__(
        self,
        app,
        max_bytes: int = 1_048_576,
        large_paths: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.max_bytes = int(max_bytes)
        # Rotas que precisam de um limite maior (upload do cache da playlist).
        self.large_paths = {
            path.rstrip("/"): int(limit) for path, limit in (large_paths or {}).items()
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", "")).rstrip("/")
        limit = self.large_paths.get(path, self.max_bytes)
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        declared = headers.get("content-length")
        if declared:
            try:
                if int(declared) > limit:
                    await _send_too_large(send)
                    return
            except ValueError:
                # Header invalido: deixa o servidor HTTP decidir; o contador
                # de streaming abaixo ainda protege o processo.
                pass

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLargeError
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except BodyTooLargeError:
            if response_started:
                raise
            await _send_too_large(send)


class SecurityHeadersMiddleware:
    """Adiciona cabecalhos de seguranca em toda resposta HTTP.

    O HSTS so vai quando a conexao e HTTPS (direto ou via proxy), para nao
    ensinar o navegador a forcar HTTPS em um ambiente local HTTP.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        add_csp = path not in {"/docs", "/redoc"}

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw = list(message.get("headers", []))
                present = {key.lower() for key, _ in raw}

                for key, value in _SECURITY_HEADERS:
                    encoded = key.encode("latin-1")
                    if encoded not in present:
                        raw.append((encoded, value.encode("latin-1")))
                if add_csp and b"content-security-policy" not in present:
                    raw.append(
                        (
                            b"content-security-policy",
                            b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                        )
                    )

                request_headers = {
                    key.decode("latin-1").lower(): value.decode("latin-1")
                    for key, value in scope.get("headers", [])
                }
                forwarded = request_headers.get("x-forwarded-proto", "").split(",")[0].strip()
                if (
                    scope.get("scheme") == "https" or forwarded == "https"
                ) and b"strict-transport-security" not in present:
                    raw.append(
                        (
                            b"strict-transport-security",
                            b"max-age=31536000; includeSubDomains",
                        )
                    )

                message["headers"] = raw
            await send(message)

        await self.app(scope, receive, send_with_headers)
