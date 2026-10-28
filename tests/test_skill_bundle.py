"""The agent skill bundled in the CLI: shape, stamping, installing and refreshing."""

import re
from pathlib import Path

import pytest

from minitest_cli import __version__
from minitest_cli.utils import skill_bundle, skill_refresh
from minitest_cli.utils.skill_refresh import UpgradeStatus

SKILL_MD = "---\nname: minitest-cli\ndescription: x\n---\n# Body\n"


class TestStamp:
    def test_adds_a_metadata_block(self) -> None:
        stamped = skill_bundle.stamp(SKILL_MD, "1.2.3")
        assert stamped == (
            "---\nname: minitest-cli\ndescription: x\n"
            'metadata:\n  cli-version: "1.2.3"\n---\n# Body\n'
        )

    def test_extends_an_existing_metadata_block(self) -> None:
        text = "---\nname: a\nmetadata:\n  owner: team\n---\nbody\n"
        stamped = skill_bundle.stamp(text, "1.2.3")
        assert 'metadata:\n  cli-version: "1.2.3"\n  owner: team' in stamped

    def test_is_idempotent_and_restamps(self) -> None:
        once = skill_bundle.stamp(SKILL_MD, "1.2.3")
        assert skill_bundle.stamp(once, "1.2.3") == once
        assert 'cli-version: "2.0.0"' in skill_bundle.stamp(once, "2.0.0")
        assert skill_bundle.stamp(once, "2.0.0").count("cli-version") == 1

    def test_leaves_text_without_frontmatter_alone(self) -> None:
        assert skill_bundle.stamp("# no frontmatter", "1.0.0") == "# no frontmatter"


class TestBundleContent:
    def test_skill_md_is_valid_and_stamped_with_this_version(self) -> None:
        text = skill_bundle.bundled_skill_md()
        assert text.startswith("---\nname: minitest-cli\n")
        assert f'cli-version: "{__version__}"' in text

    def test_relative_links_resolve_inside_the_skill(self) -> None:
        files = skill_bundle.bundled_files()
        links = re.findall(r"\]\((?!https?:|#|mailto:)([^)#\s]+)", files["SKILL.md"].decode())
        missing = [link for link in links if link not in files]
        assert missing == []

    def test_ships_references_and_commands_but_not_metadata_json(self) -> None:
        files = skill_bundle.bundled_files()
        assert any(name.startswith("reference/") for name in files)
        assert any(name.startswith("commands/") for name in files)
        assert "metadata.json" not in files


class TestInstall:
    def test_install_makes_an_exact_copy_and_drops_stale_files(self, tmp_path: Path) -> None:
        target = tmp_path / "minitest-cli"
        (target / "reference").mkdir(parents=True)
        (target / "SKILL.md").write_text("old")
        (target / "reference" / "removed-in-this-version.md").write_text("stale")

        skill_bundle.install_into(target)

        assert skill_bundle.is_current(target)
        assert not (target / "reference" / "removed-in-this-version.md").exists()

    def test_a_changed_reference_file_makes_the_install_outdated(self, tmp_path: Path) -> None:
        target = tmp_path / "minitest-cli"
        skill_bundle.install_into(target)
        reference = next((target / "reference").glob("*.md"))
        reference.write_text("edited")

        assert not skill_bundle.is_current(target)

    def test_refuses_to_overwrite_a_directory_that_is_not_the_skill(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            skill_bundle.install_into(tmp_path / "documents")

    def test_install_command_pins_the_release_tag(self) -> None:
        command = skill_bundle.install_command("1.2.3")
        assert (
            "https://github.com/minitap-ai/minitest-cli/tree/v1.2.3/skills/minitest-cli" in command
        )
        assert command[-2:] == ["--skill", "minitest-cli"]


class TestRefresh:
    def test_not_installed_is_skipped(self, monkeypatch) -> None:
        monkeypatch.setattr(skill_refresh, "find_skill_paths", lambda: [])
        assert skill_refresh.check_and_refresh() is UpgradeStatus.SKIPPED

    def test_outdated_install_is_refreshed_then_up_to_date(self, tmp_path, monkeypatch) -> None:
        target = tmp_path / "minitest-cli"
        target.mkdir()
        (target / "SKILL.md").write_text("old")
        monkeypatch.setattr(skill_refresh, "find_skill_paths", lambda: [str(target)])

        assert skill_refresh.check_and_refresh() is UpgradeStatus.UPGRADED
        assert skill_refresh.check_and_refresh() is UpgradeStatus.UP_TO_DATE

    def test_symlinked_install_is_refreshed_through_the_link(self, tmp_path, monkeypatch) -> None:
        real = tmp_path / "agents" / "skills" / "minitest-cli"
        real.mkdir(parents=True)
        (real / "SKILL.md").write_text("old")
        link_parent = tmp_path / "claude" / "skills"
        link_parent.mkdir(parents=True)
        (link_parent / "minitest-cli").symlink_to(real, target_is_directory=True)

        monkeypatch.setenv("HOME", str(tmp_path))
        # ~/.agents and ~/.claude both resolve to the same directory: refreshed once.
        (tmp_path / ".agents").symlink_to(tmp_path / "agents", target_is_directory=True)
        (tmp_path / ".claude").symlink_to(tmp_path / "claude", target_is_directory=True)

        assert len(skill_refresh.find_skill_paths()) == 1
        assert skill_refresh.check_and_refresh() is UpgradeStatus.UPGRADED
        assert skill_bundle.is_current(real)

    def test_finds_an_install_without_npx_in_the_conventional_location(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        target = tmp_path / ".agents" / "skills" / "minitest-cli"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("old")

        assert skill_refresh.find_skill_paths() == [str(target)]
