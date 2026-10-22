# `coverage-badge` — GitHub Composite Action

Generate a coverage badge from a JaCoCo or Kover XML report and deploy it with
the HTML report to GitHub Pages. Linux runners on GitHub.com and GitHub Enterprise
Server (GHES) are supported. GHES branch publishing is available from v2.1.0.

## Inputs and output

| Input | Description | Default |
| --- | --- | --- |
| `token` | Optional token for Pages deployment or publishing to a branch. | `${{ github.token }}` |
| `xml-test-report-path` | Required path to a JaCoCo or Kover XML report. | — |
| `html-test-report-path` | Required path to the HTML report directory. | — |
| `deployment-mode` | `auto`: Pages artifacts on GitHub.com, branch publishing on GHES. Override with `pages` or `branch`. | `auto` |
| `github-page-ref` | Publishing branch, used only in branch mode. | `gh-pages` |

Relative report paths resolve from `github.workspace`, regardless of the job's
working directory. Absolute paths are also supported. Paths are literal: shell
variables such as `${SOURCE_PATH}` are not expanded in input values.

Output `page-url` contains the deployed site's URL in Pages artifact mode and is
empty in branch mode. The coverage site contains
`coverage.svg` and the HTML report under `coverage/`.

## GitHub.com example workflow

In **Settings > Pages > Build and deployment**, set **Source** to **GitHub Actions**.
Configure the `github-pages` environment to allow deployments from your default
branch. The calling job must grant `pages: write` and `id-token: write`; a
composite action cannot grant itself permissions or configure the job environment.

The example assumes the default branch is `main` and a Gradle project using
Kover. Replace the report generation command and paths for your project.

```yaml
name: Coverage Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  coverage:
    if: github.ref == format('refs/heads/{0}', github.event.repository.default_branch)
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pages: write
      id-token: write
    environment:
      name: github-pages
      url: ${{ steps.coverage.outputs.page-url }}
    steps:
      - uses: actions/checkout@v6
        with:
          persist-credentials: false
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Generate coverage reports
        run: ./gradlew koverXmlReport koverHtmlReport
      - uses: pooi/coverage-badge@v2
        id: coverage
        with:
          xml-test-report-path: build/reports/kover/report.xml
          html-test-report-path: build/reports/kover/html
```

No personal access token or `contents: write` permission is needed. To supply a
different token, add `token: ${{ secrets.PAGES_TOKEN }}` to the action's `with`
mapping. That token must support Pages deployments for this repository; the job
still needs `id-token: write` and must satisfy environment protection rules.
The token is never interpolated into this action's shell scripts, Git URLs, or files.
See the [official Pages workflow requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
and [deploy-pages documentation](https://github.com/actions/deploy-pages).

## GitHub Enterprise Server

The official Pages artifact actions do not support GHES. With `deployment-mode:
auto` (the default), this action publishes to `gh-pages` on the current GHES server
instead. Set **Settings > Pages > Source** to **Deploy from a branch**, then select
`gh-pages` and `/ (root)`. The first publish creates the branch if it does not exist.

Add this step after generating reports and setting up Python in your existing job:

```yaml
- uses: pooi/coverage-badge@v2.1.0
  with:
    deployment-mode: branch
    token: ${{ secrets.BUILD_COMMON_TOKEN }}
    xml-test-report-path: ${{ env.SOURCE_PATH }}/build/reports/kover/report.xml
    html-test-report-path: ${{ env.SOURCE_PATH }}/build/reports/kover/html
```

The runner must have Python 3.7+ and Git 2.31+, and your GHES installation must
allow this public action. The token must have repository content write access and
permission to push to the publishing branch. If using the default `github.token`,
grant the job `contents: write`; verify whether token-generated pushes trigger
Pages builds on your GHES version. Use a suitable PAT or GitHub App token when
required by your server. `pages: write`, `id-token: write`, and the `github-pages`
environment are only required for Pages artifact mode, not branch publishing.

Branch publishing replaces only `coverage.svg` and `coverage/`, preserving other
files on the branch. It does not force-push; branch protection and concurrent
changes can reject a push and fail the step. Unchanged reports create no commit.
Authentication headers exist only in the Git subprocess environment, are masked
in logs, and are never written to the remote URL or Git configuration files.
Publishing a branch does not wait for the server's Pages build to finish.

## Migration from 1.x

- For GitHub.com, upgrade to v2 and switch the Pages source to **GitHub Actions**.
- For GHES, use v2.1.0 or later and keep branch-based Pages publishing.
- Remove `github-page-path`; staging always uses a temporary directory.
- `github-page-ref` is supported from v2.1.0 for branch publishing only.
- Remove the explicit `token` input unless you need a custom deployment token.
- Add the job permissions, environment, and concurrency settings shown above.
- In Pages artifact mode, no `gh-pages` branch is required or updated.
- Each Pages artifact deployment replaces the entire site with the coverage site. Existing
  branch files, other site content, and `create.txt` are not preserved. Use a
  dedicated coverage repository if your existing Pages site hosts other content.

Badge and report paths remain `/coverage.svg` and `/coverage/`. For a project site:

```markdown
[![coverage](https://USER.github.io/REPO/coverage.svg)](https://USER.github.io/REPO/coverage/)
```

## Local validation

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Tests validate site preparation, mode selection, and branch publishing to local
bare Git repositories. They do not upload artifacts or deploy to a live server.
A real deployment requires a GitHub Actions run with Pages configured.
