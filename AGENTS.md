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
- `api/client.py` - httpx async client with auto auth + X-Minitest-Channel header
- `utils/`
  - `output.py` - --json helpers: stdout=data, stderr=diagnostics
  - `update_check.py` - PyPI version check (cached 24h, non-blocking)
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
- Exit codes: 0=Success, 1=General error, 2=Auth error, 3=Network/API error, 4=Not found

### No Interactive Prompts
- All input via flags, env vars, or stdin
- Never prompt for input interactively

### Testing
- Group tests in classes by feature
- Name tests: `test_<action>_<scenario>`
- Always check exit codes and output
