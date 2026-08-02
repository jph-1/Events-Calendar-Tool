"""A real, working ingestion adapter for iCal (.ics) and RSS/Atom feeds.

No API key is required for either format: many Houston venues, galleries,
and makerspaces run the WordPress "The Events Calendar" plugin, which
publishes a free iCal feed at ``<site>/events/?ical=1``, and RSS/Atom is a
near-universal blog/announcement format. This is the one concretely
implemented no-auth source adapter; Eventbrite/Meetup/social-media adapters
that need API keys are stubbed separately in future_adapters.py.
"""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

from events_tool.ingestion.base import SourceAdapter
from events_tool.models import RawEventCandidate

_DT_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2}))?Z?$")


def _parse_ics_datetime(value: str) -> Optional[str]:
    """Convert an ICS DTSTART/DTEND value ('20260815T190000Z' or '20260815')
    into an ISO 8601 string ('2026-08-15T19:00:00'). Returns None if unparseable."""
    value = value.strip()
    match = _DT_RE.match(value)
    if not match:
        return None
    year, month, day, hour, minute, second = match.groups()
    if hour is None:
        return f"{year}-{month}-{day}T00:00:00"
    return f"{year}-{month}-{day}T{hour}:{minute}:{second}"


def _unfold_ics_lines(text: str) -> list[str]:
    """RFC 5545 line folding: continuation lines start with a space or tab."""
    raw_lines = text.replace("\r\n", "\n").split("\n")
    unfolded: list[str] = []
    for line in raw_lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        elif line.strip():
            unfolded.append(line)
    return unfolded


def _unescape_ics_text(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def parse_ics(text: str, source_name: str = "") -> list[RawEventCandidate]:
    lines = _unfold_ics_lines(text)
    candidates: list[RawEventCandidate] = []
    current: dict = {}
    in_event = False

    for line in lines:
        if line.strip() == "BEGIN:VEVENT":
            in_event = True
            current = {}
            continue
        if line.strip() == "END:VEVENT":
            in_event = False
            if current.get("SUMMARY"):
                candidates.append(
                    RawEventCandidate(
                        title=current.get("SUMMARY", ""),
                        description=current.get("DESCRIPTION", ""),
                        start_dt=current.get("DTSTART"),
                        end_dt=current.get("DTEND"),
                        location_name=current.get("LOCATION", ""),
                        url=current.get("URL", ""),
                        source_name=source_name,
                        source_type="ical",
                        external_uid=current.get("UID", ""),
                    )
                )
            continue
        if not in_event or ":" not in line:
            continue

        key_part, _, value = line.partition(":")
        key = key_part.split(";")[0].strip().upper()
        value = value.strip()

        if key in ("DTSTART", "DTEND"):
            parsed = _parse_ics_datetime(value)
            if parsed:
                current[key] = parsed
        elif key in ("SUMMARY", "DESCRIPTION", "LOCATION", "URL", "UID"):
            current[key] = _unescape_ics_text(value)

    return candidates


def _rss_item_to_candidate(item: ET.Element, source_name: str) -> Optional[RawEventCandidate]:
    def text_of(tag: str) -> str:
        el = item.find(tag)
        return (el.text or "").strip() if el is not None and el.text else ""

    title = text_of("title")
    if not title:
        return None
    description = text_of("description")
    link = text_of("link")
    guid = text_of("guid") or link
    pub_date = text_of("pubDate")

    start_dt = None
    if pub_date:
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
            try:
                start_dt = datetime.strptime(pub_date, fmt).replace(tzinfo=None).isoformat(timespec="seconds")
                break
            except ValueError:
                continue

    return RawEventCandidate(
        title=title,
        description=description,
        start_dt=start_dt,
        url=link,
        source_name=source_name,
        source_type="rss",
        external_uid=guid,
    )


def parse_rss(text: str, source_name: str = "") -> list[RawEventCandidate]:
    root = ET.fromstring(text)
    # RSS 2.0: rss/channel/item. Atom: feed/entry (namespaced).
    items = root.findall("./channel/item")
    if items:
        candidates = [_rss_item_to_candidate(item, source_name) for item in items]
        return [c for c in candidates if c is not None]

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    candidates = []
    for entry in entries:
        title_el = entry.find("atom:title", ns)
        title = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
        if not title:
            continue
        link_el = entry.find("atom:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        summary_el = entry.find("atom:summary", ns)
        description = (summary_el.text or "").strip() if summary_el is not None and summary_el.text else ""
        updated_el = entry.find("atom:updated", ns) or entry.find("atom:published", ns)
        start_dt = None
        if updated_el is not None and updated_el.text:
            try:
                start_dt = datetime.fromisoformat(updated_el.text.strip().replace("Z", "+00:00")).replace(
                    tzinfo=None
                ).isoformat(timespec="seconds")
            except ValueError:
                pass
        id_el = entry.find("atom:id", ns)
        guid = (id_el.text or link).strip() if id_el is not None and id_el.text else link
        candidates.append(
            RawEventCandidate(
                title=title,
                description=description,
                start_dt=start_dt,
                url=link,
                source_name=source_name,
                source_type="rss",
                external_uid=guid,
            )
        )
    return candidates


def parse_feed(text: str, source_name: str = "") -> list[RawEventCandidate]:
    """Detect ICS vs RSS/Atom by content and dispatch to the right parser."""
    stripped = text.strip()
    if "BEGIN:VCALENDAR" in stripped or "BEGIN:VEVENT" in stripped:
        return parse_ics(stripped, source_name)
    return parse_rss(stripped, source_name)


class IcsRssAdapter(SourceAdapter):
    def __init__(self, name: str, url: str, timeout: int = 15):
        self.name = name
        self.url = url
        self.timeout = timeout

    def _fetch_raw(self) -> str:
        with urllib.request.urlopen(self.url, timeout=self.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")

    def fetch(self) -> list[RawEventCandidate]:
        text = self._fetch_raw()
        return parse_feed(text, source_name=self.name)
