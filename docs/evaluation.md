# The evaluation set

47 requests, each with what a correct answer must contain, scored by code that looks at the finished design and not at what the model says about itself. It exists so that every change to
the prompts, the checks or the model can be judged by numbers, and so that "it works" means "it built what was asked, on these requests".

```bash
cd backend
python -m evals.run                      # the offline model: a smoke test of the harness, only the cases marked "mock"
python -m evals.run --live               # Gemini: all 47, about 25 minutes and $0.80
python -m evals.run --live --only h1,s1  # some cases;  --category sizes;  --repeat 3  to see how much a result moves
```

Results are written to `backend/evals/results/` (ignored by git) with the rooms of each result, how long it took and which checks failed. The offline part also runs in the normal test suite.

## What is checked

Every case that saves a result is checked for: it builds, room names are plain, every room can be reached by doors, every room that needs daylight has a window, every storey has a stair.
Then whatever the request asked for:

| Check | Meaning |
| --- | --- |
| storeys, rooms | The number of storeys; at least N rooms of a kind (whole words of the name or kind, so "kitchenette" is a kitchen) |
| on_level | Those rooms are on the floor the request named |
| footprint, area, room_dims | Overall size within 25 cm, total area in a range, a room's size within 15 cm either way round |
| roof, shape, courtyard | The roof type; an L or U outline; a courtyard that is open to the sky with rooms around it |
| furnished, furniture_kinds, floor, walls | Furniture in the habitable rooms, named pieces, finishes |
| unsupported | What the tool cannot build is named in the result as not built, not dropped quietly |
| kept (edits) | Rooms an edit was not about have not moved |

A case passes only when every check passes. The report also gives a mean score (the share of checks passed) so a near miss counts for more than a failure.

## Categories

Houses (10), flats (5), commercial (6), stated sizes (6), roofs (3), interiors (4), shapes (3), things not built yet (3), vague requests (2) and edits (5, each starting from a built house).
Add a case to `backend/evals/prompts.json` whenever a real request goes wrong; that is how it stays honest.

## Results

One run each, Gemini 2.5 Flash, 2026-10-16. The model gives different answers on different runs: running the same cases again moved two or three of them from pass to fail or the reverse,
so read these as a band of about three cases, and use `--repeat 3` before drawing a conclusion from a small change.

| | Before the finishing pass | After it | After it, plus named furniture and shape examples (a different day's model speed) |
| --- | --- | --- | --- |
| **Passed** | 21 of 47 | 33 of 47 | 30 of 47 |
| Mean score | 0.887 | 0.936 | 0.874 |
| Houses (10) | 3 | 6 | 6 |
| Flats (5) | 1 | 3 | 4 |
| Commercial (6) | 4 | 5 | 4 |
| Stated sizes (6) | 2 | 5 | 5 |
| Roofs (3) | 2 | 3 | 3 |
| Interiors (4) | 3 | 3 | 3 |
| Shapes (3) | 0 | 0 | 0 |
| Not built yet (3) | 0 | 2 | 1 |
| Vague (2) | 1 | 2 | 0 |
| Edits (5) | 5 | 4 | 4 |
| Median seconds | 28.9 | 22.2 | 31.0 |

The third run's drop is mostly the model, not the code: four of its failures never saved. Three (v1, v2, e5) are "the model took too long to answer" (127 s, 76 s, 64 s) and one (i3, a studio with a sofa, a double bed and a kitchen counter) was refused by the quality gate because the named pieces were counted as things not built. That was a bug and is fixed (named furniture no longer counts as evidence the building failed); the four cases have not been re-run since.

What moved the numbers: most failures at first were rooms with no way in, no window or no stair, which the model was being asked to fix over and over. The finishing pass adds them in code. What is left
is mostly layouts that cannot be fixed by adding something: a bedroom with no outside wall, a house the model did not shape as an L, a courtyard it did not leave open.

## What it does not tell you

- It is 47 requests chosen by the author. It says nothing yet about the requests real people will type; that is what [beta.md](beta.md) is for.
- A pass means the requested things are present and sized as asked, not that the plan is good architecture.
- The model's wording of an unsupported thing ("curved", "pool") is matched by keyword.
