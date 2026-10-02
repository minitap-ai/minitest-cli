"""Screen-tree commands: inspect the screens and transitions exploration mapped for an app."""

from typing import Annotated

import typer
from rich.console import Console

from minitest_cli.commands.build_helpers import resolve_app
from minitest_cli.commands.screens_detail import render_screen
from minitest_cli.commands.screens_format import (
    HEADERS,
    empty_message,
    format_screen_row,
    summary_line,
    tree_title,
)
from minitest_cli.commands.screens_helpers import (
    ScreenPlatform,
    TreeIndex,
    fetch_screen_tree,
    find_screens,
    narrow_tree,
    select_screens,
)
from minitest_cli.commands.screens_tree import render_tree
from minitest_cli.utils.output import output, print_error, print_info, print_table

EXIT_NOT_FOUND = 4

app = typer.Typer(name="screens", help="Inspect the screen tree exploration mapped for an app.")

_PLATFORM_OPTION = typer.Option(help="Only this platform's tree. Omit for every tree.")


@app.command(name="list")
def list_screens(
    platform: Annotated[ScreenPlatform | None, _PLATFORM_OPTION] = None,
    area: Annotated[str | None, typer.Option(help="Only screens in this area.")] = None,
    blocked: Annotated[
        bool,
        typer.Option("--blocked", help="Only screens with at least one blocked transition."),
    ] = False,
    tree: Annotated[
        bool,
        typer.Option("--tree", help="Render the tree from its root instead of a table."),
    ] = False,
) -> None:
    """List the screens of the app's screen tree, with their transitions by status."""
    settings, app_id, json_mode = resolve_app()
    response = fetch_screen_tree(settings, app_id, platform.value if platform else None)
    filtered = area is not None or blocked
    selections = [(t, select_screens(t, area=area, blocked_only=blocked)) for t in response.trees]

    if json_mode:
        if filtered:
            trees = [narrow_tree(t, shown) for t, shown in selections if shown]
            response = response.model_copy(update={"trees": trees})
        output(response, json_mode=True)
        return

    selections = [(t, shown) for t, shown in selections if shown]
    if not selections:
        print_info(empty_message(response, area=area, blocked=blocked))
        return

    console = Console()
    for screen_tree, shown in selections:
        index = TreeIndex.of(screen_tree)
        if tree:
            render_tree(index, shown, filtered=filtered)
        else:
            rows = [format_screen_row(index, screen) for screen in shown]
            print_table(HEADERS, rows, title=tree_title(index, shown))
        console.print(summary_line(screen_tree, shown))


@app.command(name="get")
def get_screen(
    screen: Annotated[
        str,
        typer.Argument(help="Screen key or display name (case-insensitive)."),
    ],
    platform: Annotated[ScreenPlatform | None, _PLATFORM_OPTION] = None,
) -> None:
    """Show one screen: how it is reached, its children, and every element by status."""
    settings, app_id, json_mode = resolve_app()
    response = fetch_screen_tree(settings, app_id, platform.value if platform else None)
    matches = find_screens(response, screen)

    if not matches:
        print_error(
            f"No mapped screen matches {screen!r}. "
            "Run `minitest screens list` to see what exploration reached."
        )
        raise typer.Exit(code=EXIT_NOT_FOUND)

    if json_mode:
        trees = [narrow_tree(t, [match]) for t, match in matches]
        output(response.model_copy(update={"trees": trees}), json_mode=True)
        return

    if len(matches) > 1:
        platforms = ", ".join(t.platform for t, _ in matches)
        print_info(
            f"{len(matches)} screens match {screen!r} ({platforms}). Use --platform to narrow."
        )
    for screen_tree, match in matches:
        render_screen(TreeIndex.of(screen_tree), match)
