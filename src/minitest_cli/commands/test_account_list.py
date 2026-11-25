"""`minitest test-account list`: the app's test accounts, or the ones Minitap shares."""

from typing import Annotated, Any

import typer

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.persona_helpers import (
    current_app_id,
    handle_persona_response,
    personas_path,
)
from minitest_cli.commands.test_account_helpers import (
    get_settings,
    is_json_mode,
    run_api_call,
    warn_if_qa_inbox_unreadable,
)
from minitest_cli.core.auth import require_auth
from minitest_cli.utils.output import output, print_info, print_table

SHARED_PATH = "/api/v1/test-profiles/shared"
PAGE_SIZE = 100
APP_HEADERS = ["ID", "Name", "Login", "Persona", "Default"]
SHARED_HEADERS = ["ID", "Name", "Login", "Persona ID"]


def _login(account: dict[str, Any]) -> str:
    return account.get("username") or account.get("phoneNumber") or ""


async def _app_accounts(app_id: str) -> list[dict[str, Any]]:
    async with ApiClient(get_settings()) as client:
        listed: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = await client.get(
                f"/api/v1/apps/{app_id}/test-profiles",
                params={"page": page, "page_size": PAGE_SIZE},
            )
            handle_persona_response(resp, resource="App")
            data = resp.json()
            listed += data["items"]
            if page * PAGE_SIZE >= data["total"]:
                break
            page += 1
        resp = await client.get(personas_path(app_id))
        handle_persona_response(resp)
        names = {p["id"]: p["name"] for p in resp.json()["items"]}
    return [
        account | {"personaName": names.get(account.get("personaId"))}
        for account in listed
        if account.get("source") != "shared"
    ]


async def _shared_accounts() -> list[dict[str, Any]]:
    async with ApiClient(get_settings()) as client:
        resp = await client.get(SHARED_PATH)
        handle_persona_response(resp, resource="Shared test accounts")
        return resp.json()["items"]


def register(app: typer.Typer) -> None:

    @app.command(name="list")
    def list_accounts(
        shared: Annotated[
            bool,
            typer.Option(
                "--shared",
                help="List the test accounts Minitap shares with every app (e.g. Google "
                "sign-in). A scenario plays one with --persona <its persona ID>.",
            ),
        ] = False,
    ) -> None:
        """List the app's test accounts with their persona, or Minitap's shared ones."""
        if shared:
            require_auth(get_settings())
            items = run_api_call(_shared_accounts())
        else:
            items = run_api_call(_app_accounts(current_app_id()))
            for account in items:
                warn_if_qa_inbox_unreadable(account)
        if is_json_mode():
            output(items, json_mode=True)
        elif not items:
            print_info("No shared test accounts." if shared else "No test accounts yet.")
        elif shared:
            rows = [[a["id"], a["name"], _login(a), a.get("personaId") or ""] for a in items]
            print_table(SHARED_HEADERS, rows, title=f"Shared by Minitap ({len(rows)})")
        else:
            rows = [
                [
                    a["id"],
                    a["name"],
                    _login(a),
                    a.get("personaName") or a.get("personaId") or "",
                    "★" if a.get("isDefault") else "",
                ]
                for a in items
            ]
            print_table(APP_HEADERS, rows, title=f"Test accounts ({len(rows)})")
