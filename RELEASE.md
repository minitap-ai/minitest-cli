# Release Process

## Overview

Releases are automated via GitHub Actions. Pushing a version tag triggers the
full pipeline: build, publish to PyPI, create a GitHub Release, and update the
Homebrew formula.

## Steps

### 1. Update the version

Bump the version in `pyproject.toml`:

- `pyproject.toml` — `version = "X.Y.Z"`

Then sync the lockfile:

```bash
uv sync
```

### 2. Commit and tag

```bash
git add pyproject.toml uv.lock
git commit -m "release: vX.Y.Z"
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
```

### 3. Automated pipeline

The tag push triggers `.github/workflows/release.yml`, which:

1. **Build** — runs `uv build` to produce sdist and wheel
2. **Publish to PyPI** — uses trusted publishing (OIDC), no API token needed
3. **GitHub Release** — creates a release with auto-generated notes and attaches
   the built artifacts
4. **Homebrew update** — dispatches an event to `minitap-ai/homebrew-tap` with
   the new version, sdist URL, and SHA256 hash

### 4. Verify

After the pipeline completes:

```bash
# PyPI
pip install minitest-cli==X.Y.Z
minitest --version

# uvx
uvx --from minitest-cli@X.Y.Z minitest --version

# Homebrew (after tap update completes)
brew update
brew install minitap-ai/tap/minitest-cli
minitest --version
```

## Prerequisites

### PyPI trusted publishing

Configure on PyPI at https://pypi.org/manage/project/minitest-cli/settings/publishing/:

| Field | Value |
|-------|-------|
| Owner | `minitap-ai` |
| Repository | `minitest-cli` |
| Workflow | `release.yml` |
| Environment | `pypi` |

### GitHub repository settings

Create a GitHub Actions environment named `pypi` in the repository settings.

### Homebrew tap token

A `HOMEBREW_TAP_TOKEN` secret must be set in this repository with a GitHub
personal access token that has write access to `minitap-ai/homebrew-tap`.

## Version scheme

We follow [Semantic Versioning](https://semver.org/):

- **Patch** (`0.1.1`) — bug fixes, no API changes
- **Minor** (`0.2.0`) — new features, backward-compatible
- **Major** (`1.0.0`) — breaking changes
