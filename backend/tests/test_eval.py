"""The evaluation set: well formed, the scorer tells good from bad, and the offline model passes the cases it can do."""

import json
from pathlib import Path

import pytest

from app.domain.design import Design
from app.domain.steps import Step, apply_step
from evals.run import load_cases, run_case, summarise
from evals.score import score, verdict

KNOWN_EXPECT = {"storeys", "rooms", "on_level", "footprint", "area", "room_dims", "roof", "furnished", "floor", "walls", "furniture_kinds", "shape", "courtyard", "unsupported", "kept"}


def build(*steps):
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


def test_the_cases_are_well_formed():
    cases = load_cases()
    assert len(cases) >= 45 and len({c["id"] for c in cases}) == len(cases)
    assert {c["category"] for c in cases} >= {"houses", "flats", "commercial", "sizes", "roofs", "interiors", "shapes", "not built yet", "vague", "edits"}
    for c in cases:
        assert c["prompt"].strip() and set(c["expect"]) <= KNOWN_EXPECT, c["id"]
        assert (c["category"] == "edits") == ("base" in c), c["id"]


GOOD = [
    {"step": "storey", "id": "L1", "name": "Ground floor", "height": 3},
    {"step": "room", "level": "L1", "name": "Living Room", "kind": "living", "rect": [0, 0, 5, 4]},
    {"step": "room", "level": "L1", "name": "Kitchen", "kind": "kitchen", "rect": [5, 0, 4, 4]},
    {"step": "room", "level": "L1", "name": "Bedroom", "kind": "bedroom", "rect": [0, 4, 4, 4]},
    {"step": "door", "room": "Living Room", "to": "Kitchen"},
    {"step": "door", "room": "Living Room", "to": "Bedroom"},
    {"step": "door", "room": "Living Room", "to": "outside", "side": "S"},
    {"step": "window", "room": "Living Room", "side": "W"}, {"step": "window", "room": "Kitchen", "side": "S"}, {"step": "window", "room": "Bedroom", "side": "W"},
]


def passed(checks):
    return verdict(checks)["pass"]


def test_a_good_design_passes_what_it_was_asked_for():
    d = build(*GOOD)
    case = {"expect": {"storeys": 1, "rooms": {"living": 1, "kitchen": 1, "bedroom": 1}, "room_dims": {"living": [5, 4]}, "footprint": [9, 8], "area": [48, 56], "shape": "L"}}
    cks = score(d, case, saved=True)
    assert passed(cks), verdict(cks)["failed"]


def test_each_kind_of_miss_is_caught():
    d = build(*GOOD)
    for expect, name in [({"storeys": 2}, "storeys"), ({"rooms": {"bedroom": 2}}, "2 bedroom"), ({"room_dims": {"living": [6, 4]}}, "living 6 x 4"), ({"footprint": [20, 15]}, "footprint"),
                         ({"area": [100, 120]}, "area"), ({"roof": "gable"}, "roof"), ({"furnished": True}, "furnished"), ({"floor": {"living": "oak"}}, "living floor oak"),
                         ({"shape": "U"}, "U-shaped"), ({"courtyard": True}, "courtyard"), ({"furniture_kinds": ["sofa"]}, "furniture"), ({"on_level": {"bedroom": "L2"}}, "bedroom on L2"),
                         ({"unsupported": ["basement"]}, "says 'basement' is not built")]:
        failed = [c["name"] for c in score(d, {"expect": expect}, saved=True) if not c["ok"]]
        assert name in failed, (expect, failed)


def test_nothing_saved_fails_at_once_and_a_degenerate_design_fails_the_basics():
    assert [c["name"] for c in score(None, {"expect": {"storeys": 1}}, saved=False)] == ["saved"]
    box = build({"step": "storey", "id": "L1", "height": 3}, {"step": "room", "level": "L1", "name": "Other", "kind": "other", "rect": [0, 0, 20, 15]})
    cks = score(box, {"expect": {"rooms": {"office": 1, "meeting": 2}}}, saved=True)
    assert not passed(cks) and {"1 office", "2 meeting"} <= {c["name"] for c in cks if not c["ok"]}


def test_unsupported_things_must_be_named_and_edits_must_keep_what_they_should():
    d = build(*GOOD)
    case = {"expect": {"unsupported": ["pool"]}}
    assert passed(score(d, case, saved=True, notes=["not built: The building should include a pool."]))
    assert passed(score(d, case, saved=True, requirements=[{"status": "unsupported", "text": "a swimming pool"}]))
    moved = apply_step(d, Step(step="room", level="L1", name="Kitchen", kind="kitchen", rect=[5, 0, 5, 4]))
    assert passed(score(d, {"expect": {"kept": ["kitchen"]}}, saved=True, base=d))
    assert not passed(score(moved, {"expect": {"kept": ["kitchen"]}}, saved=True, base=d))


def test_names_with_codes_in_them_are_caught():
    d = build(*GOOD).model_copy(deep=True)
    d.rooms[0].name = "hall-l1"
    assert "plain names" in [c["name"] for c in score(d, {"expect": {}}, saved=True) if not c["ok"]]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config
    from app.main import create_app

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    with TestClient(create_app()) as c:
        yield c


def test_the_offline_model_passes_the_cases_marked_for_it_and_the_summary_adds_up(client):
    profile = next(p for p in client.get("/api/llm/profiles").json() if p["name"] == "Practice mode")
    cases = [c for c in load_cases() if c.get("mock")]
    assert len(cases) >= 6
    results = [run_case(client, profile["id"], c) for c in cases]
    failing = [(r["id"], r["failed"]) for r in results if not r["pass"]]
    assert not failing, failing
    s = summarise(results)
    assert s["cases"] == s["passed"] == len(cases) and sum(v["of"] for v in s["by_category"].values()) == len(cases)
