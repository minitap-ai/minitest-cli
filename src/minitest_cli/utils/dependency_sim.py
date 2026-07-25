"""Deterministic what-if simulation over a user-story dependency graph.

Computes, without writing anything, what a set of edge additions/removals
would do to an app's dependency graph: whether a cycle appears, which
stories are affected, and the new topological run order. Agents must use
this instead of doing graph math freehand.
"""

from typing import Any

import typer

from minitest_cli.utils.output import print_error, print_info, print_success, print_warning

EXIT_GENERAL_ERROR = 1


def print_simulation_summary(result: dict[str, Any]) -> None:
    """Human-readable projection of a simulation result."""
    for entry in result["addedEdges"]:
        print_info(f"+ {entry['story']['name']} depends on {entry['dependsOn']['name']}")
    for entry in result["removedEdges"]:
        print_info(f"- {entry['story']['name']} no longer depends on {entry['dependsOn']['name']}")
    if not result["valid"]:
        cycle = " -> ".join(ref["name"] for ref in result["cycle"])
        print_warning(f"Refused: this change would create a cycle: {cycle}")
        return
    affected = ", ".join(ref["name"] for ref in result["affectedStories"]) or "none"
    print_info(f"Affected stories: {affected}")
    for index, level in enumerate(result["runOrder"] or [], start=1):
        print_info(f"Run wave {index}: {', '.join(ref['name'] for ref in level)}")
    print_success("Simulation only — nothing was written.")


def parse_edge_arg(raw: str) -> tuple[str, str]:
    """Parse ``<story_id>:<depends_on_id>`` into a (child, parent) pair."""
    child, sep, parent = raw.partition(":")
    child, parent = child.strip(), parent.strip()
    if not sep or not child or not parent:
        print_error(f"Invalid edge '{raw}': expected <story_id>:<depends_on_id>.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    if child == parent:
        print_error(f"Invalid edge '{raw}': a story cannot depend on itself.")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)
    return child, parent


def _find_cycle(children_of: dict[str, list[str]], node_ids: list[str]) -> list[str] | None:
    """Return one dependency cycle as an id path (first id repeated last), or None."""
    white, grey, black = set(node_ids), set(), set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        white.discard(node)
        grey.add(node)
        stack.append(node)
        for child in children_of.get(node, []):
            if child in grey:
                start = stack.index(child)
                return [*stack[start:], child]
            if child in white:
                found = visit(child)
                if found:
                    return found
        grey.discard(node)
        black.add(node)
        stack.pop()
        return None

    for node in sorted(node_ids):
        if node in white:
            found = visit(node)
            if found:
                return found
    return None


def _run_order(
    children_of: dict[str, list[str]],
    parents_of: dict[str, set[str]],
    node_ids: list[str],
) -> list[list[str]]:
    """Kahn's algorithm by levels: stories in the same level can run in parallel."""
    remaining_parents = {n: set(parents_of.get(n, set())) for n in node_ids}
    levels: list[list[str]] = []
    ready = sorted(n for n, parents in remaining_parents.items() if not parents)
    seen: set[str] = set()
    while ready:
        levels.append(ready)
        seen.update(ready)
        next_ready: set[str] = set()
        for node in ready:
            for child in children_of.get(node, []):
                remaining_parents[child].discard(node)
                if not remaining_parents[child] and child not in seen:
                    next_ready.add(child)
        ready = sorted(next_ready)
    return levels


def simulate_dependency_changes(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    add: list[tuple[str, str]],
    remove: list[tuple[str, str]],
) -> dict[str, Any]:
    """Apply (child, parent) edge changes in memory and project the outcome.

    ``edges`` follow the dependency-graph API shape: ``source`` is the parent
    (depended-on) story, ``target`` the dependent child.
    """
    node_ids = [str(n["id"]) for n in nodes]
    known = set(node_ids)
    name_of = {str(n["id"]): str(n.get("name", n["id"])) for n in nodes}

    unknown = sorted({sid for pair in [*add, *remove] for sid in pair if sid not in known})
    if unknown:
        print_error(f"Unknown user-story id(s): {', '.join(unknown)}")
        raise typer.Exit(code=EXIT_GENERAL_ERROR)

    edge_set = {(str(e["source"]), str(e["target"])) for e in edges}
    removed = [(c, p) for c, p in remove if (p, c) in edge_set]
    edge_set -= {(p, c) for c, p in removed}
    added = [(c, p) for c, p in add if (p, c) not in edge_set]
    edge_set |= {(p, c) for c, p in added}

    children_of: dict[str, list[str]] = {}
    parents_of: dict[str, set[str]] = {}
    for parent, child in sorted(edge_set):
        children_of.setdefault(parent, []).append(child)
        parents_of.setdefault(child, set()).add(parent)

    cycle = _find_cycle(children_of, node_ids)

    def story_ref(story_id: str) -> dict[str, str]:
        return {"id": story_id, "name": name_of[story_id]}

    # A changed edge affects its child and everything downstream of it.
    affected: set[str] = set()
    for child, _parent in [*added, *removed]:
        queue = [child]
        while queue:
            current = queue.pop()
            if current in affected:
                continue
            affected.add(current)
            queue.extend(children_of.get(current, []))

    result: dict[str, Any] = {
        "valid": cycle is None,
        "cycle": [story_ref(i) for i in cycle] if cycle else None,
        "addedEdges": [{"story": story_ref(c), "dependsOn": story_ref(p)} for c, p in added],
        "removedEdges": [{"story": story_ref(c), "dependsOn": story_ref(p)} for c, p in removed],
        "affectedStories": [story_ref(i) for i in sorted(affected, key=lambda i: name_of[i])],
        "edges": [{"source": p, "target": c} for p, c in sorted(edge_set)],
    }
    result["runOrder"] = (
        None
        if cycle
        else [
            [story_ref(i) for i in level] for level in _run_order(children_of, parents_of, node_ids)
        ]
    )
    return result
