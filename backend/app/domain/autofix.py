"""The finishing touches a building always needs, added by code when the model leaves them out: doors so every room can be reached, a window
in every room that needs daylight, and a stair up to each storey. Each addition is checked by deriving the design; one that does not fit is skipped.

This is not guessing at what the person wanted. These are the things `checks.completeness` asks for, and the model was only ever asked for them again and again.
"""

from __future__ import annotations

import re
from typing import Any

from . import checks
from .checks import NO_WINDOW_NEEDED
from .derive import DesignError, derive, exterior_sides, prune_blocking_furniture, prune_invalid_openings, wall_pieces
from .design import Design, Door, Stair, Window
from .reflow import CannotReflow, reflow
from .resize import DEFAULT_SIZES, LABELS, free_spot, free_spots, scale, stretch
from .steps import Step, StepError, apply_step, tidy_name

MIN_DOOR_WALL_M = 1.2
STAIR_ROOM_ORDER = ("hall", "living", "dining", "office", "kitchen", "bedroom", "utility", "storage", "other")


def _builds(design: Design) -> bool:
    try:
        derive(design)
        return True
    except DesignError:
        return False


def _try(design: Design) -> Design | None:
    """The design if it builds; a piece of furniture that stands where a new door, window or stair goes gives way, as it does for a door the person asks for."""
    try:
        return prune_blocking_furniture(design)[0]
    except DesignError:
        return None


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
                fixed = _try(trial)
                if fixed is not None:
                    d, done = fixed, True
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
                fixed = _try(trial)
                if fixed is not None:
                    d = fixed
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
        done = False
        for p in pieces:
            if p.length < 0.8:
                continue
            for width in (None, 0.9, 0.6):                       # a short outside wall takes a narrower window
                trial = d.model_copy(deep=True)
                wid = _unique({w.id for w in trial.windows}, f"window.{r.id}.{p.side}")
                trial.windows = [*trial.windows, Window(id=wid, room=r.id, side=p.side, at=0.5, **({"width": width} if width else {}))]
                fixed = _try(trial)
                if fixed is not None:
                    d, done = fixed, True
                    notes.append(f"added a window to {r.name} on its {p.side} side")
                    break
            if done:
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


