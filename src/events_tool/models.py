"""Dataclasses shared across config, storage, ingestion, and query modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# The full category taxonomy the product targets. Interests in profile.json
# should map to one of these; "other" is the catch-all for anything that
# doesn't fit (never silently dropped).
CATEGORIES = [
    "art",
    "maker",
    "music",
    "film",
    "books",
    "gardening",
    "fitness",
    "dance",
    "comedy",
    "sports_games",
    "natural_building",
    "networking",
    "other",
]

# How an event's facts were established. Never mixed with user-added
# signals (saved/user_category/user_notes) — this describes the *event
# record's* provenance, used to render honest coverage/trust labels instead
# of presenting every row as equally verified.
VERIFICATIONS = [
    "automated-source",   # fetched live from a working RSS/iCal adapter
    "user-manual",        # typed in directly (add-event / log-attended)
    "user-lead-structured",  # newsletter text, extracted via the LLM-prompt path
    "user-lead-heuristic",   # newsletter text, extracted via the regex fallback
]

VALID_STATUSES = {"candidate", "confirmed", "attended", "rejected"}


@dataclass
class Location:
    city: str
    state: str
    lat: Optional[float] = None
    lon: Optional[float] = None


@dataclass
class Interest:
    keyword: str
    category: str
    weight: float = 1.0
    active: bool = True


@dataclass
class Source:
    name: str
    type: str  # "rss" | "ical" | "manual" | "newsletter" | "lead"
    url: str = ""
    enabled: bool = True
    notes: str = ""


@dataclass
class Profile:
    location: Location
    future_flags: dict
    interests: list[Interest] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)


@dataclass
class RawEventCandidate:
    """What a source adapter produces, before matching/dedup/storage."""

    title: str
    description: str = ""
    start_dt: Optional[str] = None  # ISO 8601 string, e.g. "2026-08-15T19:00:00"
    end_dt: Optional[str] = None
    location_name: str = ""
    address: str = ""
    neighborhood: str = ""
    url: str = ""
    source_name: str = ""
    source_type: str = ""
    external_uid: str = ""


@dataclass
class Event:
    id: Optional[int]
    title: str
    description: str
    source_category: str
    user_category: Optional[str]
    start_dt: str
    end_dt: Optional[str]
    location_name: str
    address: str
    city: str
    state: str
    neighborhood: str
    lat: Optional[float]
    lon: Optional[float]
    url: str
    source_name: str
    source_type: str
    external_uid: str
    dedup_key: str
    status: str  # "candidate" | "confirmed" | "attended" | "rejected"
    verification: str
    saved: bool
    user_notes: str
    created_at: str
    updated_at: str

    @property
    def category(self) -> str:
        """The effective category to display/filter by: a user correction
        takes precedence over the ingested source_category, without ever
        overwriting it."""
        return self.user_category or self.source_category


@dataclass
class IngestionRun:
    id: Optional[int]
    source_name: str
    run_at: str
    items_found: int
    items_added: int
    items_deduped: int
    status: str
    notes: str = ""


@dataclass
class Place:
    id: Optional[int]
    name: str
    address: str
    lat: Optional[float]
    lon: Optional[float]
    tags: str
    list_name: str
    source: str
    imported_at: str
