import contextlib
import io
import importlib.util
import pathlib
import subprocess
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

    def test_has_unpushed_commits_without_upstream(self):
        push_release = load_push_release()

        def fake_run(cmd, capture=False):
            if cmd == "git rev-parse --verify HEAD":
                return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n")
            if "symbolic-full-name" in cmd:
                return subprocess.CompletedProcess(cmd, 1, stderr="no upstream")
            self.fail(f"unexpected command: {cmd}")

        push_release.run = fake_run

        self.assertTrue(push_release.has_unpushed_commits())

    def test_git_push_network_error_does_not_force_push(self):
        push_release = load_push_release()
        commands = []

        def fake_run(cmd, capture=False):
            commands.append(cmd)
            if cmd == "git branch --show-current":
                return subprocess.CompletedProcess(cmd, 0, stdout="master\n")
            if cmd == "git push -u origin master":
                return subprocess.CompletedProcess(
                    cmd,
                    128,
                    stderr=(
                        "fatal: unable to access "
                        "'https://github.com/MwisQing/apt-mining-platform.git/': "
                        "Failed to connect to github.com port 443"
                    ),
                )
            self.fail(f"unexpected command: {cmd}")

        push_release.run = fake_run

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(push_release.git_push())
        self.assertNotIn("git push -u origin master --force", commands)


if __name__ == "__main__":
    unittest.main()
