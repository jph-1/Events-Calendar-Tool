"""Import a personal 'preferred places' list — e.g. a Google Maps My Maps
list exported as KML, or a plain CSV you maintain yourself — as a reference
list of venues you already trust or want to keep an eye on.

This is intentionally NOT live scraping of a Google Maps share URL: Google's
unofficial share-page markup isn't a stable public API and can change
without notice, silently breaking extraction. Exporting to KML (My Maps ->
menu -> Export to KML) or maintaining a CSV is slower per-refresh but won't
quietly rot.
"""
from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}

# Column name aliases seen across different "export my Google Maps saved
# places" tools, so a CSV doesn't have to be reshaped by hand before import.
_LAT_KEYS = ("lat", "latitude")
_LON_KEYS = ("lon", "lng", "longitude")
_URL_KEYS = ("url", "website", "google_maps_url", "maps_url")
_ACTIVE_KEYS = ("is_active", "active")
_FALSY = {"false", "0", "no", "n", ""}


@dataclass
class RawPlace:
    name: str
    address: str = ""
    lat: float | None = None
    lon: float | None = None
    tags: str = ""
    url: str = ""


def _find_first(elem: ET.Element, tag: str):
    """elem.find(a) or elem.find(b) is unsafe: Element truthiness depends on
    child count, not identity, so a childless-but-real match reads as falsy.
    Always check explicitly against None instead."""
    found = elem.find(f"kml:{tag}", _KML_NS)
    if found is not None:
        return found
    return elem.find(tag)


def parse_kml(text: str) -> list[RawPlace]:
    root = ET.fromstring(text)
    placemarks = root.findall(".//kml:Placemark", _KML_NS)
    if not placemarks:
        placemarks = root.findall(".//Placemark")
    places: list[RawPlace] = []

    for placemark in placemarks:
        name_el = _find_first(placemark, "name")
        name = (name_el.text or "").strip() if name_el is not None and name_el.text else ""
        if not name:
            continue

        desc_el = _find_first(placemark, "description")
        description = (desc_el.text or "").strip() if desc_el is not None and desc_el.text else ""

        lat = lon = None
        coords_el = placemark.find(".//kml:coordinates", _KML_NS)
        if coords_el is None:
            coords_el = placemark.find(".//coordinates")
        if coords_el is not None and coords_el.text:
            parts = coords_el.text.strip().split(",")
            if len(parts) >= 2:
                try:
                    lon = float(parts[0])
                    lat = float(parts[1])
                except ValueError:
                    lat = lon = None

        places.append(RawPlace(name=name, address=description, lat=lat, lon=lon))

    return places


def _row_lookup(row: dict) -> dict:
    """Case-insensitive header access, since export tools vary (Lat vs lat vs Latitude)."""
    return {k.strip().lower(): v for k, v in row.items() if k}


def _first_present(lookup: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = (lookup.get(key) or "").strip()
        if value:
            return value
    return ""


def _parse_float(raw: str) -> float | None:
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _types_to_tags(raw: str) -> str:
    """A 'types' column is often a JSON array like '["art_gallery","museum"]'
    from Google Places-flavored exports — normalize it to our semicolon tag
    format. Falls back to the raw string as a single tag if it isn't JSON."""
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return ";".join(str(t) for t in parsed if t)
    except (ValueError, TypeError):
        pass
    return raw


def parse_csv(text: str) -> list[RawPlace]:
    """Expected columns (any subset, any order, case-insensitive):
    name, address, lat/latitude, lon/longitude, tags (or types, as a JSON
    list or a plain string), url (or website/google_maps_url). A
    is_active/active column, if present, is honored — rows explicitly
    marked inactive are skipped."""
    reader = csv.DictReader(io.StringIO(text))
    places: list[RawPlace] = []
    for row in reader:
        lookup = _row_lookup(row)
        name = (lookup.get("name") or "").strip()
        if not name:
            continue

        active_raw = _first_present(lookup, _ACTIVE_KEYS)
        if active_raw and active_raw.strip().lower() in _FALSY:
            continue

        tags = (lookup.get("tags") or "").strip() or _types_to_tags((lookup.get("types") or "").strip())

        places.append(
            RawPlace(
                name=name,
                address=(lookup.get("address") or "").strip(),
                lat=_parse_float(_first_present(lookup, _LAT_KEYS)),
                lon=_parse_float(_first_present(lookup, _LON_KEYS)),
                tags=tags,
                url=_first_present(lookup, _URL_KEYS),
            )
        )
    return places


def parse_places_file(text: str, file_format: str) -> list[RawPlace]:
    if file_format == "kml":
        return parse_kml(text)
    if file_format == "csv":
        return parse_csv(text)
    raise ValueError(f"unsupported places file format: {file_format}")
