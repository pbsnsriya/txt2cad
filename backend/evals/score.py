"""Score one finished design against what the request asked for, independently of the model's own checklist.

A case passes only when every check passes. The checks are the same kind a person would make with a tape measure and a plan:
are the rooms there, on the right floors, the right size, with doors to reach them and windows for light, and did it say so about what it cannot build?
"""

from __future__ import annotations

from typing import Any

from app.domain import checks
from app.domain.catalogue import FLOORS, PAINTS, resolve
from app.domain.derive import DesignError, derive
from app.domain.design import Design
from app.domain.envelope import find_unsupported
from app.domain.steps import tidy_name

Check = dict[str, Any]


def _check(name: str, ok: bool, detail: str = "") -> Check:
    return {"name": name, "ok": bool(ok), "detail": detail}


def score(design: Design | None, case: dict[str, Any], *, saved: bool, notes: list[str] | None = None, requirements: list[dict[str, Any]] | None = None,
          base: Design | None = None) -> list[Check]:
    """Every check for one case, in order. A run that saved nothing fails the first check and nothing else is asked."""
    out = [_check("saved", saved, "" if saved else "the run did not save a version")]
    if not saved or design is None:
        return out
    exp = case.get("expect", {})
    notes = notes or []
    requirements = requirements or []

    try:
        derive(design)
        out.append(_check("builds", True))
    except DesignError as exc:
        out.append(_check("builds", False, str(exc)))
    out.append(_check("plain names", all(tidy_name(r.name, r.kind) == r.name for r in design.rooms),
                      ", ".join(r.name for r in design.rooms if tidy_name(r.name, r.kind) != r.name)))
    problems = checks.completeness(design)
    out.append(_check("doors, windows, stairs", not problems, "; ".join(problems[:3])))

    if "storeys" in exp:
        out.append(_check("storeys", design.storeys() == exp["storeys"], f"wanted {exp['storeys']}, has {design.storeys()}"))
    for kind, n in exp.get("rooms", {}).items():
        have = len(checks._matching_rooms(design, kind, None))
        out.append(_check(f"{n} {kind}", have >= n, f"has {have}"))
    for kind, level in exp.get("on_level", {}).items():
        found = checks._matching_rooms(design, kind, None)
        wrong = [r.name for r in found if r.level != level]
        out.append(_check(f"{kind} on {level}", bool(found) and not wrong, ("none found" if not found else f"on another level: {', '.join(wrong)}")))
    if "footprint" in exp:
        got = checks._footprint(design)
        out.append(_check("footprint", got is not None and checks._same_size(got, tuple(exp["footprint"]), checks.FOOTPRINT_TOLERANCE_M), f"wanted {exp['footprint']}, built {got}"))
    if "area" in exp:
        total = sum(r.rect[2] * r.rect[3] for r in design.rooms)
        lo, hi = exp["area"]
        out.append(_check("area", lo <= total <= hi, f"wanted {lo} to {hi} m2, built {total:.1f}"))
    for kind, dims in exp.get("room_dims", {}).items():
        rooms = checks._matching_rooms(design, kind, None)
        ok = any(checks._same_size((r.rect[2], r.rect[3]), tuple(dims), checks.SIZE_TOLERANCE_M) for r in rooms)
        out.append(_check(f"{kind} {dims[0]:g} x {dims[1]:g}", ok, ", ".join(f"{r.rect[2]:g} x {r.rect[3]:g}" for r in rooms) or "no such room"))
    if "roof" in exp:
        out.append(_check("roof", design.roof == exp["roof"], f"wanted {exp['roof']}, has {design.roof}"))
    if exp.get("furnished"):
        status, detail = checks._check_furniture(design)
        out.append(_check("furnished", status == "met", detail))
    for kind, want in exp.get("floor", {}).items():
        rooms = checks._matching_rooms(design, kind, None)
        out.append(_check(f"{kind} floor {want}", any(_same_colour(r.floor, want, FLOORS) for r in rooms), ", ".join(str(r.floor) for r in rooms) or "no such room"))
    for kind, want in exp.get("walls", {}).items():
        rooms = checks._matching_rooms(design, kind, None)
        out.append(_check(f"{kind} walls {want}", any(_same_colour(r.walls, want, PAINTS) for r in rooms), ", ".join(str(r.walls) for r in rooms) or "no such room"))
    if "furniture_kinds" in exp:
        have = {f.kind for f in design.furniture}
        missing = [k for k in exp["furniture_kinds"] if k not in have]
        out.append(_check("furniture", not missing, f"missing {', '.join(missing)}"))
    if "shape" in exp:
        got = checks._outline_shape(design)
        out.append(_check(f"{exp['shape']}-shaped", got == exp["shape"], f"the outline is {got}"))
    if exp.get("courtyard"):
        status, detail = checks._check_shape(design, "courtyard", "courtyard")
        out.append(_check("courtyard", status == "met", detail))
    for word in exp.get("unsupported", []):
        said = [n for n in notes if word in n.lower()] + [r["text"] for r in requirements if r.get("status") == "unsupported" and word in r["text"].lower()]
        out.append(_check(f"says '{word}' is not built", bool(said), "it is neither in the notes nor in the checklist as not built" if not said else ""))
    if base is not None:
        for kind in exp.get("kept", []):
            before = checks._matching_rooms(base, kind, None)
            after = checks._matching_rooms(design, kind, None)
            same = bool(before) and {tuple(r.rect) for r in before} <= {tuple(r.rect) for r in after}
            out.append(_check(f"kept the {kind}", same, "a room that was not meant to change moved or went"))
    return out


def _same_colour(token: str | None, want: str, palette: dict[str, str]) -> bool:
    if not token:
        return False
    try:
        return resolve(token, palette, "x") == resolve(want, palette, "x")
    except ValueError:
        return False


def verdict(checks_: list[Check]) -> dict[str, Any]:
    ok = sum(1 for c in checks_ if c["ok"])
    return {"pass": all(c["ok"] for c in checks_), "score": round(ok / len(checks_), 3) if checks_ else 0.0, "failed": [c for c in checks_ if not c["ok"]]}


def unsupported_in(prompt: str) -> list[str]:
    return find_unsupported(prompt)
