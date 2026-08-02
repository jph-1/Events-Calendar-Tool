"""Dataclasses shared across config, storage, ingestion, and query modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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
    type: str  # "rss" | "ical" | "manual" | "newsletter"
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
    category: str
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
    created_at: str
    updated_at: str


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
