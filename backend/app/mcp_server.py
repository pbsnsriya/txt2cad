"""txt2cad as an MCP server: an agent (Claude Code, Cursor, any MCP client) can build a building from a sentence, edit it, change sizes by hand, inspect it and export it.

    python -m app.mcp_server           speaks MCP on stdin and stdout (the usual way a client starts it)

It uses the same projects, versions and files as the app (the data folder is shared), and the same operations (`app.service`) as the HTTP API, so what an agent builds shows up in the app
and the other way round. The model's API key comes from the environment (GEMINI_API_KEY, or backend/.env), never from a tool argument. Nothing is sent anywhere except the request
to the model when a build uses one.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, AsyncIterator

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import config, service
from .db import repo
from .domain import checks, direct, envelope
from .domain.design import Design
from .domain.spec import BuildingSpec
from .pipeline.run import run_pipeline
from .service import ServiceError
from .version import __version__

log = logging.getLogger("txt2cad.mcp")

INSTRUCTIONS = """txt2cad builds houses, flats, small offices and shops (1 to 5 storeys) from a plain-language description, as an IFC4 model with DXF and SVG plans and a shareable web page.

How to use it:
1. `capabilities` says what it can and cannot build. Things it cannot build (basements, balconies, pools, curved walls) are named in the result, not drawn.
2. `build` with a prompt makes a new project and a first version. `build` with a `project_id` changes the latest version of that project (an edit). A build calls the language model and takes 20 to 90 seconds.
3. `get_version` shows the result: the rooms with their ids, positions and sizes, what was asked and whether it was met, and notes about anything the tool had to leave out.
4. To change a size, use `set_sizes`: it needs no model, is instant and costs nothing. Use `build` with a prompt for anything else (add a room, change the roof, furnish).
5. `export` writes the IFC, DXF, SVG, HTML or JSON to a folder and returns the path.

