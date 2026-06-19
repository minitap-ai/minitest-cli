"""Build Mermaid flowchart strings from dependency-graph API data."""

from typing import Any

_MERMAID_SPECIAL = str.maketrans(
    {
        '"': "#quot;",
        "<": "#lt;",
        ">": "#gt;",
        "&": "#amp;",
        "{": "#lbrace;",
        "}": "#rbrace;",
    }
)


def _escape(text: str) -> str:
    return text.translate(_MERMAID_SPECIAL)


def build_dependency_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str | None:
    if not nodes:
        return None

    lines: list[str] = ["flowchart TD"]
    node_ids: set[str] = set()
    for node in sorted(nodes, key=lambda n: str(n["id"])):
        nid = str(node["id"])
        node_ids.add(nid)
        name = _escape(node.get("name", nid))
        ntype = node.get("type", "")
        label = f"{name}\\n({ntype})" if ntype else name
        lines.append(f'  {nid}["{label}"]')

    edges_added = False
    for edge in sorted(edges, key=lambda e: (str(e["source"]), str(e["target"]))):
        source = str(edge["source"])
        target = str(edge["target"])
        if source in node_ids and target in node_ids:
            lines.append(f"  {source} --> {target}")
            edges_added = True

    if not edges_added:
        lines.append("")
        lines.append("  %% No dependency edges found")

    return "\n".join(lines) + "\n"
