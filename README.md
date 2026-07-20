# minitest-cli

Command-line interface for the Minitest testing platform for mobile and web apps.

## Installation

### One-liner (recommended)

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/minitap-ai/minitest-cli/main/install.sh | bash
```

**Windows (PowerShell):**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/minitap-ai/minitest-cli/main/install.ps1 | iex"
```

Both scripts use `uv` if available, or install it automatically.

### Other methods

**uv** (all platforms):

```bash
uv tool install minitest-cli
```

**Homebrew** (macOS):

```bash
brew install minitap-ai/tap/minitest-cli
```

**uvx** (zero-install, all platforms):

```bash
uvx --from minitest-cli minitest --help
```

**From source:**

```bash
git clone https://github.com/minitap-ai/minitest-cli.git
cd minitest-cli
uv sync
uv run minitest --help
```

## Quick Start

```bash
# Authenticate
minitest auth login

# List your apps
minitest apps list

# Create a new app on your tenant
minitest apps create --name "My Mobile App" --platform ios --platform android

# Or create a web app target
minitest apps create --name "My Web App" --platform web --web-url https://example.com

# Upload native builds when testing iOS/Android apps
minitest --app <app-id> build upload ./app-release.apk

# Run tests
minitest --app <app-id> run all --web
# or, for native lanes:
minitest --app <app-id> run all --ios-build <ios-build-id> --android-build <android-build-id>
```

## Configuration

| Environment Variable          | Description                                                | Required                           |
| ----------------------------- | ---------------------------------------------------------- | ---------------------------------- |
| `MINITEST_TOKEN`              | API authentication token                                   | Yes (or use `minitest auth login`) |
| `MINITEST_APP_ID`             | Default app ID                                             | No (can use `--app` flag)          |
| `MINITEST_API_URL`            | testing-service base URL                                   | No (defaults to production)        |
| `MINITEST_APPS_MANAGER_URL`   | apps-manager base URL (used by `minitest apps create`)     | No (defaults to production)        |
| `MINITEST_INTEGRATIONS_URL`   | minihands-integrations base URL (used to list tenants)     | No (defaults to production)        |
| `MINITEST_WEBAPP_URL`         | Minitest webapp base URL (used for review links)            | No (defaults to production)        |
| `MINITEST_SUPABASE_URL`       | Supabase project URL used for OAuth login                  | No (defaults to production)        |
| `MINITEST_SUPABASE_PUBLISHABLE_KEY` | Supabase publishable (anon) key used for OAuth login | No (defaults to production)        |

> The recommended way to set these is to copy `.env.example` to `.env` — the CLI loads `.env` automatically. The shipped `.env.example` already targets the **dev** environment (see below).

## Global Flags

| Flag                 | Description                                      |
| -------------------- | ------------------------------------------------ |
| `--json`             | Output JSON to stdout (diagnostics go to stderr) |
| `--app <id-or-name>` | Target app for commands that require one         |
| `--version`          | Show CLI version                                 |
| `--help`             | Show help                                        |

## Commands

| Command          | Description               |
| ---------------- | ------------------------- |
| `minitest auth`  | Authentication management |
| `minitest apps`  | App management            |
| `minitest user-story` | User-story operations |
| `minitest build` | Native iOS/Android build management |
| `minitest run`   | Test execution for mobile and web lanes |
| `minitest maintenance` | CLI-only test-flow maintenance against local code |

## CLI-only maintenance

`minitest maintenance` lets a coding agent keep Minitest user stories in sync
without connecting GitHub. Run it from the app repository: the code stays on the
machine, while the CLI sends only proposed test-flow edits and the local HEAD SHA.

```bash
# Print the server-composed maintenance instructions for your coding agent
minitest maintenance --agent

# Agent workflow primitives
minitest --json maintenance context
minitest maintenance affected --file affected.json
minitest maintenance change --file change.json
minitest maintenance status --phase writing --message "Updating affected stories"
minitest maintenance complete --changed

# Apply proposed edits now, or open the web review queue
minitest maintenance apply
minitest maintenance apply --review
```

## Exit Codes

| Code | Meaning              |
| ---- | -------------------- |
| 0    | Success              |
| 1    | General error        |
| 2    | Authentication error |
| 3    | Network / API error  |
| 4    | Resource not found   |

## Using the Dev Environment

The shipped `.env.example` already targets the **dev** environment, so pointing the CLI at dev is just a matter of loading it. Copy it to `.env` once:

```bash
cp .env.example .env
```

The CLI loads `.env` automatically, so every command now runs against dev — no per-command environment variables needed:

```bash
minitest auth login      # authenticates against dev, stores a dev-specific token
minitest apps list       # runs against dev
```

To target **production** instead, either omit the `.env` file (the built-in defaults point at production) or comment out the dev values and uncomment the `# Production` lines in your `.env`.

> **Tip:** You can still override any single variable inline for a one-off command, e.g. `MINITEST_API_URL=https://testing-service.dev.minitap.ai minitest apps list`.

## Development

```bash
# Install dependencies
uv sync --dev

# Run linter
uv run ruff check .

# Run formatter
uv run ruff format .

# Run type checker
uv run pyright

# Run tests
uv run pytest
```
