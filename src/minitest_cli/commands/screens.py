"""Screen-map commands: inspect the screens exploration reached for an app."""

from typing import Annotated

import typer

from minitest_cli.commands.build_helpers import Platform, resolve_app
from minitest_cli.commands.screens_detail import render_screen
from minitest_cli.commands.screens_format import (
    empty_message,
    format_screen_row,
    frontier_hint,
    headers,
    table_title,
)
from minitest_cli.commands.screens_helpers import fetch_screen_map, filter_nodes, find_node
from minitest_cli.commands.screens_tree import render_tree
from minitest_cli.utils.output import output, print_error, print_info, print_table

EXIT_NOT_FOUND = 4

app = typer.Typer(name="screens", help="Inspect the screens exploration mapped for an app.")

_PLATFORM_OPTION = typer.Option(help="Restrict to one platform. Omit for every platform.")


@app.command(name="list")
def list_screens(
    platform: Annotated[Platform | None, _PLATFORM_OPTION] = None,
    area: Annotated[str | None, typer.Option(help="Only screens in this area.")] = None,
    blocked: Annotated[
        bool,
        typer.Option("--blocked", help="Only screens the crawl could not get past."),
    ] = False,
    tree: Annotated[
        bool,
        typer.Option("--tree", help="Render the map as a navigation tree instead of a table."),
    ] = False,
) -> None:
    """List every screen the exploration crawl reached for the active app."""
    settings, app_id, json_mode = resolve_app()
    screen_map = fetch_screen_map(settings, app_id, platform.value if platform else None)
    nodes = filter_nodes(screen_map.screens, area=area, blocked_only=blocked)

    if json_mode:
        # Report the filtered set honestly, count included, so a piped consumer
        # never reads a count that disagrees with the screens beside it.
        output(
            screen_map.model_copy(update={"screens": nodes, "screen_count": len(nodes)}),
            json_mode=True,
        )
        return

    if not nodes:
        print_info(empty_message(screen_map, area=area, blocked=blocked))
        return

    title = table_title(screen_map, nodes)
    if tree:
        render_tree(nodes, title=title)
    else:
        show_platform = len({n.platform for n in nodes}) > 1
        print_table(
            headers(show_platform=show_platform),
            [format_screen_row(n, show_platform=show_platform) for n in nodes],
            title=title,
        )

    hint = frontier_hint(nodes, screen_map.screens)
    if hint:
        print_info(hint)


@app.command(name="get")
def get_screen(
    screen: Annotated[
        str,
        typer.Argument(help="Screen key or display name (case-insensitive)."),
    ],
    platform: Annotated[Platform | None, _PLATFORM_OPTION] = None,
) -> None:
    """Show one screen: how to reach it, and where it leads."""
    settings, app_id, json_mode = resolve_app()
    screen_map = fetch_screen_map(settings, app_id, platform.value if platform else None)
    matches = find_node(screen_map.screens, screen)

    if not matches:
        print_error(
            f"No mapped screen matches {screen!r}. "
            "Run `minitest screens list` to see what exploration reached."
        )
        raise typer.Exit(code=EXIT_NOT_FOUND)

    if json_mode:
        output(matches if len(matches) > 1 else matches[0], json_mode=True)
        return

    if len(matches) > 1:
        # The same screen key legitimately exists per platform. Say so rather
        # than picking one and presenting it as the answer.
        print_info(
            f"{len(matches)} screens match {screen!r} "
            f"({', '.join(n.platform for n in matches)}). Use --platform to narrow."
        )
    for node in matches:
        render_screen(node)
