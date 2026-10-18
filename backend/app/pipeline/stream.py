"""Applying a streamed reply step by step, and compiling previews in the background.

IfcOpenShell must not run on two threads at once, so ONE single-thread pool (COMPILE_POOL) does every compile: previews and finals.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from pydantic import ValidationError

from .. import config
from ..domain.derive import DesignError, derive, prune_blocking_furniture, prune_invalid_openings
from ..domain.design import Design
from ..domain.steps import Step, StepError, apply_step
from ..ifc.compile import compile_ifc
from ..llm.partial_json import complete_steps, peek_draft
from .narrate import facts, headline, phase_of

COMPILE_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ifc-compile")
STRUCTURAL = {"room", "rearrange", "storey", "delete"}
PREVIEW_DEBOUNCE_S = 0.15
DRAFT_EVERY_S = 0.15

Emit = Callable[..., Awaitable[None]]


@dataclass
class StepStream:
    """Feed it the growing reply text; it applies each newly completed step and records rejections."""
    design: Design
    emit: Emit
    on_applied: Callable[[Design], None]
    applied: int = 0
    seen: int = 0
    rejections: list[str] = field(default_factory=list)
    max_steps: int = config.MAX_STEPS_PER_ROUND
    max_rejected: int = config.MAX_REJECTED_PER_ROUND
    over_limit: bool = False
    limit_reason: str = ""
    _last_draft: str | None = None
    _last_draft_at: float = 0.0

    async def feed(self, text: str) -> None:
        steps, open_fragment = complete_steps(text)
        await self.feed_steps(steps)
        draft = peek_draft(open_fragment)
        now = asyncio.get_running_loop().time()
        if draft and draft != self._last_draft and now - self._last_draft_at >= DRAFT_EVERY_S:
            self._last_draft, self._last_draft_at = draft, now
            await self.emit("writing", f"Drafting {draft}", text=draft)

    async def feed_steps(self, steps: list[dict[str, Any]]) -> None:
        while self.seen < len(steps):
            if self.over_limit:                # a reply that has run away: the rest is not even read
                self.seen = len(steps)
                return
            raw = steps[self.seen]
            self.seen += 1
            await self._apply(raw)
            if len(self.rejections) >= self.max_rejected:
                self.over_limit, self.limit_reason = True, f"{len(self.rejections)} steps of this reply were rejected"
            elif self.seen >= self.max_steps:
                self.over_limit, self.limit_reason = True, f"the reply went past {self.max_steps} steps"

    async def _apply(self, raw: dict[str, Any]) -> None:
        index = self.seen
        try:
            step = Step(**raw)
            candidate = apply_step(self.design, step)
            pruned: list[str] = []
            if step.step in STRUCTURAL:           # moving walls can strand openings: drop them and say so
                candidate, pruned = prune_invalid_openings(candidate)
            elif step.step in ("door", "stair"):  # a new door or stair may land on furniture: the furniture moves out of the way
                candidate, pruned = prune_blocking_furniture(candidate)
            else:
                derive(candidate)                 # a step that makes the design unbuildable is rejected, with the reason
        except (StepError, DesignError) as exc:
            await self._reject(index, raw, str(exc))
            return
        except (ValidationError, TypeError) as exc:
            await self._reject(index, raw, f"step {index} is malformed: {exc.errors()[0]['msg'] if isinstance(exc, ValidationError) else exc}")
            return
        self.design = candidate
        self.applied += 1
        self.on_applied(candidate)
        text = headline(step, candidate) + (f" ({len(pruned)} thing(s) no longer fit and were removed)" if pruned else "")
        if pruned:
            self.design = candidate.model_copy(update={"notes": [*candidate.notes, *pruned]})
        await self.emit("move", text, index=index, ok=True, phase=phase_of(step), why=step.why, kind=step.step, facts=facts(candidate), removed=pruned)

    async def _reject(self, index: int, raw: dict[str, Any], message: str) -> None:
        self.rejections.append(f"step {index} ({raw.get('step', '?')}): {message}")
        await self.emit("move", message, index=index, ok=False, kind=raw.get("step"), error=message)


class PreviewWorker:
    """Keeps only the newest design: while a compile runs, later designs replace each other, so slow machines still keep up."""

    def __init__(self, project_id: str, run_id: str, emit: Emit, guids: dict[str, str]) -> None:
        self.dir = config.DATA_DIR / "projects" / project_id / "previews" / run_id
        self.url_base = f"/api/files/previews/{project_id}/{run_id}"
        self.emit, self.guids = emit, guids
        self.latest: Design | None = None
        self.count = 0
        self._wake = asyncio.Event()
        self._closing = False
        self._task = asyncio.create_task(self._loop())

    def submit(self, design: Design) -> None:
        self.latest = design
        self._wake.set()

    async def _loop(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await self._wake.wait()
            await asyncio.sleep(PREVIEW_DEBOUNCE_S)
            self._wake.clear()
            design, self.latest = self.latest, None
            if design is not None:
                try:
                    n = self.count + 1
                    elements = await loop.run_in_executor(COMPILE_POOL, self._compile, design, n)
                    self.count = n
                    await self.emit("preview", f"Preview {n}: {elements} elements", url=f"{self.url_base}/{n}.ifc", n=n, elements=elements)
                except Exception as exc:  # noqa: BLE001 - a failed preview must never kill the run
                    await self.emit("preview_skipped", f"Preview skipped: {exc}")
            if self._closing and self.latest is None:
                return

    def _compile(self, design: Design, n: int) -> int:
        spec = derive(design)
        model, _ = compile_ifc(spec, "", self.guids)
        self.dir.mkdir(parents=True, exist_ok=True)
        model.write(str(self.dir / f"{n}.ifc"))
        for old in sorted(self.dir.glob("*.ifc"), key=lambda p: int(p.stem))[:-config.PREVIEW_KEEP]:
            old.unlink(missing_ok=True)
        return spec.element_count()

    async def close(self) -> None:
        self._closing = True
        self._wake.set()
        await self._task
