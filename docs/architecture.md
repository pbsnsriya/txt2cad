# Architecture

## Shape of the system

```
 browser (React + That Open viewer)                         one machine, 127.0.0.1 only
   |  POST /runs  (SSE: events stream back)         +----------------------------------------------+
   |  GET versions, exports, analysis, drawing      | FastAPI                                      |
   +----------------------------------------------> |   api/        routes, SSE framing            |
                                                    |   pipeline/   run orchestration, previews    |
                                                    |   llm/        model interface + adapters     |
                                                    |   domain/     design, steps, derive, checks  |
                                                    |   ifc/ export/ analysis/   outputs           |
                                                    |   db/         SQLite                         |
                                                    +----------------------------------------------+
                                                       data/projects/<id>/  IFC files, previews
```

One database, one process, no queue. The only background work is a single compile thread (see "Concurrency").

## The rule that shapes everything

The model emits **steps**, never geometry. A step is a small JSON object:

```json
{"step": "room", "level": "L1", "name": "Kitchen", "kind": "kitchen", "rect": [4, 0, 4, 5], "why": "next to the hall"}
```

The vocabulary is `project, storey, room, rearrange, door, window, stair, roof, material, delete, remark`. Everything else is derived:

| Layer | What it holds | Where |
| --- | --- | --- |
| **Design** | What the model builds: levels, rooms as rectangles `[x, y, width, depth]` in metres, doors, windows, stairs. Coarse and semantic. | `domain/design.py` |
| **Steps** | The deltas the model streams. `apply_step` is pure and rejects a bad step with a message addressed to the model. | `domain/steps.py` |
| **Derive** | Design to geometry. Deterministic. | `domain/derive.py` |
| **BuildingSpec** | The geometric description every output is written from: walls, slabs, roofs, openings, stairs, spaces. | `domain/spec.py` |
| **Outputs** | IFC4, DXF, SVG, analysis. | `ifc/`, `export/`, `analysis/` |

Why this split: a small house is a few hundred tokens of design and 50-200k tokens of IFC; the geometry (placements, boolean openings,
closed polygons) is where models fail; and one derived description guarantees that the viewer and the plans agree.

## A run, step by step

`pipeline/run.py`. A run is an async generator of events.

1. **Requirements.** The model turns the prompt into a checklist of atomic, checkable facts (storeys, a room kind and count, a feature)
   with a `supported` flag. Items the tool cannot build (a porch, a pitched roof) are reported, not dropped. The checker ignores a model's
   blanket "unsupported" for things it really builds.
2. **Build, streamed.** The reply is JSON that grows. `llm/partial_json.py` extracts every *complete* object of the `steps` array as the
   text arrives; a half-written step never reaches the design, but its kind and name are used for a "drafting a window in the kitchen"
   line. Each complete step is validated, applied, and dry-run through derive; a step that would make the design unbuildable is
   rejected with the reason.
3. **Previews.** After each applied step the latest design is handed to a preview worker that derives and compiles an IFC in the
   background and announces it; the viewer swaps the model. While a compile runs, newer designs replace each other, so a slow machine
   still keeps up.
4. **Fix rounds.** Rejected steps, unmet requirements, and completeness problems (a habitable room without a window, rooms not linked by
   doors, a storey without a stair) go back to the model, up to two rounds.
5. **Pruning.** A structural step (add or move a room) can leave a door, window or stair with no wall to sit in. Those are dropped and
   the step's message says so, instead of rejecting the change the user asked for.
6. **Compile and save.** Derive, write IFC4 reusing the previous GlobalIds, insert the version in one transaction.
7. **Events.** `phase, checklist, strategy, writing, move, preview, compare, packaging, selected, model_call, finished, failed`, each with `seq` and
   `t`, and a `: ping` comment every second so no proxy buffers the stream.

Edits use the same pipeline. The model is shown the current design as compact text (rooms with rectangles, exterior sides, neighbours,
doors, windows, stairs) plus the element the user clicked, and emits only the steps that change it.

## Geometry rules

- Rectangle edges are **wall centrelines**. Along each room edge, the stretch shared with a neighbour is one partition (owned by the room
  with the smaller id); the rest is an exterior wall. Exterior walls are 0.30 m, partitions 0.12 m, slabs 0.20 m.
- Wall ends are extended by half their thickness, so corners close.
- Doors and windows are placed on wall pieces and nudged to the nearest free slot with margins; a window on a wall that is not exterior
  is an error that names the exterior sides.
- A stair is a straight flight along a wall: risers at most 0.19 m, treads 0.26 m, so a 3 m storey has 16 risers and a 3.9 m run. The
  flight must fit the room, and its top must land inside a room on the level above, which gets a stairwell cut in its slab.
