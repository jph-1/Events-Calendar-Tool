from events_tool.places import parse_csv, parse_kml, parse_places_file

SAMPLE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<Placemark>
<name>Montrose Community Garden</name>
<description>Community gardening plot</description>
<Point><coordinates>-95.390,29.742,0</coordinates></Point>
</Placemark>
<Placemark>
<name>No Coordinates Place</name>
<description>Missing point data</description>
</Placemark>
<Placemark>
<description>Unnamed placemark, should be skipped</description>
</Placemark>
</Document>
</kml>
"""

SAMPLE_CSV = """name,address,lat,lon,tags
Continental Club,300 Main St Houston TX,29.75,-95.37,music;dance
Rooftop Cinema Collective,123 Main St Houston TX,29.7,-95.4,film
No Coordinates Venue,456 Elm St,,,maker
"""


def test_parse_kml_extracts_placemarks_with_coordinates():
    places = parse_kml(SAMPLE_KML)
    assert len(places) == 2  # the nameless placemark is skipped
    garden = next(p for p in places if p.name == "Montrose Community Garden")
    assert garden.lat == 29.742
    assert garden.lon == -95.390
    assert garden.address == "Community gardening plot"


def test_parse_kml_handles_missing_coordinates_gracefully():
    places = parse_kml(SAMPLE_KML)
    no_coords = next(p for p in places if p.name == "No Coordinates Place")
    assert no_coords.lat is None
    assert no_coords.lon is None


def test_parse_csv_extracts_rows():
    places = parse_csv(SAMPLE_CSV)
    assert len(places) == 3
    club = next(p for p in places if p.name == "Continental Club")
    assert club.lat == 29.75
    assert club.lon == -95.37
    assert club.tags == "music;dance"


def test_parse_csv_tolerates_missing_coordinates():
    places = parse_csv(SAMPLE_CSV)
    no_coords = next(p for p in places if p.name == "No Coordinates Venue")
    assert no_coords.lat is None
    assert no_coords.lon is None


def test_parse_csv_tolerates_malformed_coordinates_without_crashing():
    text = "name,address,lat,lon,tags\nBad Coords Place,123 St,not-a-number,also-bad,tag\n"
    places = parse_csv(text)
    assert len(places) == 1
    assert places[0].lat is None
    assert places[0].lon is None


def test_parse_csv_skips_rows_without_a_name():
    text = "name,address,lat,lon,tags\n,123 St,29.0,-95.0,tag\n"
    places = parse_csv(text)
    assert places == []


def test_parse_places_file_dispatches_by_format():
    assert len(parse_places_file(SAMPLE_KML, "kml")) == 2
    assert len(parse_places_file(SAMPLE_CSV, "csv")) == 3


def test_parse_places_file_rejects_unknown_format():
    try:
        parse_places_file("irrelevant", "geojson")
        assert False, "expected ValueError"
    except ValueError:
        pass
