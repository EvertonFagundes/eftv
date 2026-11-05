"""Sobe o server.py dentro do APK (Chaquopy)."""

from __future__ import annotations

import os
import threading

import server as srv

_httpd = None
_thread = None
_lock = threading.Lock()


def start_server(root: str, data_dir: str, host: str = "0.0.0.0", port: int = 8124) -> dict:
    global _httpd, _thread

    www = os.path.abspath(str(root))
    dados = os.path.abspath(str(data_dir))
    escuta = str(host or "0.0.0.0")
    porta = int(port)

    os.environ["EFTV_ROOT"] = www
    os.environ["EFTV_DATA_DIR"] = dados
    os.environ["HOST"] = escuta
    os.environ["PORT"] = str(porta)

    srv.configure_paths(www, dados)

    with _lock:
        if _httpd is not None:
            return {"ok": True, "already": True, "host": escuta, "port": porta}

        os.makedirs(dados, exist_ok=True)
        os.chdir(www)
        store = srv.load_store()
        if not store.get("playlists"):
            srv.save_store(store)

        try:
            httpd = srv.Servidor((escuta, porta), srv.Handler)
        except OSError as exc:
            return {"ok": False, "error": str(exc), "host": escuta, "port": porta}

        httpd.daemon_threads = True
        _httpd = httpd

        def servir() -> None:
            try:
                httpd.serve_forever()
            finally:
                httpd.server_close()

        _thread = threading.Thread(target=servir, name="eftv-http", daemon=True)
        _thread.start()
        return {"ok": True, "already": False, "host": escuta, "port": porta}


def stop_server() -> dict:
    global _httpd, _thread
    with _lock:
        httpd = _httpd
        _httpd = None
        _thread = None
    if httpd is None:
        return {"ok": True, "stopped": False}
    threading.Thread(target=httpd.shutdown, daemon=True).start()
    return {"ok": True, "stopped": True}
