import json

import pytest

from app.api.routes import make_llm
from app.domain import checks
from app.domain.derive import derive
from app.domain.describe import describe
from app.domain.design import Design
from app.domain.steps import Step, apply_step
from app.llm.base import LLMError, LLMRequest
from app.llm.program import PROGRAM_SCHEMA, ProgramLLM, program_to_levels

PROGRAM = {"storeys": 2, "rooms": [
    {"name": "Living Room", "kind": "living", "level": 1, "area": 24}, {"name": "Kitchen", "kind": "kitchen", "level": 1},
    {"name": "Garage", "kind": "garage", "level": 1, "area": 18},
    {"name": "Bedroom", "kind": "bedroom", "level": 2}, {"name": "Bedroom", "kind": "bedroom", "level": 2}, {"name": "Bedroom", "kind": "bedroom", "level": 2},
    {"name": "Bathroom", "kind": "bathroom", "level": 2}]}


class Stub:
    name, vision = "stub", False

    def __init__(self, program):
        self.program, self.calls = program, []

    def complete(self, request, on_text=None):
        self.calls.append(request)
        return self.program if request.schema_name == "program" else {"steps": [{"step": "note", "text": "inner model"}]}


def build(program) -> Design:
    out = ProgramLLM(Stub(program)).complete(LLMRequest("sys", "user", "build", {}, meta={"prompt": "a house"}))
    d = Design()
    for s in out["steps"]:
        d = apply_step(d, Step(**s))
    return d


def test_a_room_program_becomes_a_complete_connected_house_with_a_stair():
    d = build(PROGRAM)
    spec = derive(d)
    assert d.storeys() == 2 and len(d.stairs) == 1 and spec.stairs and spec.roofs
    assert sorted(r.name for r in d.rooms if r.kind == "bedroom") == ["Bedroom", "Bedroom 2", "Bedroom 3"]      # same name three times -> unique names
    assert checks.completeness(d) == []                                    # windows everywhere they are needed, every room reachable, stair present


def test_the_brief_checklist_is_met_by_a_program_build():
    d = build(PROGRAM)
    reqs = [checks.normalise(r) for r in ({"kind": "storeys", "count": 2, "text": "two storeys"}, {"kind": "room", "keyword": "bedroom", "count": 3, "text": "3 bedrooms"},
                                         {"kind": "feature", "keyword": "garage", "count": 1, "text": "garage"})]
    assert [r["status"] for r in checks.check(d, reqs)] == ["met", "met", "met"]


def test_areas_are_clamped_unknown_kinds_become_other_and_halls_are_added():
    levels = program_to_levels({"storeys": 1, "rooms": [{"name": "Tiny", "kind": "closet", "level": 1, "area": 0.5}, {"name": "Huge", "kind": "living", "level": 1, "area": 900}]})
    assert levels == [[("Hall", "hall", 10.0), ("Tiny", "other", 4.0), ("Huge", "living", 60.0)]]


def test_levels_out_of_range_are_pulled_in_and_an_overfull_level_spills_over():
    levels = program_to_levels({"storeys": 2, "rooms": [{"name": f"R{i}", "kind": "bedroom", "level": 9} for i in range(11)]})
    assert len(levels) == 2 and all(len(lv) - 1 <= 8 for lv in levels) and sum(len(lv) - 1 for lv in levels) == 11


def test_a_program_with_no_rooms_is_a_clear_error():
    with pytest.raises(LLMError, match="no rooms"):
        program_to_levels({"storeys": 2, "rooms": []})
    with pytest.raises(LLMError, match="no rooms"):
        program_to_levels({"storeys": 1, "rooms": [{"name": "Hall", "kind": "hall", "level": 1}]})


def test_a_garbled_storey_count_falls_back_to_the_rooms():
    assert len(program_to_levels({"storeys": "two", "rooms": [{"name": "A", "kind": "bedroom", "level": 2}]})) == 2


def test_edits_and_fix_rounds_go_to_the_wrapped_model_untouched():
    stub = Stub(PROGRAM)
    llm = ProgramLLM(stub)
    out = llm.complete(LLMRequest("s", "u", "build", {}, meta={"prompt": "x", "has_design": True}))
    assert out["steps"][0]["text"] == "inner model" and stub.calls[0].schema_name == "build"
    stub.calls.clear()
    llm.complete(LLMRequest("s", "u", "build", {}, meta={"prompt": "x", "round": 1}))
    assert stub.calls[0].schema_name == "build"
    stub.calls.clear()
    llm.complete(LLMRequest("s", "u", "requirements", {}, meta={"prompt": "x"}))
    assert stub.calls[0].schema_name == "requirements"


def test_the_model_is_asked_only_for_the_program_not_for_coordinates():
    stub = Stub(PROGRAM)
    ProgramLLM(stub).complete(LLMRequest("s", "u", "build", {}, meta={"prompt": "two storey house"}))
    asked = stub.calls[0]
    assert asked.schema_name == "program" and asked.schema is PROGRAM_SCHEMA and asked.user == "two storey house"
    assert "coordinates" in asked.system and "rect" not in json.dumps(asked.schema)


def test_a_profile_with_planner_program_gets_the_wrapper_and_others_do_not():
    base = {"provider": "openai_compat", "base_url": "http://x/v1", "model": "m", "api_key_env": ""}
    assert isinstance(make_llm({**base, "options_json": '{"planner": "program"}'}), ProgramLLM)
    assert not isinstance(make_llm({**base, "options_json": "{}"}), ProgramLLM)


def test_streaming_text_grows_for_the_ui():
    chunks: list[str] = []
    ProgramLLM(Stub(PROGRAM)).complete(LLMRequest("s", "u", "build", {}, meta={"prompt": "x"}), chunks.append)
    assert chunks and all(b.startswith(a) for a, b in zip(chunks, chunks[1:])) and json.loads(chunks[-1])["steps"]
    assert "STAIR" in describe(build(PROGRAM))
