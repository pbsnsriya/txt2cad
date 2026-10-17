"""The finishing touches a building always needs, added by code when the model leaves them out: doors so every room can be reached, a window
in every room that needs daylight, and a stair up to each storey. Each addition is checked by deriving the design; one that does not fit is skipped.

This is not guessing at what the person wanted. These are the things `checks.completeness` asks for, and the model was only ever asked for them again and again.
"""

from __future__ import annotations

from .checks import NO_WINDOW_NEEDED
from .derive import DesignError, derive, exterior_sides, wall_pieces
from .design import Design, Door, Stair, Window

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
