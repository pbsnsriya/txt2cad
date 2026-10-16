"""A step -> one sentence about the building, plus the phase of the work it belongs to (the UI groups the trace by phase)."""

from __future__ import annotations

from ..domain.design import Design
from ..domain.steps import Step, norm_level, norm_side

SIDE_NAMES = {"N": "north", "S": "south", "E": "east", "W": "west"}
PHASES = {"project": "Setup", "storey": "Setup", "room": "Rooms", "rearrange": "Rooms", "door": "Doors and stairs", "stair": "Doors and stairs",
          "window": "Windows and roof", "roof": "Windows and roof", "material": "Windows and roof", "delete": "Changes", "remark": "Notes"}


def phase_of(step: Step) -> str:
    return PHASES.get(step.step, "Other")


def headline(step: Step, design: Design) -> str:
    k = step.step
    if k == "project":
        return f"Named the project '{design.name}'"
    if k == "storey":
        lv = design.level(norm_level(step.id) or "") or design.levels[-1]
        return f"{lv.name or lv.id} added, {lv.height:g} m floor to floor"
    if k == "room":
        r = design.rooms[-1] if design.rooms else None      # apply_step appends the room it just placed or replaced
        return f"{r.name} on {r.level}: {r.rect[2]:g} x {r.rect[3]:g} m, {r.rect[2] * r.rect[3]:.1f} m2" if r else f"Room {step.name}"
    if k == "rearrange":
        n = len([r for r in design.rooms if r.level == norm_level(step.level)])
        return f"Laid out {n} rooms on {norm_level(step.level)}"
    if k == "door":
        to = "the outside" if (step.to or "outside") == "outside" else step.to
        return f"Door from {step.room} to {to}"
    if k == "window":
        return f"Window on the {SIDE_NAMES.get(norm_side(step.side) or '', 'chosen')} wall of {step.room}"
    if k == "stair":
        s = design.stairs[-1] if design.stairs else None
        return f"Stair in {step.room} along the {SIDE_NAMES.get(norm_side(step.side) or '', 'chosen')} wall" + (f", rising to {s.to_level}" if s and s.to_level else ", rising to the next level")
    if k == "roof":
        if design.roof == "flat":
            return "Flat roof over the top floor"
        extra = f", rising to the {SIDE_NAMES.get(design.roof_high_side or 'N')}" if design.roof == "shed" else ""
        return f"{design.roof.capitalize()} roof, {design.roof_pitch:g} degrees{extra}"
    if k == "material":
        return f"Exterior walls in {step.material}"
    if k == "delete":
        return f"Removed {step.id}"
    return step.text or k


def facts(design: Design) -> dict[str, float | int]:
    area = sum(r.rect[2] * r.rect[3] for r in design.rooms)
    return {"levels": len(design.levels), "rooms": len(design.rooms), "doors": len(design.doors), "windows": len(design.windows), "gross_area_m2": round(area, 1)}
