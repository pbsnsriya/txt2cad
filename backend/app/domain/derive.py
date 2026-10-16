"""Design -> BuildingSpec. Deterministic: the model places rectangles on a grid, this code finds the walls.

Rect edges are wall centrelines. Along each room edge, the stretch shared with a neighbouring room is a partition
(owned once, by the room with the smaller id); the rest is an exterior wall. Doors and windows are placed on those
pieces and nudged to the nearest free slot.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

from .catalogue import CATALOGUE, COLOURS, FLOORS, PAINTS, PART_COLOURS, UnknownName, parts, resolve
from .design import Design, Room, Side
from .furnish import DoesNotFit, check_fit, furniture_polygon, keep_outs
from .roofs import effective_pitch, is_rectangle, ridge_axis
from .spec import BoxSpec, BuildingSpec, CoveringSpec, FurnitureSpec, LevelSpec, OpeningSpec, RoofSpec, SlabSpec, SpaceSpec, StairSpec, WallSpec

EPS = 1e-6
EXTERIOR_THICKNESS = 0.30
PARTITION_THICKNESS = 0.12
SLAB_THICKNESS = 0.20
OPENING_END_MARGIN = 0.15      # keep openings this far from a wall end
OPENING_GAP = 0.10             # and this far from each other
ARCHWAY_END_MARGIN = 0.05      # an archway can take almost the whole wall
SPACE_INSET = 0.10
MIN_PIECE_LENGTH = 0.30        # shorter slivers are not walls worth modelling
MIN_ROOF_AREA = 0.5
HEADROOM_ABOVE_DOOR = 0.30
GARAGE_DOOR_WIDTH = 2.4
SIDE_PREFERENCE: tuple[Side, ...] = ("S", "E", "W", "N")
SIDE_NAMES = {"N": "north", "S": "south", "E": "east", "W": "west"}
MAX_RISER_M = 0.19             # IRC allows 7 3/4 in (0.197 m); stay just under
GOING_M = 0.26                 # IRC minimum tread is 10 in (0.254 m)
STAIR_WALL_CLEARANCE = 0.15    # a flight sits against the wall's inner face
STAIR_WELL_MARGIN = 0.05


class DesignError(ValueError):
    """The design cannot be built as written. The message is addressed to the model.

    `opening_id` is set when one door or window is the culprit, so a structural edit can drop it instead of failing."""

    def __init__(self, message: str, opening_id: str | None = None) -> None:
        super().__init__(message)
        self.opening_id = opening_id


@dataclass(frozen=True)
class Piece:
    """A straight stretch of wall between two rooms (other set) or between a room and the outside (other None)."""
    id: str
    level: str
    room: str
    other: str | None
    side: Side
    start: tuple[float, float]
    end: tuple[float, float]

    @property
    def length(self) -> float:
        return abs(self.end[0] - self.start[0]) + abs(self.end[1] - self.start[1])


def _interval_subtract(base: tuple[float, float], covered: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out, cursor = [], base[0]
    for a, b in sorted(covered):
        if a > cursor + EPS:
            out.append((cursor, min(a, base[1])))
        cursor = max(cursor, b)
    if cursor < base[1] - EPS:
        out.append((cursor, base[1]))
    return [(a, b) for a, b in out if b - a >= MIN_PIECE_LENGTH]


def _edge(room: Room, side: Side) -> tuple[float, tuple[float, float], bool]:
    """(fixed coordinate, (lo, hi) along the edge, edge runs along x)"""
    x, y, w, d = room.rect
    return {"N": (y + d, (x, x + w), True), "S": (y, (x, x + w), True),
            "E": (x + w, (y, y + d), False), "W": (x, (y, y + d), False)}[side]


def _touching(room: Room, other: Room, side: Side) -> tuple[float, float] | None:
    """The stretch of `room`'s `side` edge that `other` is flush against, or None."""
    fixed, (lo, hi), along_x = _edge(room, side)
    opposite: Side = {"N": "S", "S": "N", "E": "W", "W": "E"}[side]  # type: ignore[assignment]
    ofixed, (olo, ohi), _ = _edge(other, opposite)
    if abs(fixed - ofixed) > EPS:
        return None
    a, b = max(lo, olo), min(hi, ohi)
    return (a, b) if b - a > EPS else None


