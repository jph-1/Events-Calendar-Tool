"""Ad-hoc query parsing for things like:

    events query "salsa dancing tonight"
    events query "gardening workshop" --near "no limit"
    events query "art exhibitions" --near Montrose
    events query "live jazz music for August 1st"

This is a lightweight phrase parser, not a general NLP engine: it pulls out
a coarse date range from a handful of common phrases ("tonight", "today",
"this weekend", "this week", "tomorrow"), falls back to parsing an explicit
month+day ("August 1st", "Aug 1", "8/1") when no phrase matches, and treats
the remaining words as keyword/category search terms, matched against the
interests list to find the best category and against titles/descriptions as
a keyword fallback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from events_tool.models import Interest

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_MONTH_DAY_RE = re.compile(
    r"\b(?P<month>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{4}))?\b"
)
_NUMERIC_DATE_RE = re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})(?:/(?P<year>\d{2,4}))?\b")

_DATE_PHRASES = {
    "tonight": lambda now: (now.replace(hour=0, minute=0, second=0, microsecond=0), now.replace(hour=23, minute=59, second=59, microsecond=0)),
    "today": lambda now: (now.replace(hour=0, minute=0, second=0, microsecond=0), now.replace(hour=23, minute=59, second=59, microsecond=0)),
    "tomorrow": lambda now: (
        (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
        (now + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0),
    ),
    "this week": lambda now: (
        now.replace(hour=0, minute=0, second=0, microsecond=0),
        (now + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=0),
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


def _resolve_year(month: int, day: int, explicit_year: Optional[str], reference: datetime) -> int:
    if explicit_year:
        year = int(explicit_year)
        return year + 2000 if year < 100 else year
    year = reference.year
    try:
        candidate = datetime(year, month, day)
    except ValueError:
        return year
    if candidate.date() < reference.date():
        return year + 1
    return year


def _extract_explicit_date(text: str, now: datetime) -> tuple[Optional[str], Optional[str], str]:
    match = _MONTH_DAY_RE.search(text)
    if match:
        month = _MONTHS.get(match.group("month").lower())
        if month:
            day = int(match.group("day"))
            if 1 <= day <= 31:
                year = _resolve_year(month, day, match.group("year"), now)
                try:
                    start = datetime(year, month, day)
                except ValueError:
                    start = None
                if start:
                    end = start.replace(hour=23, minute=59, second=59)
                    remaining = (text[: match.start()] + text[match.end() :]).strip()
                    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"), remaining

    match = _NUMERIC_DATE_RE.search(text)
    if match:
        month, day = int(match.group("month")), int(match.group("day"))
        if 1 <= month <= 12 and 1 <= day <= 31:
            year = _resolve_year(month, day, match.group("year"), now)
            try:
                start = datetime(year, month, day)
            except ValueError:
                start = None
            if start:
                end = start.replace(hour=23, minute=59, second=59)
                remaining = (text[: match.start()] + text[match.end() :]).strip()
                return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"), remaining

    return None, None, text


def _extract_date_range(text: str, now: datetime) -> tuple[Optional[str], Optional[str], str]:
    lowered = text.lower()
    for phrase, fn in sorted(_DATE_PHRASES.items(), key=lambda kv: -len(kv[0])):
        if phrase in lowered:
            start, end = fn(now)
            remaining = lowered.replace(phrase, "").strip()
            return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds"), remaining
    return _extract_explicit_date(lowered, now)


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
