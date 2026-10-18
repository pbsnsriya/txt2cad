import pytest

from app.domain.design import Design
from app.domain.derive import DesignError, derive, exterior_sides, wall_pieces
from app.domain.steps import Step, StepError, apply_step


def build(*steps: dict) -> Design:
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


TWO_ROOMS = (
    {"step": "storey", "id": "L1", "height": 3},
    {"step": "room", "level": "L1", "name": "Kitchen", "kind": "kitchen", "rect": [0, 0, 4, 4]},
    {"step": "room", "level": "L1", "name": "Living", "kind": "living", "rect": [4, 0, 5, 4]},
)


def test_levels_must_be_added_in_order():
    with pytest.raises(StepError, match="next level id is L1"):
        build({"step": "storey", "id": "L3"})


def test_room_needs_a_level_first():
    with pytest.raises(StepError, match="add a level step first"):
        build({"step": "room", "level": "L1", "name": "Kitchen", "rect": [0, 0, 3, 3]})


def test_overlap_is_rejected_with_the_neighbour_named():
    with pytest.raises(StepError, match="overlaps 'Kitchen'"):
        build(*TWO_ROOMS, {"step": "room", "level": "L1", "name": "Hall", "rect": [3, 1, 3, 2]})


def test_lenient_inputs_are_normalised():
    d = build({"step": "storey", "id": 1}, {"step": "room", "level": 1, "name": "Hall", "rect": {"x": 0, "y": 0, "w": 3, "d": 3}},
              {"step": "window", "room": "Hall", "side": "north"})
    assert d.rooms[0].rect == (0, 0, 3, 3) and d.windows[0].side == "N"


def test_unknown_room_lists_the_known_ones():
    with pytest.raises(StepError, match="rooms: kitchen, living"):
        build(*TWO_ROOMS, {"step": "door", "room": "Attic"})


def test_shared_edge_becomes_one_partition_and_rest_is_exterior():
    d = build(*TWO_ROOMS)
    pieces = wall_pieces(d)
    partitions = [p for p in pieces if p.other]
    assert len(partitions) == 1 and partitions[0].id == "wall.L1.kitchen~living" and partitions[0].length == pytest.approx(4)
    assert exterior_sides(d)["kitchen"] == {"N", "S", "W"}
    assert exterior_sides(d)["living"] == {"N", "S", "E"}


def test_door_between_rooms_sits_on_the_partition_and_windows_avoid_it():
    d = build(*TWO_ROOMS, {"step": "door", "room": "kitchen", "to": "living", "at": 0.5},
              {"step": "window", "room": "kitchen", "side": "S"}, {"step": "door", "room": "living", "side": "S"})
    spec = derive(d)
    door = next(o for o in spec.openings if o.id.startswith("door.kitchen"))
    assert door.host == "wall.L1.kitchen~living" and door.offset == pytest.approx(2.0)
    assert len(spec.openings) == 3 and len(spec.walls) == 7


def test_openings_on_one_wall_never_overlap():
    d = build(*TWO_ROOMS, {"step": "window", "room": "living", "side": "S", "at": 0.5},
              {"step": "window", "room": "living", "side": "S", "at": 0.5, "id": "win-2"})
    spec = derive(d)
    a, b = sorted((o for o in spec.openings), key=lambda o: o.offset)
    assert b.offset - a.offset >= (a.width + b.width) / 2 + 0.1 - 1e-9


def test_window_on_an_interior_side_names_the_exterior_sides():
    d = build(*TWO_ROOMS, {"step": "window", "room": "kitchen", "side": "E"})
    with pytest.raises(DesignError, match="exterior sides are N, S, W"):
        derive(d)


def test_door_between_rooms_that_do_not_touch_is_an_error():
    d = build(*TWO_ROOMS, {"step": "room", "level": "L1", "name": "Far", "rect": [20, 20, 3, 3]},
              {"step": "door", "room": "kitchen", "to": "far"})
    with pytest.raises(DesignError, match="do not share a wall"):
        derive(d)


def test_stacked_levels_get_elevations_slabs_and_one_roof_over_the_top():
    d = build(*TWO_ROOMS, {"step": "storey", "id": "L2", "height": 2.8},
              {"step": "room", "level": "L2", "name": "Bed", "rect": [0, 0, 9, 4]})
    spec = derive(d)
    assert [lv.elevation for lv in spec.levels] == [0.0, 3.0]
    assert len(spec.slabs) == 2 and len(spec.roofs) == 1 and spec.roofs[0].level == "L2"
    assert spec.roofs[0].z_bottom == pytest.approx(5.8)


def test_a_lower_wing_gets_its_own_roof():
    d = build(*TWO_ROOMS, {"step": "storey", "id": "L2"}, {"step": "room", "level": "L2", "name": "Bed", "rect": [0, 0, 4, 4]})
    roofs = {r.level for r in derive(d).roofs}
    assert roofs == {"L1", "L2"}


def test_remove_room_cascades_to_its_openings():
    d = build(*TWO_ROOMS, {"step": "door", "room": "kitchen", "to": "living"}, {"step": "window", "room": "kitchen", "side": "S"},
              {"step": "delete", "id": "kitchen"})
    assert not d.doors and not d.windows and [r.id for r in d.rooms] == ["living"]


