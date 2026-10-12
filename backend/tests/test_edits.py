"""Bigger edits: move a room, resize it, rearrange a level, remove a level. Each must leave a design that derives and compiles."""

import pytest

from app.domain.derive import derive, prune_invalid_openings
from app.domain.design import Design
from app.domain.steps import Step, StepError, apply_step
from app.ifc.compile import compile_ifc

HOUSE = (
    {"step": "level", "id": "L1", "height": 3}, {"step": "level", "id": "L2", "height": 3},
    {"step": "room", "level": "L1", "name": "Hall", "kind": "hall", "rect": [0, 0, 3, 5]},
    {"step": "room", "level": "L1", "name": "Living", "kind": "living", "rect": [3, 0, 5, 5]},
    {"step": "room", "level": "L1", "name": "Kitchen", "kind": "kitchen", "rect": [8, 0, 4, 5]},
    {"step": "room", "level": "L2", "name": "Landing", "kind": "hall", "rect": [0, 0, 3, 5]},
    {"step": "room", "level": "L2", "name": "Bed", "kind": "bedroom", "rect": [3, 0, 9, 5]},
    {"step": "stair", "room": "Hall", "side": "W"},
    {"step": "door", "room": "Hall", "to": "Living"}, {"step": "door", "room": "Living", "to": "Kitchen"}, {"step": "door", "room": "Hall", "to": "outside", "side": "S", "at": 0.9},
    {"step": "door", "room": "Landing", "to": "Bed"},
    {"step": "window", "room": "Living", "side": "S"}, {"step": "window", "room": "Kitchen", "side": "S"}, {"step": "window", "room": "Kitchen", "side": "E"},
    {"step": "window", "room": "Bed", "side": "N"}, {"step": "window", "room": "Bed", "side": "S"},
)


def house() -> Design:
    d = Design()
    for s in HOUSE:
        d = apply_step(d, Step(**s))
    return d


def settle(d: Design):
    """What the pipeline does after a structural step: drop stranded openings, then derive."""
    d, removed = prune_invalid_openings(d)
    return d, derive(d), removed


def test_the_starting_house_is_valid_and_compiles():
    d, spec, removed = settle(house())
    assert not removed and len(spec.stairs) == 1
    model, _ = compile_ifc(spec, d.model_dump_json(), None)
    assert model.by_type("IfcStair") and len(model.by_type("IfcDoor")) == 4


def test_moving_a_room_keeps_its_id_and_the_ids_of_walls_it_did_not_touch():
    d0, spec0, _ = settle(house())
    _, g0 = compile_ifc(spec0, "", None)
    moved = apply_step(d0, Step(step="room", level="L1", name="Kitchen", kind="kitchen", rect=[8, 0, 4, 6]))   # one metre deeper
    d1, spec1, removed = settle(moved)
    assert [r.rect for r in d1.rooms if r.id == "kitchen"] == [(8, 0, 4, 6)]
    _, g1 = compile_ifc(spec1, "", g0)
    for key in ("element:L1-wall-hall-W", "element:L1-wall-hall+living", "element:L1-wall-kitchen-S", "element:L2-slab-1", "level:L2"):
        assert g1[key] == g0[key], key
    assert g1["element:L1-wall-kitchen-E"] == g0["element:L1-wall-kitchen-E"]      # same id even though the wall is longer


def test_growing_a_room_into_its_neighbour_is_rejected_naming_the_neighbour():
    with pytest.raises(StepError, match=r"overlaps 'Kitchen'.*x 8\.0\.\.12\.0"):
        apply_step(house(), Step(step="room", level="L1", name="Living", kind="living", rect=[3, 0, 7, 5]))


