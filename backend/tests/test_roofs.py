"""Pitched roofs: the geometry, the step, the derived spec, the IFC and the quantities."""

import math
from collections import Counter

import ifcopenshell
import ifcopenshell.geom
import pytest

from app.analysis.quantities import quantities
from app.domain import checks
from app.domain.derive import derive
from app.domain.design import Design
from app.domain.roofs import effective_pitch, is_rectangle, mesh_volume, roof_kind, roof_mesh, surface_area
from app.domain.steps import Step, StepError, apply_step
from app.ifc.compile import compile_ifc

RECT_12x8 = [(0, 0), (12, 0), (12, 8), (0, 8)]


def edges_are_shared_twice(tris):
    edges = Counter()
    for a, b, c in tris:
        for e in ((a, b), (b, c), (c, a)):
            edges[tuple(sorted(e))] += 1
    return all(n == 2 for n in edges.values())


# --- geometry -----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["gable", "hip", "shed"])
def test_every_roof_is_a_closed_outward_facing_body(kind):
    verts, tris = roof_mesh(RECT_12x8, 6.0, kind, 30)
    assert edges_are_shared_twice(tris)
    assert mesh_volume(verts, tris) > 0                     # negative would mean inside-out faces
    assert min(v[2] for v in verts) == 6.0 and max(v[2] for v in verts) > 6.0


def test_gable_ridge_height_and_volume():
    verts, tris = roof_mesh(RECT_12x8, 0.0, "gable", 30)
    h = 4 * math.tan(math.radians(30))
    assert max(v[2] for v in verts) == pytest.approx(h)
    assert mesh_volume(verts, tris) == pytest.approx(12 * 8 * h / 2)
    ridge = [v for v in verts if v[2] > 0]
    assert {v[1] for v in ridge} == {4.0} and {v[0] for v in ridge} == {0.0, 12.0}        # along the long side


def test_the_ridge_follows_the_longer_side():
    tall = [(0, 0), (6, 0), (6, 12), (0, 12)]
    verts, _ = roof_mesh(tall, 0.0, "gable", 30)
    ridge = [v for v in verts if v[2] > 0]
    assert {v[0] for v in ridge} == {3.0} and {v[1] for v in ridge} == {0.0, 12.0}


def test_hip_roof_pulls_the_ridge_in_and_a_square_becomes_a_pyramid():
    verts, tris = roof_mesh(RECT_12x8, 0.0, "hip", 30)
    ridge = [v for v in verts if v[2] > 0]
    assert {v[0] for v in ridge} == {4.0, 8.0}
    sq = [(0, 0), (6, 0), (6, 6), (0, 6)]
    verts, tris = roof_mesh(sq, 0.0, "hip", 30)
    h = 3 * math.tan(math.radians(30))
    assert mesh_volume(verts, tris) == pytest.approx(36 * h / 3) and sum(1 for v in verts if v[2] > 0) == 1


@pytest.mark.parametrize("side", ["N", "S", "E", "W"])
def test_shed_roof_rises_to_the_chosen_side(side):
    verts, tris = roof_mesh(RECT_12x8, 0.0, "shed", 20, side)
    span = 8 if side in "NS" else 12
    h = span * math.tan(math.radians(20))
    assert mesh_volume(verts, tris) == pytest.approx(12 * 8 * h / 2)
    high = [v for v in verts if v[2] > 0]
    coord, value = {"N": (1, 8.0), "S": (1, 0.0), "E": (0, 12.0), "W": (0, 0.0)}[side]
    assert high and all(v[coord] == value for v in high)
    assert edges_are_shared_twice(tris)


def test_pitch_is_lowered_for_a_very_wide_span():
    assert effective_pitch("gable", 40, 30, 30) == pytest.approx(math.degrees(math.atan(5 / 15)), abs=0.1)
    assert effective_pitch("gable", 12, 8, 30) == 30
    assert effective_pitch("flat", 12, 8, 30) == 0.0


def test_words_for_roofs():
    assert roof_kind("Pitched") == "gable" and roof_kind("hipped") == "hip" and roof_kind("lean-to") == "shed" and roof_kind(None) == "flat"
    assert roof_kind("dome") is None


def test_rectangles_are_told_from_l_shapes():
    assert is_rectangle(RECT_12x8)
    assert not is_rectangle([(0, 0), (6, 0), (6, 3), (3, 3), (3, 6), (0, 6)])


