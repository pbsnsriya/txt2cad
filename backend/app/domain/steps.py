"""Steps: the small, flat deltas an LLM streams. apply_step is pure and rejects bad steps with a message written for the model.

Every field except `step` is optional so lenient models can still be understood; extra keys are ignored and
common slips are normalised ("north" -> "N", 2 -> "L2", {"x","y","w","d"} -> rect).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from shapely.geometry import box

from .catalogue import FLOORS, PAINTS, UnknownName, item_for, resolve
from .derive import DesignError, derive
from .design import Design, Door, Furniture, Level, Room, Stair, Window, MAX_LEVELS
from .furnish import DoesNotFit, against, centred, check_fit, corner, footprint, furniture_polygon, inner, is_ceiling, keep_outs, layout_room
from .roofs import MAX_PITCH, MIN_PITCH, roof_kind

MAX_DOOR_WIDTH_M = 2.0
SKIPPED_PREFIX = "rearrange skipped a room: "
STEP_KINDS = ("project", "storey", "room", "rearrange", "door", "window", "stair", "roof", "material", "furnish", "furniture", "finish", "delete", "remark")
SIDE_WORDS = {"north": "N", "south": "S", "east": "E", "west": "W", "n": "N", "s": "S", "e": "E", "w": "W"}
OVERLAP_TOLERANCE_M2 = 1e-6


class StepError(ValueError):
    """A step the design cannot accept. The message goes back to the model, so say what to do instead."""


class Step(BaseModel):
    model_config = ConfigDict(extra="ignore")
    step: str
    why: str | None = None
    id: str | int | None = None
    name: str | None = None
    description: str | None = None
    level: str | int | None = None
    kind: str | None = None
    height: float | None = None
    rect: Any = None
    rooms: list[dict[str, Any]] | None = None
    roofed: bool | None = None
    room: str | None = None
    to: str | None = None
    side: str | None = None
    at: float | None = None
    width: float | None = None
    sill: float | None = None
    to_level: str | int | None = None
    material: str | None = None
    pitch: float | None = None
    depth: float | None = None
    across: float | None = None
    gap: float | None = None
    rotation: int | None = None
    colour: str | None = None
    color: str | None = None
    floor: str | None = None
    walls: str | None = None
    text: str | None = None

    @field_validator("id", "room", "to", mode="before")
    @classmethod
    def _as_text(cls, v: Any) -> Any:
        return str(v) if isinstance(v, int) and not isinstance(v, bool) else v


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "item"


def norm_level(value: str | int | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, int) or re.fullmatch(r"\d+", str(value)):
        return f"L{int(value)}"
    return str(value)


def norm_side(value: str | None) -> str | None:
    if value is None:
        return None
    side = SIDE_WORDS.get(str(value).strip().lower())
    if side is None:
        raise StepError(f"side '{value}' is not valid; use N, S, E or W")
    return side


def norm_rect(value: Any) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        try:
            return (float(value["x"]), float(value["y"]), float(value.get("w", value.get("width"))), float(value.get("d", value.get("depth"))))
        except (KeyError, TypeError, ValueError) as exc:
            raise StepError("rect object needs x, y, w, d (metres)") from exc
    try:
        x, y, w, d = (float(v) for v in value)
    except (TypeError, ValueError) as exc:
        raise StepError("rect must be [x, y, width, depth] in metres") from exc
    return (x, y, w, d)


_LEVEL_CODE = re.compile(r"\(?\b(?:L\d+|level\s*\d+)\b\)?", re.IGNORECASE)


def tidy_name(raw: str | None, kind: str = "other") -> str:
    """A room's name the way a person says it: 'bedroom-2' is 'Bedroom 2', 'L1 hall' is 'Hall', 'living room' is 'Living Room'."""
    text = (raw or "").replace("_", " ")
    text = re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z0-9])", " ", text)
    text = _LEVEL_CODE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" -/()")
    if not text:
        text = (kind or "room").replace("_", " ")
    return re.sub(r"[A-Za-z][a-z']*", lambda m: m.group(0).capitalize() if m.group(0).islower() else m.group(0), text)


