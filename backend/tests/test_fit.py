"""Rooms and sizes the request stated, put right in code: missing rooms, a stated room size, a stated total area, a U around a courtyard."""

from app.domain import autofix, checks
from app.domain.checks import _outline_shape, _sides_with_rooms
from app.domain.derive import derive
from app.domain.design import Design
from app.domain.resize import free_spot, scale, stretch
from app.domain.sizes import extract
from app.domain.steps import Step, apply_step


def build(*steps):
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


L1 = {"step": "storey", "id": "L1", "name": "Ground floor", "height": 3}
L2 = {"step": "storey", "id": "L2", "name": "First floor", "height": 3}


def room(name, kind, rect, level="L1", **extra):
    return {"step": "room", "level": level, "name": name, "kind": kind, "rect": rect, **extra}


def want(**raw):
    return checks.normalise({"supported": True, **raw})


def status(d, item):
    return checks.check(d, [item])[0]["status"]


# --- missing rooms ---------------------------------------------------------------------------------------------------------------------------------
def test_a_missing_bedroom_is_added_beside_the_others():
    d = build(L1, room("Living Room", "living", [0, 0, 4.5, 4.5]), room("Kitchen", "kitchen", [4.5, 0, 3, 4.5]), room("Bathroom", "bathroom", [0, 4.5, 3, 2.5]))
    item = want(kind="room", keyword="bedroom", count=1, text="1 bedroom")
    out, notes = autofix.add_missing_rooms(d, [item])
    assert status(out, item) == "met" and notes and len(out.rooms) == 4
    derive(out)


def test_missing_bathrooms_go_upstairs_where_the_bedrooms_are():
    d = build(L1, L2, room("Garage", "garage", [0, 0, 3, 6]), room("Living", "living", [3, 0, 5, 6]),
              room("Hall", "hall", [0, 0, 8, 4], "L2"), room("Bedroom 1", "bedroom", [0, 4, 4, 3], "L2"), room("Bedroom 2", "bedroom", [4, 4, 4, 3], "L2"))
    item = want(kind="room", keyword="bathroom", count=2, text="two bathrooms")
    out, notes = autofix.add_missing_rooms(d, [item])
    assert status(out, item) == "met" and all(r.level == "L2" for r in out.rooms if r.kind == "bathroom")
    from shapely.geometry import box
    boxes = [box(r.rect[0], r.rect[1], r.rect[0] + r.rect[2], r.rect[1] + r.rect[3]) for r in out.rooms if r.level == "L2"]
    assert all(a.intersection(b).area < 1e-6 for i, a in enumerate(boxes) for b in boxes[i + 1:])


def test_nothing_is_added_when_the_rooms_are_there():
    d = build(L1, room("Bedroom", "bedroom", [0, 0, 4, 4]))
    item = want(kind="room", keyword="bedroom", count=1, text="x")
    assert autofix.add_missing_rooms(d, [item]) == (d, [])


def test_a_free_spot_touches_the_others_and_never_overlaps():
    d = build(L1, room("A", "living", [0, 0, 4, 4]), room("B", "kitchen", [4, 0, 4, 4]))
    x, y, w, h = free_spot(d, "L1", (3.0, 3.0))
    assert not (x < 8 and x + w > 0 and y < 4 and y + h > 0 and min(x + w, 8) - max(x, 0) > 1e-6 and min(y + h, 4) - max(y, 0) > 1e-6)


# --- stated sizes ----------------------------------------------------------------------------------------------------------------------------------
def three_rooms():
    return build(L1, room("Living", "living", [0, 0, 5, 4]), room("Kitchen", "kitchen", [5, 0, 4, 4]), room("Bedroom", "bedroom", [0, 4, 5, 4]),
                 room("Bathroom", "bathroom", [5, 4, 4, 4]))


def test_stretching_keeps_rooms_touching():
    d = stretch(three_rooms(), "x", 2.5, 1.0)
    assert d is not None
    living, kitchen, bedroom = (next(r for r in d.rooms if r.kind == k) for k in ("living", "kitchen", "bedroom"))
    assert living.rect[2] == 6 and bedroom.rect[2] == 6 and kitchen.rect[0] == 6
    derive(d)


def test_a_room_that_would_get_too_narrow_is_not_stretched():
    assert stretch(three_rooms(), "x", 2.5, -4.9) is None


def test_a_stated_room_size_is_made_true_and_the_neighbours_move():
    d = three_rooms()
    item = want(kind="dimension", keyword="living", width=6, depth=4, text="living room 6 m by 4 m")
    assert status(d, item) == "unmet"
    out, notes = autofix.fit_sizes(d, [item])
    assert status(out, item) == "met" and notes
    derive(out)


