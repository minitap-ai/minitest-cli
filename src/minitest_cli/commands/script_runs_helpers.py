"""Fetching a script run and picking one of its tests."""

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.run_helpers import EXIT_NOT_FOUND, handle_response_error
from minitest_cli.core.config import Settings
from minitest_cli.models.script_run import ScriptCase, ScriptRunDetail, ScriptSession
from minitest_cli.utils.output import print_error

RUN_RETENTION = "script runs are kept 90 days"


def script_runs_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/script-runs"


def reported_tests(run: ScriptRunDetail) -> ScriptRunDetail:
    """Each test a reporter sent (Playwright) becomes one test: its last attempt, whichever worker
    session ran it (a retry runs in a new worker), with its own trace and video. Sessions without
    reported tests stay one test each."""
    last: dict[str, tuple[ScriptSession, ScriptCase]] = {}
    for session in run.sessions:
        for case in session.cases:
            if case.test_key and (case.retry or 0) >= (
                last.get(case.test_key, (session, case))[1].retry or 0
            ):
                last[case.test_key] = (session, case)
    tests = [s for s in run.sessions if not any(c.test_key for c in s.cases)]
    tests += [
        session.model_copy(
            update={
                "scripted_run_id": f"{session.scripted_run_id}#{case.position}",
                "name": case.name,
                "status": case.status,
                "cases": [case],
                "video_url": case.video_url or session.video_url,
                "trace_url": case.trace_url or session.trace_url,
            }
        )
        for session, case in last.values()
    ]
    return run.model_copy(update={"sessions": tests})


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


def status_label(session: ScriptSession) -> str:
    """Its status, and the retries a reported test took to get there."""
    retry = max((c.retry or 0 for c in session.cases), default=0)
    return f"{session.status} (retry {retry})" if retry else session.status


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
    return [sorted(group, key=_device_order) for group in groups]


_PLATFORM_ORDER = ("android", "ios", "web")


def _device_order(session: ScriptSession) -> tuple[int, int, float]:
    """Android before iOS, phones before tablets, newest OS first: as the webapp lists them."""
    target = session.device_target
    platform = session.platform or ""
    rank = _PLATFORM_ORDER.index(platform) if platform in _PLATFORM_ORDER else len(_PLATFORM_ORDER)
    tablet = int(target is not None and target.model == "tablet")
    version = (target.os_version if target else None) or (
        session.device.os_version if session.device else None
    )
    try:
        os_version = float(version or 0)
    except ValueError:
        os_version = 0.0
    return rank, tablet, -os_version


def worst_status(sessions: list[ScriptSession]) -> str:
    statuses = {session.status for session in sessions}
    return next((s for s in _WORST_FIRST if s in statuses), sessions[0].status)


def platform_label(session: ScriptSession) -> str:
    return _PLATFORM_NAMES.get(session.platform or "", session.platform or "")


_BROWSER_NAMES = {"chrome": "Chrome", "edge": "Edge", "firefox": "Firefox"}


def browser_label(session: ScriptSession) -> str | None:
    """ "Chrome 157 · 1280×800", as the webapp; None for a session that got no browser."""
    target = session.device_target
    if target is None or target.backend != "browser" or target.browser_name is None:
        return None
    name = _BROWSER_NAMES.get(target.browser_name, target.browser_name)
    browser = f"{name} {target.browser_version}" if target.browser_version else name
    size = target.viewport.replace("x", "×") if target.viewport else None
    return " · ".join(part for part in (browser, size) if part)


def device_label(session: ScriptSession) -> str:
    """The device as the webapp names it: the target given, else what the device reported."""
    browser = browser_label(session)
    if browser is not None:
        return browser
    os_name = _PLATFORM_NAMES.get(session.platform or "", "OS")
    target = session.device_target
    version = target.os_version if target else None
    reported = session.device.model if session.device else None
    if session.platform == "ios" and (target is None or target.backend != "physical"):
        model = f"{reported} simulator" if reported else "iPhone simulator"
    elif target is not None and target.model is not None:
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


def shorten(text: str | None, width: int = 80) -> str:
    line = " ".join((text or "").split())
    return line if len(line) <= width else f"{line[: width - 1]}…"
