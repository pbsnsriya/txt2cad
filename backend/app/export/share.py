"""The shareable page: one HTML file with the model, the viewer and its styles inside, that opens offline in any browser.

The model is read back from the saved IFC (so the page shows exactly what the IFC holds), turned into small triangle meshes with their colours, and packed as gzip + base64 JSON.
Nothing in the page is fetched from anywhere, and a Content-Security-Policy in it says so to the browser. The request text is not included; the project name, the version, the summary
and the room names are.
"""

from __future__ import annotations

import base64
import gzip
import html
import json
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as util
import numpy as np

ASSETS = Path(__file__).resolve().parent / "assets"
PAGE = Path(__file__).resolve().parent / "share_page.html"

CATEGORY = {
    "IfcWall": "wall", "IfcWallStandardCase": "wall", "IfcSlab": "floor", "IfcRoof": "roof", "IfcDoor": "opening", "IfcWindow": "opening", "IfcStair": "stair",
    "IfcStairFlight": "stair", "IfcFurniture": "furniture", "IfcLightFixture": "furniture", "IfcCovering": "finish",
}
SKIPPED = {"IfcOpeningElement", "IfcSpace"}
LABEL_HEIGHT = 1.1          # metres above a room's floor, where its name floats


def _b64(array: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(array).tobytes()).decode("ascii")


def _level_of(product: Any, levels: dict[int, int]) -> int:
    """Index of the storey an element is on, or -1."""
    for finder in (util.get_container, util.get_aggregate):
        try:
            parent = finder(product)
        except Exception:                                  # an element with an odd relationship is shown on no level rather than failing the export
            parent = None
        while parent is not None and not parent.is_a("IfcBuildingStorey"):
            parent = util.get_aggregate(parent)
        if parent is not None:
            return levels.get(parent.id(), -1)
    return -1


def model_data(ifc_path: Path, *, title: str, version: int, created: str, summary: str, app: str) -> dict[str, Any]:
    """The model in the form the page reads: levels, elements with coloured triangle parts, and room labels."""
    model = ifcopenshell.open(str(ifc_path))
    storeys = sorted(model.by_type("IfcBuildingStorey"), key=lambda s: float(s.Elevation or 0))
    levels = {s.id(): i for i, s in enumerate(storeys)}
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    elements: list[dict[str, Any]] = []
    rooms: list[dict[str, Any]] = []
    iterator = ifcopenshell.geom.iterator(settings, model, 4)
    if iterator.initialize():
        while True:
            shape = iterator.get()
            product = model.by_id(shape.id)
            cls = product.is_a()
            geo = shape.geometry
            verts = np.array(geo.verts, dtype=np.float64).reshape(-1, 3)
            if len(verts) == 0:
                if not iterator.next():
                    break
                continue
            lv = _level_of(product, levels)
            if cls == "IfcSpace":
                lo, hi = verts.min(axis=0), verts.max(axis=0)
                rooms.append({"name": product.LongName or product.Name or "Room", "lv": lv, "c": [round(float((lo[0] + hi[0]) / 2), 3), round(float((lo[1] + hi[1]) / 2), 3), round(float(lo[2] + LABEL_HEIGHT), 3)]})
            elif cls not in SKIPPED:
                faces = np.array(geo.faces, dtype=np.int64).reshape(-1, 3)
                material_ids = np.array(geo.material_ids, dtype=np.int64)
                parts = []
                for mid in sorted(set(material_ids.tolist())):
                    tri = faces[material_ids == mid]
                    used, inverse = np.unique(tri, return_inverse=True)
                    style = geo.materials[mid] if 0 <= mid < len(geo.materials) else None
                    colour = [style.diffuse.r(), style.diffuse.g(), style.diffuse.b()] if style is not None and style.diffuse is not None else [0.75, 0.75, 0.75]
                    opacity = 1.0 - float(style.transparency or 0.0) if style is not None else 1.0
                    parts.append({"c": [round(float(x), 3) for x in colour], "o": round(opacity, 3), "p": _b64(np.round(verts[used], 3).astype(np.float32)),
                                  "i": _b64(inverse.reshape(-1).astype(np.uint32))})
                if parts:
                    elements.append({"id": product.GlobalId, "cls": cls, "cat": CATEGORY.get(cls, "other"), "name": product.Name or cls.replace("Ifc", ""), "lv": lv, "parts": parts})
            if not iterator.next():
                break
    elements.sort(key=lambda e: (e["lv"], e["cat"], e["id"]))                      # the same IFC always gives the same page
    rooms.sort(key=lambda r: (r["lv"], r["name"], r["c"]))
    return {"v": 1, "title": title, "version": version, "created": created, "summary": summary, "app": app,
            "levels": [{"id": s.GlobalId, "name": s.Name or f"Level {i + 1}", "z": float(s.Elevation or 0)} for i, s in enumerate(storeys)], "elements": elements, "rooms": rooms}


def pack(data: dict[str, Any]) -> str:
    """gzip then base64, with a fixed header so the same model always packs to the same text."""
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode("ascii")


def _script(text: str) -> str:
    return text.replace("</script", "<\\/script")                                    # a script tag must not end early, whatever the bundle contains


def share_html(ifc_path: Path, *, title: str, version: int, created: str, summary: str, app_version: str) -> str:
    """The whole page as text."""
    data = model_data(ifc_path, title=title, version=version, created=created, summary=summary, app=f"txt2cad {app_version}")
    meta = f"Version {version} · {len(data['elements'])} elements"
    page = PAGE.read_text(encoding="utf-8")
    style = (ASSETS / "share-viewer.css").read_text(encoding="utf-8").replace("</style", "<\\/style")
    script = _script((ASSETS / "share-viewer.js").read_text(encoding="utf-8"))
    # the person-written texts are escaped; the packed data is base64, which has no markup in it
    out = page
    for key, value in (("__TITLE__", html.escape(title, quote=True)), ("__DESCRIPTION__", html.escape(summary[:300], quote=True)), ("__META__", html.escape(meta)),
                       ("__SUMMARY__", html.escape(summary)), ("__APP_VERSION__", html.escape(app_version))):
        out = out.replace(key, value)
    return out.replace("__STYLE__", style).replace("__DATA__", pack(data)).replace("__SCRIPT__", script)
