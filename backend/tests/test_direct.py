"""Sizes changed by hand, with no model: the domain rules and the endpoint."""

import json

import pytest
from fastapi.testclient import TestClient

from app import config
from app.domain import direct
from app.domain.derive import derive
from app.domain.design import Design
from app.domain.direct import RoomSize, SizeError
from app.domain.steps import Step, apply_step
from app.main import create_app


def build(*steps):
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


L1 = {"step": "storey", "id": "L1", "name": "Ground floor", "height": 3}


def room(name, kind, rect, level="L1", **extra):
    return {"step": "room", "level": level, "name": name, "kind": kind, "rect": rect, **extra}


def house():
    d = build(L1, room("Living", "living", [0, 0, 5, 4]), room("Kitchen", "kitchen", [5, 0, 4, 4]), room("Bedroom", "bedroom", [0, 4, 5, 4]), room("Bathroom", "bathroom", [5, 4, 4, 4]))
    for a, b in (("Living", "Kitchen"), ("Living", "Bedroom"), ("Bedroom", "Bathroom")):
        d = apply_step(d, Step(step="door", room=a, to=b))
    d = apply_step(d, Step(step="window", room="Living", side="S"))
    d = apply_step(d, Step(step="window", room="Bedroom", side="N"))
    d = apply_step(d, Step(step="furnish", room="all"))
    return d


def rect(d, rid):
    return tuple(d.room(rid).rect)


# --- rooms ------------------------------------------------------------------------------------------------------------------------------------
def test_a_wider_room_pushes_its_neighbours_along_and_everything_still_builds():
    d = house()
    out, notes = direct.resize_rooms(d, [RoomSize("living", width=6.5)])
    assert rect(out, "living")[2] == 6.5 and rect(out, "kitchen")[0] == 6.5 and rect(out, "bedroom")[2] == 6.5       # the room below grows with it: the plan stays whole
    assert notes and notes[0].startswith("set Living width 5 to 6.5")
    derive(out)


def test_a_deeper_room_and_a_shallower_one():
    d = house()
    out, _ = direct.resize_rooms(d, [RoomSize("living", depth=5)])
    assert rect(out, "living")[3] == 5 and rect(out, "bedroom")[1] == 5
    out2, _ = direct.resize_rooms(d, [RoomSize("living", depth=3)])
    assert rect(out2, "living")[3] == 3
    derive(out2)


def test_width_and_depth_together_and_several_rooms():
    out, notes = direct.resize_rooms(house(), [RoomSize("living", width=6, depth=4.5), RoomSize("bathroom", width=3.5)])
    assert rect(out, "living")[2:] == (6, 4.5) and rect(out, "bathroom")[2] == 3.5 and len(notes) >= 3
    derive(out)


def test_ids_stay_so_the_ifc_guids_stay():
    d = house()
    out, _ = direct.resize_rooms(d, [RoomSize("living", width=6.5)])
    assert [r.id for r in out.rooms] == [r.id for r in d.rooms] and {r.name for r in out.rooms} == {r.name for r in d.rooms}


def test_finishes_survive_a_resize():
    d = apply_step(house(), Step(step="finish", room="living", floor="oak"))
    out, _ = direct.resize_rooms(d, [RoomSize("living", width=6)])
    assert out.room("living").floor == d.room("living").floor and out.room("living").floor


def test_furniture_is_laid_out_again_in_a_resized_room_and_left_alone_elsewhere():
    d = house()
    out, _ = direct.resize_rooms(d, [RoomSize("living", width=6.5)])
    assert any(f.room == "living" for f in out.furniture)
    assert [f for f in out.furniture if f.room == "bathroom"] == [f for f in d.furniture if f.room == "bathroom"] or rect(out, "bathroom") != rect(d, "bathroom")
    derive(out)


def test_doors_and_windows_that_no_longer_fit_are_replaced_by_the_finishing_pass():
    d = house()
    out, _ = direct.resize_rooms(d, [RoomSize("bedroom", width=3.2)])        # the door and the window may lose their wall
    from app.domain import checks
    assert checks.completeness(out) == []
    derive(out)


@pytest.mark.parametrize("edit", [RoomSize("living", width=1.0), RoomSize("living", depth=99), RoomSize("living", width=0.2)])
def test_sizes_outside_the_limits_are_refused_in_words(edit):
    with pytest.raises(SizeError) as e:
        direct.resize_rooms(house(), [edit])
    assert "between" in str(e.value)


def test_a_size_that_would_squeeze_a_neighbour_is_refused():
    d = build(L1, room("A", "living", [0, 0, 4, 4]), room("C", "bedroom", [1, 4, 2.5, 4]))        # C sits under the middle of A
    with pytest.raises(SizeError) as e:
        direct.resize_rooms(d, [RoomSize("a", width=1.5)])                                         # shrinking A by 2.5 m would leave C with no width
    assert "narrower" in str(e.value)


def test_unknown_rooms_and_unchanged_sizes_are_refused():
    with pytest.raises(SizeError):
        direct.resize_rooms(house(), [RoomSize("nonexistent", width=5)])
    with pytest.raises(SizeError) as e:
        direct.resize_rooms(house(), [RoomSize("living", width=5, depth=4)])
    assert "already" in str(e.value)
    with pytest.raises(SizeError):
        direct.resize_rooms(house(), [])