def _unique_id(existing: set[str], base: str) -> str:
    candidate, n = base, 2
    while candidate in existing:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def _check_overlap(design: Design, room: Room) -> None:
    mine = box(room.rect[0], room.rect[1], room.rect[0] + room.rect[2], room.rect[1] + room.rect[3])
    for other in design.rooms:
        if other.id == room.id or other.level != room.level:
            continue
        theirs = box(other.rect[0], other.rect[1], other.rect[0] + other.rect[2], other.rect[1] + other.rect[3])
        if mine.intersection(theirs).area > OVERLAP_TOLERANCE_M2:
            raise StepError(
                f"room '{room.name}' overlaps '{other.name}' on {room.level}; rooms may touch along an edge but not overlap. "
                f"'{other.name}' occupies x {other.rect[0]}..{other.rect[0] + other.rect[2]}, y {other.rect[1]}..{other.rect[1] + other.rect[3]}"
            )


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


_LEVEL_SUFFIX = re.compile(r"[\s(]+(L\d+|level\s*\d+)\)?\s*$", re.IGNORECASE)
_LEVEL_PREFIX = re.compile(r"^\s*\(?(L\d+|level\s*\d+)\)?[\s:,-]+", re.IGNORECASE)


def _room_ref(design: Design, ref: str | None, what: str, prefer_level: str | None = None) -> Room:
    """Find a room by id, by name, or by how models like to write it: 'Living Room', 'Bedroom 1', 'Hall L2'."""
    if not ref:
        raise StepError(f"{what}: 'room' is required")
    ref = str(ref)
    exact = [r for r in design.rooms if ref == r.id] or [r for r in design.rooms if ref.lower() == r.name.lower()]
    cands = exact
    if not cands:
        level = None
        base = ref
        m = _LEVEL_SUFFIX.search(ref)
        pre = _LEVEL_PREFIX.match(ref)
        if m:
            level, base = norm_level(re.sub(r"(?i)level\s*", "", m.group(1))), ref[:m.start()]
        elif pre:
            level, base = norm_level(re.sub(r"(?i)level\s*", "", pre.group(1))), ref[pre.end():]
        k = _key(base)
        no_digits = re.sub(r"\d+$", "", k)
        variants = {k, k.removesuffix("room"), no_digits, no_digits.removesuffix("room")} - {""}
        cands = [r for r in design.rooms if (level is None or r.level == level)
                 and ({_key(r.id), _key(r.name), re.sub(r"\d+$", "", _key(r.name))} & variants)]
    if len(cands) > 1 and prefer_level:
        near = [r for r in cands if r.level == prefer_level]
        cands = near or cands
    if len(cands) > 1:
        raise StepError(f"{what}: '{ref}' matches several rooms ({', '.join(r.id for r in cands)}); use the exact room id")
    if not cands:
        ids = ", ".join(r.id for r in design.rooms) or "none yet"
        raise StepError(f"{what}: unknown room '{ref}' (rooms: {ids})")
    return cands[0]


