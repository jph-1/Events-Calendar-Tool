"""Weekly (or any window) roundup selection: confirmed/attended events in the
next N days that haven't already appeared in a previous roundup, grouped by
category for digest rendering.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from events_tool.store import EventStore


def select_roundup(store: EventStore, days: int = 7, now: datetime | None = None) -> dict[str, list]:
    now = now or datetime.now()
    since_iso = now.isoformat(timespec="seconds")
    until_iso = (now + timedelta(days=days)).isoformat(timespec="seconds")
    rows = store.upcoming_roundup_candidates(since_iso, until_iso)

    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        grouped[row["category"]].append(row)
    return dict(grouped)


def mark_included(store: EventStore, grouped: dict[str, list]) -> None:
    ids = [row["id"] for rows in grouped.values() for row in rows]
    store.mark_roundup_included(ids)
