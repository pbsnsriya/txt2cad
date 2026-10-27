"""The operations of the application, free of HTTP: the API routes and the MCP server both call these, so they cannot disagree.

Each raises ServiceError with an HTTP-style status (404, 409, 422) and a message in words; the routes turn that into a response and the MCP server into a tool error.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config
from .analysis.quantities import quantities
from .analysis.review import review
from .db import repo
from .domain import checks, direct
from .domain.derive import DesignError, derive
from .domain.design import Design
from .domain.spec import BuildingSpec
from .domain.suggest import suggest
from .export.dxf import dxf_text
from .export.share import share_html
from .export.svg import svg_text
from .ifc.compile import compile_ifc
from .llm.base import LLM
from .llm.mock import MockLLM
from .llm.openai_compat import OpenAICompatLLM
from .pipeline.run import RunInput
from .version import __version__

OWNER = config.LOCAL_OWNER
EXPORT_FORMATS = {"ifc", "dxf", "svg", "html", "spec_json", "design_json"}


class ServiceError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def not_found(exc: Exception) -> ServiceError:
    return ServiceError(404, f"not found: {exc}")


# --- models ---------------------------------------------------------------------------------------------------------------
def make_llm(profile: dict[str, Any]) -> LLM:
    if profile["provider"] == "mock":
        return MockLLM()
    options = json.loads(profile["options_json"] or "{}")
    return OpenAICompatLLM(profile["base_url"], profile["model"], profile["api_key_env"], options)


def profile_ready(p: dict[str, Any]) -> bool:
    return p["provider"] == "mock" or (bool(p["model"]) and (not p["api_key_env"] or bool(os.environ.get(p["api_key_env"]))))


def profiles() -> list[dict[str, Any]]:
    return [{k: p[k] for k in ("id", "name", "provider", "base_url", "model", "api_key_env", "is_default")} | {"ready": profile_ready(p)} for p in repo.list_profiles(OWNER)]


def pick_profile(choice: str | None) -> dict[str, Any]:
    """A profile by id, or by the words 'practice' / 'gemini', or the default one when nothing is said."""
    if not choice or choice == "default":
        return repo.get_profile(OWNER, None)
    wanted = choice.strip().lower()
    for p in repo.list_profiles(OWNER):
        if p["id"] == choice or p["name"].lower() == wanted or (wanted == "practice" and p["provider"] == "mock") or (wanted == "gemini" and p["name"].lower() == "gemini"):
            if not profile_ready(p):
                raise ServiceError(422, f"the model '{p['name']}' is not ready: set the {p['api_key_env'] or 'API key'} environment variable")
            return p
    raise ServiceError(422, f"unknown model '{choice}'; use 'default', 'practice' or 'gemini'")


# --- versions -------------------------------------------------------------------------------------------------------------
def public_version(v: dict[str, Any] | None) -> dict[str, Any] | None:
    if v is None:
        return None
    reqs = repo.version_requirements(OWNER, v["id"])
    design = json.loads(v["design_json"])
    return {"id": v["id"], "number": v["number"], "mode": v["mode"], "prompt": v["prompt"], "llm": v["llm_label"], "approach": v["approach"],
            "summary": v["summary"], "notes": json.loads(v["notes_json"]), "design": design, "created_at": v["created_at"],
            "suggestions": suggest(Design.model_validate(design)),
            "requirements": [{"kind": r["kind"], "text": r["text"], "supported": bool(r["supported"]), "status": r["status"], "detail": r["detail"]} for r in reqs]}


def get_version(pid: str, n: int | None) -> dict[str, Any]:
    """Version n of a project, or the latest when n is None."""
    try:
        v = repo.head_version(OWNER, pid) if n is None else repo.get_version(OWNER, pid, n)
    except repo.NotFound as exc:
        raise not_found(exc) from exc
    if v is None:
        raise ServiceError(404, "nothing has been built in this project yet")
    return v


def project_detail(pid: str) -> dict[str, Any]:
    try:
        return {"project": repo.get_project(OWNER, pid), "head": public_version(repo.head_version(OWNER, pid)), "versions": repo.list_versions(OWNER, pid)}
    except repo.NotFound as exc:
        raise not_found(exc) from exc


# --- runs -----------------------------------------------------------------------------------------------------------------
def prepare_run(pid: str, prompt: str, *, base_version: int | None = None, profile_id: str | None = None, focus_guids: tuple[str, ...] = (), layout: int | None = None) -> RunInput:
    """Everything a run needs, with the checks that stop a bad one before it starts."""
    try:
        head = repo.head_version(OWNER, pid)
        profile = repo.get_profile(OWNER, profile_id)
    except repo.NotFound as exc:
        raise not_found(exc) from exc
    if base_version is not None and (head["number"] if head else 0) != base_version:
        raise ServiceError(409, f"the project is at version {head['number'] if head else 0}, not {base_version}; reload and try again")
    llm = make_llm(profile)
    run_id = repo.create_run(OWNER, pid, prompt, head["id"] if head else None, profile["id"])
    return RunInput(OWNER, pid, prompt, llm, f"{profile['provider']}/{profile['model'] or profile['name']}", head, run_id, focus_guids, layout)


# --- sizes by hand --------------------------------------------------------------------------------------------------------
def change_sizes(pid: str, base_version: int, rooms: list[direct.RoomSize], building_width: float | None, building_depth: float | None) -> dict[str, Any]:
    """Change room sizes, or the footprint of the whole building, with no model. Saved as the next version."""
    try:
        head = repo.head_version(OWNER, pid)
    except repo.NotFound as exc:
        raise not_found(exc) from exc
    if head is None:
        raise ServiceError(409, "there is nothing to resize yet; build something first")
    if head["number"] != base_version:
        raise ServiceError(409, f"version {base_version} is no longer the latest (it is {head['number']}); open the latest version first")
    building = building_width is not None or building_depth is not None
    if building == bool(rooms):
        raise ServiceError(422, "change either some rooms or the whole building in one go")
    design = Design.model_validate_json(head["design_json"])
    try:
        new_design, notes = direct.resize_building(design, building_width, building_depth) if building else direct.resize_rooms(design, rooms)
        spec = derive(new_design)
    except (direct.SizeError, DesignError) as exc:
        raise ServiceError(422, str(exc)) from exc
    model, used = compile_ifc(spec, new_design.model_dump_json(), json.loads(head["guids_json"]))
    asked = [{"kind": r["kind"], "text": r["text"], "supported": bool(r["supported"]), "params": json.loads(r["params_json"])} for r in repo.version_requirements(OWNER, head["id"])]
    results = checks.check(new_design, asked)
    number = head["number"] + 1
    summary = f"Version {number}: sizes changed by hand, with no model. " + "; ".join(notes[:4]).capitalize() + ("." if notes else "")
    try:
        new = repo.insert_version(OWNER, pid, head["number"], mode="ops", prompt="Sizes changed by hand", llm_label="", design=new_design.model_dump(), spec=spec.model_dump(), guids=used,
                                  approach="", notes=[*new_design.notes, *notes, *[f"unmet: {r['text']}" for r in results if r["status"] == "unmet"]], summary=summary,
                                  ifc_bytes=model.to_string().encode("utf-8"), requirements=results)
    except repo.Conflict as exc:
        raise ServiceError(409, str(exc)) from exc
    return public_version(new)  # type: ignore[return-value]


def revert(pid: str, n: int) -> dict[str, Any]:
    try:
        head = repo.head_version(OWNER, pid)
        old = repo.get_version(OWNER, pid, n)
    except repo.NotFound as exc:
        raise not_found(exc) from exc
    try:
        new = repo.insert_version(OWNER, pid, head["number"] if head else 0, mode="revert", prompt=f"Revert to version {n}", llm_label="", design=json.loads(old["design_json"]),
                                  spec=json.loads(old["spec_json"]), guids=json.loads(old["guids_json"]), approach=old["approach"], notes=json.loads(old["notes_json"]),
                                  summary=f"Restored version {n}.", ifc_bytes=(config.DATA_DIR / old["ifc_path"]).read_bytes(), requirements=[])
    except repo.Conflict as exc:
        raise ServiceError(409, str(exc)) from exc
    return public_version(new)  # type: ignore[return-value]


# --- exports --------------------------------------------------------------------------------------------------------------
@dataclass
class Exported:
    filename: str
    media_type: str
    data: bytes | None = None             # the file as bytes, or ...
    path: Path | None = None              # ... a file on disk that holds it


def export_stem(pid: str, n: int) -> str:
    return f"{re.sub(r'[^A-Za-z0-9_-]+', '-', repo.get_project(OWNER, pid)['name']).strip('-') or 'model'}-v{n}"


def export(pid: str, n: int, fmt: str) -> Exported:
    if fmt not in EXPORT_FORMATS:
        raise ServiceError(400, f"unknown format '{fmt}'; use one of: {', '.join(sorted(EXPORT_FORMATS))}")
    try:
        v = repo.get_version(OWNER, pid, n)
        stem = export_stem(pid, n)
        name = repo.get_project(OWNER, pid)["name"]
    except repo.NotFound as exc:
        raise not_found(exc) from exc
    if fmt == "ifc":
        return Exported(f"{stem}.ifc", "application/octet-stream", path=config.DATA_DIR / v["ifc_path"])
    if fmt == "dxf":
        return Exported(f"{stem}.dxf", "application/dxf", data=dxf_text(BuildingSpec.model_validate_json(v["spec_json"])).encode("utf-8"))
    if fmt == "svg":
        return Exported(f"{stem}.svg", "image/svg+xml", data=svg_text(BuildingSpec.model_validate_json(v["spec_json"])).encode("utf-8"))
    if fmt == "html":
        page = share_html(config.DATA_DIR / v["ifc_path"], title=name, version=n, created=v["created_at"], summary=v["summary"], app_version=__version__)
        return Exported(f"{stem}.html", "text/html; charset=utf-8", data=page.encode("utf-8"))
    body = v["spec_json"] if fmt == "spec_json" else v["design_json"]
    return Exported(f"{stem}-{fmt}.json", "application/json", data=body.encode("utf-8"))


def analysis(pid: str, n: int) -> dict[str, Any]:
    """Design check and quantity take-off for one version. Clause elements come with IFC GlobalIds so the viewer can show them."""
    v = get_version(pid, n)
    spec = BuildingSpec.model_validate_json(v["spec_json"])
    guids = json.loads(v["guids_json"])
    result = review(Design.model_validate_json(v["design_json"]), spec)
    for clause in result["clauses"]:
        clause["guids"] = [guids[f"element:{e}"] for e in clause["elements"] if f"element:{e}" in guids]
    return {"review": result, "quantities": quantities(spec)}
