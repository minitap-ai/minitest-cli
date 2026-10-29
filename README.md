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

### Staying up to date

A CLI installed with `uv tool install` or the one-liner keeps itself
current. When a command sees a newer release on PyPI, it updates the CLI in the
background and your next command runs the new version. The update waits until
no other `minitest` command is running, and only installs releases that have
been out for at least an hour. The same background job refreshes the agent
skill (the copy bundled with the new CLI version, no network needed) when it has changed. The next command
prints one line saying what was updated; the details go to
`~/.minitest/auto_update.log`.

Auto-update never runs in CI (`CI` set), in containers, on Windows, or for
`uvx` and source checkouts; those keep printing an "Update available" notice.

```bash
minitest upgrade auto        # show the setting, why it is off, the last update
minitest upgrade auto off    # turn it off for this user (saved in ~/.minitest/preferences.json)
minitest upgrade auto on     # turn it back on
minitest upgrade             # update by hand at any time
```

`MINITEST_NO_AUTO_UPDATE=1` also turns it off, and wins over the saved setting.

> **Installed with Homebrew?** minitest-cli is no longer published on Homebrew:
> a copy installed from the old tap stopped at 0.24.0 and never updates itself.
> Switch to uv with `brew uninstall minitest-cli && uv tool install minitest-cli`.

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
# An Android App Bundle (.aab) works for both emulators and physical phones
minitest --app <app-id> build upload ./app-release.aab

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

## Physical devices

By default builds run on virtual devices (iOS Simulator, Android emulator). If
physical devices are enabled for your workspace, upload a device build with
`--physical` and select the physical lane when you start the run:

```bash
# iOS: an Ad Hoc or Development .ipa signed for Minitap's iPhones
BUILD_ID=$(minitest --json --app <app-id> build upload ./MyApp.ipa --physical | jq -r .id)
minitest --app <app-id> run all --ios-build "$BUILD_ID" --ios-physical

# Android: the same works with --android-physical
minitest --app <app-id> run start --tag smoke --android-build <android-build-id> --android-physical

# Android: an .aab needs no --physical; its id works on emulators and phones
BUILD_ID=$(minitest --json --app <app-id> build upload ./app-release.aab | jq -r .id)
minitest --app <app-id> run start --tag smoke --android-build "$BUILD_ID" --android-physical
```

An `.aab` with asset packs converts into two builds: one for cloud emulators
(x86_64, the id `build upload` returns) and one for physical phones (arm64).
`build upload` waits for both, lists them, and says which devices the upload
can run on (`supportedBackends` in `--json`). Pass the returned id to
`--android-build`: Minitap picks the right build for each device. A bundle
without asset packs converts into a single universal build. `--physical` is not
needed for an `.aab`. If only one of the two builds converts, the upload still
succeeds with a warning; it fails only when none converts.

- `build upload --physical` checks the build for physical devices instead of
  virtual ones. A Simulator build is rejected (`ios.simulator_only_ipa`), and a
  device build uploaded without `--physical` is rejected with a hint to add it.
- A physical Android run on a build with only x86_64 native libraries is
  refused, with a hint to upload the `.aab` or an arm64 build instead.
- `--ios-physical` / `--android-physical` need the matching `--ios-build` /
  `--android-build`, and can't be combined with `--*-device-type`.
