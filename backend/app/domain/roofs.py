"""Pitched roofs over a rectangle: gable, hip and shed, as closed triangle meshes.

A roof is the solid between the top of the walls and the sloped surface, so it reads as one body in the viewer and in IFC (an
IfcRoof with a tessellated shape). Only rectangles are handled; a roof area that is not a plain rectangle stays flat.
"""

from __future__ import annotations

import math
from typing import Literal

Vec = tuple[float, float, float]
Tri = tuple[int, int, int]

ROOF_KINDS = ("flat", "gable", "hip", "shed")
MIN_PITCH, MAX_PITCH, DEFAULT_PITCH = 5.0, 60.0, 30.0
MAX_RIDGE_HEIGHT_M = 5.0        # a very wide span at 30 degrees would otherwise grow a tower
RECT_TOLERANCE = 1e-6

RoofKind = Literal["flat", "gable", "hip", "shed"]

_ALIASES = {
    "flat": "flat", "gable": "gable", "gabled": "gable", "pitched": "gable", "sloped": "gable", "sloping": "gable", "dual": "gable", "ridge": "gable",
    "hip": "hip", "hipped": "hip", "hip roof": "hip", "shed": "shed", "mono": "shed", "monopitch": "shed", "mono-pitch": "shed", "lean-to": "shed", "skillion": "shed",
}


def roof_kind(word: str | None) -> str | None:
    """'Pitched', 'gabled', 'lean-to' ... to one of ROOF_KINDS, or None when the word is not a roof type we build."""
    if word is None:
        return "flat"
    return _ALIASES.get(str(word).strip().lower().replace("_", "-"))


def is_rectangle(outline: list[tuple[float, float]]) -> bool:
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    w, d = max(xs) - min(xs), max(ys) - min(ys)
    area = 0.0
    for i, (x1, y1) in enumerate(outline):
        x2, y2 = outline[(i + 1) % len(outline)]
        area += x1 * y2 - x2 * y1
    return len(outline) == 4 and abs(abs(area) / 2 - w * d) <= RECT_TOLERANCE * max(1.0, w * d)


def effective_pitch(kind: str, width: float, depth: float, pitch: float) -> float:
    """The pitch actually used: the asked one, lowered when the ridge would stand taller than MAX_RIDGE_HEIGHT_M."""
    if kind == "flat":
        return 0.0
    span = depth if kind == "shed" else min(width, depth)
    run = span if kind == "shed" else span / 2
    limit = math.degrees(math.atan(MAX_RIDGE_HEIGHT_M / run))
    return round(max(MIN_PITCH, min(pitch, limit)), 1) if limit >= MIN_PITCH else round(limit, 1)


def ridge_axis(width: float, depth: float) -> str:
    """'x': the ridge runs along the longer side (east-west when the plan is wider than deep)."""
    return "x" if width >= depth else "y"


def surface_area(width: float, depth: float, pitch: float) -> float:
    """Sloped surface of a pitched roof with the same pitch on every face (gable, hip and shed alike): plan area over cos(pitch)."""
    return width * depth / math.cos(math.radians(pitch)) if pitch else width * depth


