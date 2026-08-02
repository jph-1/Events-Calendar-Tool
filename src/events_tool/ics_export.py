"""Hand-written RFC 5545 (iCalendar) VEVENT writer.

No third-party icalendar library is used — the format is simple enough
(escaping + 75-octet line folding) to implement directly against the spec,
keeping the whole tool dependency-free. Round-trip tested against
ingestion.ics_rss_adapter.parse_ics, which reads back what this writes.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

_FOLD_LIMIT = 75


def _escape_text(value: str) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold_line(line: str) -> str:
    """RFC 5545 section 3.1: lines longer than 75 octets are folded with a
    CRLF followed by a single leading space on the continuation line."""
    if len(line.encode("utf-8")) <= _FOLD_LIMIT:
        return line
    parts = []
    current = ""
    for char in line:
        candidate = current + char
        if len(candidate.encode("utf-8")) > _FOLD_LIMIT:
            parts.append(current)
            current = char
        else:
            current = candidate
    if current:
        parts.append(current)
    return "\r\n ".join(parts)


def _dt_to_ics(value: str) -> str:
    """'2026-08-15T19:00:00' -> '20260815T190000' (floating local time; no
    Z suffix, since we don't track source timezone)."""
    cleaned = value.replace("-", "").replace(":", "")
    if "T" not in cleaned:
        cleaned += "T000000"
    return cleaned


def event_to_vevent(event) -> str:
    """event: a sqlite3.Row or object supporting event['field'] / attribute access
    with title, description, start_dt, end_dt, location_name, url, dedup_key, id."""

    def get(field: str, default: str = "") -> str:
        try:
            value = event[field]
        except (KeyError, IndexError, TypeError):
            value = getattr(event, field, default)
        return value if value is not None else default

    uid = get("dedup_key") or f"event-{get('id')}"
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_stamp}",
        f"DTSTART:{_dt_to_ics(get('start_dt'))}",
    ]
    end_dt = get("end_dt", "")
    if end_dt:
        lines.append(f"DTEND:{_dt_to_ics(end_dt)}")
    lines.append(f"SUMMARY:{_escape_text(get('title'))}")
    description = get("description")
    if description:
        lines.append(f"DESCRIPTION:{_escape_text(description)}")
    location = get("location_name")
    if location:
        lines.append(f"LOCATION:{_escape_text(location)}")
    url = get("url")
    if url:
        lines.append(f"URL:{url}")
    lines.append("END:VEVENT")
    return "\r\n".join(_fold_line(line) for line in lines)


def build_calendar(events: Iterable, calendar_name: str = "Personal Activity Calendar") -> str:
    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//events_tool//personal activity calendar//EN",
        f"X-WR-CALNAME:{_escape_text(calendar_name)}",
        "CALSCALE:GREGORIAN",
    ]
    body = [event_to_vevent(event) for event in events]
    footer = ["END:VCALENDAR"]
    return "\r\n".join(header + body + footer) + "\r\n"
