# API

All routes are under `/api`, JSON unless noted. The server accepts requests from its own machine only.

| Method and path | Purpose |
| --- | --- |
| `GET /health` | Liveness and the default model profile. |
| `GET /capabilities` | What the tool builds, partly builds and does not build, and the words that are flagged before you send. The Home screen and `docs/supported.md` say the same. |
| `GET /llm/profiles` | Model profiles with a `ready` flag (the key variable is set, a model is chosen). |
| `GET /projects` | Projects, newest first. |
| `POST /projects` | Create a project: `{name}`. |
| `GET /projects/{id}` | The project, its head version (design, checklist, notes) and the version list. |
| `PATCH /projects/{id}` | Rename. |
| `DELETE /projects/{id}` | Delete the project, its versions and its files. |
| `POST /projects/{id}/runs` | **SSE.** Run a prompt. Body: `{prompt, base_version?, profile_id?, focus_guids?, focus_guid?, layout?}`. `focus_guids` (up to 200) are the IFC GlobalIds of the parts picked in the viewer; `focus_guid` is the one-part form. `layout` (1 to 3) builds the prompt again from scratch as that layout option and saves it as the next version. A stale `base_version` answers 409. |
| `GET /files/previews/{project}/{run}/{n}.ifc` | A preview IFC announced by a `preview` event. Served by validated ids; old ones are pruned. |
| `GET /projects/{id}/versions/{n}` | One version's record, with `suggestions`: up to three follow-up requests worth trying, taken from the design. |
| `GET /projects/{id}/versions/{n}/ifc` | The IFC file. |
| `GET /projects/{id}/versions/{n}/export?format=` | One of `ifc, dxf, svg, spec_json, design_json`. |
| `GET /projects/{id}/versions/{n}/drawing` | The plans as an inline SVG (the Plans tab). |
| `GET /projects/{id}/versions/{n}/analysis` | The design check and the quantity take-off. Check clauses carry IFC GlobalIds so a viewer can highlight them. |
| `POST /projects/{id}/sizes` | Change room sizes (`rooms`: `[{room, width, depth}]`) or the whole footprint (`building_width`, `building_depth`) by hand, with no model. `base_version` must be the latest version, or the answer is 409. Saved as the next version with mode `ops`; 422 says why a size cannot be done. |
| `POST /projects/{id}/revert/{n}` | Append a copy of version *n* as a new version. |

## The event stream

`POST /projects/{id}/runs` answers `text/event-stream`. Each event is

```
event: move
data: {"seq": 14, "t": 8.2, "stage": "move", "message": "Kitchen on L1: 4 x 5 m, 20.0 m2", "data": {...}}
```

| Stage | Meaning |
| --- | --- |
| `phase` | A phase started (understanding the request, a fix round). |
| `checklist` | The requirements, with unsupported items flagged. |
| `strategy` | The model's approach in a sentence or two. |
| `writing` | The step being written right now, before it lands. |
| `move` | A step was applied (`ok: true`, with a sentence, the model's reason, the phase and running facts) or rejected (`ok: false`, with the reason). |
| `preview` | A preview IFC is ready (`url`, `n`, `elements`). |
| `compare` | The checklist after the build: met, unmet, not checked, not buildable. |
| `selected` | What the selected element was understood as. |
| `model_call` | A model call finished, with its duration. |
| `packaging` | The final IFC is being written. |
| `finished` | The version was saved (`number`, `elements`, `ifc_url`, `notes`). |
| `failed` | The run failed. Nothing was saved. |

A comment line `: ping` is sent every second so proxies keep the connection open; clients ignore it.

## Errors

| Status | When |
| --- | --- |
| 404 | Unknown project or version, or a project that belongs to another owner. |
| 409 | A stale `base_version`, or a version number taken by a concurrent run. |
| 400 | An unknown export format. |
