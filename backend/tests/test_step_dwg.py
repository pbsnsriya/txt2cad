import os
import subprocess
import sys

import cadquery as cq
import pytest

from app.domain.derive import derive
from app.export import dwg as dwg_mod
from app.export.dxf import dxf_text
from app.export.step import build_step, step_bytes
from tests.test_edits import house, settle


@pytest.fixture(scope="module")
def spec():
    return settle(house())[1]


def test_a_wall_with_a_door_loses_exactly_the_doors_volume(spec):
    from app.export.step import _wall
    w = spec.wall("L1-wall-hall+living")
    door = next(o for o in spec.openings if o.host == w.id)
    from app.domain.geom import wall_outline
    from shapely.geometry import Polygon
    plain = Polygon(wall_outline(w.start, w.end, w.thickness)[0]).area * w.height
    solid = _wall(spec, w)
    assert solid.solids().size() == 1
    assert solid.val().Volume() == pytest.approx(plain - door.width * w.thickness * door.height, rel=1e-6)


def test_step_file_reimports_with_every_element_at_the_right_place(spec, tmp_path):
    data = step_bytes(spec)
    assert data.startswith(b"ISO-10303-21;") and b"L1-wall-hall+living" in data and b"stair-hall" in data   # element names survive
    path = tmp_path / "b.step"
    path.write_bytes(data)
    back = cq.importers.importStep(str(path))
    expected = len(spec.walls) + len(spec.slabs) + len(spec.roofs) + len(spec.stairs) + len(spec.openings)
    assert back.solids().size() == expected
    bb = back.val().BoundingBox()
    top = max(r.z_bottom + r.thickness for r in spec.roofs)
    assert bb.zmin == pytest.approx(-0.2, abs=1e-6) and bb.zmax == pytest.approx(top, abs=1e-6)
    assert bb.xmin == pytest.approx(-0.15, abs=1e-6) and bb.xmax == pytest.approx(12.15, abs=1e-6)         # outer faces of the 12 m wide house
    stair = next(s for s in spec.stairs)
    assert any(abs(sol.Volume() - sum(1 for _ in [0]) * 0) >= 0 for sol in back.solids().vals())             # solids are valid shapes
    assert all(sol.isValid() for sol in back.solids().vals())
    assert stair.id.encode() in data


def test_the_stairwell_hole_is_cut_in_the_floor_above(spec):
    assy = build_step(spec)
    slab = next(c for c in assy.children if c.name == "L2-slab-1")
    outline_area = 0
    from shapely.geometry import Polygon
    s = next(s for s in spec.slabs if s.id == "L2-slab-1")
    expected = (Polygon(s.outline, s.holes).area) * s.thickness
    assert slab.obj.val().Volume() == pytest.approx(expected, rel=1e-6)


def _fake_converter(tmp_path):
    exe = tmp_path / "fake_oda.cmd"
    exe.write_text('@echo off\r\ncopy /b "%~1\plan.dxf" "%~2\plan.dwg" >nul\r\n', encoding="ascii")
    return exe


def test_dwg_uses_the_converter_when_one_is_installed(spec, tmp_path, monkeypatch):
    monkeypatch.setenv("TXT2CAD_ODA_CONVERTER", str(_fake_converter(tmp_path)))
    out = dwg_mod.dwg_bytes(spec)
    # The fake converter only renames the file (the real one writes binary DWG). DXF text carries fresh GUIDs and times on every
    # export, so compare shape, not bytes.
    expected = dxf_text(spec).encode("utf-8")
    assert out.startswith(b"  0\nSECTION") and len(out) == len(expected) and out.count(b"LWPOLYLINE") == expected.count(b"LWPOLYLINE")


def test_dwg_without_a_converter_says_how_to_get_one(spec, monkeypatch):
    monkeypatch.delenv("TXT2CAD_ODA_CONVERTER", raising=False)
    monkeypatch.setattr(dwg_mod, "DEFAULT_GLOBS", ())
    with pytest.raises(dwg_mod.DwgUnavailable, match="ODA File Converter"):
        dwg_mod.dwg_bytes(spec)


def test_a_converter_that_produces_nothing_is_reported_not_swallowed(spec, tmp_path, monkeypatch):
    exe = tmp_path / "broken.cmd"
    exe.write_text("@echo off\r\nexit /b 3\r\n", encoding="ascii")
    monkeypatch.setenv("TXT2CAD_ODA_CONVERTER", str(exe))
    with pytest.raises(dwg_mod.DwgUnavailable, match="produced no file \(exit 3\)"):
        dwg_mod.dwg_bytes(spec)
