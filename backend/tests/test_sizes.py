"""Sizes stated in a prompt become requirements that are measured against the design."""

import pytest

from app.domain import checks
from app.domain.design import Design
from app.domain.sizes import extract
from app.domain.steps import Step, apply_step


def build(*steps: dict) -> Design:
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


def storey(level="L1"):
    return {"step": "storey", "id": level, "name": "Ground floor", "height": 3}


def room(name, kind, rect, level="L1"):
    return {"step": "room", "level": level, "name": name, "kind": kind, "rect": list(rect)}


def only(prompt: str) -> dict:
    found = extract(prompt)
    assert len(found) == 1, found
    return found[0]


# --- extraction ---------------------------------------------------------------------------------------------------------
def test_a_room_size_is_read_with_its_subject():
    r = only("A house with a living room exactly 5 m by 4 m and a kitchen.")
    assert r["kind"] == "dimension" and r["params"] == {"keyword": "living", "width": 5.0, "depth": 4.0}
    assert "living room" in r["text"] and "5.0 x 4.0" in r["text"]


def test_overall_size_is_the_building_footprint():
    r = only("A 3 bedroom bungalow, 12 m by 9 m overall, with a porch.")
    assert r["params"] == {"keyword": "building", "width": 12.0, "depth": 9.0}


def test_a_size_after_the_subject_noun_is_found():
    r = only("Add a 6 x 3.5 m kitchen.")
    assert r["params"] == {"keyword": "kitchen", "width": 6.0, "depth": 3.5}


@pytest.mark.parametrize("text", ["35 square metres", "35 sqm", "35 sq m", "35m2", "35 m²", "35 square meters"])
def test_area_spellings(text):
    r = only(f"A studio flat of {text} with a kitchen area and a bathroom.")
    assert r["kind"] == "area" and r["params"] == {"keyword": "building", "area": 35.0}


def test_area_of_one_room_with_the_noun_after_the_number():
    r = only("A house with a 20 sqm living room.")
    assert r["kind"] == "area" and r["params"]["keyword"] == "living" and r["params"]["area"] == 20.0


def test_feet_are_converted_to_metres():
    r = only("A bedroom 12 ft by 10 ft.")
    assert r["params"]["width"] == pytest.approx(3.66, abs=0.01) and r["params"]["depth"] == pytest.approx(3.05, abs=0.01)
    r = only("A 400 sq ft flat.")
    assert r["params"]["area"] == pytest.approx(37.16, abs=0.05)


def test_several_sizes_and_none():
    found = extract("Kitchen 4 by 3 m, bedroom 3 by 3.5 m, and the whole house is 120 sqm.")
    assert [(f["params"]["keyword"], f["kind"]) for f in found] == [("kitchen", "dimension"), ("bedroom", "dimension"), ("building", "area")]
    assert extract("A house with three bedrooms and a garage.") == []
    extract("A 2 x 4 timber frame house.")          # ambiguous wording must never raise


def test_a_plot_size_is_not_a_building_size():
    assert extract("A house on a 20 m by 30 m plot.") == []


def test_implausible_numbers_are_ignored():
    assert extract("A room 0 by 4 m.") == [] and extract("A house 900 by 900 m.") == []


# --- checking -----------------------------------------------------------------------------------------------------------
def reqs(prompt):
    return extract(prompt)             # already in the stored shape


def test_a_room_of_the_right_size_is_met_and_says_so():
    d = build(storey(), room("Living Room", "living", (0, 0, 5, 4)))
    [r] = checks.check(d, reqs("A living room 5 m by 4 m."))
    assert r["status"] == "met" and "5.0 x 4.0" in r["detail"]


def test_orientation_does_not_matter_and_tolerance_is_fifteen_centimetres():
    d = build(storey(), room("Living", "living", (0, 0, 4.1, 5)))
    assert checks.check(d, reqs("A living room 5 m by 4 m."))[0]["status"] == "met"
    d = build(storey(), room("Living", "living", (0, 0, 4.3, 5)))
    assert checks.check(d, reqs("A living room 5 m by 4 m."))[0]["status"] == "unmet"


def test_a_wrong_room_size_is_unmet_with_the_numbers_and_a_way_to_fix_it():
    d = build(storey(), room("Living", "living", (0, 0, 5, 5)))
    [r] = checks.check(d, reqs("A living room 5 m by 4 m."))
    assert r["status"] == "unmet"
    assert "5.0 x 4.0" in r["detail"] and "5.0 x 5.0" in r["detail"] and "living" in r["detail"].lower()
    assert checks.unmet([r])                       # goes back to the model as feedback


def test_a_missing_room_is_unmet():
    d = build(storey(), room("Kitchen", "kitchen", (0, 0, 4, 3)))
    assert checks.check(d, reqs("A living room 5 m by 4 m."))[0]["status"] == "unmet"


