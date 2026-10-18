"""An indicative design check of a version against a small set of residential rules.

NOT a code compliance report. The rule set is a handful of dwelling rules in the style of the US International Residential Code
(2021), written in our own words with the section numbers as pointers. Real approval needs the local code, the local authority and a
licensed professional. What the model does not contain (handrails, guards, smoke alarms, fire separation, structure) is not checked.
"""

from __future__ import annotations

from typing import Any

from ..domain.design import Design
from ..domain.spec import BuildingSpec

RULESET = "US IRC 2021, dwellings (indicative, partial)"
HABITABLE = {"living", "bedroom", "kitchen", "dining", "office", "classroom", "reception", "meeting"}
MIN_EXIT_DOOR_CLEAR_M = 0.813       # R311.2: 32 in clear
DOOR_FRAME_ALLOWANCE_M = 0.05
MAX_RISER_M = 0.196                 # R311.7.5.1: 7 3/4 in
MIN_TREAD_M = 0.254                 # R311.7.5.2: 10 in
MIN_STAIR_WIDTH_M = 0.914           # R311.7.1: 36 in
MIN_CEILING_M = 2.134               # R305.1: 7 ft
DAYLIGHT_RATIO = 0.08               # R303.1: glazing at least 8 % of floor area
VENT_RATIO = 0.04                   # R303.1: openable at least 4 %
EGRESS_MIN_AREA_M2 = 0.53           # R310.2.1: 5.7 sf
EGRESS_MIN_HEIGHT_M = 0.61          # 24 in
EGRESS_MIN_WIDTH_M = 0.508          # 20 in
EGRESS_MAX_SILL_M = 1.118           # 44 in


def _clause(cid: str, title: str, section: str, status: str, measured: str, required: str, elements: list[str], fix: str = "") -> dict[str, Any]:
    return {"id": cid, "title": title, "section": section, "status": status, "measured": measured, "required": required, "elements": elements, "fix": fix}


