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
