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

# Inspect one app's full configuration
minitest apps get <app-id>

# Create a new app on your tenant
minitest apps create --name "My Mobile App" --platform ios --platform android

# Or create a web app target
minitest apps create --name "My Web App" --platform web --web-url https://example.com

# Upload native builds when testing iOS/Android apps
minitest --app <app-id> build upload ./app-release.apk
# Android App Bundle archives (.apks) are also accepted
minitest --app <app-id> build upload ./app-release.apks

# Run tests
minitest --app <app-id> run all --web
# or, for native lanes:
minitest --app <app-id> run all --ios-build <ios-build-id> --android-build <android-build-id>
```

## Native cloud tablets

Native lanes default to phones. Use `--ios-device-type phone|tablet` or
`--android-device-type phone|tablet` on `run start` (including `--tag`), `run all`,
or `run from-commit` to configure an already selected native cloud lane:

```bash
minitest --app <app-id> run all --ios-build <ios-build-id> --ios-device-type tablet
minitest --app <app-id> run start --tag smoke --android-build <android-build-id> --android-device-type tablet
minitest --app <app-id> run from-commit <full-sha> --platform ios --ios-device-type tablet
```

The device-type options do not select an OS: `start`/`all` still need the
corresponding build flag; `from-commit` uses `--platform` (or its existing iOS +
Android default). An explicit device type, even `phone`, errors when that OS is
not selected. These options do not apply to physical devices, web/mobile-web
targets, or Edge. V1 supports one form factor per OS per run; run phone and
tablet suites separately. Tablet results are labelled `iOS · Tablet` or
`Android · Tablet`; phone labels stay unchanged.

An iPhone-only build may run on iPad in compatibility mode; the server warns
that the run does not establish native tablet-layout coverage. Unknown
device-family metadata produces a different warning with the same coverage
limitation. Neither warning blocks launch. These per-run options do not change
app defaults.

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
| `minitest apps`  | List, inspect, and create apps |
| `minitest scenario` | Create, update, list and delete scenarios |
| `minitest scenario-binding` | Bind test accounts, test files or app skills to scenarios |
| `minitest draft` | Drafts — branches of the test suite |
| `minitest test-profile` | Test profiles (Test accounts in the webapp) |
| `minitest tags`  | List, create, update and delete scenario tags |
| `minitest app-skill` | App skills (Skills in the webapp): procedures Mini loads to arrange test state |
| `minitest screens` | Inspect the screens exploration mapped for an app |
| `minitest build` | Native iOS/Android build management |
| `minitest run`   | Start runs and inspect their scenario runs |
| `minitest batch` | List, inspect and cancel runs (a batch is a Run in the webapp) |
| `minitest issues` | Read app issues and their fix prompts, mark them fixed |
| `minitest maintenance` | CLI-only scenario maintenance against local code |
| `minitest skill` | Print the CLI skill for your AI coding agent (not app skills) |

### Deprecated names

Old names keep working as hidden aliases: they print a deprecation warning on
stderr and leave `--json` stdout unchanged. Switch to the new names.

| Deprecated | Use instead |
| ---------- | ----------- |
| `minitest user-story` | `minitest scenario` |
| `minitest user-story-binding` | `minitest scenario-binding` |
| `minitest scenario-binding set-skills` | `minitest scenario-binding set-app-skills` |
| `minitest df` | `minitest draft` |
| `minitest flow-types` | `minitest tags` |
| `run from-commit --user-story` / `-u` | `run from-commit --scenario` / `-s` |
| `batch list --user-story-id` | `batch list --scenario` |
| `run cancel --srp`, `run recording --srp` | `--target-id` |
| `--type` on `scenario create/update/list` | `--tag` |

## CLI-only maintenance

`minitest maintenance` lets a coding agent keep Minitest scenarios in sync
without connecting GitHub. Run it from the app repository: the code stays on the
machine, while the CLI sends only proposed scenario edits and the local HEAD SHA.

```bash
# Print the server-composed maintenance instructions for your coding agent
minitest maintenance --agent

# Agent workflow primitives
minitest --json maintenance context
minitest maintenance affected --file affected.json
minitest maintenance change --file change.json
minitest maintenance status --phase writing --message "Updating affected scenarios"
minitest maintenance complete --changed

# Apply proposed edits now, or open the web review queue
minitest maintenance apply
minitest maintenance apply --review
```

## Exit Codes

| Code | Meaning                                            |
| ---- | -------------------------------------------------- |
| 0    | Success                                            |
| 1    | General error                                      |
| 2    | Authentication error                               |
| 3    | Network / API error                                |
| 4    | Resource not found                                 |
| 5    | Build rejected as invalid                          |
| 6    | Conflict — re-read, rebuild, retry once            |

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
