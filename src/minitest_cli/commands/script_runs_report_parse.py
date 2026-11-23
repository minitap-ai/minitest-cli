"""A Playwright JSON or JUnit XML report as the test attempts testing-service records."""

import json
import xml.etree.ElementTree as ElementTree
from typing import Any

_KEY_MAX = 300
_PLAYWRIGHT_STATUS = {
    "passed": "passed",
    "failed": "failed",
    "timedOut": "failed",
    "interrupted": "error",
    "skipped": "skipped",
}


class ReportError(ValueError):
    pass


def parse_report(content: bytes) -> list[dict[str, Any]]:
    """Each attempt of each test, keyed so that re-sending the report replaces it."""
    text = content.decode("utf-8-sig", errors="replace").lstrip()
    if text.startswith("{"):
        return _playwright(json.loads(text))
    if text.startswith("<"):
        return _junit(text)
    raise ReportError("The report is neither Playwright JSON nor JUnit XML")


def _playwright(report: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(report.get("suites"), list):
        raise ReportError("Not a Playwright JSON report: it has no suites")
    cases: list[dict[str, Any]] = []
    for path, spec in _specs(report["suites"], []):
        for test in spec.get("tests", []):
            project = test.get("projectName") or None
            for result in test.get("results", []):
                cases.append(_attempt(path, spec, project, test, result))
    return cases


def _specs(suites: list[dict[str, Any]], path: list[str]):
    for suite in suites:
        here = [*path, suite["title"]] if suite.get("title") else path
        for spec in suite.get("specs", []):
            yield here, spec
        yield from _specs(suite.get("suites", []), here)


def _attempt(
    path: list[str],
    spec: dict[str, Any],
    project: str | None,
    test: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    error = result.get("error") or {}
    status = _PLAYWRIGHT_STATUS.get(result.get("status", ""), "error")
    key = f"{spec.get('id') or ' › '.join([*path, spec['title']])}@{project or ''}"
    properties = {
        a["type"]: str(a.get("description") or "")
        for a in test.get("annotations", [])
        if isinstance(a, dict) and a.get("type")
    }
    case: dict[str, Any] = {
        "testKey": key[:_KEY_MAX],
        "retry": int(result.get("retry") or 0),
        "classname": " › ".join(path) or None,
        "name": spec["title"],
        "status": status,
        "project": project,
        "durationMs": result.get("duration"),
    }
    if status in ("failed", "error") and error:
        case["failureMessage"] = error.get("message")
        case["failureStack"] = error.get("stack")
    if properties:
        case["properties"] = properties
    return case


def _junit(text: str) -> list[dict[str, Any]]:
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ReportError(f"Not a valid JUnit XML report: {exc}") from exc
    cases: list[dict[str, Any]] = []
    for node in root.iter("testcase"):
        classname, name = node.get("classname") or None, node.get("name") or "(unnamed test)"
        failure = node.find("failure")
        error = node.find("error")
        problem = failure if failure is not None else error
        status = (
            "failed"
            if failure is not None
            else "error"
            if error is not None
            else "skipped"
            if node.find("skipped") is not None
            else "passed"
        )
        case: dict[str, Any] = {
            "testKey": f"{classname or ''}::{name}"[:_KEY_MAX],
            "retry": 0,
            "classname": classname,
            "name": name,
            "status": status,
            "durationMs": _ms(node.get("time")),
        }
        if problem is not None:
            case["failureMessage"] = problem.get("message") or (problem.text or "").strip()[:500]
            case["failureStack"] = (problem.text or "").strip() or None
        cases.append(case)
    return cases


def _ms(seconds: str | None) -> int | None:
    try:
        return round(float(seconds) * 1000) if seconds else None
    except ValueError:
        return None