def wall_pieces(design: Design) -> list[Piece]:
    pieces: list[Piece] = []
    for lv in design.levels:
        rooms = [r for r in design.rooms if r.level == lv.id]
        counters: dict[str, int] = {}

        def make_id(base: str) -> str:
            counters[base] = counters.get(base, 0) + 1
            return base if counters[base] == 1 else f"{base}-{counters[base]}"

        for room in sorted(rooms, key=lambda r: r.id):
            for side in ("N", "S", "E", "W"):
                fixed, (lo, hi), along_x = _edge(room, side)
                covered: list[tuple[float, float]] = []
                for other in rooms:
                    if other.id == room.id:
                        continue
                    span = _touching(room, other, side)
                    if span is None:
                        continue
                    covered.append(span)
                    if room.id < other.id and span[1] - span[0] >= MIN_PIECE_LENGTH:
                        pieces.append(_piece(make_id(f"wall.{lv.id}.{room.id}~{other.id}"), lv.id, room.id, other.id, side, fixed, span, along_x))
                for a, b in _interval_subtract((lo, hi), covered):
                    pieces.append(_piece(make_id(f"wall.{lv.id}.{room.id}.{side}"), lv.id, room.id, None, side, fixed, (a, b), along_x))
    return pieces


def _piece(pid: str, level: str, room: str, other: str | None, side: Side, fixed: float, span: tuple[float, float], along_x: bool) -> Piece:
    start, end = ((span[0], fixed), (span[1], fixed)) if along_x else ((fixed, span[0]), (fixed, span[1]))
    return Piece(pid, level, room, other, side, start, end)


def exterior_sides(design: Design) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {r.id: set() for r in design.rooms}
    for p in wall_pieces(design):
        if p.other is None:
            out[p.room].add(p.side)
    return out


def derive(design: Design) -> BuildingSpec:
    spec = BuildingSpec(name=design.name)
    pieces = wall_pieces(design)
    elevation = 0.0
    for lv in design.levels:
        spec.levels.append(LevelSpec(id=lv.id, name=lv.name or lv.id, elevation=elevation, height=lv.height))
        elevation += lv.height
    names = {r.id: r.name for r in design.rooms}
    for p in pieces:
        lv = next(x for x in spec.levels if x.id == p.level)
        label = (f"{names[p.room]}: {SIDE_NAMES[p.side]} wall" if p.other is None else f"Wall between {names[p.room]} and {names[p.other]}")
        spec.walls.append(WallSpec(id=p.id, label=label, level=p.level, start=p.start, end=p.end, height=lv.height,
                                   thickness=EXTERIOR_THICKNESS if p.other is None else PARTITION_THICKNESS,
                                   external=p.other is None, material=design.wall_material if p.other is None else "plaster"))
    _stairs(design, spec)             # before slabs: each flight cuts a well in the floor above
    _slabs_and_roofs(design, spec)
    _spaces(design, spec)
    _openings(design, spec, pieces)
    _interiors(design, spec, pieces)
    return spec


def _polys(geom) -> list[Polygon]:
    if geom.is_empty:
        return []
    return list(geom.geoms) if isinstance(geom, MultiPolygon) else ([geom] if isinstance(geom, Polygon) else [])


def _room_box(r: Room) -> Polygon:
    return box(r.rect[0], r.rect[1], r.rect[0] + r.rect[2], r.rect[1] + r.rect[3])


