"""Roadmap stubs for sources that need paid/authenticated APIs we don't have
keys for yet. Not registered anywhere in the CLI — importing and
instantiating these is a reminder of what each would need, not a working
adapter. Wire one up by giving it real API-call logic in fetch() and adding
a source `type` for it in config.py / cli.py once credentials exist.
"""
from __future__ import annotations

from events_tool.ingestion.base import SourceAdapter
from events_tool.models import RawEventCandidate


class EventbriteAdapter(SourceAdapter):
    """Needs: an Eventbrite API OAuth token (organizer or search API access)."""

    def __init__(self, name: str, api_token: str, location_query: str):
        self.name = name
        self.api_token = api_token
        self.location_query = location_query

    def fetch(self) -> list[RawEventCandidate]:
        raise NotImplementedError("Eventbrite adapter requires an API token; not implemented yet.")


class MeetupAdapter(SourceAdapter):
    """Needs: a Meetup API key (Meetup's GraphQL API requires OAuth as of their v3->GraphQL migration)."""

    def __init__(self, name: str, api_key: str, group_urlnames: list[str]):
        self.name = name
        self.api_key = api_key
        self.group_urlnames = group_urlnames

    def fetch(self) -> list[RawEventCandidate]:
        raise NotImplementedError("Meetup adapter requires an API key; not implemented yet.")


class InstagramFacebookEventsAdapter(SourceAdapter):
    """Needs: Meta Graph API app credentials + page/business verification;
    Instagram/Facebook Events are not exposed via any public no-auth feed."""

    def __init__(self, name: str, access_token: str, page_id: str):
        self.name = name
        self.access_token = access_token
        self.page_id = page_id

    def fetch(self) -> list[RawEventCandidate]:
        raise NotImplementedError("Instagram/Facebook adapter requires Meta Graph API credentials; not implemented yet.")


class TicketmasterAdapter(SourceAdapter):
    """Needs: a Ticketmaster Discovery API consumer key."""

    def __init__(self, name: str, api_key: str, dma_id: str):
        self.name = name
        self.api_key = api_key
        self.dma_id = dma_id

    def fetch(self) -> list[RawEventCandidate]:
        raise NotImplementedError("Ticketmaster adapter requires an API key; not implemented yet.")
