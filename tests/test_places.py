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


# Real-world export schema (e.g. from third-party "export my Google Maps
# saved places" tools): latitude/longitude instead of lat/lon, a JSON-array
# 'types' column instead of 'tags', a url alias chain, and an is_active flag.
GOOGLE_EXPORT_CSV = (
    "name,address,website,google_maps_url,latitude,longitude,types,is_active\n"
    '93\' Til,"1601 W Main St, Houston, TX 77006",,'
    "https://www.google.com/maps/search/?api=1&query=93%27+Til,,,[],true\n"
    "Asia Society Texas Center,\"1370 Southmore Blvd, Houston, TX 77004\",,"
    "https://www.google.com/maps/search/?api=1&query=Asia+Society,29.7263093,-95.3846713,"
    '"[""establishment"",""museum"",""point_of_interest"",""tourist_attraction""]",true\n'
    "Closed Place,\"1 Nowhere St\",https://closed.example,,29.0,-95.0,[],false\n"
)


def test_parse_csv_understands_latitude_longitude_aliases():
    places = parse_csv(GOOGLE_EXPORT_CSV)
    asia = next(p for p in places if p.name == "Asia Society Texas Center")
    assert asia.lat == 29.7263093
    assert asia.lon == -95.3846713


def test_parse_csv_derives_tags_from_json_types_column():
    places = parse_csv(GOOGLE_EXPORT_CSV)
    asia = next(p for p in places if p.name == "Asia Society Texas Center")
    assert asia.tags == "establishment;museum;point_of_interest;tourist_attraction"


def test_parse_csv_empty_types_array_yields_empty_tags():
    places = parse_csv(GOOGLE_EXPORT_CSV)
    til = next(p for p in places if "Til" in p.name)
    assert til.tags == ""


def test_parse_csv_url_falls_back_to_google_maps_url_when_website_is_blank():
    places = parse_csv(GOOGLE_EXPORT_CSV)
    til = next(p for p in places if "Til" in p.name)
    assert til.url.startswith("https://www.google.com/maps/search")


def test_parse_csv_skips_rows_marked_inactive():
    places = parse_csv(GOOGLE_EXPORT_CSV)
    names = {p.name for p in places}
    assert "Closed Place" not in names
    assert len(places) == 2


def test_parse_csv_collapses_embedded_newlines_in_name_and_address():
    text = (
        "name,address\n"
        '"Hope Farms Urban Agricultural Showcase and Training Center - Recipe for \nSuccess",'
        '"10401 Scott St, Houston,\nTX 77051"\n'
    )
    places = parse_csv(text)
    assert len(places) == 1
    assert "\n" not in places[0].name
    assert "\n" not in places[0].address
    assert places[0].name == "Hope Farms Urban Agricultural Showcase and Training Center - Recipe for Success"
    assert places[0].address == "10401 Scott St, Houston, TX 77051"
