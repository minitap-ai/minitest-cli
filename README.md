# minitest-cli

Command-line interface for the Minitest testing platform.

## Installation

### curl (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/minitap-ai/minitest-cli/main/install.sh | bash
```

This auto-detects and uses the fastest available method (`uv` > `brew`).
If neither is installed, it bootstraps `uv` automatically.

### uv

```bash
uv tool install minitest-cli
```

### Homebrew

```bash
brew install minitap-ai/tap/minitest-cli
```

### uvx (zero-install)

Run without installing:

```bash
uvx --from minitest-cli minitest --help
```

### From source

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

# Run tests
minitest run --app <app-id>
```

## Configuration

| Environment Variable | Description              | Required                           |
| -------------------- | ------------------------ | ---------------------------------- |
| `MINITEST_TOKEN`     | API authentication token | Yes (or use `minitest auth login`) |
| `MINITEST_APP_ID`    | Default app ID           | No (can use `--app` flag)          |
| `MINITEST_API_URL`   | API base URL             | No (defaults to production)        |

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
| `minitest flow`  | Testing flow operations   |
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
minitest auth login
```

This authenticates against the dev environment and stores a dev-specific auth token. After logging in, keep the same variables set for all subsequent commands:

```bash
MINITEST_SUPABASE_URL=https://qrezuucghnmfvaxghqsv.supabase.co \
MINITEST_SUPABASE_PUBLISHABLE_KEY=sb_publishable_4JRhoCm8pa5PbII0dhS09A_jhpkQhmy \
MINITEST_API_URL=https://testing-service.dev.minitap.ai \
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
