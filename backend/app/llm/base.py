"""The single seam between the app and any model. Providers implement `complete`; everything else is provider-agnostic."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

TextCallback = Callable[[str], None]


@dataclass
class LLMRequest:
    system: str
    user: str
    schema_name: str                      # "requirements" | "build"
    schema: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)   # side channel for the mock only
    images: list[dict[str, Any]] = field(default_factory=list)
    stop: threading.Event | None = None   # set by the caller to say "enough": providers stop reading and return what they have


class LLMError(RuntimeError):
    """The model could not be reached or answered with something unusable. Message is shown to the user."""


class LLM(Protocol):
    name: str
    vision: bool

    def complete(self, request: LLMRequest, on_text: TextCallback | None = None) -> dict[str, Any]:
        """Return the parsed JSON object. Call on_text(accumulated_reply) after each chunk when streaming."""


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any]:
    """Models that introduce themselves or fence the JSON still count: cut to the outermost braces."""
    body = _FENCE.sub("", text.strip())
    start = body.find("{")
    if start < 0:
        raise LLMError("the model did not return JSON")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(body)):
        ch = body[i]
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(body[start:i + 1])
                except json.JSONDecodeError as exc:
                    raise LLMError(f"the model returned malformed JSON: {exc}") from exc
    # reply cut off mid-object: keep every complete step we can recover
    from .partial_json import complete_steps
    steps, _ = complete_steps(body)
    if steps:
        return {"steps": steps}
    raise LLMError("the reply ended before the JSON was complete")
