#!/usr/bin/env python3
"""Publish coverage without putting credentials in Git arguments or files."""

import base64
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit


def authentication_environment(server_url, token):
    server = urlsplit(server_url)
    if server.scheme != "https" or not server.netloc or server.username or server.password:
        raise ValueError("GITHUB_SERVER_URL must be an HTTPS URL without credentials")
    if not token or "\n" in token or "\r" in token:
        raise ValueError("A nonempty, single-line deployment token is required")
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    print(f"::add-mask::{encoded}", flush=True)
    environment = os.environ.copy()
    environment.pop("COVERAGE_TOKEN", None)
    # Command-scoped configuration is inherited by Git's HTTP subprocesses but
    # never written to .git/config. Reset helpers and existing headers first.
    settings = (
        ("credential.helper", ""),
        (f"http.{server_url.rstrip('/')}/.extraheader", ""),
        (f"http.{server_url.rstrip('/')}/.extraheader", f"AUTHORIZATION: basic {encoded}"),
    )
    environment["GIT_CONFIG_COUNT"] = str(len(settings))
    environment["GIT_TERMINAL_PROMPT"] = "0"
    for index, (key, value) in enumerate(settings):
        environment[f"GIT_CONFIG_KEY_{index}"] = key
        environment[f"GIT_CONFIG_VALUE_{index}"] = value
    return environment


def publish(site_path, server_url, repository, branch, token):
    environment = authentication_environment(server_url, token)
    parts = repository.split("/")
    if len(parts) != 2 or any(not part or part in (".", "..") for part in parts):
        raise ValueError("GITHUB_REPOSITORY must be owner/repository")
    if any(character in repository for character in ("?", "#", "\\", "\n", "\r")):
        raise ValueError("Invalid GITHUB_REPOSITORY")
    site_path = Path(site_path)
    if not (site_path / "coverage.svg").is_file() or not (site_path / "coverage").is_dir():
        raise ValueError("Prepared coverage site is missing")

    with tempfile.TemporaryDirectory(prefix="coverage-branch.", dir=os.environ["RUNNER_TEMP"]) as checkout:
        def git(*arguments, check=True):
            return subprocess.run(
                ["git", *arguments], cwd=checkout, env=environment,
                check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        git("check-ref-format", "--branch", branch)
        git("init")
        git("remote", "add", "origin", f"{server_url.rstrip('/')}/{repository}.git")
        remote = git("ls-remote", "--exit-code", "--heads", "origin", f"refs/heads/{branch}", check=False)
        if remote.returncode == 0:
            git("fetch", "--depth=1", "origin", f"refs/heads/{branch}")
            git("checkout", "-B", "coverage-pages", "FETCH_HEAD")
        elif remote.returncode == 2:
            git("checkout", "--orphan", "coverage-pages")
        else:
            raise RuntimeError("Cannot read publishing branch; check token permissions and repository access")

        for name in ("coverage.svg", "coverage"):
            target = Path(checkout) / name
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.exists():
                shutil.rmtree(target)
            source = site_path / name
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copyfile(source, target)

        git("config", "user.name", "github-actions[bot]")
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        git("add", "--", "coverage.svg", "coverage")
        changes = git("diff", "--cached", "--quiet", check=False)
        if changes.returncode == 0:
            print("Coverage is unchanged; no commit needed.")
            return
        if changes.returncode != 1:
            raise RuntimeError("Cannot inspect staged coverage changes")
        git("commit", "-m", "Update coverage data")
        # A concurrent publisher or protected branch must fail rather than lose commits.
        git("push", "origin", f"HEAD:refs/heads/{branch}")
        print("Coverage publishing branch updated.")


if __name__ == "__main__":
    publish(
        os.environ["COVERAGE_SITE_PATH"], os.environ["GITHUB_SERVER_URL"],
        os.environ["GITHUB_REPOSITORY"], os.environ["COVERAGE_BRANCH"],
        os.environ["COVERAGE_TOKEN"],
    )
