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
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_KML_NS = {"kml": "http://www.opengis.net/kml/2.2"}


@dataclass
class RawPlace:
    name: str
    address: str = ""
    lat: float | None = None
    lon: float | None = None
    tags: str = ""


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


def parse_csv(text: str) -> list[RawPlace]:
    """Expected columns (any subset, any order): name, address, lat, lon, tags."""
    reader = csv.DictReader(io.StringIO(text))
    places: list[RawPlace] = []
    for row in reader:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        lat_raw = (row.get("lat") or "").strip()
        lon_raw = (row.get("lon") or "").strip()
        try:
            lat = float(lat_raw) if lat_raw else None
        except ValueError:
            lat = None
        try:
            lon = float(lon_raw) if lon_raw else None
        except ValueError:
            lon = None
        places.append(
            RawPlace(
                name=name,
                address=(row.get("address") or "").strip(),
                lat=lat,
                lon=lon,
                tags=(row.get("tags") or "").strip(),
            )
        )
    return places


def parse_places_file(text: str, file_format: str) -> list[RawPlace]:
    if file_format == "kml":
        return parse_kml(text)
    if file_format == "csv":
        return parse_csv(text)
    raise ValueError(f"unsupported places file format: {file_format}")
