"""Where furniture goes: placing one piece against a wall or in the middle of a room, checking it fits, and laying out a whole room.

Plan coordinates are metres. A piece is a rectangle w across by d deep, centred on (x, y), turned counter-clockwise by `rot` degrees (0, 90, 180, 270).
At rot 0 its back is to the south and it faces north; a piece against the north wall is turned 180, against the east wall 90, against the west wall 270.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from shapely import affinity
from shapely.geometry import Polygon, box

from .catalogue import CATALOGUE, Item


def is_ceiling(kind: str) -> bool:
    item = CATALOGUE.get(kind)
    return item is not None and item.mount == "ceiling"
from .design import Furniture, Room
from .geom import box_on_wall, wall_outline
from .spec import BuildingSpec

WALL_INSET = 0.17           # from a room's edge line to the inside face of a thick wall, with a hair of clearance
EPS = 1e-6
DOOR_KEEP_OUT_M = 0.9       # room to swing a door, each side of the wall
BACK_ROT = {"S": 0, "E": 90, "N": 180, "W": 270}
SIDES = ("N", "S", "E", "W")
FRONT = {0: (0.0, 1.0), 90: (-1.0, 0.0), 180: (0.0, -1.0), 270: (1.0, 0.0)}


class DoesNotFit(ValueError):
    pass


def inner(room: Room) -> tuple[float, float, float, float]:
    x, y, w, d = room.rect
    return x + WALL_INSET, y + WALL_INSET, x + w - WALL_INSET, y + d - WALL_INSET


def footprint(cx: float, cy: float, w: float, d: float, rot: int) -> Polygon:
    return affinity.translate(affinity.rotate(box(-w / 2, -d / 2, w / 2, d / 2), rot, origin=(0, 0)), cx, cy)


def furniture_polygon(f: Furniture) -> Polygon:
    return footprint(f.x, f.y, f.w, f.d, f.rot)


CORNERS = {"NE": ("N", 1.0), "NW": ("N", 0.0), "SE": ("S", 1.0), "SW": ("S", 0.0), "EN": ("E", 1.0), "ES": ("E", 0.0), "WN": ("W", 1.0), "WS": ("W", 0.0)}


def corner(side: str) -> tuple[str, float] | None:
    """'NE' means in the north-east corner: its back to the north wall and pushed up against the east wall."""
    return CORNERS.get(side.strip().upper()[:2]) if len(side.strip()) == 2 else None


def against(room: Room, w: float, d: float, side: str, at: float, gap: float = 0.0) -> tuple[float, float, int]:
    """Centre and rotation of a w x d piece with its back to `side`, `at` (0 to 1) of the way along that wall, `gap` metres out from the wall."""
    x0, y0, x1, y1 = inner(room)
    at = min(max(at, 0.0), 1.0)
    if side in ("S", "N"):
        lo, hi = x0 + w / 2, x1 - w / 2
        if hi < lo - EPS:
            raise DoesNotFit(f"a piece {w:g} m wide does not fit along the {side} wall of '{room.name}' (inside it is {x1 - x0:.2f} m)")
        cx = lo + at * (hi - lo)
        cy = y0 + d / 2 + gap if side == "S" else y1 - d / 2 - gap
    else:
        lo, hi = y0 + w / 2, y1 - w / 2
        if hi < lo - EPS:
            raise DoesNotFit(f"a piece {w:g} m wide does not fit along the {side} wall of '{room.name}' (inside it is {y1 - y0:.2f} m)")
        cy = lo + at * (hi - lo)
        cx = x0 + d / 2 + gap if side == "W" else x1 - d / 2 - gap
    return round(cx, 3), round(cy, 3), BACK_ROT[side]


def centred(room: Room, at: float = 0.5, across: float = 0.5) -> tuple[float, float]:
    x0, y0, x1, y1 = inner(room)
    return round(x0 + min(max(at, 0.0), 1.0) * (x1 - x0), 3), round(y0 + min(max(across, 0.0), 1.0) * (y1 - y0), 3)


def check_fit(room: Room, poly: Polygon, label: str, others: list[tuple[str, Polygon]]) -> None:
    """Raise DoesNotFit with a message for the model when the piece sticks out of the room or overlaps another piece."""
    x0, y0, x1, y1 = inner(room)
    minx, miny, maxx, maxy = poly.bounds
    if minx < x0 - EPS or miny < y0 - EPS or maxx > x1 + EPS or maxy > y1 + EPS:
        raise DoesNotFit(f"{label} does not fit inside '{room.name}': it would cover x {minx:.2f}..{maxx:.2f}, y {miny:.2f}..{maxy:.2f} and the room's inside is "
                         f"x {x0:.2f}..{x1:.2f}, y {y0:.2f}..{y1:.2f}; use a smaller size, another wall or turn it")
    for name, other in others:
        if poly.intersection(other).area > 1e-4:
            raise DoesNotFit(f"{label} overlaps {name} in '{room.name}'; use another wall or position")


# --- laying out a whole room --------------------------------------------------------------------------------------------------
@dataclass
class Ctx:
    room: Room
    taken: list[tuple[str, Polygon]]            # furniture already in the room
    keep_out: list[Polygon]                     # door swings and stairs
    placed: list[Furniture]
    next_id: Callable[[str], str]               # kind -> unique id
    hanging: list[tuple[str, Polygon]] = None   # type: ignore[assignment]   # ceiling pieces already in the room

    def __post_init__(self) -> None:
        self.hanging = self.hanging or []

    def sides_by_length(self) -> list[str]:
        x0, y0, x1, y1 = inner(self.room)
        wide = (x1 - x0) >= (y1 - y0)
        return ["N", "S", "E", "W"] if wide else ["E", "W", "N", "S"]

    def free(self, poly: Polygon, front: Polygon | None = None) -> bool:
        x0, y0, x1, y1 = inner(self.room)
        minx, miny, maxx, maxy = poly.bounds
        if minx < x0 - EPS or miny < y0 - EPS or maxx > x1 + EPS or maxy > y1 + EPS:
            return False
        zone = poly if front is None else poly.union(front)
        if any(zone.intersection(k).area > 1e-4 for k in self.keep_out):
            return False
        if any(poly.intersection(p).area > 1e-4 for _, p in self.taken):
            return False
        if front is not None and any(front.intersection(p).area > 0.02 for _, p in self.taken):
            return False
        return True

    def add(self, kind: str, cx: float, cy: float, rot: int, w: float, d: float, h: float) -> Furniture:
        f = Furniture(id=self.next_id(kind), room=self.room.id, kind=kind, x=cx, y=cy, w=w, d=d, h=h, rot=rot)  # type: ignore[arg-type]
        self.placed.append(f)
        (self.hanging if is_ceiling(kind) else self.taken).append((f.id, furniture_polygon(f)))
        return f

    def lights(self) -> None:
        """Ceiling lights on an even grid, about one for every 14 m2: they hang over everything and only keep clear of each other."""
        x0, y0, x1, y1 = inner(self.room)
        n = min(4, max(1, round(((x1 - x0) * (y1 - y0)) / 14.0)))
        item = CATALOGUE["ceiling_light"]
        along_x = (x1 - x0) >= (y1 - y0)
        for i in range(n):
            frac = (i + 0.5) / n
            cx, cy = (x0 + frac * (x1 - x0), (y0 + y1) / 2) if along_x else ((x0 + x1) / 2, y0 + frac * (y1 - y0))
            poly = footprint(round(cx, 3), round(cy, 3), item.w, item.d, 0)
            if not any(poly.intersection(p).area > 1e-4 for _, p in self.hanging):
                self.add("ceiling_light", round(cx, 3), round(cy, 3), 0, item.w, item.d, item.h)

    def place(self, kind: str, sides: list[str], ats: tuple[float, ...] = (0.5, 0.15, 0.85, 0.3, 0.7, 0.0, 1.0), w: float | None = None, front_m: float = 0.0,
              skip: set[str] | None = None) -> Furniture | None:
        item = CATALOGUE[kind]
        w, d, h = w or item.w, item.d, item.h
        for side in sides:
            if skip and side in skip:
                continue
            for at in ats:
                try:
                    cx, cy, rot = against(self.room, w, d, side, at)
                except DoesNotFit:
                    break
                poly = footprint(cx, cy, w, d, rot)
                front = _front_zone(cx, cy, w, d, rot, front_m) if front_m else None
                if self.free(poly, front):
                    return self.add(kind, cx, cy, rot, w, d, h)
        return None

    def place_centre(self, kind: str, rot: int = 0, at: float = 0.5, across: float = 0.5, w: float | None = None) -> Furniture | None:
        item = CATALOGUE[kind]
        w, d, h = w or item.w, item.d, item.h
        cx, cy = centred(self.room, at, across)
        if self.free(footprint(cx, cy, w, d, rot)):
            return self.add(kind, cx, cy, rot, w, d, h)
        return None

    def place_in_front_of(self, base: Furniture, kind: str, gap: float, turn: int = 0) -> Furniture | None:
        """A piece in front of another: a chair at a desk, a table in front of a sofa."""
        item = CATALOGUE[kind]
        fx, fy = FRONT[base.rot]
        dist = base.d / 2 + gap + item.d / 2
        cx, cy = round(base.x + fx * dist, 3), round(base.y + fy * dist, 3)
        rot = (base.rot + turn) % 360
        if self.free(footprint(cx, cy, item.w, item.d, rot)):
            return self.add(kind, cx, cy, rot, item.w, item.d, item.h)
        return None


def keep_outs(spec: BuildingSpec) -> dict[str, list[Polygon]]:
    """By level: the strips in front of doors (they swing) and the stairs and stairwells. Furniture stays out of these."""
    out: dict[str, list[Polygon]] = {}
    for o in spec.openings:
        if o.kind != "door":
            continue
        w = spec.wall(o.host)
        _, u, n = wall_outline(w.start, w.end, w.thickness)
        c = (w.start[0] + u[0] * o.offset, w.start[1] + u[1] * o.offset)
        reach = 0.25 if o.style == "opening" else DOOR_KEEP_OUT_M
        out.setdefault(o.level, []).append(Polygon(box_on_wall(c, u, n, o.width, 2 * reach + w.thickness)))
    for st in spec.stairs:
        poly = Polygon(st.outline).buffer(0.05)
        out.setdefault(st.level, []).append(poly)
        out.setdefault(st.to_level, []).append(poly)
    return out


def _front_zone(cx: float, cy: float, w: float, d: float, rot: int, depth: float) -> Polygon:
    fx, fy = FRONT[rot]
    reach = d / 2 + depth / 2
    return footprint(cx + fx * reach, cy + fy * reach, w, depth, rot)


def _run(ctx: Ctx, kinds: list[tuple[str, float | None]], sides: list[str]) -> None:
    """Units in a row along one wall, from one end, skipping what is blocked (kitchen units)."""
    x0, y0, x1, y1 = inner(ctx.room)
    for side in sides:
        length = (x1 - x0) if side in ("N", "S") else (y1 - y0)
        pos, placed_here = 0.0, 0
        for kind, width in kinds:
            item = CATALOGUE[kind]
            w = width or item.w
            while pos + w <= length + EPS:
                at = (pos) / (length - w) if length - w > EPS else 0.0
                try:
                    cx, cy, rot = against(ctx.room, w, item.d, side, at)
                except DoesNotFit:
                    break
                poly = footprint(cx, cy, w, item.d, rot)
                if ctx.free(poly):
                    ctx.add(kind, cx, cy, rot, w, item.d, item.h)
                    pos += w
                    placed_here += 1
                    break
                pos += 0.1
        if placed_here >= max(2, len(kinds) - 1):
            return


def _opposite(side: str) -> str:
    return {"N": "S", "S": "N", "E": "W", "W": "E"}[side]


def layout_room(room: Room, existing: list[Furniture], keep_out: list[Polygon], next_id) -> list[Furniture]:
    """A sensible set of furniture for the room's kind, avoiding what is already there and the keep-out zones. Never raises."""
    x0, y0, x1, y1 = inner(room)
    area = (x1 - x0) * (y1 - y0)
    have = {f.kind for f in existing}
    ctx = Ctx(room, [(f.id, furniture_polygon(f)) for f in existing if not is_ceiling(f.kind)], keep_out, [], next_id,
              [(f.id, furniture_polygon(f)) for f in existing if is_ceiling(f.kind)])
    sides = ctx.sides_by_length()
    kind = room.kind

    def want(k: str) -> bool:
        return k not in have

    if kind == "bedroom":
        bed = "bed_double" if area >= 11 else "bed_single"
        if not ({"bed_double", "bed_single"} & have):
            placed = ctx.place(bed, sides, ats=(0.5, 0.2, 0.8), front_m=0.6)
            if placed is None and bed == "bed_double":
                placed = ctx.place("bed_single", sides, ats=(0.5, 0.2, 0.8), front_m=0.5)
        if want("wardrobe"):
            ctx.place("wardrobe", sides[::-1], front_m=0.6)
        if area >= 15 and want("desk"):
            desk = ctx.place("desk", sides, front_m=0.7)
            if desk:
                ctx.place_in_front_of(desk, "office_chair", 0.05, turn=180)
    elif kind == "living":
        if want("sofa"):
            sofa = ctx.place("sofa", sides, ats=(0.5, 0.25, 0.75), front_m=0.8)
            if sofa:
                back_side = next(s for s, r in BACK_ROT.items() if r == sofa.rot)
                if want("tv_unit"):
                    ctx.place("tv_unit", [_opposite(back_side), *[x for x in sides if x not in (back_side, _opposite(back_side))]], ats=(0.5, 0.3, 0.7, 0.15, 0.85), front_m=0.3)
                if want("coffee_table"):
                    ctx.place_in_front_of(sofa, "coffee_table", 0.35)
        if area >= 18 and want("armchair"):
            ctx.place("armchair", sides, ats=(0.0, 1.0, 0.5), front_m=0.4)
        if area >= 24 and want("bookshelf"):
            ctx.place("bookshelf", sides[::-1], front_m=0.5)
    elif kind == "kitchen":
        if not ({"kitchen_counter", "sink_unit", "cooker"} & have):
            _run(ctx, [("sink_unit", None), ("cooker", None), ("kitchen_counter", 1.2), ("fridge", None)], sides)
        if area >= 18 and want("kitchen_island"):
            ctx.place_centre("kitchen_island")
    elif kind == "dining":
        if want("dining_table"):
            long_x = (x1 - x0) >= (y1 - y0)
            table = ctx.place_centre("dining_table", rot=0 if long_x else 90)
            if table:
                _chairs_around(ctx, table)
    elif kind == "bathroom":
        if want("toilet"):
            ctx.place("toilet", sides, ats=(0.0, 1.0, 0.5), front_m=0.5)
        if want("basin"):
            ctx.place("basin", sides, ats=(0.5, 0.2, 0.8, 0.0, 1.0), front_m=0.4)
        if not ({"bath", "shower"} & have):
            if (x1 - x0 >= 1.9 or y1 - y0 >= 1.9) and area >= 4.5:
                ctx.place("bath", sides, ats=(0.0, 1.0, 0.5))
            if not ({"bath"} & {f.kind for f in ctx.placed}):
                ctx.place("shower", sides, ats=(0.0, 1.0), front_m=0.3)
    elif kind == "office":
        if want("desk"):
            desk = ctx.place("desk", sides, front_m=0.8)
            if desk:
                ctx.place_in_front_of(desk, "office_chair", 0.05, turn=180)
        if want("bookshelf"):
            ctx.place("bookshelf", sides[::-1], front_m=0.5)
    elif kind == "utility":
        if want("washing_machine"):
            ctx.place("washing_machine", sides, front_m=0.6)
    if kind == "living":
        if want("floor_lamp"):
            ctx.place("floor_lamp", sides, ats=(1.0, 0.0), front_m=0.0)
        if want("plant") and area >= 16:
            ctx.place("plant", sides[::-1], ats=(0.0, 1.0))
    if kind in ("bedroom", "living", "kitchen", "dining", "bathroom", "office", "hall", "utility") and want("ceiling_light"):
        ctx.lights()
    return ctx.placed


