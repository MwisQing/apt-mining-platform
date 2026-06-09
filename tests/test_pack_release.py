import importlib.util
import pathlib
import tempfile
import subprocess
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_pack_release():
    path = ROOT / "pack_release.py"
    spec = importlib.util.spec_from_file_location("pack_release", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackReleaseTest(unittest.TestCase):
    def test_build_go_backend_returns_false_when_go_is_missing(self):
        pack_release = load_pack_release()

        with mock.patch.object(
            pack_release.subprocess,
            "run",
            side_effect=FileNotFoundError("go"),
        ):
            self.assertFalse(pack_release.build_go_backend())

    def test_build_go_backend_uses_repo_go_cache(self):
        pack_release = load_pack_release()
        calls = []

        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0)

        with mock.patch.object(pack_release.subprocess, "run", side_effect=fake_run):
            self.assertTrue(pack_release.build_go_backend())

        self.assertGreaterEqual(len(calls), 2)
        for _, kwargs in calls:
            self.assertIn("GOCACHE", kwargs["env"])
            self.assertIn("backend_v2", kwargs["env"]["GOCACHE"])
            self.assertIn("GOMODCACHE", kwargs["env"])
            self.assertIn("backend_v2", kwargs["env"]["GOMODCACHE"])
            self.assertEqual(kwargs["env"]["GOPROXY"], "https://goproxy.cn,direct")
            self.assertEqual(kwargs["env"]["GOSUMDB"], "sum.golang.google.cn")
            self.assertEqual(kwargs["env"]["HTTP_PROXY"], "http://127.0.0.1:10809")
            self.assertEqual(kwargs["env"]["HTTPS_PROXY"], "http://127.0.0.1:10809")

    def test_copy_project_excludes_env_and_go_caches(self):
        pack_release = load_pack_release()

        with tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dest_tmp:
            src = pathlib.Path(src_tmp)
            dest = pathlib.Path(dest_tmp)
            (src / "VERSION").write_text("test\n", encoding="utf-8")
            (src / ".env").write_text("secret\n", encoding="utf-8")
            (src / ".gocache").mkdir()
            (src / ".gocache" / "cache.bin").write_text("cache\n", encoding="utf-8")
            (src / "backend_v2").mkdir()
            (src / "backend_v2" / ".gocache").mkdir()
            (src / "backend_v2" / ".gocache" / "cache.bin").write_text("cache\n", encoding="utf-8")
            (src / "backend_v2" / ".gomodcache").mkdir()
            (src / "backend_v2" / ".gomodcache" / "cache.bin").write_text("cache\n", encoding="utf-8")
            (src / "backend_v2" / "main.go").write_text("package main\n", encoding="utf-8")

            original_script_dir = pack_release.SCRIPT_DIR
            try:
                pack_release.SCRIPT_DIR = src
                pack_release.copy_project(dest)
            finally:
                pack_release.SCRIPT_DIR = original_script_dir

            self.assertTrue((dest / "VERSION").exists())
            self.assertTrue((dest / "backend_v2" / "main.go").exists())
            self.assertFalse((dest / ".env").exists())
            self.assertFalse((dest / ".gocache").exists())
            self.assertFalse((dest / "backend_v2" / ".gocache").exists())
            self.assertFalse((dest / "backend_v2" / ".gomodcache").exists())


if __name__ == "__main__":
    unittest.main()
