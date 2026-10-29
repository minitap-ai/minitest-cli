"""Refresh skills/minitest-cli/reference/ from the reference routes of testing-service.

The documents are rendered by testing-service from its knowledge fragments, so they are
never hand-edited here. This writes every served topic plus the `index.json` that
`minitest reference` falls back to offline, and removes files the server no longer
serves. The routes are public, so no credentials are needed.

    python3 scripts/sync-skill-references.py [--api-url URL]   # refresh from the server
    python3 scripts/sync-skill-references.py --check           # offline consistency check
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parents[1] / "skills" / "minitest-cli" / "reference"
INDEX_FILE = "index.json"
DEFAULT_API_URL = "https://testing-service.app.minitap.ai"


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "minitest-cli-release"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def sync(api_url: str) -> None:
    base = f"{api_url.rstrip('/')}/api/skills/reference"
    index = json.loads(_get(base))
    documents = {entry["topic"]: _get(f"{base}/{entry['topic']}") for entry in index}
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    for stale in REFERENCE_DIR.glob("*.md"):
        if stale.stem not in documents:
            stale.unlink()
    for topic, content in documents.items():
        (REFERENCE_DIR / f"{topic}.md").write_bytes(content)
    (REFERENCE_DIR / INDEX_FILE).write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"Synced {', '.join(documents)} from {base}")


def check() -> list[str]:
    index = json.loads((REFERENCE_DIR / INDEX_FILE).read_text(encoding="utf-8"))
    problems = [
        f"index entry without topic, title and summary: {entry}"
        for entry in index
        if not all(entry.get(key) for key in ("topic", "title", "summary"))
    ]
    indexed = {entry.get("topic") for entry in index}
    on_disk = {path.stem for path in REFERENCE_DIR.glob("*.md")}
    problems += [f"{topic}.md is missing" for topic in sorted(indexed - on_disk)]
    problems += [f"{name}.md is not in {INDEX_FILE}" for name in sorted(on_disk - indexed)]
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh or check the bundled skill references.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check:
        sync(args.api_url)
        return
    problems = check()
    for problem in problems:
        print(f"::error::{problem} (run scripts/sync-skill-references.py)")
    if problems:
        sys.exit(1)
    print("Bundled references match their index")


if __name__ == "__main__":
    main()
