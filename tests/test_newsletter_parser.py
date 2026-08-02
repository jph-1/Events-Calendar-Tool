import json
from datetime import date
from pathlib import Path

from events_tool.ingestion.newsletter_adapter import (
    build_extraction_prompt,
    heuristic_extract,
    parse_structured_response,
)
from events_tool.models import Interest

FIXTURES = Path(__file__).parent / "fixtures"


def test_heuristic_extract_finds_dated_lines():
    text = (FIXTURES / "sample_newsletter.txt").read_text()
    candidates = heuristic_extract(text, reference_date=date(2026, 1, 1))
    assert len(candidates) == 3  # the undated announcement line is skipped

    kettlebell = next(c for c in candidates if "Kettlebell" in c.title)
    assert kettlebell.start_dt == "2026-08-12T18:00:00"

    book_club = next(c for c in candidates if "Book Club" in c.title)
    assert book_club.start_dt == "2026-08-19T19:30:00"

    natural_building = next(c for c in candidates if "Natural Building" in c.title)
    assert natural_building.start_dt == "2026-09-05T10:00:00"


def test_heuristic_extract_ignores_undated_lines():
    text = (FIXTURES / "sample_newsletter.txt").read_text()
    candidates = heuristic_extract(text, reference_date=date(2026, 1, 1))
    assert not any("ignored by the extractor" in c.title for c in candidates)


def test_heuristic_extract_rolls_year_forward_when_date_already_passed():
    candidates = heuristic_extract("Old Event - Jan 1 9:00am", reference_date=date(2026, 6, 1))
    assert candidates[0].start_dt == "2027-01-01T09:00:00"


def test_parse_structured_response_from_fixture():
    json_text = (FIXTURES / "sample_structured.json").read_text()
    candidates = parse_structured_response(json_text, source_name="newsletter-structured")
    assert len(candidates) == 2
    titles = {c.title for c in candidates}
    assert "Indie Film Night: Shorts Program" in titles
    assert "Kettlebell Club Meetup" in titles
    for c in candidates:
        assert c.source_type == "newsletter"


def test_parse_structured_response_rejects_non_array():
    try:
        parse_structured_response(json.dumps({"not": "an array"}))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_build_extraction_prompt_includes_interests_and_text():
    interests = [Interest(keyword="salsa", category="dance"), Interest(keyword="book club", category="books")]
    prompt = build_extraction_prompt("Some newsletter text here.", interests)
    assert "salsa -> dance" in prompt
    assert "book club -> books" in prompt
    assert "Some newsletter text here." in prompt
