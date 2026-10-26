# Test plan

What is tested, how, and what is checked by hand. Cases are numbered `Fxx-Hn` (happy path), `-En` (edge) and `-Nn` (negative).

Layers:

| Layer | Tool | Where |
| --- | --- | --- |
| Domain, geometry, exports, pipeline, API | pytest, practice model, no network | `backend/tests` |
| Run state, SSE reader | Vitest | `frontend/src/**/*.test.ts` |
| Whole app in a browser | Playwright, isolated backend and database, practice model | `e2e/` |
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
| F03-E2 | edge | Unpick | Highlight and chip go away | e2e |

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
| F06-H1 | happy | Plans tab | Plans of every level load | e2e |
| F06-H2 | happy | Design check, "Show in model" | Disclaimer visible, clauses with sections, returns to 3D with the elements highlighted | e2e |
| F06-H3 | happy | Quantities, type a rate | Cost and total fill in | e2e |
| F06-E1 | edge | Tabs before anything is built | Disabled with a reason | e2e |
| F06-E2 | edge | Switch tabs back and forth | The 3D viewer is not torn down | e2e |

## F07 Projects

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F07-H1 | happy | New project, reopen from the Projects sheet, reload | Right project and model each time | e2e |
| F07-H2 | happy | Delete a project | Confirm dialog focuses Cancel; Escape cancels; confirm removes it | e2e |

## F08 Look and feel

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F08-H1 | happy | Toggle theme, reload | Choice persists | e2e |
| F08-E1 | edge | Screens scanned for accessibility | No serious or critical axe violations | e2e |
| F08-E2 | edge | Contrast of every text pair in both themes | At least 4.5:1 | `design/contrast.py` |

## F03 Picking parts

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F03-H1 to H2 | happy | Click a part, then send | A tag and a viewer note; the request carries its GlobalId and shows what it was about | e2e |
| F03-H3 | happy | Shift-click more parts | One tag each, "N selected", all GlobalIds sent | e2e |
| F03-H4 | happy | Close one tag, then Unpick | Only that part leaves the selection; then none | e2e |
| F03-H5 | happy | Select area, drag a box | The box is drawn while dragging; everything it touches is tagged | e2e |
| F03-E1, E3 | edge | Orbit by dragging; click in area mode | Nothing is picked | e2e |
| F03-S | unit | Several parts, a wall between rooms, unknown ids, long selections | One block for the model, with the rooms involved | `test_selection.py` |

## F09 Stated sizes

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F09-H1 | happy | Ask for a living room 6 m by 4 m | The checklist shows the size and "asked 6.0 x 4.0 m" against what was built | e2e |
| F09-U | unit | Sizes in many spellings (by, x, sqm, square metres, feet), subjects, plots, nonsense | The right requirement, or none | `test_sizes.py` |
| F09-C | unit | Check met and unmet, either orientation, tolerance, total area across levels | Correct status, with numbers and a fix in the detail | `test_sizes.py` |

## F11 Roofs

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F11-H1 | happy | Ask for a pitched roof | A gable roof is built, the roof requirement is met, quantities show it | e2e |
| F11-U | unit | Mesh closed and outward-facing for each kind, volumes, ridge direction, shed sides, pitch limit | Exact | `test_roofs.py` |
| F11-I | unit | IFC roof type and shape, sloped area in quantities, L-shaped area stays flat with a note | As described | `test_roofs.py` |

## F12 Suggestions

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F12-H1 | happy | Finish a build, click a suggestion | The box is filled, nothing is sent | e2e |
| F12-E1 | edge | Home screen | No suggestions | e2e |
| F12-U | unit | Rules for each suggestion, names of real rooms, limit, no duplicates | As described | `test_suggest.py` |

## F13 Layout options

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F13-H1 | happy | Press "Try 3 other layouts" | Versions 2 to 4 appear, each labelled with its option and difference | e2e |
| F13-E1 | edge | Press Stop during the series | The series ends and nothing half-saved remains | e2e |
| F13-A | api | Options 1 to 3, bad option, stale base | Three different plans, 422 and 409 as expected | `test_api.py` |

## F14 Your data

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F14-H1 | happy | Open the data note on Home, open the model menu, build with the practice model | The note and the per-model destination are shown; the browser contacts only this computer | e2e |

## F15 Interiors

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F15-H1 | happy | Ask for a furnished house with oak floors and cream walls | An Interiors phase, furniture and finishes in the quantities, no more "furnish" suggestion | e2e |
| F15-H2 | happy | Build an unfurnished house | "Furnish every room" and a floor are suggested | e2e |
| F15-U | unit | Every catalogue shape stays inside its footprint; placement, overlaps, door swings; finishes; coverings with holes; IFC geometry; DXF layer; quantities; archways | As described | `test_interiors.py` |

