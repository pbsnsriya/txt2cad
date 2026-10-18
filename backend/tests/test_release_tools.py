"""The commit-message check and the release script (scripts/ at the root of the repository)."""

import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


commit = load("check_commit_message")
release = load("release")


# --- conventional commits --------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("message", [
    "feat: add archways",
    "fix(derive): keep a door off a stair well",
    "feat(api)!: rename the run endpoint\n\nBREAKING CHANGE: /runs is now /builds",
    "docs: correct the README\n\nA body after a blank line.\n\nRefs: #12",
    "chore(release): v0.7.0",
    "Merge branch 'main' into feat/x",
    "Revert \"feat: add archways\"",
    "fixup! feat: add archways",
])
def test_good_messages_pass(message):
    assert commit.problems(message) == []


@pytest.mark.parametrize("message,expected", [
    ("Add archways", "type(scope)"),
    ("feature: add archways", "type(scope)"),
    ("feat:add archways", "type(scope)"),
    ("feat: add archways.", "full stop"),
    ("feat: " + "x" * 80, "characters"),
    ("feat: add archways\nno blank line", "blank line"),
])
def test_bad_messages_say_what_is_wrong(message, expected):
    assert any(expected in p for p in commit.problems(message))


def test_comment_lines_from_git_are_ignored():
    assert commit.problems("# Please enter the commit message\nfix: a bug\n# more comments") == []


# --- semantic versions -----------------------------------------------------------------------------------------------------------------------
def test_versions_are_ordered_by_the_rules_of_semver_org():
    order = ["0.1.0", "0.2.0", "0.10.0", "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0", "1.0.1", "2.0.0"]
    assert [release.key(v) for v in order] == sorted(release.key(v) for v in order)
    assert release.key("1.0.0+build.5") == release.key("1.0.0+build.9")           # build metadata does not count


@pytest.mark.parametrize("version", ["1", "1.2", "01.2.3", "1.2.3.4", "v1.2.3", "1.2.3-", "1.2.3-01x..y"])
def test_malformed_versions_are_refused(version):
    assert not release.SEMVER.match(version)


SAMPLE = """# Changelog

## [Unreleased]

### Added

- A new thing.

## [1.0.0] - 2026-01-01

### Added

- The first thing.

[Unreleased]: x
[1.0.0]: y
"""


def test_a_section_is_read_by_version():
    assert release.section(SAMPLE, "1.0.0") == "### Added\n\n- The first thing.\n"
    with pytest.raises(SystemExit):
        release.section(SAMPLE, "9.9.9")


def test_links_are_rebuilt_from_the_headings():
    text = SAMPLE.split("[Unreleased]: x")[0].replace("## [1.0.0]", "## [1.1.0] - 2026-02-01\n\n- Y\n\n## [1.0.0]")
    out = release.relink(text)
    assert "[Unreleased]: https://github.com/pbsnsriya/txt2cad/compare/v1.1.0...HEAD" in out
    assert "[1.1.0]: https://github.com/pbsnsriya/txt2cad/compare/v1.0.0...v1.1.0" in out
    assert "[1.0.0]: https://github.com/pbsnsriya/txt2cad/releases/tag/v1.0.0" in out


def test_the_real_changelog_has_a_section_for_the_current_version_and_an_unreleased_heading():
    root = SCRIPTS.parent
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    current = (root / "VERSION").read_text(encoding="utf-8").strip()
    assert "## [Unreleased]" in text and release.section(text, current).strip()