def test_a_stated_total_area_is_met_by_scaling():
    d = three_rooms()                                                         # 72 m2
    item = want(kind="area", keyword="building", area=54, text="about 54 square metres in all")
    out, notes = autofix.fit_sizes(d, [item])
    assert status(out, item) == "met" and notes
    derive(out)


def test_a_size_that_would_ruin_the_plan_is_left_alone():
    d = three_rooms()
    item = want(kind="area", keyword="building", area=500, text="about 500 square metres in all")
    assert autofix.fit_sizes(d, [item]) == (d, [])


def test_scale_keeps_shared_edges_shared():
    d = scale(three_rooms(), 0.83, 0.83)
    a, b = (next(r for r in d.rooms if r.kind == k) for k in ("living", "kitchen"))
    assert abs((a.rect[0] + a.rect[2]) - b.rect[0]) < 1e-9


def test_the_size_requirements_in_a_request_are_the_ones_fitted():
    items = extract("A two bedroom apartment of about 70 square metres.")
    assert any(i["kind"] == "area" for i in items)


# --- a U around a courtyard -----------------------------------------------------------------------------------------------------------------------
def test_a_u_around_a_courtyard_puts_the_courtyard_in_the_gap():
    d = build(L1, room("Living", "living", [0, 0, 12, 4]), room("Kitchen", "kitchen", [0, 4, 4, 4]), room("Bedroom 1", "bedroom", [4, 4, 4, 4]),
              room("Bedroom 2", "bedroom", [8, 4, 4, 4]), room("Bedroom 3", "bedroom", [0, 8, 6, 4]), room("Bedroom 4", "bedroom", [6, 8, 6, 4]),
              room("Courtyard", "other", [12, 0, 2, 2], roofed=False))
    items = [want(kind="feature", keyword="u-shaped", text="A U-shaped house"), want(kind="feature", keyword="courtyard", text="around a courtyard")]
    out, notes = autofix.reshape(d, items)
    assert _outline_shape(out) == "U"
    court = next(r for r in out.rooms if r.name == "Courtyard")
    assert court.roofed is False and _sides_with_rooms(out, court) >= 3
    assert all(status(out, i) == "met" for i in items)
    derive(out)


# --- the second round ------------------------------------------------------------------------------------------------------------------------------
def test_added_rooms_never_take_the_name_of_one_that_exists():
    d = build(L1, room("Living", "living", [0, 0, 5, 4]), room("Bedroom 2", "bedroom", [5, 0, 4, 4]), room("Hall", "hall", [0, 4, 9, 2]))
    item = want(kind="room", keyword="bedroom", count=3, text="three bedrooms")
    out, _ = autofix.add_missing_rooms(d, [item])
    names = [r.name for r in out.rooms]
    assert len(names) == len(set(n.lower() for n in names)) and status(out, item) == "met" and "Bedroom 2" in names


def test_a_plain_other_room_becomes_the_workshop_that_was_asked_for():
    d = build(L1, room("Office", "office", [0, 0, 4, 4]), room("Other", "other", [4, 0, 10, 8]), room("Other 2", "other", [0, 4, 4, 4]))
    item = want(kind="room", keyword="workshop", count=1, text="a workshop")
    out, notes = autofix.add_missing_rooms(d, [item])
    assert status(out, item) == "met" and next(r for r in out.rooms if r.name == "Workshop").rect[2] == 10 and notes


def test_furniture_gives_way_when_a_finishing_door_needs_the_wall():
    d = build(L1, room("Living", "living", [0, 0, 5, 4]), room("Bedroom", "bedroom", [5, 0, 4, 4]))
    d = apply_step(d, Step(step="furniture", room="Bedroom", kind="wardrobe", side="W"))        # against the wall the rooms share, in front of where a door would go
    out, notes = autofix.complete(d)
    assert any("door" in n for n in notes) and autofix._builds(out)


def test_two_rows_keep_a_room_whose_size_was_stated():
    d = build(L1, room("Garage", "garage", [0, 0, 3, 6]), room("Hall", "hall", [3, 0, 2.5, 6]), room("Living", "living", [5.5, 0, 4.5, 4]),
              room("Kitchen", "kitchen", [5.5, 4, 2.5, 2]), room("Bedroom", "bedroom", [3, 6, 4, 4]))
    item = want(kind="dimension", keyword="garage", width=3, depth=6, text="garage 3 m by 6 m")
    assert status(d, item) == "met"
    out, notes = autofix.reshape(d, [item])
    assert status(out, item) == "met"


def test_all_three_named_pieces_fit_in_a_studio_beside_each_other():
    from app.domain.sizes import extract_furniture
    d = build(L1, room("Studio", "living", [0, 0, 5, 8]))
    wanted = extract_furniture("A studio with a sofa, a double bed and a kitchen counter.")
    out, _ = autofix.furnish_wanted(d, wanted)
    assert all(r["status"] == "met" for r in checks.check(out, wanted))


