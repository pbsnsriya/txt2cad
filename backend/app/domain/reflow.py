"""Laying a storey out again in a given outline, in code: an L, a U, a ring of rooms around an open courtyard, or two rows so that every room has an outside wall.

The model is good at choosing rooms and poor at placing rectangles so that their outline is an L. Rooms keep their ids, names, kinds, finishes and (roughly) their areas;
only where they stand changes. Doors and windows are put back where they still fit. Nothing here runs on a building the person is editing.
"""

from __future__ import annotations

from .design import Design, Room

DEPTH = 4.0                       # depth of a row or width of an arm
MIN_SIDE = 2.0
NOTCH = 2.5                       # the least width of the gap in an L or U, and of a courtyard
SHAPES = ("L", "U", "courtyard", "rows")
_PRIVACY = {"living": 0, "dining": 0, "kitchen": 1, "hall": 1, "office": 2, "retail": 2, "utility": 3, "storage": 3, "garage": 3, "other": 3, "bathroom": 4, "bedroom": 5}


class CannotReflow(ValueError):
    pass


def _area(r: Room) -> float:
    return r.rect[2] * r.rect[3]


def _along(r: Room, depth: float) -> float:
    return max(MIN_SIDE, round(_area(r) / depth, 1))


def _row(items: list[Room], x: float, y: float, depth: float, length: float | None = None) -> dict[str, tuple[float, float, float, float]]:
    """Rooms side by side along x; the last is stretched so the row is `length` long."""
    out: dict[str, tuple[float, float, float, float]] = {}
    widths = [_along(r, depth) for r in items]
    if length is not None and widths:
        widths[-1] = round(max(widths[-1], length - sum(widths[:-1])), 1)
    for r, w in zip(items, widths):
        out[r.id] = (round(x, 1), round(y, 1), w, depth)
        x += w
    return out


def _col(items: list[Room], x: float, y: float, width: float, length: float | None = None) -> dict[str, tuple[float, float, float, float]]:
    """Rooms one above the other along y."""
    out: dict[str, tuple[float, float, float, float]] = {}
    lengths = [_along(r, width) for r in items]
    if length is not None and lengths:
        lengths[-1] = round(max(lengths[-1], length - sum(lengths[:-1])), 1)
    for r, n in zip(items, lengths):
        out[r.id] = (round(x, 1), round(y, 1), width, n)
        y += n
    return out


def _length(items: list[Room], depth: float) -> float:
    return sum(_along(r, depth) for r in items)


def _order(rooms: list[Room]) -> list[Room]:
    return sorted(rooms, key=lambda r: _PRIVACY.get(r.kind, 3))              # stable: public rooms first, bedrooms last


def _balanced(items: list[Room], into: int, depth: float) -> list[list[Room]]:
    """Deal rooms to `into` groups, always to the shortest, keeping their order within a group."""
    groups: list[list[Room]] = [[] for _ in range(into)]
    for r in items:
        min(groups, key=lambda g: _length(g, depth)).append(r)
    return groups


def _layout_l(rooms: list[Room]) -> dict[str, tuple[float, float, float, float]]:
    if len(rooms) < 3:
        raise CannotReflow("an L needs at least three rooms")
    items = _order(rooms)
    cut = max(1, round(len(items) * 0.5))
    row, arm = items[:cut], items[cut:]
    while arm and _length(row, DEPTH) - DEPTH < NOTCH:
        row.append(arm.pop(0))
    if not arm:
        raise CannotReflow("not enough room for the arm of an L")
    out = _row(row, 0, 0, DEPTH)
    out.update(_col(arm, 0, DEPTH, DEPTH))
    return out


