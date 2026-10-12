"""Offline model for demos and tests: turns a prompt into a plausible design with regexes and a strip packer. No network.

It exists so the whole pipeline (streaming, validation, derive, IFC, DXF) runs with no model installed. It understands storeys,
bedroom counts and a handful of room words; it does NOT edit (an edit prompt yields no steps, which the pipeline reports).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from .base import LLMRequest, TextCallback

NUMBER_WORDS = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
ROOM_WORDS: list[tuple[str, str, float]] = [   # keyword, kind, target area m2
    ("kitchen", "kitchen", 14.0), ("living", "living", 20.0), ("dining", "dining", 12.0), ("office", "office", 10.0), ("study", "office", 10.0),
    ("garage", "garage", 18.0), ("utility", "utility", 6.0), ("storage", "storage", 6.0),
]
ROW_WIDTH_M = 12.0
CHUNK_CHARS = 60
CHUNK_DELAY_S = 0.004


def _count(text: str, word: str) -> int:
    m = re.search(r"\b(\d+|one|two|three|four|five|six|seven|eight|an?)\s+(?:\w+\s+){0,2}?" + word, text)
    if not m:
        return 1 if re.search(word, text) else 0
    raw = m.group(1)
    return int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 1)


def parse_prompt(prompt: str) -> dict[str, Any]:
    t = prompt.lower()
    storeys = 2 if re.search(r"two[- ]stor|2[- ]stor|two floors|double stor", t) else 3 if re.search(r"three[- ]stor|3[- ]stor", t) else 1
    rooms: list[tuple[str, str, float]] = []
    for word, kind, area in ROOM_WORDS:
        if re.search(word, t):
            rooms.append((word.capitalize(), kind, area))
    return {"storeys": storeys, "bedrooms": _count(t, "bedroom"), "bathrooms": max(_count(t, "bath"), 1 if storeys > 1 else 0), "rooms": rooms}


def _pack(items: list[tuple[str, str, float]], y0: float, row_depth: float) -> list[dict[str, Any]]:
    """Lay rooms in one row, widths proportional to target area, summing to ROW_WIDTH_M exactly."""
    total = sum(a for _, _, a in items)
    out, x = [], 0.0
    for i, (name, kind, area) in enumerate(items):
        w = round(ROW_WIDTH_M * area / total, 1) if i < len(items) - 1 else round(ROW_WIDTH_M - x, 1)
        out.append({"name": name, "kind": kind, "rect": [round(x, 1), y0, w, row_depth]})
        x += w
    return out


def build_steps(prompt: str) -> list[dict[str, Any]]:
    p = parse_prompt(prompt)
    steps: list[dict[str, Any]] = [{"step": "building", "name": "Generated building", "why": "named from the brief"}]
    ground = [("Hall", "hall", 10.0), *p["rooms"]] if p["rooms"] else [("Hall", "hall", 10.0), ("Living", "living", 20.0), ("Kitchen", "kitchen", 14.0)]
    upper: list[tuple[str, str, float]] = [(f"Bedroom {i + 1}", "bedroom", 13.0) for i in range(max(p["bedrooms"], 1 if p["storeys"] > 1 else 0))]
    if p["storeys"] == 1:
        ground += [(f"Bedroom {i + 1}", "bedroom", 13.0) for i in range(p["bedrooms"])]
        if p["bathrooms"]:
            ground.append(("Bathroom", "bathroom", 6.0))
    elif p["bathrooms"]:
        upper.append(("Bathroom", "bathroom", 6.0))
    # every upper level starts with a landing at the same corner as the ground-floor hall, so one flight can climb through them
    per_level: list[list[tuple[str, str, float]]] = [ground] + [[(f"Landing {i + 1}", "hall", 10.0), *upper] for i in range(1, p["storeys"])]
    return [steps[0], *layout_steps(per_level)]


def layout_steps(per_level: list[list[tuple[str, str, float]]]) -> list[dict[str, Any]]:
    """Rooms per level (the first room of each level is its hall or landing) -> a complete, valid step list: levels, two packed rows
    of rooms, one stair per storey against the hall's west wall, doors from the hall outwards, windows, roof. No model involved."""
    steps: list[dict[str, Any]] = []
    depth_front, depth_back = 4.5, 4.0
    for i, items in enumerate(per_level, 1):
        steps.append({"step": "level", "id": f"L{i}", "name": "Ground floor" if i == 1 else f"Level {i}", "height": 3.0, "why": "storey stack"})
        mid = (len(items) + 1) // 2
        placed = _pack(items[:mid], 0.0, depth_front) + (_pack(items[mid:], depth_front, depth_back) if items[mid:] else [])
        steps.append({"step": "layout", "level": f"L{i}", "rooms": placed, "why": "rooms packed edge to edge in two rows"})
    for i in range(1, len(per_level)):
        steps.append({"step": "stair", "room": per_level[i - 1][0][0], "side": "W", "why": "stair against the hall wall, landing above"})
    steps += _openings(steps)
    steps.append({"step": "roof", "kind": "flat", "why": "flat roof is the supported type"})
    return steps


