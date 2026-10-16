"""Rendering for `minitest df show --view conflicts`.

The three sides of a conflict are whole story tuples, so printing them as three
JSON blobs in a table makes the one thing a resolver needs — which key is in
dispute, and what each side says it should be — the hardest thing to find. They
are pivoted per key instead: one row per disputed key, one column per side.
"""

import json
from typing import Any

from minitest_cli.models.draft_feature import (
    DraftFeatureConflictResponse,
    DraftFeatureConflictsResponse,
)
from minitest_cli.utils.output import output, print_info, print_table

CONFLICT_TABLE_HEADERS = ["#", "Kind", "Story ID", "Criterion ID", "Fields"]
CONFLICT_SIDE_HEADERS = ["Key", "base", "main", "branch"]

# rich divides the width between the columns it is given, so a column of dashes
# is taken out of the one carrying the kind. Story and criterion conflicts are
# different kinds, so one of the two id columns is always dead weight.
_CRITERION_COLUMN = CONFLICT_TABLE_HEADERS.index("Criterion ID")

# A side is null when that side has no version of the node at all (main deleted
# it, or the branch does). Rendered as a dash it reads as "the value is null",
# which is a different answer and a different resolution.
_ABSENT_SIDE = "(no version)"


def _cell(side: dict[str, Any] | None, key: str) -> str:
    if side is None:
        return _ABSENT_SIDE
    value = side.get(key)
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return "-" if value is None else str(value)


def _disputed_keys(conflict: DraftFeatureConflictResponse) -> list[str]:
    """The keys worth pivoting: the ones in dispute, or all of them when unnamed.

    A criterion conflict names no ``fields`` — its whole tuple is the argument —
    so falling back to the union keeps those kinds as readable as story ones.
    """
    if conflict.fields:
        return conflict.fields
    keys: list[str] = []
    for side in (conflict.base, conflict.main, conflict.branch):
        for key in side or {}:
            if key not in keys:
                keys.append(key)
    return keys


def _summary_row(index: int, conflict: DraftFeatureConflictResponse) -> list[str]:
    return [
        str(index),
        conflict.kind,
        conflict.story_id or "-",
        conflict.criterion_id or "-",
        ", ".join(conflict.fields) or "-",
    ]


def print_conflicts(report: DraftFeatureConflictsResponse, *, json_mode: bool) -> None:
    if json_mode:
        output(report.model_dump(mode="json", by_alias=True), json_mode=True)
        return

    print_info(f"Branch {report.draft_feature_id} — rebase {report.rebase_state.value}")
    if not report.conflicts:
        print_info("No conflicts.")
        output({"mainRev": report.main_rev}, json_mode=False)
        return

    headers = list(CONFLICT_TABLE_HEADERS)
    rows = [_summary_row(i, c) for i, c in enumerate(report.conflicts, start=1)]
    if not any(conflict.criterion_id for conflict in report.conflicts):
        headers.pop(_CRITERION_COLUMN)
        for row in rows:
            row.pop(_CRITERION_COLUMN)
    print_table(headers, rows, title=f"Conflicts — {len(report.conflicts)}")

    for index, conflict in enumerate(report.conflicts, start=1):
        print_info(f"[{index}] {conflict.reason}")
        if conflict.path:
            print_info(f"[{index}] cycle: {' -> '.join(conflict.path)}")
        keys = _disputed_keys(conflict)
        if not keys:
            continue
        print_table(
            CONFLICT_SIDE_HEADERS,
            [
                [
                    key,
                    _cell(conflict.base, key),
                    _cell(conflict.main, key),
                    _cell(conflict.branch, key),
                ]
                for key in keys
            ],
            title=f"[{index}] sides",
        )

    print_info("Resolve by copying a side's value into a story.edit / criterion.edit op.")
    # Out of every table title: rich wraps a title to the table width and would
    # split the one token that has to be copied verbatim into the next apply.
    output({"mainRev": report.main_rev}, json_mode=False)