def apply_step(design: Design, step: Step) -> Design:
    """Return a new Design with the step applied, or raise StepError."""
    d = design.model_copy(deep=True)
    kind = step.step
    if kind not in STEP_KINDS:
        raise StepError(f"unknown step '{kind}'; use one of: {', '.join(STEP_KINDS)}")

    if kind == "project":
        d.name = step.name or d.name
        d.description = step.description or d.description
    elif kind == "storey":
        lid = norm_level(step.id) or f"L{len(d.levels) + 1}"
        existing = d.level(lid)
        if existing is None and len(d.levels) >= MAX_LEVELS:
            raise StepError(f"at most {MAX_LEVELS} levels")
        if existing is None and lid != f"L{len(d.levels) + 1}":
            raise StepError(f"levels must be added in order; the next level id is L{len(d.levels) + 1}")
        lv = Level(id=lid, name=step.name or (existing.name if existing else f"Level {len(d.levels) + 1}"),
                   height=step.height or (existing.height if existing else 3.0))
        d.levels = [lv if x.id == lid else x for x in d.levels] if existing else [*d.levels, lv]
    elif kind == "room":
        _apply_room(d, step)
    elif kind == "rearrange":
        lid = _default_level(d, step.level)
        if d.level(lid or "") is None:
            raise StepError(f"rearrange: unknown level '{step.level}' (levels: {', '.join(x.id for x in d.levels) or 'none yet'})")
        old = {r.name.lower(): r for r in d.rooms if r.level == lid}
        d.rooms = [r for r in d.rooms if r.level != lid]
        skipped: list[str] = []
        for spec in step.rooms or []:
            try:
                _apply_room(d, Step(step="room", level=lid, **{k: v for k, v in spec.items() if k in Step.model_fields and k not in ('level', 'step')}), keep=old)
            except (StepError, ValidationError) as exc:
                name = spec.get("name") or spec.get("kind") or "a room"
                skipped.append(str(exc) if isinstance(exc, StepError) else f"room '{name}': {exc.errors()[0]['msg'].removeprefix('Value error, ')}")
        if skipped and not any(r.level == lid for r in d.rooms):
            raise StepError(f"rearrange: none of the {len(skipped)} rooms could be placed; the first problem was: {skipped[0]}")
        for message in skipped:               # the rooms that fit stay; each one that did not is reported so the next round can fix it
            d.notes.append(f"{SKIPPED_PREFIX}{message}")
        _drop_dangling(d)                     # rooms that disappeared take their doors, windows and stairs with them
    elif kind == "door":
        room = _room_ref(d, step.room, "door")
        to = step.to or "outside"
        if to != "outside":
            other = _room_ref(d, to, "door", prefer_level=room.level)
            if other.level != room.level:
                raise StepError(f"door: '{room.name}' and '{other.name}' are on different levels")
            to = other.id
        wide = step.width is not None and step.width > MAX_DOOR_WIDTH_M and step.kind in (None, "single", "double") and to != "outside"
        if wide:                                              # no door is that wide: the request means a gap in the wall, whatever the model called it
            step = step.model_copy(update={"kind": "opening"})
        if step.kind == "opening" and to != "outside":      # an archway takes the place of any door already in that wall
            d.doors = [x for x in d.doors if {x.room, x.to} != {room.id, to}]
        did = step.id or _unique_id({x.id for x in d.doors}, f"door.{room.id}.{to}")
        data = dict(id=did, room=room.id, to=to, side=norm_side(step.side), at=step.at if step.at is not None else 0.5)
        if step.kind:
            data["kind"] = step.kind
        if step.width:
            data["width"] = step.width
        d.doors = [x for x in d.doors if x.id != did] + [Door(**data)]
    elif kind == "window":
        room = _room_ref(d, step.room, "window")
        side = norm_side(step.side)
        if side is None:
            raise StepError(f"window: 'side' (N, S, E or W) is required for '{room.name}'")
        wid = step.id or _unique_id({x.id for x in d.windows}, f"window.{room.id}.{side}")
        data = dict(id=wid, room=room.id, side=side, at=step.at if step.at is not None else 0.5)
        if step.kind:
            data["kind"] = step.kind
        if step.width:
            data["width"] = step.width
        if step.sill is not None:
            data["sill"] = step.sill
        d.windows = [x for x in d.windows if x.id != wid] + [Window(**data)]
    elif kind == "stair":
        room = _room_ref(d, step.room, "stair")
        side = norm_side(step.side)
        if side is None:
            raise StepError(f"stair: 'side' (N, S, E or W: the wall it runs along) is required for '{room.name}'")
        sid = step.id if isinstance(step.id, str) and step.id else f"stair.{room.id}"
        data: dict = dict(id=sid, room=room.id, side=side, to_level=norm_level(step.to_level))
        if step.width:
            data["width"] = step.width
        d.stairs = [x for x in d.stairs if x.id != sid and x.room != room.id] + [Stair(**data)]
    elif kind == "roof":
        rk = roof_kind(step.kind)
        if rk is None:
            raise StepError(f"roof kind '{step.kind}' is not one this tool builds; use flat, gable, hip or shed (pitched means gable)")
        if step.pitch is not None and not (MIN_PITCH <= step.pitch <= MAX_PITCH):
            raise StepError(f"roof pitch is in degrees, between {MIN_PITCH:g} and {MAX_PITCH:g} (got {step.pitch:g})")
        d.roof = rk  # type: ignore[assignment]
        if step.pitch is not None:
            d.roof_pitch = step.pitch
        if rk == "shed":
            side = norm_side(step.side)
            d.roof_high_side = side or d.roof_high_side or "N"
    elif kind == "material":
        if step.material not in ("masonry", "concrete", "timber", "plaster"):
            raise StepError("material must be masonry, concrete, timber or plaster")
        d.wall_material = step.material  # type: ignore[assignment]
    elif kind == "furniture":
        _apply_furniture(d, step)
    elif kind == "furnish":
        _apply_furnish(d, step)
    elif kind == "finish":
        _apply_finish(d, step)
    elif kind == "delete":
        _remove(d, step.id)
    elif kind == "remark":
        d.notes.append(step.text or "")
    return d