def _slabs_and_roofs(design: Design, spec: BuildingSpec) -> None:
    half = EXTERIOR_THICKNESS / 2
    for i, lv in enumerate(design.levels):
        rooms = [r for r in design.rooms if r.level == lv.id]
        if not rooms:
            continue
        footprint = unary_union([_room_box(r) for r in rooms])
        slab_area = footprint.buffer(half, join_style=2)
        wells = [Polygon(s.outline).buffer(STAIR_WELL_MARGIN, join_style=2) for s in spec.stairs if s.to_level == lv.id]
        if wells:
            slab_area = slab_area.difference(unary_union(wells))
        for n, poly in enumerate(_polys(slab_area), 1):
            spec.slabs.append(SlabSpec(id=f"floor.{lv.id}.{n}", label=f"{lv.name or lv.id} floor", level=lv.id, outline=list(poly.exterior.coords)[:-1],
                                       holes=[list(r.coords)[:-1] for r in poly.interiors],
                                       thickness=SLAB_THICKNESS, z_top=spec.level_elevation(lv.id)))
        roofed = unary_union([_room_box(r) for r in rooms if r.roofed])
        above = unary_union([_room_box(r) for r in design.rooms if design.levels.index(design.level(r.level)) > i]) if i + 1 < len(design.levels) else Polygon()
        exposed = roofed.difference(above)
        z = spec.level_elevation(lv.id) + lv.height
        for n, poly in enumerate([p for p in _polys(exposed.buffer(half, join_style=2)) if p.area >= MIN_ROOF_AREA], 1):
            outline = list(poly.exterior.coords)[:-1]
            kind, pitch, note, extra = "flat", 0.0, "", {}
            if design.roof != "flat":
                if is_rectangle(outline):
                    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
                    w, d = max(xs) - min(xs), max(ys) - min(ys)
                    kind, pitch = design.roof, effective_pitch(design.roof, w, d, design.roof_pitch)
                    extra = {"ridge_along": ridge_axis(w, d), "high_side": (design.roof_high_side or "N") if kind == "shed" else None}
                else:
                    note = f"{lv.name or lv.id} roof is kept flat: a {design.roof} roof needs a plain rectangle and this area is not one"
            spec.roofs.append(RoofSpec(id=f"roof.{lv.id}.{n}", label=f"{lv.name or lv.id} roof", level=lv.id, outline=outline, thickness=SLAB_THICKNESS, z_bottom=z,
                                       kind=kind, pitch=pitch, note=note, **extra))


def _stairs(design: Design, spec: BuildingSpec) -> None:
    for st in design.stairs:
        room = design.room(st.room)
        if room is None:
            raise DesignError(f"stair '{st.id}': unknown room '{st.room}'", st.id)
        levels = [lv.id for lv in design.levels]
        nxt = levels[levels.index(room.level) + 1] if levels.index(room.level) + 1 < len(levels) else None
        to_level = st.to_level or nxt
        if to_level is None or to_level != nxt:
            raise DesignError(f"stair '{st.id}': there is no level above {room.level} to climb to; add a level first", st.id)
        rise = design.level(room.level).height  # type: ignore[union-attr]
        risers = max(2, math.ceil(rise / MAX_RISER_M - 1e-9))
        length = (risers - 1) * GOING_M
        x, y, w, d = room.rect
        c = STAIR_WALL_CLEARANCE
        along_y = st.side in ("E", "W")
        inner_len, inner_cross = (d, w) if along_y else (w, d)
        if inner_len - 2 * c < length - EPS or inner_cross - 2 * c < st.width - EPS:
            raise DesignError(f"stair '{st.id}': a flight for {rise:g} m needs {length:.2f} m along the wall and {st.width:g} m across; "
                              f"'{room.name}' side {st.side} offers {inner_len - 2 * c:.2f} x {inner_cross - 2 * c:.2f} m. Use a longer room or another side", st.id)
        if along_y:
            x0 = x + c if st.side == "W" else x + w - c - st.width
            rect = box(x0, y + c, x0 + st.width, y + c + length)
            start, direction = (x0 + st.width / 2, y + c), (0.0, 1.0)
        else:
            y0 = y + c if st.side == "S" else y + d - c - st.width
            rect = box(x + c, y0, x + c + length, y0 + st.width)
            start, direction = (x + c, y0 + st.width / 2), (1.0, 0.0)
        above = unary_union([_room_box(r) for r in design.rooms if r.level == to_level])
        if not above.buffer(EPS).contains(rect):
            raise DesignError(f"stair '{st.id}': its top would land outside every room on {to_level}. Put a hall or landing on {to_level} that covers "
                              f"x {rect.bounds[0]:.2f}..{rect.bounds[2]:.2f}, y {rect.bounds[1]:.2f}..{rect.bounds[3]:.2f}", st.id)
        spec.stairs.append(StairSpec(id=st.id, label=f"Stair in {room.name}", level=room.level, to_level=to_level, outline=list(rect.exterior.coords)[:-1], start=start,
                                     direction=direction, width=st.width, risers=risers, riser_height=round(rise / risers, 4), going=GOING_M,
                                     length=length, z0=spec.level_elevation(room.level)))


