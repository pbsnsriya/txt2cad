"""The shareable page: one HTML file with the model, the viewer and its styles inside."""

import base64
import gzip
import json
import re

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import config
from app.export import share
from app.main import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(create_app()) as c:
        yield c


def built(client, name="House", prompt="Two storey house with a kitchen, living room and three bedrooms, a garage. Gable roof. Furnish every room."):
    pid = client.post("/api/projects", json={"name": name}).json()["id"]
    with client.stream("POST", f"/api/projects/{pid}/runs", json={"prompt": prompt}) as r:
        assert r.status_code == 200
        list(r.iter_lines())
    return pid


def data_of(page: str) -> dict:
    packed = re.search(r'<script type="text/plain" id="model-data">([^<]*)</script>', page).group(1)
    return json.loads(gzip.decompress(base64.b64decode(packed)))


def test_the_export_is_one_html_file_named_after_the_project(client):
    pid = built(client, "My house")
    r = client.get(f"/api/projects/{pid}/versions/1/export?format=html")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert r.headers["content-disposition"] == 'attachment; filename="My-house-v1.html"'
    assert r.text.startswith("<!doctype html>") and "</html>" in r.text


def test_the_page_carries_the_model_the_viewer_and_the_styles_and_asks_nothing_of_the_network(client):
    pid = built(client)
    page = client.get(f"/api/projects/{pid}/versions/1/export?format=html").text
    assert "Content-Security-Policy" in page and "connect-src 'none'" in page and "default-src 'none'" in page
    assert not re.search(r'(?:src|href|action)\s*=\s*["\']?(?:https?:)?//', page)                  # no external resource, link or form target
    assert not re.search(r"url\(\s*['\"]?(?:https?:)?//", page)
    assert "<style>" in page and "<canvas" in page and "model-data" in page
    assert page.count("</script>") == 2                                                              # the model data and the viewer, and nothing ended early
    assert len(page) < 2_000_000


def test_the_model_data_has_the_elements_levels_rooms_and_colours(client):
    pid = built(client)
    page = client.get(f"/api/projects/{pid}/versions/1/export?format=html").text
    d = data_of(page)
    assert d["v"] == 1 and d["version"] == 1 and d["app"].startswith("txt2cad ")
    assert [l["name"] for l in d["levels"]] and len(d["levels"]) == 2
    cats = {e["cat"] for e in d["elements"]}
    assert {"wall", "floor", "roof", "opening", "stair", "furniture"} <= cats
    assert all(e["cls"] not in ("IfcSpace", "IfcOpeningElement") for e in d["elements"])
    assert {r["name"] for r in d["rooms"]} >= {"Kitchen", "Living", "Garage"}
    glass = [p for e in d["elements"] if e["cls"] == "IfcWindow" for p in e["parts"] if p["o"] < 1]
    assert glass, "windows keep their transparency"
    for e in d["elements"][:20]:
        for p in e["parts"]:
            pos = np.frombuffer(base64.b64decode(p["p"]), dtype=np.float32)
            idx = np.frombuffer(base64.b64decode(p["i"]), dtype=np.uint32)
            assert len(pos) % 3 == 0 and len(idx) % 3 == 0 and idx.max() < len(pos) // 3
            assert all(0 <= c <= 1 for c in p["c"])


def test_levels_and_elements_agree(client):
    pid = built(client)
    d = data_of(client.get(f"/api/projects/{pid}/versions/1/export?format=html").text)
    assert {e["lv"] for e in d["elements"]} <= {-1, 0, 1} and {r["lv"] for r in d["rooms"]} == {0, 1}
    roof = [e for e in d["elements"] if e["cat"] == "roof"]
    assert roof and all(e["lv"] == 1 for e in roof)                                                  # the roof goes away when only the ground floor is shown


def test_the_request_text_is_not_in_the_file_but_the_name_and_summary_are(client):
    secret = "Confidential: a house for Mrs Example at 12 Private Lane with a kitchen and a living room."
    pid = built(client, "Client house", secret)
    page = client.get(f"/api/projects/{pid}/versions/1/export?format=html").text
    assert "Mrs Example" not in page and "Private Lane" not in page
    assert "Client house" in page and "Version 1:" in page


def test_a_hostile_project_name_cannot_break_out_of_the_page(client):
    name = '<script>alert(1)</script>"><img src=x onerror=alert(2)>'
    pid = built(client, name)
    page = client.get(f"/api/projects/{pid}/versions/1/export?format=html").text
    assert "<script>alert(1)</script>" not in page and "<img src=x" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert page.count("</script>") == 2
    assert data_of(page)["title"] == name                                                            # kept exactly in the data, shown only as text by the viewer


def test_the_same_version_always_gives_the_same_file(client):
    pid = built(client)
    a = client.get(f"/api/projects/{pid}/versions/1/export?format=html").text
    b = client.get(f"/api/projects/{pid}/versions/1/export?format=html").text
    assert a == b


def test_an_unknown_version_is_a_404_and_the_other_formats_are_unchanged(client):
    pid = built(client)
    assert client.get(f"/api/projects/{pid}/versions/9/export?format=html").status_code == 404
    assert client.get(f"/api/projects/{pid}/versions/1/export?format=ifc").status_code == 200
    assert client.get(f"/api/projects/{pid}/versions/1/export?format=nope").status_code == 400


def test_pack_round_trips():
    d = {"v": 1, "x": ["é", 1.5]}
    assert json.loads(gzip.decompress(base64.b64decode(share.pack(d)))) == d
    assert share.pack(d) == share.pack(d)


def test_the_built_viewer_is_in_the_repository_and_has_no_stray_script_end():
    js = (share.ASSETS / "share-viewer.js").read_text(encoding="utf-8")
    assert len(js) > 100_000 and "txt2cadShare" in js
    assert "</script" not in share._script(js).replace("<\\/script", "")
