"""In-app purchase flag option and display for user-story commands."""

from typing import Annotated, Any

import typer

from minitest_cli.utils.output import print_info, print_warning

InAppPurchasesOption = Annotated[
    bool | None,
    typer.Option(
        "--in-app-purchases/--no-in-app-purchases",
        help=(
            "Mark the scenario as going through an in-app purchase, subscription or "
            "restore; on physical iPhones it then runs on a device signed in to a "
            "Sandbox Apple Account. Omit to leave unchanged (off on create)."
        ),
    ),
]


def requires_in_app_purchases(story: dict[str, Any]) -> bool:
    return story.get("requiresInAppPurchases", story.get("requires_in_app_purchases")) is True


def report_in_app_purchases(story: dict[str, Any], requested: bool | None) -> None:
    if requested is None:
        return
    if requested and not requires_in_app_purchases(story):
        print_warning("In-app purchases are not enabled for this workspace; the flag was ignored.")
        return
    print_info(f"In-app purchases: {'on' if requested else 'off'}")
