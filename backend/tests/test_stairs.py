import io

import ezdxf
import ifcopenshell
import ifcopenshell.geom
import numpy as np
import pytest

from app.domain.checks import completeness
from app.domain.derive import DesignError, derive, prune_invalid_openings
from app.domain.design import Design
from app.domain.steps import Step, apply_step
from app.export.dxf import dxf_text
from app.ifc.compile import compile_ifc


def build(*steps: dict) -> Design:
    d = Design()
    for s in steps:
        d = apply_step(d, Step(**s))
    return d


TWO_STOREY = (
    {"step": "level", "id": "L1", "height": 3}, {"step": "level", "id": "L2", "height": 3},
    {"step": "room", "level": "L1", "name": "Hall", "kind": "hall", "rect": [0, 0, 3, 5]},
    {"step": "room", "level": "L1", "name": "Living", "kind": "living", "rect": [3, 0, 5, 5]},
    {"step": "room", "level": "L2", "name": "Landing", "kind": "hall", "rect": [0, 0, 3, 5]},
    {"step": "room", "level": "L2", "name": "Bed", "kind": "bedroom", "rect": [3, 0, 5, 5]},
)


def test_a_three_metre_flight_has_sixteen_risers_under_the_code_limit():
    spec = derive(build(*TWO_STOREY, {"step": "stair", "room": "Hall", "side": "W"}))
    st = spec.stairs[0]
    assert st.risers == 16 and st.riser_height == pytest.approx(0.1875) and st.riser_height <= 0.197
    assert st.length == pytest.approx(3.9) and st.to_level == "L2" and st.z0 == 0
    xs, ys = zip(*st.outline)
    assert (min(xs), max(xs)) == (pytest.approx(0.15), pytest.approx(1.15)) and (min(ys), max(ys)) == (pytest.approx(0.15), pytest.approx(4.05))


def test_the_floor_above_gets_a_stairwell_hole_and_the_floor_below_does_not():
    spec = derive(build(*TWO_STOREY, {"step": "stair", "room": "Hall", "side": "W"}))
    upper = [s for s in spec.slabs if s.level == "L2"]
    assert len(upper) == 1 and len(upper[0].holes) == 1
    assert not any(s.holes for s in spec.slabs if s.level == "L1")


def test_a_room_too_short_for_the_flight_says_what_it_needs():
    d = build({"step": "level", "id": "L1"}, {"step": "level", "id": "L2"},
              {"step": "room", "level": "L1", "name": "Hall", "rect": [0, 0, 3, 3]}, {"step": "room", "level": "L2", "name": "Landing", "rect": [0, 0, 3, 3]},
              {"step": "stair", "room": "Hall", "side": "W"})
    with pytest.raises(DesignError, match=r"needs 3\.90 m along the wall"):
        derive(d)


def test_a_stair_whose_top_has_no_room_above_is_rejected_with_the_range_to_cover():
    d = build(*TWO_STOREY[:5], {"step": "stair", "room": "Hall", "side": "E"})   # E side: x 1.85..2.85, but Landing covers 0..3 -> fine
    derive(d)
    d = build({"step": "level", "id": "L1"}, {"step": "level", "id": "L2"}, {"step": "room", "level": "L1", "name": "Hall", "rect": [0, 0, 3, 5]},
              {"step": "room", "level": "L2", "name": "Bed", "rect": [10, 0, 4, 5]}, {"step": "stair", "room": "Hall", "side": "W"})
    with pytest.raises(DesignError, match=r"land outside every room on L2.*x 0\.15\.\.1\.15"):
        derive(d)


def test_stair_on_the_top_level_is_an_error():
    d = build({"step": "level", "id": "L1"}, {"step": "room", "level": "L1", "name": "Hall", "rect": [0, 0, 3, 5]}, {"step": "stair", "room": "Hall", "side": "W"})
    with pytest.raises(DesignError, match="no level above"):
        derive(d)


def test_completeness_asks_for_a_stair_between_levels():
    d = build(*TWO_STOREY)
    assert any("L2 has no stair up from L1" in i for i in completeness(d))
    assert not any("no stair" in i for i in completeness(build(*TWO_STOREY, {"step": "stair", "room": "Hall", "side": "W"})))