def _spaces(design: Design, spec: BuildingSpec) -> None:
    for r in design.rooms:
        inner = _room_box(r).buffer(-SPACE_INSET, join_style=2)
        if inner.is_empty:
            continue
        spec.spaces.append(SpaceSpec(id=f"room.{r.level}.{r.id}", name=r.name, level=r.level, kind=r.kind,
                                     outline=list(inner.exterior.coords)[:-1], area=round(inner.area, 2)))


def _free_centre(length: float, width: float, preferred: float, taken: list[tuple[float, float]], margin: float = OPENING_END_MARGIN) -> float | None:
    """Centre nearest `preferred` where an opening of `width` fits without touching the ends or other openings."""
    lo, hi = margin + width / 2, length - margin - width / 2
    if hi < lo - EPS:
        return None
    best: float | None = None
    steps = int(round((hi - lo) / 0.05)) + 1
    for k in range(steps):
        c = lo + k * 0.05 if steps > 1 else lo
        if all(c + width / 2 + OPENING_GAP <= a or c - width / 2 - OPENING_GAP >= b for a, b in taken):
            if best is None or abs(c - preferred) < abs(best - preferred):
                best = c
    return best


def _openings(design: Design, spec: BuildingSpec, pieces: list[Piece]) -> None:
    by_id = {p.id: p for p in pieces}
    taken: dict[str, list[tuple[float, float]]] = {}

    def place(candidates: list[Piece], at: float, width: float, height: float, sill: float, oid: str, kind: str, style: str, what: str, label: str) -> None:
        margin = ARCHWAY_END_MARGIN if style == "opening" else OPENING_END_MARGIN        # an archway may run nearly the whole wall
        for p in candidates:
            centre = _free_centre(p.length, width, at * p.length, taken.get(p.id, []), margin)
            if centre is None:
                continue
            taken.setdefault(p.id, []).append((centre - width / 2, centre + width / 2))
            spec.openings.append(OpeningSpec(id=oid, label=label, kind=kind, host=p.id, offset=round(centre, 3), width=width, height=height,  # type: ignore[arg-type]
                                             sill=sill, style=style, level=p.level))
            return
        longest = max((p.length for p in candidates), default=0.0)
        hint = (f"; for a gap that wide use kind \"opening\" (an archway can be up to {longest - 0.1:.1f} m)" if style != "opening" and width > longest - 2 * OPENING_END_MARGIN > 0 else "")
        raise DesignError(f"{what}: no free space for a {width} m opening on the chosen wall; make the wall longer, use a narrower opening or another side{hint}", oid)

    for door in design.doors:
        room = design.room(door.room)
        assert room is not None
        level_h = design.level(room.level).height  # type: ignore[union-attr]
        width = max(door.width, GARAGE_DOOR_WIDTH) if door.kind == "garage" else door.width
        height = min(door.height, level_h - HEADROOM_ABOVE_DOOR)
        if door.to == "outside":
            cands = [p for p in pieces if p.room == room.id and p.other is None and (door.side is None or p.side == door.side)]
            cands.sort(key=lambda p: (SIDE_PREFERENCE.index(p.side), -p.length))
            if not cands:
                raise DesignError(f"door '{door.id}': room '{room.name}' has no exterior wall" + (f" on side {door.side}" if door.side else ""), door.id)
        else:
            cands = [p for p in pieces if {p.room, p.other} == {room.id, door.to}]
            cands.sort(key=lambda p: -p.length)
            if not cands:
                raise DesignError(f"door '{door.id}': '{room.name}' and '{door.to}' do not share a wall; use a room they both touch or 'outside'", door.id)
        place(cands, door.at, width, height, 0.0, door.id, "door", door.kind, f"door '{door.id}'",
              f"Door: {room.name} to " + ("outside" if door.to == "outside" else (design.room(door.to).name if design.room(door.to) else door.to)))

    for win in design.windows:
        room = design.room(win.room)
        assert room is not None
        level_h = design.level(room.level).height  # type: ignore[union-attr]
        cands = [p for p in pieces if p.room == room.id and p.other is None and p.side == win.side]
        if not cands:
            sides = sorted({p.side for p in pieces if p.room == room.id and p.other is None})
            raise DesignError(f"window '{win.id}': the {win.side} wall of '{room.name}' is not an exterior wall; exterior sides are {', '.join(sides) or 'none'}", win.id)
        cands.sort(key=lambda p: -p.length)
        height = min(win.height, level_h - win.sill - HEADROOM_ABOVE_DOOR)
        place(cands, win.at, win.width, height, win.sill, win.id, "window", win.kind, f"window '{win.id}'", f"Window: {room.name}, {SIDE_NAMES[win.side]} wall")
    assert all(o.host in by_id for o in spec.openings)