def _layout_u(rooms: list[Room], court: bool = False) -> dict[str, tuple[float, float, float, float]]:
    if len(rooms) < 4:
        raise CannotReflow("a U needs at least four rooms")
    items = _order(rooms)
    cut = max(1, len(items) // 3)
    row, arms = items[:cut], items[cut:]
    left, right = _balanced(arms, 2, DEPTH)
    if not left or not right:
        raise CannotReflow("a U needs a room in each arm")
    total = max(_length(row, DEPTH), 2 * DEPTH + NOTCH)
    arm = max(_length(left, DEPTH), _length(right, DEPTH))
    out = _row(row, 0, 0, DEPTH, total)
    out.update(_col(left, 0, DEPTH, DEPTH, arm if court else None))
    out.update(_col(right, total - DEPTH, DEPTH, DEPTH, arm if court else None))
    if court:
        out["__court__"] = (DEPTH, DEPTH, round(total - 2 * DEPTH, 1), round(arm, 1))          # the gap of the U is the courtyard, with rooms on three sides
    return out


def _layout_rows(rooms: list[Room], fixed: dict[str, tuple[float, float]] | None = None) -> dict[str, tuple[float, float, float, float]]:
    """Two rows. A room with a size the request stated keeps it: it is placed as it is and its row is as deep as the deepest of them."""
    if len(rooms) < 2:
        raise CannotReflow("two rows need at least two rooms")
    fixed = fixed or {}
    free = [r for r in rooms if r.id not in fixed]
    south, north = _balanced(_order(free), 2, DEPTH)
    for r in rooms:
        if r.id in fixed:
            min((south, north), key=lambda g: _length(g, DEPTH) + sum(fixed[x.id][0] for x in g if x.id in fixed)).append(r)

    def lay(row: list[Room], y: float, depth: float, length: float | None) -> dict[str, tuple[float, float, float, float]]:
        out, x = {}, 0.0
        widths = {r.id: (fixed[r.id][0] if r.id in fixed else _along(r, depth)) for r in row}
        if length is not None and row:
            last = row[-1]
            widths[last.id] = round(max(widths[last.id], length - sum(w for i, w in widths.items() if i != last.id)), 1)
        for r in row:
            out[r.id] = (round(x, 1), round(y, 1), widths[r.id], fixed[r.id][1] if r.id in fixed else depth)
            x += widths[r.id]
        return out

    ds = max([DEPTH, *[fixed[r.id][1] for r in south if r.id in fixed]])
    dn = max([DEPTH, *[fixed[r.id][1] for r in north if r.id in fixed]])
    total = max(sum(fixed[r.id][0] if r.id in fixed else _along(r, ds) for r in south), sum(fixed[r.id][0] if r.id in fixed else _along(r, dn) for r in north))
    out = lay(south, 0, ds, total)
    out.update(lay(north, ds, dn, total))
    return out


def _layout_courtyard(rooms: list[Room], court: tuple[float, float, float, float] | None = None) -> dict[str, tuple[float, float, float, float]]:
    if len(rooms) < 4:
        raise CannotReflow("a ring around a courtyard needs at least four rooms")
    items = _order(rooms)
    south, north, west, east = [items[0]], [items[-1]], [items[1]], [items[-2]]
    for r in items[2:-2]:
        side = min((south, north, west, east), key=lambda g: _length(g, DEPTH))
        side.append(r)
    width = max(_length(south, DEPTH), _length(north, DEPTH), 2 * DEPTH + NOTCH)
    height = max(_length(west, DEPTH), _length(east, DEPTH), NOTCH)
    out = _row(south, 0, 0, DEPTH, width)
    out.update(_row(north, 0, DEPTH + height, DEPTH, width))
    out.update(_col(west, 0, DEPTH, DEPTH, height))
    out.update(_col(east, width - DEPTH, DEPTH, DEPTH, height))
    out["__court__"] = (DEPTH, DEPTH, round(width - 2 * DEPTH, 1), round(height, 1))
    return out


def _is_court(r: Room) -> bool:
    return bool({"courtyard", "patio", "atrium"} & set(r.name.lower().replace("-", " ").split()))


def reflow(design: Design, level: str, shape: str, court_in_notch: bool = False, fixed: dict[str, tuple[float, float]] | None = None) -> Design:
    """The design with the rooms of `level` laid out as `shape`. Raises CannotReflow when the rooms cannot make it; the caller checks that the result builds."""
    if shape not in SHAPES:
        raise CannotReflow(f"unknown shape {shape}")
    d = design.model_copy(deep=True)
    here = [r for r in d.rooms if r.level == level]
    notch = court_in_notch and shape == "U"
    court = next((r for r in here if _is_court(r)), None) if (shape == "courtyard" or notch) else None
    others = [r for r in here if r is not court]
    if shape == "L":
        spots = _layout_l(others)
    elif shape == "U":
        spots = _layout_u(others, notch)
    elif shape == "rows":
        spots = _layout_rows(others, fixed)
    else:
        spots = _layout_courtyard(others)
    for r in here:
        if r.id in spots:
            r.rect = spots[r.id]
    if shape == "courtyard" or notch:
        rect = spots["__court__"]
        if court is not None:
            court.rect, court.roofed = rect, False
        else:
            ids = {r.id for r in d.rooms}
            cid = "courtyard" if "courtyard" not in ids else "courtyard-2"
            d.rooms.append(Room(id=cid, name="Courtyard", level=level, kind="other", rect=rect, roofed=False))
    gone = {r.id for r in here}
    d.stairs = [s for s in d.stairs if s.room not in gone]
    d.furniture = [f for f in d.furniture if f.room not in gone]
    d.doors = [x for x in d.doors if x.room not in gone and x.to not in gone]
    d.windows = [w for w in d.windows if w.room not in gone]
    return d
