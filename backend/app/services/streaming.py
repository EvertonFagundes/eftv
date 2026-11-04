# services/streaming.py - Geração de URLs de stream assinadas
from datetime import UTC

from app.config import settings


async def generate_stream_url(original_url: str, token: str) -> str:
    """
    Gera URL final de stream com token de autorização.
    A implementação varia conforme o provedor:
    - Cloudflare Stream: adiciona token como query param ou header
    - Mux: signed URLs com JWT
    - Custom: token no header Authorization
    """
    provider = settings.STREAM_PROVIDER.lower()

    if provider == "cloudflare":
        return _cloudflare_stream_url(original_url, token)
    elif provider == "mux":
        return _mux_stream_url(original_url, token)
    else:
        # Custom: retorna URL original, token vai no header Authorization
        return original_url


def _cloudflare_stream_url(original_url: str, token: str) -> str:
    """
    Cloudflare Stream aceita token via:
    1. Query parameter: ?token=<jwt>
    2. Header: Authorization: Bearer <jwt>
    3. Cookie: cf_stream_token=<jwt>

    Para player web (hls.js), query param é mais simples.
    """
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    parsed = urlparse(original_url)
    query_params = parse_qs(parsed.query)
    query_params["token"] = [token]
    new_query = urlencode(query_params, doseq=True)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def _mux_stream_url(original_url: str, token: str) -> str:
    """
    Mux usa signed URLs - o token é incorporado na própria URL
    gerada pelo Mux. Aqui assumimos que original_url já é signed
    ou adicionamos o token como query param.
    """
    from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

    parsed = urlparse(original_url)
    query_params = parse_qs(parsed.query)
    query_params["token"] = [token]
    new_query = urlencode(query_params, doseq=True)

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )


def create_cloudflare_signed_token(
    video_uid: str,
    expiration_seconds: int = 900,
    allowed_origins: list[str] | None = None,
    require_signed_urls: bool = True,
) -> str:
    """
    Cria token assinado para Cloudflare Stream usando Workers/Token Auth.
    Requer configuração no dashboard Cloudflare Stream > Token Auth.
    """
    from datetime import datetime, timedelta

    import jwt

    now = datetime.now(UTC)
    exp = now + timedelta(seconds=expiration_seconds)

    claims: dict[str, object] = {
        "kid": settings.CLOUDFLARE_ACCOUNT_ID,  # Key ID configurado no Cloudflare
        "video": video_uid,
        "exp": int(exp.timestamp()),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
    }

    if allowed_origins:
        claims["allowed_origins"] = allowed_origins

    # A chave privada deve estar configurada no Cloudflare
    # Aqui apenas exemplo - implementação real usa chave Ed25519
    private_key = settings.CLOUDFLARE_API_TOKEN or ""
    if not private_key:
        raise RuntimeError("CLOUDFLARE_API_TOKEN nao configurado")

    return str(jwt.encode(claims, private_key, algorithm="EdDSA"))


async def upload_to_cloudflare_stream(
    video_file_path: str,
    title: str,
    meta: dict | None = None,
) -> dict:
    """
    Upload de vídeo para Cloudflare Stream via API.
    Retorna dict com uid, playback_url, etc.
    """
    import httpx

    if not settings.CLOUDFLARE_ACCOUNT_ID or not settings.CLOUDFLARE_API_TOKEN:
        raise RuntimeError("Credenciais Cloudflare não configuradas")

    url = f"https://api.cloudflare.com/client/v4/accounts/{settings.CLOUDFLARE_ACCOUNT_ID}/stream"

    headers = {
        "Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}",
    }

    with open(video_file_path, "rb") as f:
        files = {"file": (video_file_path, f, "video/mp4")}
        data = {"meta": {"name": title}}
        if meta:
            data["meta"].update(meta)

        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, headers=headers, files=files, data=data)

    if response.status_code >= 400:
        raise RuntimeError(f"Erro no upload Cloudflare: {response.status_code} - {response.text}")

    return dict(response.json()["result"])
