"""Tests for minitest_cli.utils.mermaid — Mermaid graph generation."""

from minitest_cli.utils.mermaid import build_dependency_graph


class TestBuildDependencyGraph:
    def test_empty_list_returns_none(self):
        assert build_dependency_graph([], []) is None

    def test_nodes_without_edges_renders_nodes_only(self):
        nodes = [
            {"id": "a", "name": "Login", "type": "feature"},
            {"id": "b", "name": "Signup", "type": "feature"},
        ]
        result = build_dependency_graph(nodes, [])
        assert result is not None
        assert result.startswith("flowchart TD\n")
        assert '"Login\\n(feature)"' in result
        assert '"Signup\\n(feature)"' in result
        assert "No dependency edges found" in result

    def test_edges_rendered(self):
        nodes = [
            {"id": "a", "name": "Login", "type": "feature"},
            {"id": "b", "name": "Dashboard", "type": "feature"},
            {"id": "c", "name": "Settings", "type": "feature"},
        ]
        edges = [
            {"source": "a", "target": "b"},
            {"source": "a", "target": "c"},
            {"source": "b", "target": "c"},
        ]
        result = build_dependency_graph(nodes, edges)
        assert result is not None
        assert "a --> b" in result
        assert "a --> c" in result
        assert "b --> c" in result
        assert "No dependency edges found" not in result

    def test_dangling_edge_ids_are_excluded(self):
        nodes = [{"id": "a", "name": "Login", "type": "feature"}]
        edges = [{"source": "nonexistent", "target": "a"}]
        result = build_dependency_graph(nodes, edges)
        assert result is not None
        assert "-->" not in result

    def test_special_chars_are_escaped(self):
        nodes = [{"id": "a", "name": 'Click "OK" & <done>', "type": "other"}]
        result = build_dependency_graph(nodes, [])
        assert result is not None
        assert "#quot;" in result
        assert "#amp;" in result
        assert "#lt;" in result
        assert "#gt;" in result
        label = result.split('["')[1].split('"]')[0]
        assert '"' not in label
        assert "<" not in label
        assert ">" not in label
        assert "&" not in label

    def test_deterministic_output_order(self):
        nodes = [
            {"id": "c", "name": "Third", "type": "feature"},
            {"id": "a", "name": "First", "type": "feature"},
            {"id": "b", "name": "Second", "type": "feature"},
        ]
        edges = [
            {"source": "a", "target": "c"},
            {"source": "a", "target": "b"},
        ]
        result = build_dependency_graph(nodes, edges)
        assert result is not None
        lines = result.strip().split("\n")
        node_lines = [line for line in lines if '["' in line]
        assert node_lines[0].strip().startswith("a[")
        assert node_lines[1].strip().startswith("b[")
        assert node_lines[2].strip().startswith("c[")
