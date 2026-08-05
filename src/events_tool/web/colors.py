"""Category color mapping, shared with templates/calendar_prototype.html's
JS version (kept in sync by hand — same hue values) so the Phase 1
artifact and the Phase 2 app read as the same product."""
from __future__ import annotations

CATEGORY_HUES = {
    "art": 288, "maker": 205, "music": 250, "film": 222, "books": 95,
    "gardening": 135, "fitness": 355, "dance": 320, "comedy": 60,
    "sports_games": 185, "natural_building": 28, "networking": 265, "other": None,
}


def cat_color(category: str) -> dict:
    hue = CATEGORY_HUES.get(category)
    if hue is None:
        return {"text": "var(--mist)", "bg": "var(--paper)"}
    return {
        "text": f"hsl({hue}, var(--chip-s), var(--chip-l))",
        "bg": f"hsl({hue}, var(--chip-s), var(--chip-bg-l))",
    }
