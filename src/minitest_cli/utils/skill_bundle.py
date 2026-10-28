"""The agent skill that ships inside this CLI.

The skill lives in the repository at ``skills/minitest-cli`` and is force-included in
the wheel at ``minitest_cli/_skills/minitest-cli``, so the skill an agent reads always
describes the CLI version it is installed with. Everything here works offline.
"""

import hashlib
import re
import shutil
from importlib import resources
from pathlib import Path

from minitest_cli import __version__

SKILL_NAME = "minitest-cli"

# Files the `skills` installer does not copy into an installed skill.
_NOT_INSTALLED = frozenset({"metadata.json"})
_IGNORED_DIRS = frozenset({"__pycache__"})

_FRONTMATTER = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
_STAMP_KEY = "cli-version"


def bundle_dir() -> Path:
    """Directory holding the skill: the wheel copy, else the repo copy (source checkout)."""
    packaged = Path(str(resources.files("minitest_cli") / "_skills" / SKILL_NAME))
    if (packaged / "SKILL.md").is_file():
        return packaged
    checkout = Path(__file__).resolve().parents[3] / "skills" / SKILL_NAME
    if (checkout / "SKILL.md").is_file():
        return checkout
    raise FileNotFoundError("The minitest-cli agent skill is not bundled with this install.")


def stamp(skill_md: str, version: str) -> str:
    """Record the CLI version in the SKILL.md frontmatter (``metadata.cli-version``).

    Done at read time from the running version, so releases need no extra file to bump.
    Idempotent: stamping twice leaves one line.
    """
    match = _FRONTMATTER.match(skill_md)
    if match is None:
        return skill_md
    lines = [
        line for line in match.group("body").split("\n") if not re.match(rf"\s+{_STAMP_KEY}:", line)
    ]
    entry = f'  {_STAMP_KEY}: "{version}"'
    if "metadata:" in lines:
        lines.insert(lines.index("metadata:") + 1, entry)
    else:
        lines += ["metadata:", entry]
    return f"---\n{chr(10).join(lines)}\n---\n{skill_md[match.end() :]}"


def bundled_skill_md() -> str:
    """The stamped SKILL.md of this CLI version."""
    return stamp((bundle_dir() / "SKILL.md").read_text(encoding="utf-8"), __version__)


def bundled_files() -> dict[str, bytes]:
    """Every file of the installed skill, keyed by path relative to the skill directory."""
    root = bundle_dir()
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or relative.name in _NOT_INSTALLED:
            continue
        if _IGNORED_DIRS.intersection(relative.parts):
            continue
        data = path.read_bytes()
        if str(relative) == "SKILL.md":
            data = stamp(data.decode("utf-8"), __version__).encode("utf-8")
        files[relative.as_posix()] = data
    return files


def _digest(files: dict[str, bytes]) -> str:
    hasher = hashlib.sha256()
    for name in sorted(files):
        hasher.update(name.encode())
        hasher.update(b"\0")
        hasher.update(hashlib.sha256(files[name]).digest())
    return hasher.hexdigest()


def read_installed(target: Path) -> dict[str, bytes]:
    """Files of an installed copy, with the same key shape as ``bundled_files``."""
    return {
        path.relative_to(target).as_posix(): path.read_bytes()
        for path in sorted(target.rglob("*"))
        if path.is_file() and not _IGNORED_DIRS.intersection(path.relative_to(target).parts)
    }


def is_current(target: Path) -> bool:
    """True when the installed skill is byte-for-byte this CLI's skill (references included)."""
    return _digest(read_installed(target)) == _digest(bundled_files())


def install_into(target: Path) -> None:
    """Make ``target`` an exact copy of this CLI's skill, in place.

    Writes into the existing directory so symlinks to it (``~/.claude/skills`` pointing
    at ``~/.agents/skills``) keep working. Files the new version dropped are removed.
    """
    if target.name != SKILL_NAME:
        raise ValueError(f"Refusing to overwrite {target}: not a {SKILL_NAME} skill directory.")
    files = bundled_files()
    target.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    for path in sorted(target.rglob("*"), reverse=True):
        relative = path.relative_to(target).as_posix()
        if path.is_file() and relative not in files:
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            shutil.rmtree(path)


def install_command(version: str = __version__) -> list[str]:
    """The `skills` command that installs this CLI version's skill from its release tag."""
    return [
        "npx",
        "skills",
        "add",
        f"https://github.com/minitap-ai/minitest-cli/tree/v{version}/skills/{SKILL_NAME}",
        "--skill",
        SKILL_NAME,
    ]