def test_overall_footprint_uses_the_ground_floor_outline():
    d = build(storey(), room("A", "living", (0, 0, 6, 9)), room("B", "kitchen", (6, 0, 6, 9)))
    assert checks.check(d, reqs("A bungalow, 12 m by 9 m overall."))[0]["status"] == "met"
    d = build(storey(), room("A", "living", (0, 0, 6, 9)), room("B", "kitchen", (6, 0, 3, 9)))
    r = checks.check(d, reqs("A bungalow, 12 m by 9 m overall."))[0]
    assert r["status"] == "unmet" and "9.0 x 9.0" in r["detail"]


def test_total_area_is_checked_so_a_tiny_studio_cannot_pass():
    d = build(storey(), room("Studio", "other", (0, 0, 2.5, 2.5)))
    [r] = checks.check(d, reqs("Studio flat of 35 square metres."))
    assert r["status"] == "unmet" and "6.2" in r["detail"] and "35" in r["detail"]
    d = build(storey(), room("Studio", "other", (0, 0, 7, 5)))
    assert checks.check(d, reqs("Studio flat of 35 square metres."))[0]["status"] == "met"


def test_total_area_adds_up_every_level():
    d = build(storey("L1"), storey("L2"), room("A", "living", (0, 0, 6, 5), "L1"), room("B", "bedroom", (0, 0, 6, 5), "L2"))
    assert checks.check(d, reqs("A two storey house of 60 sqm."))[0]["status"] == "met"


def test_room_area_within_ten_percent():
    d = build(storey(), room("Living", "living", (0, 0, 5, 4.4)))      # 22 m2 vs 20
    assert checks.check(d, reqs("A 20 sqm living room."))[0]["status"] == "met"
    d = build(storey(), room("Living", "living", (0, 0, 5, 5)))        # 25 vs 20
    assert checks.check(d, reqs("A 20 sqm living room."))[0]["status"] == "unmet"


def test_merge_replaces_the_models_unmeasurable_size_items():
    model_items = [checks.normalise({"kind": "area", "text": "about 35 m2", "supported": True}),
                   checks.normalise({"kind": "room", "text": "a kitchen", "keyword": "kitchen", "count": 1})]
    merged = checks.merge_sizes(model_items, extract("A flat of 35 sqm with a kitchen."))
    assert [m["kind"] for m in merged] == ["room", "area"] and merged[1]["params"]["area"] == 35.0


def test_normalise_keeps_the_numbers():
    r = checks.normalise({"kind": "dimension", "text": "x", "keyword": "kitchen", "width": 4, "depth": 3})
    assert r["params"] == {"keyword": "kitchen", "width": 4, "depth": 3}


def test_a_total_given_after_other_room_words_is_still_the_whole_building():
    r = only("A small studio, one main room plus a bathroom, 25 square metres in all.")
    assert r["kind"] == "area" and r["params"] == {"keyword": "building", "area": 25.0}


# --- pieces named in the request ---------------------------------------------------------------------------------------------------------------------
from app.domain.sizes import extract_furniture  # noqa: E402


def test_pieces_named_in_the_request_become_requirements_with_counts():
    got = extract_furniture("A studio with a sofa, a double bed and two armchairs and a kitchen counter.")
    assert [(g["params"]["keyword"], g["params"]["count"]) for g in got] == [("sofa", 1), ("bed_double", 1), ("armchair", 2), ("kitchen_counter", 1)]
    assert got[0]["text"] == "There is a sofa" and got[2]["text"] == "There are 2 armchairs"


def test_rooms_and_bathroom_fixtures_are_not_taken_for_furniture():
    assert extract_furniture("A house with three bedrooms, a bathroom, a kitchen and two toilets in the office.") == []
    assert extract_furniture("Plain house") == []
    assert [g["params"]["keyword"] for g in extract_furniture("a bed and a desk")] == ["bed", "desk"]


def test_wanted_furniture_is_checked_against_the_design():
    d = build(storey(), room("Living", "living", (0, 0, 5, 5)), {"step": "furniture", "room": "Living", "kind": "sofa", "side": "S"})
    want = extract_furniture("a sofa and two armchairs and a bed")
    by = {r["params"]["keyword"]: r for r in checks.check(d, want)}
    assert by["sofa"]["status"] == "met" and by["armchair"]["status"] == "unmet" and "furniture step" in by["armchair"]["detail"] and by["bed"]["status"] == "unmet"
    d2 = apply_step(d, Step(step="furniture", room="Living", kind="bed_single", side="N"))
    assert {r["params"]["keyword"]: r["status"] for r in checks.check(d2, want)}["bed"] == "met"          # any bed will do for "a bed"