# --- the building -----------------------------------------------------------------------------------------------------------------------------
def test_the_whole_building_can_be_made_wider_and_keeps_its_proportions():
    d = house()
    out, notes = direct.resize_building(d, width=12, depth=None)
    from app.domain import checks
    assert abs(checks._footprint(out)[0] - 12) < 0.3 and abs(checks._footprint(out)[1] - 8) < 0.3
    assert notes[0].startswith("set the building from 9 x 8 m")
    derive(out)


def test_the_building_limits():
    with pytest.raises(SizeError):
        direct.resize_building(house(), width=60, depth=None)
    with pytest.raises(SizeError):
        direct.resize_building(house(), width=9, depth=8)             # the size it is
    with pytest.raises(SizeError):
        direct.resize_building(house(), width=2, depth=None)


# --- the endpoint -----------------------------------------------------------------------------------------------------------------------------
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(create_app()) as c:
        yield c


def built(client):
    pid = client.post("/api/projects", json={"name": "House"}).json()["id"]
    with client.stream("POST", f"/api/projects/{pid}/runs", json={"prompt": "A one storey house with a living room, a kitchen and two bedrooms."}) as r:
        assert r.status_code == 200
        list(r.iter_lines())
    return pid, client.get(f"/api/projects/{pid}").json()["head"]


def test_the_endpoint_saves_a_new_version_without_calling_a_model(client):
    pid, head = built(client)
    room = head["design"]["rooms"][0]
    w = room["rect"][2] + 1
    r = client.post(f"/api/projects/{pid}/sizes", json={"base_version": head["number"], "rooms": [{"room": room["id"], "width": w}]})
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["number"] == head["number"] + 1 and v["mode"] == "ops" and v["llm"] == "" and "by hand" in v["summary"]
    assert next(x for x in v["design"]["rooms"] if x["id"] == room["id"])["rect"][2] == w
    ifc = client.get(f"/api/projects/{pid}/versions/{v['number']}/ifc")
    assert ifc.status_code == 200 and ifc.content.startswith(b"ISO-10303-21")


def test_the_same_guids_are_kept(client):
    import ifcopenshell
    pid, head = built(client)
    room = head["design"]["rooms"][0]
    before = ifcopenshell.file.from_string(client.get(f"/api/projects/{pid}/versions/{head['number']}/ifc").text)
    r = client.post(f"/api/projects/{pid}/sizes", json={"base_version": head["number"], "rooms": [{"room": room["id"], "depth": room["rect"][3] + 1}]})
    after = ifcopenshell.file.from_string(client.get(f"/api/projects/{pid}/versions/{r.json()['number']}/ifc").text)
    spaces = lambda m: {s.Name: s.GlobalId for s in m.by_type("IfcSpace")}
    assert spaces(before) == spaces(after)


def test_the_endpoint_says_why_it_cannot(client):
    pid, head = built(client)
    room = head["design"]["rooms"][0]
    n = head["number"]
    assert client.post(f"/api/projects/{pid}/sizes", json={"base_version": n, "rooms": [{"room": room["id"], "width": 0.5}]}).status_code == 422
    assert client.post(f"/api/projects/{pid}/sizes", json={"base_version": n, "rooms": []}).status_code == 422
    both = {"base_version": n, "rooms": [{"room": room["id"], "width": 6}], "building_width": 10}
    assert client.post(f"/api/projects/{pid}/sizes", json=both).status_code == 422
    assert client.post(f"/api/projects/{pid}/sizes", json={"base_version": n + 5, "rooms": [{"room": room["id"], "width": 6}]}).status_code == 409
    empty = client.post("/api/projects", json={"name": "Empty"}).json()["id"]
    assert client.post(f"/api/projects/{empty}/sizes", json={"base_version": 0, "rooms": [{"room": "x", "width": 3}]}).status_code == 409
    assert client.post("/api/projects/nope/sizes", json={"base_version": 1, "rooms": [{"room": "x", "width": 3}]}).status_code == 404


def test_a_stale_base_version_is_a_conflict_and_changes_nothing(client):
    pid, head = built(client)
    room = head["design"]["rooms"][0]
    first = client.post(f"/api/projects/{pid}/sizes", json={"base_version": head["number"], "rooms": [{"room": room["id"], "width": room["rect"][2] + 1}]})
    assert first.status_code == 201
    stale = client.post(f"/api/projects/{pid}/sizes", json={"base_version": head["number"], "rooms": [{"room": room["id"], "width": room["rect"][2] + 2}]})
    assert stale.status_code == 409
    assert len(client.get(f"/api/projects/{pid}").json()["versions"]) == head["number"] + 1


def test_the_whole_building_through_the_endpoint(client):
    pid, head = built(client)
    r = client.post(f"/api/projects/{pid}/sizes", json={"base_version": head["number"], "building_width": 14})
    assert r.status_code == 201, r.text
    assert "building" in r.json()["summary"]