- If physical devices aren't enabled for your workspace, the run is refused
  with a message saying so.

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
| `MINITEST_CONDUCTOR_URL`      | Conductor base URL (used by `minitest draft`)              | No (defaults to production)        |
| `MINITEST_INTEGRATIONS_URL`   | minihands-integrations base URL (used to list tenants)     | No (defaults to production)        |
| `MINITEST_WEBAPP_URL`         | Minitest webapp base URL (used for review links)            | No (defaults to production)        |
| `MINITEST_SUPABASE_URL`       | Supabase project URL used for OAuth login                  | No (defaults to production)        |
| `MINITEST_SUPABASE_PUBLISHABLE_KEY` | Supabase publishable (anon) key used for OAuth login | No (defaults to production)        |
| `MINITEST_NO_AUTO_UPDATE`     | Set to `1` to stop the CLI and agent skill from updating themselves (or run `minitest upgrade auto off`) | No |

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
| `minitest apps`  | List, inspect, and create apps; residential proxy and private network settings |
| `minitest scenario` | Create, update, list and delete scenarios |
| `minitest scenario-binding` | Bind test accounts, test files or app skills to scenarios |
| `minitest draft` | Ask Mini for a suite change, follow it, check and merge it (drafts in the webapp) |
| `minitest df` | Low-level suite branches Mini writes (draft features) |
| `minitest test-profile` | Test profiles (Test accounts in the webapp) |
| `minitest tags`  | List, create, update and delete scenario tags |
| `minitest brief` | Product brief: what the app is, who uses it, its core flows (Knowledge v2) |
| `minitest app-guide` | App guide: how to use the app when testing it (Knowledge v2) |
| `minitest glossary` | Glossary: product terms, their meaning and aliases (Knowledge v2) |
| `minitest knowledge` | Change history of the brief, app guide and glossary, and reverts |
| `minitest app-knowledge` | The single Memory document of workspaces without Knowledge v2 |
| `minitest app-skill` | App skills (Skills in the webapp): procedures Mini loads to arrange test state |
| `minitest secret` | App secrets vault: passwords, OTP seeds, cards, API tokens referenced as `{{secret:NAME}}` (write-only values) |
| `minitest screens` | Inspect the screens exploration mapped for an app |
| `minitest build` | Native iOS/Android build management |
| `minitest run`   | Start runs and inspect their scenario runs |
| `minitest batch` | List, inspect and cancel runs (a batch is a Run in the webapp) |
| `minitest schedules` | Scheduled runs: run scenarios at a set time and post a Slack summary |
| `minitest issues` | Read app issues and their fix prompts, mark them fixed |
| `minitest skill` | Print the CLI skill for your AI coding agent (not app skills) |

### Deprecated names

Old names keep working as hidden aliases: they print a deprecation warning on
stderr and leave `--json` stdout unchanged. Switch to the new names.

| Deprecated | Use instead |
| ---------- | ----------- |
| `minitest user-story` | `minitest scenario` |
| `minitest user-story-binding` | `minitest scenario-binding` |
| `minitest scenario-binding set-skills` | `minitest scenario-binding set-app-skills` |
| `minitest draft show/apply/delete` (v0.34–v0.36) | `minitest df show/apply/delete` |
| `minitest flow-types` | `minitest tags` |
| `run from-commit --user-story` / `-u` | `run from-commit --scenario` / `-s` |
| `batch list --user-story-id` | `batch list --scenario` |
| `run cancel --srp`, `run recording --srp` | `--target-id` |
| `--type` on `scenario create/update/list` | `--tag` |

## Scheduled runs

A schedule starts an ordinary run on its own at a wall-clock time on chosen
weekdays, then posts one summary to a Slack channel. What runs (the whole suite,
tags minus exclusions, or picked scenarios) is re-resolved at every start, so
scenarios tagged later join on their own.

```bash
# Weekdays at 03:00 (this machine's timezone), tagged scenarios on desktop and Android Chrome
minitest schedules create --name "Nightly sanity check" --at 03:00 \
  --tag Navigation --exclude "Deals page opens" \
  --url https://www.example.com --browser chrome --browser chrome:android \
  --slack-channel C0123ABCD --slack-channel-name minitap

# Native: newest installable build on Android, a fixed iOS build, every day in Oslo
minitest schedules create --name "Monitoring" --at 05:00 --days every-day --timezone Europe/Oslo \
  --android --ios-build <build-id> --slack-channel C0123ABCD

minitest schedules preview "Nightly sanity check"     # duration, builds tonight would pick, next starts
minitest schedules list                               # cadence, next run, scenario count
minitest --json schedules get "Nightly sanity check" > nightly.json
minitest schedules create --from-file nightly.json --name "Nightly copy"   # JSON or YAML
minitest schedules update "Nightly sanity check" --at 04:00 --android-branch main
minitest schedules pause|resume "Nightly sanity check"
minitest schedules run "Nightly sanity check"         # start one now (posts to Slack too)
minitest schedules fires "Nightly sanity check"       # last runs: verdict, new / still open / fixed, or why it didn't run
minitest schedules delete "Nightly sanity check" --yes   # `schedules restore <id>` undoes it
```