def _drop_dangling(d: Design) -> None:
    ids = {r.id for r in d.rooms}
    d.doors = [x for x in d.doors if x.room in ids and (x.to == "outside" or x.to in ids)]
    d.windows = [x for x in d.windows if x.room in ids]
    d.stairs = [x for x in d.stairs if x.room in ids]
    d.furniture = [x for x in d.furniture if x.room in ids]


def _default_level(d: Design, level: str | int | None) -> str | None:
    """Small models often leave the level out. With levels present, the newest one is the obvious meaning."""
    return norm_level(level) or (d.levels[-1].id if d.levels else None)


_KIND_WORDS = {"bedroom": "bedroom", "bathroom": "bathroom", "kitchen": "kitchen", "living": "living", "lounge": "living", "dining": "dining", "hall": "hall",
               "hallway": "hall", "corridor": "hall", "office": "office", "study": "office", "garage": "garage", "utility": "utility", "storage": "storage", "store": "storage"}


def kind_from_name(name: str, kind: str | None) -> str:
    """The kind a room is when the model left it as 'other' but called it Bedroom 1 or Living Room."""
    if kind and kind != "other":
        return kind
    for word in re.findall(r"[a-z]+", name.lower()):
        if word in _KIND_WORDS:
            return _KIND_WORDS[word]
    return kind or "other"


def _apply_room(d: Design, step: Step, keep: dict[str, Room] | None = None) -> None:
    lid = _default_level(d, step.level)
    if lid is None:
        raise StepError("room: 'level' is required (for example \"L1\"); add a level step first")
    if d.level(lid) is None:
        raise StepError(f"room: unknown level '{lid}' (levels: {', '.join(x.id for x in d.levels) or 'none yet; add a level step first'})")
    name = step.name or step.room            # the schema has both fields; small models mix them up
    if not name and step.kind:               # ...and often give only a kind: "bedroom" -> "Bedroom", "Bedroom 2" if taken
        base = step.kind.replace("_", " ").capitalize()
        taken = {r.name.lower() for r in d.rooms if r.level == lid}
        name = base if base.lower() not in taken else next(f"{base} {n}" for n in range(2, 99) if f"{base} {n}".lower() not in taken)
    if not name:
        raise StepError("room: 'name' (or at least 'kind') is required")
    name = tidy_name(name, step.kind or "other")
    rect = norm_rect(step.rect)
    existing = next((r for r in d.rooms if r.id == step.id or (r.level == lid and r.name.lower() == name.lower())), None)
    if existing is None and keep:
        existing = keep.get(name.lower())
    if rect is None and existing is None:
        raise StepError(f"room '{name}': 'rect' [x, y, width, depth] in metres is required for a new room")
    rid = existing.id if existing else _unique_id({r.id for r in d.rooms}, slug(name))
    room = Room(id=rid, name=name, level=lid, kind=kind_from_name(name, step.kind or (existing.kind if existing else "other")),
                rect=rect or existing.rect, roofed=step.roofed if step.roofed is not None else (existing.roofed if existing else True))
    _check_overlap(d, room)
    d.rooms = [r for r in d.rooms if r.id != rid] + [room]


