import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


SAMPLE = """#EXTM3U
#EXTINF:-1 tvg-name="Demo",Demo
http://example.com/live/demo.ts
"""


class ServerHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self._root = server.ROOT
        self._data = server.DATA_DIR
        self.httpd = None
        self.tmp = tempfile.TemporaryDirectory()
        www = Path(self.tmp.name) / "www"
        data = Path(self.tmp.name) / "data"
        www.mkdir()
        (www / "index.html").write_text("<html>ok</html>", encoding="utf-8")
        server.configure_paths(str(www), str(data))
        server.save_store({"playlists": []})
        self.httpd = server.Servidor(("127.0.0.1", 0), server.Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.05)

    def tearDown(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
        server.configure_paths(self._root, self._data)
        self.tmp.cleanup()

    def _url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def test_health_e_status_iniciais(self) -> None:
        with urlopen(self._url("/health"), timeout=2) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(body["ok"])
        with urlopen(self._url("/api/status"), timeout=2) as resp:
            status = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(status["playlists"], 0)
        self.assertEqual(status["canais"], 0)
        self.assertEqual(status["host"], "127.0.0.1")

    def test_upload_grava_em_data_dir(self) -> None:
        req = Request(
            self._url("/api/playlists/upload?name=teste"),
            data=SAMPLE.encode("utf-8"),
            headers={"Content-Type": "audio/x-mpegurl"},
            method="POST",
        )
        with urlopen(req, timeout=2) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        with urlopen(self._url("/api/status"), timeout=2) as resp:
            status = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(status["playlists"], 1)
        self.assertGreaterEqual(status["canais"], 1)
        store = Path(server.STORE_PATH)
        self.assertTrue(store.is_file())
        self.assertIn("teste", store.read_text(encoding="utf-8"))

    def test_remove_playlist_na_versao_web(self) -> None:
        self._enviar_playlist("teste")
        pid = server.load_store()["playlists"][0]["id"]

        req = Request(self._url(f"/api/playlists?id={pid}"), method="DELETE")
        with urlopen(req, timeout=2) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        self.assertTrue(payload["ok"])
        self.assertEqual(server.load_store()["playlists"], [])

    def test_playlists_somente_leitura_dentro_do_apk(self) -> None:
        self._enviar_playlist("teste")
        pid = server.load_store()["playlists"][0]["id"]
        os.environ["EFTV_PLAYLIST_READONLY"] = "1"
        try:
            with self.assertRaises(HTTPError) as remover:
                urlopen(
                    Request(self._url(f"/api/playlists?id={pid}"), method="DELETE"),
                    timeout=2,
                )
            self.assertEqual(remover.exception.code, 403)

            with self.assertRaises(HTTPError) as adicionar:
                urlopen(
                    Request(
                        self._url("/api/playlists/upload?name=outra"),
                        data=SAMPLE.encode("utf-8"),
                        headers={"Content-Type": "audio/x-mpegurl"},
                        method="POST",
                    ),
                    timeout=2,
                )
            self.assertEqual(adicionar.exception.code, 403)
        finally:
            os.environ.pop("EFTV_PLAYLIST_READONLY", None)

        self.assertEqual(len(server.load_store()["playlists"]), 1)

    def _enviar_playlist(self, nome: str) -> None:
        req = Request(
            self._url(f"/api/playlists/upload?name={nome}"),
            data=SAMPLE.encode("utf-8"),
            headers={"Content-Type": "audio/x-mpegurl"},
            method="POST",
        )
        with urlopen(req, timeout=2) as resp:
            self.assertTrue(json.loads(resp.read().decode("utf-8"))["ok"])


if __name__ == "__main__":
    unittest.main()
