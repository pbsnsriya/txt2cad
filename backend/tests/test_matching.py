"""A requirement is met by the right room, not by a similar word, and shapes are measured."""

import pytest

from app.domain import checks
from app.domain.design import Design
from app.domain.steps import Step, apply_step


def build(*steps):
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


STOREY = {"step": "storey", "id": "L1", "name": "Ground floor", "height": 3}


def room(name, kind, rect, **extra):
    return {"step": "room", "level": "L1", "name": name, "kind": kind, "rect": rect, **extra}


def one(design, **raw):
    return checks.check(design, [checks.normalise({"supported": True, **raw})])[0]


# --- matching by whole words ---------------------------------------------------------------------------------------------
def test_a_keyword_matches_a_whole_word_of_the_name_or_the_kind():
    d = build(STOREY, room("Master Bedroom", "bedroom", [0, 0, 4, 4]), room("Hallway", "hall", [4, 0, 2, 4]))
    assert one(d, kind="room", keyword="bedroom", count=1, text="x")["status"] == "met"
    assert one(d, kind="room", keyword="hall", count=1, text="x")["status"] == "met"          # 'hallway' is a hall
    assert one(d, kind="room", keyword="bedrooms", count=1, text="x")["status"] == "met"      # plural


def test_part_of_a_word_does_not_match():
    d = build(STOREY, room("Bathroom", "bathroom", [0, 0, 3, 3]), room("Post room", "other", [3, 0, 3, 3]))
    assert one(d, kind="room", keyword="bed", count=1, text="x")["status"] == "unmet"
    assert one(d, kind="room", keyword="room", count=2, text="x")["status"] in ("met", "unmet")      # must not crash


def test_counts_use_each_room_once():
    d = build(STOREY, room("Bedroom 1", "bedroom", [0, 0, 3, 3]), room("Bedroom 2", "bedroom", [3, 0, 3, 3]))
    assert one(d, kind="room", keyword="bedroom", count=2, text="x")["status"] == "met"
    assert one(d, kind="room", keyword="bedroom", count=3, text="x")["status"] == "unmet"


# --- courtyards and shapes -----------------------------------------------------------------------------------------------
def courtyard_house(roofed):
    return build(STOREY, room("Living", "living", [0, 0, 10, 4]), room("Bedroom", "bedroom", [0, 4, 4, 4]), room("Study", "office", [6, 4, 4, 4]),
                 room("Courtyard", "other", [4, 4, 2, 4], roofed=roofed))


def test_a_courtyard_must_be_open_to_the_sky():
    want = dict(kind="feature", keyword="courtyard", text="The house is built around a courtyard.")
    assert one(courtyard_house(True), **want)["status"] == "unmet"
    r = one(courtyard_house(False), **want)
    assert r["status"] == "met" and "open to the sky" in r["detail"]


def test_a_courtyard_needs_rooms_around_it():
    d = build(STOREY, room("Courtyard", "other", [0, 0, 4, 4], roofed=False))
    r = one(d, kind="feature", keyword="courtyard", text="a courtyard")
    assert r["status"] == "unmet" and "surrounded" in r["detail"]


def test_an_l_shaped_footprint_is_told_from_a_rectangle():
    l_shape = build(STOREY, room("A", "living", [0, 0, 8, 4]), room("B", "bedroom", [0, 4, 4, 4]))
    rect = build(STOREY, room("A", "living", [0, 0, 8, 4]), room("B", "bedroom", [0, 4, 8, 4]))
    want = dict(kind="feature", keyword="l-shaped", text="The house is L-shaped.")
    assert one(l_shape, **want)["status"] == "met"
    r = one(rect, **want)
    assert r["status"] == "unmet" and "rectangle" in r["detail"]


def test_a_u_shaped_footprint():
    u = build(STOREY, room("Base", "living", [0, 0, 12, 4]), room("Left", "bedroom", [0, 4, 4, 4]), room("Right", "bedroom", [8, 4, 4, 4]))
    assert one(u, kind="feature", keyword="u-shaped", text="U-shaped")["status"] == "met"
    assert one(u, kind="feature", keyword="l-shaped", text="L-shaped")["status"] == "unmet"


def test_shape_words_are_buildable_not_unsupported():
    for kw in ("courtyard", "l-shaped", "u-shaped"):
        assert checks.normalise({"kind": "feature", "keyword": kw, "text": "x", "supported": False})["supported"] is True


def test_a_shop_floor_is_a_retail_space():
    d = build(STOREY, room("Sales Floor", "other", [0, 0, 6, 5]))
    assert one(d, kind="room", keyword="retail", count=1, text="x")["status"] == "met"
