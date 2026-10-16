"""HTTP API. Every handler passes the owner into the data layer; there is no way to reach a row without it."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import config
from ..db import repo
from ..analysis.quantities import quantities
from ..analysis.review import review
from ..domain.design import Design
from ..domain.spec import BuildingSpec
from ..domain.suggest import suggest
from ..export.dxf import dxf_text
from ..export.svg import svg_text
from ..llm.base import LLM
from ..llm.mock import MockLLM
from ..llm.openai_compat import OpenAICompatLLM
from ..pipeline.run import RunInput, run_pipeline

router = APIRouter(prefix="/api")
OWNER = config.LOCAL_OWNER
UUID = re.compile(r"^[0-9a-f-]{36}$")


def _nf(exc: Exception) -> HTTPException:
    return HTTPException(404, f"not found: {exc}")


def make_llm(profile: dict[str, Any]) -> LLM:
    if profile["provider"] == "mock":
        return MockLLM()
    options = json.loads(profile["options_json"] or "{}")
    return OpenAICompatLLM(profile["base_url"], profile["model"], profile["api_key_env"], options)


@router.get("/health")
def health() -> dict[str, Any]:
    default = repo.get_profile(OWNER, None)
    return {"ok": True, "llm": {"profile": default["name"], "provider": default["provider"], "model": default["model"]}}


# --- LLM profiles -----------------------------------------------------------------------------------------------------
@router.get("/llm/profiles")
def profiles() -> list[dict[str, Any]]:
    import os
    out = []
    for p in repo.list_profiles(OWNER):
        ready = p["provider"] == "mock" or (bool(p["model"]) and (not p["api_key_env"] or bool(os.environ.get(p["api_key_env"]))))
        out.append({k: p[k] for k in ("id", "name", "provider", "base_url", "model", "api_key_env", "is_default")} | {"ready": ready})
    return out


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
        return {"project": repo.get_project(OWNER, pid), "head": _public_version(repo.head_version(OWNER, pid)), "versions": repo.list_versions(OWNER, pid)}
    except repo.NotFound as exc:
        raise _nf(exc) from exc


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


def _public_version(v: dict[str, Any] | None) -> dict[str, Any] | None:
    if v is None:
        return None
    reqs = repo.version_requirements(OWNER, v["id"])
    design = json.loads(v["design_json"])
    return {"id": v["id"], "number": v["number"], "mode": v["mode"], "prompt": v["prompt"], "llm": v["llm_label"], "approach": v["approach"],
            "summary": v["summary"], "notes": json.loads(v["notes_json"]), "design": design, "created_at": v["created_at"],
            "suggestions": suggest(Design.model_validate(design)),
            "requirements": [{"kind": r["kind"], "text": r["text"], "supported": bool(r["supported"]), "status": r["status"], "detail": r["detail"]} for r in reqs]}


# --- runs (SSE) -------------------------------------------------------------------------------------------------------
class RunBody(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    base_version: int | None = None
    profile_id: str | None = None
    focus_guid: str | None = Field(None, max_length=64)   # IFC GlobalId of the element selected in the viewer
    layout: int | None = Field(None, ge=1, le=3)          # build the prompt again from scratch as layout option 1..3; saved as the next version


def sse(event: dict[str, Any], seq: int) -> str:
    payload = {"seq": seq, "t": event.get("t", 0), "stage": event["stage"], "message": event.get("message", ""), "data": event.get("data", {})}
    return f"event: {event['stage']}\ndata: {json.dumps(payload)}\n\n"


@router.post("/projects/{pid}/runs")
async def run(pid: str, body: RunBody) -> StreamingResponse:
    try:
        head = repo.head_version(OWNER, pid)
        profile = repo.get_profile(OWNER, body.profile_id)
    except repo.NotFound as exc:
        raise _nf(exc) from exc
    if body.base_version is not None and (head["number"] if head else 0) != body.base_version:
        raise HTTPException(409, f"the project is at version {head['number'] if head else 0}, not {body.base_version}; reload and try again")
    llm = make_llm(profile)
    run_id = repo.create_run(OWNER, pid, body.prompt, head["id"] if head else None, profile["id"])
    inp = RunInput(OWNER, pid, body.prompt, llm, f"{profile['provider']}/{profile['model'] or profile['name']}", head, run_id, body.focus_guid, body.layout)

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
        return _public_version(repo.get_version(OWNER, pid, n))  # type: ignore[return-value]
    except repo.NotFound as exc:
        raise _nf(exc) from exc


@router.get("/projects/{pid}/versions/{n}/ifc")
def version_ifc(pid: str, n: int) -> FileResponse:
    try:
        v = repo.get_version(OWNER, pid, n)
    except repo.NotFound as exc:
        raise _nf(exc) from exc
    return FileResponse(config.DATA_DIR / v["ifc_path"], media_type="application/octet-stream", filename=f"v{n}.ifc")


EXPORT_FORMATS = {"ifc", "dxf", "svg", "spec_json", "design_json"}


@router.get("/projects/{pid}/versions/{n}/export")
def export(pid: str, n: int, format: str = Query(...)) -> Response:
    if format not in EXPORT_FORMATS:
        raise HTTPException(400, f"unknown format '{format}'; use one of: {', '.join(sorted(EXPORT_FORMATS))}")
    try:
        v = repo.get_version(OWNER, pid, n)
    except repo.NotFound as exc:
        raise _nf(exc) from exc
    stem = f"{re.sub(r'[^A-Za-z0-9_-]+', '-', repo.get_project(OWNER, pid)['name']).strip('-') or 'model'}-v{n}"
    if format == "ifc":
        return FileResponse(config.DATA_DIR / v["ifc_path"], media_type="application/octet-stream", filename=f"{stem}.ifc")
    if format == "dxf":
        text = dxf_text(BuildingSpec.model_validate_json(v["spec_json"]))
        return Response(text, media_type="application/dxf", headers={"Content-Disposition": f'attachment; filename="{stem}.dxf"'})
    if format == "svg":
        return Response(svg_text(BuildingSpec.model_validate_json(v["spec_json"])), media_type="image/svg+xml",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.svg"'})
    data = v["spec_json"] if format == "spec_json" else v["design_json"]
    return JSONResponse(json.loads(data), headers={"Content-Disposition": f'attachment; filename="{stem}-{format}.json"'})


@router.post("/projects/{pid}/revert/{n}", status_code=201)
def revert(pid: str, n: int) -> dict[str, Any]:
    try:
        head = repo.head_version(OWNER, pid)
        old = repo.get_version(OWNER, pid, n)
    except repo.NotFound as exc:
        raise _nf(exc) from exc
    try:
        new = repo.insert_version(OWNER, pid, head["number"] if head else 0, mode="revert", prompt=f"Revert to version {n}", llm_label="",
                                  design=json.loads(old["design_json"]), spec=json.loads(old["spec_json"]), guids=json.loads(old["guids_json"]),
                                  approach=old["approach"], notes=json.loads(old["notes_json"]), summary=f"Restored version {n}.",
                                  ifc_bytes=(config.DATA_DIR / old["ifc_path"]).read_bytes(), requirements=[])
    except repo.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return _public_version(new)  # type: ignore[return-value]


@router.get("/projects/{pid}/versions/{n}/drawing")
def drawing(pid: str, n: int) -> Response:
    """The plans as SVG for the Drawings tab (inline, not a download)."""
    try:
        v = repo.get_version(OWNER, pid, n)
    except repo.NotFound as exc:
        raise _nf(exc) from exc
    return Response(svg_text(BuildingSpec.model_validate_json(v["spec_json"])), media_type="image/svg+xml")


@router.get("/projects/{pid}/versions/{n}/analysis")
def analysis(pid: str, n: int) -> dict[str, Any]:
    """Design check and quantity take-off for one version. Clause elements come with IFC GlobalIds so the viewer can show them."""
    try:
        v = repo.get_version(OWNER, pid, n)
    except repo.NotFound as exc:
        raise _nf(exc) from exc
    spec = BuildingSpec.model_validate_json(v["spec_json"])
    guids = json.loads(v["guids_json"])
    result = review(Design.model_validate_json(v["design_json"]), spec)
    for clause in result["clauses"]:
        clause["guids"] = [guids[f"element:{e}"] for e in clause["elements"] if f"element:{e}" in guids]
    return {"review": result, "quantities": quantities(spec)}
