# Your data

txt2cad is a program you run on your own computer. This page says what it keeps, what it sends and where.

## What stays on your computer

- Every project, version, IFC and DXF file, and the history of what you asked, is saved in the backend's data folder
  (`backend/data` by default: a SQLite database and one folder per project).
- There is no account and no sign-in. The app has no analytics, no tracking and no crash reporting.
- The 3D viewer's WebAssembly file and worker are shipped with the app (they used to be fetched from a public CDN at run time; they are not any more).
  A browser test (`F14-H1`) checks that, with the Practice model, the page only talks to this computer.
- The server listens on `127.0.0.1` only, and accepts requests from the app's own address only.
- Deleting a project removes its rows from the database and its folder of files.

## What is sent, and when

**Practice mode** builds designs offline with simple rules. Nothing is sent anywhere.

**Gemini** (or any other model you configure) sends, on each model call:

| Sent | When |
| --- | --- |
| The text of your request | Always |
| The checklist made from your request, including any sizes it found | Always |
| The current design as text: rooms, sizes, doors, windows, stairs | When you change an existing building |
| A description of the element you picked in the 3D view | When something is selected |
| Rejected steps and unmet items, so the model can correct them | In fix rounds |

It does **not** send the IFC or DXF files, screenshots, or anything from other projects. Images are not supported.

The destination is the address configured for the model (for Gemini, `generativelanguage.googleapis.com`, Google). The model menu shows it before
you pick. The request goes with **your own key**, so your agreement with Google applies. At the time of writing Google's pricing page says content sent
on the free tier may be used to improve its products and content sent on the paid tier is not. Check their current terms before you rely on that.

## Your key

The key lives in the backend's environment (`GEMINI_API_KEY`, for example in `backend/.env`, which is ignored by git). It is not stored in the database, not
returned by the API (only the variable's name and whether it is set) and never sent to the browser.

## What it does not do

- It does not encrypt the data folder. Anyone who can read your user account's files can read your projects.
- It does not back up anything. Copy the data folder if you want a backup.
- It does not check what you type for sensitive content before it goes to the model. Do not put anything in a request that you would not send to Google.

If txt2cad is ever offered as a hosted service, this page will need rewriting: the answers above are for the local program.