def test_sloped_area_is_plan_area_over_cos_pitch():
    assert surface_area(12, 8, 30) == pytest.approx(96 / math.cos(math.radians(30)))
    assert surface_area(12, 8, 0) == 96


# --- the step -----------------------------------------------------------------------------------------------------------
def base_design() -> Design:
    d = Design()
    for s in ({"step": "storey", "id": "L1", "name": "Ground floor", "height": 3},
              {"step": "room", "level": "L1", "name": "Main", "kind": "living", "rect": [0, 0, 12, 8]}):
        d = apply_step(d, Step(**s))
    return d


def test_a_roof_step_sets_kind_pitch_and_side():
    d = apply_step(base_design(), Step(step="roof", kind="pitched", pitch=35))
    assert (d.roof, d.roof_pitch) == ("gable", 35)
    d = apply_step(d, Step(step="roof", kind="shed", side="s"))
    assert d.roof == "shed" and d.roof_high_side == "S"
    d = apply_step(d, Step(step="roof", kind="flat"))
    assert d.roof == "flat" and not any("not supported" in n for n in d.notes)


def test_a_bad_roof_step_says_what_is_allowed():
    with pytest.raises(StepError, match="flat, gable, hip or shed"):
        apply_step(base_design(), Step(step="roof", kind="dome"))
    with pytest.raises(StepError, match="between 5 and 60"):
        apply_step(base_design(), Step(step="roof", kind="gable", pitch=80))


# --- derive, IFC, quantities --------------------------------------------------------------------------------------------
def pitched_house(kind="gable", pitch=30):
    d = base_design()
    return apply_step(d, Step(step="roof", kind=kind, pitch=pitch))


def test_derive_makes_a_pitched_roof_for_a_rectangle():
    spec = derive(pitched_house())
    [r] = spec.roofs
    assert (r.kind, r.pitch, r.ridge_along) == ("gable", 30.0, "x") and r.note == ""


def test_an_l_shaped_roof_area_stays_flat_and_says_why():
    d = base_design()
    for s in ({"step": "storey", "id": "L2", "height": 3},
              {"step": "room", "level": "L2", "name": "Up", "kind": "bedroom", "rect": [0, 0, 6, 4]},
              {"step": "roof", "kind": "gable"}):
        d = apply_step(d, Step(**s))
    spec = derive(d)
    kinds = {r.level: r for r in spec.roofs}
    assert kinds["L2"].kind == "gable"
    assert kinds["L1"].kind == "flat" and "rectangle" in kinds["L1"].note


def test_ifc_roof_is_a_real_pitched_body():
    spec = derive(pitched_house("hip", 25))
    model, _ = compile_ifc(spec)
    [roof] = model.by_type("IfcRoof")
    assert roof.PredefinedType == "HIP_ROOF"
    shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), roof)
    zs = shape.geometry.verts[2::3]
    assert min(zs) == pytest.approx(3.0, abs=0.01) and max(zs) > 3.5
    assert len(model.by_type("IfcRoof")) == 1


def test_quantities_use_the_sloped_surface():
    spec = derive(pitched_house("gable", 30))
    rows = {r["item"]: r for r in quantities(spec)["rows"] if r["group"] == "Roof"}
    [row] = rows.values()
    assert row["item"] == "Roof (gable, 30 deg)" and row["qty"] == pytest.approx(surface_area(12.3, 8.3, 30), abs=0.1)


# --- requirements -------------------------------------------------------------------------------------------------------
def test_a_roof_requirement_is_measured():
    want = checks.normalise({"kind": "feature", "keyword": "roof", "text": "The building has a pitched roof.", "supported": False})
    assert want["supported"] is True                     # roofs are buildable now, whatever the model flagged
    flat = base_design()
    [r] = checks.check(flat, [want])
    assert r["status"] == "unmet" and "gable, hip or shed" in r["detail"]
    [r] = checks.check(pitched_house(), [want])
    assert r["status"] == "met" and "gable" in r["detail"]
    hip = checks.normalise({"kind": "feature", "keyword": "roof", "text": "A hip roof.", "supported": True})
    assert checks.check(pitched_house("gable"), [hip])[0]["status"] == "unmet"
    assert checks.check(pitched_house("hip"), [hip])[0]["status"] == "met"
