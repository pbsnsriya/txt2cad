"""The version of the application: one number, kept in the VERSION file at the root of the repository and changed only by scripts/release.py."""

from __future__ import annotations

from pathlib import Path

_FILE = Path(__file__).resolve().parents[2] / "VERSION"


def _read() -> str:
    try:
        return _FILE.read_text(encoding="utf-8").strip() or "0.0.0+unknown"
    except OSError:
        return "0.0.0+unknown"                     # semantic versioning's build metadata: a copy without the VERSION file says so


__version__ = _read()