def _openings(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from ..domain.design import Design
    from ..domain.derive import exterior_sides, wall_pieces
    from ..domain.steps import Step, apply_step

    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    sides = exterior_sides(d)
    pieces = wall_pieces(d)
    out: list[dict[str, Any]] = []
    for lv in d.levels:
        rooms = [r for r in d.rooms if r.level == lv.id]
        hall = next((r for r in rooms if r.kind == "hall"), rooms[0])
        seen, queue = {hall.id}, [hall.id]
        while queue:                                   # connect every room to the hall through doors, breadth first
            cur = queue.pop(0)
            for p in pieces:
                if p.level == lv.id and p.other and cur in (p.room, p.other):
                    nxt = p.other if p.room == cur else p.room
                    if nxt not in seen and p.length >= 1.3:
                        seen.add(nxt)
                        queue.append(nxt)
                        out.append({"step": "door", "room": cur, "to": nxt, "why": "circulation from the hall"})
        if lv.id == "L1":
            out.append({"step": "door", "room": hall.id, "to": "outside", "side": "S" if "S" in sides[hall.id] else sorted(sides[hall.id])[0], "at": 0.85, "why": "front door"})
        for r in rooms:
            for side in [s for s in ("S", "E", "W", "N") if s in sides[r.id]][:2 if r.kind in ("living", "kitchen") else 1]:
                out.append({"step": "window", "room": r.id, "side": side, "kind": "large" if r.kind == "living" else "standard", "why": "daylight"})
    return out


def build_requirements(prompt: str) -> list[dict[str, Any]]:
    p = parse_prompt(prompt)
    reqs: list[dict[str, Any]] = [{"kind": "storeys", "count": p["storeys"], "text": f"{p['storeys']} storey(s)", "supported": True}]
    if p["bedrooms"]:
        reqs.append({"kind": "room", "keyword": "bedroom", "count": p["bedrooms"], "text": f"{p['bedrooms']} bedroom(s)", "supported": True})
    for word, kind, _ in p["rooms"]:
        reqs.append({"kind": "room" if kind != "garage" else "feature", "keyword": kind, "count": 1, "text": word.lower(), "supported": True})
    return reqs


class MockLLM:
    name = "mock"
    vision = False

    def complete(self, request: LLMRequest, on_text: TextCallback | None = None) -> dict[str, Any]:
        prompt = request.meta.get("prompt", "")
        if request.schema_name == "requirements":
            return {"requirements": build_requirements(prompt)}
        if request.meta.get("has_design") or request.meta.get("round", 0) > 0:
            return {"approach": "The offline model cannot edit an existing design.", "steps": []}
        payload = {"approach": "Two rows of rooms packed edge to edge, a hall linking them, windows on exterior sides.", "steps": build_steps(prompt)}
        text = json.dumps(payload)
        if on_text:
            for end in range(CHUNK_CHARS, len(text) + CHUNK_CHARS, CHUNK_CHARS):
                on_text(text[:end])
                time.sleep(CHUNK_DELAY_S)
        return payload
