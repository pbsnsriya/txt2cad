"""Rooms are named the way a person would say it: no ids, no level codes, no lower-case slugs."""

import pytest

from app.domain.design import Design
from app.domain.steps import Step, apply_step, tidy_name


@pytest.mark.parametrize("raw, kind, expected", [
    ("living room", "living", "Living Room"),
    ("bedroom-2", "bedroom", "Bedroom 2"),
    ("master_bedroom", "bedroom", "Master Bedroom"),
    ("Hall L1", "hall", "Hall"),
    ("L2 Hall", "hall", "Hall"),
    ("Level 3 Landing", "hall", "Landing"),
    ("hall-l1", "hall", "Hall"),
    ("  Kitchen  ", "kitchen", "Kitchen"),
    ("WC", "bathroom", "WC"),
    ("Open Plan Office", "office", "Open Plan Office"),
    ("kitchen/diner", "kitchen", "Kitchen/Diner"),
    ("", "bedroom", "Bedroom"),
    ("L1", "living", "Living"),
    ("Bedroom 1", "bedroom", "Bedroom 1"),
    ("dining room (L2)", "dining", "Dining Room"),
    ("tv lounge", "living", "Tv Lounge"),
])
def test_names_come_out_plain(raw, kind, expected):
    assert tidy_name(raw, kind) == expected


def build(*steps):
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


def test_a_room_step_stores_the_plain_name_and_a_clean_id():
    d = build({"step": "storey", "id": "L1", "height": 3}, {"step": "room", "level": "L1", "name": "L1 hall-way", "kind": "hall", "rect": [0, 0, 3, 3]})
    assert d.rooms[0].name == "Hall Way" and d.rooms[0].id == "hall-way"


def test_the_same_name_on_two_levels_keeps_its_name_and_gets_a_unique_id():
    d = build({"step": "storey", "id": "L1", "height": 3}, {"step": "storey", "id": "L2", "height": 3},
              {"step": "room", "level": "L1", "name": "Hall", "kind": "hall", "rect": [0, 0, 3, 3]},
              {"step": "room", "level": "L2", "name": "Hall", "kind": "hall", "rect": [0, 0, 3, 3]})
    assert [r.name for r in d.rooms] == ["Hall", "Hall"] and len({r.id for r in d.rooms}) == 2


def test_rooms_can_be_referred_to_with_a_level_in_front_or_behind():
    d = build({"step": "storey", "id": "L1", "height": 3}, {"step": "storey", "id": "L2", "height": 3},
              {"step": "room", "level": "L1", "name": "Hall", "kind": "hall", "rect": [0, 0, 3, 3]},
              {"step": "room", "level": "L2", "name": "Landing", "kind": "hall", "rect": [0, 0, 3, 3]},
              {"step": "room", "level": "L1", "name": "Living", "kind": "living", "rect": [3, 0, 4, 3]})
    for ref in ("L1 Hall", "Hall L1", "Hall (L1)", "level 1 hall"):
        d2 = apply_step(d, Step(step="door", room=ref, to="Living"))
        assert d2.doors[-1].room == "hall", ref
    assert apply_step(d, Step(step="window", room="L2 Landing", side="S")).windows[-1].room == "landing"


def test_the_names_a_user_sees_in_the_ifc_have_no_codes():
    from app.domain.derive import derive
    d = build({"step": "storey", "id": "L1", "height": 3}, {"step": "room", "level": "L1", "name": "bedroom-2", "kind": "bedroom", "rect": [0, 0, 4, 4]})
    spec = derive(d)
    assert spec.spaces[0].name == "Bedroom 2" and all("bedroom-2" not in w.label for w in spec.walls)
