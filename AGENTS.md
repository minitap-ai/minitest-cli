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
- `commands/` - One Typer sub-app per command group (auth, apps, flow, build, run, maintenance)
- `core/`
  - `config.py` - pydantic-settings: MINITEST_API_URL, MINITEST_TOKEN, config dir
  - `app_context.py` - --app flag / MINITEST_APP_ID resolution
  - `auth.py` - Token storage (read/write ~/.minitest/credentials.json)
- `api/client.py` - httpx async client with auto auth + X-Minitest-Channel header
- `utils/`
  - `output.py` - --json helpers: stdout=data, stderr=diagnostics
  - `update_check.py` - PyPI version check (cached 24h, non-blocking)
- `main.py` - Typer app entry point, global flags, command group registration
- `tests/` - Unit tests

## Deployment

`minitest-cli` is a **public** CLI shipped to end users. Unlike `mobile-use-cli`, it is **not** continuously deployed: merging to `main` publishes nothing.

A release is triggered by pushing a version tag, and only that:

1. Bump `version` in `pyproject.toml`, then `uv sync` to refresh `uv.lock`
2. Commit both, then `git tag vX.Y.Z && git push origin main && git push origin vX.Y.Z`

The tag push runs `.github/workflows/release.yml`, which builds, publishes to public PyPI (trusted publishing, no token), creates the GitHub Release, and dispatches the Homebrew formula update to `minitap-ai/homebrew-tap`. The tag must match `pyproject.toml` exactly or CI fails.

There is no dev/prod split and no version pin to flip — once the tag is pushed, every user gets it from PyPI, `uvx`, or Homebrew. Ask the user for explicit confirmation before tagging. Full detail and prerequisites: `RELEASE.md`.

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

### Agent Skill Sync (CRITICAL)
The public agent skill at `repos/agent-skills/skills/minitest-cli/SKILL.md` documents every CLI command for AI agents. Customers use the CLI with this skill simultaneously — they MUST stay in sync.

When you add, remove, or change a CLI command/flag:
1. Update `repos/agent-skills/skills/minitest-cli/SKILL.md` in a paired PR
2. Update the Quick Reference table and any relevant sections

The skill now has two writers — do not confuse them:
- **Hand-maintained:** `SKILL.md` and its Quick Reference table. These are the CLI's responsibility; the paired PR above applies to them.
- **CI-generated:** the `reference/*.md` files under `repos/agent-skills/skills/minitest-cli/reference/` are produced by testing-service CI — never hand-edit them. That CI also owns the machine-managed `<!-- skill-references-hash: <sha256> -->` line inside `SKILL.md`, which it bumps whenever the reference files change.

Both file sets ship to users together via `npx skills add/update` (whole-skill sync). The CLI's refresh check (`utils/skill_refresh.py`) md5-compares `SKILL.md` only, so reference-file changes stay visible to `minitest upgrade` solely because the CI-managed hash line flips `SKILL.md`. Leave that hash line alone in hand-written edits.
