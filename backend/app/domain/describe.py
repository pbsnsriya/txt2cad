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
            finish = (f" floor={r.floor}" if r.floor else "") + (f" walls={r.walls}" if r.walls else "") + ("" if r.roofed else " open to the sky")
            lines.append(f"  room {r.id} '{r.name}' kind={r.kind} rect=[{x},{y},{w},{d}] area={w * d:.1f} m2{finish} exterior sides: {ext}; touches: {', '.join(near) or '-'}")
    lines += [f"DOOR {x.id}: {x.room} -> {x.to}" + (f" side {x.side}" if x.side else "") for x in design.doors]
    lines += [f"WINDOW {x.id}: {x.room} side {x.side}" for x in design.windows]
    lines += [f"FURNITURE {f.id}: {f.kind} {f.w:g} x {f.d:g} x {f.h:g} m in {f.room}, centre ({f.x:g}, {f.y:g}), back to the {SIDE_WORDS[{0: 'S', 90: 'E', 180: 'N', 270: 'W'}[f.rot]]}"
              + (f", colour {f.colour}" if f.colour else "") for f in design.furniture]
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
    for f in design.furniture:
        if f.id == element_id:
            return f"the {f.kind.replace('_', ' ')} {f.id} in {_name(design, f.room)}, {f.w:g} x {f.d:g} m, centre ({f.x:g}, {f.y:g})"
    if element_id.startswith("covering."):
        room = design.room(element_id.rsplit(".", 1)[1])
        if room is not None and element_id.startswith("covering.floor."):
            return f"the floor finish ({room.floor}) of {_name(design, room.id)}"
        if room is not None:
            return f"the wall finish ({room.walls}) of {_name(design, room.id)}"
    for r in design.rooms:
        if element_id == f"room.{r.level}.{r.id}":
            return f"the room {r.id} '{r.name}' ({r.kind}) on {r.level}, rect {list(r.rect)}" + (f", floor {r.floor}" if r.floor else "") + (f", walls {r.walls}" if r.walls else "")
    for p in wall_pieces(design):
        if p.id == element_id:
            if p.other is None:
                return f"the {SIDE_WORDS[p.side]} exterior wall {p.id} of {_name(design, p.room)} on {p.level}"
            doors = [x.id for x in design.doors if {x.room, x.to} == {p.room, p.other}]
            return (f"the partition wall {p.id} between {_name(design, p.room)} and {_name(design, p.other)} on {p.level}, {p.length:.1f} m long"
                    + (f"; it holds the door {', '.join(doors)}" if doors else "")
                    + f". To take it away or open it up, send ONE door step: room \"{p.room}\", to \"{p.other}\", kind \"opening\", width {max(p.length - 0.1, 0.9):.1f}")
    if element_id.startswith("floor."):
        return f"the floor slab {element_id} of {element_id.split('.')[1]}"
    if element_id.startswith("roof."):
        return f"the roof {element_id} over {element_id.split('.')[1]}"
    return None


MAX_LISTED = 30


def _rooms_in(design: Design, element_id: str, pieces) -> set[str]:
    """The rooms an element belongs to or separates."""
    for d in design.doors:
        if d.id == element_id:
            return {d.room} | ({d.to} if d.to != "outside" else set())
    for w in design.windows:
        if w.id == element_id:
            return {w.room}
    for s in design.stairs:
        if s.id == element_id:
            return {s.room}
    for f in design.furniture:
        if f.id == element_id:
            return {f.room}
    if element_id.startswith("covering."):
        return {element_id.rsplit(".", 1)[1]} if design.room(element_id.rsplit(".", 1)[1]) else set()
    for r in design.rooms:
        if element_id == f"room.{r.level}.{r.id}":
            return {r.id}
    for p in pieces:
        if p.id == element_id:
            return {p.room} | ({p.other} if p.other else set())
    return set()


def describe_selection(design: Design, element_ids: list[str], limit: int = MAX_LISTED) -> str | None:
    """Everything picked in the viewer, as one block for the model: each part in words, then the rooms they belong to. None when no id is known."""
    try:
        pieces = wall_pieces(design)
    except DesignError:
        pieces = []
    known: list[tuple[str, str]] = []
    for eid in dict.fromkeys(element_ids):
        text = describe_focus(design, eid)
        if text:
            known.append((eid, text))
    if not known:
        return None
    n = len(known)
    lines = [f"SELECTED IN THE VIEWER: {n} element{'s' if n != 1 else ''}. When the request says this, these, it, them, here or \"the selected\", "
             "it means exactly these parts; change nothing else."]
    lines += [f"- {text}" for _, text in known[:limit]]
    if n > limit:
        lines.append(f"- ...and {n - limit} more")
    involved: list[str] = []
    for eid, _ in known:
        for rid in sorted(_rooms_in(design, eid, pieces)):
            if rid not in involved:
                involved.append(rid)
    if involved:
        lines.append("ROOMS INVOLVED: " + ", ".join(f"{rid} '{design.room(rid).name}'" for rid in involved if design.room(rid)))
    return "\n".join(lines)


def _name(design: Design, room_id: str) -> str:
    r = design.room(room_id)
    return f"{r.name} ({r.id})" if r else room_id
