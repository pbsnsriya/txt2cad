"""The "program" planner: for models too small to place rooms and openings reliably.

The model only answers what a brief answers: how many storeys and which rooms on which level (and roughly how big). Code does the
rest, deterministically: packs the rooms, connects them with doors, adds windows, a stair per storey and the roof. The result is
always buildable, so a 1.5B model can produce a sensible house. Edits and fix rounds still go to the wrapped model as ordinary steps.
"""

from __future__ import annotations

import json
from typing import Any

from .base import LLM, LLMError, LLMRequest, TextCallback
from .mock import layout_steps

PROGRAM_SYSTEM = """You write the room program for a building. Return JSON: {"storeys": 1-3, "rooms": [ ... ]}.
Each room: {"name": "Kitchen", "kind": one of living kitchen dining bedroom bathroom hall office garage utility storage other, "level": 1 for the ground floor, 2 for the next, "area": square metres (optional)}.
Include every room the request names, with the right count (three bedrooms = three bedroom rooms). Bedrooms usually go upstairs in a house with two storeys.
Do not include halls, corridors or stairs: they are added automatically. Do not write any coordinates."""

PROGRAM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"storeys": {"type": "integer"}, "rooms": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "kind": {"type": "string"}, "level": {"type": "integer"}, "area": {"type": "number"}}, "required": ["name", "kind", "level"]}}},
    "required": ["storeys", "rooms"],
}

DEFAULT_AREA_M2 = {"living": 20.0, "kitchen": 14.0, "dining": 12.0, "bedroom": 13.0, "bathroom": 6.0, "office": 10.0, "garage": 18.0, "utility": 6.0, "storage": 6.0, "other": 10.0}
HALL_AREA_M2 = 10.0
MIN_AREA_M2, MAX_AREA_M2 = 4.0, 60.0
MAX_STOREYS = 3
MAX_ROOMS_PER_LEVEL = 8


def program_to_levels(program: dict[str, Any]) -> list[list[tuple[str, str, float]]]:
    """A room program -> per-level room lists with a hall first, unique names, sane areas. Raises LLMError if there is nothing to build."""
    rooms = [r for r in program.get("rooms", []) if isinstance(r, dict) and r.get("name") and r.get("kind") != "hall"]
    if not rooms:
        raise LLMError("the model listed no rooms")
    def level_of(r: dict[str, Any]) -> int:
        try:
            return max(1, int(r.get("level") or 1))
        except (TypeError, ValueError):
            return 1

    top = max(level_of(r) for r in rooms)
    try:
        declared = int(program.get("storeys") or top)
    except (TypeError, ValueError):
        declared = top                                  # "two" or null: trust the levels the rooms were given
    storeys = max(1, min(MAX_STOREYS, declared))            # the declared count wins; a storey with no rooms still gets a hall and a stair
    levels: list[list[tuple[str, str, float]]] = [[] for _ in range(storeys)]
    seen: dict[str, int] = {}
    for r in rooms:
        lv = min(storeys, level_of(r)) - 1
        if len(levels[lv]) >= MAX_ROOMS_PER_LEVEL:
            lv = min(range(storeys), key=lambda i: len(levels[i]))        # spill over to the emptiest level rather than drop a room
        kind = str(r.get("kind") or "other")
        kind = kind if kind in DEFAULT_AREA_M2 else "other"
        base = str(r["name"]).strip()[:30] or kind.capitalize()
        seen[base.lower()] = seen.get(base.lower(), 0) + 1
        name = base if seen[base.lower()] == 1 else f"{base} {seen[base.lower()]}"
        area = r.get("area")
        area = min(MAX_AREA_M2, max(MIN_AREA_M2, float(area))) if isinstance(area, (int, float)) else DEFAULT_AREA_M2[kind]
        levels[lv].append((name, kind, area))
    out = []
    for i, items in enumerate(levels, 1):
        out.append([("Hall" if i == 1 else f"Landing {i}", "hall", HALL_AREA_M2), *items])
    return out


class ProgramLLM:
    """Wraps another model. New designs go through the room-program route; everything else is passed straight through."""

    vision = False

    def __init__(self, inner: LLM) -> None:
        self.inner = inner
        self.name = f"program/{inner.name}"
        self.vision = inner.vision

    def complete(self, request: LLMRequest, on_text: TextCallback | None = None) -> dict[str, Any]:
        if request.schema_name != "build" or request.meta.get("has_design") or request.meta.get("round", 0) > 0:
            return self.inner.complete(request, on_text)
        asked = LLMRequest(PROGRAM_SYSTEM, request.meta.get("prompt", request.user), "program", PROGRAM_SCHEMA, meta=request.meta)
        program = self.inner.complete(asked, None)
        steps = [{"step": "building", "name": str(program.get("name") or request.meta.get("prompt", "Building"))[:60], "why": "named from the brief"}, *layout_steps(program_to_levels(program))]
        payload = {"approach": "Room program from the model; layout, doors, windows and stairs placed by rule.", "steps": steps}
        if on_text:
            text = json.dumps(payload)
            for end in range(80, len(text) + 80, 80):
                on_text(text[:end])
        return payload
