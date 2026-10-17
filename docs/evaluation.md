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

| | Before the finishing pass | After it | After it, plus named furniture and shape examples (a different day's model speed) | Layout in code, wanted furniture, untouched rooms kept |
| --- | --- | --- | --- | --- |
| **Passed** | 21 of 47 | 33 of 47 | 30 of 47 | **42 of 47** |
| Mean score | 0.887 | 0.936 | 0.874 | 0.986 |
| Houses (10) | 3 | 6 | 6 | 9 |
| Flats (5) | 1 | 3 | 4 | 3 |
| Commercial (6) | 4 | 5 | 4 | 6 |
| Stated sizes (6) | 2 | 5 | 5 | 6 |
| Roofs (3) | 2 | 3 | 3 | 3 |
| Interiors (4) | 3 | 3 | 3 | 4 |
| Shapes (3) | 0 | 0 | 0 | 2 |
| Not built yet (3) | 0 | 2 | 1 | 3 |
| Vague (2) | 1 | 2 | 0 | 2 |
| Edits (5) | 5 | 4 | 4 | 4 |
| Median seconds | 28.9 | 22.2 | 31.0 | 31.5 |

The third run's drop was mostly the model, not the code: three cases never saved because the model took too long to answer, and one (a studio with a sofa, a double bed and a kitchen counter) was refused by the quality gate because the named pieces were counted as things not built. That bug is fixed; all four passed in the last run.

The last column is the same 47 requests after three changes made from the earlier misses: a storey the model could not draw as an L, a U or a ring around a courtyard is laid out again in code (and rooms with no outside wall are put in two rows so each has a window); pieces the request names are placed if the model left them out; and an edit puts back a room it was not about. One run, so the same three-case band applies.

What moved the numbers: most failures at first were rooms with no way in, no window or no stair, which the model was being asked to fix over and over. The finishing pass adds them in code. What is left
is a model that leaves out a room that was asked for (a second bathroom, a bedroom), a stated total area missed by a wide margin, and an edit that resizes the room it was meant to leave alone.

## What it does not tell you

- It is 47 requests chosen by the author. It says nothing yet about the requests real people will type; that is what [beta.md](beta.md) is for.
- A pass means the requested things are present and sized as asked, not that the plan is good architecture.
- The model's wording of an unsupported thing ("curved", "pool") is matched by keyword.
