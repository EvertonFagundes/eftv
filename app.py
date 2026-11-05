#!/usr/bin/env python3
"""EFTV - Backend na nuvem (Render).
Serviço mínimo que disponibiliza os endpoints que o app Android espera:
  - POST /auth/login
  - POST /auth/refresh
  - GET /player/playlist
  - GET /player/device
  - POST /player/device/revoke

Ele lê a playlist data/playlists.json deste repositório e serve as URLs
de stream para o player do Android (MPEG-TS/HLS). O proxy real dos
streams pode ser feito pelo server.py da versão web na mesma máquina ou
outro serviço; este backend só precisa entregar a URL correta.
"""

import os
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, abort, send_file
from flask_cors import CORS

###############################################################################
# Configuração básica
###############################################################################

API_PASSWORD = os.environ.get("EFTV_API_PASSWORD", "eftv-password-change-me")
PORT = int(os.environ.get("PORT", 10000))

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ---------------------------------------------------------------------------
# Dados: playlist e estado guardados em memória (reset na reinicialização).
# Em produção use um banco de dados persistente (Postgres/SQLite arquivo).
# ---------------------------------------------------------------------------

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PLAYLIST_PATH = os.path.join(DATA_DIR, "playlists.json")

_lock = threading.Lock()

def _load_playlist():
    try:
        with open(PLAYLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _save_playlist(p):
    with _lock:
        with open(PLAYLIST_PATH, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False, indent=2)

# Playlist global (carregada uma vez ao iniciar)
playlist_data = _load_playlist()

# Estado simples de sessão (em memória). Em produção use Redis ou DB.
# {token: {"user": "...", "expires": datetime, "device_ids": set()}}
sessions = {}

# Contador de dispositivos vinculados (para o endpoint /device)
device_counter = 0

# -------------------------------------------------------------------------
# Utilitários
# -------------------------------------------------------------------------

def _senha_valida(senha: str) -> bool:
    return senha == API_PASSWORD

def _gerar_token(user: str = "user") -> str:
    import uuid, base64
    tok = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode()[:24]
    expiry = datetime.now(timezone.utc) + timedelta(hours=12)
    sessions[tok] = {"user": user, "expires": expiry, "device_ids": set()}
    return tok

def _token_valido(tok: str) -> bool:
    if tok not in sessions:
        return False
    if datetime.now(timezone.utc) > sessions[tok]["expires"]:
        # limpeza preguiçosa: removemos depois do próximo request
        return False
    return True

def _require_auth(f):
    """Decorator: espera header Authorization: Bearer <tok> ou query token."""
    def wrapped(*args, **kwargs):
        tok = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            tok = auth[7:]
        if not tok:
            tok = request.args.get("token")
        if not tok or not _token_valido(tok):
            abort(401, description="Token inválido ou expirado")
        return f(tok=tok, *args, **kwargs)
    wrapped._skip_body = True
    return wrapped

###############################################################################
# Rotas
###############################################################################

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    senha = data.get("senha", "").strip()

    if not _senha_valida(senha):
        abort(401, description="Senha incorreta")

    # Usa email como identificador simples (ou gera um user_id fixo)
    token = _gerar_token(email or "user")
    return jsonify({
        "access_token": token,
        "refresh_token": token,
        "expires_in": 43200,  # 12 horas
        "token_type": "Bearer",
    }), 200


@app.route("/auth/refresh", methods=["POST"])
def refresh():
    data = request.get_json(silent=True) or {}
    old_tok = data.get("token", "")
    if not _token_valido(old_tok):
        abort(401, description="Token inválido")
    # Renova por mais 12h
    new_tok = _gerar_token(sessions[old_tok]["user"])
    sessions.pop(old_tok, None)
    return jsonify({
        "access_token": new_tok,
        "refresh_token": new_tok,
        "expires_in": 43200,
        "token_type": "Bearer",
    }), 200


@app.route("/player/playlist", methods=["GET"])
@_require_auth
def player_playlist(tok: str):
    """Retorna a playlist no formato que o app Android espera."""
    global playlist_data

    with _lock:
        # Re-carrega a playlist a cada pedido para pegar eventuais atualizações
        playlist_data = _load_playlist()

    if not playlist_data or "canais" not in playlist_data:
        abort(404, description="Playlist não encontrada")

    canais = playlist_data.get("canais", [])

    # Monta a resposta esperada pelo EftvApi.playlist()
    # O Android vai usar o playlistUrl + userAgent + referer para reproduzir
    user_agent = "EFTV-Android/1.0.0"
    referer = "http://127.0.0.1:8000"

    # Se houver canais, pegamos o primeiro (ou montamos uma playlist genérica)
    # Neste exemplo simples, montamos um objeto com a estrutura esperada.
    # A URL do stream será a que o player do Android tentar conectar.
    # Como esse backend está na nuvem, a URL precisa ser acessível da internet.
    # Como vamos apontar para o server.py local via túnel Cloudflare, a URL
    # será http://URL-do-túnel:8000/... ou webrtc/hls direto.

    # Aqui montamos um exemplo genérico. Em produção, cada canal teria sua URL.
    playlist_url = os.environ.get(
        "EFTV_PLAYLIST_URL",
        "http://127.0.0.1:8124",  # fallback: server da versão web
    )

    # Montagem simplificada: o app Android espera playlistUrl que ele vai tentar reproduzir.
    # O segredo é que essa URL deve levar a um proxy HLS/MPEG-TS.
    # Como integração com o server.py da versão web: a URL poderia ser
    # http://URL-do-túnel/api/proxy?url=... ou um stream direto.

    return jsonify({
        "ok": True,
        "playlistUrl": playlist_url,
        "userAgent": user_agent,
        "referer": referer,
        "subscriptionStatus": "active",
        "daysRemaining": 9999,
        "refreshInSeconds": 300,
        "offlineGraceSeconds": 0,
    }), 200


@app.route("/player/device", methods=["GET"])
@_require_auth
def player_device(tok: str):
    global device_counter
    with _lock:
        device_counter += 1
        dev_id = f"device-{device_counter}"
        sessions[tok]["device_ids"].add(dev_id)
    return jsonify({
        "ok": True,
        "deviceId": dev_id,
        "limit": 3,  # limite de aparelhos simultâneos
        "bound": device_counter,
    }), 200


@app.route("/player/device/revoke", methods=["POST"])
@_require_auth
def device_revoke(tok: str):
    data = request.get_json(silent=True) or {}
    dev_id = data.get("deviceId", "")
    with _lock:
        sessions[tok]["device_ids"].discard(dev_id)
    return jsonify({"ok": True, "revoked": dev_id}), 200


###############################################################################
# Página inicial (opcional — útil para testar que o serviço está no ar)
###############################################################################

@app.route("/")
def index():
    return """
    <h1>EFTV Backend na Nuvem</h1>
    <p>Serviço ativo. Use o app Android com a URL configurada.</p>
    <p>Endpoints disponíveis:</p>
    <ul>
      <li>POST /auth/login    (senha: {}</ul>
      <li>GET  /player/playlist (Bearer token)</ul>
      <li>GET  /player/device (Bearer token)</ul>
      <li>POST /player/device/revoke (Bearer token)</ul>
    </p>
    """.format(API_PASSWORD)


if __name__ == "__main__":
    # Escuta em 0.0.0.0 para aceitar conexões externas (Render/Ingress etc.)
    app.run(host="0.0.0.0", port=PORT, debug=False)


###############################################################################
# Exemplo de como gerar o data/playlists.json caso ele não exista
###############################################################################

if not os.path.exists(PLAYLIST_PATH):
    # Gera um arquivo mínimmo para o backend não cair.
    # O ideal é que o usuário tenha o arquivo real da EFTV nesta posição.
    sample = {
        "total": 0,
        "canais": [],
        "obs": "Substitua este arquivo pelo data/playlists.json real da EFTV."
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PLAYLIST_PATH, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)
    print(f"⚠️  Arquivo {PLAYLIST_PATH} criado vazio. Substitua pela playlist real.")
else:
    print(f"✅ Playlist carregada: {PLAYLIST_PATH}")