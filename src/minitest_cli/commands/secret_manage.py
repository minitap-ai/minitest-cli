"""``secret unset|rename``."""

from typing import Annotated

import typer

from minitest_cli.commands.secret_helpers import (
    JsonOption,
    call,
    command_context,
    reference,
    secrets_path,
    validate_name,
)
from minitest_cli.utils.output import print_json, print_success


def register(app: typer.Typer) -> None:

    @app.command(name="unset")
    def unset_secret(
        name: Annotated[str, typer.Argument(help="Secret name.")],
        json_flag: JsonOption = False,
    ) -> None:
        """Delete a secret. Refused (exit 6) while personas, scenarios or skills reference it."""
        settings, json_mode, app_id = command_context(json_flag)
        call(settings, "DELETE", f"{secrets_path(app_id)}/{name}")
        if json_mode:
            print_json({"removed": name})
            return
        print_success(f"Secret {name} deleted.")

    @app.command(name="rename")
    def rename_secret(
        old: Annotated[str, typer.Argument(help="Current secret name.")],
        new: Annotated[str, typer.Argument(help="New UPPER_SNAKE secret name.")],
        json_flag: JsonOption = False,
    ) -> None:
        """Rename a secret; every {{secret:OLD}} in scenarios, criteria and skills is rewritten."""
        validate_name(new)
        settings, json_mode, app_id = command_context(json_flag)
        saved = call(settings, "PATCH", f"{secrets_path(app_id)}/{old}", json={"newName": new})
        if json_mode:
            print_json(saved)
            return
        print_success(f"Secret {old} renamed to {new}. Reference: {reference(new)}")