def _targets(d: Design, step: Step, what: str) -> list[Room]:
    """The rooms a furnish or finish step is about: one room, a level, or all of them."""
    ref = (step.room or "").strip()
    if ref.lower() in ("", "all", "every room", "everything", "*"):
        level = norm_level(step.level)
        rooms = [r for r in d.rooms if level is None or r.level == level]
        if not rooms:
            raise StepError(f"{what}: there are no rooms{' on ' + level if level else ''} yet")
        return rooms
    return [_room_ref(d, ref, what)]


def _apply_furniture(d: Design, step: Step) -> None:
    """Place a piece, or change one: with the id of a piece that exists, only the fields given change and the rest stays as it was."""
    existing = next((f for f in d.furniture if step.id and f.id == step.id), None)
    room = _room_ref(d, step.room or (existing.room if existing else None), "furniture")
    if existing is None and not step.kind:
        raise StepError("furniture: 'kind' is required for a new piece; to change one that exists, give its id")
    try:
        item = item_for(step.kind or (existing.kind if existing else None))
        resolve(step.colour or step.color, {}, "colour")
    except UnknownName as exc:
        raise StepError(f"furniture: {exc}") from exc
    w = step.width or (existing.w if existing else item.w)
    depth = step.depth or (existing.d if existing else item.d)
    h = step.height or (existing.h if existing else item.h)
    moving = any(v is not None for v in (step.side, step.at, step.across, step.rotation))
    side = (step.side or "center").strip().lower()
    try:
        if existing is not None and not moving and not is_ceiling(item.kind):
            fx, fy = {0: (0.0, -1.0), 90: (1.0, 0.0), 180: (0.0, 1.0), 270: (-1.0, 0.0)}[existing.rot]       # the way its back faces
            back = (existing.x + fx * existing.d / 2, existing.y + fy * existing.d / 2)                      # keep the back where it was against the wall
            cx, cy, rot = round(back[0] - fx * depth / 2, 3), round(back[1] - fy * depth / 2, 3), existing.rot
        elif side in ("center", "centre", "middle", "centred"):
            cx, cy = centred(room, step.at if step.at is not None else 0.5, step.across if step.across is not None else 0.5)
            rot = (step.rotation or 0) % 360
            if rot not in (0, 90, 180, 270):
                raise StepError("furniture: rotation is 0, 90, 180 or 270 degrees")
        elif corner(side):
            wall, at_end = corner(side)  # type: ignore[misc]
            cx, cy, rot = against(room, w, depth, wall, at_end, step.gap or 0.0)
        else:
            cx, cy, rot = against(room, w, depth, norm_side(side) or "S", step.at if step.at is not None else 0.5, step.gap or 0.0)
            if step.rotation is not None:
                rot = step.rotation % 360
                if rot not in (0, 90, 180, 270):
                    raise StepError("furniture: rotation is 0, 90, 180 or 270 degrees")
                x0, y0, x1, y1 = inner(room)               # turned, it may reach past the wall it stands on: slide it back inside
                minx, miny, maxx, maxy = footprint(cx, cy, w, depth, rot).bounds
                cx = round(cx + max(x0 - minx, 0.0) - max(maxx - x1, 0.0), 3)
                cy = round(cy + max(y0 - miny, 0.0) - max(maxy - y1, 0.0), 3)
    except DoesNotFit as exc:
        raise StepError(f"furniture: {exc}") from exc
    fid = step.id if isinstance(step.id, str) and step.id else _unique_id({f.id for f in d.furniture}, f"furn.{room.id}.{item.kind}")
    others = [(f.id, furniture_polygon(f)) for f in d.furniture if f.room == room.id and f.id != fid and is_ceiling(f.kind) == is_ceiling(item.kind)]
    try:
        check_fit(room, footprint(cx, cy, w, depth, rot), f"{item.label} '{fid}'", others)
    except DoesNotFit as exc:
        raise StepError(f"furniture: {exc}") from exc
    colour_token = (step.colour or step.color or "").strip().lower() or (existing.colour if existing else None)
    piece = Furniture(id=fid, room=room.id, kind=item.kind, x=cx, y=cy, w=w, d=depth, h=h, rot=rot, colour=colour_token)  # type: ignore[arg-type]
    d.furniture = [f for f in d.furniture if f.id != fid] + [piece]