def _chairs_around(ctx: Ctx, table: Furniture) -> None:
    """Chairs at a table: two along each long side, one at each end, as many as fit."""
    item = CATALOGUE["chair"]
    along = table.w
    spots = [(off, side) for off in (-0.3, 0.3) for side in (1, -1)] + [(0.0, 2), (0.0, -2)]      # (offset along the table, which side)
    for off, which in spots:
        base_rot = table.rot
        # local table frame: x across (width), y back-to-front (depth); build the chair centre in that frame, then rotate
        if abs(which) == 1:
            lx, ly = off * (along / 1.6), which * (table.d / 2 + item.d / 2 + 0.05)
            chair_rot = (base_rot + (180 if which == 1 else 0)) % 360
        else:
            lx, ly = (table.w / 2 + item.d / 2 + 0.05) * (1 if which == 2 else -1), 0.0
            chair_rot = (base_rot + (90 if which == 2 else 270)) % 360
        c, s = math.cos(math.radians(base_rot)), math.sin(math.radians(base_rot))
        cx, cy = round(table.x + lx * c - ly * s, 3), round(table.y + lx * s + ly * c, 3)
        if ctx.free(footprint(cx, cy, item.w, item.d, chair_rot)):
            ctx.add("chair", cx, cy, chair_rot, item.w, item.d, item.h)
