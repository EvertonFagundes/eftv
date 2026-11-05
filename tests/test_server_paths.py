import os
import tempfile
import unittest
from pathlib import Path

import server


class ServerPathsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._root = server.ROOT
        self._data = server.DATA_DIR

    def tearDown(self) -> None:
        server.configure_paths(self._root, self._data)

    def test_configure_paths_grava_fora_do_apk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            www = Path(tmp) / "www"
            data = Path(tmp) / "data"
            www.mkdir()
            server.configure_paths(str(www), str(data))
            server.save_store({"playlists": []})
            self.assertTrue((data / "playlists.json").is_file())
            self.assertEqual(server.ROOT, str(www))
            self.assertEqual(server.DATA_DIR, str(data))

    def test_env_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = os.path.join(tmp, "android-files")
            os.makedirs(data)
            os.environ["EFTV_DATA_DIR"] = data
            try:
                server.configure_paths(tmp, None)
                self.assertEqual(server.DATA_DIR, os.path.abspath(data))
                self.assertEqual(
                    server.STORE_PATH,
                    os.path.join(os.path.abspath(data), "playlists.json"),
                )
            finally:
                os.environ.pop("EFTV_DATA_DIR", None)


if __name__ == "__main__":
    unittest.main()
