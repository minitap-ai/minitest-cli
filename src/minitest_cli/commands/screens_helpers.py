"""Data access and selection for ``minitest screens``.

Presentation lives in ``screens_format`` (table), ``screens_tree`` (tree) and
``screens_detail`` (one screen).
"""

from dataclasses import dataclass
from enum import StrEnum

from rich.markup import escape

from minitest_cli.api.client import ApiClient
from minitest_cli.commands._response_errors import handle_response_error
from minitest_cli.commands.build_helpers import run_api_call
from minitest_cli.core.config import Settings
from minitest_cli.models import (
    ScreenTransition,
    ScreenTree,
    ScreenTreeResponse,
    TreeCounts,
    TreeScreen,
)

SIGNED_OUT = "signed out"
_VIA_WIDTH = 46


class ScreenPlatform(StrEnum):
    android = "android"
    ios = "ios"
    web = "web"


def screen_tree_path(app_id: str) -> str:
    return f"/api/v1/apps/{app_id}/screen-tree"


async def _get_screen_tree(
    settings: Settings, app_id: str, platform: str | None
) -> ScreenTreeResponse:
    params: dict[str, str] = {}
    if platform is not None:
        params["platform"] = platform

    async with ApiClient(settings) as client:
        resp = await client.get(screen_tree_path(app_id), params=params)
    handle_response_error(resp, resource="Screen tree")
    return ScreenTreeResponse.model_validate(resp.json())


def fetch_screen_tree(settings: Settings, app_id: str, platform: str | None) -> ScreenTreeResponse:
    response = run_api_call(_get_screen_tree(settings, app_id, platform))
    if platform is None:
        return response
    trees = [tree for tree in response.trees if tree.platform == platform]
    return response.model_copy(update={"trees": trees})


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def account_label(transition: ScreenTransition) -> str:
    return transition.persona_ref or SIGNED_OUT


def element_label(transition: ScreenTransition) -> str:
    return "(auto)" if transition.is_auto else transition.element_label


def via_markup(transition: ScreenTransition) -> str:
    """Element tapped, plus the account when the walk was not signed out."""
    label = escape(truncate(element_label(transition), _VIA_WIDTH))
    if transition.persona_ref:
        label += f" [magenta]as {escape(transition.persona_ref)}[/magenta]"
    return label


@dataclass(frozen=True)
class TreeIndex:
    tree: ScreenTree
    screens: dict[str, TreeScreen]
    transitions: dict[str, ScreenTransition]

    @classmethod
    def of(cls, tree: ScreenTree) -> "TreeIndex":
        return cls(
            tree=tree,
            screens={s.screen_key: s for s in tree.screens},
            transitions={t.id: t for t in tree.transitions},
        )

    def name(self, screen_key: str | None) -> str:
        if screen_key is None:
            return "?"
        screen = self.screens.get(screen_key)
        return screen.display_name if screen else screen_key

    def pick(self, ids: list[str]) -> list[ScreenTransition]:
        return [self.transitions[i] for i in ids if i in self.transitions]

    def parent(self, screen: TreeScreen) -> ScreenTransition | None:
        if screen.parent_transition_id is None:
            return None
        return self.transitions.get(screen.parent_transition_id)


def select_screens(tree: ScreenTree, *, area: str | None, blocked_only: bool) -> list[TreeScreen]:
    selected = tree.screens
    if area is not None:
        wanted = area.strip().casefold()
        selected = [s for s in selected if (s.area or "").casefold() == wanted]
    if blocked_only:
        selected = [s for s in selected if s.counts.blocked > 0]
    return selected


def narrow_tree(tree: ScreenTree, keep: list[TreeScreen]) -> ScreenTree:
    """Restrict a tree to ``keep`` and every transition touching it, counts recomputed.

    Tree counts stay the sum of the kept screens' outgoing counts, and every
    transition id a kept screen references is still present.
    """
    keys = {s.screen_key for s in keep}
    counts = TreeCounts(
        screens=len(keep),
        explored=sum(s.counts.explored for s in keep),
        pending=sum(s.counts.pending for s in keep),
        blocked=sum(s.counts.blocked for s in keep),
        skipped=sum(s.counts.skipped for s in keep),
    )
    transitions = [
        t for t in tree.transitions if t.from_screen_key in keys or t.to_screen_key in keys
    ]
    detached = [k for k in tree.detached_screen_keys if k in keys]
    return tree.model_copy(
        update={
            "screens": keep,
            "transitions": transitions,
            "counts": counts,
            "detached_screen_keys": detached,
        }
    )


def find_screens(response: ScreenTreeResponse, needle: str) -> list[tuple[ScreenTree, TreeScreen]]:
    """Match by screen key or display name, case-insensitively, across every tree."""
    wanted = " ".join(needle.split()).casefold()
    return [
        (tree, screen)
        for tree in response.trees
        for screen in tree.screens
        if wanted in (screen.screen_key.casefold(), screen.display_name.casefold())
    ]
