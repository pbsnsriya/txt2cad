"""Changing sizes in code while the plan stays a plan: stretching it along a line, scaling it, and finding a free place for a room that is missing.

Rooms are rectangles that touch. Stretching along a line moves everything beyond the line and widens whatever the line crosses, so touching rooms still touch and nothing overlaps.
"""

from __future__ import annotations

from shapely.geometry import box
from shapely.ops import unary_union

from .design import Design, Room

EPS = 1e-6
MIN_SIDE = 1.5

# the size a room of a missing kind is given: width x depth in metres
DEFAULT_SIZES: dict[str, tuple[float, float]] = {
    "bedroom": (3.5, 3.5), "bathroom": (2.5, 3.0), "kitchen": (3.5, 3.0), "living": (4.5, 4.0), "dining": (3.5, 3.0), "office": (3.0, 3.0),
    "hall": (2.0, 3.0), "utility": (2.0, 2.5), "storage": (2.0, 2.0), "garage": (3.0, 6.0),
}
LABELS = {"bedroom": "Bedroom", "bathroom": "Bathroom", "kitchen": "Kitchen", "living": "Living room", "dining": "Dining room", "office": "Office",
          "hall": "Hall", "utility": "Utility", "storage": "Storage", "garage": "Garage"}


def _edge(x: float, y: float, w: float, h: float, axis: str) -> tuple[float, float]:
    return (x, x + w) if axis == "x" else (y, y + h)


def stretch(design: Design, axis: str, cut: float, delta: float) -> Design | None:
    """Everything beyond `cut` (on every storey) moves by `delta` along the axis; rooms the line crosses grow by it. None when a room would get too narrow."""
    d = design.model_copy(deep=True)
    for r in d.rooms:
        x, y, w, h = r.rect
        lo, hi = _edge(x, y, w, h, axis)
        if lo >= cut - EPS:
            lo, hi = lo + delta, hi + delta
        elif hi > cut + EPS:
            hi += delta
        else:
            continue
        if hi - lo < MIN_SIDE:
            return None
        r.rect = (round(lo, 2), y, round(hi - lo, 2), h) if axis == "x" else (x, round(lo, 2), w, round(hi - lo, 2))
    return d


def scale(design: Design, sx: float, sy: float) -> Design | None:
    """Every coordinate multiplied; a shared edge stays shared because both rooms round the same number the same way."""
    d = design.model_copy(deep=True)
    for r in d.rooms:
        x, y, w, h = r.rect
        x0, x1, y0, y1 = round(x * sx, 1), round((x + w) * sx, 1), round(y * sy, 1), round((y + h) * sy, 1)
        if x1 - x0 < MIN_SIDE or y1 - y0 < MIN_SIDE:
            return None
        r.rect = (x0, y0, round(x1 - x0, 1), round(y1 - y0, 1))
    return d


def _box(r: Room):
    return box(r.rect[0], r.rect[1], r.rect[0] + r.rect[2], r.rect[1] + r.rect[3])


def free_spot(design: Design, level: str, size: tuple[float, float]) -> tuple[float, float, float, float] | None:
    """A rectangle of about `size` on `level` that touches rooms already there and overlaps none; on an upper storey, one over the floor below is preferred."""
    spots = free_spots(design, level, size)
    return spots[0] if spots else None


def free_spots(design: Design, level: str, size: tuple[float, float], skip: str | None = None) -> list[tuple[float, float, float, float]]:
    """All such rectangles, best first (`skip` is a room to leave out of the plan, for finding it a new place)."""
    here = [r for r in design.rooms if r.level == level and r.id != skip]
    if not here:
        return []
    others = unary_union([_box(r) for r in here])
    idx = [lv.id for lv in design.levels].index(level) if any(lv.id == level for lv in design.levels) else 0
    below = unary_union([_box(r) for r in design.rooms if idx > 0 and r.level == design.levels[idx - 1].id]) if idx > 0 else None
    found: dict[tuple[float, float, float, float], float] = {}
    for w, h in (size, size[::-1]):
        for r in here:
            x0, y0, x1, y1 = r.rect[0], r.rect[1], r.rect[0] + r.rect[2], r.rect[1] + r.rect[3]
            cands = [(x, y0 + off) for x in (x0 - w, x1) for off in [k * 0.5 - h + 0.5 for k in range(int((y1 - y0 + h) / 0.5))]]
            cands += [(x0 + off, y) for y in (y0 - h, y1) for off in [k * 0.5 - w + 0.5 for k in range(int((x1 - x0 + w) / 0.5))]]
            for x, y in cands:
                c = box(x, y, x + w, y + h)
                if c.intersection(others).area > EPS:
                    continue
                shared = c.buffer(0.01).intersection(others).area / 0.02          # about the length of wall shared with other rooms
                score = min(shared, 8.0)
                if below is not None and c.difference(below).area < EPS:
                    score += 6.0                                                    # stands on the floor below
                elif below is not None:
                    score -= 3.0 * c.difference(below).area / (w * h)
                found[(round(x, 2), round(y, 2), w, h)] = max(score, found.get((round(x, 2), round(y, 2), w, h), float("-inf")))
    return sorted(found, key=lambda k: -found[k])
