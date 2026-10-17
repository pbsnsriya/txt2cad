"""The finishing pass adds the doors, windows and stairs every building needs, and nothing it cannot place."""

from app.domain import checks
from app.domain.autofix import complete
from app.domain.derive import derive
from app.domain.design import Design
from app.domain.steps import Step, apply_step


def build(*steps):
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


def room(name, kind, rect, level="L1"):
    return {"step": "room", "level": level, "name": name, "kind": kind, "rect": rect}


STOREY = {"step": "storey", "id": "L1", "name": "Ground floor", "height": 3}
STOREY2 = {"step": "storey", "id": "L2", "name": "Upper floor", "height": 3}


def test_a_building_with_no_doors_gets_every_room_connected():
    d = build(STOREY, room("Hall", "hall", [0, 0, 3, 4]), room("Living", "living", [3, 0, 5, 4]), room("Kitchen", "kitchen", [8, 0, 4, 4]), room("Bedroom", "bedroom", [0, 4, 4, 4]),
              room("Bath", "bathroom", [4, 4, 3, 4]))
    fixed, notes = complete(d)
    assert not any("not linked" in p for p in checks.completeness(fixed))
    assert len(fixed.doors) >= 4 and all(n.startswith("added a door between") for n in notes if "door" in n)
    derive(fixed)


def test_doors_prefer_the_hall_and_a_room_already_reachable_is_left_alone():
    d = build(STOREY, room("Hall", "hall", [0, 0, 3, 4]), room("Living", "living", [3, 0, 5, 4]), room("Study", "office", [8, 0, 3, 4]),
              {"step": "door", "room": "Hall", "to": "Living"}, {"step": "door", "room": "Living", "to": "Study"})
    fixed, notes = complete(d)
    assert [x.id for x in fixed.doors] == [x.id for x in d.doors] and not [n for n in notes if "door" in n]


def test_a_room_with_no_window_gets_one_on_its_longest_outside_wall_and_a_bathroom_does_not_need_one():
    d = build(STOREY, room("Living", "living", [0, 0, 6, 4]), room("Bath", "bathroom", [6, 0, 2.5, 4]), {"step": "door", "room": "Living", "to": "Bath"})
    fixed, notes = complete(d)
    assert [w.room for w in fixed.windows] == ["living"] and any("window to Living" in n for n in notes)
    assert fixed.windows[0].side in ("S", "N")                               # the longer outside wall


def test_a_second_storey_gets_a_stair_and_the_rooms_above_stay_reachable():
    d = build(STOREY, STOREY2, room("Hall", "hall", [0, 0, 5, 4]), room("Living", "living", [5, 0, 5, 4]), room("Landing", "hall", [0, 0, 5, 4], "L2"), room("Bedroom", "bedroom", [5, 0, 5, 4], "L2"))
    fixed, notes = complete(d)
    assert len(fixed.stairs) == 1 and any("added a stair" in n for n in notes)
    assert checks.completeness(fixed) == []
    derive(fixed)


def test_what_cannot_be_placed_is_skipped_and_an_unbuildable_design_is_returned_as_it_was():
    tiny = build(STOREY, room("A", "bedroom", [0, 0, 1.0, 1.0]), room("B", "bedroom", [1.0, 0, 1.0, 1.0]))
    fixed, notes = complete(tiny)
    assert fixed.doors == [] and fixed.windows == [] and notes == []         # the walls are too short for a door or a window
    assert complete(Design())[1] == []


def test_a_complete_design_is_untouched():
    d = build(STOREY, room("Living", "living", [0, 0, 5, 4]), room("Kitchen", "kitchen", [5, 0, 4, 4]),
              {"step": "door", "room": "Living", "to": "Kitchen"}, {"step": "window", "room": "Living", "side": "S"}, {"step": "window", "room": "Kitchen", "side": "S"})
    fixed, notes = complete(d)
    assert notes == [] and fixed.model_dump() == d.model_dump()


def test_the_pipeline_finishes_what_a_careless_model_left_out(tmp_path, monkeypatch):
    """A model that places rooms and nothing else still gives a house with doors and windows, and the version says what was added."""
    import asyncio
    import json

    from app import config
    from app.db import repo
    from app.llm.base import LLMRequest
    from app.pipeline.run import RunInput, run_pipeline

    class Careless:
        name, vision = "careless", False

        def complete(self, request: LLMRequest, on_text=None):
            if request.schema_name == "requirements":
                return {"requirements": []}
            return {"approach": "rooms only", "steps": [
                {"step": "storey", "id": "L1", "height": 3},
                {"step": "room", "level": "L1", "name": "Living", "kind": "living", "rect": [0, 0, 5, 4]},
                {"step": "room", "level": "L1", "name": "Kitchen", "kind": "kitchen", "rect": [5, 0, 4, 4]},
                {"step": "room", "level": "L1", "name": "Bedroom", "kind": "bedroom", "rect": [0, 4, 4, 4]}]}

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    repo.init_db()
    project = repo.create_project(config.LOCAL_OWNER, "Careless")
    run_id = repo.create_run(config.LOCAL_OWNER, project["id"], "a small house", None, None)

    async def go():
        return [e async for e in run_pipeline(RunInput(config.LOCAL_OWNER, project["id"], "a small house", Careless(), "careless", None, run_id))]

    evs = asyncio.run(go())
    assert evs[-1]["stage"] == "finished", evs[-1]["message"]
    head = repo.head_version(config.LOCAL_OWNER, project["id"])
    design = Design.model_validate_json(head["design_json"])
    assert checks.completeness(design) == [] and len(design.doors) >= 2 and len(design.windows) >= 3
    assert any(n.startswith("added a door") for n in json.loads(head["notes_json"]))
    assert any(e["stage"] == "move" and e["data"].get("phase") == "Finishing touches" for e in evs)
