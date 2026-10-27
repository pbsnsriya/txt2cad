"""The MCP server: the tools an agent sees, what they return, what they refuse, and the real protocol over stdio."""

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from app import config
from app.db import repo
from app.main import create_app

BACKEND = Path(__file__).resolve().parents[1]
HOUSE = "A one storey house with a living room, a kitchen and two bedrooms."


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    repo.init_db()
    from app.mcp_server import mcp
    return mcp


def data(result):
    """The structured answer of a tool call (a dict, or a list wrapped as {'result': [...]})."""
    assert not result.is_error, result.content
    s = result.structured_content
    return s["result"] if isinstance(s, dict) and set(s) == {"result"} else s


async def built(client, prompt=HOUSE, **extra):
    return data(await client.call_tool("build", {"prompt": prompt, "model": "practice", **extra}))


# --- what an agent sees ---------------------------------------------------------------------------------------------------------
async def test_the_tools_are_listed_with_descriptions_and_honest_annotations(server):
    async with Client(server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert set(tools) == {"capabilities", "list_projects", "list_versions", "get_version", "analysis", "build", "set_sizes", "restore_version", "export"}
        assert all(t.description and len(t.description) > 40 for t in tools.values())
        for name in ("capabilities", "list_projects", "list_versions", "get_version", "analysis"):
            assert tools[name].annotations.read_only_hint is True
        for t in tools.values():
            assert t.annotations.destructive_hint is False                                   # nothing an agent can call deletes anything
        assert tools["build"].annotations.open_world_hint is True                            # it reaches a model
        assert tools["set_sizes"].annotations.open_world_hint is False
        assert "20 to 90 seconds" in tools["build"].description and "no model" in tools["set_sizes"].description
        assert "x runs east" in (c.instructions or "")


async def test_capabilities_says_what_is_not_built(server):
    async with Client(server) as c:
        cap = data(await c.call_tool("capabilities", {}))
        ids = json.dumps(cap)
        assert "basement" in ids.lower() and "capabilities" in cap and "unsupported_words" in cap


# --- building and reading -------------------------------------------------------------------------------------------------------
async def test_a_build_makes_a_project_and_returns_what_an_agent_needs(server):
    progress = []

    async def on_progress(p, total, message):
        progress.append((p, message))

    async with Client(server) as c:
        r = data(await c.call_tool("build", {"prompt": HOUSE, "model": "practice", "project_name": "Agent house"}, progress_callback=on_progress))
        assert r["version"] == 1 and r["how_made"] == "by a model run" and r["model"].startswith("mock")
        assert {"living", "kitchen", "bedroom"} <= {x["kind"] for x in r["rooms"]}
        room = r["rooms"][0]
        assert {"id", "name", "level", "x", "y", "width", "depth", "area_m2"} <= set(room)
        assert r["footprint_m"]["width"] > 0 and r["gross_area_m2"] > 20 and r["elements"] > 20 and r["counts"]["doors"] >= 1
        assert any(q["status"] in ("met", "unmet") for q in r["requirements"])
        assert progress and any("room" in (m or "").lower() or "setup" in (m or "").lower() or m for _, m in progress)      # the agent hears the build going on
        projects = data(await c.call_tool("list_projects", {}))
        assert [p["name"] for p in projects] == ["Agent house"] and projects[0]["versions"] == 1
        versions = data(await c.call_tool("list_versions", {"project_id": r["project_id"]}))
        assert [v["version"] for v in versions] == [1] and versions[0]["request"] == HOUSE


async def test_get_version_returns_the_latest_or_a_numbered_one_and_the_full_design_on_request(server):
    async with Client(server) as c:
        first = await built(c)
        pid = first["project_id"]
        got = data(await c.call_tool("get_version", {"project_id": pid}))
        assert got["version"] == 1 and "design" not in got
        full = data(await c.call_tool("get_version", {"project_id": pid, "version": 1, "full": True}))
        assert {"rooms", "doors", "windows", "levels"} <= set(full["design"])
        assert full["design"]["rooms"][0]["id"] == first["rooms"][0]["id"]


async def test_building_with_a_project_id_edits_the_latest_version(server, monkeypatch):
    from app import service

    class Edit:                                                                        # a model that answers an edit with a pitched roof
        name, vision = "edit", False

        def complete(self, request, on_text=None):
            return {"requirements": []} if request.schema_name == "requirements" else {"steps": [{"step": "roof", "kind": "gable", "pitch": 30}], "approach": "a gable roof"}

    async with Client(server) as c:
        first = await built(c)
        assert first["roof"]["type"] == "flat"
        monkeypatch.setattr(service, "make_llm", lambda profile: Edit())
        second = await built(c, "Give it a gable roof.", project_id=first["project_id"])
        assert second["version"] == 2 and second["project_id"] == first["project_id"] and second["roof"]["type"] == "gable"
        assert data(await c.call_tool("list_versions", {"project_id": first["project_id"]}))[-1]["version"] == 2


async def test_a_build_that_cannot_be_done_is_an_error_and_saves_nothing(server):
    async with Client(server) as c:
        first = await built(c)
        failed = await c.call_tool("build", {"prompt": "Add a second bathroom.", "project_id": first["project_id"], "model": "practice"})
        assert failed.is_error and "could be applied" in "".join(getattr(x, "text", "") for x in failed.content)
        assert len(data(await c.call_tool("list_versions", {"project_id": first["project_id"]}))) == 1


async def test_analysis_gives_the_design_check_and_quantities(server):
    async with Client(server) as c:
        r = await built(c)
        a = data(await c.call_tool("analysis", {"project_id": r["project_id"]}))
        assert a["disclaimer"] and a["clauses"] and a["quantities"] and a["totals"]["elements"] > 0
        assert {"title", "status", "measured", "fix"} <= set(a["clauses"][0])


# --- sizes by hand --------------------------------------------------------------------------------------------------------------
async def test_set_sizes_changes_a_room_with_no_model_and_saves_a_new_version(server):
    async with Client(server) as c:
        r = await built(c)
        room = r["rooms"][0]
        out = data(await c.call_tool("set_sizes", {"project_id": r["project_id"], "rooms": [{"room": room["id"], "width": room["width"] + 1}]}))
        assert out["version"] == 2 and out["how_made"] == "by hand, with no model"
        assert next(x for x in out["rooms"] if x["id"] == room["id"])["width"] == room["width"] + 1
        wide = data(await c.call_tool("set_sizes", {"project_id": r["project_id"], "building_width": out["footprint_m"]["width"] + 2}))
        assert wide["version"] == 3 and wide["footprint_m"]["width"] > out["footprint_m"]["width"]


async def test_restore_brings_an_earlier_version_back_as_a_new_one(server):
    async with Client(server) as c:
        r = await built(c)
        room = r["rooms"][0]
        await c.call_tool("set_sizes", {"project_id": r["project_id"], "rooms": [{"room": room["id"], "width": room["width"] + 1}]})
        back = data(await c.call_tool("restore_version", {"project_id": r["project_id"], "version": 1}))
        assert back["version"] == 3 and back["how_made"] == "restored from an earlier version"
        assert next(x for x in back["rooms"] if x["id"] == room["id"])["width"] == room["width"]
        assert len(data(await c.call_tool("list_versions", {"project_id": r["project_id"]}))) == 3          # nothing was deleted


# --- export ------------------------------------------------------------------------------------------------------------------------
async def test_export_writes_each_format_and_never_overwrites(server, tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    async with Client(server) as c:
        r = await built(c, project_name="My House")
        pid = r["project_id"]
        files = {}
        for fmt, start in (("ifc", b"ISO-10303-21"), ("dxf", b"0\nSECTION"), ("svg", b"<svg"), ("html", b"<!doctype html>"), ("design_json", b"{")):
            e = data(await c.call_tool("export", {"project_id": pid, "format": fmt, "directory": str(out_dir)}))
            body = Path(e["path"]).read_bytes()
            assert body.lstrip().startswith(start) or start in body[:200], fmt
            assert e["bytes"] == len(body) and e["version"] == 1 and Path(e["path"]).parent == out_dir.resolve()
            files[fmt] = Path(e["path"]).name
        assert files["ifc"] == "My-House-v1.ifc" and files["html"] == "My-House-v1.html"
        again = data(await c.call_tool("export", {"project_id": pid, "format": "ifc", "directory": str(out_dir)}))
        assert Path(again["path"]).name == "My-House-v1-2.ifc"                                 # the first file is untouched
        default = data(await c.call_tool("export", {"project_id": pid, "format": "svg"}))
        assert Path(default["path"]).parent == config.DATA_DIR / "exports"


# --- what it refuses -------------------------------------------------------------------------------------------------------------
async def test_bad_requests_come_back_as_errors_in_words(server, tmp_path):
    async with Client(server) as c:
        r = await built(c)
        pid = r["project_id"]
        cases = [
            ("get_version", {"project_id": "nope"}, "not found"),
            ("get_version", {"project_id": pid, "version": 9}, "not found"),
            ("list_versions", {"project_id": "nope"}, "no project"),
            ("set_sizes", {"project_id": pid, "rooms": [{"room": "nonexistent", "width": 4}]}, "no room"),
            ("set_sizes", {"project_id": pid, "rooms": [{"room": r["rooms"][0]["id"], "width": 0.3}]}, ""),
            ("set_sizes", {"project_id": pid}, "either"),
            ("set_sizes", {"project_id": pid, "rooms": [{"room": r["rooms"][0]["id"], "width": 5}], "building_width": 12}, "either"),
            ("export", {"project_id": pid, "format": "pdf"}, "unknown format"),
            ("export", {"project_id": pid, "format": "ifc", "directory": str(tmp_path / "missing")}, "existing folder"),
            ("build", {"prompt": ""}, ""),
            ("build", {"prompt": "x" * 9000}, ""),
            ("build", {"prompt": HOUSE, "project_id": "nope", "model": "practice"}, "no project"),
            ("build", {"prompt": HOUSE, "model": "gpt-nothing"}, "unknown model"),
            ("restore_version", {"project_id": pid, "version": 99}, "not found"),
        ]
        for name, args, words in cases:
            result = await c.call_tool(name, args)
            assert result.is_error, (name, args)
            assert words in "".join(getattr(x, "text", "") for x in result.content).lower(), (name, args, result.content)


async def test_the_gemini_model_is_refused_clearly_when_it_has_no_key(server):
    async with Client(server) as c:
        result = await c.call_tool("build", {"prompt": HOUSE, "model": "gemini"})
        assert result.is_error
        text = "".join(getattr(x, "text", "") for x in result.content)
        assert "not ready" in text and "GEMINI_API_KEY" in text


async def test_no_key_or_path_can_be_passed_in_a_tool_call(server):
    async with Client(server) as c:
        for t in (await c.list_tools()).tools:
            props = " ".join((t.input_schema or {}).get("properties", {}).keys()).lower()
            assert "key" not in props and "token" not in props and "password" not in props, t.name


# --- shared with the app ---------------------------------------------------------------------------------------------------------
async def test_what_an_agent_builds_is_what_the_app_shows(server):
    async with Client(server) as c:
        r = await built(c, project_name="Shared")
    with TestClient(create_app()) as api:
        listed = api.get("/api/projects").json()
        assert [p["name"] for p in listed] == ["Shared"]
        detail = api.get(f"/api/projects/{r['project_id']}").json()
        assert detail["head"]["number"] == 1 and len(detail["head"]["design"]["rooms"]) == len(r["rooms"])
        assert api.get(f"/api/projects/{r['project_id']}/versions/1/ifc").content.startswith(b"ISO-10303-21")


# --- the real protocol over stdio ----------------------------------------------------------------------------------------------
async def test_a_client_can_start_the_server_as_a_program_and_use_it(tmp_path):
    env = {**os.environ, "TXT2CAD_DATA_DIR": str(tmp_path / "data"), "TXT2CAD_DB_PATH": str(tmp_path / "data" / "s.sqlite3"), "GEMINI_API_KEY": ""}
    params = StdioServerParameters(command=sys.executable, args=[str(BACKEND / "run_mcp.py")], env=env, cwd=str(tmp_path))          # started from some other folder
    async with Client(params, read_timeout_seconds=120) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert {"build", "set_sizes", "export"} <= names
        r = data(await c.call_tool("build", {"prompt": HOUSE, "model": "practice"}))
        assert r["version"] == 1
        out = tmp_path / "files"
        out.mkdir()
        e = data(await c.call_tool("export", {"project_id": r["project_id"], "format": "ifc", "directory": str(out)}))
        assert Path(e["path"]).read_bytes().startswith(b"ISO-10303-21")
