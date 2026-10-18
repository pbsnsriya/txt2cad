"""Cut a release: one command, so every release is made the same way.

    python scripts/release.py 0.7.0            move the Unreleased notes of CHANGELOG.md under 0.7.0, set the version everywhere, commit and tag
    python scripts/release.py 0.7.0 --dry-run  show what would change and touch nothing
    python scripts/release.py --notes 0.7.0    print the changelog section of a version (the release workflow uses this for the GitHub Release text)

It does not push. Afterwards:  git push && git push origin v0.7.0   (the tag starts the release workflow).
The version is kept in VERSION, frontend/package.json and e2e/package.json; the backend reads VERSION.
"""

from __future__ import annotations

import datetime
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$")
REPO = "https://github.com/pbsnsriya/txt2cad"


def run(*cmd: str, cwd: Path = ROOT) -> str:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True, shell=(sys.platform == "win32" and cmd[0] == "npm")).stdout.strip()


def key(version: str) -> tuple:
    """Sort key following the precedence rules of semver.org: a pre-release is older than its release, numeric identifiers compare as numbers."""
    m = SEMVER.match(version)
    assert m, version
    pre = m.group(4)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), pre is None, [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in (pre or "").split(".")])


def section(changelog: str, version: str) -> str:
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: )", changelog, re.S | re.M)
    if not m:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    return m.group(1).strip() + "\n"


def relink(changelog: str) -> str:
    """Rebuild the comparison links at the bottom from the version headings."""
    body = re.split(r"^\[Unreleased\]: ", changelog, flags=re.M)[0].rstrip("\n")
    versions = re.findall(r"^## \[(\d[^\]]*)\]", body, re.M)
    links = [f"[Unreleased]: {REPO}/compare/v{versions[0]}...HEAD"] if versions else []
    for i, v in enumerate(versions):
        links.append(f"[{v}]: {REPO}/compare/v{versions[i + 1]}...v{v}" if i + 1 < len(versions) else f"[{v}]: {REPO}/releases/tag/v{v}")
    return body + "\n\n" + "\n".join(links) + "\n"


def main(argv: list[str]) -> int:
    changelog_path = ROOT / "CHANGELOG.md"
    if len(argv) == 3 and argv[1] == "--notes":
        print(section(changelog_path.read_text(encoding="utf-8"), argv[2].removeprefix("v")), end="")
        return 0
    if len(argv) < 2 or not SEMVER.match(argv[1]):
        print(__doc__)
        return 2
    version, dry = argv[1], "--dry-run" in argv
    current = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if key(version) <= key(current):
        raise SystemExit(f"{version} is not newer than the current version {current}")
    if not dry and run("git", "status", "--porcelain"):
        raise SystemExit("the working tree is not clean; commit or stash first")
    if not dry and run("git", "branch", "--show-current") != "main":
        raise SystemExit("release from main")
    if run("git", "tag", "--list", f"v{version}"):
        raise SystemExit(f"the tag v{version} exists already; a released version is never changed, release a new one")

    text = changelog_path.read_text(encoding="utf-8")
    m = re.search(r"^## \[Unreleased\]\n(.*?)(?=^## \[)", text, re.S | re.M)
    if not m or not re.search(r"^- ", m.group(1), re.M):
        raise SystemExit("CHANGELOG.md has nothing under [Unreleased]; write what changed for people first")
    new = text.replace(m.group(0), f"## [Unreleased]\n\n## [{version}] - {datetime.date.today().isoformat()}\n{m.group(1).rstrip()}\n\n", 1)
    new = relink(new)
    print(f"{current} -> {version}\n--- notes ---\n{section(new, version)}")
    if dry:
        return 0

    changelog_path.write_text(new, encoding="utf-8", newline="\n")
    (ROOT / "VERSION").write_text(version + "\n", encoding="utf-8", newline="\n")
    for folder in ("frontend", "e2e"):
        run("npm", "version", version, "--no-git-tag-version", "--allow-same-version", cwd=ROOT / folder)
    run("git", "add", "CHANGELOG.md", "VERSION", "frontend/package.json", "frontend/package-lock.json", "e2e/package.json", "e2e/package-lock.json")
    run("git", "commit", "-m", f"chore(release): v{version}")
    run("git", "tag", "-a", f"v{version}", "-m", f"txt2cad {version}")
    print(f"committed and tagged v{version}. Push with:  git push && git push origin v{version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
