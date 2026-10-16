"""Several parts picked in the viewer reach the model as one clear block of facts."""

from app.db import repo
from app.domain.describe import describe_selection
from app.domain.design import Design
from app.domain.steps import Step, apply_step


def build(*steps):
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


HOUSE = [
    {"step": "storey", "id": "L1", "name": "Ground floor", "height": 3},
    {"step": "room", "level": "L1", "name": "Kitchen", "kind": "kitchen", "rect": [0, 0, 4, 4]},
    {"step": "room", "level": "L1", "name": "Living", "kind": "living", "rect": [4, 0, 5, 4]},
    {"step": "door", "room": "Kitchen", "to": "Living"},
    {"step": "window", "room": "Kitchen", "side": "S"},
]


def test_one_part_is_described_with_the_instruction_about_this():
    d = build(*HOUSE)
    text = describe_selection(d, ["room.L1.kitchen"])
    assert text.startswith("SELECTED IN THE VIEWER: 1 element") and "the room kitchen 'Kitchen'" in text
    assert "this" in text and "change nothing else" in text


def test_several_parts_list_each_and_name_the_rooms_involved():
    d = build(*HOUSE)
    text = describe_selection(d, ["room.L1.living", "door.kitchen.living", "window.kitchen.S"])
    assert "3 elements" in text
    assert "the room living 'Living'" in text and "the door door.kitchen.living between Kitchen" in text and "the window window.kitchen.S" in text
    involved = next(line for line in text.splitlines() if line.startswith("ROOMS INVOLVED"))
    assert "kitchen 'Kitchen'" in involved and "living 'Living'" in involved


def test_a_wall_brings_in_the_rooms_on_both_sides():
    d = build(*HOUSE)
    wall = next(p for p in __import__("app.domain.derive", fromlist=["wall_pieces"]).wall_pieces(d) if p.other)
    text = describe_selection(d, [wall.id])
    assert "partition wall" in text and "ROOMS INVOLVED" in text and "Kitchen" in text and "Living" in text


def test_ids_the_design_does_not_know_are_ignored_and_nothing_known_gives_none():
    d = build(*HOUSE)
    assert "1 element" in describe_selection(d, ["room.L1.kitchen", "nonsense.id"])
    assert describe_selection(d, ["nonsense.id"]) is None and describe_selection(d, []) is None


def test_a_big_selection_lists_some_and_counts_the_rest():
    d = build(*HOUSE)
    ids = ["room.L1.kitchen"] * 0 + [f"window.fake.{i}" for i in range(50)]
    assert describe_selection(d, ids) is None
    many = ["room.L1.kitchen", "room.L1.living", "door.kitchen.living", "window.kitchen.S"]
    short = describe_selection(d, many, limit=2)
    assert short.count("\n- ") == 3 and "...and 2 more" in short            # two listed, then one line saying how many were left out


def test_the_run_endpoint_takes_a_list_and_tells_the_model(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config
    from app.main import create_app

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite3")
    with TestClient(create_app()) as c:
        pid = c.post("/api/projects", json={"name": "Pick"}).json()["id"]
        with c.stream("POST", f"/api/projects/{pid}/runs", json={"prompt": "A one storey house with a kitchen, living room and a bedroom."}) as r:
            list(r.iter_lines())
        guids = repo.get_version(config.LOCAL_OWNER, pid, 1)["guids_json"]
        import json
        g = json.loads(guids)
        picked = [g["element:room.L1.kitchen"], g["element:room.L1.living"]]
        head = c.get(f"/api/projects/{pid}").json()["head"]
        events = []
        with c.stream("POST", f"/api/projects/{pid}/runs", json={"prompt": "make these bigger", "base_version": head["number"], "focus_guids": picked}) as r:
            for line in r.iter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:]))
        selected = [e for e in events if e["stage"] == "selected"]
        assert len(selected) == 1 and "2 elements" in selected[0]["data"]["text"] and "kitchen" in selected[0]["data"]["text"]
        # too many ids, or an id that is not a GlobalId, is refused before anything runs
        assert c.post(f"/api/projects/{pid}/runs", json={"prompt": "x", "focus_guids": ["a" * 100]}).status_code == 422


def test_a_selected_partition_wall_says_how_long_it_is_and_which_door_it_holds():
    d = build(*HOUSE)
    wall = next(p for p in __import__("app.domain.derive", fromlist=["wall_pieces"]).wall_pieces(d) if p.other)
    text = describe_selection(d, [wall.id])
    assert "m long" in text and "it holds the door door.kitchen.living" in text