def roof_mesh(outline: list[tuple[float, float]], z: float, kind: str, pitch: float, high_side: str | None = None) -> tuple[list[Vec], list[Tri]]:
    """Vertices and outward-facing triangles of the roof body. `outline` must be a rectangle."""
    xs, ys = [p[0] for p in outline], [p[1] for p in outline]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, d = x1 - x0, y1 - y0
    t = math.tan(math.radians(pitch))
    base: list[Vec] = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
    xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
    verts = list(base)
    faces: list[list[int]] = [[0, 1, 2, 3]]

    if kind == "gable" or kind == "hip":
        along_x = ridge_axis(w, d) == "x"
        span = d if along_x else w
        h = span / 2 * t
        inset = span / 2 if kind == "hip" else 0.0
        if along_x:
            verts += [(x0 + inset, ym, z + h), (x1 - inset, ym, z + h)]
            faces += [[0, 1, 5, 4], [2, 3, 4, 5], [0, 4, 3], [1, 2, 5]]
        else:
            verts += [(xm, y0 + inset, z + h), (xm, y1 - inset, z + h)]
            faces += [[0, 3, 5, 4], [1, 2, 5, 4], [0, 1, 4], [3, 2, 5]]
        if kind == "hip" and abs(w - d) < RECT_TOLERANCE:      # a square: both ridge ends meet at the apex
            verts, faces = list(base) + [(xm, ym, z + h)], [[0, 1, 2, 3], [0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]
    elif kind == "shed":
        side = (high_side or "N").upper()
        if side not in "NSEW" or len(side) != 1:
            raise ValueError(f"high side must be N, S, E or W, not {high_side!r}")
        span = d if side in "NS" else w
        heights = {"N": [0, 0, 1, 1], "S": [1, 1, 0, 0], "E": [0, 1, 1, 0], "W": [1, 0, 0, 1]}[side]
        top = [(base[i][0], base[i][1], z + span * t * heights[i]) for i in range(4)]
        verts = list(base) + top
        faces = [[0, 1, 2, 3], [4, 5, 6, 7]]
        for i in range(4):
            j = (i + 1) % 4
            if heights[i] or heights[j]:
                faces.append([i, j, 4 + j, 4 + i])
    else:
        raise ValueError(f"not a pitched roof: {kind!r}")

    verts, faces = _weld(verts, faces)
    return _orient(verts, [_clean(f, verts) for f in faces])


def _weld(verts: list[Vec], faces: list[list[int]]) -> tuple[list[Vec], list[list[int]]]:
    """Merge vertices that sit at the same point (a shed's low edge has a corner above a corner at height zero) so every edge is shared."""
    index: dict[tuple[float, float, float], int] = {}
    out: list[Vec] = []
    remap: list[int] = []
    for v in verts:
        key = (round(v[0], 6), round(v[1], 6), round(v[2], 6))
        if key not in index:
            index[key] = len(out)
            out.append(v)
        remap.append(index[key])
    return out, [[remap[i] for i in f] for f in faces]


def _clean(face: list[int], verts: list[Vec]) -> list[int]:
    """Drop vertices that sit on top of each other (a shed's low edge has zero height) so a face never has repeated points."""
    out: list[int] = []
    for i in face:
        if not out or verts[i] != verts[out[-1]]:
            out.append(i)
    if len(out) > 1 and verts[out[0]] == verts[out[-1]]:
        out.pop()
    return out


def _orient(verts: list[Vec], faces: list[list[int]]) -> tuple[list[Vec], list[Tri]]:
    cx = sum(v[0] for v in verts) / len(verts)
    cy = sum(v[1] for v in verts) / len(verts)
    cz = sum(v[2] for v in verts) / len(verts)
    tris: list[Tri] = []
    for f in faces:
        if len(f) < 3:
            continue
        # Newell normal, flipped when it points at the middle of the body
        nx = ny = nz = 0.0
        for k, i in enumerate(f):
            a, b = verts[i], verts[f[(k + 1) % len(f)]]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        if math.sqrt(nx * nx + ny * ny + nz * nz) < 1e-9:
            continue
        mx = sum(verts[i][0] for i in f) / len(f)
        my = sum(verts[i][1] for i in f) / len(f)
        mz = sum(verts[i][2] for i in f) / len(f)
        ordered = f if (nx * (mx - cx) + ny * (my - cy) + nz * (mz - cz)) > 0 else list(reversed(f))
        for k in range(1, len(ordered) - 1):
            tris.append((ordered[0], ordered[k], ordered[k + 1]))
    return verts, tris


def mesh_volume(verts: list[Vec], tris: list[Tri]) -> float:
    """Signed volume by the divergence theorem: positive for a closed mesh with outward-facing triangles."""
    v = 0.0
    for a, b, c in tris:
        p, q, r = verts[a], verts[b], verts[c]
        v += (p[0] * (q[1] * r[2] - q[2] * r[1]) - p[1] * (q[0] * r[2] - q[2] * r[0]) + p[2] * (q[0] * r[1] - q[1] * r[0])) / 6
    return v
