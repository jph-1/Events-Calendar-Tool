"""Repeatable "go find real events for me" flow — the discover-prompt /
discover-import pair.

The tool itself has no runtime web-search or LLM capability (same
constraint as newsletter ingestion), so this follows the same two-step
pattern: `discover-prompt` renders a research brief — the user's saved
places plus their active interests, with a strict output schema — for any
LLM with live web search (Claude, run inside an agent session, or pasted
into any chat) to execute; `discover-import` imports its structured JSON
reply.

This source type carries more fabrication risk than newsletter ingestion
(the LLM is searching the open web, not reading text the user chose and
handed over), so it's held to a stricter contract than the newsletter
path: every event MUST include a real source URL or it's dropped with a
warning, and it always lands as a review candidate — there is no
auto-confirm option here, unlike `ingest-text`.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from events_tool.models import CATEGORIES, Interest, RawEventCandidate

DISCOVERY_PROMPT_TEMPLATE = """\
I want you to research real, currently-scheduled events in {city}, {state} over \
the next {days} days (from {today}), for a personal events calendar tool.

Use live web search. Only include an event if you found a concrete date, \
time, and a specific source URL (the venue's own site, a ticketing page, or \
similar) confirming that date. Never infer a date from a recurring pattern \
("runs every Tuesday") unless you found that exact upcoming occurrence \
stated directly on a page. If you can't confirm something with a real \
source link, leave it out rather than guess.

Check these known places for scheduled events — skip ones that clearly \
wouldn't host events (parks, retail stores, nurseries) unless you have a \
specific reason to check them; focus on venues that plausibly run \
programming: music/comedy venues, galleries, theaters, museums, \
makerspaces, bars/clubs with events, gardens with programming, etc.:

{places_lines}

Also run general/organic searches in {city} for these interest areas, not \
tied to any specific venue above. For these, prioritize checking Meetup.com \
and Eventbrite.com group/event listing pages first — they usually give a \
specific dated occurrence (or an explicit list of dates, e.g. "08/05, \
08/12, 08/19" — using one of those listed dates is fine, that's a stated \
date, not an inferred one). Generic "best salsa nights in {city}" blog or \
listicle pages are usually too vague to confirm a specific date from and \
should be a last resort:

{interest_lines}

For each event you find, return a JSON array where each item has exactly \
these fields:
  "title": string
  "description": string (1-2 sentences, can be empty)
  "start_dt": string, ISO 8601 "YYYY-MM-DDTHH:MM:SS"
  "end_dt": string or null
  "location_name": string (venue name)
  "address": string (can be empty)
  "neighborhood": string (can be empty)
  "url": string — REQUIRED. Must be a real, specific source URL you found;
    entries without one will be discarded.
  "category": string — one of: {categories}

Respond with ONLY the JSON array, no surrounding prose. If you find \
nothing you can confirm with a source, return an empty array [].
"""


def build_discovery_prompt(
    interests: list[Interest],
    places: list,
    city: str,
    state: str,
    days: int = 7,
    today: Optional[date] = None,
) -> str:
    today = today or date.today()
    places_lines = (
        "\n".join(f"  - {p['name']} — {p['address']}" if p["address"] else f"  - {p['name']}" for p in places)
        or "  (none saved yet)"
    )
    interest_lines = (
        "\n".join(f"  - {i.keyword} ({i.category})" for i in interests if i.active) or "  (none active)"
    )
    return DISCOVERY_PROMPT_TEMPLATE.format(
        city=city,
        state=state,
        days=days,
        today=today.isoformat(),
        places_lines=places_lines,
        interest_lines=interest_lines,
        categories=", ".join(CATEGORIES),
    )


def parse_event_item(
    item: dict, source_name: str, item_label: str
) -> tuple[Optional[tuple[RawEventCandidate, str]], Optional[str]]:
    """Shared validation for one LLM-reported event object, used by both
    discover-import and ask-import. Returns ((candidate, category), warning)
    — candidate is None if the item was dropped, in which case warning
    explains why. A warning can also accompany a non-None result (e.g. an
    unrecognized category, downgraded to 'other' rather than dropped)."""
    title = (item.get("title") or "").strip()
    start_dt = (item.get("start_dt") or "").strip()
    url = (item.get("url") or "").strip()

    if not title or not start_dt:
        return None, f"skipped {item_label}: missing title or start_dt"
    if not url:
        return None, f"skipped '{title}': no source url provided (required)"

    category = (item.get("category") or "").strip() or "other"
    warning = None
    if category not in CATEGORIES:
        warning = f"'{title}': category '{category}' not recognized, using 'other'"
        category = "other"

    candidate = RawEventCandidate(
        title=title,
        description=item.get("description", "") or "",
        start_dt=start_dt,
        end_dt=item.get("end_dt"),
        location_name=item.get("location_name", "") or "",
        address=item.get("address", "") or "",
        neighborhood=item.get("neighborhood", "") or "",
        url=url,
        source_name=source_name,
        source_type="assistant-research",
    )
    return (candidate, category), warning


def parse_discovery_response(
    json_text: str, source_name: str = "discover"
) -> tuple[list[tuple[RawEventCandidate, str]], list[str]]:
    """Returns (list of (candidate, category) pairs, warnings). Entries
    missing a title, start_dt, or url are dropped with a warning rather
    than silently guessing a value for them."""
    data = json.loads(json_text)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array of event objects")

    results: list[tuple[RawEventCandidate, str]] = []
    warnings: list[str] = []

    for i, item in enumerate(data):
        result, warning = parse_event_item(item, source_name, f"item {i}")
        if warning:
            warnings.append(warning)
        if result:
            results.append(result)

    return results, warnings
