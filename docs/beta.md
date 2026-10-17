# Private beta: how to find out if people want this

Nothing here has been sent to anyone. It is a plan and some wording to use or change. The point is to learn, in about two weeks and with five to ten
people, whether txt2cad is worth building further and worth charging for, before spending time on billing.

## The question, and what would count as yes

Do working architects, BIM people and designers get a result they would use, and would they come back or pay for it?

| Measure | Yes looks like | Where it comes from |
| --- | --- | --- |
| A usable first result | 7 of 10 first requests give a building the person would keep working on | Watching sessions; the evaluation set for the same kinds of request |
| Time to a useful model | Under 2 minutes from opening the app | Watching sessions |
| Would use it again | 3 of 5 say they would use it again within a month, and name the job | The closing question |
| Would pay | 2 of 5 name a price they would pay without being pushed, or ask how | The closing question |
| What stops them | The same one or two reasons come up more than once | The notes sheet |

If fewer than two of the last four are met after ten sessions, the answer is "not yet": change the product, not the marketing.

## Who

Five to ten people who do concept-stage building design or BIM modelling for a living, or teach it. Not friends who are being polite. A mix helps:
an architect at a small firm, a BIM coordinator, a student or teacher, someone who builds homes. Fewer than five is a story, not evidence.

## Where to look

Places where BIM and architecture people already talk about AI tools: the OSArch community forum, the Dynamo forum, BIM and architecture groups on LinkedIn, and
the comment threads under text-to-CAD and text-to-BIM posts. Offer a 20 minute call, not a link to try on your own: watching someone use it teaches more
than a survey. Do not post the same message in many places at once, and do not message people who have not said anything about this kind of tool.

## A message to start with

> I'm building a small local tool that turns a sentence into a building model (IFC and DXF plans). It works well for plain houses and small offices and is clearly an
> early version, so I'm not selling anything. I'd like to watch two or three people use it for 20 minutes and hear what's missing. Nothing you type is stored by me;
> it runs on your computer. Would you be up for a short call this week?

Say plainly what it cannot do (see [supported.md](supported.md)), so nobody is disappointed by something you never offered.

## The 20 minute session

1. **Before (3 min).** "What do you do today when you need a quick concept model?" "What do you use?" "What takes the longest?" Do not demonstrate anything yet.
2. **Their own request (8 min).** "Describe a building you worked on recently, or one you would like to try." Let them type it. Say nothing. Note where they hesitate, what they
   change, what they check first, and whether they trust the comparison list or look at the plan.
3. **One change (4 min).** Ask them to change something by picking it in the 3D view ("make this bigger", "open this wall").
4. **After (5 min).** Ask:
   - "Would you use the result? For what, exactly?" and "What would you have to fix first?"
   - "What would stop you using this next week?"
   - "If this existed as a service, what would you expect to pay per month before it felt too cheap to trust, and where would it feel too expensive?"
   - "Who else should I show this to?"

Ask permission before keeping their request. If they say yes, add it (without their name) to `backend/evals/prompts.json` as a new case.

## What to write down

One row per session in a sheet: date, role, what they asked for, whether the first result was usable (yes, with fixes, no), time to a useful model, the first thing they fixed or
distrusted, would use again (yes, maybe, no) and for what, a price if they gave one, and any sentence worth quoting exactly. Keep quotes with permission only.

## What to do with it

- Read the sheet after every two sessions. If the same thing blocks three people, fix it before the next call.
- Put every real request that failed into the evaluation set, then make it pass.
- After ten sessions, decide against the table above, in writing, before looking at how much effort you have already put in.

## What the app already offers for this

- **Feedback** in the top bar writes a note the person can read in full and opens it as a GitHub issue; their request and the result are included only if they tick the box. Nothing is sent by the app.
- The evaluation set (`backend/evals`) tells you whether a change made things better or worse for the kinds of request people really make.
