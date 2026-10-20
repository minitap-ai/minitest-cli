"""``minitest build signing-certificate``: the key that signs APKs converted from an .aab."""

from minitest_cli.api.client import ApiClient
from minitest_cli.commands.build_helpers import (
    base_path,
    handle_response_error,
    resolve_app,
    run_api_call,
)
from minitest_cli.utils.output import output


def signing_certificate() -> None:
    """Show the SHA-1 / SHA-256 of the key Minitap signs your converted .aab builds with.

    Add the SHA-1 to your Firebase project (or Google Cloud OAuth client) so
    Google sign-in works on those builds.
    """
    settings, app_id, json_mode = resolve_app()

    async def _run() -> dict[str, str]:
        async with ApiClient(settings) as client:
            resp = await client.get(f"{base_path(app_id)}/builds/android-signing-certificate")
        handle_response_error(resp)
        return resp.json()

    output(run_api_call(_run()), json_mode=json_mode)
