"""Deterministic check of a design against the checklist extracted from the prompt."""

from __future__ import annotations

import re
from typing import Any

from shapely.geometry import box
from shapely.ops import unary_union

from .design import Design

UNSUPPORTED_FEATURES = {"porch", "balcony", "basement", "pool", "garden", "terrace", "veranda", "cellar"}
ALWAYS_BUILDABLE = {"storeys", "room", "window", "door"}
WHOLE_BUILDING_WORDS = {"studio", "flat", "apartment", "house", "home", "bungalow", "cabin", "villa", "cottage", "townhouse", "building"}
FURNITURE_WORDS = {"furniture", "furnished", "furnishing", "interior", "interiors", "furnish"}
HABITABLE = {"living", "bedroom", "kitchen", "dining", "bathroom", "office"}
SHAPE_WORDS = {"courtyard", "patio", "atrium", "l-shaped", "l shaped", "l-shape", "l shape", "u-shaped", "u shaped", "u-shape", "u shape"}
ROOF_WORDS = {"roof", "pitched", "pitched roof", "gable", "gabled", "hip", "hipped", "shed", "mono-pitch", "monopitch", "sloped", "flat roof"}


def normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """A checklist item as the app stores it (kind, text, supported, params)."""
    params = {k: raw[k] for k in ("keyword", "count", "level", "side", "width", "depth", "area") if raw.get(k) is not None}
    keyword = str(params.get("keyword", "")).lower()
    kind = raw.get("kind", "other")
    if kind in ("room", "feature") and keyword in WHOLE_BUILDING_WORDS:
        kind = "other"                 # "a studio flat" names the building, not a room to look for
    # Small models mark everything "unsupported". For kinds this tool really builds, ignore the model's flag; keep it for the rest.
    supported = True if kind in ALWAYS_BUILDABLE else raw.get("supported", True) is not False
    if kind == "feature" and keyword in UNSUPPORTED_FEATURES:
        supported = False
    if kind == "feature" and (keyword in ROOF_WORDS or keyword in SHAPE_WORDS or keyword in FURNITURE_WORDS):
        supported = True
    return {"kind": kind, "text": raw.get("text", ""), "supported": supported, "params": params}


_ALIASES = {"hallway": "hall", "corridor": "hall", "entrance": "hall", "lounge": "living", "study": "office", "workspace": "office", "wc": "bathroom",
            "toilet": "bathroom", "ensuite": "bathroom", "kitchenette": "kitchen", "patio": "courtyard", "shop": "retail", "sale": "retail", "sales": "retail", "showroom": "retail"}
_GENERIC = {"room", "area", "space", "the", "a", "an"}


def _words(text: str) -> set[str]:
    """Whole words of a name or keyword, lower case, singular, with common alternatives folded together (hallway -> hall)."""
    out = set()
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        t = t[:-1] if t.endswith("s") and len(t) > 3 else t
        out.add(_ALIASES.get(t, t))
    return out


def _matching_rooms(design: Design, keyword: str, level: str | None):
    """Rooms whose kind or name contains every meaningful word of the keyword: 'bedrooms' finds 'Master Bedroom', 'bed' finds nothing."""
    wanted = _words(keyword) - _GENERIC or _words(keyword)
    out = []
    for r in design.rooms:
        if level is not None and r.level != level:
            continue
        have = _words(r.name) | _words(r.kind)
        if wanted and wanted <= have:
            out.append(r)
    return out


def _footprint_polygon(design: Design):
    for lv in design.levels:
        rooms = [r for r in design.rooms if r.level == lv.id]
        if rooms:
            return unary_union([box(r.rect[0], r.rect[1], r.rect[0] + r.rect[2], r.rect[1] + r.rect[3]) for r in rooms])
    return None


def _outline_shape(design: Design) -> str:
    """'rectangle', 'L', 'U' or 'other' for the outline of the lowest storey."""
    poly = _footprint_polygon(design)
    if poly is None:
        return "other"
    poly = poly.simplify(1e-6)                       # drop the extra points where two rooms meet along a straight edge
    if poly.geom_type != "Polygon":
        return "other"
    corners = len(poly.exterior.coords) - 1
    notches = [g for g in (poly.convex_hull.difference(poly).geoms if poly.convex_hull.difference(poly).geom_type == "MultiPolygon" else [poly.convex_hull.difference(poly)]) if g.area > 0.5]
    if corners == 4:
        return "rectangle"
    if corners == 6 and len(notches) == 1:
        return "L"
    if corners == 8 and len(notches) == 1:
        return "U"
    return "other"


