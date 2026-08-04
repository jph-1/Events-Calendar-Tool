import json
from datetime import date

from events_tool.discovery import build_discovery_prompt, parse_discovery_response
from events_tool.models import Interest


def _place(name, address=""):
    return {"name": name, "address": address}


def test_build_discovery_prompt_includes_places_and_interests():
    interests = [Interest(keyword="salsa", category="dance"), Interest(keyword="book club", category="books", active=False)]
    places = [_place("The Continental Club", "3714 Main St, Houston, TX")]
    prompt = build_discovery_prompt(interests, places, "Houston", "TX", days=7, today=date(2026, 8, 4))

    assert "The Continental Club — 3714 Main St, Houston, TX" in prompt
    assert "salsa (dance)" in prompt
    assert "book club" not in prompt  # inactive interest excluded
    assert "Houston, TX" in prompt
    assert "next 7 days" in prompt
    assert "2026-08-04" in prompt
    assert "REQUIRED" in prompt  # url requirement is spelled out


def test_build_discovery_prompt_handles_empty_places_and_interests():
    prompt = build_discovery_prompt([], [], "Austin", "TX")
    assert "none saved yet" in prompt
    assert "none active" in prompt


def test_parse_discovery_response_requires_url():
    data = [
        {"title": "Has URL", "start_dt": "2026-08-07T19:00:00", "url": "https://example.org/a", "category": "comedy"},
        {"title": "No URL", "start_dt": "2026-08-08T19:00:00", "url": "", "category": "comedy"},
    ]
    results, warnings = parse_discovery_response(json.dumps(data))
    assert len(results) == 1
    assert results[0][0].title == "Has URL"
    assert any("No URL" in w for w in warnings)


def test_parse_discovery_response_requires_title_and_start_dt():
    data = [
        {"title": "", "start_dt": "2026-08-07T19:00:00", "url": "https://example.org/a"},
        {"title": "No Date", "start_dt": "", "url": "https://example.org/b"},
    ]
    results, warnings = parse_discovery_response(json.dumps(data))
    assert results == []
    assert len(warnings) == 2


def test_parse_discovery_response_falls_back_unknown_category_to_other():
    data = [{"title": "Mystery Event", "start_dt": "2026-08-07T19:00:00", "url": "https://example.org/a", "category": "not-a-real-category"}]
    results, warnings = parse_discovery_response(json.dumps(data))
    assert results[0][1] == "other"
    assert any("not-a-real-category" in w for w in warnings)


def test_parse_discovery_response_sets_source_type_for_provenance():
    data = [{"title": "Event", "start_dt": "2026-08-07T19:00:00", "url": "https://example.org/a", "category": "music"}]
    results, _ = parse_discovery_response(json.dumps(data), source_name="discover:test")
    candidate, category = results[0]
    assert candidate.source_type == "assistant-research"
    assert candidate.source_name == "discover:test"
    assert category == "music"


def test_parse_discovery_response_rejects_non_array():
    try:
        parse_discovery_response(json.dumps({"not": "an array"}))
        assert False, "expected ValueError"
    except ValueError:
        pass
