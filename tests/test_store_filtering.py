import pytest

from events_tool import db as db_mod
from events_tool.models import RawEventCandidate
from events_tool.store import EventStore


@pytest.fixture
def store(tmp_path):
    conn = db_mod.get_connection(tmp_path / "test_events.db")
    return EventStore(conn)


def _candidate(title, start_dt, neighborhood="", location_name=""):
    return RawEventCandidate(
        title=title, start_dt=start_dt, neighborhood=neighborhood, location_name=location_name
    )


def test_insert_and_dedup(store):
    c = _candidate("Salsa Night", "2026-08-15T19:00:00")
    id1, new1 = store.insert_candidate(c, "dance", "Houston", "TX")
    id2, new2 = store.insert_candidate(c, "dance", "Houston", "TX")
    assert new1 is True
    assert new2 is False
    assert id1 == id2


def test_query_by_category(store):
    store.insert_candidate(_candidate("Salsa Night", "2026-08-15T19:00:00"), "dance", "Houston", "TX")
    store.insert_candidate(_candidate("Book Club", "2026-08-16T18:00:00"), "books", "Houston", "TX")
    rows = store.query(category="dance")
    assert len(rows) == 1
    assert rows[0]["title"] == "Salsa Night"


def test_query_by_near(store):
    store.insert_candidate(
        _candidate("Art Show", "2026-08-15T19:00:00", neighborhood="Montrose"), "art", "Houston", "TX"
    )
    store.insert_candidate(
        _candidate("Gardening Workshop", "2026-08-16T10:00:00", neighborhood="Heights"), "gardening", "Houston", "TX"
    )
    rows = store.query(near="Montrose")
    assert len(rows) == 1
    assert rows[0]["title"] == "Art Show"


def test_query_by_date_range(store):
    store.insert_candidate(_candidate("Early Event", "2026-08-01T10:00:00"), "art", "Houston", "TX")
    store.insert_candidate(_candidate("Late Event", "2026-09-01T10:00:00"), "art", "Houston", "TX")
    rows = store.query(date_from="2026-08-15T00:00:00", date_to="2026-08-31T23:59:59")
    assert rows == []
    rows = store.query(date_from="2026-07-15T00:00:00", date_to="2026-08-15T00:00:00")
    assert len(rows) == 1
    assert rows[0]["title"] == "Early Event"


def test_status_transitions_and_pending_review(store):
    event_id, _ = store.insert_candidate(
        _candidate("New Candidate", "2026-08-15T19:00:00"), "art", "Houston", "TX", status="candidate"
    )
    pending = store.pending_review()
    assert len(pending) == 1
    store.update_status(event_id, "confirmed")
    assert store.pending_review() == []
    row = store.get_by_id(event_id)
    assert row["status"] == "confirmed"


def test_invalid_status_rejected(store):
    with pytest.raises(ValueError):
        store.insert_candidate(_candidate("X", "2026-08-15T19:00:00"), "art", "Houston", "TX", status="bogus")


def test_upcoming_roundup_candidates_excludes_already_included(store):
    event_id, _ = store.insert_candidate(
        _candidate("Confirmed Event", "2026-08-15T19:00:00"), "art", "Houston", "TX", status="confirmed"
    )
    rows = store.upcoming_roundup_candidates("2026-08-01T00:00:00", "2026-08-31T00:00:00")
    assert len(rows) == 1
    store.mark_roundup_included([event_id])
    rows = store.upcoming_roundup_candidates("2026-08-01T00:00:00", "2026-08-31T00:00:00")
    assert rows == []


def test_user_category_override_does_not_touch_source_category(store):
    event_id, _ = store.insert_candidate(
        _candidate("Comedy Open Mic", "2026-08-06T20:00:00"), "comedy", "Houston", "TX", status="confirmed"
    )
    store.set_user_category(event_id, "sports_games")
    row = store.get_by_id(event_id)
    assert row["source_category"] == "comedy"
    assert row["user_category"] == "sports_games"
    assert row["category"] == "sports_games"  # effective category is the override

    # Filtering by the corrected category finds it; filtering by the old
    # ingested category no longer does — but the source fact is untouched.
    assert len(store.query(category="sports_games")) == 1
    assert len(store.query(category="comedy")) == 0


def test_clearing_user_category_reverts_to_source_fact(store):
    event_id, _ = store.insert_candidate(
        _candidate("Comedy Open Mic", "2026-08-06T20:00:00"), "comedy", "Houston", "TX", status="confirmed"
    )
    store.set_user_category(event_id, "sports_games")
    store.set_user_category(event_id, None)
    row = store.get_by_id(event_id)
    assert row["source_category"] == "comedy"
    assert row["category"] == "comedy"


def test_save_and_unsave(store):
    event_id, _ = store.insert_candidate(
        _candidate("Salsa Night", "2026-08-15T19:00:00"), "dance", "Houston", "TX", status="confirmed"
    )
    assert store.get_by_id(event_id)["saved"] == 0
    store.set_saved(event_id, True)
    assert store.get_by_id(event_id)["saved"] == 1
    assert len(store.query(saved_only=True)) == 1
    store.set_saved(event_id, False)
    assert store.get_by_id(event_id)["saved"] == 0
    assert store.query(saved_only=True) == []


def test_attend_and_reverse_attendance(store):
    event_id, _ = store.insert_candidate(
        _candidate("Salsa Night", "2026-08-15T19:00:00"), "dance", "Houston", "TX", status="confirmed"
    )
    store.update_status(event_id, "attended")
    assert store.get_by_id(event_id)["status"] == "attended"
    # Reversing attendance is just a status transition back — no separate API needed.
    store.update_status(event_id, "confirmed")
    assert store.get_by_id(event_id)["status"] == "confirmed"


def test_user_notes_are_independent_of_description(store):
    event_id, _ = store.insert_candidate(
        _candidate("Salsa Night", "2026-08-15T19:00:00"), "dance", "Houston", "TX", status="confirmed"
    )
    store.set_user_notes(event_id, "Great band, will go again")
    row = store.get_by_id(event_id)
    assert row["user_notes"] == "Great band, will go again"
    assert row["description"] == ""  # untouched source fact


def test_verification_provenance_recorded(store):
    event_id, _ = store.insert_candidate(
        _candidate("Salsa Night", "2026-08-15T19:00:00"),
        "dance",
        "Houston",
        "TX",
        status="confirmed",
        verification="automated-source",
    )
    row = store.get_by_id(event_id)
    assert row["verification"] == "automated-source"


def test_category_counts_filtered_by_verification(store):
    store.insert_candidate(
        _candidate("Automated Show", "2026-08-15T19:00:00"),
        "art",
        "Houston",
        "TX",
        status="confirmed",
        verification="automated-source",
    )
    store.insert_candidate(
        _candidate("Manual Show", "2026-08-16T19:00:00"),
        "art",
        "Houston",
        "TX",
        status="confirmed",
        verification="user-manual",
    )
    all_counts = store.category_counts()
    automated_counts = store.category_counts(verification="automated-source")
    assert all_counts["art"] == 2
    assert automated_counts["art"] == 1


def test_places_insert_and_list(store):
    from events_tool.models import Place

    store.insert_place(
        Place(
            id=None,
            name="Continental Club",
            address="300 Main St",
            lat=29.75,
            lon=-95.37,
            tags="music",
            list_name="Favorites",
            source="csv",
            imported_at="2026-08-02T00:00:00",
        )
    )
    rows = store.places()
    assert len(rows) == 1
    assert rows[0]["name"] == "Continental Club"
    assert store.places(list_name="Favorites") == rows
    assert store.places(list_name="Nonexistent") == []
