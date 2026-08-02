"""Manual ingestion: events the user types in directly.

Backs two CLI commands: `events add-event` (a candidate you found yourself,
e.g. from a friend or a flyer) and `events log-attended` (an event you
already went to, recorded straight to the 'attended' status for history/
curation purposes rather than as something still to review).
"""
from __future__ import annotations

from events_tool.models import RawEventCandidate


def build_candidate(
    title: str,
    start_dt: str,
    end_dt: str = "",
    description: str = "",
    location_name: str = "",
    address: str = "",
    neighborhood: str = "",
    url: str = "",
) -> RawEventCandidate:
    return RawEventCandidate(
        title=title,
        description=description,
        start_dt=start_dt,
        end_dt=end_dt or None,
        location_name=location_name,
        address=address,
        neighborhood=neighborhood,
        url=url,
        source_name="manual",
        source_type="manual",
        external_uid="",
    )
