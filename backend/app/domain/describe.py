"""The design as compact text for the model: what it sees when it edits. Includes derived facts it cannot compute itself."""

from __future__ import annotations

from .derive import DesignError, exterior_sides, wall_pieces
from .design import Design


def describe(design: Design) -> str:
    if not design.levels:
        return "(empty design)"
    try:
        sides = exterior_sides(design)
        pieces = wall_pieces(design)
    except DesignError:
        sides, pieces = {}, []
    lines = [f"BUILDING: {design.name}"]
    for lv in design.levels:
        lines.append(f"LEVEL {lv.id} '{lv.name}' height {lv.height} m, floor at {design.elevation(lv.id):.1f} m")
        for r in (r for r in design.rooms if r.level == lv.id):
            x, y, w, d = r.rect
            near = sorted({(p.other if p.room == r.id else p.room) for p in pieces if r.id in (p.room, p.other) and p.other})
            ext = ",".join(sorted(sides.get(r.id, []))) or "-"
            lines.append(f"  room {r.id} '{r.name}' kind={r.kind} rect=[{x},{y},{w},{d}] area={w * d:.1f} m2 exterior sides: {ext}; touches: {', '.join(near) or '-'}")
    lines += [f"DOOR {x.id}: {x.room} -> {x.to}" + (f" side {x.side}" if x.side else "") for x in design.doors]
    lines += [f"WINDOW {x.id}: {x.room} side {x.side}" for x in design.windows]
    lines += [f"STAIR {x.id}: in {x.room} along the {x.side} wall, up to {x.to_level or 'the next level'}" for x in design.stairs]
    return "\n".join(lines)


SIDE_WORDS = {"N": "north", "S": "south", "E": "east", "W": "west"}


def describe_focus(design: Design, element_id: str) -> str | None:
    """What the person clicked in the viewer, in words the model can act on. None if the id is not in this design."""
    for d in design.doors:
        if d.id == element_id:
            where = "to the outside" if d.to == "outside" else f"between {_name(design, d.room)} and {_name(design, d.to)}"
            return f"the door {d.id} {where}"
    for w in design.windows:
        if w.id == element_id:
            return f"the window {w.id} on the {SIDE_WORDS[w.side]} wall of {_name(design, w.room)}"
    for st in design.stairs:
        if st.id == element_id:
            return f"the stair {st.id} in {_name(design, st.room)}"
    for r in design.rooms:
        if element_id == f"room.{r.level}.{r.id}":
            return f"the room {r.id} '{r.name}' ({r.kind}) on {r.level}, rect {list(r.rect)}"
    for p in wall_pieces(design):
        if p.id == element_id:
            if p.other is None:
                return f"the {SIDE_WORDS[p.side]} exterior wall {p.id} of {_name(design, p.room)} on {p.level}"
            return f"the partition wall {p.id} between {_name(design, p.room)} and {_name(design, p.other)} on {p.level}"
    if element_id.startswith("floor."):
        return f"the floor slab {element_id} of {element_id.split('.')[1]}"
    if element_id.startswith("roof."):
        return f"the roof {element_id} over {element_id.split('.')[1]}"
    return None


def _name(design: Design, room_id: str) -> str:
    r = design.room(room_id)
    return f"{r.name} ({r.id})" if r else room_id
