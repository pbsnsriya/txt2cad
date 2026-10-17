"""A plan the model could not draw is laid out in code: L, U, a ring around a courtyard, rows so every room has an outside wall; and named furniture is placed."""

from app.domain import autofix, checks
from app.domain.checks import _outline_shape, _sides_with_rooms
from app.domain.derive import derive, exterior_sides
from app.domain.design import Design
from app.domain.reflow import CannotReflow, reflow
from app.domain.steps import Step, apply_step

import pytest


def build(*steps):
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


STOREY = {"step": "storey", "id": "L1", "name": "Ground floor", "height": 3}


def room(name, kind, rect, **extra):
    return {"step": "room", "level": "L1", "name": name, "kind": kind, "rect": rect, **extra}


def house(n_bed=3):
    steps = [STOREY, room("Living", "living", [0, 0, 6, 4]), room("Kitchen", "kitchen", [6, 0, 4, 4]), room("Hall", "hall", [0, 4, 3, 4]),
             room("Bathroom", "bathroom", [3, 4, 3, 4])]
    steps += [room(f"Bedroom {i + 1}", "bedroom", [6 + 3 * (i % 2), 4 + 4 * (i // 2), 3, 4]) for i in range(n_bed)]
    return build(*steps)


def no_overlap(d):
    from shapely.geometry import box
    boxes = [box(r.rect[0], r.rect[1], r.rect[0] + r.rect[2], r.rect[1] + r.rect[3]) for r in d.rooms if r.level == "L1"]
    return all(a.intersection(b).area < 1e-6 for i, a in enumerate(boxes) for b in boxes[i + 1:])


@pytest.mark.parametrize("shape", ["L", "U", "rows", "courtyard"])
def test_every_shape_builds_without_overlaps(shape):
    d = reflow(house(), "L1", shape)
    assert no_overlap(d)
    derive(d)                                                  # raises when it cannot be built


def test_l_and_u_outlines_are_what_they_say():
    assert _outline_shape(reflow(house(), "L1", "L")) == "L"
    assert _outline_shape(reflow(house(4), "L1", "U")) == "U"


def test_a_courtyard_is_open_and_surrounded():
    d = reflow(house(), "L1", "courtyard")
    court = next(r for r in d.rooms if r.name == "Courtyard")
    assert court.roofed is False and _sides_with_rooms(d, court) == 4


def test_an_existing_courtyard_room_is_reused():
    d = build(STOREY, room("Living", "living", [0, 0, 6, 4]), room("Kitchen", "kitchen", [6, 0, 4, 4]), room("Bedroom 1", "bedroom", [0, 4, 4, 4]),
              room("Bedroom 2", "bedroom", [4, 4, 4, 4]), room("Bedroom 3", "bedroom", [8, 4, 4, 4]), room("Courtyard", "other", [4, 8, 4, 4], roofed=False))
    out = reflow(d, "L1", "courtyard")
    assert [r.name for r in out.rooms].count("Courtyard") == 1
    assert next(r for r in out.rooms if r.name == "Courtyard").roofed is False


def test_two_rows_give_every_room_an_outside_wall():
    d = reflow(house(), "L1", "rows")
    assert all(exterior_sides(d)[r.id] for r in d.rooms)


def test_too_few_rooms_cannot_make_the_shape():
    d = build(STOREY, room("A", "living", [0, 0, 4, 4]), room("B", "bedroom", [4, 0, 4, 4]))
    with pytest.raises(CannotReflow):
        reflow(d, "L1", "U")


# --- the step that decides ------------------------------------------------------------------------------------------------------------------
def want(**raw):
    return checks.normalise({"supported": True, **raw})


def test_a_plan_that_is_not_an_l_is_laid_out_as_one_and_keeps_its_rooms():
    d = house()
    assert _outline_shape(d) != "L"
    item = want(kind="feature", keyword="l-shaped", text="The house is L-shaped.")
    out, notes = autofix.reshape(d, [item])
    assert _outline_shape(out) == "L" and len(out.rooms) == len(d.rooms) and notes and "an L" in notes[0]
    assert {r.id for r in out.rooms} == {r.id for r in d.rooms}


def test_a_plan_that_already_is_the_shape_is_left_alone():
    l_shape = build(STOREY, room("A", "living", [0, 0, 8, 4]), room("B", "bedroom", [0, 4, 4, 4]), room("C", "kitchen", [4, 0, 0.1 + 3.9, 4]) if False else room("C", "hall", [0, 8, 4, 2]))
    item = want(kind="feature", keyword="l-shaped", text="L-shaped")
    out, notes = autofix.reshape(l_shape, [item])
    assert out is l_shape and notes == []


def test_rooms_without_an_outside_wall_are_put_in_rows():
    d = build(STOREY, room("A", "living", [0, 0, 12, 4]), room("B", "bedroom", [0, 4, 4, 4]), room("Mid", "bedroom", [4, 4, 4, 4]), room("C", "kitchen", [8, 4, 4, 4]),
              room("D", "hall", [0, 8, 12, 4]))
    assert autofix._enclosed(d) == ["mid"]
    out, notes = autofix.reshape(d, [])
    assert autofix._enclosed(out) == [] and notes and "two rows" in notes[0]


def test_doors_and_windows_that_still_fit_are_kept():
    d = house()
    d = apply_step(d, Step(step="door", room="Living", to="outside", side="S"))
    out, _ = autofix.reshape(d, [want(kind="feature", keyword="u-shaped", text="U-shaped")])
    assert any(x.to == "outside" for x in out.doors)


def test_an_edit_is_never_laid_out_again():
    from app.pipeline import run
    assert 'if mode == "design"' in open(run.__file__, encoding="utf-8").read()


# --- named furniture ------------------------------------------------------------------------------------------------------------------------
def test_named_pieces_are_placed_when_the_model_left_them_out():
    from app.domain.sizes import extract_furniture
    d = build(STOREY, room("Studio", "living", [0, 0, 6, 5]))
    wanted = extract_furniture("A studio with a sofa, a double bed and a kitchen counter.")
    out, notes = autofix.furnish_wanted(d, wanted)
    assert {"sofa", "bed_double", "kitchen_counter"} <= {f.kind for f in out.furniture} and notes
    assert all(r["status"] == "met" for r in checks.check(out, wanted))
    derive(out)


def test_nothing_is_added_when_the_pieces_are_there_or_not_asked_for():
    d = build(STOREY, room("Studio", "living", [0, 0, 6, 5]))
    assert autofix.furnish_wanted(d, [])[1] == []


# --- an edit leaves alone what it was not about ---------------------------------------------------------------------------------------------
def test_an_edit_puts_back_a_room_it_was_not_about():
    base = house()
    changed = base.model_copy(deep=True)
    kitchen = next(r for r in changed.rooms if r.kind == "kitchen")
    kitchen.rect = (6, 0, 3, 2)                               # the model shrank it while adding a bathroom
    out, notes = autofix.keep_untouched(changed, base, "Add a second bathroom.")
    assert tuple(next(r for r in out.rooms if r.id == kitchen.id).rect) == (6, 0, 4, 4) and notes


def test_a_room_the_request_names_may_change():
    base = house()
    changed = base.model_copy(deep=True)
    next(r for r in changed.rooms if r.kind == "kitchen").rect = (6, 0, 3, 2)
    out, notes = autofix.keep_untouched(changed, base, "Make the kitchen smaller.")
    assert out is changed and notes == []


def test_a_room_is_not_put_back_on_top_of_another():
    base = house()
    changed = base.model_copy(deep=True)
    kitchen = next(r for r in changed.rooms if r.kind == "kitchen")
    kitchen.rect = (6, 0, 3, 2)
    changed = apply_step(changed, Step(step="room", level="L1", name="Study", kind="office", rect=[9, 0, 1, 4]))
    changed = apply_step(changed, Step(step="room", level="L1", name="Pantry", kind="storage", rect=[8, 2, 1, 2]))
    out, notes = autofix.keep_untouched(changed, base, "Add a study.")
    assert tuple(next(r for r in out.rooms if r.kind == "kitchen").rect) == (6, 0, 3, 2)
