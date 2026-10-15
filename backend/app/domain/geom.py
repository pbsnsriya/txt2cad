"""Plan geometry shared by every exporter, so IFC and DXF agree to the millimetre."""

from __future__ import annotations

import math

from .spec import Point


def wall_outline(start: Point, end: Point, thickness: float) -> tuple[list[Point], Point, Point]:
    """Rectangle around the wall axis, extended by half a thickness at both ends so corners close. Also returns the unit
    vectors along the wall and across it."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    e = h = thickness / 2
    pts = [(start[0] - ux * e + nx * h, start[1] - uy * e + ny * h), (end[0] + ux * e + nx * h, end[1] + uy * e + ny * h),
           (end[0] + ux * e - nx * h, end[1] + uy * e - ny * h), (start[0] - ux * e - nx * h, start[1] - uy * e - ny * h)]
    return pts, (ux, uy), (nx, ny)


def box_on_wall(centre: Point, u: Point, n: Point, width: float, thickness: float) -> list[Point]:
    hw, ht = width / 2, thickness / 2
    return [(centre[0] - u[0] * hw + n[0] * ht, centre[1] - u[1] * hw + n[1] * ht), (centre[0] + u[0] * hw + n[0] * ht, centre[1] + u[1] * hw + n[1] * ht),
            (centre[0] + u[0] * hw - n[0] * ht, centre[1] + u[1] * hw - n[1] * ht), (centre[0] - u[0] * hw - n[0] * ht, centre[1] - u[1] * hw - n[1] * ht)]


def stair_profile(risers: int, riser_height: float, going: float) -> list[tuple[float, float]]:
    """The side view of a flight as (run, height) points. n risers means n-1 treads inside the flight: the last riser lifts onto the
    floor above, so the solid ends at the top tread."""
    r, g, n = riser_height, going, risers
    pts = [(0.0, 0.0), (0.0, r)]
    for i in range(1, n):
        pts.append((i * g, i * r))
        if i < n - 1:
            pts.append((i * g, (i + 1) * r))
    pts.append(((n - 1) * g, 0.0))
    return pts
