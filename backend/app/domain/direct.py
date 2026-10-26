"""Changing sizes by hand, with no model: set a room to a new width and depth, or the whole building to a new footprint.

The plan is stretched along a line through the room (or scaled, for the building), so rooms that touch still touch. Doors, windows, stairs and furniture that no longer fit are dropped,
and the finishing pass (doors, windows, stairs) and the furnishing of rooms that had furniture run again, exactly as after a run. Room ids stay, so IFC GlobalIds stay.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import autofix, checks
from .derive import DesignError, derive, prune_invalid_openings
from .design import Design
from .resize import MIN_SIDE, scale, stretch
from .steps import Step, StepError, apply_step

MAX_SIDE = 40.0
EPS = 1e-6


class SizeError(ValueError):
    """The request cannot be done; the message says why, in words for the person."""


@dataclass
class RoomSize:
    room: str
    width: float | None = None
    depth: float | None = None


def _check_side(value: float | None, what: str) -> None:
    if value is not None and not (MIN_SIDE <= value <= MAX_SIDE):
        raise SizeError(f"{what} must be between {MIN_SIDE:g} and {MAX_SIDE:g} m")


def _finish(before: Design, after: Design, furnished: set[str]) -> tuple[Design, list[str]]:
    """Put right what the new sizes broke, and say what changed."""
    notes: list[str] = []
    changed = {r.id for r in after.rooms if (b := before.room(r.id)) is None or tuple(b.rect) != tuple(r.rect)}
    after = after.model_copy(update={"furniture": [f for f in after.furniture if f.room not in changed]})      # a moved or resized room's furniture no longer fits
    try:
        after, dropped = prune_invalid_openings(after)
    except DesignError as exc:
        raise SizeError(f"that size does not fit the rest of the plan: {exc}") from exc
    notes += [f"{d}" for d in dropped if d.startswith(("door", "window", "stair"))]
    after, completed = autofix.complete(after)
    notes += completed
    for rid in sorted(changed & furnished):
        try:
            after = apply_step(after, Step(step="furnish", room=rid))
        except StepError:
            pass
    try:
        derive(after)
    except DesignError as exc:
        raise SizeError(f"that size does not fit the rest of the plan: {exc}") from exc
    return after, notes


def resize_rooms(design: Design, edits: list[RoomSize]) -> tuple[Design, list[str]]:
    """Each room gets the width (east-west) and depth (north-south) given; the rooms beside it move or grow to make way."""
    if not edits:
        raise SizeError("no size was given")
    furnished = {f.room for f in design.furniture}
    cur: Design | None = design
    said: list[str] = []
    for e in edits:
        _check_side(e.width, "a width")
        _check_side(e.depth, "a depth")
        room = cur.room(e.room) if cur else None
        if room is None:
            raise SizeError(f"there is no room '{e.room}' in this version")
        x, y, w, h = cur.room(e.room).rect                                                                           # type: ignore[union-attr]
        if e.width is not None and abs(e.width - w) > EPS:
            cur = stretch(cur, "x", x + w / 2, e.width - w)                                                              # type: ignore[arg-type]
            if cur is None:
                raise SizeError(f"{room.name} cannot be {e.width:g} m wide: a room beside it would get narrower than {MIN_SIDE:g} m")
            said.append(f"{room.name} width {w:g} to {e.width:g} m")
        x, y, w, h = cur.room(e.room).rect                                                                           # type: ignore[union-attr]
        if e.depth is not None and abs(e.depth - h) > EPS:
            cur = stretch(cur, "y", y + h / 2, e.depth - h)
            if cur is None:
                raise SizeError(f"{room.name} cannot be {e.depth:g} m deep: a room beside it would get narrower than {MIN_SIDE:g} m")
            said.append(f"{room.name} depth {h:g} to {e.depth:g} m")
    if not said:
        raise SizeError("those are the sizes already")
    out, notes = _finish(design, cur, furnished)                                                                      # type: ignore[arg-type]
    return out, [f"set {s}" for s in said] + notes


def resize_building(design: Design, width: float | None, depth: float | None) -> tuple[Design, list[str]]:
    """The overall footprint of the ground floor, stretched evenly: every room keeps its proportions."""
    _check_side(width, "the building width")
    _check_side(depth, "the building depth")
    got = checks._footprint(design)
    if got is None:
        raise SizeError("there is nothing to resize yet")
    sx = (width / got[0]) if width is not None else 1.0
    sy = (depth / got[1]) if depth is not None else 1.0
    if abs(sx - 1) < EPS and abs(sy - 1) < EPS:
        raise SizeError("that is the size already")
    if not (0.4 <= sx <= 3.0 and 0.4 <= sy <= 3.0):
        raise SizeError("the building can be made at most about 2.5 times larger or 60% smaller in one go")
    scaled = scale(design, sx, sy)
    if scaled is None:
        raise SizeError(f"at that size a room would get narrower than {MIN_SIDE:g} m")
    furnished = {f.room for f in design.furniture}
    out, notes = _finish(design, scaled, furnished)
    now = checks._footprint(out) or got
    return out, [f"set the building from {got[0]:g} x {got[1]:g} m to about {now[0]:g} x {now[1]:g} m"] + notes
