# AGENTS.md - minitest-cli

## Commands

```bash
uv run minitest --help                             # Show CLI help
uv run pytest                                      # Run tests
uv run ruff check .                                # Lint
uv run ruff format .                               # Format
uv run pyright                                     # Type check
uv add <package>                                   # Add new dependency (always use uv add, never edit pyproject.toml manually)
```

## Project Structure

- `src/minitest_cli/` - Main package
- `commands/` - One Typer sub-app per command group (auth, apps, flow, build, run)
- `core/`
  - `config.py` - pydantic-settings: MINITEST_API_URL, MINITEST_TOKEN, config dir
  - `app_context.py` - --app flag / MINITEST_APP_ID resolution
  - `auth.py` - Token storage (read/write ~/.minitest/credentials.json)
- `api/client.py` - httpx async client with auto auth + X-Minitest-Channel and X-Minitap-Cli (minitest/<version>) headers
- `utils/`
  - `output.py` - --json helpers: stdout=data, stderr=diagnostics
  - `update_check.py` - PyPI version check (cached 1h, non-blocking); hands newer releases to auto-update
  - `auto_update*.py` - background self-update of the CLI and agent skill: eligibility and plan (`auto_update.py`), lock/state/running-command registry and the saved on/off preference (`auto_update_state.py`, toggled by `minitest upgrade auto`, `commands/upgrade_auto.py`), one-time notices, and the detached worker (`python -m minitest_cli.utils.auto_update_worker`). Tests run with `MINITEST_NO_AUTO_UPDATE=1` (conftest) so they never touch the real install.
- `main.py` - Typer app entry point, global flags, command group registration
- `tests/` - Unit tests

## Coding Guidelines

### Imports
- ALWAYS use absolute imports (relative imports banned by ruff)
- ALWAYS place imports at the top of the file
- Order: standard library → third-party → local imports

### Naming
- Files/modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Test files: `test_*.py`

### Code Style
- Keep files under 150 lines when possible
- Use `X | None` syntax (not `Optional[X]`)
- Use `Annotated[Type, ...]` for Typer parameters
- Enums: inherit from `str, Enum`

### Output Convention
- `--json` flag: JSON to stdout, diagnostics to stderr
- Without `--json`: human-friendly rich tables to stdout, diagnostics to stderr
- Exit codes: 0=Success, 1=General error, 2=Auth error, 3=Network/API error, 4=Not found, 5=Build invalid

### No Interactive Prompts
- All input via flags, env vars, or stdin
- Never prompt for input interactively

### Testing
- Group tests in classes by feature
- Name tests: `test_<action>_<scenario>`
- Always check exit codes and output

### Agent Skill (CRITICAL)
The agent skill lives in this repo at `skills/minitest-cli/` and ships **inside the wheel** (`minitest_cli/_skills/minitest-cli`), so the skill an agent reads is always the one of the CLI version installed. There is no paired PR: change the command and its documentation in the same PR.

When you add, remove, or change a CLI command/flag, update `skills/minitest-cli/SKILL.md` (and the Quick Reference table) in that PR.

- **Hand-maintained:** `SKILL.md`, `README.md`, `commands/`.
- **Generated, never hand-edit:** `reference/*.md` and `reference/index.json`. testing-service renders the documents from its knowledge fragments and serves them on its public `GET /api/skills/reference[/{topic}]` routes, which `minitest reference [TOPIC]` reads live (topic names come from the server, never from CLI code). The committed files are the offline / older-backend fallback: `python3 scripts/sync-skill-references.py [--api-url URL]` refreshes them from the server (production by default, no credentials), `release.yml` runs it before building, and `ci.yml` runs `--check` so the index and the files cannot drift. `minitest-target.md` is no longer bundled: the executor envelope is `minitest capabilities` (testing-service images re-render it into the skill they bake; conductor bakes it as its own `minitest-capabilities` skill).
- **Stamped at read time:** `metadata.cli-version` in the SKILL.md frontmatter is added by `utils/skill_bundle.py` from the running version. Do not write it in the file.

How it reaches users: `minitest skill` prints the bundled skill (offline). `minitest upgrade` and the background auto-update make every installed copy (found via `npx skills ls`, or `~/.agents|.claude/skills/minitest-cli` without npx) byte-identical to the bundled one, references included. First install: `npx skills add https://github.com/minitap-ai/minitest-cli/tree/v<version>/skills/minitest-cli --skill minitest-cli`. `ci.yml` and `release.yml` run `scripts/check-dist-skill.py` so a build that drops the skill fails.

`minitap-ai/agent-skills` still holds a frozen copy for CLIs older than the release that introduced this; do not update it.
