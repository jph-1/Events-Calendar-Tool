"""Tests for the Flask app: auth guards, login flow, and the ICS token
endpoint. Uses a temp DB path for isolation but relies on the real
config/profile.json for location/interests (as the CLI does too — this
repo has one global profile, not per-test isolation of it)."""
import pytest

from events_tool import db as db_mod
from events_tool.store import EventStore
from events_tool.users import create_user
from events_tool.web import create_app


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test_events.db"
    application = create_app(db_path=db_path, testing=True)
    application.config["WTF_CSRF_ENABLED"] = False
    with application.app_context():
        conn = db_mod.get_connection(db_path)
        create_user(conn, "testuser", "testpassword123")
        conn.close()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username="testuser", password="testpassword123"):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def test_login_page_loads(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_protected_route_redirects_to_login_when_anonymous(client):
    resp = client.get("/calendar/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_with_correct_credentials_succeeds(client):
    resp = login(client)
    assert resp.status_code == 302
    assert "/calendar" in resp.headers["Location"]


def test_login_with_wrong_password_fails(client):
    resp = login(client, password="wrong-password")
    assert resp.status_code == 200
    assert b"Incorrect username or password" in resp.data


def test_authenticated_calendar_view_loads(client):
    login(client)
    resp = client.get("/calendar/")
    assert resp.status_code == 200
    assert b"Calendar" in resp.data


def test_authenticated_can_reach_all_main_pages(client):
    login(client)
    for path in ("/calendar/", "/calendar/agenda", "/ask/", "/review/", "/coverage/", "/places/", "/settings/"):
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"


def test_logout_clears_session(client):
    login(client)
    assert client.get("/calendar/").status_code == 200
    client.post("/logout")
    resp = client.get("/calendar/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_ics_feed_requires_valid_token(app, client):
    login(client)
    with app.app_context():
        store = EventStore(db_mod.get_connection(app.config["DB_PATH"]))
        from events_tool.users import get_user

        user = get_user(store.conn)

    resp_wrong = client.get("/calendar/not-a-real-token.ics")
    assert resp_wrong.status_code == 404

    resp_right = client.get(f"/calendar/{user.ics_token}.ics")
    assert resp_right.status_code == 200
    assert resp_right.mimetype == "text/calendar"
    assert b"BEGIN:VCALENDAR" in resp_right.data


def test_ics_feed_does_not_require_login(app):
    """Calendar apps poll this URL without an interactive session — it
    must work even when the client never logged in."""
    with app.app_context():
        store = EventStore(db_mod.get_connection(app.config["DB_PATH"]))
        from events_tool.users import get_user

        user = get_user(store.conn)

    anon_client = app.test_client()
    resp = anon_client.get(f"/calendar/{user.ics_token}.ics")
    assert resp.status_code == 200


def test_add_event_via_direct_store_then_confirm_reject_flow(app, client):
    """Exercises confirm/reject through the actual HTTP routes, since
    those are the security/behavior-sensitive parts of the review flow."""
    login(client)
    with app.app_context():
        store = EventStore(db_mod.get_connection(app.config["DB_PATH"]))
        from events_tool.models import RawEventCandidate

        candidate = RawEventCandidate(title="Test Event", start_dt="2026-08-10T19:00:00")
        event_id, _ = store.insert_candidate(candidate, "music", "Houston", "TX", status="candidate")

    resp = client.get("/review/")
    assert resp.status_code == 200
    assert b"Test Event" in resp.data

    resp = client.post(f"/review/{event_id}/confirm", data={"notes": "verified in person"}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        store = EventStore(db_mod.get_connection(app.config["DB_PATH"]))
        row = store.get_by_id(event_id)
        assert row["status"] == "confirmed"
        assert row["user_notes"] == "verified in person"


def _insert_event(app, **overrides):
    from events_tool.models import RawEventCandidate

    with app.app_context():
        store = EventStore(db_mod.get_connection(app.config["DB_PATH"]))
        defaults = dict(title="Card Test Event", start_dt="2026-08-10T19:00:00", location_name="Test Venue")
        defaults.update(overrides)
        candidate = RawEventCandidate(**{k: v for k, v in defaults.items() if k in ("title", "start_dt", "location_name", "description")})
        event_id, _ = store.insert_candidate(candidate, "music", "Houston", "TX", status="confirmed")
        return event_id


def test_not_interested_rejects_from_any_status(app, client):
    login(client)
    event_id = _insert_event(app)
    resp = client.post(f"/calendar/event/{event_id}/not-interested", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        store = EventStore(db_mod.get_connection(app.config["DB_PATH"]))
        assert store.get_by_id(event_id)["status"] == "rejected"


def test_add_to_interests_seeds_a_new_interest_from_venue_name(app, client):
    from events_tool import config as config_mod

    login(client)
    event_id = _insert_event(app, location_name="The Continental Club")
    resp = client.post(f"/calendar/event/{event_id}/add-to-interests", follow_redirects=True)
    assert resp.status_code == 200

    profile = config_mod.load_profile()
    try:
        keywords = {i.keyword for i in profile.interests}
        assert "the continental club" in keywords
    finally:
        config_mod.remove_interest(profile, "the continental club")
        config_mod.save_profile(profile)


def test_confirm_via_calendar_route(app, client):
    login(client)
    with app.app_context():
        from events_tool.models import RawEventCandidate

        store = EventStore(db_mod.get_connection(app.config["DB_PATH"]))
        candidate = RawEventCandidate(title="Pending Card", start_dt="2026-08-11T19:00:00")
        event_id, _ = store.insert_candidate(candidate, "music", "Houston", "TX", status="candidate")

    resp = client.post(f"/calendar/event/{event_id}/confirm", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        store = EventStore(db_mod.get_connection(app.config["DB_PATH"]))
        assert store.get_by_id(event_id)["status"] == "confirmed"


def test_agenda_cards_view_renders(client):
    login(client)
    resp = client.get("/calendar/agenda?view=cards")
    assert resp.status_code == 200


def test_review_page_renders_cards_for_pending(app, client):
    login(client)
    with app.app_context():
        from events_tool.models import RawEventCandidate

        store = EventStore(db_mod.get_connection(app.config["DB_PATH"]))
        candidate = RawEventCandidate(title="Card Review Test", start_dt="2026-08-12T19:00:00", url="https://example.org/x")
        store.insert_candidate(candidate, "art", "Houston", "TX", status="candidate")

    resp = client.get("/review/")
    assert resp.status_code == 200
    assert b"Card Review Test" in resp.data
    assert b"Add to interests" in resp.data
    assert b"Not for me" in resp.data
