"""BuildingSpec -> DXF floor plans (R2018, metres). One drawing per level, laid out left to right in model space.

Layers follow the AIA/NCS naming idea: A-WALL, A-WALL-PATT (poché), A-DOOR, A-GLAZ, A-AREA, A-AREA-IDEN, A-ANNO-DIMS, A-ANNO-TTLB.
"""

from __future__ import annotations

import io
import math

import ezdxf
from ezdxf import units
from ezdxf.document import Drawing
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from ..domain.spec import BuildingSpec, OpeningSpec, WallSpec

LEVEL_GAP_M = 8.0
TEXT_HEIGHT_M = 0.22
TITLE_HEIGHT_M = 0.45
DIM_OFFSET_M = 1.8
# The stock EZDXF dimstyle scales to centimetres (dimlfac 100); the drawing is in metres, so say so.
DIM_OVERRIDE = {"dimlfac": 1.0, "dimdec": 2, "dimtxt": 0.25, "dimasz": 0.2, "dimexe": 0.15, "dimexo": 0.1}
LAYERS: dict[str, int] = {
    "A-WALL": 7, "A-WALL-PATT": 8, "A-DOOR": 3, "A-GLAZ": 5, "A-AREA": 9, "A-AREA-IDEN": 7, "A-ANNO-DIMS": 2, "A-ANNO-TTLB": 7, "A-FLOR-STRS": 6,
}


def _axes(w: WallSpec) -> tuple[tuple[float, float], tuple[float, float]]:
    length = w.length
    ux, uy = (w.end[0] - w.start[0]) / length, (w.end[1] - w.start[1]) / length
    return (ux, uy), (-uy, ux)


def _wall_polygon(w: WallSpec) -> Polygon:
    (ux, uy), (nx, ny) = _axes(w)
    e = h = w.thickness / 2
    return Polygon([(w.start[0] - ux * e + nx * h, w.start[1] - uy * e + ny * h), (w.end[0] + ux * e + nx * h, w.end[1] + uy * e + ny * h),
                    (w.end[0] + ux * e - nx * h, w.end[1] + uy * e - ny * h), (w.start[0] - ux * e - nx * h, w.start[1] - uy * e - ny * h)])


def _opening_box(w: WallSpec, o: OpeningSpec, depth: float) -> Polygon:
    (ux, uy), (nx, ny) = _axes(w)
    cx, cy = w.start[0] + ux * o.offset, w.start[1] + uy * o.offset
    hw, hd = o.width / 2, depth / 2
    return Polygon([(cx - ux * hw + nx * hd, cy - uy * hw + ny * hd), (cx + ux * hw + nx * hd, cy + uy * hw + ny * hd),
                    (cx + ux * hw - nx * hd, cy + uy * hw - ny * hd), (cx - ux * hw - nx * hd, cy - uy * hw - ny * hd)])


