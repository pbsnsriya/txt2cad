# Changelog

All notable changes to txt2cad are written here, for people, newest first.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html);
[CONTRIBUTING.md](CONTRIBUTING.md) says what counts as the public API while the major version is 0.

The first releases below were written afterwards, from the history, and tagged on the commit that finished each one.

## [Unreleased]

### Added

- A shareable page: "Shareable page (.html)" in the Export menu is one file with the model, a viewer and its styles inside, for opening offline in any browser. Turn, move and zoom the model, perspective or orthographic, top, side and 3D views, floors one at a time, layers (roof, furniture, doors and windows), "Look inside" with room names, click an element to see what it is, keyboard and touch control, light and dark themes, and Save picture. The file asks nothing of the network and does not contain your request. `GET /api/projects/{id}/versions/{n}/export?format=html`.

## [0.8.0] - 2026-10-26

### Added

- Sizes by hand: a Sizes tab lists every room with its width and depth. Type a new size, or a new footprint for the whole building, and the plan is stretched to fit and saved as a new version. No model is called, so it is instant and free. `POST /api/projects/{id}/sizes`.
- A licence: txt2cad is released under the GNU General Public License v3.0 (`LICENSE`, and the `license` field of both `package.json` files).

## [0.7.0] - 2026-10-18

### Added

- `GET /api/health` and the OpenAPI document report the application version, read from the `VERSION` file.
- A release process: `scripts/release.py` turns the Unreleased notes into a dated version, commits and tags it; pushing the tag publishes a GitHub Release with these notes once CI has passed.
- A commit-message check (`scripts/check_commit_message.py`, a git hook and a CI job for pull requests) for the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) format.
- `CONTRIBUTING.md`, a pull request template, `.editorconfig` and `.gitattributes`.

### Changed

- Every text file in the repository now has LF line endings, so a file saved on Windows no longer shows as changed on every line.

## [0.6.1] - 2026-10-18

### Added

- Continuous integration: the backend tests, the frontend type check, tests, build and audit, and the browser tests run on every push and pull request.
- Dependabot update pull requests for the Python and npm packages and the workflow actions.

### Fixed

- `pillow` is declared in `backend/requirements.txt`. ezdxf's drawing add-on needs it for the SVG plan, and a clean install failed without it.

## [0.6.0] - 2026-10-18

### Added

- A plan the model draws as the wrong shape is laid out again in code: an L, a U, a U around a courtyard, or a ring of rooms around an open courtyard. Rooms with no outside wall are put in two rows so each can have a window.
- Rooms the request counted that the model left out (a second bathroom, a bedroom, a meeting room) are added beside the others. A plain room called "Other" is named for what was asked.
- A stated room size, overall size or total area is made true by stretching or scaling the plan, so rooms keep touching.
- Pieces of furniture named in the request are placed, then the rooms are furnished around them.
- For edits: a room the edit was not about is put back as it was, and a new room is moved off the only outside wall of another room.

### Changed

- A court open to the sky is no longer part of the outline when an L or U is checked.
- A room called "Bedroom 1" that the model left as kind "other" is treated as a bedroom.
- A short outside wall takes a narrower window; furniture gives way when a finishing door needs the wall.

### Fixed

- A finishing step that fails is logged and skipped instead of ending the run.
- The quality gate no longer refuses a building only because named furniture is missing.
- The evaluation set passes 44 of 47 requests in the latest live run, up from 21 (see `docs/evaluation.md`).

## [0.5.0] - 2026-10-17

### Added

- A finishing pass adds missing doors, windows and stairs in code instead of sending the model round again.
- Rooms get plain names: no ids, level codes or slugs.
- A list of what is built, partly built and not built (`GET /api/capabilities`, the Home screen, `docs/supported.md`), and a warning under the message box when a request names something that is not built.
- An evaluation set of 47 requests, scored independently of the model (`backend/evals`, `docs/evaluation.md`).
- A Feedback dialog that writes a note you can read in full and opens a prefilled GitHub issue; nothing is sent by the app.
- Save picture: the 3D view as a PNG.
- A plan for a small beta (`docs/beta.md`).

### Changed

- Interiors gained ceiling and floor lights, a plant, corner placement and a gap from the wall.

## [0.4.0] - 2026-10-16

### Added

- Interiors: furniture, floor and wall finishes, and archways.

## [0.3.0] - 2026-10-16

### Added

- Pick several parts of the model, or drag a box around an area, and talk about them: each is a tag in the chat and goes with the message.
- Limits on a run: a cap on steps and rejected steps in a round, a stop flag, and a quality gate that refuses a result that is not usable instead of saving it.

## [0.2.0] - 2026-10-16

### Added

- Sizes in a request ("12 m by 9 m", "about 70 square metres") are read from the prompt and checked against the design.
- Gable, hip and shed roofs.
- Suggested next requests after a build; three other layouts of the same brief, built one after another and saved as new versions.
- A statement of where data goes, on the Home screen and in the model menu.
- Rearranging a storey keeps the rooms that fit.

### Changed

- The scope is Gemini for the model and IFC and DXF for the output.
- The conversation is on the left and the top bar was reshaped; the step vocabulary, element ids and labels were reworked.

### Fixed

- Three bugs found by the new browser tests, which cover every flow.

## [0.1.0] - 2026-10-12

### Added

- The first complete app: type a sentence, watch the model build step by step, see it in 3D, and keep every version.
- A backend that turns small steps into walls, slabs, openings and stairs and writes IFC4 with stable ids, and DXF floor plans.
- Projects, versions and runs stored in SQLite; runs streamed over Server-Sent Events.
- A design check and a quantity take-off.
- A React frontend with a Home screen, a workspace, a trace of the run, a version list and the analysis tabs.

[Unreleased]: https://github.com/pbsnsriya/txt2cad/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/pbsnsriya/txt2cad/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/pbsnsriya/txt2cad/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/pbsnsriya/txt2cad/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/pbsnsriya/txt2cad/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/pbsnsriya/txt2cad/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/pbsnsriya/txt2cad/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/pbsnsriya/txt2cad/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/pbsnsriya/txt2cad/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/pbsnsriya/txt2cad/releases/tag/v0.1.0