def _apply_furnish(d: Design, step: Step) -> None:
    rooms = _targets(d, step, "furnish")
    try:
        spec = derive(d)
    except DesignError as exc:
        raise StepError(f"furnish: the design cannot be built yet ({exc}); fix that first") from exc
    zones = keep_outs(spec)
    added = 0
    for room in rooms:
        taken = {f.id for f in d.furniture}

        def next_id(kind: str, room=room, taken=taken) -> str:
            nid = _unique_id(taken, f"furn.{room.id}.{kind}")
            taken.add(nid)
            return nid

        new = layout_room(room, [f for f in d.furniture if f.room == room.id], zones.get(room.level, []), next_id)
        d.furniture = [*d.furniture, *new]
        added += len(new)
    if not added:
        d.notes.append("furnish: nothing more to add; the rooms are furnished already or are not kinds this tool furnishes (living, bedroom, kitchen, dining, bathroom, office, utility)")


def _apply_finish(d: Design, step: Step) -> None:
    if step.floor is None and step.walls is None:
        raise StepError("finish: give 'floor' and/or 'walls' (a name such as oak or cream, or a colour like #b89464)")
    try:
        floor = None if step.floor is None else (None if step.floor.strip().lower() in ("none", "") else (resolve(step.floor, FLOORS, "floor finish"), step.floor.strip().lower()))
        walls = None if step.walls is None else (None if step.walls.strip().lower() in ("none", "") else (resolve(step.walls, PAINTS, "wall paint"), step.walls.strip().lower()))
    except UnknownName as exc:
        raise StepError(f"finish: {exc}") from exc
    for room in _targets(d, step, "finish"):
        if step.floor is not None:
            room.floor = floor[1] if floor else None
        if step.walls is not None:
            room.walls = walls[1] if walls else None


def _remove(d: Design, item_id: str | None) -> None:
    if not item_id:
        raise StepError("remove: 'id' is required")
    if any(f.id == item_id for f in d.furniture):
        d.furniture = [f for f in d.furniture if f.id != item_id]
    elif d.room(item_id):
        d.rooms = [r for r in d.rooms if r.id != item_id]
        d.doors = [x for x in d.doors if x.room != item_id and x.to != item_id]
        d.windows = [x for x in d.windows if x.room != item_id]
        d.stairs = [x for x in d.stairs if x.room != item_id]
        d.furniture = [x for x in d.furniture if x.room != item_id]
    elif d.level(item_id):
        gone = {r.id for r in d.rooms if r.level == item_id}
        d.rooms = [r for r in d.rooms if r.level != item_id]
        d.doors = [x for x in d.doors if x.room not in gone and x.to not in gone]
        d.windows = [x for x in d.windows if x.room not in gone]
        d.stairs = [x for x in d.stairs if x.room not in gone]
        d.furniture = [x for x in d.furniture if x.room not in gone]
        d.levels = [x for x in d.levels if x.id != item_id]
    elif any(x.id == item_id for x in d.doors):
        d.doors = [x for x in d.doors if x.id != item_id]
    elif any(x.id == item_id for x in d.windows):
        d.windows = [x for x in d.windows if x.id != item_id]
    elif any(x.id == item_id for x in d.stairs):
        d.stairs = [x for x in d.stairs if x.id != item_id]
    else:
        raise StepError(f"remove: nothing with id '{item_id}'")
