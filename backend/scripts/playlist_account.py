"""Consulta os dados da conta na playlist licenciada (Xtream Codes).

Le a IPTV_PLAYLIST_URL do ambiente (ou de backend/.env) e chama o
`player_api.php` do mesmo servidor para descobrir, entre outras coisas,
quantas conexoes simultaneas o plano permite e quantas estao em uso.

Uso:

    cd backend
    python scripts/playlist_account.py

Nunca imprime usuario nem senha. Nao abre stream nenhum: e uma chamada de
leitura, do mesmo tipo que o app ja faz para listar o catalogo.
"""

# ruff: noqa: T201 - script de linha de comando: a saida e o proprio relatorio

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"


def load_env() -> None:
    """Carrega backend/.env sem sobrescrever variaveis ja definidas."""
    if not ENV_FILE.exists():
        return

    from dotenv import dotenv_values

    for key, value in dotenv_values(ENV_FILE).items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def build_api_url(playlist_url: str) -> tuple[str, str]:
    """Deriva a URL do player_api.php e devolve o usuario da conta."""
    parsed = urlparse(playlist_url)
    query = parse_qs(parsed.query)

    username = (query.get("username") or [""])[0]
    password = (query.get("password") or [""])[0]

    if not username or not password:
        raise SystemExit(
            "IPTV_PLAYLIST_URL nao tem username/password na query. "
            "Este script so funciona com playlist Xtream Codes."
        )

    base = f"{parsed.scheme}://{parsed.netloc}/player_api.php"
    api = f"{base}?username={username}&password={password}"
    return api, username


def mask(value: str) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    return value[:1] + "*" * (len(value) - 2) + value[-1]


def format_expiry(timestamp: str | None) -> str:
    if not timestamp or timestamp in ("0", "null", "None"):
        return "sem data (ou ilimitado)"
    try:
        return datetime.fromtimestamp(int(timestamp), tz=UTC).strftime("%d/%m/%Y %H:%M UTC")
    except (TypeError, ValueError):
        return str(timestamp)


def main() -> int:
    load_env()

    playlist_url = os.environ.get("IPTV_PLAYLIST_URL", "").strip()
    if not playlist_url:
        print("IPTV_PLAYLIST_URL nao configurada.", file=sys.stderr)
        return 1

    api_url, username = build_api_url(playlist_url)

    headers = {"User-Agent": os.environ.get("IPTV_PLAYLIST_USER_AGENT", "VLC/3.0.20")}
    referer = os.environ.get("IPTV_PLAYLIST_REFERER")
    if referer:
        headers["Referer"] = referer

    try:
        response = httpx.get(api_url, headers=headers, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        print(f"Servidor respondeu HTTP {exc.response.status_code}.", file=sys.stderr)
        return 1
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        print(f"Nao foi possivel consultar a conta: {exc}", file=sys.stderr)
        return 1

    user = data.get("user_info") or {}
    server = data.get("server_info") or {}

    if not user:
        print("Resposta sem user_info. O servidor pode nao ser Xtream Codes.", file=sys.stderr)
        return 1

    print("Conta na playlist")
    print(f"  usuario ........: {mask(username)}")
    print(f"  status .........: {user.get('status', '?')}")
    print(f"  vencimento .....: {format_expiry(user.get('exp_date'))}")
    print(f"  trial ..........: {user.get('is_trial', '?')}")
    print(
        f"  conexoes .......: {user.get('active_cons', '?')} em uso de "
        f"{user.get('max_connections', '?')} permitidas"
    )
    print(f"  formatos .......: {user.get('allowed_output_formats', '?')}")

    if server:
        print("Servidor")
        print(f"  host ...........: {server.get('url', '?')}:{server.get('port', '?')}")
        print(f"  protocolo ......: {server.get('server_protocol', '?')}")
        print(f"  fuso ...........: {server.get('timezone', '?')}")

    active = user.get("active_cons")
    maximum = user.get("max_connections")
    try:
        if int(str(active)) >= int(str(maximum)):
            print("\nAtencao: todas as conexoes do plano estao em uso agora.")
    except (TypeError, ValueError):
        pass

    if str(user.get("status", "")).lower() != "active":
        print("\nAtencao: a conta nao esta ativa no provedor.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
