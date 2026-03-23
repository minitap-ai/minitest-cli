---
name: release
description: >
  Release a new version of minitest-cli. Use when the user says "release",
  "tag a new version", "bump version", "create a release", or "publish".
  Determines the next semver tag from git history, updates pyproject.toml,
  syncs the lockfile, commits, tags, and pushes.
---

# Release minitest-cli

## Process

### 1. Determine the next version

Fetch all existing tags and the commits since the latest tag:

```bash
git fetch --tags
git tag -l 'v*' --sort=-v:refname   # find latest tag
git log <latest-tag>..HEAD --oneline # commits since last release
```

Apply semver rules to the commit list:

| Condition | Bump |
|-----------|------|
| Any commit message **breaks** backward compatibility (`BREAKING CHANGE`, `!:`) | **major** (X.0.0) |
| At least one `feat:` commit | **minor** (0.X.0) |
| Only `fix:`, `docs:`, `test:`, `chore:`, `refactor:`, `style:`, `perf:`, `ci:` | **patch** (0.0.X) |

Present the suggested version and commit summary to the user. Wait for confirmation before proceeding.

### 2. Bump version

```bash
# Edit pyproject.toml version field
# Then sync lockfile
uv sync
```

### 3. Commit, tag, push

```bash
git add pyproject.toml uv.lock
git commit -m "release: v<VERSION>"
git tag v<VERSION>
git push origin HEAD
git push origin v<VERSION>
```

The tag push triggers the release workflow (PyPI publish, GitHub Release, Homebrew tap update).