Platforms: `--browser BROWSER[:SURFACE]` (`chrome`, `chrome:mobile`,
`chrome:tablet`, `chrome:android`, `safari:ios`…) tests `--url` or builds
`--web-branch` first. `--ios` / `--android` run the newest build that installs;
`--<platform>-build <id>` pins one build, `--<platform>-branch <branch>` builds
the branch before each run. On `update`, any `--<platform>-*` flag redefines that
platform, `--browser` replaces the browsers, `--drop web|ios|android` removes one.

A night that can't run is still a fire, with a reason (out of credits, no
installable build, branch build failed, previous run still going, no phone
free…); `fires` shows it and Slack gets a message. On a server without
scheduled runs, every command exits 4 with `Scheduled runs are not available
on this workspace yet.`

## Knowledge

On workspaces with Knowledge v2, what Mini knows about an app is split by job:

| Element | Holds | Commands |
| ------- | ----- | -------- |
| Product brief | What the app is, who uses it, its core flows. Short (max 2000 chars). | `brief get`, `brief update --content/--content-file` |
| App guide | How to use the app when testing: navigation, quirks, test data. | `app-guide get`, `app-guide update --content/--content-file` |
| Glossary | Product terms and what they mean, with aliases. | `glossary list`, `glossary add --term --meaning [--alias]`, `glossary update <id-or-term>`, `glossary remove <id-or-term> --yes` |

Every change is versioned with its author and channel (`cli` for these
commands): `minitest knowledge history [--element product_brief|app_guide|glossary]`
lists each change with its version ID, and `minitest knowledge revert <version-id>`
restores that version as a new `reverted` change.
On a workspace without Knowledge v2, writes fail with a message pointing to
`minitest app-knowledge`.

## Secrets

Credentials live in the app's vault, never in scenario text. Write
`{{secret:NAME}}` (card fields: `{{secret:NAME.number}}`, `.expiry`, `.cvc`,
`.holder_name`, `.postal_code`) where Mini must type one; `$NAME` still works
but `secret lint` warns. Values are write-only: no command prints one back.
Workspaces without the feature get `Secrets are not enabled for this workspace yet` (exit 4).

```bash
printf '%s' "$ADMIN_PW" | minitest secret set ADMIN_PASSWORD --kind password --note "Admin login"
echo '{"number":"<number>","expiry":"<MM/YY>","cvc":"<cvc>"}' \
  | minitest secret set STRIPE_CARD --kind card          # optional holder_name, postal_code
minitest secret create QA_PASSWORD --kind password --generate [--length 24] [--charset default|alnum]
minitest secret create SANDBOX_KEY --kind token --empty --reason "Checkout calls the sandbox" [--scenario <id>]
minitest secret list [--missing]                         # names, kinds, state (set / missing + reason), usages
minitest secret describe ADMIN_PASSWORD                  # usages + reference to copy
minitest secret lint --scenario <id>                     # exit 1 on leaks or missing; warns on pending
minitest secret extract <id> --as ADMIN_PASSWORD --kind password [--dry-run]
minitest test-profile update <id> --password-secret ADMIN_PASSWORD
```

