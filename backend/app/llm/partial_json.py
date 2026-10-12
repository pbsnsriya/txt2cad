"""Read the steps of a JSON reply that is still being written.

`complete_steps(text)` returns the objects of the "steps" array that are fully written, plus the text of the one still open
(so the UI can say what is being drafted). Never raises on a truncated reply.
"""

from __future__ import annotations

import json
import re
from typing import Any

_STEPS_KEY = re.compile(r'"steps"\s*:\s*\[')


def complete_steps(text: str) -> tuple[list[dict[str, Any]], str | None]:
    m = _STEPS_KEY.search(text)
    if not m:
        return [], None
    steps: list[dict[str, Any]] = []
    i, n = m.end(), len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            return steps, None
        if text[i] != "{":
            return steps, None            # unexpected shape; stop rather than guess
        depth, in_str, esc, j = 0, False, False, i
        while j < n:
            ch = text[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth != 0 or j >= n:
            return steps, text[i:]        # still being written
        try:
            obj = json.loads(text[i:j + 1])
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            steps.append(obj)
        i = j + 1
    return steps, None


def peek_draft(open_fragment: str | None) -> str | None:
    """A short human label for the step being written ("room Kitchen"), from whatever fields have arrived."""
    if not open_fragment:
        return None
    kind = re.search(r'"step"\s*:\s*"([a-z]+)"', open_fragment)
    name = re.search(r'"(?:name|room)"\s*:\s*"([^"]+)"', open_fragment)
    if not kind:
        return None
    return f"{kind.group(1)} {name.group(1)}" if name else kind.group(1)
