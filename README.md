# `coverage-badge` - Github Composite Action

This action create a test coverage badge.

## Input

|Name|Description|
|---|---|
|`token`|Token to use for `git clone` commend|
|`xml-test-report-path`|Path of `.xml` type test report generated from `jacoco` or `kover`.|
|`html-test-report-path`|Path of `html` test report generated from `jacoco` or `kover`.|
|`github-page-ref`|Github page branch name|
|`github-page-path`|Github page branch path|

## Example Workflow File

```yaml
jobs:
  build-service:
    runs-on: ubuntu-18.04
    steps:
      - uses: actions/checkout@v2

      ... // You must generate a test coverage report here.

      - uses: pooi/coverage-badge@1.0.0
        with:
          token: ${{ secret.GITHUB_ACCESS_TOKEN }}
          xml-test-report-path: ${SOURCE_PATH}/build/reports/kover/report.xml
          html-test-report-path: ${SOURCE_PATH}/build/reports/kover/html
```

## README.md

```markdown
[![coverage](https://pages.github.com/user/repo/coverage.svg)](https://pages.github.com/user/repo/coverage)
```