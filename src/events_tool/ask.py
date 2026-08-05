"""The "ask a specific question" flow — `events ask` / `events ask-import`.

Distinct from discover-prompt/discover-import (which sweeps saved places +
active interests broadly): `ask` answers one specific question ("find a
chess club in houston") against an *explicit* date range the caller
chooses (today / this week / 30 days / 90 days / a custom range) — never a
range inferred from the question's wording. That range is a real filter:
if research turns up something outside it, that's reported as a distinct
"next occurrence" suggestion rather than silently included or silently
dropped, so a query like "Formula 1 watch party" with no race this week
can still surface "the next one is Aug 23 — add it?" instead of a dead end.

Same no-runtime-search-capability constraint as discover and newsletter
ingestion: `ask` only ever checks the local database and, if empty, emits
a prompt for a web-search-capable LLM to fill in; `ask-import` reads that
reply back in. Matches land as ordinary review candidates. Suggestions
(found outside the requested range) are reported but NOT auto-inserted —
they need an explicit follow-up (--add-suggested) to land on the
calendar at all, since they're answering a different question than the
one asked.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from events_tool.discovery import parse_event_item
from events_tool.models import CATEGORIES, RawEventCandidate

RANGE_CHOICES = ("today", "week", "30d", "90d", "custom")

_RANGE_LABELS = {
    "today": "today",
    "week": "the next 7 days",
    "30d": "the next 30 days",
    "90d": "the next 90 days",
}

ASK_PROMPT_TEMPLATE = """\
I want to know whether this specific thing is happening in {city}, {state} \
within {range_label} ({date_from} to {date_to}):

  "{query_text}"

Use live web search. Only report a match if you found a concrete date, \
time, and a specific source URL confirming it falls within that window. \
Prefer a direct single-event page (an Eventbrite/Meetup event permalink, a \
venue's own calendar entry) over a generic aggregator or blog page.

If you find NOTHING within that window, try to confirm the next real \
upcoming occurrence of the same thing even if it falls outside the \
window, and report that separately as a suggestion — with its own \
confirmed date and source URL. Do not invent a next occurrence; only \
report one you can actually source. If you can't confirm one either, \
leave the suggestions list empty rather than guess.

Return a JSON object with exactly these two fields:
{{
  "matches": [ <event objects for anything within the window> ],
  "next_occurrence_suggestions": [ <event objects for anything found outside the window> ]
}}

Each event object needs exactly these fields:
  "title": string
  "description": string (1-2 sentences, can be empty)
  "start_dt": string, ISO 8601 "YYYY-MM-DDTHH:MM:SS"
  "end_dt": string or null
  "location_name": string
  "address": string (can be empty)
  "neighborhood": string (can be empty)
  "url": string — REQUIRED. Must be a real, specific source URL you found;
    entries without one will be discarded.
  "category": string — one of: {categories}
  "note": string — for next_occurrence_suggestions ONLY: briefly explain
    it's outside the requested window (e.g. "next race is Aug 23, outside
    your 7-day window").

Respond with ONLY the JSON object, no surrounding prose. If you find \
nothing at all, return {{"matches": [], "next_occurrence_suggestions": []}}.
"""


def resolve_range(
    range_choice: str,
    now: Optional[datetime] = None,
    custom_from: Optional[str] = None,
    custom_to: Optional[str] = None,
) -> tuple[datetime, datetime, str]:
    """Returns (date_from, date_to, human-readable range_label)."""
    now = now or datetime.now()

    if range_choice == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
        return start, end, _RANGE_LABELS["today"]

    if range_choice in ("week", "30d", "90d"):
        days = {"week": 7, "30d": 30, "90d": 90}[range_choice]
        return now, now + timedelta(days=days), _RANGE_LABELS[range_choice]

    if range_choice == "custom":
        if not custom_from or not custom_to:
            raise ValueError("custom range requires both custom_from and custom_to")
        start = datetime.fromisoformat(custom_from)
        end = datetime.fromisoformat(custom_to)
        return start, end, f"{custom_from} to {custom_to}"

    raise ValueError(f"unknown range choice: {range_choice}")


def build_ask_prompt(
    query_text: str,
    city: str,
    state: str,
    date_from: datetime,
    date_to: datetime,
    range_label: str,
) -> str:
    return ASK_PROMPT_TEMPLATE.format(
        city=city,
        state=state,
        query_text=query_text,
        date_from=date_from.isoformat(timespec="seconds"),
        date_to=date_to.isoformat(timespec="seconds"),
        range_label=range_label,
        categories=", ".join(CATEGORIES),
    )


def parse_ask_response(
    json_text: str, source_name: str = "ask"
) -> tuple[list[tuple[RawEventCandidate, str]], list[tuple[RawEventCandidate, str, str]], list[str]]:
    """Returns (matches, suggestions, warnings).
    matches: list of (candidate, category) within the requested range.
    suggestions: list of (candidate, category, note) found outside it.
    """
    data = json.loads(json_text)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object with 'matches' and 'next_occurrence_suggestions'")

    warnings: list[str] = []

    matches: list[tuple[RawEventCandidate, str]] = []
    for i, item in enumerate(data.get("matches", []) or []):
        result, warning = parse_event_item(item, source_name, f"match {i}")
        if warning:
            warnings.append(warning)
        if result:
            matches.append(result)

    suggestions: list[tuple[RawEventCandidate, str, str]] = []
    for i, item in enumerate(data.get("next_occurrence_suggestions", []) or []):
        result, warning = parse_event_item(item, source_name, f"suggestion {i}")
        if warning:
            warnings.append(warning)
        if result:
            candidate, category = result
            note = (item.get("note") or "outside the requested range").strip()
            suggestions.append((candidate, category, note))

    return matches, suggestions, warnings
