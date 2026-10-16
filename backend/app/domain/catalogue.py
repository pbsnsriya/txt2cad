"""The furniture and finishes the tool knows: their sizes, their shapes (a few boxes each) and their colours.

A furniture piece is drawn in its own frame: the footprint is centred on the origin, x is across, y runs from the back (negative) to the front (positive).
A piece placed with its back against the south wall therefore faces north. Every shape is a handful of boxes so it reads as the thing it is in 3D
without a mesh library.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

Box = tuple[float, float, float, float, float, float, str]        # x0, y0, x1, y1, z0, z1, colour key

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Named colours for finishes and for pieces. A request can also give any #rrggbb.
FLOORS: dict[str, str] = {
    "oak": "#b89464", "walnut": "#6b4a2f", "birch": "#d9bf94", "parquet": "#a97e4f", "pine": "#cfa66a", "tile": "#d8d8d4", "marble": "#e6e3dc",
    "stone": "#9b9a94", "concrete": "#9c9c9c", "carpet": "#8a8d96", "beige carpet": "#c9b99a", "slate": "#4b5058", "terracotta": "#b4673f", "white": "#f2f2f0",
}
PAINTS: dict[str, str] = {
    "white": "#f4f3ef", "cream": "#efe3c8", "grey": "#a7a9ad", "light grey": "#d0d2d5", "charcoal": "#4a4d52", "black": "#1f2124", "blue": "#6f93c4",
    "navy": "#27406b", "green": "#7da684", "sage": "#a8b89b", "yellow": "#e8cf6a", "pink": "#e2a6b4", "terracotta": "#c0704c", "brown": "#7a5a43",
    "red": "#b5483f", "teal": "#4f8c92", "lavender": "#b6a6d1", "beige": "#d8c8aa",
}
COLOURS: dict[str, str] = {**PAINTS, **{k: v for k, v in FLOORS.items() if k not in PAINTS}, "oak": "#b89464", "wood": "#a9794a", "fabric": "#7d8590", "steel": "#b9bcc0"}

# colour keys used inside a shape; "main" is the colour of the piece (the catalogue default, or the one a request chose)
PART_COLOURS = {"wood": "#a9794a", "white": "#f1f1ee", "dark": "#3a3d42", "steel": "#b9bcc0", "fabric": "#7d8590", "cushion": "#d9d6cf", "water": "#a9cfe6"}


class UnknownName(ValueError):
    pass


def resolve(name: str | None, palette: dict[str, str], what: str) -> str | None:
    """'oak', 'Light Grey' or '#aabbcc' to '#rrggbb'. None stays None. Anything else says what is allowed."""
    if name is None or str(name).strip() == "":
        return None
    key = str(name).strip().lower().replace("_", " ")
    if HEX.match(key):
        return key.lower()
    if key in palette:
        return palette[key]
    if key in COLOURS:
        return COLOURS[key]
    raise UnknownName(f"unknown {what} '{name}'; use one of {', '.join(sorted(palette))}, or a colour like #b89464")


@dataclass(frozen=True)
class Item:
    kind: str
    label: str
    w: float
    d: float
    h: float
    colour: str                    # the main colour (a COLOURS key or a PART_COLOURS key)
    ifc: str = "NOTDEFINED"        # IfcFurnitureTypeEnum value
    resizable_w: bool = False      # runs of kitchen units come in any length


def _item(kind, label, w, d, h, colour, ifc="NOTDEFINED", resizable_w=False) -> Item:
    return Item(kind, label, w, d, h, colour, ifc, resizable_w)


CATALOGUE: dict[str, Item] = {i.kind: i for i in (
    _item("bed_double", "Double bed", 1.6, 2.0, 0.9, "wood", "BED"), _item("bed_single", "Single bed", 0.9, 2.0, 0.9, "wood", "BED"),
    _item("bedside_table", "Bedside table", 0.45, 0.4, 0.5, "wood"), _item("wardrobe", "Wardrobe", 1.8, 0.6, 2.1, "wood", "FILECABINET", True),
    _item("dresser", "Chest of drawers", 1.2, 0.5, 0.9, "wood", "FILECABINET"),
    _item("desk", "Desk", 1.4, 0.7, 0.75, "wood", "DESK", True), _item("office_chair", "Office chair", 0.55, 0.55, 0.9, "dark", "CHAIR"),
    _item("bookshelf", "Bookshelf", 0.9, 0.3, 1.9, "wood", "SHELF", True),
    _item("sofa", "Sofa", 2.0, 0.9, 0.85, "fabric", "SOFA", True), _item("armchair", "Armchair", 0.85, 0.85, 0.85, "fabric", "CHAIR"),
    _item("coffee_table", "Coffee table", 1.0, 0.6, 0.4, "wood", "TABLE"), _item("tv_unit", "TV unit", 1.5, 0.4, 0.5, "wood", "NOTDEFINED", True),
    _item("dining_table", "Dining table", 1.6, 0.9, 0.75, "wood", "TABLE", True), _item("chair", "Chair", 0.45, 0.45, 0.9, "wood", "CHAIR"),
    _item("bench", "Bench", 1.2, 0.4, 0.45, "wood", "NOTDEFINED", True),
    _item("kitchen_counter", "Kitchen units", 1.2, 0.6, 0.9, "white", "NOTDEFINED", True), _item("kitchen_island", "Kitchen island", 1.8, 0.9, 0.9, "white"),
    _item("sink_unit", "Sink unit", 0.8, 0.6, 0.9, "white"), _item("cooker", "Cooker", 0.6, 0.6, 0.9, "steel"), _item("fridge", "Fridge", 0.7, 0.7, 1.8, "steel"),
    _item("toilet", "Toilet", 0.4, 0.7, 0.8, "white"), _item("basin", "Basin", 0.6, 0.45, 0.85, "white"), _item("bath", "Bath", 1.7, 0.75, 0.55, "white"),
    _item("shower", "Shower", 0.9, 0.9, 2.0, "water"), _item("washing_machine", "Washing machine", 0.6, 0.6, 0.85, "white"),
)}

KIND_WORDS = {"bed": "bed_double", "double bed": "bed_double", "single bed": "bed_single", "couch": "sofa", "table": "dining_table", "wc": "toilet",
              "sink": "sink_unit", "kitchen": "kitchen_counter", "counter": "kitchen_counter", "units": "kitchen_counter", "shelf": "bookshelf",
              "bookcase": "bookshelf", "tv": "tv_unit", "television": "tv_unit", "stove": "cooker", "oven": "cooker", "fridge freezer": "fridge",
              "refrigerator": "fridge", "cupboard": "wardrobe", "closet": "wardrobe", "nightstand": "bedside_table", "bedside": "bedside_table",
              "drawers": "dresser", "chest of drawers": "dresser", "washer": "washing_machine", "bathtub": "bath", "sofa bed": "sofa", "island": "kitchen_island"}


def item_for(word: str | None) -> Item:
    key = (word or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in CATALOGUE:
        return CATALOGUE[key]
    spaced = key.replace("_", " ")
    if spaced in KIND_WORDS:
        return CATALOGUE[KIND_WORDS[spaced]]
    raise UnknownName(f"unknown furniture '{word}'; use one of {', '.join(sorted(CATALOGUE))}")


def parts(kind: str, w: float, d: float, h: float) -> list[Box]:
    """The boxes of a piece in its own frame. Everything stays inside [-w/2, w/2] x [-d/2, d/2] x [0, h]."""
    hw, hd = w / 2, d / 2
    back = -hd
    if kind in ("bed_double", "bed_single"):
        frame_h, mat_h = 0.30, 0.50
        out = [(-hw, -hd, hw, hd, 0.0, frame_h, "main"), (-hw + 0.04, back + 0.10, hw - 0.04, hd - 0.04, frame_h, mat_h, "white"),
               (-hw, back, hw, back + 0.08, 0.0, h, "main")]
        pillow_w = (w - 0.2) / (2 if kind == "bed_double" else 1)
        for i in range(2 if kind == "bed_double" else 1):
            x0 = -hw + 0.08 + i * (pillow_w + 0.04)
            out.append((x0, back + 0.14, x0 + pillow_w - 0.04, back + 0.54, mat_h, mat_h + 0.12, "cushion"))
        return out
    if kind == "sofa":
        arm = min(0.22, w / 6)
        return [(-hw, back + 0.25, hw, hd, 0.0, 0.42, "main"), (-hw, back, hw, back + 0.25, 0.0, h, "main"),
                (-hw, back + 0.25, -hw + arm, hd, 0.0, 0.62, "main"), (hw - arm, back + 0.25, hw, hd, 0.0, 0.62, "main"),
                (-hw + arm, back + 0.25, hw - arm, hd, 0.42, 0.52, "cushion")]
    if kind == "armchair":
        return [(-hw, back + 0.2, hw, hd, 0.0, 0.42, "main"), (-hw, back, hw, back + 0.2, 0.0, h, "main"),
                (-hw, back + 0.2, -hw + 0.15, hd, 0.0, 0.6, "main"), (hw - 0.15, back + 0.2, hw, hd, 0.0, 0.6, "main")]
    if kind in ("dining_table", "coffee_table", "desk"):
        top = 0.04
        leg = 0.06
        inset = 0.05
        out = [(-hw, -hd, hw, hd, h - top, h, "main")]
        for sx in (-1, 1):
            for sy in (-1, 1):
                cx, cy = sx * (hw - inset - leg / 2), sy * (hd - inset - leg / 2)
                out.append((cx - leg / 2, cy - leg / 2, cx + leg / 2, cy + leg / 2, 0.0, h - top, "dark" if kind == "desk" else "main"))
        return out
    if kind in ("chair", "office_chair"):
        seat = 0.45
        out = [(-hw, -hd, hw, hd, seat - 0.04, seat, "main"), (-hw, back, hw, back + 0.05, seat, h, "main")]
        for sx in (-1, 1):
            for sy in (-1, 1):
                cx, cy = sx * (hw - 0.04), sy * (hd - 0.04)
                out.append((cx - 0.02, cy - 0.02, cx + 0.02, cy + 0.02, 0.0, seat - 0.04, "dark"))
        return out
    if kind in ("kitchen_counter", "sink_unit", "cooker", "washing_machine", "kitchen_island"):
        top = "dark" if kind in ("kitchen_counter", "sink_unit", "kitchen_island") else "main"
        out = [(-hw, -hd, hw, hd, 0.0, h - 0.04, "main"), (-hw - 0.01, -hd - 0.01, hw + 0.01, hd + 0.01, h - 0.04, h, top)]
        out = [(max(x0, -hw), max(y0, -hd), min(x1, hw), min(y1, hd), z0, z1, c) for x0, y0, x1, y1, z0, z1, c in out]
        if kind == "sink_unit":
            out.append((-hw * 0.5, -hd * 0.4, hw * 0.5, hd * 0.4, h, h + 0.01, "steel"))
        if kind == "cooker":
            for sx in (-1, 1):
                for sy in (-1, 1):
                    out.append((sx * hw * 0.5 - 0.09, sy * hd * 0.4 - 0.09, sx * hw * 0.5 + 0.09, sy * hd * 0.4 + 0.09, h, h + 0.02, "dark"))
        return out
    if kind == "toilet":
        return [(-hw, back, hw, back + 0.22, 0.0, h, "main"), (-hw + 0.02, back + 0.22, hw - 0.02, hd, 0.0, 0.42, "main")]
    if kind == "basin":
        return [(-0.08, back, 0.08, back + 0.15, 0.0, h - 0.15, "main"), (-hw, -hd, hw, hd, h - 0.15, h, "main")]
    if kind == "bath":
        rim = 0.08
        return [(-hw, -hd, hw, hd, 0.0, 0.2, "main"), (-hw, -hd, hw, -hd + rim, 0.2, h, "main"), (-hw, hd - rim, hw, hd, 0.2, h, "main"),
                (-hw, -hd + rim, -hw + rim, hd - rim, 0.2, h, "main"), (hw - rim, -hd + rim, hw, hd - rim, 0.2, h, "main"),
                (-hw + rim, -hd + rim, hw - rim, hd - rim, 0.2, 0.3, "water")]
    if kind == "shower":
        return [(-hw, -hd, hw, hd, 0.0, 0.06, "white"), (-hw, back, -hw + 0.02, hd, 0.06, h, "water"), (hw - 0.02, back, hw, hd, 0.06, h, "water"),
                (-hw, hd - 0.02, hw, hd, 0.06, h, "water")]
    if kind in ("wardrobe", "bookshelf", "dresser", "bedside_table", "tv_unit", "fridge", "bench"):
        out = [(-hw, -hd, hw, hd, 0.0, h, "main")]
        if kind == "bookshelf":                           # shelves read as slats
            out = [(-hw, back, hw, back + 0.03, 0.0, h, "main"), (-hw, -hd, -hw + 0.03, hd, 0.0, h, "main"), (hw - 0.03, -hd, hw, hd, 0.0, h, "main")]
            out += [(-hw, -hd, hw, hd, z, z + 0.03, "main") for z in (0.0, h * 0.25, h * 0.5, h * 0.75, h - 0.03)]
        return out
    return [(-hw, -hd, hw, hd, 0.0, h, "main")]
