import io
import json

import pytest

from app.analysis.quantities import quantities
from app.analysis.review import review
from app.domain.derive import derive
from app.domain.steps import Step, apply_step
from app.domain.design import Design
from app.export.svg import svg_text
from tests.test_edits import house, settle


def clause(result, cid):
    return next(c for c in result["clauses"] if c["id"] == cid)


def test_the_sample_house_passes_the_structural_rules_and_fails_daylight_where_windows_are_small():
    d, spec, _ = settle(house())
    r = review(d, spec)
    assert clause(r, "exits")["status"] == "pass" and clause(r, "egress-L2")["status"] == "pass" and clause(r, "stair.hall")["status"] == "pass"
    assert clause(r, "light-living")["status"] == "fail" and "5.8 %" in clause(r, "light-living")["measured"]
    assert clause(r, "light-kitchen")["status"] == "pass" and clause(r, "escape-bed")["status"] == "pass"
    assert r["summary"]["pass"] + r["summary"]["fail"] + r["summary"]["info"] == len(r["clauses"])
    assert "Indicative only" in r["disclaimer"] and clause(r, "not-modelled")["status"] == "info"


def test_no_exterior_door_and_no_stair_are_failures_with_a_fix():
    d = Design()
    for s in ({"step": "storey", "id": "L1"}, {"step": "storey", "id": "L2"}, {"step": "room", "level": "L1", "name": "A", "rect": [0, 0, 5, 5]},
              {"step": "room", "level": "L2", "name": "B", "rect": [0, 0, 5, 5]}):
        d = apply_step(d, Step(**s))
    r = review(d, derive(d))
    assert clause(r, "exits")["status"] == "fail" and "to: outside" in clause(r, "exits")["fix"]
    assert clause(r, "egress-L2")["status"] == "fail"


def test_a_bedroom_without_a_big_enough_window_fails_the_escape_rule():
    d = Design()
    for s in ({"step": "storey", "id": "L1"}, {"step": "room", "level": "L1", "name": "Bed", "kind": "bedroom", "rect": [0, 0, 4, 4]},
              {"step": "window", "room": "Bed", "side": "S", "width": 0.5, "kind": "small"}):
        d = apply_step(d, Step(**s))
    d.windows[0].height = 0.5
    r = review(d, derive(d))
    assert clause(r, "escape-bed")["status"] == "fail"


def test_quantities_add_up():
    d, spec, _ = settle(house())
    q = quantities(spec)
    by = {(x["group"], x["item"]): x for x in q["rows"]}
    assert by[("Openings", "Windows")]["qty"] == 5 and by[("Openings", "Doors")]["qty"] == 4 and by[("Stairs", "Stair flights")]["qty"] == 1
    gross = by[("External walls", "External wall, masonry (net of openings)")]["qty"]
    raw = sum(w.length * w.height for w in spec.walls if w.external)
    openings = sum(o.width * o.height for o in spec.openings if spec.wall(o.host).external)
    assert gross == pytest.approx(raw - openings, abs=0.01)
    assert by[("Roof", "Roof (flat)")]["qty"] > 0 and q["totals"]["net_area_m2"] == pytest.approx(sum(s.area for s in spec.spaces), abs=0.1)
    l2 = by[("Floors", "Level 2: slab")]["qty"]
    l1 = by[("Floors", "Level 1: slab")]["qty"]
    assert l2 < l1 + 5 and "stairwell" in by[("Floors", "Level 2: slab")]["note"]


def test_the_svg_plan_is_a_valid_svg_with_both_levels():
    _, spec, _ = settle(house())
    svg = svg_text(spec)
    assert svg.startswith("<?xml") and "<svg" in svg and (svg.count("<path") + svg.count("<polygon")) > 10


def test_analysis_and_drawing_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import config
    from app.main import create_app
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    with TestClient(create_app()) as c:
        pid = c.post("/api/projects", json={}).json()["id"]
        with c.stream("POST", f"/api/projects/{pid}/runs", json={"prompt": "Two storey house with a kitchen, living room and three bedrooms, a garage."}) as r:
            list(r.iter_lines())
        a = c.get(f"/api/projects/{pid}/versions/1/analysis").json()
        assert a["review"]["clauses"] and a["quantities"]["rows"]
        with_guid = [cl for cl in a["review"]["clauses"] if cl["elements"]]
        assert with_guid and all(len(cl["guids"]) == len(cl["elements"]) for cl in with_guid)
        svg = c.get(f"/api/projects/{pid}/versions/1/drawing")
        assert svg.headers["content-type"].startswith("image/svg+xml") and "<svg" in svg.text
        assert c.get(f"/api/projects/{pid}/versions/1/export", params={"format": "svg"}).status_code == 200
        assert c.get(f"/api/projects/{pid}/versions/7/analysis").status_code == 404