def test_moving_the_landing_away_drops_the_stair_instead_of_failing_the_edit():
    d = build(*TWO_STOREY, {"step": "stair", "room": "Hall", "side": "W"})
    d = apply_step(d, Step(step="remove", id="landing"))
    d = apply_step(d, Step(step="room", level="L2", name="Landing", kind="hall", rect=[20, 0, 3, 5]))
    pruned, removed = prune_invalid_openings(d)
    assert not pruned.stairs and "stair" in removed[0]


def test_removing_a_room_removes_its_stair():
    d = build(*TWO_STOREY, {"step": "stair", "room": "Hall", "side": "W"})
    assert not apply_step(d, Step(step="remove", id="hall")).stairs


def test_ifc_has_a_stair_whose_geometry_climbs_one_storey_and_a_slab_with_a_void():
    spec = derive(build(*TWO_STOREY, {"step": "stair", "room": "Hall", "side": "W"}))
    model, _ = compile_ifc(spec, "", None)
    stairs = model.by_type("IfcStair")
    assert len(stairs) == 1 and stairs[0].PredefinedType == "STRAIGHT_RUN_STAIR"
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    v = np.array(ifcopenshell.geom.create_shape(settings, stairs[0]).geometry.verts).reshape(-1, 3)
    assert v[:, 2].min() == pytest.approx(0, abs=1e-6) and v[:, 2].max() == pytest.approx(15 * 0.1875, abs=1e-6)   # top tread; the 16th riser lifts onto the floor above
    assert np.ptp(v[:, 1]) == pytest.approx(3.9, abs=1e-6) and np.ptp(v[:, 0]) == pytest.approx(1.0, abs=1e-6)  # along y, 1 m wide
    slab = next(s for s in model.by_type("IfcSlab") if s.Name == "L2-slab-1")
    prof = slab.Representation.Representations[0].Items[0].SweptArea
    assert prof.is_a("IfcArbitraryProfileDefWithVoids") and len(prof.InnerCurves) == 1
    sv = np.array(ifcopenshell.geom.create_shape(settings, slab).geometry.verts).reshape(-1, 3)
    assert len(sv) > 8                                           # a plain box has 8; the well adds faces


def test_a_stair_running_along_x_rises_in_the_right_direction():
    d = build({"step": "level", "id": "L1"}, {"step": "level", "id": "L2"},
              {"step": "room", "level": "L1", "name": "Hall", "rect": [0, 0, 6, 3]}, {"step": "room", "level": "L2", "name": "Landing", "rect": [0, 0, 6, 3]},
              {"step": "stair", "room": "Hall", "side": "N"})
    spec = derive(d)
    model, _ = compile_ifc(spec, "", None)
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    v = np.array(ifcopenshell.geom.create_shape(settings, model.by_type("IfcStair")[0]).geometry.verts).reshape(-1, 3)
    assert np.ptp(v[:, 0]) == pytest.approx(3.9, abs=1e-6) and v[:, 1].min() == pytest.approx(1.85, abs=1e-6) and v[:, 1].max() == pytest.approx(2.85, abs=1e-6)
    top = v[v[:, 2] > 2.8]
    assert top[:, 0].min() > 3.4                                 # the high end is at the far end of the run (x increasing)


def test_dxf_draws_the_flight_on_both_floors():
    spec = derive(build(*TWO_STOREY, {"step": "stair", "room": "Hall", "side": "W"}))
    doc = ezdxf.read(io.StringIO(dxf_text(spec)))
    assert not doc.audit().errors
    msp = doc.modelspace()
    layer = lambda t: [e for e in msp.query(t) if e.dxf.layer == "A-FLOR-STRS"]  # noqa: E731
    assert len(layer("LWPOLYLINE")) == 2                          # footprint on L1 and on L2
    assert len(layer("LINE")) == (16 - 1) + 1 + 2                 # treads, centre line, two arrow barbs
    assert sorted(e.dxf.text for e in layer("TEXT")) == ["DN", "UP"]
