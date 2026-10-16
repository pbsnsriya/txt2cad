"""The Design: what the LLM builds. Semantic and coarse; geometry is derived from it (see derive.py).

Coordinates are metres, x east, y north. A room's rect is [x, y, width, depth] with (x, y) the south-west corner.
Rect edges are WALL CENTRELINES: walls are centred on them, so two rooms that share an edge share one partition.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Side = Literal["N", "S", "E", "W"]
RoomKind = Literal[
    "living", "kitchen", "dining", "office", "bedroom", "bathroom", "hall", "garage", "utility", "storage",
    "reception", "meeting", "classroom", "retail", "workshop", "other",
]
DoorKind = Literal["single", "double", "garage", "opening"]      # "opening" is an archway: the wall is open, there is no leaf
WindowKind = Literal["standard", "large", "small"]

LEVEL_MIN_HEIGHT, LEVEL_MAX_HEIGHT = 2.2, 12.0
MAX_LEVELS = 40
MIN_ROOM_SIDE = 1.0


class Level(BaseModel):
    id: str
    name: str = ""
    height: float = Field(3.0, ge=LEVEL_MIN_HEIGHT, le=LEVEL_MAX_HEIGHT)


class Room(BaseModel):
    id: str
    name: str
    level: str
    kind: RoomKind = "other"
    rect: tuple[float, float, float, float]
    roofed: bool = True
    floor: str | None = None      # finish of the floor: a name from the palette or #rrggbb
    walls: str | None = None      # paint of the inside of the walls

    @field_validator("rect")
    @classmethod
    def _rect_positive(cls, v: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        if v[2] < MIN_ROOM_SIDE or v[3] < MIN_ROOM_SIDE:
            raise ValueError(f"room sides must be at least {MIN_ROOM_SIDE} m (got {v[2]} x {v[3]})")
        return v


class Furniture(BaseModel):
    """A piece placed in a room. (x, y) is the centre of its footprint in plan metres; `rot` turns it counter-clockwise, and at 0 its back is to the south."""
    id: str
    room: str
    kind: str
    x: float
    y: float
    w: float = Field(gt=0.05, le=8.0)          # across the piece
    d: float = Field(gt=0.05, le=8.0)          # from its back to its front
    h: float = Field(gt=0.05, le=4.0)
    rot: Literal[0, 90, 180, 270] = 0
    colour: str | None = None                  # a name from the palettes or #rrggbb; None keeps the catalogue colour


class Door(BaseModel):
    id: str
    room: str
    to: str = "outside"          # another room id, or "outside"
    side: Side | None = None     # required for "outside" when the room has several exterior sides
    at: float = Field(0.5, ge=0.0, le=1.0)
    kind: DoorKind = "single"
    width: float = Field(0.9, ge=0.6, le=12.0)
    height: float = Field(2.1, ge=1.8, le=4.0)


class Window(BaseModel):
    id: str
    room: str
    side: Side
    at: float = Field(0.5, ge=0.0, le=1.0)
    kind: WindowKind = "standard"
    width: float = Field(1.2, ge=0.4, le=6.0)
    height: float = Field(1.2, ge=0.4, le=3.0)
    sill: float = Field(0.9, ge=0.0, le=2.0)


class Stair(BaseModel):
    """A straight flight along one wall of a room, rising to the next level (or `to_level`)."""
    id: str
    room: str
    side: Side
    to_level: str | None = None
    width: float = Field(1.0, ge=0.8, le=2.5)


class Design(BaseModel):
    name: str = "Untitled building"
    description: str = ""
    levels: list[Level] = Field(default_factory=list)
    rooms: list[Room] = Field(default_factory=list)
    doors: list[Door] = Field(default_factory=list)
    windows: list[Window] = Field(default_factory=list)
    stairs: list[Stair] = Field(default_factory=list)
    furniture: list[Furniture] = Field(default_factory=list)
    roof: Literal["flat", "gable", "hip", "shed"] = "flat"
    roof_pitch: float = Field(30.0, ge=5.0, le=60.0)
    roof_high_side: Side | None = None      # shed roofs: the side that is high
    wall_material: Literal["masonry", "concrete", "timber", "plaster"] = "masonry"
    notes: list[str] = Field(default_factory=list)

    def level(self, level_id: str) -> Level | None:
        return next((lv for lv in self.levels if lv.id == level_id), None)

    def room(self, room_id: str) -> Room | None:
        return next((r for r in self.rooms if r.id == room_id), None)

    def storeys(self) -> int:
        return len(self.levels)

    def elevation(self, level_id: str) -> float:
        """Floor level of a storey: the sum of the heights below it."""
        z = 0.0
        for lv in self.levels:
            if lv.id == level_id:
                return z
            z += lv.height
        raise KeyError(level_id)
