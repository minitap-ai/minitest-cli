"""Validate and send what `minitest pr check` is given: builds, context, commits, files."""

import glob
import mimetypes
import sys
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.build_upload import upload_build
from minitest_cli.commands.draft_helpers import DraftTarget
from minitest_cli.commands.pr_api import EXIT_ERRORED, check_path
from minitest_cli.commands.run_helpers import extract_detail, is_uuid
from minitest_cli.commands.pr_render import error, info, warn

MAX_CONTEXT_CHARS = 10_000
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
ATTACHMENT_TYPES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"})


def fail(message: str) -> typer.Exit:
    error(message)
    return typer.Exit(code=EXIT_ERRORED)


def read_text(path: str, flag: str) -> str:
    if path == "-":
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise fail(f"{flag}: cannot read {path}: {exc}") from exc


def read_context(path: str) -> str:
    context = read_text(path, "--context-file").strip()
    if not context:
        raise fail("--context-file is empty: send the PR description and its ticket.")
    if len(context) > MAX_CONTEXT_CHARS:
        raise fail(
            f"--context-file has {len(context):,} characters, the limit is {MAX_CONTEXT_CHARS:,}."
            " Shorten it yourself (keep the acceptance criteria): nothing was sent."
        )
    return context


def read_commits(path: str | None) -> list[str] | None:
    if path is None:
        return None
    lines = read_text(path, "--commits-file").splitlines()
    return [line.strip() for line in lines if line.strip()]


class WebBrowser(StrEnum):
    CHROME = "chrome"
    FIREFOX = "firefox"
    SAFARI = "safari"
    EDGE = "edge"


def check_build_values(builds: dict[str, str | None], *, web: bool) -> dict[str, str]:
    given = {platform: value for platform, value in builds.items() if value}
    if not given and not web:
        raise fail(
            "Pass at least one platform: --ios-build or --android-build (a file or an id),"
            " or --web-url."
        )
    for platform, value in given.items():
        if not Path(value).is_file() and not is_uuid(value):
            raise fail(f"--{platform}-build: '{value}' is neither a build file nor a build id.")
    return given


def check_web(url: str | None, browser: WebBrowser | None) -> dict[str, str] | None:
    if url is None:
        if browser is not None:
            raise fail("--web-browser needs --web-url.")
        return None
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise fail(f"--web-url: '{url}' is not an http(s) URL.")
    return {"url": url} | ({"browser": browser.value} if browser else {})


async def resolve_builds(client: ApiClient, app_id: str, builds: dict[str, str]) -> dict[str, str]:
    """Upload the builds given as files; return the build id of each platform."""
    ids = {}
    for platform, value in builds.items():
        file = Path(value)
        if not file.is_file():
            ids[platform] = value
            continue
        build = await upload_build(client, app_id, file, platform)
        info(f"Uploaded the {platform} build {file.name}: {build.id}")
        ids[platform] = build.id
    return ids


def expand_attachments(patterns: list[str]) -> list[Path]:
    """Files to send; unsupported or oversized ones are skipped with a warning."""
    files: list[Path] = []
    for pattern in patterns:
        matches = sorted(glob.glob(pattern, recursive=True))
        if not matches:
            warn(f"--attach '{pattern}' matches no file.")
        for match in map(Path, matches):
            if not match.is_file() or match in files:
                continue
            if match.suffix.lower() not in ATTACHMENT_TYPES:
                warn(f"Skipped {match}: only png, jpg, gif, webp and pdf are sent.")
            elif match.stat().st_size > MAX_ATTACHMENT_BYTES:
                warn(f"Skipped {match}: larger than 10 MB.")
            else:
                files.append(match)
    return files


async def send_attachments(
    client: ApiClient, target: DraftTarget, check_id: str, files: list[Path]
) -> None:
    for file in files:
        mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        with file.open("rb") as f:
            resp = await client.upload_file(
                check_path(check_id, "/files"),
                files={"file": (file.name, f, mime)},
                params=target.params,
            )
        if resp.status_code >= 400:
            detail = extract_detail(resp) or resp.text
            warn(f"Skipped {file}: rejected ({resp.status_code}): {detail}")
        else:
            info(f"Attached {file}")
