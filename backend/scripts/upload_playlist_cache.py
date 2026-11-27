#!/usr/bin/env python
"""Envia a playlist licenciada para o cache do backend.

Use este script em uma rede que alcanca o provedor (ex.: a sua casa no
Brasil). Ele baixa a M3U, confere o cabecalho, comprime e envia para
``PUT /admin/playlist/cache`` com o token de um admin.

A URL do provedor e o token nunca sao impressos. Exemplos:

    set IPTV_PLAYLIST_URL=<url completa>
    python scripts/upload_playlist_cache.py

    python scripts/upload_playlist_cache.py --file playlist.m3u
    python scripts/upload_playlist_cache.py --dry-run

O Render nao alcanca o provedor por geobloqueio; o cache e o que mantem o
catalogo funcionando ate o provedor liberar a regiao.
"""

from __future__ import annotations

import argparse
import getpass
import gzip
import hashlib
import os
import sys
from pathlib import Path

import httpx

DEFAULT_API = "https://eftv.onrender.com"
DEFAULT_UA = "VLC/3.0.20 LibVLC/3.0.20"


def _m3u(raw: bytes) -> bool:
    start = raw[:8192]
    if start.startswith(b"\xef\xbb\xbf"):
        start = start[3:]
    start = start.lstrip()
    if not start:
        return False
    first = start.splitlines()[0].strip().upper()
    return first.startswith(b"#EXTM3U") or first.startswith(b"#EXTINF")


def _download(url: str, *, timeout: float, user_agent: str) -> bytes:
    headers = {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        return response.content


def _login(client: httpx.Client, base: str, email: str, password: str) -> str:
    response = client.post(
        f"{base}/auth/login",
        json={"email": email, "password": password},
    )
    if response.status_code != 200:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = f"HTTP {response.status_code}"
        raise SystemExit(f"Login recusado: {detail}")
    token = response.json().get("access_token")
    if not token:
        raise SystemExit("Login sem access_token")
    return str(token)


def main() -> int:
    parser = argparse.ArgumentParser(description="Envia a playlist para o cache do EFTV")
    parser.add_argument("--url", default=os.getenv("IPTV_PLAYLIST_URL", ""))
    parser.add_argument("--file", type=Path, help="M3U local; pula o download")
    parser.add_argument("--api-base", default=os.getenv("EFTV_API_URL", DEFAULT_API))
    parser.add_argument("--email", default=os.getenv("EFTV_ADMIN_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("EFTV_ADMIN_PASSWORD", ""))
    parser.add_argument("--access-token", default=os.getenv("EFTV_ACCESS_TOKEN", ""))
    parser.add_argument("--user-agent", default=os.getenv("IPTV_PLAYLIST_USER_AGENT", DEFAULT_UA))
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--dry-run", action="store_true", help="Baixa e valida, sem enviar")
    args = parser.parse_args()

    if args.file:
        raw = args.file.read_bytes()
        origin = f"arquivo {args.file.name}"
    else:
        url = (args.url or "").strip()
        if not url:
            raise SystemExit("Informe --url ou defina IPTV_PLAYLIST_URL")
        # Hash seguro: permite comparar com /health sem imprimir a URL.
        print(f"Fingerprint da URL: {hashlib.sha256(url.encode()).hexdigest()[:12]}")
        raw = _download(url, timeout=args.timeout, user_agent=args.user_agent)
        origin = "download direto"

    if not _m3u(raw):
        raise SystemExit("O conteudo recebido nao comeca com #EXTM3U/#EXTINF")
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    print(f"Playlist: {origin}; {len(raw)} bytes; {len(compressed)} comprimidos")
    if args.dry_run:
        print("Dry-run: nada foi enviado.")
        return 0

    base = args.api_base.rstrip("/")
    token = (args.access_token or "").strip()
    with httpx.Client(timeout=args.timeout, follow_redirects=True) as client:
        if not token:
            email = (args.email or "").strip() or input("E-mail admin: ").strip()
            password = args.password or getpass.getpass("Senha admin: ")
            token = _login(client, base, email, password)

        response = client.put(
            f"{base}/admin/playlist/cache",
            content=compressed,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
                "Content-Encoding": "gzip",
            },
        )
        if response.status_code != 200:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text[:200]
            raise SystemExit(f"Envio recusado (HTTP {response.status_code}): {detail}")
        payload = response.json()

    print(
        "Cache atualizado: "
        f"{payload.get('size_bytes')} bytes, "
        f"{payload.get('compressed_bytes')} comprimidos, "
        f"atualizado em {payload.get('updated_at')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
