"""Steps: the small, flat deltas an LLM streams. apply_step is pure and rejects bad steps with a message written for the model.

Every field except `step` is optional so lenient models can still be understood; extra keys are ignored and
common slips are normalised ("north" -> "N", 2 -> "L2", {"x","y","w","d"} -> rect).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from shapely.geometry import box

from .design import Design, Door, Level, Room, Stair, Window, MAX_LEVELS

STEP_KINDS = ("building", "level", "room", "layout", "door", "window", "stair", "roof", "material", "remove", "note")
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
        if m:
            level, base = norm_level(re.sub(r"(?i)level\s*", "", m.group(1))), ref[:m.start()]
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

    if kind == "building":
        d.name = step.name or d.name
        d.description = step.description or d.description
    elif kind == "level":
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
    elif kind == "layout":
        lid = _default_level(d, step.level)
        if d.level(lid or "") is None:
            raise StepError(f"layout: unknown level '{step.level}' (levels: {', '.join(x.id for x in d.levels) or 'none yet'})")
        old = {r.name.lower(): r for r in d.rooms if r.level == lid}
        d.rooms = [r for r in d.rooms if r.level != lid]
        for spec in step.rooms or []:
            _apply_room(d, Step(step="room", level=lid, **{k: v for k, v in spec.items() if k in Step.model_fields and k not in ('level', 'step')}), keep=old)
        _drop_dangling(d)                     # rooms that disappeared take their doors, windows and stairs with them
    elif kind == "door":
        room = _room_ref(d, step.room, "door")
        to = step.to or "outside"
        if to != "outside":
            other = _room_ref(d, to, "door", prefer_level=room.level)
            if other.level != room.level:
                raise StepError(f"door: '{room.name}' and '{other.name}' are on different levels")
            to = other.id
        did = step.id or _unique_id({x.id for x in d.doors}, f"door-{room.id}-{to}")
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
        wid = step.id or _unique_id({x.id for x in d.windows}, f"win-{room.id}-{side}")
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
        sid = step.id if isinstance(step.id, str) and step.id else f"stair-{room.id}"
        data: dict = dict(id=sid, room=room.id, side=side, to_level=norm_level(step.to_level))
        if step.width:
            data["width"] = step.width
        d.stairs = [x for x in d.stairs if x.id != sid and x.room != room.id] + [Stair(**data)]
    elif kind == "roof":
        if step.kind not in (None, "flat"):
            d.notes.append(f"roof '{step.kind}' is not supported yet; a flat roof was used")
    elif kind == "material":
        if step.material not in ("masonry", "concrete", "timber", "plaster"):
            raise StepError("material must be masonry, concrete, timber or plaster")
        d.wall_material = step.material  # type: ignore[assignment]
    elif kind == "remove":
        _remove(d, step.id)
    elif kind == "note":
        d.notes.append(step.text or "")
    return d


def _drop_dangling(d: Design) -> None:
    ids = {r.id for r in d.rooms}
    d.doors = [x for x in d.doors if x.room in ids and (x.to == "outside" or x.to in ids)]
    d.windows = [x for x in d.windows if x.room in ids]
    d.stairs = [x for x in d.stairs if x.room in ids]


def _default_level(d: Design, level: str | int | None) -> str | None:
    """Small models often leave the level out. With levels present, the newest one is the obvious meaning."""
    return norm_level(level) or (d.levels[-1].id if d.levels else None)


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
    rect = norm_rect(step.rect)
    existing = next((r for r in d.rooms if r.id == step.id or (r.level == lid and r.name.lower() == name.lower())), None)
    if existing is None and keep:
        existing = keep.get(name.lower())
    if rect is None and existing is None:
        raise StepError(f"room '{name}': 'rect' [x, y, width, depth] in metres is required for a new room")
    rid = existing.id if existing else _unique_id({r.id for r in d.rooms}, slug(name))
    room = Room(id=rid, name=name, level=lid, kind=step.kind or (existing.kind if existing else "other"),
                rect=rect or existing.rect, roofed=step.roofed if step.roofed is not None else (existing.roofed if existing else True))
    _check_overlap(d, room)
    d.rooms = [r for r in d.rooms if r.id != rid] + [room]


def _remove(d: Design, item_id: str | None) -> None:
    if not item_id:
        raise StepError("remove: 'id' is required")
    if d.room(item_id):
        d.rooms = [r for r in d.rooms if r.id != item_id]
        d.doors = [x for x in d.doors if x.room != item_id and x.to != item_id]
        d.windows = [x for x in d.windows if x.room != item_id]
        d.stairs = [x for x in d.stairs if x.room != item_id]
    elif d.level(item_id):
        gone = {r.id for r in d.rooms if r.level == item_id}
        d.rooms = [r for r in d.rooms if r.level != item_id]
        d.doors = [x for x in d.doors if x.room not in gone and x.to not in gone]
        d.windows = [x for x in d.windows if x.room not in gone]
        d.stairs = [x for x in d.stairs if x.room not in gone]
        d.levels = [x for x in d.levels if x.id != item_id]
    elif any(x.id == item_id for x in d.doors):
        d.doors = [x for x in d.doors if x.id != item_id]
    elif any(x.id == item_id for x in d.windows):
        d.windows = [x for x in d.windows if x.id != item_id]
    elif any(x.id == item_id for x in d.stairs):
        d.stairs = [x for x in d.stairs if x.id != item_id]
    else:
        raise StepError(f"remove: nothing with id '{item_id}'")
