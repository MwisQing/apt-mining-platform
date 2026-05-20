import os
import sys
import unittest
from unittest.mock import patch

os.environ["DISABLE_AUTO_SNAPSHOT_BUILD"] = "1"

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import start


class TestRuntimeOpsScripts(unittest.TestCase):
    def test_start_test_sets_isolated_env_defaults(self):
        captured = {}

        def fake_run(cmd, cwd=None, env=None):
            captured["cmd"] = cmd
            captured["cwd"] = cwd
            captured["env"] = env
            class Result:
                returncode = 0
            return Result()

        with patch.object(sys, "argv", ["start.py", "--test", "--no-browser"]):
            with patch("start.ensure_runtime_ready", return_value="python"):
                with patch("start.port_in_use", return_value=False):
                    with patch("subprocess.run", side_effect=fake_run):
                        with patch.object(sys, "exit") as exit_mock:
                            start.main()
                            exit_mock.assert_called_once_with(0)

        env = captured["env"]
        self.assertEqual(env["APT_SERVER_PORT"], "9099")
        self.assertTrue(env["APT_DB_PATH"].endswith("workbench-test.db"))
        self.assertTrue(env["APT_UPLOAD_TMP"].endswith("uploads-test"))
        self.assertEqual(env["VITE_API_TARGET"], "http://127.0.0.1:9099")


if __name__ == "__main__":
    unittest.main()