COVERING_THICKNESS = 0.012


def _interiors(design: Design, spec: BuildingSpec, pieces: list[Piece]) -> None:
    """Furniture (checked: inside its room, not on another piece, not where a door swings or a stair runs) and the floor and wall finishes."""
    if design.furniture:
        zones = keep_outs(spec)
        for f in design.furniture:
            room = design.room(f.room)
            if room is None:
                raise DesignError(f"furniture '{f.id}': unknown room '{f.room}'", f.id)
            item = CATALOGUE.get(f.kind)
            if item is None:
                raise DesignError(f"furniture '{f.id}': unknown kind '{f.kind}'", f.id)
            poly = furniture_polygon(f)
            before = [(g.id, furniture_polygon(g)) for g in design.furniture if g.room == f.room and g.id < f.id]
            try:
                check_fit(room, poly, f"{item.label} '{f.id}'", before)
            except DoesNotFit as exc:
                raise DesignError(str(exc), f.id) from exc
            if any(poly.intersection(z).area > 1e-3 for z in zones.get(room.level, [])):
                raise DesignError(f"{item.label} '{f.id}' is where a door swings or a stair runs in '{room.name}'; put it on another wall or position", f.id)
            try:
                main = resolve(f.colour, COLOURS, "colour") if f.colour else (PART_COLOURS.get(item.colour) or COLOURS[item.colour])
            except UnknownName as exc:
                raise DesignError(f"furniture '{f.id}': {exc}", f.id) from exc
            z = spec.level_elevation(room.level)
            boxes: list[BoxSpec] = []
            for x0, y0, x1, y1, z0, z1, key in parts(f.kind, f.w, f.d, f.h):
                if z1 - z0 < 1e-3 or x1 - x0 < 1e-3 or y1 - y0 < 1e-3:
                    continue
                ring = affinity_rotate(box(x0, y0, x1, y1), f.rot).exterior.coords
                boxes.append(BoxSpec(outline=[(round(px + f.x, 4), round(py + f.y, 4)) for px, py in list(ring)[:-1]], z0=round(z + z0, 4), depth=round(z1 - z0, 4),
                                     colour=main if key == "main" else PART_COLOURS[key]))
            spec.furniture.append(FurnitureSpec(id=f.id, label=f"{item.label}: {room.name}", level=room.level, room=room.id, kind=f.kind,
                                                outline=[(round(px, 4), round(py, 4)) for px, py in list(poly.exterior.coords)[:-1]], z0=z, height=f.h,
                                                ifc=item.ifc, rot=f.rot, w=f.w, d=f.d, boxes=boxes))
    if any(r.floor or r.walls for r in design.rooms):
        _coverings(design, spec, pieces)


def affinity_rotate(poly: Polygon, rot: int) -> Polygon:
    from shapely import affinity
    return affinity.rotate(poly, rot, origin=(0, 0))


