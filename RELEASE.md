# Release Process

This document defines the lightweight release process for publishing `aipf` to PyPI.
It is intentionally manual until the package and public contracts stabilize.

## Version Strategy

`aipf` uses semantic versioning.

- `MAJOR`: breaking changes to `RunReport`, capture schema, CLI defaults, provider
  routing behavior, or exit-code contracts.
- `MINOR`: new checks, new CLI flags, new non-breaking report/capture fields, or
  provider compatibility improvements.
- `PATCH`: bug fixes, documentation, packaging metadata, test fixes, or internal
  refactors with no public behavior change.

Before `1.0.0`, keep breaking changes rare and document them explicitly in
`CHANGELOG.md`.

## Public Contracts

Treat these as compatibility-sensitive:

- `aipf` console script and `python -m aipf`;
- `aipf run` exit codes: `0`, `1`, `2`;
- `RunReport` JSON schema in `src/aipf/models.py`;
- capture schema version in `src/aipf/capture.py`;
- OpenAI endpoint `/v1/chat/completions`;
- Anthropic endpoint `/v1/messages`;
- models endpoint `/v1/models`;
- redaction guarantees for API keys and authorization material.

## Version Bump Workflow

1. Update `version` in `pyproject.toml`.
2. Update `__version__` in `src/aipf/__init__.py`.
3. Add a dated entry to `CHANGELOG.md`.
4. Run the full local gate:

   ```bash
   pytest
   ruff check src tests
   mypy
   python -m build
   ```

5. Install the built wheel in a clean virtual environment and run:

   ```bash
   aipf --help
   aipf run --help
   python -m aipf --help
   ```

6. Tag the release:

   ```bash
   git tag -s v0.1.0
   git push origin v0.1.0
   ```

Use unsigned tags only if the project has not adopted signing yet.

## Build

Build artifacts are generated with the standard Python build frontend:

```bash
python -m pip install --upgrade build
python -m build
```

Expected artifacts:

- `dist/aipf-<version>.tar.gz`
- `dist/aipf-<version>-py3-none-any.whl`

`MANIFEST.in` is not required because the project uses Hatchling. The sdist file
list is controlled by `[tool.hatch.build.targets.sdist]` in `pyproject.toml`.

## Local Release Checklist

Run from a clean checkout:

```bash
python -m venv /tmp/aipf-release-src
/tmp/aipf-release-src/bin/python -m pip install --upgrade pip
/tmp/aipf-release-src/bin/python -m pip install .
/tmp/aipf-release-src/bin/aipf --help

python -m venv /tmp/aipf-release-wheel
/tmp/aipf-release-wheel/bin/python -m pip install --upgrade pip
/tmp/aipf-release-wheel/bin/python -m pip install dist/aipf-*.whl
/tmp/aipf-release-wheel/bin/aipf --help
/tmp/aipf-release-wheel/bin/python -m aipf --help
```

Verify artifact contents:

```bash
tar -tzf dist/aipf-*.tar.gz | sort
python -m zipfile -l dist/aipf-*-py3-none-any.whl
```

The sdist should include docs, tests, release notes, architecture notes, and
`assets/logo.txt`. The wheel should include the `aipf` package, `py.typed`, license
metadata, and the `aipf` entrypoint.

## PyPI Trusted Publishing

Recommended PyPI setup:

1. Create the PyPI project manually for the first release.
2. Configure PyPI Trusted Publishing for the GitHub repository.
3. Limit publishing to GitHub release/tag events.
4. Keep CI permissions minimal: `contents: read`, `id-token: write` only in the
   publish job.
5. Do not store long-lived PyPI API tokens in GitHub secrets unless Trusted
   Publishing is unavailable.

## GitHub Release Workflow Proposal

Keep release automation small:

- test, lint, typecheck, and build on every tag matching `v*`;
- upload `dist/*` as GitHub Release artifacts;
- publish to PyPI only from a protected release environment;
- require manual approval for the first public releases.

Minimal workflow shape:

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: pyproject.toml
      - run: python -m pip install -e ".[dev]" build
      - run: python -m pytest -q
      - run: python -m ruff check src tests --output-format=concise
      - run: python -m mypy --no-error-summary
      - run: python -m build
      - uses: actions/upload-artifact@v5
        with:
          name: dist
          path: dist/*

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/download-artifact@v6
        with:
          name: dist
          path: dist
      - uses: pypa/gh-action-pypi-publish@release/v1
```

Do not add this workflow until the public repository URL, branch protection, release
environment, and PyPI Trusted Publishing binding are configured.

## Pre-Publish Readiness

Before publishing:

- confirm the package name `aipf` is available on PyPI, or choose a clear alternate;
- add real repository/project URLs to `[project.urls]` once the public repository
  exists;
- verify README rendering on PyPI;
- run the full local gate on Python 3.11 and at least one newer Python version;
- check that no `.env`, logs, reports, captures, or secrets are included in artifacts.