`set` reads stdin only and refuses a terminal (`--interactive` opens a hidden
prompt) and also fills a secret that is waiting for a value. Inside a test run
(`MINITAP_SECRETS_SOCKET` or `STORY_RUN_ID` set) it refuses: use `secret create`
instead, which never handles a value. `--generate` (password, token, text) lets
the server pick a random value (default 24 chars, 12–64); `--empty --reason`
creates the secret without a value for a human to fill, and runs that need it
wait until then. Personas can point at either (`--password-secret` etc.).
`secret request` is a deprecated alias of `create --empty`; on servers that
predate `create`, `--empty` falls back to the old request endpoint.
`extract` reads the leaked literal from the scenario on your machine, creates
the secret with it, then rewrites every occurrence to `{{secret:NAME}}`. Older
scenario versions and past run logs may still hold the literal: rotate it.

## App network settings

Two per-app settings decide how test devices reach the network. Anyone on the
app can read them; only workspace **owners and admins** can change them (other
roles get `Only workspace owners and admins can change this setting`, exit 2).
`set` reads the current settings first and changes only what you pass.
Domains are an exact host (`api.stg.example.com`) or `*.example.com`, which
matches subdomains only, not `example.com` itself.

```bash
# Residential proxy: reach the listed domains from a residential IP in one country
minitest --app <app-id> apps residential-proxy show
minitest --app <app-id> apps residential-proxy set [--enable|--disable] [--country tr] \
  [--domain ipinfo.io ...] [--remove-domain <d> ...] [--clear-domains]

# Private network: reach internal domains through a connector running in your network
minitest --app <app-id> apps private-network show
minitest --app <app-id> apps private-network connectors
minitest --app <app-id> apps private-network set [--enable|--disable] [--connector <name-or-id>] \
  [--domain api.stg.corp.internal ...] [--remove-domain <d> ...] [--clear-domains] [--port 443 ...]
```

`--clear-domains --domain a --domain b` replaces the list; `--port` replaces the
ports (default 443). Turning the private network on needs a connector and at
least one domain. Connectors cannot be created from the CLI: a workspace owner
or admin creates them in the webapp, under **Workspace settings → Private
network**.

## Backend API

Mini can read the OpenAPI document of a backend you own and call it during runs,
authenticated with app vault secrets (it is off by default). `set` reads the
current settings first and changes only what you pass.

```bash
minitest --app <app-id> apps backend-api show
minitest --app <app-id> apps backend-api set --enable \
  --base-url https://api.staging.example.com \
  --openapi-url https://api.staging.example.com/openapi.json \
  --secret API_TOKEN [--remove-secret <name> ...] [--clear-secrets] \
  [--skill <name-or-id> | --clear-skill]
minitest --app <app-id> apps backend-api set --disable
```

Secrets are named references to the app vault (`minitest secret set`); `show`
warns about names no longer in the vault. URLs must be public `http(s)`
addresses: private, loopback and cloud-metadata addresses are rejected.

When the OpenAPI document itself needs authentication, say how to download it.
The credential comes from the app vault, is used for that download only, and is
sent only to the saved OpenAPI URL's origin (a one-run OpenAPI URL on another
origin gets none):

```bash
minitest --app <app-id> apps backend-api set --openapi-auth bearer --openapi-auth-secret API_TOKEN
minitest --app <app-id> apps backend-api set --openapi-auth header \
  --openapi-auth-header X-Api-Key --openapi-auth-secret API_TOKEN
minitest --app <app-id> apps backend-api set --openapi-auth basic \
  --openapi-auth-username docs-reader --openapi-auth-secret DOCS_PASSWORD
minitest --app <app-id> apps backend-api set --openapi-auth query \
  --openapi-auth-param api_key --openapi-auth-secret API_TOKEN
minitest --app <app-id> apps backend-api set --openapi-auth none
```

To point one run at another backend, pass `--backend-base-url` and/or
`--backend-openapi-url` to `run start`, `run all` or `run from-commit`. Only
that run uses them; the saved settings do not change, and the app's backend API
must be on.

```bash
minitest --app <app-id> run all --web \
  --backend-base-url https://pr-42.api.example.com \
  --backend-openapi-url https://pr-42.api.example.com/openapi.json
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
