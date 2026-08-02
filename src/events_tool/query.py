"""Ad-hoc query parsing for things like:

    events query "salsa dancing tonight"
    events query "gardening workshop" --near "no limit"
    events query "art exhibitions" --near Montrose

This is a lightweight phrase parser, not a general NLP engine: it pulls out
a coarse date range from a handful of common phrases ("tonight", "today",
"this weekend", "this week", "tomorrow") and treats the remaining words as
keyword/category search terms, matched against the interests list to find
the best category and against titles/descriptions as a keyword fallback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from events_tool.models import Interest

_DATE_PHRASES = {
    "tonight": lambda now: (now.replace(hour=0, minute=0, second=0, microsecond=0), now.replace(hour=23, minute=59, second=59, microsecond=0)),
    "today": lambda now: (now.replace(hour=0, minute=0, second=0, microsecond=0), now.replace(hour=23, minute=59, second=59, microsecond=0)),
    "tomorrow": lambda now: (
        (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
        (now + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0),
    ),
    "this week": lambda now: (
        now.replace(hour=0, minute=0, second=0, microsecond=0),
        (now + timedelta(days=(6 - now.weekday()))).replace(hour=23, minute=59, second=59, microsecond=0),
    ),
    "this weekend": lambda now: (
        (now + timedelta(days=max(0, 5 - now.weekday()))).replace(hour=0, minute=0, second=0, microsecond=0),
        (now + timedelta(days=max(0, 6 - now.weekday()))).replace(hour=23, minute=59, second=59, microsecond=0),
    ),
}

_NEAR_UNLIMITED_PHRASES = {"no limit", "no limits", "no distance limit", "any distance", "anywhere"}


@dataclass
class ParsedQuery:
    raw_text: str
    date_from: Optional[str]
    date_to: Optional[str]
    near: Optional[str]
    near_unlimited: bool
    category: Optional[str]
    keywords: list[str]


def _extract_date_range(text: str, now: datetime) -> tuple[Optional[str], Optional[str], str]:
    lowered = text.lower()
    for phrase, fn in sorted(_DATE_PHRASES.items(), key=lambda kv: -len(kv[0])):
        if phrase in lowered:
            start, end = fn(now)
            remaining = lowered.replace(phrase, "").strip()
            return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"), remaining
    return None, None, lowered


def _best_category(text: str, interests: list[Interest]) -> Optional[str]:
    best_category = None
    best_score = 0.0
    scores: dict[str, float] = {}
    for interest in interests:
        if interest.active and interest.keyword.lower() in text:
            scores[interest.category] = scores.get(interest.category, 0.0) + interest.weight
    if scores:
        best_category = max(scores.items(), key=lambda kv: kv[1])[0]
        best_score = scores[best_category]
    return best_category if best_score > 0 else None


def parse_query(text: str, interests: list[Interest], near: Optional[str] = None, now: Optional[datetime] = None) -> ParsedQuery:
    now = now or datetime.now()
    date_from, date_to, remaining = _extract_date_range(text, now)
    category = _best_category(text.lower(), interests)

    near_unlimited = False
    if near and near.strip().lower() in _NEAR_UNLIMITED_PHRASES:
        near_unlimited = True
        near = None

    # Leftover words (stopwords stripped) become keyword fallback search terms.
    stopwords = {"i", "want", "to", "a", "an", "the", "any", "new", "near", "at", "in", "for"}
    words = [w for w in re.findall(r"[a-z]+", remaining) if w not in stopwords]

    return ParsedQuery(
        raw_text=text,
        date_from=date_from,
        date_to=date_to,
        near=near,
        near_unlimited=near_unlimited,
        category=category,
        keywords=words,
    )