def build_dxf(spec: BuildingSpec) -> Drawing:
    doc = ezdxf.new("R2018", setup=True)
    doc.units = units.M
    for name, colour in LAYERS.items():
        doc.layers.add(name, color=colour)
    msp = doc.modelspace()
    cursor_x = 0.0
    for lv in spec.levels:
        walls = [w for w in spec.walls if w.level == lv.id]
        if not walls:
            continue
        bounds = unary_union([_wall_polygon(w) for w in walls]).bounds
        dx, dy = cursor_x - bounds[0], -bounds[1]

        def at(pt: tuple[float, float]) -> tuple[float, float]:
            return (pt[0] + dx, pt[1] + dy)

        _draw_walls(msp, spec, lv.id, walls, dx, dy)
        _draw_openings(msp, spec, walls, lv.id, dx, dy)
        _draw_stairs(msp, spec, lv.id, dx, dy)
        for sp in (s for s in spec.spaces if s.level == lv.id):
            ring = [at(p) for p in sp.outline]
            msp.add_lwpolyline(ring, close=True, dxfattribs={"layer": "A-AREA"})
            centroid = Polygon(ring).centroid
            msp.add_text(f"{sp.name}  {sp.area:.1f} m2", height=TEXT_HEIGHT_M, dxfattribs={"layer": "A-AREA-IDEN"}).set_placement(
                (centroid.x, centroid.y), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
        width, depth = bounds[2] - bounds[0], bounds[3] - bounds[1]
        x0, y0 = cursor_x, 0.0
        msp.add_text(f"{lv.name or lv.id}  (+{lv.elevation:.2f} m)", height=TITLE_HEIGHT_M, dxfattribs={"layer": "A-ANNO-TTLB"}).set_placement(
            (x0, y0 + depth + 1.0))
        msp.add_linear_dim(base=(x0, y0 - DIM_OFFSET_M), p1=(x0, y0), p2=(x0 + width, y0), override=DIM_OVERRIDE, dxfattribs={"layer": "A-ANNO-DIMS"}).render()
        msp.add_linear_dim(base=(x0 - DIM_OFFSET_M, y0), p1=(x0, y0), p2=(x0, y0 + depth), angle=90, override=DIM_OVERRIDE, dxfattribs={"layer": "A-ANNO-DIMS"}).render()
        cursor_x += width + LEVEL_GAP_M
    return doc


def _draw_walls(msp, spec: BuildingSpec, level: str, walls: list[WallSpec], dx: float, dy: float) -> None:
    cut = [_opening_box(spec.wall(o.host), o, spec.wall(o.host).thickness * 2) for o in spec.openings if o.level == level]
    merged = unary_union([_wall_polygon(w) for w in walls])
    if cut:
        merged = merged.difference(unary_union(cut))
    geoms = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
    for poly in geoms:
        if poly.is_empty or poly.area < 1e-6:
            continue
        rings = [list(poly.exterior.coords)[:-1], *[list(r.coords)[:-1] for r in poly.interiors]]
        shifted = [[(x + dx, y + dy) for x, y in ring] for ring in rings]
        for ring in shifted:
            msp.add_lwpolyline(ring, close=True, dxfattribs={"layer": "A-WALL"})
        hatch = msp.add_hatch(color=8, dxfattribs={"layer": "A-WALL-PATT"})
        hatch.set_solid_fill(color=8)
        for i, ring in enumerate(shifted):
            hatch.paths.add_polyline_path(ring, is_closed=True, flags=1 if i == 0 else 16)


def _draw_openings(msp, spec: BuildingSpec, walls: list[WallSpec], level: str, dx: float, dy: float) -> None:
    for o in (x for x in spec.openings if x.level == level):
        w = spec.wall(o.host)
        (ux, uy), (nx, ny) = _axes(w)
        cx, cy = w.start[0] + ux * o.offset + dx, w.start[1] + uy * o.offset + dy
        hw, ht = o.width / 2, w.thickness / 2
        if o.kind == "door":
            hinge = (cx - ux * hw, cy - uy * hw)
            tip = (hinge[0] + nx * o.width, hinge[1] + ny * o.width)
            msp.add_line(hinge, tip, dxfattribs={"layer": "A-DOOR"})
            start_deg = math.degrees(math.atan2(uy, ux))
            nrm_deg = math.degrees(math.atan2(ny, nx))
            a0, a1 = sorted((start_deg, start_deg + 90 if abs(((nrm_deg - start_deg + 180) % 360) - 180 - 90) < 1e-6 else start_deg - 90))
            msp.add_arc(hinge, o.width, a0 % 360, a1 % 360, dxfattribs={"layer": "A-DOOR"})
        else:
            for off in (-ht, 0.0, ht):
                msp.add_line((cx - ux * hw + nx * off, cy - uy * hw + ny * off), (cx + ux * hw + nx * off, cy + uy * hw + ny * off),
                             dxfattribs={"layer": "A-GLAZ"})


def _draw_stairs(msp, spec: BuildingSpec, level: str, dx: float, dy: float) -> None:
    """Plan symbol: footprint, one line per tread, an arrow up the flight and UP at the bottom; the floor above shows DN at the top."""
    for st in spec.stairs:
        if level not in (st.level, st.to_level):
            continue
        ring = [(x + dx, y + dy) for x, y in st.outline]
        ux, uy = st.direction
        nx, ny = -uy, ux
        sx, sy = st.start[0] + dx, st.start[1] + dy
        hw = st.width / 2
        attrs = {"layer": "A-FLOR-STRS"}
        msp.add_lwpolyline(ring, close=True, dxfattribs=attrs)
        if level == st.level:
            for i in range(1, st.risers):
                px, py = sx + ux * i * st.going, sy + uy * i * st.going
                msp.add_line((px + nx * hw, py + ny * hw), (px - nx * hw, py - ny * hw), dxfattribs=attrs)
            tip = (sx + ux * st.length, sy + uy * st.length)
            msp.add_line((sx, sy), tip, dxfattribs=attrs)
            head = 0.25
            for side in (-1, 1):
                msp.add_line(tip, (tip[0] - ux * head + nx * head * 0.5 * side, tip[1] - uy * head + ny * head * 0.5 * side), dxfattribs=attrs)
            label, at = "UP", (sx + nx * (hw + 0.15), sy + ny * (hw + 0.15))
        else:
            label, at = "DN", (sx + ux * st.length + nx * (hw + 0.15), sy + uy * st.length + ny * (hw + 0.15))
        msp.add_text(label, height=TEXT_HEIGHT_M, dxfattribs=attrs).set_placement(at)


def dxf_text(spec: BuildingSpec) -> str:
    buf = io.StringIO()
    build_dxf(spec).write(buf)
    return buf.getvalue()
