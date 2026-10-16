"""End to end through HTTP on the mock model: create a project, stream a run, read the version, export IFC and DXF."""

import io
import json

import ezdxf
import ifcopenshell
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import create_app

PROMPT = "Two storey house with a kitchen, living room and three bedrooms, a garage."


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)     # tests must not depend on the developer's real key in backend/.env
    with TestClient(create_app()) as c:
        yield c


def events(resp) -> list[dict]:
    out, stage = [], None
    for line in resp.iter_lines():
        if line.startswith("event:"):
            stage = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            out.append(json.loads(line[5:]))
            assert out[-1]["stage"] == stage
    return out


def run(client, pid, prompt=PROMPT, **extra):
    with client.stream("POST", f"/api/projects/{pid}/runs", json={"prompt": prompt, **extra}) as r:
        assert r.status_code == 200, r.read()
        return events(r)


def test_health_and_profiles(client):
    assert client.get("/api/health").json()["llm"]["provider"] == "mock"
    names = {p["name"]: p for p in client.get("/api/llm/profiles").json()}
    assert names["Practice mode"]["ready"] and not names["Gemini"]["ready"]


def test_full_run_streams_steps_and_saves_a_valid_version(client):
    pid = client.post("/api/projects", json={"name": "House"}).json()["id"]
    evs = run(client, pid)
    stages = [e["stage"] for e in evs]
    assert stages[0] == "phase" and stages[-1] == "finished" and "checklist" in stages and "strategy" in stages
    assert [e["seq"] for e in evs] == list(range(1, len(evs) + 1))
    steps = [e for e in evs if e["stage"] == "move"]
    assert len(steps) > 10 and all(s["data"]["ok"] for s in steps) and {s["data"]["phase"] for s in steps} >= {"Setup", "Rooms", "Doors and stairs", "Windows and roof"}
    assert any(e["stage"] == "preview" for e in evs)                  # previews were compiled while the reply streamed
    done = evs[-1]["data"]
    assert done["number"] == 1 and done["elements"] > 50

    head = client.get(f"/api/projects/{pid}").json()
    assert head["head"]["number"] == 1 and len(head["versions"]) == 1
    assert {r["kind"] for r in head["head"]["requirements"]} >= {"storeys", "room"}
    assert all(r["status"] == "met" for r in head["head"]["requirements"] if r["kind"] in ("storeys", "room"))
    verify = [e for e in evs if e["stage"] == "compare"][-1]
    assert verify["data"]["tally"]["unmet"] == 0 and "unmet" in verify["message"]

    ifc = client.get(f"/api/projects/{pid}/versions/1/ifc")
    model = ifcopenshell.file.from_string(ifc.text)
    assert len(model.by_type("IfcBuildingStorey")) == 2 and model.by_type("IfcWall")

    dxf = client.get(f"/api/projects/{pid}/versions/1/export", params={"format": "dxf"})
    doc = ezdxf.read(io.StringIO(dxf.text))
    assert not doc.audit().errors and len(doc.modelspace().query("HATCH")) >= 2


def test_preview_files_are_served_by_id_only(client):
    pid = client.post("/api/projects", json={}).json()["id"]
    evs = run(client, pid, "a small cabin with a kitchen")
    url = next(e for e in evs if e["stage"] == "preview")["data"]["url"]
    run_id = url.split("/")[-2]
    assert url.startswith(f"/api/files/previews/{pid}/")
    assert client.get(url).status_code == 200            # the URL the event carries must work as-is
    n = url.rsplit("/", 1)[1].split(".")[0]
    assert client.get(f"/api/files/previews/..%2f{pid}/{run_id}/{n}.ifc").status_code == 404


def test_an_edit_that_changes_nothing_is_reported_and_does_not_create_a_version(client):
    pid = client.post("/api/projects", json={}).json()["id"]
    run(client, pid)
    evs = run(client, pid, "add a basement", base_version=1)
    assert evs[-1]["stage"] == "failed" and "could be applied" in evs[-1]["message"]
    assert client.get(f"/api/projects/{pid}").json()["head"]["number"] == 1


def test_stale_base_version_is_rejected_with_409(client):
    pid = client.post("/api/projects", json={}).json()["id"]
    run(client, pid)
    r = client.post(f"/api/projects/{pid}/runs", json={"prompt": "x", "base_version": 0})
    assert r.status_code == 409


def test_revert_appends_a_copy_and_does_not_delete_history(client):
    pid = client.post("/api/projects", json={}).json()["id"]
    run(client, pid)
    r = client.post(f"/api/projects/{pid}/revert/1")
    assert r.status_code == 201 and r.json()["number"] == 2 and r.json()["mode"] == "revert"
    assert len(client.get(f"/api/projects/{pid}").json()["versions"]) == 2


def test_other_owner_cannot_see_a_project(client):
    from app.db import repo
    pid = client.post("/api/projects", json={}).json()["id"]
    with pytest.raises(repo.NotFound):
        repo.get_project("someone-else", pid)


