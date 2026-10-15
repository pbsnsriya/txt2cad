# Test plan

What is tested, how, and what is checked by hand. Cases are numbered `Fxx-Hn` (happy path), `-En` (edge) and `-Nn` (negative).

Layers:

| Layer | Tool | Where |
| --- | --- | --- |
| Domain, geometry, exports, pipeline, API | pytest, offline mock model, no network | `backend/tests` |
| Run state, SSE reader | Vitest | `frontend/src/**/*.test.ts` |
| Whole app in a browser | Playwright, isolated backend and database, offline mock model | `e2e/` |
| Real model | Playwright `@live` tests, Gemini, only with `E2E_LIVE=1` | `e2e/tests/live.spec.ts` |

Run the browser tests: `cd e2e && npm install && npm test`. Set `E2E_PYTHON` to the backend's Python if it is not `python`.
Every spec fails on a console error or a 5xx response, and the screens are scanned with axe (WCAG 2 A and AA, serious and critical).

## F01 Build a building from a sentence

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F01-H1 | happy | Home, type a two-storey house prompt, Enter | Trace shows phases, checklist met, version 1, 3D canvas, IFC downloadable and valid | e2e |
| F01-H2 | happy | Click a starter chip | Text fills the box, nothing is sent | e2e |
| F01-E1 | edge | Empty or whitespace input | Send is disabled, nothing is created | e2e |
| F01-E2 | edge | Prompt over the length limit | A readable message, no crash, no project left half-made | e2e |
| F01-E3 | edge | Emoji and accents in the prompt | Builds, name shown intact | e2e |
| F01-E4 | edge | Double Enter / double click on send | One project, one run | e2e |
| F01-E5 | edge | Reload while a run is in progress | App returns, no crash; the finished version is reachable | e2e |
| F01-E6 | edge | Backend unreachable | "Offline" status, composer disabled with a reason, no crash | e2e |
| F01-E7 | edge | 390 px wide, keyboard only | No horizontal scroll; whole flow completes without a mouse | e2e |
| F01-N1 | negative | Model returns nothing usable | Error shown in the trace, nothing saved | pytest |

## F02 Edit by prompting

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F02-H1 | happy (live) | Build a house, then "add a study next to the kitchen" | Version 2 with a Study; the kitchen window on the covered wall is dropped and noted | e2e live |
| F02-E1 | edge | An edit the mock cannot do | Alert "no applicable steps", still version 1 | e2e |
| F02-E2 | edge | Two tabs edit the same project | The second answers 409 with a clear message | e2e |
| F02-E3 | edge | Move, resize, rearrange, remove a level | Valid design, ids kept, nothing dangling | pytest |

## F03 Select an element

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F03-H1 | happy | Click the model | Element highlighted, name shown, composer says what the message is about | e2e |
| F03-H2 | happy | Send a message with a selection | The request carries the element's GlobalId | e2e |
| F03-E1 | edge | Drag to orbit | Nothing is selected | e2e |
| F03-E2 | edge | Clear selection | Highlight and chip go away | e2e |

## F04 Versions

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F04-H1 | happy | Open an older version, restore it | A new version is appended, history intact | e2e |
| F04-N1 | negative | Stale base version | 409 | pytest, e2e |

## F05 Export

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F05-H1 | happy | Export menu: IFC, DXF, SVG, JSON | Files download with readable names and valid content | e2e |
| F05-E1 | edge | Nothing built yet | Export disabled with a reason | e2e |
| F05-N1 | negative | Unknown format | 400 | pytest |

## F06 Analysis tabs

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F06-H1 | happy | Drawings | Plans of every level load | e2e |
| F06-H2 | happy | Design check, "Show in model" | Disclaimer visible, clauses with sections, returns to 3D with the elements highlighted | e2e |
| F06-H3 | happy | Quantities, type a rate | Cost and total fill in | e2e |
| F06-E1 | edge | Tabs before anything is built | Disabled with a reason | e2e |
| F06-E2 | edge | Switch tabs back and forth | The 3D viewer is not torn down | e2e |

## F07 Sessions

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F07-H1 | happy | New session, reopen from the list, reload | Right session and model each time | e2e |
| F07-H2 | happy | Delete a session | Confirm dialog focuses Cancel; Escape cancels; confirm removes it | e2e |

## F08 Look and feel

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F08-H1 | happy | Toggle theme, reload | Choice persists | e2e |
| F08-E1 | edge | Screens scanned for accessibility | No serious or critical axe violations | e2e |
| F08-E2 | edge | Contrast of every text pair in both themes | At least 4.5:1 | `design/contrast.py` |

## Checked by hand

- Visual glitches in the 3D view on real graphics hardware (the automated runs use a software renderer).
- Screen-reader announcements of the live trace.
- Large models (hundreds of elements) for viewer performance.
- Gemini quality on unusual prompts.