def _coverings(design: Design, spec: BuildingSpec, pieces: list[Piece]) -> None:
    sides = exterior_sides(design)
    holes_by_wall: dict[str, list[tuple[float, float, float, float]]] = {}
    for o in spec.openings:
        holes_by_wall.setdefault(o.host, []).append((o.offset - o.width / 2, o.sill, o.offset + o.width / 2, o.sill + o.height))
    for r in design.rooms:
        z = spec.level_elevation(r.level)
        try:
            floor = resolve(r.floor, FLOORS, "floor finish") if r.floor else None
            paint = resolve(r.walls, PAINTS, "wall paint") if r.walls else None
        except UnknownName as exc:
            raise DesignError(f"room '{r.name}': {exc}") from exc
        x, y, w, d = r.rect
        if floor:
            ins = {s: (EXTERIOR_THICKNESS if s in sides[r.id] else PARTITION_THICKNESS) / 2 for s in ("N", "S", "E", "W")}
            x0, y0, x1, y1 = x + ins["W"], y + ins["S"], x + w - ins["E"], y + d - ins["N"]
            spec.coverings.append(CoveringSpec(id=f"covering.floor.{r.level}.{r.id}", label=f"Floor finish: {r.name} ({r.floor})", level=r.level, room=r.id, kind="floor",
                                               finish=str(r.floor), colour=floor, thickness=COVERING_THICKNESS, z0=z, area=round((x1 - x0) * (y1 - y0), 2),
                                               outline=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))
        if not paint:
            continue
        cx, cy = x + w / 2, y + d / 2
        lv_h = design.level(r.level).height  # type: ignore[union-attr]
        for p in (q for q in pieces if q.level == r.level and r.id in (q.room, q.other)):
            ux, uy = (p.end[0] - p.start[0]) / p.length, (p.end[1] - p.start[1]) / p.length
            n = (-uy, ux)
            mid = ((p.start[0] + p.end[0]) / 2, (p.start[1] + p.end[1]) / 2)
            if (cx - mid[0]) * n[0] + (cy - mid[1]) * n[1] < 0:
                n = (uy, -ux)
            t = EXTERIOR_THICKNESS if p.other is None else PARTITION_THICKNESS
            holes = sorted(holes_by_wall.get(p.id, []))
            hole_area = sum((a1 - a0) * (b1 - b0) for a0, b0, a1, b1 in holes)
            spec.coverings.append(CoveringSpec(
                id=f"covering.wall.{p.id}.{r.id}", label=f"Wall finish: {r.name}, {SIDE_NAMES[p.side]} wall ({r.walls})" if p.room == r.id else f"Wall finish: {r.name}, shared wall ({r.walls})",
                level=r.level, room=r.id, kind="wall", finish=str(r.walls), colour=paint, thickness=COVERING_THICKNESS, z0=z,
                area=round(max(p.length * lv_h - hole_area, 0.0), 2), start=p.start, end=p.end, normal=n, wall_thickness=t, length=round(p.length, 4), height=lv_h, holes=holes))


MAX_PRUNED_OPENINGS = 40


def prune_blocking_furniture(design: Design) -> tuple[Design, list[str]]:
    """A new door or stair may land where a piece stands. The piece gives way (and the version says so) rather than the door being refused."""
    removed: list[str] = []
    current = design
    for _ in range(MAX_PRUNED_OPENINGS):
        try:
            derive(current)
            return current, removed
        except DesignError as exc:
            if exc.opening_id is None or not any(f.id == exc.opening_id for f in current.furniture):
                raise
            current = current.model_copy(update={"furniture": [f for f in current.furniture if f.id != exc.opening_id]})
            removed.append(f"furniture {exc.opening_id} removed: it stood where the new door or stair goes")
    raise DesignError("too many pieces of furniture are in the way; move or delete some first")


def prune_invalid_openings(design: Design) -> tuple[Design, list[str]]:
    """After a structural change (a room added, moved or removed) some doors and windows may no longer have a wall to sit in.
    Drop those and say so, rather than rejecting the change the user actually asked for."""
    removed: list[str] = []
    current = design
    for _ in range(MAX_PRUNED_OPENINGS):
        try:
            derive(current)
            return current, removed
        except DesignError as exc:
            if exc.opening_id is None:
                raise
            kind = ("door" if any(d.id == exc.opening_id for d in current.doors) else
                    "stair" if any(t.id == exc.opening_id for t in current.stairs) else
                    "furniture" if any(f.id == exc.opening_id for f in current.furniture) else "window")
            current = current.model_copy(update={"doors": [d for d in current.doors if d.id != exc.opening_id],
                                                 "windows": [w for w in current.windows if w.id != exc.opening_id],
                                                 "stairs": [t for t in current.stairs if t.id != exc.opening_id],
                                                 "furniture": [f for f in current.furniture if f.id != exc.opening_id]})
            removed.append(f"{kind} {exc.opening_id} removed: {exc}")
    raise DesignError("too many openings no longer fit; rearrange the rooms first")
