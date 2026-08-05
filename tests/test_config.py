import pytest

from events_tool import config as config_mod


@pytest.fixture
def profile_path(tmp_path):
    return tmp_path / "profile.json"


def test_init_profile_seeds_from_example_and_sets_location(profile_path):
    profile = config_mod.init_profile(city="Austin", state="TX", path=profile_path)
    assert profile.location.city == "Austin"
    assert profile.location.state == "TX"
    assert len(profile.interests) > 0
    assert profile_path.exists()


def test_init_profile_refuses_to_overwrite_without_force(profile_path):
    config_mod.init_profile(city="Houston", state="TX", path=profile_path)
    with pytest.raises(FileExistsError):
        config_mod.init_profile(city="Austin", state="TX", path=profile_path)


def test_init_profile_force_overwrites(profile_path):
    config_mod.init_profile(city="Houston", state="TX", path=profile_path)
    profile = config_mod.init_profile(city="Austin", state="TX", path=profile_path, force=True)
    assert profile.location.city == "Austin"


def test_load_profile_missing_raises(profile_path):
    with pytest.raises(config_mod.ProfileNotFoundError):
        config_mod.load_profile(profile_path)


def test_save_and_load_round_trip(profile_path):
    profile = config_mod.init_profile(city="Houston", state="TX", path=profile_path)
    config_mod.add_interest(profile, "pottery class", "maker", weight=0.8)
    config_mod.save_profile(profile, profile_path)

    reloaded = config_mod.load_profile(profile_path)
    keywords = {i.keyword for i in reloaded.interests}
    assert "pottery class" in keywords


def test_add_interest_updates_existing_instead_of_duplicating(profile_path):
    profile = config_mod.init_profile(city="Houston", state="TX", path=profile_path)
    config_mod.add_interest(profile, "salsa", "dance", weight=0.5)
    config_mod.add_interest(profile, "salsa", "dance", weight=0.9)
    matches = [i for i in profile.interests if i.keyword.lower() == "salsa"]
    assert len(matches) == 1
    assert matches[0].weight == 0.9


def test_remove_interest(profile_path):
    profile = config_mod.init_profile(city="Houston", state="TX", path=profile_path)
    assert config_mod.remove_interest(profile, "salsa") is True
    assert config_mod.remove_interest(profile, "nonexistent-keyword") is False


def test_add_and_remove_source(profile_path):
    profile = config_mod.init_profile(city="Houston", state="TX", path=profile_path)
    config_mod.add_source(profile, "my-venue", "ical", "https://venue.example/events/?ical=1")
    names = {s.name for s in profile.sources}
    assert "my-venue" in names
    assert config_mod.remove_source(profile, "my-venue") is True
    assert config_mod.remove_source(profile, "my-venue") is False


def test_add_source_records_notes(profile_path):
    profile = config_mod.init_profile(city="Houston", state="TX", path=profile_path)
    config_mod.add_source(profile, "my-venue", "ical", "https://venue.example/events/?ical=1", notes="unverified, standard plugin URL convention")
    source = next(s for s in profile.sources if s.name == "my-venue")
    assert source.notes == "unverified, standard plugin URL convention"


def test_add_source_updates_notes_on_existing_source(profile_path):
    profile = config_mod.init_profile(city="Houston", state="TX", path=profile_path)
    config_mod.add_source(profile, "my-venue", "ical", "https://venue.example/events/?ical=1", notes="first note")
    config_mod.add_source(profile, "my-venue", "ical", "https://venue.example/events/?ical=1", notes="updated note")
    source = next(s for s in profile.sources if s.name == "my-venue")
    assert source.notes == "updated note"
