# Release Process

## Overview

Releases are automated via GitHub Actions. Pushing a version tag triggers the
full pipeline: refresh the bundled agent skill's references, build, publish to PyPI,
and create a GitHub Release. The agent skill lives in this repo and ships inside the
wheel, so there is nothing to merge in `agent-skills` before releasing. uv is the
only distribution channel (the Homebrew formula is retired); users
on a `uv tool install` pick the release up automatically through auto-update
once it has been on PyPI for an hour.

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

### 4. Verify

After the pipeline completes:

```bash
# PyPI
pip install minitest-cli==X.Y.Z
minitest --version

# uvx
uvx --from minitest-cli@X.Y.Z minitest --version
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

## Version scheme

We follow [Semantic Versioning](https://semver.org/):

- **Patch** (`0.1.1`) — bug fixes, no API changes
- **Minor** (`0.2.0`) — new features, backward-compatible
- **Major** (`1.0.0`) — breaking changes
