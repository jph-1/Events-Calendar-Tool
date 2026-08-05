import json
from datetime import datetime

import pytest

from events_tool.ask import build_ask_prompt, parse_ask_response, resolve_range


def test_resolve_range_today():
    now = datetime(2026, 8, 4, 15, 30, 0)
    start, end, label = resolve_range("today", now=now)
    assert start == datetime(2026, 8, 4, 0, 0, 0)
    assert end == datetime(2026, 8, 4, 23, 59, 59)
    assert label == "today"


def test_resolve_range_week():
    now = datetime(2026, 8, 4, 15, 30, 0)
    start, end, label = resolve_range("week", now=now)
    assert start == now
    assert end == datetime(2026, 8, 11, 15, 30, 0)
    assert "7 days" in label


def test_resolve_range_30d_and_90d():
    now = datetime(2026, 8, 4, 0, 0, 0)
    _, end30, _ = resolve_range("30d", now=now)
    _, end90, _ = resolve_range("90d", now=now)
    assert (end30 - now).days == 30
    assert (end90 - now).days == 90


def test_resolve_range_custom():
    start, end, label = resolve_range("custom", custom_from="2026-08-20T00:00:00", custom_to="2026-08-25T00:00:00")
    assert start == datetime(2026, 8, 20)
    assert end == datetime(2026, 8, 25)
    assert "2026-08-20" in label and "2026-08-25" in label


def test_resolve_range_custom_requires_both_bounds():
    with pytest.raises(ValueError):
        resolve_range("custom", custom_from="2026-08-20T00:00:00", custom_to=None)


def test_resolve_range_unknown_choice_raises():
    with pytest.raises(ValueError):
        resolve_range("next-decade")


def test_build_ask_prompt_states_explicit_range_not_inferred():
    now = datetime(2026, 8, 4, 0, 0, 0)
    date_from, date_to, label = resolve_range("week", now=now)
    prompt = build_ask_prompt("Formula 1 watch party", "Houston", "TX", date_from, date_to, label)
    assert "Formula 1 watch party" in prompt
    assert "Houston, TX" in prompt
    assert "next_occurrence_suggestions" in prompt
    assert "2026-08-04" in prompt and "2026-08-11" in prompt


def test_parse_ask_response_separates_matches_and_suggestions():
    data = {
        "matches": [
            {"title": "In Range Event", "start_dt": "2026-08-05T19:00:00", "url": "https://example.org/a", "category": "music"}
        ],
        "next_occurrence_suggestions": [
            {
                "title": "Next F1 Watch Party",
                "start_dt": "2026-08-23T14:00:00",
                "url": "https://example.org/f1",
                "category": "sports_games",
                "note": "Next race is the Dutch GP, Aug 23 - outside your 7-day window",
            }
        ],
    }
    matches, suggestions, warnings = parse_ask_response(json.dumps(data))
    assert len(matches) == 1
    assert matches[0][0].title == "In Range Event"
    assert len(suggestions) == 1
    candidate, category, note = suggestions[0]
    assert candidate.title == "Next F1 Watch Party"
    assert category == "sports_games"
    assert "outside your 7-day window" in note
    assert warnings == []


def test_parse_ask_response_suggestion_without_note_gets_default():
    data = {"matches": [], "next_occurrence_suggestions": [
        {"title": "Something", "start_dt": "2026-09-01T00:00:00", "url": "https://example.org/x", "category": "other"}
    ]}
    _, suggestions, _ = parse_ask_response(json.dumps(data))
    assert suggestions[0][2] == "outside the requested range"


def test_parse_ask_response_drops_entries_without_url():
    data = {"matches": [{"title": "No URL", "start_dt": "2026-08-05T19:00:00", "url": ""}], "next_occurrence_suggestions": []}
    matches, suggestions, warnings = parse_ask_response(json.dumps(data))
    assert matches == []
    assert any("No URL" in w for w in warnings)


def test_parse_ask_response_empty_object_is_valid():
    matches, suggestions, warnings = parse_ask_response(json.dumps({"matches": [], "next_occurrence_suggestions": []}))
    assert matches == []
    assert suggestions == []
    assert warnings == []


def test_parse_ask_response_rejects_non_object():
    with pytest.raises(ValueError):
        parse_ask_response(json.dumps([1, 2, 3]))