def test_resizing_two_rooms_at_once_with_layout_keeps_ids_and_drops_nothing_that_still_fits():
    d = apply_step(house(), Step(step="layout", level="L1", rooms=[
        {"name": "Hall", "kind": "hall", "rect": [0, 0, 3, 5]}, {"name": "Living", "kind": "living", "rect": [3, 0, 6, 5]},
        {"name": "Kitchen", "kind": "kitchen", "rect": [9, 0, 3, 5]}]))
    d, spec, removed = settle(d)
    assert {r.id for r in d.rooms if r.level == "L1"} == {"hall", "living", "kitchen"}
    assert {x.id for x in d.doors} >= {"door-hall-living", "door-living-kitchen"} and len(spec.stairs) == 1


def test_a_layout_that_drops_a_room_also_drops_its_doors_windows_and_stairs():
    d = apply_step(house(), Step(step="layout", level="L1", rooms=[
        {"name": "Living", "kind": "living", "rect": [3, 0, 5, 5]}, {"name": "Kitchen", "kind": "kitchen", "rect": [8, 0, 4, 5]}]))   # the Hall is gone
    assert not [x for x in d.doors if "hall" in (x.room, x.to) and x.room == "hall"] and not d.stairs
    d, spec, removed = settle(d)
    assert spec.walls and not spec.stairs


def test_removing_the_top_level_removes_its_rooms_and_the_stair_that_led_to_it():
    d = apply_step(house(), Step(step="remove", id="L2"))
    assert [lv.id for lv in d.levels] == ["L1"] and not [r for r in d.rooms if r.level == "L2"]
    d, spec, removed = settle(d)
    assert not d.stairs and any("stair" in r for r in removed) and not spec.stairs
    assert all(s.holes == [] for s in spec.slabs) and [r.level for r in spec.roofs] == ["L1"]


def test_removing_the_ground_level_leaves_a_valid_one_storey_building():
    d = apply_step(house(), Step(step="remove", id="L1"))
    d, spec, _ = settle(d)
    assert [lv.id for lv in d.levels] == ["L2"] and spec.levels[0].elevation == 0.0       # the remaining level drops to the ground
    compile_ifc(spec, "", None)


def test_removing_a_room_beside_a_windowed_wall_leaves_the_window_in_place():
    d, spec, removed = settle(apply_step(house(), Step(step="remove", id="kitchen")))
    assert not removed and any(w.id == "win-living-S" for w in d.windows) and not any(r.id == "kitchen" for r in d.rooms)
    assert all("kitchen" not in (x.room, x.to) for x in d.doors)


def test_adding_a_third_level_then_a_second_stair_works():
    d = house()
    for s in ({"step": "level", "id": "L3", "height": 3}, {"step": "room", "level": "L3", "name": "Attic Hall", "kind": "hall", "rect": [0, 0, 3, 5]},
              {"step": "stair", "room": "Landing", "side": "W"}):
        d = apply_step(d, Step(**s))
    d, spec, _ = settle(d)
    assert [s.level for s in spec.stairs] == ["L1", "L2"] and [lv.elevation for lv in spec.levels] == [0, 3, 6]


def test_a_stair_step_for_a_room_with_no_exterior_side_given_asks_for_a_side():
    with pytest.raises(StepError, match="'side' .* is required"):
        apply_step(house(), Step(step="stair", room="Landing"))


def test_clicked_elements_are_described_in_words_the_model_can_use():
    from app.domain.describe import describe_focus
    d = house()
    assert describe_focus(d, "L1-wall-kitchen-E") == "the east exterior wall L1-wall-kitchen-E of Kitchen (kitchen) on L1"
    assert describe_focus(d, "L1-wall-hall+living") == "the partition wall L1-wall-hall+living between Hall (hall) and Living (living) on L1"
    assert describe_focus(d, "door-hall-living") == "the door door-hall-living between Hall (hall) and Living (living)"
    assert describe_focus(d, "win-living-S") == "the window win-living-S on the south wall of Living (living)"
    assert describe_focus(d, "L1-space-kitchen").startswith("the room kitchen 'Kitchen'")
    assert describe_focus(d, "stair-hall") == "the stair stair-hall in Hall (hall)"
    assert describe_focus(d, "L2-slab-1") == "the floor slab L2-slab-1 of L2"
    assert describe_focus(d, "nonsense") is None
