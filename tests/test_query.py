from datetime import datetime

from events_tool.models import Interest
from events_tool.query import parse_query

INTERESTS = [
    Interest(keyword="salsa", category="dance"),
    Interest(keyword="gardening workshop", category="gardening"),
    Interest(keyword="art exhibition", category="art"),
]

NOW = datetime(2026, 8, 15, 14, 0, 0)  # a Saturday


def test_tonight_extracts_today_date_range():
    parsed = parse_query("I want to salsa dance tonight", INTERESTS, now=NOW)
    assert parsed.date_from.startswith("2026-08-15T00:00:00")
    assert parsed.date_to.startswith("2026-08-15T23:59:59")
    assert parsed.category == "dance"


def test_category_matched_from_interest_keyword():
    parsed = parse_query("gardening workshop, no limits to distance", INTERESTS, now=NOW)
    assert parsed.category == "gardening"


def test_near_unlimited_phrase_detected():
    parsed = parse_query("gardening workshop", INTERESTS, near="no limit", now=NOW)
    assert parsed.near_unlimited is True
    assert parsed.near is None


def test_near_area_passed_through():
    parsed = parse_query("any new art exhibitions", INTERESTS, near="Montrose", now=NOW)
    assert parsed.near == "Montrose"
    assert parsed.near_unlimited is False
    assert parsed.category == "art"


def test_tomorrow_extracts_next_day():
    parsed = parse_query("book club tomorrow", INTERESTS, now=NOW)
    assert parsed.date_from.startswith("2026-08-16T00:00:00")
    assert parsed.date_to.startswith("2026-08-16T23:59:59")


def test_no_date_phrase_leaves_range_unset():
    parsed = parse_query("salsa dancing", INTERESTS, now=NOW)
    assert parsed.date_from is None
    assert parsed.date_to is None


def test_unmatched_text_leaves_category_none_and_keeps_keywords():
    parsed = parse_query("underwater basket weaving", INTERESTS, now=NOW)
    assert parsed.category is None
    assert "underwater" in parsed.keywords
