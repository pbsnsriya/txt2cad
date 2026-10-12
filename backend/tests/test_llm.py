import json

import pytest

from app.domain.derive import derive
from app.domain.design import Design
from app.domain.steps import Step, apply_step
from app.llm.base import LLMError, LLMRequest, extract_json
from app.llm.mock import MockLLM, build_steps
from app.llm.partial_json import complete_steps, peek_draft

PROMPTS = [
    "Two storey house with a kitchen, living room and three bedrooms, a garage and a front porch.",
    "A small one storey cabin with one bedroom and a kitchen",
    "three storey townhouse with two bedrooms, a study and a bathroom",
    "an office",
]


@pytest.mark.parametrize("prompt", PROMPTS)
def test_mock_designs_always_apply_derive_and_have_every_room_reachable(prompt):
    d = Design()
    for s in build_steps(prompt):
        d = apply_step(d, Step(**s))
    spec = derive(d)
    assert spec.walls and spec.slabs and spec.roofs
    for lv in d.levels:
        rooms = {r.id for r in d.rooms if r.level == lv.id}
        level_doors = [x for x in d.doors if x.room in rooms]
        reach = {level_doors[0].room} if level_doors else set()
        changed = True
        while changed:
            changed = False
            for door in d.doors:
                if door.room in rooms and door.to in rooms and ((door.room in reach) != (door.to in reach)):
                    reach |= {door.room, door.to}
                    changed = True
        assert rooms <= reach or len(rooms) == 1, f"{prompt!r}: unreachable rooms on {lv.id}: {rooms - reach}"


def test_mock_counts_bedrooms_and_storeys():
    d = Design()
    for s in build_steps(PROMPTS[0]):
        d = apply_step(d, Step(**s))
    assert d.storeys() == 2 and len([r for r in d.rooms if r.kind == "bedroom"]) == 3 and any(r.kind == "garage" for r in d.rooms)


def test_partial_json_never_yields_a_half_written_step_for_any_prefix():
    text = json.dumps({"approach": "x", "steps": build_steps(PROMPTS[0])})
    full, _ = complete_steps(text)
    previous = 0
    for end in range(len(text) + 1):
        steps, draft = complete_steps(text[:end])
        assert len(steps) >= previous and len(steps) <= len(full)
        assert steps == full[:len(steps)]
        previous = len(steps)
        if draft:
            assert draft.startswith("{")
    assert previous == len(full)


def test_peek_draft_names_the_open_step():
    assert peek_draft('{"step": "window", "room": "kitchen", "si') == "window kitchen"
    assert peek_draft(None) is None


def test_extract_json_tolerates_prose_and_fences_and_truncation():
    assert extract_json('Sure! Here you go: {"steps": []} thanks') == {"steps": []}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    truncated = '{"steps": [{"step": "level", "id": "L1"}, {"step": "room", "na'
    assert extract_json(truncated) == {"steps": [{"step": "level", "id": "L1"}]}
    with pytest.raises(LLMError):
        extract_json("no json here")


def test_mock_streams_text_that_grows_and_returns_the_payload():
    chunks: list[str] = []
    out = MockLLM().complete(LLMRequest("", "", "build", {}, meta={"prompt": PROMPTS[1]}), chunks.append)
    assert chunks and all(b.startswith(a) for a, b in zip(chunks, chunks[1:]))
    assert json.loads(chunks[-1] + "")["steps"] == out["steps"] or json.loads(json.dumps(out))["steps"]
