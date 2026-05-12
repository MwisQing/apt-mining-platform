import os
import sys
import unittest
from unittest.mock import patch

os.environ["DISABLE_AUTO_SNAPSHOT_BUILD"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import backend.utils as utils


class TestRuntimeEnvOverrides(unittest.TestCase):
    def setUp(self):
        self.original_config = dict(utils._config)
        utils._config = {
            "paths": {
                "db": "./data/workbench.db",
                "upload_tmp": "./uploads",
            },
            "server": {
                "host": "127.0.0.1",
                "port": 8088,
            },
        }

    def tearDown(self):
        utils._config = self.original_config

    def test_server_host_and_port_can_be_overridden_by_env(self):
        with patch.dict(os.environ, {
            "APT_SERVER_HOST": "0.0.0.0",
            "APT_SERVER_PORT": "9099",
        }, clear=False):
            cfg = utils.get_runtime_server_config()
        self.assertEqual(cfg["host"], "0.0.0.0")
        self.assertEqual(cfg["port"], 9099)

    def test_db_and_upload_paths_can_be_overridden_by_env(self):
        with patch.dict(os.environ, {
            "APT_DB_PATH": "./data/workbench-test.db",
            "APT_UPLOAD_TMP": "./uploads-test",
        }, clear=False):
            expected_db = os.path.join(utils._project_root(), "data", "workbench-test.db")
            expected_upload = os.path.join(utils._project_root(), "uploads-test")
            self.assertEqual(os.path.normpath(utils.get_path("db")), os.path.normpath(expected_db))
            self.assertEqual(os.path.normpath(utils.get_path("upload_tmp")), os.path.normpath(expected_upload))


if __name__ == "__main__":
    unittest.main()
