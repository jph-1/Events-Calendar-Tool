from pathlib import Path

from events_tool.ingestion.ics_rss_adapter import parse_feed, parse_ics, parse_rss

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_ics_extracts_all_vevents():
    text = (FIXTURES / "sample.ics").read_text()
    candidates = parse_ics(text, source_name="test-venue")
    assert len(candidates) == 3
    titles = {c.title for c in candidates}
    assert "Salsa Night Social" in titles
    assert "Community Garden Volunteer Day" in titles
    assert "All-Day Maker Space Open House" in titles


def test_parse_ics_datetime_and_description_unescaping():
    text = (FIXTURES / "sample.ics").read_text()
    candidates = parse_ics(text)
    salsa = next(c for c in candidates if c.title == "Salsa Night Social")
    assert salsa.start_dt == "2026-08-15T19:00:00"
    assert salsa.end_dt == "2026-08-15T22:00:00"
    assert "beginners welcome" in salsa.description
    assert "\\," not in salsa.description
    assert salsa.location_name == "The Dance Hall"
    assert salsa.url == "https://testvenue.example/events/salsa-night"
    assert salsa.source_type == "ical"


def test_parse_ics_all_day_event_defaults_midnight():
    text = (FIXTURES / "sample.ics").read_text()
    candidates = parse_ics(text)
    open_house = next(c for c in candidates if "Open House" in c.title)
    assert open_house.start_dt == "2026-09-01T00:00:00"


def test_parse_rss_extracts_items():
    text = (FIXTURES / "sample_rss.xml").read_text()
    candidates = parse_rss(text, source_name="test-gallery")
    assert len(candidates) == 2
    titles = {c.title for c in candidates}
    assert "New Art Exhibition Opening" in titles
    assert "Woodworking Basics Workshop" in titles
    for c in candidates:
        assert c.source_type == "rss"
        assert c.url.startswith("https://testgallery.example")


def test_parse_feed_dispatches_by_content():
    ics_text = (FIXTURES / "sample.ics").read_text()
    rss_text = (FIXTURES / "sample_rss.xml").read_text()
    assert len(parse_feed(ics_text)) == 3
    assert len(parse_feed(rss_text)) == 2
