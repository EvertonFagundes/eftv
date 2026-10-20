#!/usr/bin/env python3
"""EFTV - servidor local.

Serve os arquivos estáticos da pasta, guarda playlists .m3u/.m3u8 adicionadas
pelo usuário e faz proxy dos streams HLS/DASH para que eles toquem no player
mesmo quando o servidor de origem não envia cabeçalhos CORS.

Uso:
    python3 server.py            # http://127.0.0.1:8124
    PORT=9000 python3 server.py  # outra porta
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
STORE_PATH = os.path.join(DATA_DIR, "playlists.json")
PORT = int(os.environ.get("PORT", "8124"))
HOST = os.environ.get("HOST", "127.0.0.1")

MAX_PLAYLIST_MB = int(os.environ.get("MAX_PLAYLIST_MB", "128"))
MAX_PLAYLIST_BYTES = max(1, MAX_PLAYLIST_MB) * 1024 * 1024
MAX_CHANNELS = int(os.environ.get("MAX_CHANNELS", "50000"))
FETCH_TIMEOUT = 25

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

STORE_LOCK = threading.Lock()

mimetypes.add_type("application/vnd.apple.mpegurl", ".m3u8")
mimetypes.add_type("audio/x-mpegurl", ".m3u")
mimetypes.add_type("application/dash+xml", ".mpd")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("text/javascript", ".js")


# --------------------------------------------------------------------------- #
# Armazenamento
# --------------------------------------------------------------------------- #
def load_store() -> dict:
    if not os.path.exists(STORE_PATH):
        return {"playlists": []}
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"playlists": []}
    if not isinstance(data, dict) or not isinstance(data.get("playlists"), list):
        return {"playlists": []}
    return data


def save_store(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STORE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, STORE_PATH)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Playlists M3U / M3U8
# --------------------------------------------------------------------------- #
ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')
URI_RE = re.compile(r'(URI=")([^"]*)(")')


class FetchError(Exception):
    pass


def is_http_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def filename_from_url(url: str) -> str:
    try:
        name = unquote(os.path.basename(urlsplit(url).path))
    except ValueError:
        name = ""
    name = re.sub(r"\.(m3u8?|mpd|mp4|ts)$", "", name, flags=re.I)
    name = name.replace("_", " ").replace("-", " ").strip()
    return name or "Playlist"


def fetch_text(url: str) -> tuple[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/x-mpegURL, application/vnd.apple.mpegurl, audio/x-mpegurl, text/plain, */*",
        "Accept-Encoding": "identity",
    }
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            data = resp.read(MAX_PLAYLIST_BYTES + 1)
            if len(data) > MAX_PLAYLIST_BYTES:
                raise FetchError(f"A playlist é maior que o limite de {MAX_PLAYLIST_MB} MB.")
            charset = resp.headers.get_content_charset()
            if charset:
                text = data.decode(charset, "replace")
            else:
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    text = data.decode("latin-1")
            return text, resp.geturl()
    except HTTPError as exc:
        raise FetchError(f"O servidor respondeu HTTP {exc.code} ao buscar a playlist.") from exc
    except URLError as exc:
        raise FetchError(f"Não foi possível acessar a playlist: {exc.reason}") from exc
    except TimeoutError as exc:
        raise FetchError("Tempo esgotado ao buscar a playlist.") from exc
    except OSError as exc:
        raise FetchError(f"Falha de rede ao buscar a playlist: {exc}") from exc


def looks_like_hls_manifest(text: str) -> bool:
    head = text[:4096].lstrip("\ufeff \t\r\n")
    if not head.startswith("#EXTM3U"):
        return False
    return any(
        tag in text
        for tag in ("#EXT-X-STREAM-INF", "#EXT-X-TARGETDURATION", "#EXT-X-MEDIA-SEQUENCE")
    )


def parse_m3u(text: str, base_url: str = "") -> tuple[str, list[dict], bool]:
    """Extrai canais de uma lista M3U/M3U8.

    Aceita o formato IPTV (#EXTINF com tvg-logo/group-title) e listas simples
    (uma URL por linha). Devolve (nome_da_playlist, canais, truncada).
    """
    text = text.lstrip("\ufeff")
    playlist_name = ""
    channels: list[dict] = []
    pending: dict | None = None
    truncated = False

    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue

        if line.startswith("#EXTM3U"):
            continue

        if line.startswith("#PLAYLIST:"):
            playlist_name = line.split(":", 1)[1].strip()
            continue

        if line.startswith("#EXTINF:"):
            info = line[len("#EXTINF:"):]
            meta, _, title = info.partition(",")
            attrs = {k.lower(): v for k, v in ATTR_RE.findall(meta)}
            name = title.strip() or attrs.get("tvg-name", "").strip()
            logo = attrs.get("tvg-logo", "").strip()
            if logo and base_url and not is_http_url(logo) and not logo.startswith("data:"):
                logo = urljoin(base_url, logo)
            pending = {
                "name": name,
                "group": attrs.get("group-title", "").strip(),
                "logo": logo,
                "tvg_id": attrs.get("tvg-id", "").strip(),
            }
            continue

        if line.startswith("#EXTGRP:"):
            if pending is not None:
                pending["group"] = line.split(":", 1)[1].strip()
            continue

        # Diretivas que não interessam para a lista de canais.
        if line.startswith("#"):
            continue

        url = urljoin(base_url, line) if base_url else line
        if not is_http_url(url):
            continue

        if pending is None:
            pending = {"name": "", "group": "", "logo": "", "tvg_id": ""}
        pending["url"] = url
        pending["name"] = pending.get("name") or filename_from_url(url)
        channels.append(pending)
        pending = None

        if len(channels) >= MAX_CHANNELS:
            truncated = True
            break

    return playlist_name, channels, truncated


def parse_playlist_text(text: str, source_url: str, fallback_name: str = "") -> tuple[str, list[dict], bool]:
    """Interpreta o conteúdo de uma playlist e devolve (nome, canais, truncada).

    Se o conteúdo for um manifesto HLS (um único stream), devolve um único
    canal apontando para a URL do manifesto.
    """
    if looks_like_hls_manifest(text):
        name = fallback_name or (filename_from_url(source_url) if source_url else "Stream HLS")
        return (
            name,
            [
                {
                    "name": name,
                    "group": "",
                    "logo": "",
                    "tvg_id": "",
                    "url": source_url,
                }
            ],
            False,
        )

    playlist_name, channels, truncated = parse_m3u(text, source_url)
    return fallback_name or playlist_name, channels, truncated


def infer_tipo(url: str) -> str:
    path = urlsplit(url).path.lower()
    if path.endswith(".mpd"):
        return "dash"
    if path.endswith(".ts"):
        return "ts"
    if path.endswith((".mp4", ".m4v", ".webm", ".mkv", ".avi", ".mov", ".mpeg", ".mpg")):
        return "mp4"
    return "hls"


def variante_hls(url: str) -> str:
    """Deriva a variante HLS de um link Xtream Codes terminado em .ts.

    O mesmo servidor costuma expor /usuario/senha/12345.m3u8, que é um HLS
    contínuo, enquanto o .ts é entregue em blocos finitos. Só derivamos quando
    o "nome" do canal é numérico, para não alterar links genéricos de outros
    provedores.
    """
    partes = urlsplit(url)
    caminho = partes.path
    if not caminho.lower().endswith(".ts"):
        return ""
    nome = caminho.rsplit("/", 1)[-1]
    if not nome[:-3].isdigit():
        return ""
    return urlunsplit(
        (partes.scheme, partes.netloc, caminho[:-3] + ".m3u8", partes.query, partes.fragment)
    )


def proxy_url(url: str) -> str:
    return "/api/proxy?url=" + quote(url, safe="")


def make_playlist(name: str, url: str, channels: list[dict]) -> dict:
    return {
        "id": uuid.uuid4().hex[:10],
        "name": name or "Playlist",
        "url": url,
        "channels": channels,
        "imported_at": now_iso(),
        "updated_at": now_iso(),
    }


def summarize(playlist: dict) -> dict:
    return {
        "id": playlist.get("id", ""),
        "name": playlist.get("name", "Playlist"),
        "url": playlist.get("url", ""),
        "count": len(playlist.get("channels", [])),
        "importedAt": playlist.get("imported_at", ""),
        "updatedAt": playlist.get("updated_at", ""),
        "uploaded": not bool(playlist.get("url")),
    }


def contagem_canais(total: int) -> str:
    return f"{total} canal" if total == 1 else f"{total} canais"


def mensagem_importacao(total: int, truncada: bool, nome: str) -> str:
    texto = f"{contagem_canais(total)} {'importado' if total == 1 else 'importados'} de {nome}."
    if truncada:
        texto += f" A lista foi limitada aos primeiros {MAX_CHANNELS} canais."
    return texto


# --------------------------------------------------------------------------- #
# Catálogo consumido pelo site
# --------------------------------------------------------------------------- #
def build_catalog() -> dict:
    store = load_store()
    canais = []
    playlists = []

    for playlist in store.get("playlists", []):
        playlists.append(summarize(playlist))
        pid = playlist.get("id", "")
        pname = playlist.get("name", "Playlist")

        for index, canal in enumerate(playlist.get("channels", [])):
            stream = canal.get("url", "")
            if not stream:
                continue
            name = (canal.get("name") or f"Canal {index + 1}").strip()
            group = (canal.get("group") or "").strip()
            logo = (canal.get("logo") or "").strip()
            tipo_stream = infer_tipo(stream)
            eh_ao_vivo = tipo_stream in ("hls", "ts", "dash")

            hls = variante_hls(stream)
            if hls:
                # HLS contínuo como fonte principal; o .ts fica como
                # alternativa caso o provedor não tenha a variante .m3u8.
                fontes = [
                    {
                        "label": "HLS",
                        "nome": name,
                        "tipo": "hls",
                        "demo": False,
                        "url": proxy_url(hls),
                        "fallbackTipo": "ts",
                        "fallbackUrl": proxy_url(stream),
                    }
                ]
            else:
                fontes = [
                    {
                        "label": "Opção 1",
                        "nome": name,
                        "tipo": tipo_stream,
                        "demo": False,
                        "url": proxy_url(stream),
                    }
                ]

            canais.append(
                {
                    "slug": f"ext-{pid}-{index}",
                    "nome": name,
                    "categoria": "importados",
                    "grupo": group,
                    "logo": proxy_url(logo) if is_http_url(logo) else logo,
                    "aoVivo": eh_ao_vivo,
                    "agora": {
                        "titulo": group or ("Transmissão ao vivo" if eh_ao_vivo else "Conteúdo sob demanda"),
                        "inicio": "--:--",
                        "fim": "--:--",
                        "descricao": (
                            f"Canal importado da playlist {pname}."
                            if eh_ao_vivo
                            else f"Vídeo sob demanda da playlist {pname}."
                        ),
                    },
                    "aSeguir": "Programação não disponível",
                    "origem": {"playlist": pname, "playlistId": pid},
                    "fontes": fontes,
                }
            )

    return {
        "playlists": playlists,
        "categorias": [{"id": "importados", "nome": "Importados"}] if canais else [],
        "canais": canais,
    }


CATALOGO_JS = """(function () {
  if (!window.CANAIS_DATA) return;
  var extra = %s;

  window.CANAIS_EXTRA = extra;
  window.CANAIS_BASE = window.CANAIS_BASE || {
    canais: (window.CANAIS_DATA.canais || []).slice(),
    categorias: (window.CANAIS_DATA.categorias || []).slice()
  };

  window.CanaisAplicarCatalogo = function (novo) {
    var base = window.CANAIS_BASE;
    var categorias = base.categorias.slice();
    (novo.categorias || []).forEach(function (cat) {
      if (!categorias.some(function (c) { return c.id === cat.id; })) categorias.push(cat);
    });
    window.CANAIS_DATA.categorias = categorias;
    window.CANAIS_DATA.canais = base.canais.concat(novo.canais || []);
    window.CANAIS_EXTRA_PLAYLISTS = novo.playlists || [];
  };

  window.CanaisAplicarCatalogo(extra);
})();
"""


# --------------------------------------------------------------------------- #
# Proxy de streams e imagens
# --------------------------------------------------------------------------- #
def rewrite_playlist(text: str, base_url: str) -> str:
    out = []
    for raw in text.splitlines():
        line = raw
        if line.lstrip().startswith("#"):
            def troca(match: re.Match) -> str:
                uri = match.group(2).strip()
                if not uri or uri.startswith("data:"):
                    return match.group(0)
                return match.group(1) + proxy_url(urljoin(base_url, uri)) + match.group(3)

            out.append(URI_RE.sub(troca, line))
            continue

        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue

        out.append(proxy_url(urljoin(base_url, stripped)))

    return "\n".join(out)


class Handler(SimpleHTTPRequestHandler):
    server_version = "EFTV/1.0"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------ util
    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _same_origin(self) -> bool:
        """Bloqueia POST/DELETE disparados por outras páginas (CSRF local)."""
        origin = self.headers.get("Origin")
        if not origin:
            return True  # curl / requisições fora do navegador
        host = self.headers.get("Host", "")
        return origin in (f"http://{host}", f"https://{host}")

    def _error(self, message: str, status: int = 400) -> None:
        self._send_json({"ok": False, "error": message}, status)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 2 * 1024 * 1024:
            raise ValueError("Corpo da requisição inválido.")
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ValueError("JSON inválido.") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON inválido.")
        return data

    def _read_body(self, limit: int = MAX_PLAYLIST_BYTES) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            raise ValueError("Arquivo vazio.")
        if length > limit:
            raise ValueError(f"O arquivo é maior que o limite de {MAX_PLAYLIST_MB} MB.")
        return self.rfile.read(length)

    # ------------------------------------------------------------------- API
    def do_GET(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        route = parts.path

        if route == "/api/playlists":
            store = load_store()
            self._send_json(
                {"ok": True, "playlists": [summarize(p) for p in store.get("playlists", [])]}
            )
            return

        if route == "/api/catalogo.json":
            self._send_json({"ok": True, **build_catalog()})
            return

        if route == "/api/catalogo.js":
            catalogo = build_catalog()
            body = (CATALOGO_JS % json.dumps(catalogo, ensure_ascii=False)).replace("</", "<\\/")
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return

        if route == "/api/proxy":
            self._handle_proxy(parts.query)
            return

        if route.startswith("/data/"):
            self._error("Rota não encontrada.", 404)
            return

        if route.startswith("/api/"):
            self._error("Rota não encontrada.", 404)
            return

        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        route = parts.path

        if not self._same_origin():
            self._error("Origem não permitida.", 403)
            return

        try:
            if route == "/api/playlists":
                payload = self._read_json()
                self._add_from_url(payload)
                return

            if route == "/api/playlists/upload":
                query = parse_qs(parts.query)
                name = (query.get("name") or [""])[0].strip()
                raw = self._read_body()
                try:
                    text = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = raw.decode("latin-1")
                self._add_from_text(text, name or "Playlist enviada")
                return

            if route == "/api/playlists/refresh":
                payload = self._read_json()
                self._refresh_playlist(payload.get("id", ""))
                return

            if route == "/api/playlists/clear":
                with STORE_LOCK:
                    save_store({"playlists": []})
                self._send_json({"ok": True})
                return

            self._error("Rota não encontrada.", 404)
        except ValueError as exc:
            self._error(str(exc), 400)
        except FetchError as exc:
            self._error(str(exc), 502)
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001 - resposta de erro para o cliente
            self._error(f"Erro inesperado: {exc}", 500)

    def do_DELETE(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        if not self._same_origin():
            self._error("Origem não permitida.", 403)
            return
        if parts.path != "/api/playlists":
            self._error("Rota não encontrada.", 404)
            return
        query = parse_qs(parts.query)
        pid = (query.get("id") or [""])[0].strip()
        if not pid:
            self._error("Informe o id da playlist.", 400)
            return
        with STORE_LOCK:
            store = load_store()
            antes = len(store["playlists"])
            store["playlists"] = [p for p in store["playlists"] if p.get("id") != pid]
            save_store(store)
        if len(store["playlists"]) == antes:
            self._error("Playlist não encontrada.", 404)
            return
        self._send_json({"ok": True})

    # --------------------------------------------------------- manipuladores
    def _add_from_url(self, payload: dict) -> None:
        url = str(payload.get("url", "")).strip()
        nome = str(payload.get("name", "")).strip()
        if not url:
            raise ValueError("Informe o link da playlist .m3u ou .m3u8.")
        if not is_http_url(url):
            raise ValueError("O link precisa começar com http:// ou https://.")

        text, final_url = fetch_text(url)
        nome_playlist, channels, truncada = parse_playlist_text(text, final_url, nome)
        if not channels:
            raise ValueError(
                "Nenhum canal foi encontrado nessa playlist. "
                "Verifique se o link aponta para uma lista .m3u/.m3u8 válida."
            )

        playlist = make_playlist(nome or nome_playlist or filename_from_url(final_url), final_url, channels)
        with STORE_LOCK:
            store = load_store()
            store["playlists"].append(playlist)
            save_store(store)

        self._send_json(
            {
                "ok": True,
                "playlist": summarize(playlist),
                "message": mensagem_importacao(len(channels), truncada, playlist["name"]),
            }
        )

    def _add_from_text(self, text: str, nome: str) -> None:
        if not text.strip():
            raise ValueError("O arquivo está vazio.")
        if looks_like_hls_manifest(text):
            raise ValueError(
                "Esse arquivo é um manifesto HLS de um único stream. "
                "Para adicionar esse canal, use o link http(s) do .m3u8 no campo de URL."
            )

        _, channels, truncada = parse_m3u(text)
        if not channels:
            raise ValueError(
                "Nenhum canal foi encontrado no arquivo. "
                "Envie uma lista .m3u/.m3u8 com linhas #EXTINF ou uma URL por linha."
            )

        playlist = make_playlist(nome, "", channels)
        with STORE_LOCK:
            store = load_store()
            store["playlists"].append(playlist)
            save_store(store)

        self._send_json(
            {
                "ok": True,
                "playlist": summarize(playlist),
                "message": mensagem_importacao(len(channels), truncada, playlist["name"]),
            }
        )

    def _refresh_playlist(self, pid: str) -> None:
        pid = str(pid or "").strip()
        if not pid:
            raise ValueError("Informe o id da playlist.")

        with STORE_LOCK:
            store = load_store()
            playlist = next((p for p in store["playlists"] if p.get("id") == pid), None)
            if playlist is None:
                raise ValueError("Playlist não encontrada.")
            url = playlist.get("url", "")
            if not is_http_url(url):
                raise ValueError("Esta playlist foi enviada por arquivo e não tem URL para atualizar.")

            text, final_url = fetch_text(url)
            _, channels, truncada = parse_playlist_text(text, final_url, playlist.get("name", ""))
            if not channels:
                raise ValueError("A playlist não tem mais canais válidos.")
            playlist["channels"] = channels
            playlist["url"] = final_url
            playlist["updated_at"] = now_iso()
            save_store(store)

        self._send_json(
            {
                "ok": True,
                "playlist": summarize(playlist),
                "message": f"Playlist atualizada: {contagem_canais(len(channels))}."
                + (f" Limitada aos primeiros {MAX_CHANNELS} canais." if truncada else ""),
            }
        )

    # ---------------------------------------------------------------- proxy
    def _handle_proxy(self, query: str) -> None:
        params = parse_qs(query)
        target = (params.get("url") or [""])[0].strip()
        if not target:
            self._error("Parâmetro url ausente.", 400)
            return
        if not is_http_url(target):
            self._error("Somente URLs http(s) podem ser reproduzidas.", 400)
            return

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        parts = urlsplit(target)
        headers["Referer"] = f"{parts.scheme}://{parts.netloc}/"
        range_header = self.headers.get("Range")
        if range_header:
            headers["Range"] = range_header

        try:
            req = Request(target, headers=headers)
            resp = urlopen(req, timeout=FETCH_TIMEOUT)
        except HTTPError as exc:
            self._error(f"A origem respondeu HTTP {exc.code}.", 502)
            return
        except (URLError, TimeoutError, OSError) as exc:
            self._error(f"Não foi possível acessar o stream: {exc}", 502)
            return

        try:
            final_url = resp.geturl()
            ctype = (resp.headers.get("Content-Type") or "").lower()
            path = urlsplit(final_url).path.lower()

            is_playlist = path.endswith((".m3u8", ".m3u")) or "mpegurl" in ctype
            first = b""
            if not is_playlist:
                first = resp.read(1024)
                if first.lstrip().startswith(b"#EXTM3U"):
                    is_playlist = True

            if is_playlist:
                data = first + resp.read(MAX_PLAYLIST_BYTES + 1)
                if len(data) > MAX_PLAYLIST_BYTES:
                    self._error("Manifesto muito grande.", 502)
                    return
                text = data.decode("utf-8", "replace")
                rewritten = rewrite_playlist(text, final_url).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Content-Length", str(len(rewritten)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(rewritten)
                return

            self.send_response(getattr(resp, "status", 200))
            self.send_header("Content-Type", resp.headers.get("Content-Type") or "application/octet-stream")
            content_length = resp.headers.get("Content-Length")
            for header in ("Content-Length", "Content-Range", "Accept-Ranges", "ETag", "Last-Modified"):
                value = resp.headers.get(header)
                if value:
                    self.send_header(header, value)
            if not content_length:
                # Sem Content-Length não há como delimitar o corpo em HTTP/1.1.
                self.send_header("Connection", "close")
                self.close_connection = True
            self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if first:
                self.wfile.write(first)
            shutil.copyfileobj(resp, self.wfile, length=64 * 1024)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # noqa: BLE001
            try:
                self._error(f"Falha ao repassar o stream: {exc}", 502)
            except Exception:  # noqa: BLE001
                pass
        finally:
            try:
                resp.close()
            except Exception:  # noqa: BLE001
                pass

    def log_message(self, fmt: str, *args) -> None:
        # Não registra a query string: URLs de playlists podem conter usuário,
        # senha ou tokens de acesso.
        try:
            caminho = urlsplit(self.path).path
        except ValueError:
            caminho = "/"
        sys.stderr.write("%s - %s %s\n" % (self.address_string(), self.command, caminho))


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.chdir(ROOT)
    store = load_store()
    if not store.get("playlists"):
        save_store(store)

    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    print(f"EFTV em http://{HOST}:{PORT}/  (playlists: {STORE_PATH})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrando...", flush=True)
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
