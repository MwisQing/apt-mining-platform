import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_push_release():
    path = ROOT / "push_release.py"
    spec = importlib.util.spec_from_file_location("push_release", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PushReleaseTest(unittest.TestCase):
    def test_git_exclude_contains_env_and_go_caches(self):
        push_release = load_push_release()

        self.assertIn(".env", push_release.GIT_EXCLUDE)
        self.assertIn(".gocache/", push_release.GIT_EXCLUDE)
        self.assertIn("backend_v2/.gocache/", push_release.GIT_EXCLUDE)
        self.assertIn(".gomodcache/", push_release.GIT_EXCLUDE)
        self.assertIn("backend_v2/.gomodcache/", push_release.GIT_EXCLUDE)

    def test_git_add_safe_excludes_go_module_cache_during_add(self):
        push_release = load_push_release()
        commands = []

        push_release.run = lambda cmd, capture=False: commands.append(cmd)

        self.assertTrue(push_release.git_add_safe())

        add_command = commands[0]
        self.assertIn("git add -A -- .", add_command)
        self.assertIn(":(exclude)backend_v2/.gomodcache/**", add_command)
        self.assertNotEqual("git add -A", add_command)


if __name__ == "__main__":
    unittest.main()
