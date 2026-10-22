import base64
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("publish_branch", ROOT / "publish-branch.py")
PUBLISHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLISHER)
TOKEN = "test-token-never-in-url"


class BranchPublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.site = self.root / "site"
        (self.site / "coverage").mkdir(parents=True)
        (self.site / "coverage.svg").write_text("badge")
        (self.site / "coverage" / "index.html").write_text("new coverage")
        self.remote = self.root / "repositories" / "owner" / "repo.git"
        self.remote.parent.mkdir(parents=True)
        self.git("init", "--bare", str(self.remote))
        self.config = self.root / "gitconfig"
        self.git("config", "--file", str(self.config),
                 f"url.{(self.root / 'repositories').as_uri()}/.insteadOf", "https://github.example.test/")
        self.environment = dict(
            os.environ,
            GIT_CONFIG_GLOBAL=str(self.config), GIT_CONFIG_NOSYSTEM="1",
            RUNNER_TEMP=str(self.root), GITHUB_SERVER_URL="https://github.example.test",
            GITHUB_REPOSITORY="owner/repo", COVERAGE_SITE_PATH=str(self.site),
            COVERAGE_BRANCH="gh-pages", COVERAGE_TOKEN=TOKEN,
        )
        self.environment.pop("GIT_CONFIG_COUNT", None)

    def git(self, *arguments, cwd=None):
        return subprocess.run(["git", *arguments], cwd=cwd, check=True,
                              text=True, capture_output=True).stdout.strip()

    def publish(self, **overrides):
        return subprocess.run([sys.executable, str(ROOT / "publish-branch.py")],
                              env=dict(self.environment, **overrides), text=True, capture_output=True)

    def read_remote(self, object_name):
        return self.git("--git-dir", str(self.remote), "show", object_name)

    def test_new_branch_and_unchanged_second_publish(self):
        first = self.publish()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.read_remote("gh-pages:coverage/index.html"), "new coverage")
        self.assertEqual(self.read_remote("gh-pages:coverage.svg"), "badge")
        commit = self.git("--git-dir", str(self.remote), "rev-parse", "gh-pages")
        second = self.publish()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("no commit needed", second.stdout)
        self.assertEqual(self.git("--git-dir", str(self.remote), "rev-parse", "gh-pages"), commit)
        self.assertNotIn(TOKEN, first.stdout + first.stderr + second.stdout + second.stderr)
        self.assertNotIn(TOKEN, (self.remote / "config").read_text())
        self.assertFalse(list(self.root.glob("coverage-branch.*")))

    def test_preserves_other_files_and_replaces_old_coverage(self):
        seed = self.root / "seed"
        seed.mkdir()
        self.git("init", cwd=seed)
        self.git("checkout", "--orphan", "gh-pages", cwd=seed)
        (seed / "CNAME").write_text("coverage.example.test")
        (seed / "coverage").mkdir()
        (seed / "coverage" / "old.html").write_text("obsolete")
        self.git("add", ".", cwd=seed)
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-m", "Seed", cwd=seed)
        self.git("push", str(self.remote), "gh-pages", cwd=seed)
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_remote("gh-pages:CNAME"), "coverage.example.test")
        tree = self.git("--git-dir", str(self.remote), "ls-tree", "-r", "--name-only", "gh-pages")
        self.assertNotIn("old.html", tree)
        self.assertIn("coverage/index.html", tree)

    def test_rejected_push_fails_and_cleans_up(self):
        hook = self.remote / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)
        self.assertFalse(list(self.root.glob("coverage-branch.*")))

    def test_invalid_branch_and_empty_token_fail(self):
        for overrides in ({"COVERAGE_BRANCH": "bad branch"}, {"COVERAGE_TOKEN": ""}):
            with self.subTest(overrides=overrides):
                result = self.publish(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(list(self.root.glob("coverage-branch.*")))

    def test_authentication_is_scoped_and_not_persisted(self):
        output = io.StringIO()
        with patch.dict(os.environ, COVERAGE_TOKEN=TOKEN), contextlib.redirect_stdout(output):
            environment = PUBLISHER.authentication_environment("https://github.example.test", TOKEN)
        encoded = base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()
        self.assertNotIn("COVERAGE_TOKEN", environment)
        self.assertEqual(environment["GIT_CONFIG_KEY_1"], "http.https://github.example.test/.extraheader")
        self.assertEqual(environment["GIT_CONFIG_VALUE_1"], "")
        self.assertEqual(environment["GIT_CONFIG_VALUE_2"], f"AUTHORIZATION: basic {encoded}")
        self.assertIn(f"::add-mask::{encoded}", output.getvalue())
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")


if __name__ == "__main__":
    unittest.main()
