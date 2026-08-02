"""Fingerprinting so the same real-world event, seen via two sources (or the
same source twice), lands as one row instead of a duplicate.

The fingerprint deliberately ignores punctuation/case/whitespace noise and
collapses the timestamp to a date+hour granularity, since the same event
often shows slightly different minute-level times or trailing venue text
across a newsletter blurb vs. an RSS feed vs. an iCal entry.
"""
from __future__ import annotations

import hashlib
import re

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]")


def _normalize_text(value: str) -> str:
    value = value.lower().strip()
    value = _NON_ALNUM_RE.sub(" ", value)
    value = _WHITESPACE_RE.sub(" ", value).strip()
    return value


def _normalize_dt(start_dt: str) -> str:
    """Collapse an ISO datetime to date+hour, e.g. '2026-08-15T19:32:00' -> '2026-08-15T19'."""
    if not start_dt:
        return ""
    # Handle both 'YYYY-MM-DDTHH:MM:SS' and 'YYYY-MM-DD' forms.
    date_part = start_dt[:13] if len(start_dt) >= 13 else start_dt[:10]
    return date_part


def fingerprint(title: str, start_dt: str, location_name: str = "") -> str:
    key = "|".join(
        [
            _normalize_text(title),
            _normalize_dt(start_dt),
            _normalize_text(location_name),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
