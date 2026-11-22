"""What `script-runs submit` prints once the job is done: one row per test, then whole failures."""

from rich.console import Console

from minitest_cli.commands.script_runs_helpers import failure_reason, minitap_issue
from minitest_cli.models.script_run import ScriptJobUnit


def _first_line(text: str | None) -> str:
    return (text or "").strip().split("\n", 1)[0][:200]


def result_rows(units: list[ScriptJobUnit]) -> list[list[str]]:
    rows: list[list[str]] = []
    for unit in units:
        tests = unit.cases or [None]
        for case in tests:
            failure = case.failure_message if case else failure_reason(unit)
            rows.append(
                [
                    unit.unit or "",
                    case.name if case else (unit.name or ""),
                    case.status if case else unit.state,
                    _first_line(failure),
                    minitap_issue(unit) or "",
                ]
            )
    return rows


def print_failures(units: list[ScriptJobUnit]) -> None:
    """The whole failure of each failed test (an Espresso stack trace...), after the table."""
    console = Console()
    for unit in units:
        for case in unit.cases or []:
            if case.failure_message and "\n" in case.failure_message.strip():
                console.rule(f"{unit.unit} {case.name}", align="left")
                console.print(case.failure_message.strip(), markup=False, highlight=False)
