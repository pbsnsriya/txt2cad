"""Deterministic check of a design against the checklist extracted from the prompt."""

from __future__ import annotations

from typing import Any

from .design import Design

UNSUPPORTED_FEATURES = {"porch", "balcony", "basement", "pool", "garden", "furniture"}
ALWAYS_BUILDABLE = {"storeys", "room", "window", "door"}
ROOF_WORDS = {"roof", "pitched", "pitched roof", "gable", "gabled", "hip", "hipped", "shed", "mono-pitch", "monopitch", "sloped", "flat roof"}


def normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """A checklist item as the app stores it (kind, text, supported, params)."""
    params = {k: raw[k] for k in ("keyword", "count", "level", "side", "width", "depth", "area") if raw.get(k) is not None}
    keyword = str(params.get("keyword", "")).lower()
    kind = raw.get("kind", "other")
    # Small models mark everything "unsupported". For kinds this tool really builds, ignore the model's flag; keep it for the rest.
    supported = True if kind in ALWAYS_BUILDABLE else raw.get("supported", True) is not False
    if kind == "feature" and keyword in UNSUPPORTED_FEATURES:
        supported = False
    if kind == "feature" and keyword in ROOF_WORDS:
        supported = True
    return {"kind": kind, "text": raw.get("text", ""), "supported": supported, "params": params}


def _matching_rooms(design: Design, keyword: str, level: str | None):
    kw = keyword.lower()
    return [r for r in design.rooms if (r.kind == kw or kw in r.name.lower()) and (level is None or r.level == level)]


SIZE_TOLERANCE_M = 0.15        # a stated room size, either way round
FOOTPRINT_TOLERANCE_M = 0.25   # a stated overall size
AREA_TOLERANCE = 0.10          # a stated area, as a fraction
SIZE_KINDS = ("dimension", "area")


def merge_sizes(items: list[dict[str, Any]], sizes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sizes read from the prompt replace whatever size items the model listed: those have no numbers to measure."""
    return [i for i in items if i.get("kind") not in SIZE_KINDS] + sizes


def _rect_area(r) -> float:
    return r.rect[2] * r.rect[3]


def _footprint(design: Design) -> tuple[float, float] | None:
    """Overall width and depth of the lowest storey that has rooms."""
    for lv in design.levels:
        rooms = [r for r in design.rooms if r.level == lv.id]
        if rooms:
            x0, y0 = min(r.rect[0] for r in rooms), min(r.rect[1] for r in rooms)
            x1, y1 = max(r.rect[0] + r.rect[2] for r in rooms), max(r.rect[1] + r.rect[3] for r in rooms)
            return round(x1 - x0, 2), round(y1 - y0, 2)
    return None


def _same_size(a: tuple[float, float], b: tuple[float, float], tol: float) -> bool:
    return (abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol) or (abs(a[0] - b[1]) <= tol and abs(a[1] - b[0]) <= tol)


def _wanted_roof(text: str, keyword: str) -> str:
    """'flat', 'hip', 'shed', 'gable', or 'pitched' (any slope will do) from how the request words the roof."""
    t = f"{keyword} {text}".lower()
    if "flat" in t:
        return "flat"
    if "hip" in t:
        return "hip"
    if "shed" in t or "mono" in t or "lean-to" in t:
        return "shed"
    if "gable" in t:
        return "gable"
    return "pitched"


def _check_roof(design: Design, r: dict[str, Any]) -> tuple[str, str]:
    want = _wanted_roof(r.get("text", ""), str(r.get("params", {}).get("keyword", "")))
    have = design.roof
    ok = (have != "flat") if want == "pitched" else (have == want)
    if ok:
        return "met", f"{have} roof" + (f", {design.roof_pitch:g} degrees" if have != "flat" else "")
    return "unmet", (f"wanted a {want} roof, the design has a {have} roof; send a roof step with kind "
                     f"{'gable, hip or shed' if want == 'pitched' else want} (and pitch in degrees, 5 to 60, default 30)")


def _check_dimension(design: Design, p: dict[str, Any]) -> tuple[str, str]:
    want = (float(p["width"]), float(p["depth"]))
    asked = f"asked {want[0]:.1f} x {want[1]:.1f} m"
    if p["keyword"] == "building":
        got = _footprint(design)
        if got is None:
            return "unmet", f"{asked}; the design has no rooms yet"
        if _same_size(got, want, FOOTPRINT_TOLERANCE_M):
            return "met", f"{asked}, built {got[0]:.1f} x {got[1]:.1f} m"
        return "unmet", (f"{asked} for the outline of the ground floor, built {got[0]:.1f} x {got[1]:.1f} m; "
                         f"resize and rearrange the rooms so their outer edges measure {want[0]:.1f} x {want[1]:.1f} m")
    rooms = _matching_rooms(design, str(p["keyword"]), None)
    if not rooms:
        return "unmet", f"{asked}, but there is no '{p['keyword']}' room to measure; add one with exactly that size"
    for r in rooms:
        if _same_size((r.rect[2], r.rect[3]), want, SIZE_TOLERANCE_M):
            return "met", f"{asked}, built {r.rect[2]:.1f} x {r.rect[3]:.1f} m ({r.name})"
    r = rooms[0]
    return "unmet", (f"{asked}, but '{r.name}' (id {r.id}) is {r.rect[2]:.1f} x {r.rect[3]:.1f} m; "
                     f"send a room step with that name and rect [{r.rect[0]:g}, {r.rect[1]:g}, {want[0]:g}, {want[1]:g}], and move its neighbours if they now overlap")


def _check_area(design: Design, p: dict[str, Any]) -> tuple[str, str]:
    want = float(p["area"])
    asked = f"asked about {want:.0f} m2"
    if p["keyword"] == "building":
        got = sum(_rect_area(r) for r in design.rooms)
        if abs(got - want) <= max(want * AREA_TOLERANCE, 1.0):
            return "met", f"{asked} in total, built {got:.1f} m2"
        return "unmet", (f"{asked} in total, the design has {got:.1f} m2; "
                         f"size the rooms so that all floors together add up to about {want:.0f} m2 (within 10%)")
    rooms = _matching_rooms(design, str(p["keyword"]), None)
    if not rooms:
        return "unmet", f"{asked}, but there is no '{p['keyword']}' room to measure"
    for r in rooms:
        if abs(_rect_area(r) - want) <= max(want * AREA_TOLERANCE, 1.0):
            return "met", f"{asked}, built {_rect_area(r):.1f} m2 ({r.name})"
    r = rooms[0]
    return "unmet", f"{asked}, but '{r.name}' (id {r.id}) is {_rect_area(r):.1f} m2; resize it to about {want:.0f} m2 within 10%"


def check(design: Design, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for req in requirements:
        r = dict(req)
        p = r.get("params", {})
        if not r.get("supported", True):
            r["status"], r["detail"] = "unsupported", "this tool cannot build it yet; noted in the version summary"
        elif r["kind"] == "feature" and str(p.get("keyword", "")).lower() in ROOF_WORDS:
            r["status"], r["detail"] = _check_roof(design, r)
        elif r["kind"] == "dimension" and {"keyword", "width", "depth"} <= p.keys():
            r["status"], r["detail"] = _check_dimension(design, p)
        elif r["kind"] == "area" and {"keyword", "area"} <= p.keys():
            r["status"], r["detail"] = _check_area(design, p)
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