def _stated_sizes(design: Design, checklist: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    """Rooms whose size the request stated and that have it now: a new layout keeps them as they are."""
    out: dict[str, tuple[float, float]] = {}
    for item in checklist:
        p = item.get("params", {})
        if item.get("kind") == "dimension" and p.get("keyword") not in (None, "building") and checks.check(design, [item])[0]["status"] == "met":
            for r in checks._matching_rooms(design, str(p["keyword"]), None):
                out[r.id] = (r.rect[2], r.rect[3])
    return out


def _relaid(design: Design, level: str, shape: str, court: bool = False, fixed: dict[str, tuple[float, float]] | None = None) -> Design | None:
    try:
        new = reflow(design, level, shape, court_in_notch=court, fixed=fixed)
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
    return [r.id for r in design.rooms if r.roofed and r.kind not in NO_WINDOW_NEEDED and not outside.get(r.id)]


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
    wanted = {_wanted_shape(i) for i in checklist} - {None}
    for item in checklist:
        shape = _wanted_shape(item)
        if shape is None or checks.check(design, [item])[0]["status"] != "unmet":
            continue
        around = shape == "courtyard" and "U" in wanted                 # "a U-shaped house around a courtyard": the gap of the U is the courtyard
        new = _relaid(design, ground, "U" if around else shape, court=around or (shape == "U" and "courtyard" in wanted))
        new = fit_sizes(new, checklist)[0] if new is not None else None
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
        new = _relaid(design, lv.id, "rows", fixed=_stated_sizes(design, checklist))
        new = fit_sizes(new, checklist)[0] if new is not None else None
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


def _place(design: Design, room_id: str, kind: str) -> Design | None:
    for side in ("N", "S", "E", "W", "NE", "NW", "SE", "SW", "center"):
        try:
            trial = apply_step(design, Step(step="furniture", room=room_id, kind=kind, side=side))
        except (StepError, ValueError):
            continue
        fixed = _try(trial)
        new_ids = {f.id for f in trial.furniture} - {f.id for f in design.furniture}
        if fixed is not None and new_ids <= {f.id for f in fixed.furniture} and len(fixed.furniture) >= len(design.furniture):       # the piece itself was not what gave way
            return fixed
    return None


def furnish_wanted(design: Design, checklist: list[dict[str, Any]]) -> tuple[Design, list[str]]:
    """Pieces the request named that the model did not place: each goes in a fitting room first, then the rooms are furnished the usual way around them."""
    wanted = [i for i in checklist if i.get("kind") == "furniture" and i.get("params", {}).get("keyword")]
    if not wanted or not design.rooms or not _builds(design):
        return design, []
    notes: list[str] = []
    if not any(checks.check(design, [i])[0]["status"] == "unmet" for i in wanted):
        return design, notes
    for item in wanted:
        kw = str(item["params"]["keyword"])
        kind = "bed_double" if kw == "bed" else kw
        homes = _HOME_FOR.get(kind, ("living", "other"))
        rooms = sorted([r for r in design.rooms if r.kind in homes and r.roofed], key=lambda r: (homes.index(r.kind), -r.rect[2] * r.rect[3]))
        for _ in range(int(item["params"].get("count", 1))):
            if checks.check(design, [item])[0]["status"] != "unmet":
                break
            for room in rooms:
                fixed = _place(design, room.id, kind)
                if fixed is not None:
                    design = fixed
                    notes.append(f"placed a {kind.replace('_', ' ')} in {room.name}, because the request named one")
                    break
            else:
                break
    try:
        trial = apply_step(design, Step(step="furnish", room="all"))
        fixed = _try(trial)
        if fixed is not None:
            design = fixed
            notes.append("furnished the rooms in the usual way around them, because the request named pieces of furniture")
    except StepError:
        pass
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


# --- rooms and sizes the request stated that the model got wrong ------------------------------------------------------------------------------------------------
def _tidy(design: Design) -> Design | None:
    """The design with openings and furniture that no longer fit dropped, or None when it cannot be built at all."""
    try:
        return prune_invalid_openings(design)[0]
    except DesignError:
        return None


def _accept(new: Design | None, item: dict[str, Any], before: int, checklist: list[dict[str, Any]]) -> bool:
    return new is not None and checks.check(new, [item])[0]["status"] == "met" and _met(new, checklist) >= before


def _stretched_to(design: Design, got: tuple[float, float], want: tuple[float, float], item: dict[str, Any], before: int, checklist: list[dict[str, Any]]) -> Design | None:
    """The overall size made right by stretching the plan along a line through one room, trying each room in turn, so rooms with a stated size can stay as they are."""
    x0 = min(r.rect[0] for r in design.rooms)
    y0 = min(r.rect[1] for r in design.rooms)
    cur: Design | None = design
    for axis, have, need, low in (("x", got[0], want[0], x0), ("y", got[1], want[1], y0)):
        if abs(have - need) <= 1e-6 or cur is None:
            continue
        best: Design | None = None
        for r in sorted(cur.rooms, key=lambda r: -r.rect[2] * r.rect[3]):
            mid = (r.rect[0] + r.rect[2] / 2) if axis == "x" else (r.rect[1] + r.rect[3] / 2)
            trial = stretch(cur, axis, mid, need - have)
            trial = _tidy(trial) if trial is not None else None
            if trial is not None and _met(trial, checklist) >= _met(cur, checklist):
                best = trial
                break
        cur = best
    return cur if cur is not None and cur is not design and checks.check(cur, [item])[0]["status"] == "met" else None


def fit_sizes(design: Design, checklist: list[dict[str, Any]]) -> tuple[Design, list[str]]:
    """A stated room size or total area the plan misses is put right by stretching or scaling the plan, so rooms keep touching. Kept only when the stated thing is then
    met and nothing that was met is lost."""
    notes: list[str] = []
    for item in checklist:
        p = item.get("params", {})
        if item.get("kind") not in ("dimension", "area") or not design.rooms or checks.check(design, [item])[0]["status"] != "unmet":
            continue
        before = _met(design, checklist)
        new: Design | None = None
        if item["kind"] == "area" and p.get("keyword") == "building":
            built = sum(r.rect[2] * r.rect[3] for r in design.rooms)
            if built > 0:
                f = (float(p["area"]) / built) ** 0.5
                new = _tidy(scale(design, f, f)) if 0.5 <= f <= 1.6 and scale(design, f, f) is not None else None
                what = f"scaled the plan to about {float(p['area']):.0f} m2 in all"
        elif item["kind"] == "dimension" and p.get("keyword") == "building":
            got = checks._footprint(design)
            if got:
                W, D = float(p["width"]), float(p["depth"])
                straight = abs(got[0] - W) + abs(got[1] - D) <= abs(got[0] - D) + abs(got[1] - W)
                tx, ty = (W, D) if straight else (D, W)
                new = _stretched_to(design, got, (tx, ty), item, before, checklist)
                if new is None:
                    sx, sy = tx / got[0], ty / got[1]
                    scaled = scale(design, sx, sy) if 0.5 <= sx <= 1.8 and 0.5 <= sy <= 1.8 else None
                    new = _tidy(scaled) if scaled is not None else None
                what = f"fitted the plan to {W:g} x {D:g} m"
        elif item["kind"] == "dimension":
            rooms = checks._matching_rooms(design, str(p["keyword"]), None)
            if rooms:
                r = rooms[0]
                W, D = float(p["width"]), float(p["depth"])
                x, y, w, h = r.rect
                straight = abs(w - W) + abs(h - D) <= abs(w - D) + abs(h - W)
                tw, th = (W, D) if straight else (D, W)
                cur: Design | None = design
                if abs(tw - w) > 1e-6:
                    cur = stretch(cur, "x", x + w / 2, tw - w)
                if cur is not None and abs(th - h) > 1e-6:
                    cur = stretch(cur, "y", y + h / 2, th - h)
                new = _tidy(cur) if cur is not None else None
                what = f"made {r.name} {tw:g} x {th:g} m and moved what is beside it"
        if _accept(new, item, before, checklist):
            design = new  # type: ignore[assignment]
            notes.append(what)  # type: ignore[possibly-undefined]
    return design, notes


_ROOM_KINDS = tuple(DEFAULT_SIZES)


def _kind_of(keyword: str) -> str | None:
    words = checks._words(keyword) - checks._GENERIC
    return next((k for k in _ROOM_KINDS if k in words), None)


def _level_for(design: Design, kind: str, asked: Any) -> str | None:
    ids = [lv.id for lv in design.levels]
    if asked in ids:
        return asked
    with_rooms = [lv.id for lv in design.levels if any(r.level == lv.id for r in design.rooms)]
    if not with_rooms:
        return None
    if kind in ("bedroom", "bathroom") and len(with_rooms) > 1:
        return max(with_rooms, key=lambda i: (sum(r.kind == "bedroom" for r in design.rooms if r.level == i), ids.index(i)))      # where the bedrooms are
    return with_rooms[0]


def add_missing_rooms(design: Design, checklist: list[dict[str, Any]]) -> tuple[Design, list[str]]:
    """Rooms the request counted (two bathrooms, one bedroom) that the model never made: a room of the usual size is added beside the others. A new building only."""
    notes: list[str] = []
    for item in checklist:
        p = item.get("params", {})
        if item.get("kind") != "room" or not p.get("keyword") or checks.check(design, [item])[0]["status"] != "unmet":
            continue
        kind = _kind_of(str(p["keyword"]))
        if kind is None:                                      # a name with no kind of its own (workshop, classroom): plain "Other" rooms become it, then new ones are added
            design, more = _named_rooms(design, item)
            notes.extend(more)
            continue
        level = _level_for(design, kind, p.get("level"))
        if level is None:
            continue
        for _ in range(int(p.get("count", 1)) + 1):
            if checks.check(design, [item])[0]["status"] != "unmet":
                break
            spot = free_spot(design, level, DEFAULT_SIZES[kind])
            if spot is None:
                break
            taken = {r.name.lower() for r in design.rooms}
            n = 1
            name = LABELS[kind]
            while name.lower() in taken:
                n += 1
                name = f"{LABELS[kind]} {n}"
            try:
                trial = _tidy(apply_step(design, Step(step="room", level=level, name=name, kind=kind, rect=list(spot))))
            except (StepError, ValueError):
                break
            if trial is None:
                break
            design = trial
            notes.append(f"added a {name.lower()} on {design.level(level).name or level}, because the request asked for one and the model left it out")  # type: ignore[union-attr]
    return design, notes


def _named_rooms(design: Design, item: dict[str, Any]) -> tuple[Design, list[str]]:
    p = item["params"]
    keyword = str(p["keyword"]).strip()
    if not re.fullmatch(r"[a-z][a-z \-]{2,30}", keyword.lower()):
        return design, []
    text = str(item.get("text", "")).lower()
    label = tidy_name(f"{keyword} room" if f"{keyword.lower()} room" in text else keyword, "other")
    notes: list[str] = []
    level = _level_for(design, "other", p.get("level"))
    for _ in range(int(p.get("count", 1)) + 1):
        if checks.check(design, [item])[0]["status"] != "unmet" or level is None:
            break
        taken = {r.name.lower() for r in design.rooms}
        n, name = 1, label
        while name.lower() in taken:
            n += 1
            name = f"{label} {n}"
        generic = sorted([r for r in design.rooms if r.kind == "other" and re.fullmatch(r"other( \d+)?", r.name.lower())], key=lambda r: -r.rect[2] * r.rect[3])
        if generic:
            design = design.model_copy(deep=True)
            design.room(generic[0].id).name = name                                                  # type: ignore[union-attr]
            notes.append(f"renamed the plain room \"Other\" to {name}, because the request asked for one")
            continue
        spot = free_spot(design, level, (4.0, 4.0))
        try:
            trial = _tidy(apply_step(design, Step(step="room", level=level, name=name, kind="other", rect=list(spot)))) if spot else None
        except (StepError, ValueError):
            trial = None
        if trial is None:
            break
        design = trial
        notes.append(f"added a {name.lower()}, because the request asked for one and the model left it out")
    return design, notes


def keep_daylight(design: Design, base: Design) -> tuple[Design, list[str]]:
    """After an edit: a room added where it covers the last outside wall of another room is moved to a place that does not."""
    before = set(_enclosed(base))
    notes: list[str] = []
    for room in [r for r in design.rooms if base.room(r.id) is None]:
        if not (set(_enclosed(design)) - before):
            break
        for spot in free_spots(design, room.level, (room.rect[2], room.rect[3]), skip=room.id)[:60]:
            trial = design.model_copy(deep=True)
            trial.room(room.id).rect = spot                                                          # type: ignore[union-attr]
            trial = _tidy(trial)
            if trial is not None and not (set(_enclosed(trial)) - before):
                design = trial
                notes.append(f"moved the new {room.name} so that it does not cover the only outside wall of another room")
                break
    return design, notes
