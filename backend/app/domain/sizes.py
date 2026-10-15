"""Sizes stated in a prompt ("living room 5 m by 4 m", "35 square metres", "12 x 9 overall") as checkable requirements.

Read with plain patterns, not by the model: a model that is asked to list requirements tends to leave the numbers out, and the numbers
are the part that can be measured. Each size is tied to the nearest thing it describes (a room kind, or the whole building).
"""

from __future__ import annotations

import re
from typing import Any

FT = 0.3048
SQFT = FT * FT
MIN_SIDE, MAX_SIDE = 1.0, 200.0
MIN_AREA, MAX_AREA = 2.0, 40000.0

_NUM = r"(\d+(?:\.\d+)?)"
_LEN = r"(?:\s*(metres?|meters?|m|feet|foot|ft|'))?"
DIM_RE = re.compile(_NUM + _LEN + r"\s*(?:by|x|×|\*)\s*" + _NUM + _LEN + r"(?![\w²])", re.IGNORECASE)
AREA_RE = re.compile(_NUM + r"\s*-?\s*(sq\.?\s?ft|sqft|square\s+(?:feet|foot|ft)|sq\.?\s?m|sqm|square\s+met(?:re|er)s?|m\^?2|m²)(?![a-z])", re.IGNORECASE)

# keyword is what the checker matches against a room's kind or name
ROOM_WORDS: list[tuple[str, str, str]] = [
    (r"living\s*rooms?|lounge|sitting\s*room|living", "living", "living room"),
    (r"master\s*bed\s*rooms?|bed\s*rooms?", "bedroom", "bedroom"),
    (r"kitchen(?:ette)?", "kitchen", "kitchen"),
    (r"bath\s*rooms?|toilets?|wc|ensuite|en-suite", "bathroom", "bathroom"),
    (r"garage", "garage", "garage"),
    (r"dining(?:\s*room|\s*area)?", "dining", "dining room"),
    (r"offices?|study|workspace", "office", "office"),
    (r"hall(?:way)?|corridor|entrance", "hall", "hall"),
    (r"utility", "utility", "utility room"),
    (r"storage|store\s*room", "storage", "storage room"),
    (r"meeting\s*rooms?", "meeting", "meeting room"),
]
BUILDING_WORDS = r"house|bungalow|cabin|villa|townhouse|building|flat|apartment|studio|floor|overall|total|footprint|home|residence|cottage"
PLOT_WORDS = r"plot|lot|site|parcel|land|garden|yard|lawn"
_STOP = {"a", "an", "and", "the", "with", "of", "in", "for", "on", "at", "to", "is", "are", "plus", "has", "have"}


def _subjects(text: str) -> list[tuple[int, int, str, str]]:
    """Every thing a size could describe: (start, end, keyword, label); keyword 'building' or '' (a plot) are the special ones."""
    out: list[tuple[int, int, str, str]] = []
    for pattern, keyword, label in ROOM_WORDS:
        for m in re.finditer(rf"\b(?:{pattern})\b", text, re.IGNORECASE):
            out.append((m.start(), m.end(), keyword, label))
    for m in re.finditer(rf"\b(?:{BUILDING_WORDS})\b", text, re.IGNORECASE):
        out.append((m.start(), m.end(), "building", "building"))
    for m in re.finditer(rf"\b(?:{PLOT_WORDS})\b", text, re.IGNORECASE):
        out.append((m.start(), m.end(), "", "plot"))
    return out


def _subject_for(text: str, start: int, end: int) -> tuple[str, str] | None:
    subs = _subjects(text)
    # before: the closest subject ending before the number, with at most three plain words between and no sentence break
    before = None
    for s in subs:
        if s[1] <= start:
            gap = text[s[1]:start]
            if re.search(r"[.;!?]", gap) or len(gap.split()) > 3:
                continue
            if before is None or s[1] > before[1]:
                before = s
    # after: a subject right behind the number ("a 6 x 3.5 m kitchen"), at most one plain word between
    after = None
    for s in subs:
        if s[0] >= end:
            gap = text[end:s[0]]
            words = gap.replace(",", " ").split()
            if re.search(r"[.;!?]", gap) or len(words) > 1 or (words and words[0].lower() in _STOP) or "," in gap:
                continue
            if after is None or s[0] < after[0]:
                after = s
    if before and after:
        before_words = len(text[before[1]:start].split())
        after_words = len(text[end:after[0]].split())
        chosen = after if (after_words == 0 and before_words >= 2) else before
    else:
        chosen = before or after
    if chosen is None or chosen[2] == "":
        return None
    return chosen[2], chosen[3]


def _units(u1: str | None, u2: str | None) -> float:
    feet = any(u and (u.lower().startswith("f") or u == "'") for u in (u1, u2))
    return FT if feet else 1.0


def extract(prompt: str) -> list[dict[str, Any]]:
    """Requirement items (same shape as checks.normalise returns) for every size the prompt states, in reading order."""
    found: list[tuple[int, dict[str, Any]]] = []
    taken: list[tuple[int, int]] = []
    for m in DIM_RE.finditer(prompt):
        scale = _units(m.group(2), m.group(4))
        w, d = round(float(m.group(1)) * scale, 2), round(float(m.group(3)) * scale, 2)
        if not (MIN_SIDE <= w <= MAX_SIDE and MIN_SIDE <= d <= MAX_SIDE):
            continue
        subject = _subject_for(prompt, m.start(), m.end())
        if subject is None:
            continue
        keyword, label = subject
        text = (f"The building footprint is {w:.1f} x {d:.1f} m" if keyword == "building" else f"The {label} is {w:.1f} x {d:.1f} m")
        found.append((m.start(), {"kind": "dimension", "text": text, "supported": True, "params": {"keyword": keyword, "width": w, "depth": d}}))
        taken.append((m.start(), m.end()))
    for m in AREA_RE.finditer(prompt):
        if any(a <= m.start() < b for a, b in taken):
            continue
        unit = m.group(2).lower()
        scale = SQFT if "f" in unit else 1.0
        area = round(float(m.group(1)) * scale, 2)
        if not (MIN_AREA <= area <= MAX_AREA):
            continue
        subject = _subject_for(prompt, m.start(), m.end())
        if subject is None:
            continue
        keyword, label = subject
        shown = f"{area:.0f}" if abs(area - round(area)) < 0.05 else f"{area:.1f}"
        text = (f"The total floor area is about {shown} m2" if keyword == "building" else f"The {label} is about {shown} m2")
        found.append((m.start(), {"kind": "area", "text": text, "supported": True, "params": {"keyword": keyword, "area": area}}))
    return [item for _, item in sorted(found, key=lambda t: t[0])]
