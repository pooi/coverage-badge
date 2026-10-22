# `coverage-badge` — GitHub Composite Action

Generate a coverage badge from a JaCoCo or Kover XML report and deploy it with
the HTML report to GitHub Pages. GitHub.com and Linux runners are supported.

## Inputs and output

| Input | Description | Default |
| --- | --- | --- |
| `token` | Optional token passed only to the official Pages deployment action. | `${{ github.token }}` |
| `xml-test-report-path` | Required path to a JaCoCo or Kover XML report. | — |
| `html-test-report-path` | Required path to the HTML report directory. | — |

Relative report paths resolve from `github.workspace`, regardless of the job's
working directory. Absolute paths are also supported. Paths are literal: shell
variables such as `${SOURCE_PATH}` are not expanded in input values.

Output `page-url` contains the deployed site's URL. The site contains
`coverage.svg` and the HTML report under `coverage/`.

## Example workflow (next major version)

In **Settings > Pages > Build and deployment**, set **Source** to **GitHub Actions**.
Configure the `github-pages` environment to allow deployments from your default
branch. The calling job must grant `pages: write` and `id-token: write`; a
composite action cannot grant itself permissions or configure the job environment.

The example assumes the default branch is `main` and a Gradle project using
Kover. Replace the report generation command and paths for your project.
`@v2` below is the intended next major release; use it after that release exists.

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
The token is never inserted into this action's shell scripts, Git URLs, or files.
See the [official Pages workflow requirements](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
and [deploy-pages documentation](https://github.com/actions/deploy-pages).

## Migration from 1.x

- Upgrade to the next major release and switch the Pages source to **GitHub Actions**.
- Remove `github-page-ref` and `github-page-path`; these inputs are no longer supported.
- Remove the explicit `token` input unless you need a custom deployment token.
- Add the job permissions, environment, and concurrency settings shown above.
- Git clone, commit, and push are removed. No `gh-pages` branch is required or updated.
- Each deployment replaces the entire Pages site with the coverage site. Existing
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

Tests validate site preparation and action wiring without uploading artifacts or
deploying. A real deployment requires a GitHub Actions run with Pages configured.