def test_unknown_export_formats_are_a_400_and_missing_versions_a_404(client):
    pid = client.post("/api/projects", json={}).json()["id"]
    run(client, pid)
    for fmt in ("pdf", "step", "dwg"):
        assert client.get(f"/api/projects/{pid}/versions/1/export", params={"format": fmt}).status_code == 400
    assert client.get(f"/api/projects/{pid}/versions/9/ifc").status_code == 404


def test_delete_removes_rows_and_files(client, tmp_path):
    pid = client.post("/api/projects", json={}).json()["id"]
    run(client, pid)
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404 and not (tmp_path / "projects" / pid).exists()


def test_the_selected_element_reaches_the_model_as_words(client, monkeypatch):
    from app.api import routes
    from app.llm.base import LLMRequest
    seen: list[LLMRequest] = []

    class Spy:
        name, vision = "spy", False

        def complete(self, request, on_text=None):
            seen.append(request)
            return {"requirements": []} if request.schema_name == "requirements" else {"steps": [{"step": "window", "room": "kitchen", "side": "S"}]}

    pid = client.post("/api/projects", json={}).json()["id"]
    run(client, pid, "a small cabin with a kitchen and one bedroom")
    guids = json.loads(__import__("app.db.repo", fromlist=["x"]).get_version(config.LOCAL_OWNER, pid, 1)["guids_json"])
    guid = guids["element:room.L1.kitchen"]
    monkeypatch.setattr(routes, "make_llm", lambda profile: Spy())
    evs = run(client, pid, "make this room bigger", base_version=1, focus_guid=guid)
    build = [r for r in seen if r.schema_name == "build"][0]
    assert "SELECTED IN THE VIEWER: the room kitchen 'Kitchen'" in build.user
    assert any(e["stage"] == "selected" for e in evs)
    seen.clear()
    run(client, pid, "make this room bigger", base_version=2, focus_guid="0" * 22)      # an unknown id is ignored, not an error
    assert "SELECTED IN THE VIEWER" not in [r for r in seen if r.schema_name == "build"][0].user


def test_a_validation_error_is_one_readable_sentence(client):
    pid = client.post("/api/projects", json={}).json()["id"]
    r = client.post(f"/api/projects/{pid}/runs", json={"prompt": "a house " * 1200})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert r.json()["detail"].startswith("prompt:") and "8000" in r.json()["detail"]
    r = client.post(f"/api/projects/{pid}/runs", json={})
    assert r.status_code == 422 and r.json()["detail"].startswith("prompt:")


def test_stated_sizes_reach_the_checklist_and_are_measured(client):
    pid = client.post("/api/projects", json={"name": "Sizes"}).json()["id"]
    evs = run(client, pid, "A one storey house with a living room 6 m by 4 m and a kitchen.")
    items = [e for e in evs if e["stage"] == "checklist"][0]["data"]["items"]
    size = [i for i in items if i["kind"] == "dimension"]
    assert len(size) == 1 and size[0]["params"] == {"keyword": "living", "width": 6.0, "depth": 4.0}
    compared = [e for e in evs if e["stage"] == "compare"][-1]["data"]["items"]
    measured = [i for i in compared if i["kind"] == "dimension"][0]
    assert measured["status"] in ("met", "unmet") and "asked 6.0 x 4.0 m" in measured["detail"]   # the offline model does not try to hit it, but it is measured


def test_a_pitched_roof_runs_through_to_ifc_and_exports(client):
    pid = client.post("/api/projects", json={"name": "Gable"}).json()["id"]
    evs = run(client, pid, "A one storey house with a kitchen, living room and two bedrooms, with a pitched roof.")
    assert evs[-1]["stage"] == "finished"
    assert any(e["stage"] == "move" and "roof" in e["message"].lower() and "gable" in e["message"].lower() for e in evs)
    compared = [e for e in evs if e["stage"] == "compare"][-1]["data"]["items"]
    assert [i["status"] for i in compared if i["text"].lower().startswith("a gable roof")] == ["met"]
    head = client.get(f"/api/projects/{pid}").json()["head"]
    assert head["design"]["roof"] == "gable"
    model = ifcopenshell.file.from_string(client.get(f"/api/projects/{pid}/versions/1/export", params={"format": "ifc"}).text)
    [roof] = model.by_type("IfcRoof")
    assert roof.PredefinedType == "GABLE_ROOF" and roof.Representation.Representations[0].Items[0].is_a() in ("IfcTriangulatedFaceSet", "IfcPolygonalFaceSet")
    assert client.get(f"/api/projects/{pid}/versions/1/export", params={"format": "dxf"}).status_code == 200
    rows = client.get(f"/api/projects/{pid}/versions/1/analysis").json()["quantities"]["rows"]
    assert any(r["item"].startswith("Roof (gable") for r in rows)
