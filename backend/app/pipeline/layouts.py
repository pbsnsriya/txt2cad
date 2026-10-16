"""Layout options: the same brief built again, each time pushed towards a different plan, so the options differ in more than room names."""

from __future__ import annotations

LAYOUT_OPTIONS: dict[int, tuple[str, str]] = {
    1: ("Compact", "pack the rooms into two tidy rows around a central hall, with as little corridor as possible"),
    2: ("Open plan", "put one large open living, kitchen and dining space along the south side and the bedrooms and bathrooms along the north side behind a hall"),
    3: ("Spine", "make a long, narrow plan: one hall running along the middle as a spine, with rooms on both sides of it"),
}
MAX_OPTION = max(LAYOUT_OPTIONS)


def hint(option: int) -> str:
    label, idea = LAYOUT_OPTIONS[option]
    return (f"LAYOUT OPTION {option} OF {MAX_OPTION} ({label}): design this building from scratch and make the plan clearly different from a conventional one. "
            f"Idea: {idea}. Keep every requirement. Start your \"approach\" with \"Difference:\" and one short sentence saying how this layout differs.")


def difference(approach: str) -> str:
    """The one-line difference from the model's approach: its first sentence without the 'Difference:' lead-in."""
    text = approach.strip()
    if text.lower().startswith("difference:"):
        text = text[len("difference:"):].strip()
    first = text.split(". ")[0].strip().rstrip(".")
    return (first[:160] + ".") if first else ""