def review(design: Design, spec: BuildingSpec) -> dict[str, Any]:
    clauses: list[dict[str, Any]] = []
    walls = {w.id: w for w in spec.walls}
    ground = spec.levels[0].id if spec.levels else ""

    exits = [o for o in spec.openings if o.kind == "door" and walls[o.host].external and o.level == ground]
    clauses.append(_clause("exits", "Exit from the building", "IRC R311.1", "pass" if exits else "fail", f"{len(exits)} exterior door(s) on {ground}", "at least 1",
                           [o.id for o in exits], "" if exits else "Add a door with 'to: outside' in a ground-floor room."))
    if exits:
        narrow = [o for o in exits if o.width - DOOR_FRAME_ALLOWANCE_M < MIN_EXIT_DOOR_CLEAR_M]
        best = max(o.width for o in exits) - DOOR_FRAME_ALLOWANCE_M
        clauses.append(_clause("exit-width", "Exit door width", "IRC R311.2", "pass" if len(narrow) < len(exits) else "fail", f"{best * 1000:.0f} mm clear on the widest",
                               f">= {MIN_EXIT_DOOR_CLEAR_M * 1000:.0f} mm on one door", [o.id for o in (exits if narrow == exits else [])],
                               "Make one exterior door at least 0.9 m wide." if len(narrow) == len(exits) else ""))

    for i, lv in enumerate(spec.levels[1:], 1):
        below = spec.levels[i - 1].id
        has = any(s.level == below and s.to_level == lv.id for s in spec.stairs)
        clauses.append(_clause(f"egress-{lv.id}", f"Way down from {lv.id}", "IRC R311.7", "pass" if has else "fail", "a stair" if has else "no stair",
                               f"a stair from {below}", [s.id for s in spec.stairs if s.to_level == lv.id], "" if has else f"Add a stair from {below} to {lv.id}."))

    for st in spec.stairs:
        ok = st.riser_height <= MAX_RISER_M + 1e-9 and st.going >= MIN_TREAD_M - 1e-9 and st.width >= MIN_STAIR_WIDTH_M - 1e-9
        clauses.append(_clause(f"{st.id}", f"Stair geometry: {st.id}", "IRC R311.7.1, R311.7.5", "pass" if ok else "fail",
                               f"riser {st.riser_height * 1000:.0f} mm, tread {st.going * 1000:.0f} mm, width {st.width * 1000:.0f} mm",
                               f"riser <= {MAX_RISER_M * 1000:.0f}, tread >= {MIN_TREAD_M * 1000:.0f}, width >= {MIN_STAIR_WIDTH_M * 1000:.0f} mm", [st.id],
                               "" if ok else "Use a wider stair or a taller storey split."))

    if spec.levels:
        low = min(spec.levels, key=lambda lv: lv.height)
        clear = low.height - 0.2          # floor slab depth; finishes and ceiling build-up are not modelled
        clauses.append(_clause("ceiling", "Ceiling height", "IRC R305.1", "pass" if clear >= MIN_CEILING_M else "fail", f"{clear:.2f} m clear ({low.id}, slab deducted)",
                               f">= {MIN_CEILING_M:.2f} m", [], "" if clear >= MIN_CEILING_M else f"Raise {low.id} to at least 2.4 m."))

    by_room: dict[str, list] = {}
    for w in design.windows:
        o = next((o for o in spec.openings if o.id == w.id), None)
        if o is not None:
            by_room.setdefault(w.room, []).append(o)
    for r in design.rooms:
        if r.kind not in HABITABLE:
            continue
        area = r.rect[2] * r.rect[3]
        glass = sum(o.width * o.height for o in by_room.get(r.id, []))
        ratio = glass / area if area else 0
        clauses.append(_clause(f"light-{r.id}", f"Daylight and fresh air: {r.name}", "IRC R303.1", "pass" if ratio >= DAYLIGHT_RATIO else "fail",
                               f"glazing {ratio * 100:.1f} % of {area:.1f} m2 (assumes windows open fully)", f">= {DAYLIGHT_RATIO * 100:.0f} % light, >= {VENT_RATIO * 100:.0f} % openable",
                               [o.id for o in by_room.get(r.id, [])], "" if ratio >= DAYLIGHT_RATIO else f"Add or enlarge a window in '{r.name}'."))
        if r.kind == "bedroom":
            good = [o for o in by_room.get(r.id, []) if o.width * o.height >= EGRESS_MIN_AREA_M2 and o.height >= EGRESS_MIN_HEIGHT_M
                    and o.width >= EGRESS_MIN_WIDTH_M and o.sill <= EGRESS_MAX_SILL_M]
            clauses.append(_clause(f"escape-{r.id}", f"Emergency escape opening: {r.name}", "IRC R310.1", "pass" if good else "fail",
                                   f"{len(good)} opening(s) big enough", f"area >= {EGRESS_MIN_AREA_M2} m2, height >= {EGRESS_MIN_HEIGHT_M} m, width >= {EGRESS_MIN_WIDTH_M} m, sill <= {EGRESS_MAX_SILL_M} m",
                                   [o.id for o in by_room.get(r.id, [])], "" if good else f"Give '{r.name}' a window of at least 0.6 x 0.9 m with a sill under 1.1 m."))

    clauses.append(_clause("not-modelled", "Not modelled, so not checked", "-", "info", "handrails, guards, smoke alarms, fire separation, structure, plumbing, energy", "-", []))
    counts = {k: sum(c["status"] == k for c in clauses) for k in ("pass", "fail", "info")}
    area = sum(s.area for s in spec.spaces)
    return {"ruleset": RULESET, "disclaimer": "Indicative only. Not a compliance report; check the local code with a licensed professional.",
            "summary": {"gross_area_m2": round(area, 1), "levels": len(spec.levels), "rooms": len(spec.spaces), **counts}, "clauses": clauses}