## F16 Limits and the gate

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F16-U | unit | A model that never stops writing invalid steps | The run is cut off, fails fast and saves nothing | `test_limits.py` |
| F16-G | unit | Nothing met, one room for many, far too small, no doors, an edit that wipes the building | Refused with reasons; a sound result passes | `test_limits.py` |
| F16-M | unit | Whole-word matching, courtyards open to the sky, L and U outlines | As described | `test_matching.py` |

## F17 to F19 What it builds, feedback, pictures

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F17-H1 | happy | Open "What it builds today"; type a request that names a basement and a pool | The three groups are listed; a note names what is not built, and goes when the words do | e2e |
| F18-H1 | happy | Open Feedback after a build, rate, write, tick the box | The preview is the whole note; the request is in it only when ticked; nothing leaves the computer | e2e |
| F19-H1 | happy | Press Save picture | A real PNG named after the project and version | e2e |

## Evaluation

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| EV-1 | unit | The 47 cases are well formed; each kind of miss is caught by the scorer | As described | `test_eval.py` |
| EV-2 | smoke | The offline model passes the cases marked for it | All pass | `test_eval.py` |
| EV-3 | live | `python -m evals.run --live` | A pass rate by category; see `docs/evaluation.md` | by hand, costs about $0.80 |

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request and every push to `main`, as three parallel jobs, and none of them can be skipped:

| Job | What it runs |
| --- | --- |
| Backend tests | `pytest` on the practice model, with no network and no API key |
| Frontend | `tsc --noEmit`, Vitest, the production build, and `npm audit --audit-level=high` |
| Browser tests | The Playwright suite against an isolated backend and database (Chromium), with the report kept for 7 days when it fails |

The live checks (`python -m evals.run --live`, `E2E_LIVE=1`) are not part of CI: they need a real key and cost money. Dependabot opens weekly update pull requests for the Python and npm packages and a monthly one for the workflow actions.
To make the checks block a merge, turn on branch protection for `main` in the repository settings and require the three jobs.

## F20 Sizes by hand

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F20-H1 | happy | Sizes tab, type a wider width for a room, Apply | A new version (mode ops, "by hand"); the table starts again from it; the history says "resized" | e2e |
| F20-H2 | happy | Type a new building width, Apply to the building | A new version whose summary names the building | e2e |
| F20-E1 | edge | Type 0.5 | The reason is shown and Apply stays disabled; clearing the box clears the reason | e2e |
| F20-E2 | edge | Another tab saves a version first, then Apply | "no longer the latest"; nothing extra is saved | e2e |
| F20-U | unit | Stretching, limits, finishes, furniture, GlobalIds, 409/422/404 | See `test_direct.py` and `sizes.test.ts` | pytest, Vitest |

## F21 Shareable page

| Case | Type | Steps | Expected | Auto |
| --- | --- | --- | --- | --- |
| F21-H1 | happy | Export the shareable page, save it, open the file | The model is drawn offline; no request leaves the file; a Content-Security-Policy forbids them; nothing is logged as an error | e2e |
| F21-H2 | happy | Drag, scroll, right-drag, press the view buttons, switch to orthographic and back, use the keyboard | The camera moves as asked, turning does not zoom, views end where they should (top is straight above, east is level) | e2e |
| F21-H3 | happy | Switch floors, the roof, furniture and the ground | The visible count follows; room names show only for rooms that can be seen | e2e |
| F21-H4 | happy | Hover, click and double-click an element; Esc; Save picture | It says what the element is; double-click flies to it; the picture is a real PNG | e2e |
| F21-H5 | happy | Controls help, dark theme, a phone-width screen | The dialog opens and closes; the theme changes; the options sit behind a button; no sideways scroll | e2e |
| F21-H6 | happy | Look inside | The roof goes, the camera tilts down, room names appear; pressed again, it all comes back | e2e |
| F21-E1 | edge | Automatic accessibility check; a file whose data is cut out | No violations; a clear message in an alert | e2e |
| F21-U | unit | Camera maths and visibility rules; the page builder, data, escaping, determinism and privacy | See `logic.test.ts` and `test_share.py` | Vitest, pytest |

## Checked by hand

- Visual glitches in the 3D view on real graphics hardware (the automated runs use a software renderer).
- Screen-reader announcements of the live trace.
- Large models (hundreds of elements) for viewer performance.
- Gemini quality on unusual prompts.
