"""Load, save, and edit the user's profile: location, interests, and sources.

The profile is a single hand-editable JSON file (config/profile.json). It is
intentionally not a database table: interests and sources are things a user
wants to read and tweak directly, and a plain JSON file is the friendliest
format for that. A Houston-seeded example ships as config/profile.example.json
so `events init` has sensible starting defaults for any new user/city.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from events_tool.models import Interest, Location, Profile, Source

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "config" / "profile.json"
EXAMPLE_PROFILE_PATH = PROJECT_ROOT / "config" / "profile.example.json"


class ProfileNotFoundError(RuntimeError):
    pass


def _profile_from_dict(data: dict[str, Any]) -> Profile:
    location = Location(**data.get("location", {"city": "", "state": ""}))
    future_flags = dict(data.get("future_flags", {"use_geolocation": False}))
    interests = [Interest(**i) for i in data.get("interests", [])]
    sources = [Source(**s) for s in data.get("sources", [])]
    return Profile(location=location, future_flags=future_flags, interests=interests, sources=sources)


def _profile_to_dict(profile: Profile) -> dict[str, Any]:
    return {
        "location": asdict(profile.location),
        "future_flags": profile.future_flags,
        "interests": [asdict(i) for i in profile.interests],
        "sources": [asdict(s) for s in profile.sources],
    }


def load_profile(path: Path = DEFAULT_PROFILE_PATH) -> Profile:
    if not path.exists():
        raise ProfileNotFoundError(
            f"No profile found at {path}. Run `events init` first "
            f"(optionally with --city/--state), or copy config/profile.example.json."
        )
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return _profile_from_dict(data)


def save_profile(profile: Profile, path: Path = DEFAULT_PROFILE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(_profile_to_dict(profile), f, indent=2, sort_keys=False)
        f.write("\n")


def init_profile(
    city: str = "Houston",
    state: str = "TX",
    path: Path = DEFAULT_PROFILE_PATH,
    force: bool = False,
) -> Profile:
    """Create a new profile, seeded from the example profile, with location overridden."""
    if path.exists() and not force:
        raise FileExistsError(f"Profile already exists at {path}. Pass force=True to overwrite.")
    with EXAMPLE_PROFILE_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    profile = _profile_from_dict(data)
    profile.location = Location(city=city, state=state, lat=None, lon=None)
    save_profile(profile, path)
    return profile


def add_interest(
    profile: Profile, keyword: str, category: str, weight: float = 1.0
) -> Profile:
    keyword_norm = keyword.strip().lower()
    for existing in profile.interests:
        if existing.keyword.lower() == keyword_norm:
            existing.category = category
            existing.weight = weight
            existing.active = True
            return profile
    profile.interests.append(Interest(keyword=keyword.strip(), category=category, weight=weight, active=True))
    return profile


def remove_interest(profile: Profile, keyword: str) -> bool:
    keyword_norm = keyword.strip().lower()
    before = len(profile.interests)
    profile.interests = [i for i in profile.interests if i.keyword.lower() != keyword_norm]
    return len(profile.interests) < before


def add_source(profile: Profile, name: str, source_type: str, url: str, enabled: bool = True) -> Profile:
    for existing in profile.sources:
        if existing.name == name:
            existing.type = source_type
            existing.url = url
            existing.enabled = enabled
            return profile
    profile.sources.append(Source(name=name, type=source_type, url=url, enabled=enabled))
    return profile


def remove_source(profile: Profile, name: str) -> bool:
    before = len(profile.sources)
    profile.sources = [s for s in profile.sources if s.name != name]
    return len(profile.sources) < before
