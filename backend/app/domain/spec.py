"""BuildingSpec: the geometric intermediate representation every output (IFC, DXF, previews) is written from.

Units are metres. Plan coordinates (x, y); z comes from level elevations. Every element has a stable string id.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Point = tuple[float, float]


class WallSpec(BaseModel):
    id: str
    label: str = ""          # human name, e.g. "Kitchen: south wall"; shown in the viewer and used as the IFC name
    level: str
    start: Point
    end: Point
    thickness: float
    height: float
    external: bool
    material: str

    @property
    def length(self) -> float:
        return ((self.end[0] - self.start[0]) ** 2 + (self.end[1] - self.start[1]) ** 2) ** 0.5


class SlabSpec(BaseModel):
    id: str
    label: str = ""
    level: str
    outline: list[Point]
    thickness: float
    z_top: float
    holes: list[list[Point]] = Field(default_factory=list)   # stairwell openings


class RoofSpec(BaseModel):
    id: str
    label: str = ""
    level: str
    outline: list[Point]
    thickness: float
    z_bottom: float
    kind: Literal["flat", "gable", "hip", "shed"] = "flat"
    pitch: float = 0.0                       # degrees, the pitch actually used
    ridge_along: Literal["x", "y"] = "x"     # gable and hip: the direction the ridge runs
    high_side: Literal["N", "S", "E", "W"] | None = None
    note: str = ""                           # why a roof that was asked to be pitched is flat


class OpeningSpec(BaseModel):
    id: str
    label: str = ""
    kind: Literal["door", "window"]
    host: str                # wall id
    offset: float            # distance of the opening centre along the wall from its start
    width: float
    height: float
    sill: float = 0.0
    style: str = "single"
    level: str


class StairSpec(BaseModel):
    id: str
    label: str = ""
    level: str                 # the level it starts on
    to_level: str
    outline: list[Point]       # plan footprint (rectangle)
    start: Point               # centre of the bottom edge of the flight
    direction: Point           # unit vector in plan, direction of climbing
    width: float
    risers: int
    riser_height: float
    going: float
    length: float              # plan length of the flight
    z0: float                  # floor level it starts from


class SpaceSpec(BaseModel):
    id: str
    name: str
    level: str
    outline: list[Point]
    area: float
    kind: str = "other"


class LevelSpec(BaseModel):
    id: str
    name: str
    elevation: float
    height: float


class BuildingSpec(BaseModel):
    name: str
    levels: list[LevelSpec] = Field(default_factory=list)
    walls: list[WallSpec] = Field(default_factory=list)
    slabs: list[SlabSpec] = Field(default_factory=list)
    roofs: list[RoofSpec] = Field(default_factory=list)
    openings: list[OpeningSpec] = Field(default_factory=list)
    stairs: list[StairSpec] = Field(default_factory=list)
    spaces: list[SpaceSpec] = Field(default_factory=list)

    def level_elevation(self, level_id: str) -> float:
        return next(lv.elevation for lv in self.levels if lv.id == level_id)

    def wall(self, wall_id: str) -> WallSpec:
        return next(w for w in self.walls if w.id == wall_id)

    def element_count(self) -> int:
        return len(self.walls) + len(self.slabs) + len(self.roofs) + len(self.openings) + len(self.spaces) + len(self.stairs)
