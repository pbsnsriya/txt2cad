import ifcopenshell
import ifcopenshell.geom
import numpy as np

from app.domain.design import Design
from app.domain.derive import derive
from app.domain.steps import Step, apply_step
from app.ifc.compile import compile_ifc


def sample() -> Design:
    d = Design(name="Test house")
    for s in (
        {"step": "storey", "id": "L1", "height": 3}, {"step": "storey", "id": "L2", "height": 2.8},
        {"step": "room", "level": "L1", "name": "Kitchen", "kind": "kitchen", "rect": [0, 0, 4, 4]},
        {"step": "room", "level": "L1", "name": "Living", "kind": "living", "rect": [4, 0, 5, 4]},
        {"step": "room", "level": "L2", "name": "Bed", "kind": "bedroom", "rect": [0, 0, 9, 4]},
        {"step": "door", "room": "kitchen", "to": "living"}, {"step": "door", "room": "living", "side": "S"},
        {"step": "window", "room": "kitchen", "side": "S"}, {"step": "window", "room": "bed", "side": "N"},
    ):
        d = apply_step(d, Step(**s))
    return d


def test_compile_has_the_expected_classes_and_valid_geometry(tmp_path):
    spec = derive(sample())
    model, guids = compile_ifc(spec, sample().model_dump_json())
    assert len(model.by_type("IfcWall")) == len(spec.walls)
    assert len(model.by_type("IfcDoor")) == 2 and len(model.by_type("IfcWindow")) == 2
    assert len(model.by_type("IfcOpeningElement")) == 4 and len(model.by_type("IfcRelVoidsElement")) == 4
    assert len(model.by_type("IfcBuildingStorey")) == 2 and model.by_type("IfcRoof")
    path = tmp_path / "t.ifc"
    model.write(str(path))
    reread = ifcopenshell.open(str(path))
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    count, zmax = 0, 0.0
    it = ifcopenshell.geom.iterator(settings, reread, 1)
    assert it.initialize()
    while True:
        verts = np.array(it.get().geometry.verts).reshape(-1, 3)
        assert len(verts) > 0 and np.isfinite(verts).all()
        zmax = max(zmax, verts[:, 2].max())
        count += 1
        if not it.next():
            break
    assert count >= len(spec.walls) + len(spec.slabs)
    assert abs(zmax - (3 + 2.8 + 0.2)) < 1e-6        # roof top
    assert len(guids) > 20


def test_globalids_survive_an_unrelated_edit():
    d = sample()
    _, first = compile_ifc(derive(d), "", None)
    d2 = apply_step(d, Step(step="window", room="living", side="N"))
    _, second = compile_ifc(derive(d2), "", first)
    survived = {k for k in first if k in second and first[k] == second[k]}
    assert survived == set(first) & set(second) and len(survived) >= len(first) - 1


def test_openings_actually_cut_the_wall():
    model, _ = compile_ifc(derive(sample()), "", None)
    settings = ifcopenshell.geom.settings()
    wall = next(w for w in model.by_type("IfcWall") if w.Tag == "wall.L1.kitchen~living")
    shape = ifcopenshell.geom.create_shape(settings, wall)
    verts = np.array(shape.geometry.verts).reshape(-1, 3)
    # the door cut leaves faces at the door jamb: a plain box would only have 8 vertices
    assert len(verts) > 8


def test_ifc_names_are_human_labels_and_the_tag_keeps_the_stable_id():
    model, guids = compile_ifc(derive(sample()), "", None)
    wall = next(w for w in model.by_type("IfcWall") if w.Tag == "wall.L1.kitchen~living")
    assert wall.Name == "Wall between Kitchen and Living"
    assert {w.Name for w in model.by_type("IfcWall")} >= {"Kitchen: south wall", "Bed: north wall"}
    assert {d.Name for d in model.by_type("IfcDoor")} == {"Door: Kitchen to Living", "Door: Living to outside"}
    assert any(s.Name == "Level 2 floor" for s in model.by_type("IfcSlab")) and any(r.Name == "Level 2 roof" for r in model.by_type("IfcRoof"))
    assert "element:wall.L1.kitchen~living" in guids
