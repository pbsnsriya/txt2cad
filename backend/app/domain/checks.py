"""Deterministic check of a design against the checklist extracted from the prompt."""

from __future__ import annotations

from typing import Any

from .design import Design

UNSUPPORTED_FEATURES = {"porch", "balcony", "basement", "pool", "garden", "furniture"}
ALWAYS_BUILDABLE = {"storeys", "room", "window", "door"}


def normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """A checklist item as the app stores it (kind, text, supported, params)."""
    params = {k: raw[k] for k in ("keyword", "count", "level", "side") if raw.get(k) is not None}
    keyword = str(params.get("keyword", "")).lower()
    kind = raw.get("kind", "other")
    # Small models mark everything "unsupported". For kinds this tool really builds, ignore the model's flag; keep it for the rest.
    supported = True if kind in ALWAYS_BUILDABLE else raw.get("supported", True) is not False
    if kind == "feature" and keyword in UNSUPPORTED_FEATURES:
        supported = False
    return {"kind": kind, "text": raw.get("text", ""), "supported": supported, "params": params}


def _matching_rooms(design: Design, keyword: str, level: str | None):
    kw = keyword.lower()
    return [r for r in design.rooms if (r.kind == kw or kw in r.name.lower()) and (level is None or r.level == level)]


def check(design: Design, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for req in requirements:
        r = dict(req)
        p = r.get("params", {})
        if not r.get("supported", True):
            r["status"], r["detail"] = "unsupported", "this tool cannot build it yet; noted in the version summary"
        elif r["kind"] == "storeys":
            want, have = int(p.get("count", 1)), design.storeys()
            r["status"], r["detail"] = ("met", f"{have} storey(s)") if have == want else ("unmet", f"wanted {want} storeys, the design has {have}")
        elif r["kind"] in ("room", "feature") and p.get("keyword"):
            want = int(p.get("count", 1))
            found = _matching_rooms(design, str(p["keyword"]), p.get("level"))
            r["status"], r["detail"] = ("met", f"{len(found)} found") if len(found) >= want else ("unmet", f"wanted {want} '{p['keyword']}', found {len(found)}")
        else:
            r["status"], r["detail"] = "not_checked", "no automatic check for this kind of requirement"
        out.append(r)
    return out


def unmet(results: list[dict[str, Any]]) -> list[str]:
    return [f"{r['text']}: {r['detail']}" for r in results if r["status"] == "unmet"]


NO_WINDOW_NEEDED = {"hall", "storage", "utility", "garage", "bathroom", "other"}


def completeness(design: Design) -> list[str]:
    """Things every building needs that no prompt states: daylight in habitable rooms, doors linking the rooms of a level."""
    out: list[str] = []
    windowed = {w.room for w in design.windows}
    for r in design.rooms:
        if r.kind not in NO_WINDOW_NEEDED and r.id not in windowed:
            out.append(f"room '{r.name}' has no window; add one on an exterior side")
    for i, lv in enumerate(design.levels[1:], 1):
        below = design.levels[i - 1].id
        if not any((design.room(s.room) is not None and design.room(s.room).level == below) for s in design.stairs):  # type: ignore[union-attr]
            out.append(f"{lv.id} has no stair up from {below}; add a stair step in a room on {below} (side = the wall it runs along), "
                       f"with a hall or landing on {lv.id} exactly above it")
    for lv in design.levels:
        ids = [r.id for r in design.rooms if r.level == lv.id]
        if len(ids) < 2:
            continue
        parent = {i: i for i in ids}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for door in design.doors:
            if door.room in parent and door.to in parent:
                parent[find(door.room)] = find(door.to)
        groups: dict[str, list[str]] = {}
        for i in ids:
            groups.setdefault(find(i), []).append(i)
        if len(groups) > 1:
            names = [", ".join(g) for g in groups.values()]
            out.append(f"on {lv.id} these rooms are not linked by doors: {' | '.join(names)}; add doors so every room can be reached")
    return out
