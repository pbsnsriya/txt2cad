"""Check commit messages against Conventional Commits 1.0.0 (https://www.conventionalcommits.org/en/v1.0.0/).

    python scripts/check_commit_message.py .git/COMMIT_EDITMSG        one message in a file (what the commit-msg hook passes)
    python scripts/check_commit_message.py --range origin/main..HEAD   every commit in a range (what CI runs on a pull request)

The first line must be   type(scope)!: description   with a type from TYPES, a description of at most 72 characters that does not end with a full stop.
Merge, revert, fixup! and squash! commits are left alone.
"""

from __future__ import annotations

import re
import subprocess
import sys

TYPES = ("feat", "fix", "docs", "style", "refactor", "perf", "test", "build", "ci", "chore", "revert")
PATTERN = re.compile(rf"^(?:{'|'.join(TYPES)})(?:\([a-z0-9][a-z0-9._/-]*\))?!?: \S.*$")
MAX_SUBJECT = 72
SKIPPED = ("Merge ", "Revert ", "fixup! ", "squash! ")


def problems(message: str) -> list[str]:
    lines = [ln for ln in message.splitlines() if not ln.startswith("#")]
    subject = next((ln for ln in lines if ln.strip()), "")
    if subject.startswith(SKIPPED):
        return []
    out = []
    if not PATTERN.match(subject):
        out.append(f"the first line must look like 'type(scope): description' with a type from {', '.join(TYPES)}")
    if len(subject) > MAX_SUBJECT:
        out.append(f"the first line is {len(subject)} characters; keep it to {MAX_SUBJECT} and put the rest in the body")
    if subject.endswith("."):
        out.append("the first line should not end with a full stop")
    rest = lines[lines.index(subject) + 1:] if subject in lines else []
    if rest and rest[0].strip():
        out.append("leave one blank line between the first line and the body")
    return out


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--range":
        log = subprocess.run(["git", "log", "--format=%H%x1f%B%x1e", argv[2]], capture_output=True, text=True, check=True).stdout
        commits = [c.strip("\n") for c in log.split("\x1e") if c.strip()]
        bad = 0
        for c in commits:
            sha, _, message = c.partition("\x1f")
            found = problems(message)
            if found:
                bad += 1
                print(f"{sha[:8]} {message.splitlines()[0][:80]}")
                for p in found:
                    print(f"    - {p}")
        print(f"{len(commits)} commit(s) checked, {bad} to fix")
        return 1 if bad else 0
    if len(argv) == 2:
        with open(argv[1], encoding="utf-8") as f:
            found = problems(f.read())
        for p in found:
            print(f"commit message: {p}", file=sys.stderr)
        if found:
            print("see CONTRIBUTING.md; example:  fix(derive): keep a door off a stair well", file=sys.stderr)
        return 1 if found else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
