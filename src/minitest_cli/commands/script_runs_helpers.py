"""Fetching a script run and picking one of its tests."""

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import EXIT_NOT_FOUND, handle_response_error
from minitest_cli.core.config import Settings
from minitest_cli.models.script_run import ScriptRunDetail, ScriptSession
from minitest_cli.utils.output import print_error

RUN_RETENTION = "script runs are kept 90 days"


def script_runs_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/script-runs"


async def fetch_run(settings: Settings, app_id: str, run_id: str) -> ScriptRunDetail:
    async with ApiClient(settings) as client:
        resp = await client.get(f"{script_runs_path(app_id)}/{run_id}")
    if resp.status_code == 404:
        print_error(f"Script run {run_id} not found for this app ({RUN_RETENTION}).")
        raise typer.Exit(code=EXIT_NOT_FOUND)
    handle_response_error(resp, resource="Script run")
    return ScriptRunDetail.model_validate(resp.json())


def test_label(session: ScriptSession) -> str:
    return session.name or session.external_session_id or session.scripted_run_id


def pick_test(run: ScriptRunDetail, test: str | None) -> ScriptSession:
    """The run's only test, or the one whose id, hub session id or name is `test`."""
    if test is None and len(run.sessions) == 1:
        return run.sessions[0]
    matches = [
        s
        for s in run.sessions
        if test is not None and test in (s.scripted_run_id, s.external_session_id, s.name)
    ]
    if len(matches) == 1:
        return matches[0]
    listing = "\n".join(f"  {s.scripted_run_id}  {test_label(s)}" for s in run.sessions)
    if test is None:
        print_error(f"This run has {len(run.sessions)} tests; pick one with --test:\n{listing}")
        raise typer.Exit(code=1)
    reason = "Several tests match" if matches else "No test matches"
    print_error(f"{reason} '{test}' in this run. Its tests:\n{listing}")
    raise typer.Exit(code=EXIT_NOT_FOUND)


def failure_reason(session: ScriptSession) -> str | None:
    failed = next((c for c in session.cases if c.status in ("failed", "error")), None)
    return failed.failure_message if failed else None


def minitap_issue(session: ScriptSession) -> str | None:
    """How Minitap's side of the session ended, when it did not end well."""
    if session.infra_outcome in (None, "ok"):
        return None
    if session.infra_detail:
        return f"{session.infra_outcome}: {session.infra_detail}"
    return session.infra_outcome


_PLATFORM_NAMES = {"android": "Android", "ios": "iOS", "web": "Web"}


_WORST_FIRST = ("failed", "error", "running", "unmarked", "skipped", "passed")


def group_by_test(sessions: list[ScriptSession]) -> list[list[ScriptSession]]:
    """One group per test across devices, as the webapp; the same test twice on a device is two."""
    groups: list[list[ScriptSession]] = []
    for session in sessions:
        name, device = test_label(session), device_label(session)
        group = next(
            (
                g
                for g in groups
                if test_label(g[0]) == name and all(device_label(o) != device for o in g)
            ),
            None,
        )
        if group is None:
            groups.append([session])
        else:
            group.append(session)
    return groups


def worst_status(sessions: list[ScriptSession]) -> str:
    statuses = {session.status for session in sessions}
    return next((s for s in _WORST_FIRST if s in statuses), sessions[0].status)


def platform_label(session: ScriptSession) -> str:
    return _PLATFORM_NAMES.get(session.platform or "", session.platform or "")


def device_label(session: ScriptSession) -> str:
    """The device as the webapp names it: the target given, else what the device reported."""
    os_name = _PLATFORM_NAMES.get(session.platform or "", "OS")
    target = session.device_target
    version = target.os_version if target else None
    reported = session.device.model if session.device else None
    if session.platform == "ios" and (target is None or target.backend != "physical"):
        model = f"{reported} simulator" if reported else "iPhone simulator"
    elif target is not None:
        model = target.model if target.backend == "physical" else _emulator(target.model)
    else:
        model = reported
    version = version or (session.device.os_version if session.device else None)
    if model is None:
        return ""
    os_version = f"{os_name} {version}" if version else None
    return " · ".join(part for part in (model, os_version) if part)


def _emulator(form_factor: str) -> str:
    return f"{form_factor[:1].upper()}{form_factor[1:]} emulator"
