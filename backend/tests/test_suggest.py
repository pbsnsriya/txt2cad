"""Suggested next requests come from the building on screen."""

from app.domain.design import Design
from app.domain.steps import Step, apply_step
from app.domain.suggest import suggest


def build(*steps: dict) -> Design:
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


STOREY = {"step": "storey", "id": "L1", "name": "Ground floor", "height": 3}


def mk(name, kind, rect, level="L1"):
    return {"step": "room", "level": level, "name": name, "kind": kind, "rect": rect}


def test_nothing_built_nothing_suggested():
    assert suggest(Design()) == []


def test_a_flat_roofed_house_is_offered_a_pitched_roof_and_a_study_beside_the_kitchen():
    d = build(STOREY, mk("Kitchen", "kitchen", [0, 0, 4, 4]), mk("Living Room", "living", [4, 0, 5, 4]), mk("Bedroom 1", "bedroom", [0, 4, 9, 4]))
    got = suggest(d, limit=10)
    assert got[0] == "Give it a gable roof." and "Add a study next to the Kitchen." in got and len(suggest(d)) == 3


def test_suggestions_name_rooms_that_exist_and_depend_on_the_design():
    d = build(STOREY, mk("Kitchen", "kitchen", [0, 0, 4, 4]), mk("Study", "office", [4, 0, 3, 4]), mk("Bedroom 1", "bedroom", [0, 4, 3, 3]),
              {"step": "roof", "kind": "gable"})
    got = suggest(d, limit=10)
    assert not any("study next to" in s.lower() for s in got)               # it already has one
    assert "Make Bedroom 1 bigger." in got                                     # 9 m2 is small for a bedroom
    assert "Change the roof to a hip roof." in got and "Give it a gable roof." not in got


def test_a_big_family_house_gets_a_second_bathroom_only_with_three_bedrooms():
    rooms = [mk(f"Bedroom {i}", "bedroom", [i * 4, 0, 4, 4]) for i in range(3)]
    assert "Add a second bathroom." in suggest(build(STOREY, *rooms, mk("Bath", "bathroom", [0, 4, 2, 2])), limit=10)
    assert "Add a second bathroom." not in suggest(build(STOREY, *rooms[:2], mk("Bath", "bathroom", [0, 4, 2, 2])), limit=10)


def test_a_big_single_storey_gets_a_second_storey_and_limit_is_respected():
    d = build(STOREY, mk("Living", "living", [0, 0, 8, 6]))
    assert "Add a second storey with two bedrooms and a bathroom." in suggest(d, limit=10)
    assert len(suggest(d, limit=2)) == 2
    assert len(set(suggest(d, limit=10))) == len(suggest(d, limit=10))
