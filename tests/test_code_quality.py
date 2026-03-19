"""Code quality guardrails enforced as tests."""

from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
MAX_FILE_LINES = 200


class TestFileLength:
    """Enforce a maximum line count per source file."""

    def test_no_source_file_exceeds_max_lines(self):
        violations: list[str] = []
        for py_file in sorted(SRC_DIR.rglob("*.py")):
            line_count = len(py_file.read_text(encoding="utf-8").splitlines())
            if line_count > MAX_FILE_LINES:
                rel = py_file.relative_to(SRC_DIR)
                violations.append(f"  {rel}: {line_count} lines (max {MAX_FILE_LINES})")

        assert not violations, f"Source files exceeding {MAX_FILE_LINES} lines:\n" + "\n".join(
            violations
        )
