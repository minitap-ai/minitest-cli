"""``secret create``: a secret with a generated value, or one waiting for a human's value.

No value ever crosses the CLI: the server generates it or a human sets it later. Allowed
inside a test run (an agent may create, never write a value). ``secret request`` is the
deprecated alias of ``create --empty``.
"""

from enum import StrEnum
from typing import Annotated, Any, NoReturn

import httpx
import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.secret_helpers import (
    EXIT_GENERAL_ERROR,
    EXIT_NOT_FOUND,
    JsonOption,
    KindOption,
    SecretKind,
    command_context,
    handle_secret_response,
    reference,
    secrets_path,
    validate_name,
)
from minitest_cli.commands.user_story_helpers import extract_detail, run_api_call
from minitest_cli.utils.output import print_error, print_json, print_success, print_warning

GENERATE_KINDS = (SecretKind.password, SecretKind.token, SecretKind.text)
MIN_LENGTH, MAX_LENGTH = 12, 64
OLD_SERVER = (
    "This server does not support `secret create --generate` yet (or Secrets are not enabled "
    "for this workspace). Ask a human to set the value with `minitest secret set`."
)


class Charset(StrEnum):
    default = "default"
    alnum = "alnum"


NameArg = Annotated[str, typer.Argument(help="UPPER_SNAKE secret name, e.g. QA_PASSWORD.")]
ReasonOption = Annotated[
    str | None, typer.Option("--reason", help="With --empty: why the test needs it.")
]
ScenarioOption = Annotated[
    str | None, typer.Option("--scenario", help="With --empty: scenario ID that needs it.")
]
NoteOption = Annotated[str | None, typer.Option("--note", help="What this secret is for.")]


def _fail(message: str) -> NoReturn:
    print_error(message)
    raise typer.Exit(code=EXIT_GENERAL_ERROR)


def _check_flags(kind: SecretKind, generate: bool, opts: dict[str, Any]) -> None:
    if generate:
        if kind not in GENERATE_KINDS:
            _fail(f"--generate works for password, token or text, not {kind.value}.")
        for flag in ("--reason", "--scenario"):
            if opts[flag] is not None:
                _fail(f"{flag} goes with --empty, not --generate.")
        length = opts["--length"]
        if length is not None and not MIN_LENGTH <= length <= MAX_LENGTH:
            _fail(f"--length must be between {MIN_LENGTH} and {MAX_LENGTH}.")
        return
    if not (opts["--reason"] or "").strip():
        _fail("--empty needs --reason: tell the human why the test needs this value.")
    for flag in ("--length", "--charset"):
        if opts[flag] is not None:
            _fail(f"{flag} goes with --generate, not --empty.")


def _is_old_server(resp: httpx.Response) -> bool:
    """A server without ``POST /secrets``: 405 (the path only has GET), or FastAPI's bare 404."""
    if resp.status_code == 405:
        return True
    return resp.status_code == 404 and extract_detail(resp) in (None, "Not Found")


async def _post(settings: Any, app_id: str, body: dict[str, Any]) -> Any:
    async with ApiClient(settings) as client:
        resp = await client.request("POST", secrets_path(app_id), json=body)
        if _is_old_server(resp) and body["mode"] == "empty":
            legacy = {"name": body["name"], "kind": body["kind"], "reason": body["reason"]}
            if body.get("userStoryId"):
                legacy["storyId"] = body["userStoryId"]
            resp = await client.request("POST", f"{secrets_path(app_id)}/requests", json=legacy)
            handle_secret_response(resp, collection=True)
        elif _is_old_server(resp):
            print_error(OLD_SERVER)
            raise typer.Exit(code=EXIT_NOT_FOUND)
        else:
            handle_secret_response(resp)
        return resp.json() if resp.content else {}


def create(
    name: str, kind: SecretKind, json_flag: bool, *, generate: bool, opts: dict[str, Any]
) -> None:
    """``opts`` maps each optional flag (``--note``, ``--reason``, …) to its value or None."""
    validate_name(name)
    _check_flags(kind, generate, opts)
    settings, json_mode, app_id = command_context(json_flag)
    body: dict[str, Any] = {"name": name, "kind": kind.value}
    body["mode"] = "generate" if generate else "empty"
    for flag, key in (
        ("--note", "note"),
        ("--reason", "reason"),
        ("--scenario", "userStoryId"),
        ("--length", "length"),
        ("--charset", "charset"),
    ):
        if opts[flag] is not None:
            body[key] = str(opts[flag]) if isinstance(opts[flag], StrEnum) else opts[flag]
    created = run_api_call(_post(settings, app_id, body))
    if json_mode:
        print_json(created)
    elif generate:
        print_success(f"Secret {name} created with a generated value. Reference: {reference(name)}")
    else:
        print_success(
            f"Secret {name} created without a value; a human must set it "
            f"(minitest secret set {name} --kind {kind.value}). Reference: {reference(name)}"
        )


def register(app: typer.Typer) -> None:

    @app.command(name="create")
    def create_secret(
        name: NameArg,
        kind: KindOption,
        generate: Annotated[
            bool, typer.Option("--generate", help="Generate the value (password, token, text).")
        ] = False,
        length: Annotated[
            int | None,
            typer.Option("--length", help=f"With --generate: {MIN_LENGTH}-{MAX_LENGTH}, def. 24."),
        ] = None,
        charset: Annotated[
            Charset | None,
            typer.Option(
                "--charset", help="With --generate: default (letters, digits, !-) or alnum."
            ),
        ] = None,
        empty: Annotated[
            bool, typer.Option("--empty", help="No value yet: a human sets it later.")
        ] = False,
        reason: ReasonOption = None,
        scenario: ScenarioOption = None,
        note: NoteOption = None,
        json_flag: JsonOption = False,
    ) -> None:
        """Create a secret without typing its value: --generate one, or --empty for a human.

        --generate: Mini gets a value it never sees, e.g. a password to sign up with.

        --empty --reason: only a human has the value; runs that need it wait until it is set.

        Reference it as {{secret:NAME}} or link it with test-profile --password-secret.

        Never prints a value. Allowed inside a test run.
        """
        if generate == empty:
            _fail("Give exactly one of --generate or --empty.")
        opts = {"--length": length, "--charset": charset, "--reason": reason}
        opts |= {"--scenario": scenario, "--note": note}
        create(name, kind, json_flag, generate=generate, opts=opts)

    @app.command(name="request", hidden=True)
    def request_secret(
        name: NameArg,
        kind: KindOption,
        reason: Annotated[str, typer.Option("--reason", help="Why the test needs it.")],
        scenario: ScenarioOption = None,
        json_flag: JsonOption = False,
    ) -> None:
        """Deprecated: use ``secret create NAME --kind K --empty --reason TEXT``."""
        print_warning("`minitest secret request` is deprecated; use `secret create --empty`.")
        opts = {"--length": None, "--charset": None, "--reason": reason}
        opts |= {"--scenario": scenario, "--note": None}
        create(name, kind, json_flag, generate=False, opts=opts)
