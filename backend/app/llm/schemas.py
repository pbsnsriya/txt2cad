"""JSON Schemas handed to providers that can constrain decoding. Flat and permissive on purpose: some endpoints reject
oneOf, numeric bounds or very large grammars, so strict validation happens on our side (pydantic + apply_step)."""

from __future__ import annotations

from typing import Any

STEP_KINDS = ["project", "storey", "room", "rearrange", "door", "window", "stair", "roof", "material", "furnish", "furniture", "finish", "delete", "remark"]
REQUIREMENT_KINDS = ["storeys", "room", "feature", "area", "dimension", "adjacent", "orientation", "window", "door", "material", "style", "other"]

_step_props: dict[str, Any] = {
    "step": {"type": "string", "enum": STEP_KINDS},
    "why": {"type": "string"}, "id": {"type": "string"}, "name": {"type": "string"}, "description": {"type": "string"},
    "level": {"type": "string"}, "kind": {"type": "string"}, "height": {"type": "number"},
    "rect": {"type": "array", "items": {"type": "number"}},
    "rooms": {"type": "array", "items": {"type": "object", "properties": {
        "name": {"type": "string"}, "kind": {"type": "string"}, "rect": {"type": "array", "items": {"type": "number"}}, "roofed": {"type": "boolean"}},
        "required": ["name", "rect"]}},
    "roofed": {"type": "boolean"}, "room": {"type": "string"}, "to": {"type": "string"}, "side": {"type": "string"},
    "to_level": {"type": "string"}, "at": {"type": "number"}, "across": {"type": "number"}, "gap": {"type": "number"}, "depth": {"type": "number"}, "rotation": {"type": "integer"},
    "colour": {"type": "string"}, "floor": {"type": "string"}, "walls": {"type": "string"          }, "width": {"type": "number"}, "sill": {"type": "number"}, "material": {"type": "string"}, "text": {"type": "string"},
}

BUILD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"approach": {"type": "string"}, "steps": {"type": "array", "items": {"type": "object", "properties": _step_props, "required": ["step"]}}},
    "required": ["steps"],
}

REQUIREMENTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"requirements": {"type": "array", "items": {"type": "object", "properties": {
        "kind": {"type": "string", "enum": REQUIREMENT_KINDS}, "text": {"type": "string"}, "supported": {"type": "boolean"},
        "keyword": {"type": "string"}, "count": {"type": "integer"}, "level": {"type": "string"}, "side": {"type": "string"}},
        "required": ["kind", "text"]}}},
    "required": ["requirements"],
}
