"""SourceAdapter: the interface every ingestion source implements.

Adding a new real source later (Eventbrite, Meetup, a specific venue's own
scraper) means writing one class with a fetch() method — the CLI, matching,
dedup, and storage pipeline is unchanged.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from events_tool.models import RawEventCandidate


class SourceAdapter(ABC):
    name: str

    @abstractmethod
    def fetch(self) -> list[RawEventCandidate]:
        """Return raw event candidates from this source. Must not raise on
        empty results — return [] instead."""
        raise NotImplementedError