def test_layout_step_replaces_a_storeys_rooms_but_keeps_ids():
    d = build(*TWO_ROOMS, {"step": "rearrange", "level": "L1", "rooms": [
        {"name": "Kitchen", "kind": "kitchen", "rect": [0, 0, 5, 4]}, {"name": "Living", "kind": "living", "rect": [5, 0, 4, 4]}]})
    assert {r.id: r.rect for r in d.rooms} == {"kitchen": (0, 0, 5, 4), "living": (5, 0, 4, 4)}


def test_missing_level_defaults_to_the_newest_one():
    d = build({"step": "storey", "id": "L1"}, {"step": "room", "name": "Hall", "rect": [0, 0, 3, 3]},
              {"step": "rearrange", "rooms": [{"name": "Hall", "rect": [0, 0, 3, 3]}, {"name": "Study", "rect": [3, 0, 3, 3]}]})
    assert [r.level for r in d.rooms] == ["L1", "L1"]


def test_room_name_may_arrive_in_the_room_field():
    d = build({"step": "storey", "id": "L1"}, {"step": "room", "room": "Kitchen", "kind": "kitchen", "rect": [0, 0, 3, 3]})
    assert d.rooms[0].name == "Kitchen" and d.rooms[0].id == "kitchen"


def test_room_without_a_name_gets_one_from_its_kind():
    d = build({"step": "storey", "id": "L1"}, {"step": "room", "kind": "bedroom", "rect": [0, 0, 3, 3]}, {"step": "room", "kind": "bedroom", "rect": [3, 0, 3, 3]})
    assert [r.name for r in d.rooms] == ["Bedroom", "Bedroom 2"]


def test_completeness_flags_missing_windows_and_unlinked_rooms():
    from app.domain.checks import completeness
    d = build(*TWO_ROOMS)
    issues = completeness(d)
    assert any("Kitchen" in i and "no window" in i for i in issues) and any("not linked by doors" in i for i in issues)
    d = build(*TWO_ROOMS, {"step": "door", "room": "kitchen", "to": "living"}, {"step": "window", "room": "kitchen", "side": "S"}, {"step": "window", "room": "living", "side": "S"})
    assert completeness(d) == []


def test_rooms_can_be_named_the_way_models_write_them():
    d = build({"step": "storey", "id": "L1"}, {"step": "storey", "id": "L2"},
              {"step": "room", "level": "L1", "name": "Living", "kind": "living", "rect": [0, 0, 5, 4]},
              {"step": "room", "level": "L1", "name": "Hall", "kind": "hall", "rect": [5, 0, 3, 4]},
              {"step": "room", "level": "L2", "name": "Hall", "kind": "hall", "rect": [0, 0, 8, 4]},
              {"step": "room", "level": "L2", "name": "Bedroom", "kind": "bedroom", "rect": [8, 0, 4, 4]})
    for ref, want in [("Living Room", "living"), ("living", "living"), ("Hall L2", "hall-2"), ("Hall (L1)", "hall"), ("Bedroom 1", "bedroom"), ("hall-2", "hall-2")]:
        d2 = apply_step(d, Step(step="window", room=ref, side="N"))
        assert d2.windows[-1].room == want, (ref, d2.windows[-1].room)


def test_ambiguous_room_name_asks_for_an_id():
    d = build({"step": "storey", "id": "L1"}, {"step": "storey", "id": "L2"},
              {"step": "room", "level": "L1", "name": "Hall", "rect": [0, 0, 4, 4]}, {"step": "room", "level": "L2", "name": "Hall", "rect": [0, 0, 4, 4]})
    with pytest.raises(StepError, match=r"matches several rooms \(hall, hall-2\)"):
        apply_step(d, Step(step="window", room="Hall room", side="N"))


def test_adding_a_room_beside_a_windowed_wall_drops_that_window_instead_of_failing():
    from app.domain.derive import prune_invalid_openings
    d = build(*TWO_ROOMS, {"step": "window", "room": "living", "side": "E"}, {"step": "window", "room": "living", "side": "S"})
    d2 = apply_step(d, Step(step="room", level="L1", name="Study", kind="office", rect=[9, 0, 3, 4]))
    with pytest.raises(DesignError, match="not an exterior wall"):
        derive(d2)
    pruned, removed = prune_invalid_openings(d2)
    assert [w.side for w in pruned.windows] == ["S"] and len(removed) == 1 and "window.living.E" in removed[0]
    assert derive(pruned).openings


def test_a_model_that_calls_everything_unsupported_is_overruled_for_things_the_tool_builds():
    from app.domain.checks import normalise
    assert normalise({"kind": "storeys", "text": "two storeys", "count": 2, "supported": False})["supported"] is True
    assert normalise({"kind": "room", "keyword": "bedroom", "count": 3, "text": "3 bedrooms", "supported": False})["supported"] is True
    assert normalise({"kind": "feature", "keyword": "garage", "text": "garage", "supported": True})["supported"] is True
    assert normalise({"kind": "feature", "keyword": "porch", "text": "porch", "supported": True})["supported"] is False     # we know better
    assert normalise({"kind": "style", "text": "curved roof", "supported": False})["supported"] is False                  # the model's flag stands elsewhere
