"""Next requests worth trying, taken from the building on screen, so people learn what the tool can change by seeing it done.

Every suggestion is something the step vocabulary can really do, worded the way a person would say it, and names rooms that exist.
"""

from __future__ import annotations

from .design import Design

MIN_COMFORTABLE_BEDROOM_M2 = 10.0
SECOND_STOREY_FROM_M2 = 45.0


def _area(room) -> float:
    return room.rect[2] * room.rect[3]


def suggest(design: Design, limit: int = 3) -> list[str]:
    """Up to `limit` follow-up requests, most useful first. Empty when there is nothing built yet."""
    if not design.rooms:
        return []
    out: list[str] = []

    def add(text: str) -> None:
        if text not in out:
            out.append(text)

    rooms = design.rooms
    bedrooms = [r for r in rooms if r.kind == "bedroom"]
    bathrooms = [r for r in rooms if r.kind == "bathroom"]
    ground = [r for r in rooms if r.level == design.levels[0].id] if design.levels else rooms

    if design.roof == "flat":
        add("Give it a gable roof.")
    if not design.furniture and len(rooms) >= 3:
        add("Furnish every room.")
    living_room = next((r for r in rooms if r.kind == "living"), None)
    if living_room is not None and not living_room.floor:
        add(f"Give the {living_room.name} an oak floor.")
    if bedrooms and not any(r.walls for r in bedrooms):
        add("Paint the bedrooms cream.")
    if not any(r.kind == "office" for r in rooms):
        anchor = next((r for r in ground if r.kind == "kitchen"), None) or next((r for r in ground if r.kind == "living"), None)
        if anchor:
            add(f"Add a study next to the {anchor.name}.")
    if len(bedrooms) >= 3 and len(bathrooms) < 2:
        add("Add a second bathroom.")
    small = min(bedrooms, key=_area, default=None)
    if small is not None and _area(small) < MIN_COMFORTABLE_BEDROOM_M2:
        add(f"Make {small.name} bigger.")
    living = next((r for r in rooms if r.kind == "living"), None)
    if living is not None and not any(w.room == living.id and w.kind == "large" for w in design.windows):
        add(f"Add a larger window to the {living.name}.")
    if len(design.levels) == 1 and sum(_area(r) for r in rooms) >= SECOND_STOREY_FROM_M2:
        add("Add a second storey with two bedrooms and a bathroom.")
    if design.roof == "gable":
        add("Change the roof to a hip roof.")
    elif design.roof != "flat":
        add("Give it a gable roof.")
    if design.wall_material == "masonry":
        add("Change the exterior walls to timber.")
    return out[:limit]
