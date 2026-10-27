"""HTTP API. Every handler passes the owner into the data layer; there is no way to reach a row without it."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import config, service
from ..db import repo
from ..domain import direct, envelope
from ..pipeline.run import run_pipeline
from ..service import ServiceError
from ..version import __version__

router = APIRouter(prefix="/api")
OWNER = config.LOCAL_OWNER
UUID = re.compile(r"^[0-9a-f-]{36}$")


def _nf(exc: Exception) -> HTTPException:
    return HTTPException(404, f"not found: {exc}")


def _http(exc: ServiceError) -> HTTPException:
    return HTTPException(exc.status, exc.message)


@router.get("/health")
def health() -> dict[str, Any]:
    default = repo.get_profile(OWNER, None)
    return {"ok": True, "version": __version__, "llm": {"profile": default["name"], "provider": default["provider"], "model": default["model"]}}


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    """What the tool builds and what it does not: one list for the Home screen, the composer's early warning and the docs."""
    return envelope.payload()


# --- LLM profiles -----------------------------------------------------------------------------------------------------
@router.get("/llm/profiles")
def profiles() -> list[dict[str, Any]]:
    return service.profiles()


# --- projects ---------------------------------------------------------------------------------------------------------
class NewProject(BaseModel):
    name: str = Field("Untitled", min_length=1, max_length=200)


@router.get("/projects")
def projects() -> list[dict[str, Any]]:
    return repo.list_projects(OWNER)


@router.post("/projects", status_code=201)
def create_project(body: NewProject) -> dict[str, Any]:
    return repo.create_project(OWNER, body.name)


@router.get("/projects/{pid}")
def project(pid: str) -> dict[str, Any]:
    try:
        return service.project_detail(pid)
    except ServiceError as exc:
        raise _http(exc) from exc


@router.patch("/projects/{pid}")
def rename(pid: str, body: NewProject) -> dict[str, Any]:
    try:
        return repo.rename_project(OWNER, pid, body.name)
    except repo.NotFound as exc:
        raise _nf(exc) from exc


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str) -> Response:
    try:
        repo.delete_project(OWNER, pid)
    except repo.NotFound as exc:
        raise _nf(exc) from exc
    import shutil
    shutil.rmtree(config.DATA_DIR / "projects" / pid, ignore_errors=True)
    return Response(status_code=204)


# --- runs (SSE) -------------------------------------------------------------------------------------------------------
class RunBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    base_version: int | None = None
    profile_id: str | None = None
    focus_guid: str | None = Field(None, max_length=64)   # IFC GlobalId of one element selected in the viewer
    focus_guids: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=200)   # ...or of several
    layout: int | None = Field(None, ge=1, le=3)          # build the prompt again from scratch as layout option 1..3; saved as the next version


def sse(event: dict[str, Any], seq: int) -> str:
    payload = {"seq": seq, "t": event.get("t", 0), "stage": event["stage"], "message": event.get("message", ""), "data": event.get("data", {})}
    return f"event: {event['stage']}\ndata: {json.dumps(payload)}\n\n"


@router.post("/projects/{pid}/runs")
async def run(pid: str, body: RunBody) -> StreamingResponse:
    try:
        inp = service.prepare_run(pid, body.prompt, base_version=body.base_version, profile_id=body.profile_id,
                                  focus_guids=tuple(dict.fromkeys([*([body.focus_guid] if body.focus_guid else []), *body.focus_guids])), layout=body.layout)
    except ServiceError as exc:
        raise _http(exc) from exc

    async def stream() -> AsyncIterator[str]:
        agen = run_pipeline(inp)
        seq = 0
        nxt: asyncio.Future | None = None
        try:
            while True:
                nxt = nxt or asyncio.ensure_future(agen.__anext__())
                done, _ = await asyncio.wait({nxt}, timeout=config.STREAM_PING_S)
                if not done:
                    yield ": ping\n\n"
                    continue
                try:
                    ev = nxt.result()
                except StopAsyncIteration:
                    return
                nxt = None
                seq += 1
                yield sse(ev, seq)
        finally:
            if nxt and not nxt.done():
                nxt.cancel()
                await asyncio.gather(nxt, return_exceptions=True)   # let the generator leave its await before closing it
            await agen.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/files/previews/{pid}/{run_id}/{n}.ifc")
