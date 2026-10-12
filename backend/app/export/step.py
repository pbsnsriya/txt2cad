"""BuildingSpec -> STEP (AP214/AP242 via OpenCascade, through CadQuery). Solids with names and colours, in metres.

Walls are cut by their openings with real boolean operations; doors and windows are thin panels in the openings; slabs keep
their stairwells. This is a mechanical-CAD view of the building (SolidWorks, Fusion, FreeCAD, Rhino), not BIM: use the IFC for BIM.
"""

from __future__ import annotations

import os
import tempfile

import cadquery as cq

from ..domain.geom import box_on_wall, stair_profile, wall_outline
from ..domain.spec import BuildingSpec, Point

DOOR_LEAF_M = 0.05
WINDOW_PANE_M = 0.08
OVERCUT_M = 0.05
COLOURS = {"wall": (0.78, 0.74, 0.68, 1.0), "partition": (0.90, 0.89, 0.86, 1.0), "slab": (0.55, 0.56, 0.58, 1.0), "roof": (0.36, 0.38, 0.42, 1.0),
           "door": (0.50, 0.33, 0.18, 1.0), "window": (0.55, 0.75, 0.90, 0.4), "stair": (0.66, 0.60, 0.52, 1.0)}


def _prism(pts: list[Point], z0: float, depth: float) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z0).polyline(pts).close().extrude(depth)


def _wall(spec: BuildingSpec, w) -> cq.Workplane:
    pts, u, n = wall_outline(w.start, w.end, w.thickness)
    z0 = spec.level_elevation(w.level)
    solid = _prism(pts, z0, w.height)
    for o in (o for o in spec.openings if o.host == w.id):
        centre = (w.start[0] + u[0] * o.offset, w.start[1] + u[1] * o.offset)
        solid = solid.cut(_prism(box_on_wall(centre, u, n, o.width, w.thickness + 2 * OVERCUT_M), z0 + o.sill, o.height))
    return solid


def _stair(st) -> cq.Workplane:
    ux, uy = st.direction
    nx, ny = -uy, ux
    origin = (st.start[0] + nx * st.width / 2, st.start[1] + ny * st.width / 2, st.z0)
    plane = cq.Plane(origin=origin, xDir=(ux, uy, 0), normal=(-nx, -ny, 0))      # local y is up, extrusion runs across the width
    return cq.Workplane(plane).polyline(stair_profile(st.risers, st.riser_height, st.going)).close().extrude(st.width)


def build_step(spec: BuildingSpec) -> cq.Assembly:
    assy = cq.Assembly(name=spec.name or "building")
    for w in spec.walls:
        assy.add(_wall(spec, w), name=w.id, color=cq.Color(*COLOURS["wall" if w.external else "partition"]))
    for s in spec.slabs:
        solid = _prism(s.outline, s.z_top - s.thickness, s.thickness)
        for hole in s.holes:
            solid = solid.cut(_prism(hole, s.z_top - s.thickness - OVERCUT_M, s.thickness + 2 * OVERCUT_M))
        assy.add(solid, name=s.id, color=cq.Color(*COLOURS["slab"]))
    for r in spec.roofs:
        assy.add(_prism(r.outline, r.z_bottom, r.thickness), name=r.id, color=cq.Color(*COLOURS["roof"]))
    for st in spec.stairs:
        assy.add(_stair(st), name=st.id, color=cq.Color(*COLOURS["stair"]))
    for o in spec.openings:
        w = spec.wall(o.host)
        _, u, n = wall_outline(w.start, w.end, w.thickness)
        centre = (w.start[0] + u[0] * o.offset, w.start[1] + u[1] * o.offset)
        thickness = DOOR_LEAF_M if o.kind == "door" else WINDOW_PANE_M
        assy.add(_prism(box_on_wall(centre, u, n, o.width, thickness), spec.level_elevation(o.level) + o.sill, o.height), name=o.id, color=cq.Color(*COLOURS[o.kind]))
    return assy


def step_bytes(spec: BuildingSpec) -> bytes:
    assy = build_step(spec)
    fd, path = tempfile.mkstemp(suffix=".step")
    os.close(fd)
    try:
        assy.save(path, exportType="STEP")
        with open(path, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(path)
