# Minitest CLI

Use the minitest CLI to manage testing flows, upload native builds, execute mobile and web app test runs, and analyse results.

## Overview

This skill teaches AI agents how to use the `minitest` command-line tool. Where the [minitest](../minitest/) skill uses MCP tools to manage flow templates directly, this skill drives the same workflows through the CLI — useful when MCP is not available or when working in CI/automation contexts.

## Use Cases

- "Run my mobile or web app tests"
- "Upload a native build and start a test run"
- "Run my web app tests from the CLI"
- "Create testing flows via the CLI"
- "Check test results for my app"
- "Set up minitest in CI"

## What It Does

1. **Guides CLI installation and authentication** (`uv tool install minitest-cli`, `minitest auth login`)
2. **Manages testing flows** — create, list, update, and delete flows with acceptance criteria
3. **Handles native build uploads** — upload `.apk` / `.ipa` artifacts for Android/iOS apps
4. **Runs tests on mobile and web targets** — start runs, watch progress, collect results
5. **Supports CI/automation** — JSON output mode, exit codes, scripting patterns

## Requirements

- Python 3.10+
- `minitest-cli` installed (`uv tool install minitest-cli`; needs `uv` —
  https://docs.astral.sh/uv/getting-started/installation/ if missing)
- A Minitap account and registered app

## Installation

```
npx skills add minitap-ai/agent-skills --skill minitest-cli
```

## Maintenance — two writers

This skill has two distinct writers; keep them separate:

- **Hand-maintained:** `SKILL.md`, `README.md`, `metadata.json`, and everything
  under `commands/` — the deep-dive guides for command groups whose contract is
  too long to keep in the prompt. Edit these by hand.
- **Machine-generated:** everything under `reference/`. Those files are rendered
  by the testing-service CI (each begins with
  `<!-- rendered by Minitap — do not edit -->`) and must not be
  hand-edited — changes belong in testing-service and are re-rendered from there.
  The `<!-- skill-references-hash: … -->` line near the top of `SKILL.md` is
  likewise machine-managed: CI rewrites it whenever the reference files change so
  that `minitest upgrade` (which hashes `SKILL.md` only) detects the update. Do
  not hand-edit that line.
