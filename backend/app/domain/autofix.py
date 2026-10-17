"""The finishing touches a building always needs, added by code when the model leaves them out: doors so every room can be reached, a window
in every room that needs daylight, and a stair up to each storey. Each addition is checked by deriving the design; one that does not fit is skipped.

This is not guessing at what the person wanted. These are the things `checks.completeness` asks for, and the model was only ever asked for them again and again.
"""

from __future__ import annotations

from typing import Any

from . import checks
from .checks import NO_WINDOW_NEEDED
from .derive import DesignError, derive, exterior_sides, wall_pieces
from .design import Design, Door, Stair, Window
from .reflow import CannotReflow, reflow
from .steps import Step, StepError, apply_step

MIN_DOOR_WALL_M = 1.2
STAIR_ROOM_ORDER = ("hall", "living", "dining", "office", "kitchen", "bedroom", "utility", "storage", "other")


def _builds(design: Design) -> bool:
    try:
        derive(design)
        return True
    except DesignError:
        return False


def _unique(existing: set[str], base: str) -> str:
    out, n = base, 2
    while out in existing:
        out, n = f"{base}-{n}", n + 1
    return out


def complete(design: Design) -> tuple[Design, list[str]]:
    """The design with what was missing added, and a sentence for each addition. Never makes a design that builds into one that does not."""
    d = design.model_copy(deep=True)
    notes: list[str] = []
    if not d.rooms or not _builds(d):
        return design, notes
    for step in (_stairs, _link_rooms, _windows):
        d = step(d, notes)
    return d, notes


def _stairs(d: Design, notes: list[str]) -> Design:
    for i, lv in enumerate(d.levels[1:], 1):
        below = d.levels[i - 1].id
        if any((d.room(s.room) is not None and d.room(s.room).level == below) for s in d.stairs):  # type: ignore[union-attr]
            continue
        rooms = sorted([r for r in d.rooms if r.level == below], key=lambda r: (STAIR_ROOM_ORDER.index(r.kind) if r.kind in STAIR_ROOM_ORDER else 99, -r.rect[2] * r.rect[3]))
        done = False
        for r in rooms:
            for side in ("W", "E", "S", "N"):
                trial = d.model_copy(deep=True)
                trial.stairs = [*trial.stairs, Stair(id=_unique({s.id for s in trial.stairs}, f"stair.{r.id}"), room=r.id, side=side)]  # type: ignore[arg-type]
                if _builds(trial):
                    d, done = trial, True
                    notes.append(f"added a stair up to {lv.name or lv.id}, in {r.name} along the {side} wall")
                    break
            if done:
                break
    return d


