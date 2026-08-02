"""Turning pasted newsletter text into event candidates.

The tool itself has no runtime LLM API key, so newsletter ingestion offers
two paths:

1. LLM-assisted (recommended, higher quality): `build_extraction_prompt()`
   renders a filled-in prompt — the user's active interests plus a
   documented JSON schema — that the user pastes into any LLM chat (e.g.
   Claude) themselves. The LLM's structured JSON reply is then imported via
   `parse_structured_response()`, going through the normal matching/dedup/
   storage pipeline like any other source.
2. Heuristic fallback (`heuristic_extract()`): pure regex-based extraction
   of "<title> ... <month day[, year]> ... <time>" patterns, no LLM
   required. Always produces low-confidence 'candidate' rows for review —
   good enough to not miss things entirely when you just want something
   fast, but expected to need human review before confirming.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional

from events_tool.models import Interest, RawEventCandidate

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_DATE_RE = re.compile(
    r"\b(?P<month>[A-Za-z]{3,9})\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{4}))?\b"
)
_TIME_RE = re.compile(r"\b(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>[ap]\.?m\.?)\b", re.IGNORECASE)

PROMPT_TEMPLATE = """\
I'm going to paste a newsletter below. Extract every distinct event it \
mentions that matches ANY of these interests (keyword -> category):

{interest_lines}

For each matching event, return a JSON array where each item has exactly \
these fields:
  "title": string
  "description": string (1-2 sentences, can be empty)
  "start_dt": string, ISO 8601 "YYYY-MM-DDTHH:MM:SS" (best guess if the \
newsletter is vague about time; use "T00:00:00" if no time is given)
  "end_dt": string or null
  "location_name": string (venue/organization name, can be empty)
  "address": string (can be empty)
  "neighborhood": string (can be empty)
  "url": string (event/ticket link if present, can be empty)

Respond with ONLY the JSON array, no surrounding prose.

--- NEWSLETTER TEXT BELOW ---
{newsletter_text}
"""


def build_extraction_prompt(newsletter_text: str, interests: list[Interest]) -> str:
    interest_lines = "\n".join(
        f"  - {i.keyword} -> {i.category}" for i in interests if i.active
    )
    return PROMPT_TEMPLATE.format(interest_lines=interest_lines, newsletter_text=newsletter_text.strip())


def parse_structured_response(json_text: str, source_name: str = "newsletter") -> list[RawEventCandidate]:
    data = json.loads(json_text)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array of event objects")
    candidates = []
    for item in data:
        candidates.append(
            RawEventCandidate(
                title=item.get("title", "").strip(),
                description=item.get("description", ""),
                start_dt=item.get("start_dt"),
                end_dt=item.get("end_dt"),
                location_name=item.get("location_name", ""),
                address=item.get("address", ""),
                neighborhood=item.get("neighborhood", ""),
                url=item.get("url", ""),
                source_name=source_name,
                source_type="newsletter",
                external_uid="",
            )
        )
    return [c for c in candidates if c.title]


def _resolve_year(month: int, day: int, explicit_year: Optional[str], reference: date) -> int:
    if explicit_year:
        return int(explicit_year)
    year = reference.year
    try:
        candidate_date = date(year, month, day)
    except ValueError:
        return year
    if candidate_date < reference:
        return year + 1
    return year


def heuristic_extract(
    text: str, source_name: str = "newsletter-heuristic", reference_date: Optional[date] = None
) -> list[RawEventCandidate]:
    """Regex-only fallback: find blocks of text containing both a date and a
    time, and treat the text before the date as the title. No API/LLM
    required; lower precision than the LLM-assisted path."""
    reference = reference_date or date.today()
    candidates: list[RawEventCandidate] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        date_match = _DATE_RE.search(line)
        if not date_match:
            continue
        month_word = date_match.group("month").lower()
        month = _MONTHS.get(month_word)
        if not month:
            continue
        day = int(date_match.group("day"))
        if day < 1 or day > 31:
            continue
        year = _resolve_year(month, day, date_match.group("year"), reference)

        time_match = _TIME_RE.search(line)
        hour, minute = 0, 0
        if time_match:
            hour = int(time_match.group("hour")) % 12
            minute = int(time_match.group("minute") or 0)
            if time_match.group("ampm").lower().startswith("p"):
                hour += 12

        try:
            start_dt = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00"
        except ValueError:
            continue

        title = line[: date_match.start()].strip(" -:–—")
        if not title:
            title = line.strip()

        candidates.append(
            RawEventCandidate(
                title=title,
                description=line,
                start_dt=start_dt,
                source_name=source_name,
                source_type="newsletter",
                external_uid="",
            )
        )

    return candidates