- Element ids come from room ids and sides (`wall.L1.kitchen.S`, `wall.L1.hall~living`, `door.kitchen.hall`, `stair.hall`), so moving or resizing a room keeps the ids of
  walls that still exist.
- Units are metres end to end. The IFC declares metres explicitly (the IfcOpenShell default is millimetres).

## Data model

SQLite, eight tables ([schema](../backend/app/db/schema.sql)):

| Table | Purpose |
| --- | --- |
| `projects` | A project. Points at its head version. |
| `versions` | One finished version: design, derived spec, IFC GlobalId map, approach, notes, IFC path. Unique on `(project_id, number)`. |
| `requirements` | The checklist for a version, with each item's checked status. |
| `runs` | One prompt run, including ones that failed and produced no version. |
| `attachments` | Images attached to a prompt (schema in place, upload UI not built). |
| `exports` | Reserved for cached deliverables. |
| `llm_profiles` | Which model to call. The API key is never stored: `api_key_env` names an environment variable. |
| `bricks` | Reserved for reusable parametric assets. |

Access rule: every repository function takes `owner_id` and puts it in the `WHERE`. There is one owner (`local`) while the server only
listens on localhost; the column exists so authentication can be added without changing queries. Files are served by id, never by path.

## Concurrency and consistency

- **Two edits against the same version cannot both win.** An edit reads the head number and inserts `n + 1`; the unique constraint on
  `(project_id, number)` makes the loser fail with HTTP 409 and a clear message.
- **IfcOpenShell is not used from two threads.** One single-thread pool does every compile, previews and finals.
- **History is linear and append-only.** Restoring version *n* appends a copy; nothing is deleted by undoing.
- The SSE handler cancels the pipeline when the client disconnects, and awaits the cancelled read before closing the generator.

## The model interface

```python
class LLM(Protocol):
    name: str
    vision: bool
    def complete(self, request: LLMRequest, on_text: Callable[[str], None] | None) -> dict: ...
```

- `mock` runs the whole pipeline with no network (regexes and a strip packer).
- `openai_compat` talks to Gemini's OpenAI-compatible endpoint. It asks for a JSON-schema response, retries with `json_object` and
  then plain text if the endpoint rejects it, streams deltas, and accepts `reasoning_effort`.
- The JSON schemas are flat and permissive on purpose (some endpoints reject `oneOf`, bounds, or large grammars); strict validation is on
  our side, with lenient normalisation for what models actually write: `"north"` to `N`, a missing level to the newest level, a missing
  room name from its kind, `"Living Room"`, `"Bedroom 1"`, `"Hall L2"` resolved to room ids, and a clear error when a name is ambiguous.

## Frontend

- `src/ui/` is a small design system built on Radix primitives and tokens (see [design/components.md](../design/components.md)).
  Components use `bg-surface`, `text-muted`, `border-border`; there are no raw colours. Light and dark themes switch one attribute.
- `src/state/run.ts` folds the event stream into what the assistant panel shows (phases, rejected steps, checklist). It is a pure
  function with tests.
- `src/viewer/IfcViewer.ts` is the only file that knows the 3D library. It keeps one model at a time, drops stale loads when a newer one
  starts, refits the camera while a build is followed, raycasts on a click that did not drag, and highlights by IFC GlobalId.
- The 3D tab stays mounted while another tab is open, so switching tabs never tears down the WebGL context.
- `web-ifc` is pinned (`overrides`) because the WebAssembly binary must match the library's JavaScript.

## Security notes

- The server binds `127.0.0.1`; CORS allows only the dev origins.
- Everything the model returns is data validated by pydantic. There is no `eval`, and models are given no tools.
- API keys come from the environment (or an ignored `backend/.env`) and are never written to the database or logs.
- Preview files are served by validated ids; project deletion removes rows and files together.
- Uploads (when added) are to be sniffed by content, size-capped and stored by hash.

## Decisions

| Decision | Reason |
| --- | --- |
| Model emits steps, code derives geometry | Models are bad at geometry and at consistent IFC references; steps are small, validated and explainable. |
| Rectangles on a grid | The only way detailed layouts ("kitchen next to the dining room") are honoured; overlaps are caught per step. |
| Centreline rectangles | Neighbouring rooms share exactly one wall; element ids stay stable when rooms move. |
| One derived spec for every format | The viewer and the plans can never disagree. |
| SSE over POST | One-way, proxy-friendly, no WebSocket infrastructure; the build is visible step by step. |
| SQLite, plain SQL | One user, local-first, zero setup; the schema is written to move to Postgres. |
| Whole-model reload in the viewer | Correct by construction; patching meshes by id is deferred. |
| Review and quantities labelled as indicative / priceless | Rules differ by country and prices by place and date; the app shows what it can measure and says so. |
