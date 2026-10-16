"""A run can no longer spiral: steps and rejections are capped per round, a stuck model is stopped, rounds that do not improve end, and a degenerate
result is refused instead of saved."""

import asyncio
import json
import threading
import time

import pytest

from app import config
from app.domain.design import Design
from app.domain.steps import Step, apply_step
from app.llm.base import LLMRequest
from app.llm.mock import MockLLM
from app.pipeline import gate
from app.pipeline.stream import StepStream


def build(*steps):
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


STOREY = {"step": "storey", "id": "L1", "name": "Ground floor", "height": 3}


def room(name, kind, rect, level="L1"):
    return {"step": "room", "level": level, "name": name, "kind": kind, "rect": rect}


async def _noop(*a, **k):
    return None


# --- the stream stops reading a runaway reply --------------------------------------------------------------------------
def test_too_many_rejected_steps_in_one_round_stops_the_stream():
    async def go():
        stream = StepStream(Design(), _noop, lambda d: None, max_rejected=5, max_steps=500)
        await stream.feed_steps([{"step": "room", "name": f"R{i}", "rect": [0, 0, 3, 3]} for i in range(100)])      # no level: every one is rejected
        return stream
    s = asyncio.run(go())
    assert s.over_limit and "rejected" in s.limit_reason and len(s.rejections) == 5 and s.seen == 100         # the rest is skipped, not judged


def test_too_many_steps_in_one_round_stops_the_stream():
    async def go():
        stream = StepStream(Design(), _noop, lambda d: None, max_rejected=500, max_steps=10)
        await stream.feed_steps([{"step": "remark", "text": f"note {i}"} for i in range(50)])
        return stream
    s = asyncio.run(go())
    assert s.over_limit and "steps" in s.limit_reason and s.applied == 10


def test_a_normal_reply_never_hits_the_limits():
    async def go():
        stream = StepStream(Design(), _noop, lambda d: None)
        await stream.feed_steps([STOREY, room("A", "living", [0, 0, 4, 4]), room("B", "kitchen", [4, 0, 4, 4])])
        return stream
    s = asyncio.run(go())
    assert not s.over_limit and s.applied == 3


# --- the whole run ends even when the model never stops ------------------------------------------------------------------
class Runaway:
    """A model that writes invalid steps for as long as it is allowed to: it only stops when the request's stop flag is set."""
    name, vision = "runaway", False

    def __init__(self):
        self.calls = 0
        self.stopped = 0

    def complete(self, request: LLMRequest, on_text=None):
        if request.schema_name == "requirements":
            return {"requirements": []}
        self.calls += 1
        steps, deadline = [], time.monotonic() + 20
        while time.monotonic() < deadline:
            steps.append({"step": "room", "name": f"R{len(steps)}", "rect": [0, 0, 3, 3]})             # no level, so rejected
            if on_text:
                on_text(json.dumps({"approach": "x", "steps": steps}))
            if request.stop is not None and request.stop.is_set():
                self.stopped += 1
                break
            time.sleep(0.002)
        return {"approach": "x", "steps": steps}


def test_a_runaway_model_is_stopped_and_the_run_fails_fast_without_saving(tmp_path, monkeypatch):
    from app.db import repo
    from app.pipeline.run import RunInput, run_pipeline

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    monkeypatch.setattr(config, "MAX_REJECTED_PER_ROUND", 8)
    repo.init_db()
    project = repo.create_project(config.LOCAL_OWNER, "Runaway")
    run_id = repo.create_run(config.LOCAL_OWNER, project["id"], "a house", None, None)
    llm = Runaway()

    async def go():
        evs = []
        async for ev in run_pipeline(RunInput(config.LOCAL_OWNER, project["id"], "a house", llm, "runaway", None, run_id)):
            evs.append(ev)
        return evs

    started = time.monotonic()
    evs = asyncio.run(go())
    assert time.monotonic() - started < 10                                            # never waits for the 20 s the model would take
    assert evs[-1]["stage"] == "failed" and llm.stopped >= 1
    assert repo.head_version(config.LOCAL_OWNER, project["id"]) is None             # nothing half-built was saved
    rejected = [e for e in evs if e["stage"] == "move" and not e["data"]["ok"]]
    assert len(rejected) <= 8 * (config.MAX_REPAIR_ROUNDS + 1)                       # bounded, not hundreds


# --- the gate ------------------------------------------------------------------------------------------------------------
def result(kind, status, **params):
    return {"kind": kind, "status": status, "text": "x", "supported": True, "params": params}


def test_nothing_met_of_several_checkable_things_is_refused():
    d = build(STOREY, room("Other", "other", [0, 0, 20, 15]))
    out = gate.problems(d, [result("room", "unmet", keyword="office"), result("room", "unmet", keyword="meeting", count=2)], None)
    assert any("none of the 2" in p for p in out)


def test_a_one_room_answer_to_a_many_room_request_is_refused():
    d = build(STOREY, room("Studio", "other", [0, 0, 3, 3]))
    out = gate.problems(d, [result("room", "unmet", keyword="bedroom", count=3), result("room", "met", keyword="other")], None)
    assert any("names 4 rooms" in p and "1 room" in p for p in out)


def test_far_too_small_for_the_stated_area_is_refused():
    d = build(STOREY, room("Box", "other", [0, 0, 2.5, 2.5]))
    out = gate.problems(d, [result("area", "unmet", keyword="building", area=35.0)], None)
    assert any("less than half" in p for p in out)


def test_rooms_without_a_single_door_are_refused():
    d = build(STOREY, room("A", "living", [0, 0, 4, 4]), room("B", "kitchen", [4, 0, 4, 4]))
    assert any("door" in p for p in gate.problems(d, [], None))


def test_a_sound_result_passes_and_so_does_an_unchecked_one():
    d = build(STOREY, room("A", "living", [0, 0, 4, 4]), room("B", "kitchen", [4, 0, 4, 4]), {"step": "door", "room": "A", "to": "B"})
    assert gate.problems(d, [result("room", "met", keyword="living"), result("room", "unmet", keyword="garage")], None) == []
    assert gate.problems(d, [result("feature", "not_checked")], None) == []


def test_an_edit_that_wipes_out_most_of_the_building_is_refused():
    d = build(STOREY, room("A", "living", [0, 0, 4, 4]))
    assert any("removed 5 of the 6" in p for p in gate.problems(d, [], started_with=6))
    assert gate.problems(d, [], started_with=2) == []