def test_a_room_added_over_a_window_wall_takes_the_window_with_it_and_still_builds():
    d = build(L1, room("Living", "living", [0, 0, 5, 4]), room("Bedroom", "bedroom", [5, 0, 4, 4]))
    d = apply_step(d, Step(step="window", room="Living", side="W"))
    d = apply_step(d, Step(step="window", room="Bedroom", side="S"))
    item = want(kind="room", keyword="bathroom", count=2, text="two bathrooms")
    out, notes = autofix.add_missing_rooms(d, [item])
    assert status(out, item) == "met" and autofix._builds(out)


def test_a_room_named_for_the_request_is_in_title_case():
    d = build(L1, room("Office", "office", [0, 0, 4, 4]), room("Other", "other", [4, 0, 4, 4]))
    item = want(kind="room", keyword="staff room", count=1, text="a staff room")
    out, _ = autofix.add_missing_rooms(d, [item])
    assert any(r.name == "Staff Room" for r in out.rooms)


# --- the third round -------------------------------------------------------------------------------------------------------------------------------
def test_a_room_called_bedroom_is_a_bedroom_even_if_the_model_said_other():
    d = build(L1, room("Bedroom 1", "other", [0, 0, 4, 4]), room("Living Room", "other", [4, 0, 4, 4]), room("Hallway", "other", [0, 4, 8, 2]), room("Utility Store", "other", [8, 0, 2, 2]))
    assert [r.kind for r in d.rooms] == ["bedroom", "living", "hall", "utility"]


def test_a_short_outside_wall_takes_a_narrow_window():
    d = build(L1, room("Living", "living", [0, 0, 6, 4]), room("Bedroom", "bedroom", [0, 4, 4, 4]), room("Bath", "bathroom", [4, 4, 1.8, 4]))
    d = apply_step(d, Step(step="room", level="L1", name="Hall", kind="hall", rect=[5.8, 4, 0.2 + 0.8, 4]))
    fixed, notes = autofix.complete(d)
    assert all(any(w.room == r.id for w in fixed.windows) for r in fixed.rooms if r.kind in ("living", "bedroom"))


def test_unknown_kinds_become_rooms_named_for_the_request():
    d = build(L1, room("Reception", "other", [0, 0, 4, 4]), room("Office", "office", [4, 0, 4, 4]))
    item = want(kind="room", keyword="meeting", count=1, text="a meeting room")
    out, notes = autofix.add_missing_rooms(d, [item])
    assert status(out, item) == "met" and any(r.name == "Meeting Room" for r in out.rooms)


def test_plain_other_rooms_are_named_for_each_missing_classroom():
    d = build(L1, room("Classroom", "other", [0, 0, 8, 6]), room("Classroom 2", "other", [8, 0, 8, 6]), room("Other 3", "other", [0, 6, 8, 6]), room("Other 4", "other", [8, 6, 8, 6]))
    item = want(kind="room", keyword="classroom", count=4, text="four classrooms")
    out, _ = autofix.add_missing_rooms(d, [item])
    assert status(out, item) == "met" and len(out.rooms) == 4


def test_the_overall_size_is_fitted_through_a_room_whose_size_was_not_stated():
    d = build(L1, room("Living", "living", [0, 0, 5, 4]), room("Kitchen", "kitchen", [5, 0, 4, 4]), room("Bedroom", "bedroom", [0, 4, 5, 5.7]), room("Bath", "bathroom", [5, 4, 4, 5.7]))
    living = want(kind="dimension", keyword="living", width=5, depth=4, text="living 5 x 4")
    whole = want(kind="dimension", keyword="building", width=9, depth=9, text="9 m by 9 m")
    assert status(d, living) == "met" and status(d, whole) == "unmet"
    out, _ = autofix.fit_sizes(d, [living, whole])
    assert status(out, whole) == "met" and status(out, living) == "met"


def test_an_added_room_does_not_cover_the_only_outside_wall_of_another():
    base = build(L1, room("Kitchen", "kitchen", [0, 0, 3, 4]), room("Living", "living", [3, 0, 5, 4]))
    edited = apply_step(base, Step(step="room", level="L1", name="Study", kind="office", rect=[-3, 0, 3, 4]))      # west of the kitchen: its only outside wall on that side
    edited = apply_step(edited, Step(step="room", level="L1", name="Pantry", kind="storage", rect=[0, 4, 3, 2]))
    out, notes = autofix.keep_daylight(edited, base)
    assert not (set(autofix._enclosed(out)) - set(autofix._enclosed(base)))
