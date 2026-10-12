"""Quantity take-off straight from the geometry: areas, volumes and counts a quantity surveyor starts from.

No prices here. Costs depend on place and date, so the app only multiplies these quantities by rates the user types in.
"""

from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon

from ..domain.spec import BuildingSpec


def _poly_area(outline, holes) -> float:
    return Polygon(outline, holes).area


def quantities(spec: BuildingSpec) -> dict[str, Any]:
    walls = {w.id: w for w in spec.walls}
    opening_area: dict[str, float] = {}
    for o in spec.openings:
        opening_area[o.host] = opening_area.get(o.host, 0.0) + o.width * o.height

    def net(w) -> float:
        return max(w.length * w.height - opening_area.get(w.id, 0.0), 0.0)

    rows: list[dict[str, Any]] = []

    def row(group: str, item: str, qty: float, unit: str, note: str = "") -> None:
        rows.append({"group": group, "item": item, "qty": round(qty, 2), "unit": unit, "note": note})

    for lv in spec.levels:
        rows_before = len(rows)
        row("Floor area", f"{lv.name or lv.id}: net room area", sum(s.area for s in spec.spaces if s.level == lv.id), "m2", "inside the walls")
        slab = sum(_poly_area(s.outline, s.holes) for s in spec.slabs if s.level == lv.id)
        thick = next((s.thickness for s in spec.slabs if s.level == lv.id), 0.0)
        row("Floors", f"{lv.name or lv.id}: slab", slab, "m2", f"{thick * 1000:.0f} mm thick, stairwell deducted")
        row("Floors", f"{lv.name or lv.id}: slab volume", slab * thick, "m3")
        assert len(rows) > rows_before
    roof = sum(_poly_area(r.outline, []) for r in spec.roofs)
    row("Roof", "Roof (flat)", roof, "m2")
    materials = sorted({w.material for w in spec.walls if w.external})
    for m in materials:
        row("External walls", f"External wall, {m} (net of openings)", sum(net(w) for w in spec.walls if w.external and w.material == m), "m2",
            f"{next(w.thickness for w in spec.walls if w.external and w.material == m) * 1000:.0f} mm")
    row("Internal walls", "Partition wall (net of openings)", sum(net(w) for w in spec.walls if not w.external), "m2",
        f"{next((w.thickness for w in spec.walls if not w.external), 0) * 1000:.0f} mm")
    wins = [o for o in spec.openings if o.kind == "window"]
    doors = [o for o in spec.openings if o.kind == "door"]
    row("Openings", "Windows", len(wins), "no.", f"{sum(o.width * o.height for o in wins):.1f} m2 of glazing")
    row("Openings", "Doors", len(doors), "no.", f"{sum(1 for o in doors if walls[o.host].external)} external")
    row("Stairs", "Stair flights", len(spec.stairs), "no.", ", ".join(f"{s.risers} risers" for s in spec.stairs))
    total = sum(s.area for s in spec.spaces)
    return {"rows": rows, "rooms": [{"name": s.name, "level": s.level, "kind": s.kind, "area_m2": s.area} for s in spec.spaces],
            "totals": {"net_area_m2": round(total, 1), "elements": spec.element_count()}}
