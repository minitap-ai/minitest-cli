"""Build failure guidance: class allowlist plus a labelled fallback ladder."""

from typing import Any

from minitest_cli.models import BuildListResponse, BuildResponse
from minitest_cli.utils.output import err_console

SURFACEABLE_ERROR_CLASSES = ("code", "user_action")
FAILED_STATUS = "failed"
WITHHELD_NOTICE = (
    "This failure is not actionable from your side. Nothing to fix in your app: "
    "retry the build, and contact support if it keeps failing."
)
NO_GUIDANCE_NOTICE = "No failure details were recorded for this build."
SOURCE_LABELS = {
    "fix_prompt": "Fix prompt",
    "remediation": "Remediation",
    "summary": "Summary",
    "raw": "Raw builder output",
    "withheld": "Notice",
}


def is_withheld(error_class: str | None) -> bool:
    return error_class is not None and error_class not in SURFACEABLE_ERROR_CLASSES


def build_guidance(build: BuildResponse) -> dict[str, str | None]:
    if is_withheld(build.error_class):
        return {"source": "withheld", "text": WITHHELD_NOTICE}
    ladder = (
        ("fix_prompt", build.error_fix_prompt),
        ("remediation", build.error_remediation),
        ("summary", build.error_summary),
        ("raw", build.error_raw),
    )
    for source, text in ladder:
        if text:
            return {"source": source, "text": text}
    return {"source": "none", "text": None}


def redacted_payload(result: BuildListResponse) -> dict[str, Any]:
    payload = result.model_dump(mode="json", by_alias=True)
    for item, build in zip(payload.get("items", []), result.items, strict=False):
        if build.status != FAILED_STATUS:
            item["guidance"] = None
            continue
        item["guidance"] = build_guidance(build)
        if is_withheld(build.error_class):
            item["errorSummary"] = WITHHELD_NOTICE
            item["errorRemediation"] = None
            item["errorFixPrompt"] = None
            item["errorRaw"] = None
    return payload


def print_fix_prompts(builds: list[BuildResponse]) -> None:
    for build in [b for b in builds if b.status == FAILED_STATUS]:
        err_console.print(f"[bold red]Build {build.id} failed[/bold red]")
        guidance = build_guidance(build)
        text = guidance["text"]
        if not text:
            err_console.print(f"  [dim]{NO_GUIDANCE_NOTICE}[/dim]")
            continue
        if build.error_summary and guidance["source"] not in ("summary", "withheld"):
            err_console.print(f"  [dim]Summary:[/dim] {build.error_summary}")
        label = SOURCE_LABELS.get(guidance["source"] or "", "Notice")
        err_console.print(f"  [yellow]{label}:[/yellow] {text}")
