# Contributing

How changes are made, named and released. The rules follow three published standards: [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/),
[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) and [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/).

## Set up once

```bash
git config core.hooksPath .githooks     # checks every commit message as you write it
```

Line endings are LF everywhere (`.gitattributes`, `.editorconfig`), whatever your operating system.

## Commit messages

```
<type>(<scope>): <description>        at most 72 characters, no full stop

<body: what and why, wrapped at about 100 characters>

<footer: Refs: #12, or BREAKING CHANGE: what breaks and what to do instead>
```

| Type | Use it for | Changes the version |
| --- | --- | --- |
| `feat` | something people can now do | minor |
| `fix` | a bug fixed | patch |
| `perf` | the same thing, faster | patch |
| `docs` | documentation only | none |
| `refactor` | code reshaped, behaviour the same | none |
| `test` | tests only | none |
| `build` | dependencies, packaging, `requirements.txt`, `package.json` | none |
| `ci` | workflows and automation | none |
| `chore` | everything else (releases, housekeeping) | none |
| `style` | formatting only | none |

A `!` after the type, or a `BREAKING CHANGE:` footer, marks a breaking change (major, or minor while the major version is 0).
The scope names the part of the code, for example `derive`, `autofix`, `api`, `viewer`, `ifc`, `dxf`, `evals`, `e2e`.
One logical change per commit: if the message needs "and", it is probably two commits.

Examples:

```
feat(autofix): add rooms the request counted and the model left out
fix(derive): keep a door off a stair well
docs: record the third evaluation run
feat(api)!: rename /runs to /builds

BREAKING CHANGE: clients must call /api/projects/{id}/builds
```

The history before version 0.7.0 was written before this convention and is not rewritten: published history is never changed. Its changes are in [CHANGELOG.md](CHANGELOG.md).

## Branches and pull requests

Trunk-based: `main` is always releasable, and work happens on short-lived branches that are merged back within days.

- Name branches `<type>/<short-description>`: `feat/archways`, `fix/stair-well-door`, `docs/evaluation`.
- Open a pull request into `main`. The three CI checks (backend, frontend, browser tests) must pass; the repository protects `main` with them.
- Merge with **squash**, so `main` gets one commit per change, and make the pull request title a Conventional Commit: it becomes the commit message.
- Delete the branch after merging.
- Never force-push `main` and never rewrite commits that are pushed.

## Versions

`MAJOR.MINOR.PATCH`, as in Semantic Versioning. The current version is in the `VERSION` file, and `GET /api/health` reports it.

**The public API** (what a version number promises) is:

1. the HTTP API under `/api` (`docs/api.md`);
2. the design and step JSON that a version stores and the model emits;
3. the structure of the exported files: IFC4 entity types and property sets, DXF layer names.

Everything else (the UI, the prompts, how rooms are laid out) can change in any version.

| Change | Before 1.0.0 | From 1.0.0 |
| --- | --- | --- |
| Breaks the public API | minor | **major** |
| Adds to it, or something people can now do | minor | minor |
| Fixes a bug | patch | patch |

Major version 0 is initial development: anything may change in a minor version, and the API is not stable. Version 1.0.0 is cut when the public API above is declared stable.
A pre-release carries a suffix, for example `1.0.0-rc.1`, and is marked as a pre-release on GitHub.
A released version is never edited: a mistake is fixed in the next version, and a bad release is superseded, not deleted.

## The changelog

[CHANGELOG.md](CHANGELOG.md) is written for people, not copied from `git log`. Whoever makes a change that people would notice adds a line under `## [Unreleased]` in the same pull request,
under **Added**, **Changed**, **Deprecated**, **Removed**, **Fixed** or **Security**. Changes that nobody would notice (tests, refactors, CI) need no line.

## Releasing

From a clean `main` with green CI:

```bash
python scripts/release.py 0.7.0 --dry-run    # look at the notes first
python scripts/release.py 0.7.0              # moves Unreleased under 0.7.0 with today's date, sets the version in VERSION and both package.json files, commits and tags
git push && git push origin v0.7.0           # the tag starts the release workflow
```

The release workflow runs the whole test suite again on the tagged commit, checks that the tag matches the `VERSION` file, and then publishes a GitHub Release whose text is the changelog section.
Tags are annotated and named `vMAJOR.MINOR.PATCH`.

To roll back, deploy the previous tag. To withdraw a release, publish a new patch version with the fix; do not delete or move tags.
