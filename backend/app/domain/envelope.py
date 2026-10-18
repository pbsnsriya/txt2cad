"""What the first release builds, said once. The Home screen, the API, the composer's early warning and docs/supported.md all read from here
(a test keeps the document in step), so nobody is promised something the tool does not do."""

from __future__ import annotations

import re
from typing import Literal

Status = Literal["yes", "partly", "no"]

CAPABILITIES: list[dict[str, str]] = [
    {"id": "houses", "status": "yes", "label": "Houses, flats, small offices and shops of 1 to 5 storeys",
     "note": "Rooms are rectangles on a grid, packed edge to edge. Many more storeys are accepted but only up to 5 are tested."},
    {"id": "openings", "status": "yes", "label": "Doors, windows, archways and one straight stair per storey",
     "note": "A door wider than 2 m is read as an archway, which is how a wall is opened up."},
    {"id": "sizes", "status": "yes", "label": "Sizes you state: room sizes, the overall footprint, total areas",
     "note": "Checked after the build and shown as asked against built; metres or feet."},
    {"id": "roofs", "status": "yes", "label": "Flat, gable, hip and shed roofs",
     "note": "On plain rectangular roof areas. An L-shaped area stays flat and the version says so."},
    {"id": "shapes", "status": "partly", "label": "L-shaped and U-shaped houses, and courtyards",
     "note": "Built from rectangles that touch, with the notch left empty. Whether the model gets it right is checked and reported."},
    {"id": "interiors", "status": "yes", "label": "Furniture, floor finishes and wall paint",
     "note": "30 pieces drawn as simple blocks, including ceiling and floor lights and a plant, in colours. No textures."},
    {"id": "exports", "status": "yes", "label": "IFC4, DXF and SVG floor plans, and JSON",
     "note": "Plans have dimensions, door swings, stairs and furniture footprints."},
    {"id": "checks", "status": "partly", "label": "Design check and quantities",
     "note": "A few dwelling rules in the style of the US IRC, labelled indicative. Quantities have no prices."},
    {"id": "nonres", "status": "partly", "label": "Offices, classrooms, shops and workshops",
     "note": "As room kinds with the same walls, doors and windows. No occupancy, egress or accessibility rules."},
    {"id": "basements", "status": "no", "label": "Basements and cellars", "note": "Reported as not built; the rest is built without it."},
    {"id": "outdoors", "status": "no", "label": "Balconies, porches, verandas, pools, gardens and the plot", "note": "Reported as not built."},
    {"id": "shapes2", "status": "no", "label": "Curved or angled walls, domes, round rooms", "note": "Walls are straight and square."},
    {"id": "structure", "status": "no", "label": "Structure and services", "note": "No columns, beams, ducts, pipes, wiring or lifts."},
    {"id": "visuals", "status": "no", "label": "Textures, computed lighting and rendered images",
     "note": "Colours only. \"Save picture\" saves the 3D view as it is."},
    {"id": "import", "status": "no", "label": "Importing an existing IFC or DWG to edit", "note": "Projects start from a description."},
]

# Words in a request that name something the tool cannot build, with how to say it. Found in the composer before sending and in the checklist after.
UNSUPPORTED_WORDS: dict[str, str] = {
    "basement": "a basement", "cellar": "a cellar", "pool": "a pool", "swimming pool": "a pool", "porch": "a porch", "veranda": "a veranda", "verandah": "a veranda",
    "balcony": "a balcony", "terrace": "a terrace", "garden": "a garden", "landscaping": "landscaping", "curved wall": "curved walls", "curved walls": "curved walls",
    "round room": "round rooms", "circular": "round shapes", "dome": "a dome", "elevator": "a lift", "lift": "a lift", "escalator": "an escalator",
}


def find_unsupported(text: str) -> list[str]:
    """What a request names that the tool cannot build, each once, in the order it appears."""
    found: list[tuple[int, str]] = []
    for word, label in sorted(UNSUPPORTED_WORDS.items(), key=lambda kv: -len(kv[0])):
        m = re.search(rf"\b{re.escape(word)}s?\b", text, re.IGNORECASE)
        if m and not any(label == l for _, l in found):
            found.append((m.start(), label))
    return [label for _, label in sorted(found)]


def payload() -> dict:
    return {"capabilities": CAPABILITIES, "unsupported_words": UNSUPPORTED_WORDS}


STATUS_TITLES = {"yes": "Builds today", "partly": "Partly: read the note", "no": "Not built yet"}


def render_markdown() -> str:
    """docs/supported.md. Regenerate with: python -m app.domain.envelope --write"""
    out = ["# What txt2cad builds", "",
           "Generated from `backend/app/domain/envelope.py`; the Home screen and `GET /api/capabilities` say the same thing. Anything in the last section is",
           "named in the result as \"not built\" instead of being left out quietly.", ""]
    for status in ("yes", "partly", "no"):
        out += [f"## {STATUS_TITLES[status]}", "", "| What | Note |", "| --- | --- |"]
        out += [f"| {c['label']} | {c['note']} |" for c in CAPABILITIES if c["status"] == status]
        out.append("")
    out += ["## Words that are flagged before you send", "", ", ".join(sorted(UNSUPPORTED_WORDS)), ""]
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    from pathlib import Path

    if "--write" in sys.argv:
        target = Path(__file__).resolve().parents[3] / "docs" / "supported.md"
        target.write_text(render_markdown(), encoding="utf-8")
        print(f"wrote {target}")
    else:
        print(render_markdown())
