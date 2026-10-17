"""A result that is not worth saving: refused, with the reasons, instead of becoming a version the user pays for."""

from __future__ import annotations

from typing import Any

from ..domain.design import Design

MIN_FRACTION_OF_STATED_AREA = 0.5
MIN_KEPT_FRACTION_ON_EDIT = 0.5
MIN_ROOMS_BEFORE_EDIT_CHECK = 4


class QualityError(RuntimeError):
    """The model finished but the design is not usable. The message is shown to the user and nothing is saved."""


def problems(design: Design, results: list[dict[str, Any]], started_with: int | None) -> list[str]:
    """Reasons to refuse. `started_with` is the number of rooms before the run when it edits a building, None for a new one."""
    out: list[str] = []
    rooms = len(design.rooms)
    if started_with is not None:
        if started_with >= MIN_ROOMS_BEFORE_EDIT_CHECK and rooms < started_with * MIN_KEPT_FRACTION_ON_EDIT:
            out.append(f"the change would have removed {started_with - rooms} of the {started_with} rooms")
        return out

    checkable = [r for r in results if r["status"] in ("met", "unmet") and r["kind"] != "furniture"]      # pieces are a finish, not proof the building failed
    if len(checkable) >= 2 and not any(r["status"] == "met" for r in checkable):
        out.append(f"none of the {len(checkable)} things you asked for that can be checked were built")
    wanted = sum(int(r.get("params", {}).get("count", 1) or 1) for r in results if r["kind"] == "room" and r.get("supported", True))
    if wanted >= 3 and rooms <= 1:
        out.append(f"the request names {wanted} rooms and the design has {rooms} room" + ("" if rooms == 1 else "s"))
    total = sum(r.rect[2] * r.rect[3] for r in design.rooms)
    for r in results:
        p = r.get("params", {})
        if r["kind"] == "area" and r["status"] == "unmet" and p.get("keyword") == "building" and total < float(p.get("area", 0)) * MIN_FRACTION_OF_STATED_AREA:
            out.append(f"the design is less than half the {float(p['area']):.0f} m2 you asked for ({total:.1f} m2)")
    if rooms >= 2 and not design.doors:
        out.append("none of the rooms is connected by a door")
    return out