def _check_shape(design: Design, keyword: str, text: str) -> tuple[str, str]:
    kw = f"{keyword} {text}".lower().replace("-", " ")
    if "courtyard" in kw or "patio" in kw or "atrium" in kw:
        found = [r for r in design.rooms if {"courtyard", "patio", "atrium"} & _words(r.name)]
        if not found:
            return "unmet", "there is no courtyard room; add one inside the plan with roofed set to false so it is open to the sky"
        for r in found:
            if r.roofed:
                continue
            sides = _sides_with_rooms(design, r)
            if sides >= 3:
                return "met", f"'{r.name}' is open to the sky and has rooms on {sides} sides"
        r = found[0]
        if r.roofed:
            return "unmet", f"'{r.name}' has a roof; send a room step for it with roofed set to false so it is open to the sky"
        return "unmet", f"'{r.name}' is not surrounded: it has rooms on {_sides_with_rooms(design, r)} of its sides and needs at least 3; place the other rooms around it"
    shape = _outline_shape(design)
    want = "L" if re.search(r"\bl shape", kw) else "U"
    if shape == want:
        return "met", f"the ground floor outline is {want}-shaped"
    names = {"rectangle": "a plain rectangle", "L": "L-shaped", "U": "U-shaped", "other": "neither an L nor a U"}
    return "unmet", (f"the ground floor outline is {names[shape]}; arrange the ground floor rooms so they form an {want} "
                     f"(rooms are rectangles: build it from rectangles that touch, and leave the notch empty)")


def _sides_with_rooms(design: Design, room) -> int:
    x0, y0, x1, y1 = room.rect[0], room.rect[1], room.rect[0] + room.rect[2], room.rect[1] + room.rect[3]
    touched = set()
    for o in design.rooms:
        if o.id == room.id or o.level != room.level:
            continue
        ox0, oy0, ox1, oy1 = o.rect[0], o.rect[1], o.rect[0] + o.rect[2], o.rect[1] + o.rect[3]
        overlap_y, overlap_x = min(y1, oy1) - max(y0, oy0) > 1e-6, min(x1, ox1) - max(x0, ox0) > 1e-6
        if abs(ox1 - x0) < 1e-6 and overlap_y:
            touched.add("W")
        if abs(ox0 - x1) < 1e-6 and overlap_y:
            touched.add("E")
        if abs(oy1 - y0) < 1e-6 and overlap_x:
            touched.add("S")
        if abs(oy0 - y1) < 1e-6 and overlap_x:
            touched.add("N")
    return len(touched)


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


def _check_furniture(design: Design) -> tuple[str, str]:
    rooms = [r for r in design.rooms if r.kind in HABITABLE]
    furnished = [r for r in rooms if any(f.room == r.id for f in design.furniture)]
    if rooms and len(furnished) * 2 >= len(rooms):
        return "met", f"{len(design.furniture)} pieces in {len(furnished)} of {len(rooms)} rooms"
    return "unmet", (f"only {len(furnished)} of {len(rooms)} living, sleeping, cooking, dining, washing and working rooms have furniture; "
                     "send one furnish step with room \"all\"")


def _check_wanted_furniture(design: Design, p: dict[str, Any]) -> tuple[str, str]:
    want, kw = int(p.get("count", 1)), str(p["keyword"])
    kinds = {"bed_double", "bed_single"} if kw == "bed" else {kw}
    have = sum(1 for f in design.furniture if f.kind in kinds)
    if have >= want:
        return "met", f"{have} placed"
    return "unmet", (f"wanted {want}, the design has {have}; add {'one' if want - have == 1 else str(want - have)} with a furniture step (kind "
                     f"{'bed_double or bed_single' if kw == 'bed' else kw}) in a fitting room, or send a furnish step for \"all\" first")


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
        elif r["kind"] == "feature" and str(p.get("keyword", "")).lower() in FURNITURE_WORDS:
            r["status"], r["detail"] = _check_furniture(design)
        elif r["kind"] == "feature" and str(p.get("keyword", "")).lower() in SHAPE_WORDS:
            r["status"], r["detail"] = _check_shape(design, str(p["keyword"]), r.get("text", ""))
        elif r["kind"] == "feature" and str(p.get("keyword", "")).lower() in ROOF_WORDS:
            r["status"], r["detail"] = _check_roof(design, r)
        elif r["kind"] == "furniture" and "keyword" in p:
            r["status"], r["detail"] = _check_wanted_furniture(design, p)
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
