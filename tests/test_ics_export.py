from events_tool.ics_export import build_calendar, event_to_vevent
from events_tool.ingestion.ics_rss_adapter import parse_ics


def _event(**overrides):
    base = dict(
        id=1,
        dedup_key="abc123",
        title="Salsa Night",
        description="Live music, dancing.",
        start_dt="2026-08-15T19:00:00",
        end_dt="2026-08-15T22:00:00",
        location_name="The Dance Hall",
        url="https://example.org/salsa",
    )
    base.update(overrides)
    return base


def test_round_trip_through_ingestion_parser():
    calendar_text = build_calendar([_event()])
    parsed = parse_ics(calendar_text)
    assert len(parsed) == 1
    assert parsed[0].title == "Salsa Night"
    assert parsed[0].start_dt == "2026-08-15T19:00:00"
    assert parsed[0].end_dt == "2026-08-15T22:00:00"
    assert parsed[0].location_name == "The Dance Hall"
    assert parsed[0].url == "https://example.org/salsa"


def test_calendar_has_required_header_and_footer():
    calendar_text = build_calendar([_event()])
    assert calendar_text.startswith("BEGIN:VCALENDAR")
    assert "VERSION:2.0" in calendar_text
    assert calendar_text.strip().endswith("END:VCALENDAR")


def test_escaping_of_commas_semicolons_and_newlines():
    event = _event(title="Art, Wine & Cheese; Reception", description="Line one\nLine two")
    vevent = event_to_vevent(event)
    assert "Art\\, Wine & Cheese\\; Reception" in vevent
    assert "Line one\\nLine two" in vevent
    # And it should parse back to the original unescaped values.
    parsed = parse_ics(build_calendar([event]))
    assert parsed[0].title == "Art, Wine & Cheese; Reception"
    assert "Line one\nLine two" in parsed[0].description


def test_long_lines_are_folded():
    long_description = "A" * 200
    event = _event(description=long_description)
    vevent = event_to_vevent(event)
    lines = vevent.split("\r\n")
    for line in lines:
        assert len(line.encode("utf-8")) <= 76  # 75 + leading fold space on continuations
    # Folded continuation lines start with a single space per RFC 5545.
    assert any(line.startswith(" ") for line in lines)


def test_missing_optional_fields_omit_lines():
    event = _event(end_dt=None, description="", location_name="", url="")
    vevent = event_to_vevent(event)
    assert "DTEND" not in vevent
    assert "DESCRIPTION" not in vevent
    assert "LOCATION" not in vevent
    assert "URL" not in vevent
