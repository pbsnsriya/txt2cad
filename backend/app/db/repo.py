"""SQLite access. One function per query; every function takes owner_id and puts it in the WHERE (the access rule).

Files (IFC, previews, run logs) live under DATA_DIR; the database stores paths relative to it, with forward slashes.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .. import config

SCHEMA = Path(__file__).with_name("schema.sql")


class Conflict(Exception):
    """Another version took this number first (HTTP 409)."""


class NotFound(Exception):
    pass


def connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma journal_mode = wal")
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with tx() as c:
        if not c.execute("select 1 from sqlite_master where name = 'projects'").fetchone():
            c.executescript(SCHEMA.read_text(encoding="utf-8"))
        if not c.execute("select 1 from llm_profiles where owner_id = ?", (config.LOCAL_OWNER,)).fetchone():
            seed_profiles(c)


def seed_profiles(c: sqlite3.Connection) -> None:
    rows = [
        ("Offline mock", "mock", "", "", "", 1, "{}"),
        # a small local model cannot place rooms and openings (qwen2.5vl:7b rejected half its steps), so it only writes the room program
        ("Local (Ollama)", "openai_compat", "http://127.0.0.1:11434/v1", "qwen2.5vl:7b", "", 0, '{"planner": "program"}'),
        # reasoning_effort "low" cut Gemini 2.5 Flash from 25-48 s to about 11 s per build call with the same step quality
        ("Gemini", "openai_compat", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash", "GEMINI_API_KEY", 0,
         '{"reasoning_effort": "low"}'),
    ]
    for name, provider, url, model, env, default, options in rows:
        c.execute("insert into llm_profiles (id, owner_id, name, provider, base_url, model, api_key_env, options_json, is_default) values (?,?,?,?,?,?,?,?,?)",
                  (new_id(), config.LOCAL_OWNER, name, provider, url, model, env, options, default))


def new_id() -> str:
    return str(uuid.uuid4())


def rel(path: Path) -> str:
    return path.relative_to(config.DATA_DIR).as_posix()


# --- projects -------------------------------------------------------------------------------------------------------
def create_project(owner: str, name: str) -> dict[str, Any]:
    pid = new_id()
    with tx() as c:
        c.execute("insert into projects (id, owner_id, name) values (?,?,?)", (pid, owner, name))
    return get_project(owner, pid)


def get_project(owner: str, pid: str) -> dict[str, Any]:
    with tx() as c:
        row = c.execute("select * from projects where id = ? and owner_id = ?", (pid, owner)).fetchone()
    if row is None:
        raise NotFound(pid)
    return dict(row)


def list_projects(owner: str) -> list[dict[str, Any]]:
    with tx() as c:
        return [dict(r) for r in c.execute("select * from projects where owner_id = ? order by updated_at desc", (owner,))]


def rename_project(owner: str, pid: str, name: str) -> dict[str, Any]:
    with tx() as c:
        if c.execute("update projects set name = ? where id = ? and owner_id = ?", (name, pid, owner)).rowcount == 0:
            raise NotFound(pid)
    return get_project(owner, pid)


def delete_project(owner: str, pid: str) -> None:
    with tx() as c:
        if c.execute("delete from projects where id = ? and owner_id = ?", (pid, owner)).rowcount == 0:
            raise NotFound(pid)


# --- versions -------------------------------------------------------------------------------------------------------
def head_version(owner: str, pid: str) -> dict[str, Any] | None:
    project = get_project(owner, pid)
    return get_version_by_id(owner, project["head_version_id"]) if project["head_version_id"] else None


def get_version_by_id(owner: str, vid: str) -> dict[str, Any]:
    with tx() as c:
        row = c.execute("select * from versions where id = ? and owner_id = ?", (vid, owner)).fetchone()
    if row is None:
        raise NotFound(vid)
    return dict(row)


def get_version(owner: str, pid: str, number: int) -> dict[str, Any]:
    get_project(owner, pid)
    with tx() as c:
        row = c.execute("select * from versions where project_id = ? and number = ? and owner_id = ?", (pid, number, owner)).fetchone()
    if row is None:
        raise NotFound(f"{pid} v{number}")
    return dict(row)


def list_versions(owner: str, pid: str) -> list[dict[str, Any]]:
    get_project(owner, pid)
    with tx() as c:
        rows = c.execute("select id, number, parent_id, mode, prompt, llm_label, summary, created_at from versions "
                         "where project_id = ? and owner_id = ? order by number", (pid, owner))
        return [dict(r) for r in rows]


def insert_version(owner: str, pid: str, base_number: int | None, *, mode: str, prompt: str, llm_label: str, design: dict, spec: dict,
                   guids: dict[str, str], approach: str, notes: list[str], summary: str, ifc_bytes: bytes,
                   requirements: list[dict[str, Any]]) -> dict[str, Any]:
    """Append version base_number+1. If another run already took that number the unique constraint fires and we raise Conflict."""
    number = (base_number or 0) + 1
    vid = new_id()
    out = config.DATA_DIR / "projects" / pid / f"v{number}.ifc"
    with tx() as c:
        get_project_row = c.execute("select head_version_id from projects where id = ? and owner_id = ?", (pid, owner)).fetchone()
        if get_project_row is None:
            raise NotFound(pid)
        parent = get_project_row["head_version_id"]
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            c.execute(
                "insert into versions (id, project_id, owner_id, number, parent_id, mode, prompt, llm_label, design_json, spec_json, guids_json,"
                " approach, notes_json, summary, ifc_path) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (vid, pid, owner, number, parent, mode, prompt, llm_label, json.dumps(design), json.dumps(spec), json.dumps(guids),
                 approach, json.dumps(notes), summary, rel(out)))
        except sqlite3.IntegrityError as exc:
            raise Conflict(f"version {number} already exists; the project changed while this run was working") from exc
        for i, r in enumerate(requirements):
            c.execute("insert into requirements (id, version_id, position, kind, params_json, text, supported, status, detail) values (?,?,?,?,?,?,?,?,?)",
                      (new_id(), vid, i, r["kind"], json.dumps(r.get("params", {})), r["text"], 1 if r.get("supported", True) else 0,
                       r.get("status", "not_checked"), r.get("detail", "")))
        c.execute("update projects set head_version_id = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') where id = ?", (vid, pid))
        out.write_bytes(ifc_bytes)       # written inside the transaction: if the insert failed above, no stray file is left behind
    return get_version_by_id(owner, vid)


def version_requirements(owner: str, vid: str) -> list[dict[str, Any]]:
    get_version_by_id(owner, vid)
    with tx() as c:
        return [dict(r) for r in c.execute("select * from requirements where version_id = ? order by position", (vid,))]


# --- runs -----------------------------------------------------------------------------------------------------------
def create_run(owner: str, pid: str, prompt: str, base_version_id: str | None, llm_profile_id: str | None) -> str:
    get_project(owner, pid)
    rid = new_id()
    with tx() as c:
        c.execute("insert into runs (id, project_id, owner_id, base_version_id, prompt, status, llm_profile_id, started_at) "
                  "values (?,?,?,?,?, 'running', ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))", (rid, pid, owner, base_version_id, prompt, llm_profile_id))
    return rid


def finish_run(rid: str, status: str, error: str = "", result_version_id: str | None = None) -> None:
    with tx() as c:
        c.execute("update runs set status = ?, error = ?, result_version_id = ?, finished_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') where id = ?",
                  (status, error, result_version_id, rid))


# --- llm profiles ---------------------------------------------------------------------------------------------------
def list_profiles(owner: str) -> list[dict[str, Any]]:
    with tx() as c:
        return [dict(r) for r in c.execute("select * from llm_profiles where owner_id = ? order by is_default desc, name", (owner,))]


def get_profile(owner: str, profile_id: str | None) -> dict[str, Any]:
    with tx() as c:
        row = (c.execute("select * from llm_profiles where id = ? and owner_id = ?", (profile_id, owner)).fetchone() if profile_id
               else c.execute("select * from llm_profiles where owner_id = ? and is_default = 1", (owner,)).fetchone())
    if row is None:
        raise NotFound(profile_id or "default profile")
    return dict(row)
