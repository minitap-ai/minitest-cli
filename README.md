# minitest-cli

Command-line interface for the Minitest testing platform.

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
minitest apps create --name "My App"

# Run tests
minitest run --app <app-id>
```

## Configuration

| Environment Variable          | Description                                                | Required                           |
| ----------------------------- | ---------------------------------------------------------- | ---------------------------------- |
| `MINITEST_TOKEN`              | API authentication token                                   | Yes (or use `minitest auth login`) |
| `MINITEST_APP_ID`             | Default app ID                                             | No (can use `--app` flag)          |
| `MINITEST_API_URL`            | testing-service base URL                                   | No (defaults to production)        |
| `MINITEST_APPS_MANAGER_URL`   | apps-manager base URL (used by `minitest apps create`)     | No (defaults to production)        |
| `MINITEST_INTEGRATIONS_URL`   | minihands-integrations base URL (used to list tenants)     | No (defaults to production)        |

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
| `minitest build` | Build management          |
| `minitest run`   | Test execution            |

## Exit Codes

| Code | Meaning              |
| ---- | -------------------- |
| 0    | Success              |
| 1    | General error        |
| 2    | Authentication error |
| 3    | Network / API error  |
| 4    | Resource not found   |

## Using the Dev Environment

To point the CLI at the **dev** environment instead of production, set these environment variables when running `minitest`:

```bash
MINITEST_SUPABASE_URL=https://qrezuucghnmfvaxghqsv.supabase.co \
MINITEST_SUPABASE_PUBLISHABLE_KEY=sb_publishable_4JRhoCm8pa5PbII0dhS09A_jhpkQhmy \
MINITEST_API_URL=https://testing-service.dev.minitap.ai \
MINITEST_APPS_MANAGER_URL=https://apps-manager.dev.minitap.ai \
MINITEST_INTEGRATIONS_URL=https://integrations.dev.minitap.ai \
minitest auth login
```

This authenticates against the dev environment and stores a dev-specific auth token. After logging in, keep the same variables set for all subsequent commands:

```bash
MINITEST_SUPABASE_URL=https://qrezuucghnmfvaxghqsv.supabase.co \
MINITEST_SUPABASE_PUBLISHABLE_KEY=sb_publishable_4JRhoCm8pa5PbII0dhS09A_jhpkQhmy \
MINITEST_API_URL=https://testing-service.dev.minitap.ai \
MINITEST_APPS_MANAGER_URL=https://apps-manager.dev.minitap.ai \
MINITEST_INTEGRATIONS_URL=https://integrations.dev.minitap.ai \
minitest apps list
```

> **Tip:** You can `export` these variables in your shell session (or add them to a `.envrc` / `.env` file) to avoid repeating them on every invocation.

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