def _groups(d: Design, level: str) -> list[set[str]]:
    ids = [r.id for r in d.rooms if r.level == level]
    parent = {i: i for i in ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for door in d.doors:
        if door.room in parent and door.to in parent:
            parent[find(door.room)] = find(door.to)
    groups: dict[str, set[str]] = {}
    for i in ids:
        groups.setdefault(find(i), set()).add(i)
    return list(groups.values())


def _link_rooms(d: Design, notes: list[str]) -> Design:
    for lv in d.levels:
        for _ in range(40):
            groups = _groups(d, lv.id)
            if len(groups) <= 1:
                break
            owner = {rid: n for n, g in enumerate(groups) for rid in g}
            kinds = {r.id: r.kind for r in d.rooms}
            candidates = [p for p in wall_pieces(d) if p.level == lv.id and p.other and owner.get(p.room) != owner.get(p.other) and p.length >= MIN_DOOR_WALL_M]
            candidates.sort(key=lambda p: (0 if "hall" in (kinds[p.room], kinds[p.other]) else 1, -p.length))
            for p in candidates:
                trial = d.model_copy(deep=True)
                did = _unique({x.id for x in trial.doors}, f"door.{p.room}.{p.other}")
                trial.doors = [*trial.doors, Door(id=did, room=p.room, to=p.other, at=0.5)]  # type: ignore[arg-type]
                if _builds(trial):
                    d = trial
                    a, b = d.room(p.room), d.room(p.other)  # type: ignore[arg-type]
                    notes.append(f"added a door between {a.name} and {b.name}")  # type: ignore[union-attr]
                    break
            else:
                break
    return d


def _windows(d: Design, notes: list[str]) -> Design:
    for r in list(d.rooms):
        if r.kind in NO_WINDOW_NEEDED or not r.roofed or any(w.room == r.id for w in d.windows):
            continue
        pieces = sorted([p for p in wall_pieces(d) if p.room == r.id and p.other is None], key=lambda p: -p.length)
        for p in pieces:
            if p.length < 1.0:
                continue
            trial = d.model_copy(deep=True)
            wid = _unique({w.id for w in trial.windows}, f"window.{r.id}.{p.side}")
            trial.windows = [*trial.windows, Window(id=wid, room=r.id, side=p.side, at=0.5)]
            if _builds(trial):
                d = trial
                notes.append(f"added a window to {r.name} on its {p.side} side")
                break
    return d


# --- a plan the model could not draw: lay the ground floor out in code --------------------------------------------------------------------------------------
def _wanted_shape(item: dict[str, Any]) -> str | None:
    kw = f"{item.get('params', {}).get('keyword', '')} {item.get('text', '')}".lower().replace("-", " ")
    if item.get("kind") != "feature":
        return None
    if any(w in kw for w in ("courtyard", "patio", "atrium")):
        return "courtyard"
    if "l shape" in kw:
        return "L"
    if "u shape" in kw:
        return "U"
    return None


def _met(design: Design, checklist: list[dict[str, Any]]) -> int:
    return sum(1 for r in checks.check(design, checklist) if r["status"] == "met")


def _put_back(new: Design, old: Design, level: str) -> Design:
    """The doors and windows of the old plan on `level` that still have a wall to sit in."""
    on_level = {r.id for r in old.rooms if r.level == level}
    d = new
    for door in [x for x in old.doors if x.room in on_level]:
        for candidate in (door, door.model_copy(update={"side": None})):
            trial = d.model_copy(deep=True)
            trial.doors = [*trial.doors, candidate]
            if _builds(trial):
                d = trial
                break
    for win in [w for w in old.windows if w.room in on_level]:
        trial = d.model_copy(deep=True)
        trial.windows = [*trial.windows, win]
        if _builds(trial):
            d = trial
    return d


def _relaid(design: Design, level: str, shape: str) -> Design | None:
    try:
        new = reflow(design, level, shape)
    except CannotReflow:
        return None
    if not _builds(new):
        return None
    new = _put_back(new, design, level)
    if any(f.room in {r.id for r in design.rooms if r.level == level} for f in design.furniture):       # it had furniture: furnish the new plan the same way
        try:
            new = apply_step(new, Step(step="furnish", room="all", level=level))
        except StepError:
            pass
    return new if _builds(new) else None


def _enclosed(design: Design) -> list[str]:
    outside = exterior_sides(design)
    return [r.id for r in design.rooms if r.roofed and r.kind not in NO_WINDOW_NEEDED and not outside.get(r.id) and not any(w.room == r.id for w in design.windows)]


SHAPE_SENTENCE = {"L": "an L", "U": "a U", "courtyard": "a ring of rooms around an open courtyard"}


def reshape(design: Design, checklist: list[dict[str, Any]]) -> tuple[Design, list[str]]:
    """For a new building only: if the request asked for an L, a U or a courtyard and the plan is not one, lay the ground floor out as that; and if a room that needs
    daylight has no outside wall, put the storey's rooms in two rows so each one has. Kept only when the building still builds and no requirement that was met is lost."""
    if not design.rooms or not design.levels or not _builds(design):
        return design, []
    notes: list[str] = []
    ground = next((lv.id for lv in design.levels if any(r.level == lv.id for r in design.rooms)), None)
    if ground is None:
        return design, notes
    before = _met(design, checklist)
    for item in checklist:
        shape = _wanted_shape(item)
        if shape is None or checks.check(design, [item])[0]["status"] != "unmet":
            continue
        new = _relaid(design, ground, shape)
        if new is not None and checks.check(new, [item])[0]["status"] == "met" and _met(new, checklist) >= before:
            design, before = new, _met(new, checklist)
            notes.append(f"laid the {design.level(ground).name or ground} out again as {SHAPE_SENTENCE[shape]}, because the plan was not one")  # type: ignore[union-attr]
    shaped = any(_wanted_shape(i) for i in checklist)
    for lv in design.levels:
        if shaped and lv.id == ground:
            continue
        enclosed = _enclosed(design)
        if not any(r.id in enclosed and r.level == lv.id for r in design.rooms):
            continue
        new = _relaid(design, lv.id, "rows")
        if new is not None and not any(r.level == lv.id and r.id in _enclosed(new) for r in new.rooms) and _met(new, checklist) >= before:
            design, before = new, _met(new, checklist)
            notes.append(f"laid {lv.name or lv.id} out in two rows, because some rooms had no outside wall and so no window")
    return design, notes


# --- pieces asked for by name ---------------------------------------------------------------------------------------------------------------------------------
_HOME_FOR = {"bed_double": ("bedroom", "living", "other"), "bed_single": ("bedroom", "living", "other"), "sofa": ("living", "other"), "armchair": ("living", "bedroom", "other"),
             "coffee_table": ("living",), "dining_table": ("dining", "living", "kitchen"), "wardrobe": ("bedroom", "living"), "desk": ("office", "bedroom", "living"),
             "bookshelf": ("living", "office", "bedroom"), "tv_unit": ("living", "bedroom"), "kitchen_counter": ("kitchen", "living", "dining"),
             "kitchen_island": ("kitchen", "living"), "fridge": ("kitchen", "living"), "cooker": ("kitchen", "living"), "washing_machine": ("utility", "kitchen", "bathroom"),
             "plant": ("living", "hall", "bedroom"), "floor_lamp": ("living", "bedroom"), "bench": ("hall", "living"), "dresser": ("bedroom", "living")}


def furnish_wanted(design: Design, checklist: list[dict[str, Any]]) -> tuple[Design, list[str]]:
    """Pieces the request named that the model did not place: furnish the rooms the usual way, then put any still missing against a free wall."""
    wanted = [i for i in checklist if i.get("kind") == "furniture" and i.get("params", {}).get("keyword")]
    if not wanted or not design.rooms or not _builds(design):
        return design, []
    notes: list[str] = []
    if not any(checks.check(design, [i])[0]["status"] == "unmet" for i in wanted):
        return design, notes
    trial = design.model_copy(deep=True)
    try:
        trial = apply_step(trial, Step(step="furnish", room="all"))
        if _builds(trial):
            design = trial
            notes.append("furnished the rooms in the usual way, because the request named pieces of furniture")
    except StepError:
        pass
    for item in wanted:
        kw = str(item["params"]["keyword"])
        kind = "bed_double" if kw == "bed" else kw
        homes = _HOME_FOR.get(kind, ("living", "other"))
        rooms = sorted([r for r in design.rooms if r.kind in homes and r.roofed], key=lambda r: (homes.index(r.kind), -r.rect[2] * r.rect[3]))
        for _ in range(int(item["params"].get("count", 1))):
            if checks.check(design, [item])[0]["status"] != "unmet":
                break
            placed = False
            for room in rooms:
                for side in ("N", "S", "E", "W", "NE", "NW", "SE", "SW"):
                    trial = design.model_copy(deep=True)
                    try:
                        trial = apply_step(trial, Step(step="furniture", room=room.id, kind=kind, side=side))
                    except (StepError, ValueError):
                        continue
                    if _builds(trial):
                        design, placed = trial, True
                        notes.append(f"placed a {kind.replace('_', ' ')} in {room.name}, because the request named one")
                        break
                if placed:
                    break
            if not placed:
                break
    return design, notes


# --- an edit leaves alone what it was not about -------------------------------------------------------------------------------------------------------------
def keep_untouched(design: Design, base: Design, prompt: str) -> tuple[Design, list[str]]:
    """After an edit, a room the request did not mention that moved, changed size or went is put back as it was, if it fits there without touching another room."""
    from shapely.geometry import box

    words = set(prompt.lower().replace("-", " ").replace(",", " ").replace(".", " ").split())
    notes: list[str] = []
    d = design
    for old in base.rooms:
        mentioned = {w.rstrip("s") for w in words}
        if {w.rstrip("s") for w in old.name.lower().split()} & mentioned or old.kind.rstrip("s") in mentioned or old.level not in {lv.id for lv in d.levels}:
            continue
        now = d.room(old.id)
        if now is not None and tuple(now.rect) == tuple(old.rect):
            continue
        shape = box(old.rect[0], old.rect[1], old.rect[0] + old.rect[2], old.rect[1] + old.rect[3])
        if any(r.id != old.id and r.level == old.level and shape.intersection(box(r.rect[0], r.rect[1], r.rect[0] + r.rect[2], r.rect[1] + r.rect[3])).area > 1e-6 for r in d.rooms):
            continue
        trial = d.model_copy(deep=True)
        trial.rooms = [old.model_copy(deep=True) if r.id == old.id else r for r in trial.rooms] if now is not None else [*trial.rooms, old.model_copy(deep=True)]
        if not _builds(trial):
            continue
        trial = _put_back(trial, base.model_copy(update={"doors": [x for x in base.doors if x.room == old.id or x.to == old.id]}), old.level) if now is None else trial
        d = trial if _builds(trial) else d
        notes.append(f"kept {old.name} as it was, because the request was not about it")
    return d, notes
