# API

All routes are under `/api`, JSON unless noted. The server accepts requests from its own machine only.

| Method and path | Purpose |
| --- | --- |
| `GET /health` | Liveness, the default model profile, and whether a DWG converter was found. |
| `GET /llm/profiles` | Model profiles with a `ready` flag (the key variable is set, a model is chosen). |
| `GET /projects` | Sessions, newest first. |
| `POST /projects` | Create a session: `{name}`. |
| `GET /projects/{id}` | The project, its head version (design, checklist, notes) and the version list. |
| `PATCH /projects/{id}` | Rename. |
| `DELETE /projects/{id}` | Delete the project, its versions and its files. |
| `POST /projects/{id}/runs` | **SSE.** Run a prompt. Body: `{prompt, base_version?, profile_id?, focus_guid?}`. `focus_guid` is the IFC GlobalId of the element selected in the viewer. A stale `base_version` answers 409. |
| `GET /files/previews/{project}/{run}/{n}.ifc` | A preview IFC announced by a `partial` event. Served by validated ids; old ones are pruned. |
| `GET /projects/{id}/versions/{n}` | One version's record. |
| `GET /projects/{id}/versions/{n}/ifc` | The IFC file. |
| `GET /projects/{id}/versions/{n}/export?format=` | One of `ifc, dxf, step, svg, dwg, spec_json, design_json`. `dwg` answers 409 with instructions when no converter is installed. |
| `GET /projects/{id}/versions/{n}/drawing` | The plans as an inline SVG (the Drawings tab). |
| `GET /projects/{id}/versions/{n}/analysis` | The design check and the quantity take-off. Check clauses carry IFC GlobalIds so a viewer can highlight them. |
| `POST /projects/{id}/revert/{n}` | Append a copy of version *n* as a new version. |

## The event stream

`POST /projects/{id}/runs` answers `text/event-stream`. Each event is

```
event: step
data: {"seq": 14, "t": 8.2, "stage": "step", "message": "Kitchen on L1: 4 x 5 m, 20.0 m2", "data": {...}}
```

| Stage | Meaning |
| --- | --- |
| `build` | A phase started (reading the brief, a fix round). |
| `requirements` | The checklist, with unsupported items flagged. |
| `approach` | The model's strategy in a sentence or two. |
| `draft` | The step being written right now, before it lands. |
| `step` | A step was applied (`ok: true`, with a sentence, the model's reason, the phase and running facts) or rejected (`ok: false`, with the reason). |
| `partial` | A preview IFC is ready (`url`, `n`, `elements`). |
| `verify` | The checklist after the build: met, unmet, not checked, not buildable. |
| `focus` | What the selected element was understood as. |
| `llm` | A model call finished, with its duration. |
| `compile` | The final IFC is being written. |
| `done` | The version was saved (`number`, `elements`, `ifc_url`, `notes`). |
| `error` | The run failed. Nothing was saved. |

A comment line `: ping` is sent every second so proxies keep the connection open; clients ignore it.

## Errors

| Status | When |
| --- | --- |
| 404 | Unknown project or version, or a project that belongs to another owner. |
| 409 | A stale `base_version`, a version number taken by a concurrent run, or an export that needs something missing (DWG without the converter). |
| 400 | An unknown export format. |
