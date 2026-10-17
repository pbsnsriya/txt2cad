"""One prompt run: requirements -> streamed build steps -> fix rounds -> check -> derive -> compile -> save a version.

`run_pipeline` is an async generator of event dicts {stage, message, data}. The API wraps them as Server-Sent Events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

from .. import config
from ..db import repo
from ..domain import autofix, checks, sizes
from ..domain.derive import DesignError, derive
from ..domain.describe import describe, describe_selection
from ..domain.design import Design
from ..domain.steps import SKIPPED_PREFIX
from ..ifc.compile import compile_ifc
from ..llm.base import LLM, LLMError, LLMRequest
from ..llm.prompts import BUILD_SYSTEM, REQUIREMENTS_SYSTEM
from ..llm.schemas import BUILD_SCHEMA, REQUIREMENTS_SCHEMA
from . import gate, layouts
from .narrate import facts
from .stream import COMPILE_POOL, PreviewWorker, StepStream


log = logging.getLogger('txt2cad.run')


@dataclass
class RunInput:
    owner: str
    project_id: str
    prompt: str
    llm: LLM
    llm_label: str
    base_version: dict[str, Any] | None
    run_id: str
    focus_guids: tuple[str, ...] = ()      # IFC GlobalIds of the parts picked in the viewer
    layout: int | None = None          # 1..3: build the brief again from scratch as that layout option


def _user_prompt(prompt: str, design: Design, checklist: list[dict[str, Any]], feedback: list[str], focus: str | None = None, layout: int | None = None) -> str:
    parts = []
    if design.rooms:
        parts.append(f"CURRENT DESIGN:\n{describe(design)}")
    if focus:
        parts.append(focus)
    parts.append(f"REQUEST:\n{prompt}")
    if layout:
        parts.append(layouts.hint(layout))
    if checklist:
        parts.append("CHECKLIST:\n" + "\n".join(f"- {r['text']}" + ("" if r.get("supported", True) else " (not supported)") for r in checklist))
    if feedback:
        parts.append("FIX THESE (they were rejected or are still unmet; emit steps that correct them):\n" + "\n".join(f"- {f}" for f in feedback))
    return "\n\n".join(parts)


def _focus_text(inp: RunInput, design: Design, guids: dict[str, str]) -> str | None:
    """The viewer sends the IFC GlobalIds of the picked parts; our guid map says which design element each one is."""
    if not inp.focus_guids or not inp.base_version:
        return None
    by_guid = {g: k.split(":", 1)[1] for k, g in guids.items() if k.startswith("element:")}
    return describe_selection(design, [by_guid[g] for g in inp.focus_guids if g in by_guid])


async def run_pipeline(inp: RunInput) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    started = time.monotonic()

    async def emit(stage: str, message: str = "", **data: Any) -> None:
        await queue.put({"stage": stage, "message": message, "data": data})

    async def body() -> None:
        try:
            await _run(inp, emit)
        except (LLMError, DesignError, repo.Conflict, gate.QualityError) as exc:
            repo.finish_run(inp.run_id, "failed", str(exc))
            await emit("failed", str(exc), kind=type(exc).__name__)
        except asyncio.CancelledError:
            repo.finish_run(inp.run_id, "cancelled")
            raise
        except Exception as exc:  # noqa: BLE001
            repo.finish_run(inp.run_id, "failed", f"{type(exc).__name__}: {exc}")
            await emit("failed", f"Unexpected error: {exc}", kind=type(exc).__name__)
        finally:
            await queue.put(None)

    task = asyncio.create_task(body())
    try:
        while (ev := await queue.get()) is not None:
            ev["t"] = round(time.monotonic() - started, 3)
            yield ev
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def _trim(feedback: list[str], keep: int = 12) -> list[str]:
    """A long list of complaints drowns the model; send the first few and say how many more there are."""
    return feedback if len(feedback) <= keep else [*feedback[:keep], f"...and {len(feedback) - keep} more of the same kind"]


async def _call_llm(inp: RunInput, request: LLMRequest, on_chunk=None, emit=None) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    cb = (lambda text: loop.call_soon_threadsafe(on_chunk, text)) if on_chunk else None
    started = time.monotonic()
    result = await asyncio.to_thread(inp.llm.complete, request, cb)
    seconds = round(time.monotonic() - started, 1)
    log.info("llm %s %s: %.1fs", inp.llm_label, request.schema_name, seconds)
    if emit:
        await emit("model_call", f"{request.schema_name} answered in {seconds} s", seconds=seconds, kind=request.schema_name)
    return result


async def _run(inp: RunInput, emit) -> None:
    base = inp.base_version
    fresh = inp.layout is not None             # a layout option starts from an empty design but is still saved after the current head
    design = Design.model_validate_json(base["design_json"]) if base and not fresh else Design()
    guids: dict[str, str] = json.loads(base["guids_json"]) if base and not fresh else {}
    mode = "edit" if base and not fresh else "design"
    await emit("phase", "Understanding the request", mode=mode, model=inp.llm_label)

    req_raw = await _call_llm(inp, LLMRequest(REQUIREMENTS_SYSTEM, inp.prompt, "requirements", REQUIREMENTS_SCHEMA, meta={"prompt": inp.prompt}), emit=emit)
    checklist = checks.merge_sizes([checks.normalise(r) for r in req_raw.get("requirements", [])], [*sizes.extract(inp.prompt), *sizes.extract_furniture(inp.prompt)])
    await emit("checklist", f"{len(checklist)} requirements", items=checklist)

    focus = None if fresh else _focus_text(inp, design, guids)
    if focus:
        await emit("selected", focus.split("\n")[0].removeprefix("SELECTED IN THE VIEWER: ").split(".")[0], text=focus)
    previews = PreviewWorker(inp.project_id, inp.run_id, emit, guids)
    approach, feedback, applied_total = "", [], 0
    started_with = len(design.rooms) if (base and not fresh) else None
    run_started, previous_open = time.monotonic(), None
    try:
        for rnd in range(config.MAX_REPAIR_ROUNDS + 1):
            if rnd:
                await emit("phase", f"Fix round {rnd}: {len(feedback)} issue(s) go back to the model")
            chunks: asyncio.Queue[str] = asyncio.Queue()
            notes_before = len(design.notes)
            stream = StepStream(design, emit, previews.submit, max_steps=config.MAX_STEPS_PER_ROUND, max_rejected=config.MAX_REJECTED_PER_ROUND)
            stop = threading.Event()
            round_started = time.monotonic()
            request = LLMRequest(BUILD_SYSTEM, _user_prompt(inp.prompt, design, checklist, feedback, focus, inp.layout), "build", BUILD_SCHEMA,
                                 meta={"prompt": inp.prompt, "has_design": bool(design.rooms), "round": rnd, "option": inp.layout or 0})
            request.stop = stop
            call = asyncio.create_task(_call_llm(inp, request, chunks.put_nowait, emit))
            while not (call.done() and chunks.empty()):
                try:
                    await stream.feed(await asyncio.wait_for(chunks.get(), 0.1))
                except asyncio.TimeoutError:
                    pass
                if not stop.is_set():
                    now = time.monotonic()
                    why = stream.limit_reason if stream.over_limit else (
                        "the model took too long on this round" if now - round_started > config.MAX_CALL_SECONDS else
                        "the run reached its time limit" if now - run_started > config.MAX_RUN_SECONDS else "")
                    if why:
                        stop.set()
                        log.warning("run %s round %d stopped: %s", inp.run_id, rnd + 1, why)
                        stream.limit_reason = stream.limit_reason or why
                        stream.over_limit = True
            try:
                result = await call
            except LLMError:
                if not stop.is_set():
                    raise
                result = {"steps": []}                # we cut the reply short on purpose; what was applied so far stands
            await stream.feed_steps(result.get("steps", []))      # anything the stream missed (non-streaming providers)
            approach = result.get("approach") or approach
            if rnd == 0 and approach:
                await emit("strategy", approach, text=approach)
            design = stream.design
            if stream.over_limit:
                design.notes.append(f"round {rnd + 1} was stopped early: {stream.limit_reason}")
            applied_total += stream.applied
            design, finishing = autofix.complete(design)          # the doors, windows and stairs every building needs, when the model left them out
            for text in finishing:
                await emit("move", text[0].upper() + text[1:], index=-1, ok=True, phase="Finishing touches", why="every building needs this", kind="finishing", facts=facts(design), removed=[])
            if finishing:
                design.notes.extend(finishing)
                previews.submit(design)
            results = checks.check(design, checklist)
            skipped = [n.removeprefix(SKIPPED_PREFIX) for n in design.notes[notes_before:] if n.startswith(SKIPPED_PREFIX)]
            feedback = [*stream.rejections, *skipped, *checks.unmet(results), *checks.completeness(design)]
            tally = {k: sum(r["status"] == k for r in results) for k in ("met", "unmet", "unsupported", "not_checked")}
            await emit("compare", f"{tally['met']} met, {tally['unmet']} unmet" + (f", {tally['not_checked']} not checked automatically" if tally["not_checked"] else "")
                       + (f", {tally['unsupported']} not buildable yet" if tally["unsupported"] else ""), items=results, tally=tally)
            feedback = _trim(feedback)
            open_items = len(checks.unmet(results)) + len(checks.completeness(design))
            if not feedback or (rnd and not stream.applied):
                break
            if previous_open is not None and open_items >= previous_open:
                break                                  # this round fixed nothing, so another one will not either
            previous_open = open_items
            if time.monotonic() - run_started > config.MAX_RUN_SECONDS:
                break
    finally:
        await previews.close()

    if not design.rooms or applied_total == 0:     # nothing changed: do not mint an identical version
        raise LLMError("nothing in the model's answer could be applied; " + (feedback[0] if feedback else "try describing the building again"))

    spec = derive(design)
    results = checks.check(design, checklist)
    reasons = gate.problems(design, results, started_with)
    if reasons:
        raise gate.QualityError("This was not saved, because it did not turn out well enough: " + "; ".join(reasons) + ". Try describing it with fewer "
                                "constraints, or name the rooms you want.")
    await emit("packaging", "Compiling IFC4")
    loop = asyncio.get_running_loop()
    model, used = await loop.run_in_executor(COMPILE_POOL, compile_ifc, spec, design.model_dump_json(), guids)
    ifc_bytes = model.to_string().encode("utf-8")
    notes = [*design.notes, *[r.note for r in spec.roofs if r.note], *[f"not built: {r['text']}" for r in results if r["status"] == "unsupported"],
             *[f"unmet: {r['text']}" for r in results if r["status"] == "unmet"], *feedback[:5]]
    number = (base["number"] if base else 0) + 1
    names = ", ".join(r.name for r in design.rooms[:12])
    summary = f"Version {number}: {len(design.levels)} level(s) and {spec.element_count()} elements, as valid IFC4. Spaces: {names}."
    saved_prompt = inp.prompt
    if inp.layout:
        label = layouts.LAYOUT_OPTIONS[inp.layout][0]
        saved_prompt = f"{inp.prompt} [layout option {inp.layout}: {label}]"
        summary += f" Layout option {inp.layout} ({label}): {layouts.difference(approach) or 'a different plan for the same brief.'}"
    version = repo.insert_version(inp.owner, inp.project_id, base["number"] if base else None, mode=mode, prompt=saved_prompt, llm_label=inp.llm_label,
                                  design=design.model_dump(), spec=spec.model_dump(), guids=used, approach=approach, notes=notes, summary=summary,
                                  ifc_bytes=ifc_bytes, requirements=results)
    repo.finish_run(inp.run_id, "succeeded", result_version_id=version["id"])
    await emit("finished", summary, number=number, version_id=version["id"], elements=spec.element_count(),
               ifc_url=f"/api/projects/{inp.project_id}/versions/{number}/ifc", notes=notes)
