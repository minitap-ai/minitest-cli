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
npx skills add https://github.com/minitap-ai/minitest-cli/tree/v<version>/skills/minitest-cli --skill minitest-cli
```

## Maintenance — two writers

This skill has two distinct writers; keep them separate:

- **Hand-maintained:** `SKILL.md`, `README.md`, `metadata.json`, and everything
  under `commands/` — the deep-dive guides for command groups whose contract is
  too long to keep in the prompt. Edit these by hand.
- **Machine-generated:** everything under `reference/`. testing-service renders
  those documents from its knowledge fragments and serves them on its public
  `/api/skills/reference` routes, which is what `minitest reference <topic>` prints.
  The files here, with their `index.json`, are the copy the CLI falls back to
  offline; `scripts/sync-skill-references.py` refreshes them from the server. Do
  not hand-edit them: changes belong in testing-service.