Coordinates are in metres: x runs east, y runs north, a room's `width` is its east-west size and `depth` its north-south size, and `x`, `y` is its south-west corner.
Every change is saved as a new version; nothing is overwritten, and `restore_version` brings an earlier one back."""


@asynccontextmanager
async def lifespan(_: MCPServer) -> AsyncIterator[None]:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    repo.init_db()
    yield


mcp = MCPServer("txt2cad", instructions=INSTRUCTIONS, version=__version__, lifespan=lifespan)
READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)      # makes a new version; nothing is overwritten
MODEL = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)       # also calls the language model


def _fail(exc: ServiceError) -> ToolError:
    return ToolError(exc.message)


def describe_version(pid: str, v: dict[str, Any], *, full: bool = False) -> dict[str, Any]:
    """A version as an agent needs it: ids and sizes to act on, what was asked, what was met."""
    design = Design.model_validate_json(v["design_json"])
    spec = BuildingSpec.model_validate_json(v["spec_json"])
    requirements = [{"text": r["text"], "status": r["status"], "detail": r["detail"]} for r in repo.version_requirements(service.OWNER, v["id"]) if r["status"] != "not_checked"]
    footprint = checks._footprint(design)
    out: dict[str, Any] = {
        "project_id": pid, "version": v["number"], "how_made": {"design": "by a model run", "edit": "by a model run (an edit)", "ops": "by hand, with no model", "revert": "restored from an earlier version"}.get(v["mode"], v["mode"]),
        "summary": v["summary"], "notes": json.loads(v["notes_json"]),
        "requirements": requirements,
        "footprint_m": {"width": footprint[0], "depth": footprint[1]} if footprint else None,
        "gross_area_m2": round(sum(r.rect[2] * r.rect[3] for r in design.rooms), 1),
        "levels": [{"id": lv.id, "name": lv.name, "height_m": lv.height} for lv in design.levels],
        "rooms": [{"id": r.id, "name": r.name, "kind": r.kind, "level": r.level, "x": r.rect[0], "y": r.rect[1], "width": r.rect[2], "depth": r.rect[3], "area_m2": round(r.rect[2] * r.rect[3], 1)}
                  for r in design.rooms],
        "counts": {"doors": len(design.doors), "windows": len(design.windows), "stairs": len(design.stairs), "furniture": len(design.furniture)},
        "roof": {"type": design.roof, "pitch_degrees": design.roof_pitch if design.roof != "flat" else None},
        "elements": spec.element_count(),
    }
    if full:
        out["design"] = design.model_dump()
    return out


def _exports_dir(directory: str | None) -> Path:
    if not directory:
        target = config.DATA_DIR / "exports"
        target.mkdir(parents=True, exist_ok=True)
        return target
    target = Path(directory).expanduser().resolve()
    if not target.is_dir():
        raise ToolError(f"'{directory}' is not an existing folder; create it first or leave `directory` out to use {config.DATA_DIR / 'exports'}")
    return target


# --- reading ---------------------------------------------------------------------------------------------------------------
@mcp.tool(annotations=READ)
def capabilities() -> dict[str, Any]:
    """What txt2cad builds, partly builds and does not build, and the words that tell you a request asks for something it cannot do. Read this before promising anything."""
    return envelope.payload()


@mcp.tool(annotations=READ)
def list_projects() -> list[dict[str, Any]]:
    """The projects in the data folder (the same ones the app shows), newest first, with how many versions each has."""
    out = []
    for p in repo.list_projects(service.OWNER):
        versions = repo.list_versions(service.OWNER, p["id"])
        out.append({"project_id": p["id"], "name": p["name"], "versions": len(versions), "updated_at": p.get("updated_at")})
    return out


@mcp.tool(annotations=READ)
def list_versions(project_id: str) -> list[dict[str, Any]]:
    """Every version of a project, oldest first: its number, how it was made, the request and a one-line summary."""
    try:
        repo.get_project(service.OWNER, project_id)
    except repo.NotFound as exc:
        raise ToolError(f"no project '{project_id}'") from exc
    return [{"version": v["number"], "mode": v["mode"], "request": v["prompt"], "summary": v["summary"], "created_at": v["created_at"]} for v in repo.list_versions(service.OWNER, project_id)]


@mcp.tool(annotations=READ)
def get_version(project_id: str, version: Annotated[int | None, Field(ge=1, description="Version number; the latest when left out")] = None,
                full: Annotated[bool, Field(description="Also return the whole design (doors, windows, stairs, furniture with their positions)")] = False) -> dict[str, Any]:
    """One version of a project: its rooms with ids, positions and sizes, what was asked and whether it was met, notes about what was left out, counts and the roof. Use the room ids with `set_sizes`."""
    try:
        return describe_version(project_id, service.get_version(project_id, version), full=full)
    except ServiceError as exc:
        raise _fail(exc) from exc


@mcp.tool(annotations=READ)
def analysis(project_id: str, version: Annotated[int | None, Field(ge=1)] = None) -> dict[str, Any]:
    """The design check (a few dwelling rules, labelled indicative) and the quantity take-off (areas, wall lengths, counts; no prices) of a version."""
    try:
        data = service.analysis(project_id, service.get_version(project_id, version)["number"])
    except ServiceError as exc:
        raise _fail(exc) from exc
    review = data["review"]
    return {
        "ruleset": review["ruleset"], "disclaimer": review["disclaimer"], "summary": review["summary"],
        "clauses": [{"title": c["title"], "section": c["section"], "status": c["status"], "measured": c["measured"], "required": c["required"], "fix": c["fix"]} for c in review["clauses"]],
        "quantities": data["quantities"]["rows"], "totals": data["quantities"]["totals"],
    }


# --- changing ----------------------------------------------------------------------------------------------------------------
@mcp.tool(annotations=MODEL)
async def build(prompt: Annotated[str, Field(min_length=1, max_length=8000, description="What to build, or what to change, in plain language")], ctx: Context,
                project_id: Annotated[str | None, Field(description="Change the latest version of this project; leave out to make a new project")] = None,
                project_name: Annotated[str | None, Field(max_length=200, description="Name for a new project")] = None,
                model: Annotated[str, Field(description="'default', 'practice' (offline, simple, free) or 'gemini'")] = "default") -> dict[str, Any]:
    """Build a building from a description, or change an existing one. With no `project_id` it makes a new project; with one it edits that project's latest version and saves the result as the next version.
    It calls the language model (about 1.6 US cents with Gemini) and takes 20 to 90 seconds. The result says what was built, what was asked and met, and what it had to leave out."""
    try:
        profile = service.pick_profile(model)
        if project_id:
            repo.get_project(service.OWNER, project_id)
            pid = project_id
        else:
            pid = repo.create_project(service.OWNER, (project_name or " ".join(prompt.split())[:60]) or "Untitled")["id"]
        inp = service.prepare_run(pid, prompt, profile_id=profile["id"])
    except repo.NotFound as exc:
        raise ToolError(f"no project '{project_id}'") from exc
    except ServiceError as exc:
        raise _fail(exc) from exc

    agen = run_pipeline(inp)
    last: dict[str, Any] = {"stage": "", "message": ""}
    steps = 0
    try:
        async for ev in agen:
            last = ev
            stage = ev["stage"]
            if stage == "move":
                steps += 1
                if steps % 10 == 1:
                    await ctx.report_progress(steps, None, ev.get("message") or "building")
            elif stage in ("phase", "strategy", "compare", "packaging"):
                await ctx.report_progress(steps, None, (ev.get("message") or stage)[:200])
    finally:
        await agen.aclose()
    if last["stage"] != "finished":
        raise ToolError(last.get("message") or "the build did not finish")
    number = last["data"].get("number")
    result = describe_version(pid, service.get_version(pid, number))
    result["model"] = inp.llm_label
    return result


class RoomSizeArg(BaseModel):
    room: str = Field(max_length=80, description="The room id")
    width: float | None = Field(None, gt=0, le=1000, description="East-west size in metres")
    depth: float | None = Field(None, gt=0, le=1000, description="North-south size in metres")


@mcp.tool(annotations=WRITE)
def set_sizes(project_id: str,
              rooms: Annotated[list[RoomSizeArg] | None, Field(max_length=60, description="Rooms to resize, by id (from get_version): width is east-west, depth north-south, both in metres")] = None,
              building_width: Annotated[float | None, Field(gt=0, le=1000, description="Make the whole building this wide (east-west, metres); every room is stretched evenly")] = None,
              building_depth: Annotated[float | None, Field(gt=0, le=1000, description="Make the whole building this deep (north-south, metres)")] = None) -> dict[str, Any]:
    """Change room sizes, or the size of the whole building, with no model: instant and free. The rooms beside a resized room move over, doors and windows are put back, furniture is laid out again, and the
    result is saved as the next version of the latest one. Give either `rooms` or `building_width`/`building_depth`, not both. Sizes are 1.5 to 40 m."""
    try:
        head = service.get_version(project_id, None)
        service.change_sizes(project_id, head["number"], [direct.RoomSize(r.room, r.width, r.depth) for r in rooms or []], building_width, building_depth)
        return describe_version(project_id, service.get_version(project_id, None))
    except ServiceError as exc:
        raise _fail(exc) from exc


@mcp.tool(annotations=WRITE)
def restore_version(project_id: str, version: Annotated[int, Field(ge=1)]) -> dict[str, Any]:
    """Bring an earlier version back by saving a copy of it as the newest version. Nothing is deleted."""
    try:
        service.revert(project_id, version)
        return describe_version(project_id, service.get_version(project_id, None))
    except ServiceError as exc:
        raise _fail(exc) from exc


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False))
def export(project_id: str, format: Annotated[str, Field(description="ifc (BIM file), dxf (floor plans), svg (plans as a picture), html (a shareable page that opens offline), spec_json or design_json")],
           version: Annotated[int | None, Field(ge=1)] = None,
           directory: Annotated[str | None, Field(description="An existing folder to write into; the app's exports folder when left out")] = None) -> dict[str, Any]:
    """Write a version to a file and return its path. An existing file is never overwritten: a number is added to the name instead."""
    try:
        v = service.get_version(project_id, version)
        out = service.export(project_id, v["number"], format)
    except ServiceError as exc:
        raise _fail(exc) from exc
    target = _exports_dir(directory)
    name = Path(out.filename).name
    stem, suffix = Path(name).stem, Path(name).suffix
    path, n = target / name, 1
    while path.exists():
        n += 1
        path = target / f"{stem}-{n}{suffix}"
    if out.path is not None:
        shutil.copyfile(out.path, path)
    else:
        path.write_bytes(out.data or b"")
    return {"path": str(path), "bytes": path.stat().st_size, "format": format, "version": v["number"]}


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")     # stdout belongs to the protocol
    if "--version" in sys.argv:
        print(f"txt2cad-mcp {__version__}")
        return
    mcp.run("stdio")


if __name__ == "__main__":
    main()