def preview(pid: str, run_id: str, n: int) -> FileResponse:
    if not (UUID.match(pid) and UUID.match(run_id)):
        raise HTTPException(404, "not found")
    path = config.DATA_DIR / "projects" / pid / "previews" / run_id / f"{n}.ifc"
    if not path.is_file():
        raise HTTPException(404, "preview expired")
    return FileResponse(path, media_type="application/octet-stream")


# --- versions and exports ---------------------------------------------------------------------------------------------
@router.get("/projects/{pid}/versions/{n}")
def version(pid: str, n: int) -> dict[str, Any]:
    try:
        return service.public_version(service.get_version(pid, n))  # type: ignore[return-value]
    except ServiceError as exc:
        raise _http(exc) from exc


@router.get("/projects/{pid}/versions/{n}/ifc")
def version_ifc(pid: str, n: int) -> FileResponse:
    try:
        v = service.get_version(pid, n)
    except ServiceError as exc:
        raise _http(exc) from exc
    return FileResponse(config.DATA_DIR / v["ifc_path"], media_type="application/octet-stream", filename=f"v{n}.ifc")


@router.get("/projects/{pid}/versions/{n}/export")
def export(pid: str, n: int, format: str = Query(...)) -> Response:
    try:
        out = service.export(pid, n, format)
    except ServiceError as exc:
        raise _http(exc) from exc
    headers = {"Content-Disposition": f'attachment; filename="{out.filename}"'}
    if out.path is not None:
        return FileResponse(out.path, media_type=out.media_type, filename=out.filename)
    return Response(out.data, media_type=out.media_type, headers=headers)


@router.post("/projects/{pid}/revert/{n}", status_code=201)
def revert(pid: str, n: int) -> dict[str, Any]:
    try:
        return service.revert(pid, n)
    except ServiceError as exc:
        raise _http(exc) from exc


class RoomSizeBody(BaseModel):
    room: str = Field(max_length=80)                      # the room id
    width: float | None = Field(None, gt=0, le=1000)      # east-west, metres
    depth: float | None = Field(None, gt=0, le=1000)      # north-south, metres


class SizesBody(BaseModel):
    base_version: int
    rooms: list[RoomSizeBody] = Field(default_factory=list, max_length=60)
    building_width: float | None = Field(None, gt=0, le=1000)
    building_depth: float | None = Field(None, gt=0, le=1000)


@router.post("/projects/{pid}/sizes", status_code=201)
def set_sizes(pid: str, body: SizesBody) -> dict[str, Any]:
    """Change room sizes, or the footprint of the whole building, by hand: no model is called, so it costs nothing and is immediate. Saved as the next version."""
    try:
        return service.change_sizes(pid, body.base_version, [direct.RoomSize(r.room, r.width, r.depth) for r in body.rooms], body.building_width, body.building_depth)
    except ServiceError as exc:
        raise _http(exc) from exc


@router.get("/projects/{pid}/versions/{n}/drawing")
def drawing(pid: str, n: int) -> Response:
    """The plans as SVG for the Drawings tab (inline, not a download)."""
    try:
        out = service.export(pid, n, "svg")
    except ServiceError as exc:
        raise _http(exc) from exc
    return Response(out.data, media_type="image/svg+xml")


@router.get("/projects/{pid}/versions/{n}/analysis")
def analysis(pid: str, n: int) -> dict[str, Any]:
    """Design check and quantity take-off for one version. Clause elements come with IFC GlobalIds so the viewer can show them."""
    try:
        return service.analysis(pid, n)
    except ServiceError as exc:
        raise _http(exc) from exc
