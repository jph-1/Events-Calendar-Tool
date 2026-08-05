"""Flask app factory for the events_tool Phase 2 web app.

Built on the exact same engine as the CLI (events_tool.store, .config,
.digest, .discovery, .ask, .places, .ics_export) — this app is a UI layer
on top of it, not a parallel implementation. A request-scoped SQLite
connection (via flask.g) backs an EventStore per request, mirroring how
the CLI opens one connection per invocation.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, current_app, g, redirect, session, url_for

from events_tool import config as config_mod
from events_tool import db as db_mod
from events_tool.matching import score_candidate
from events_tool.models import RawEventCandidate
from events_tool.store import EventStore
from events_tool.users import User, get_user
from events_tool.web.colors import cat_color

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SECRET_KEY_PATH = PROJECT_ROOT / "data" / "flask_secret.key"


def _load_or_create_secret_key() -> str:
    """The session-signing secret. Prefers the EVENTS_TOOL_SECRET_KEY env
    var (the natural fit for platforms with a secrets manager — Fly.io
    secrets, Render/Railway env vars — where persistent-file storage isn't
    guaranteed across deploys); otherwise it's generated once and persisted
    to a local file. Unlike data/events.db and config/profile.json, neither
    form is tracked in git — leaking it would let someone forge sessions."""
    env_key = os.environ.get("EVENTS_TOOL_SECRET_KEY")
    if env_key:
        return env_key
    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_text(encoding="utf-8").strip()
    SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    SECRET_KEY_PATH.write_text(key, encoding="utf-8")
    return key


def get_store() -> EventStore:
    if "store" not in g:
        db_path = current_app.config.get("DB_PATH", db_mod.DEFAULT_DB_PATH)
        g.store = EventStore(db_mod.get_connection(db_path))
    return g.store


def get_profile():
    if "profile" not in g:
        g.profile = config_mod.load_profile()
    return g.profile


def get_current_user() -> User | None:
    if "user" not in g:
        store = get_store()
        user = get_user(store.conn)
        g.user = user if (user and session.get("user_id") == user.id) else None
    return g.user


def matched_keywords_for(event) -> list[str]:
    """Recomputed live against *current* active interests, not stored on
    the event row — so if you edit your interests later, a card's "why
    this matched" chips reflect that immediately rather than going stale."""
    profile = get_profile()
    candidate = RawEventCandidate(title=event["title"], description=event["description"])
    result = score_candidate(candidate, profile.interests)
    return result.matched_keywords if result.matched else []


def create_app(db_path=None, testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = _load_or_create_secret_key()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Set EVENTS_TOOL_HTTPS=1 once this is actually served over HTTPS (any
    # real deployment) so the session cookie is marked Secure. Left off by
    # default so `events web run` still works for plain-HTTP local testing.
    app.config["SESSION_COOKIE_SECURE"] = os.environ.get("EVENTS_TOOL_HTTPS") == "1"
    app.config["TESTING"] = testing
    if db_path is not None:
        app.config["DB_PATH"] = db_path
    elif os.environ.get("EVENTS_TOOL_DB_PATH"):
        app.config["DB_PATH"] = Path(os.environ["EVENTS_TOOL_DB_PATH"])

    @app.teardown_appcontext
    def close_db(exception=None):
        store = g.pop("store", None)
        if store is not None:
            store.conn.close()

    @app.context_processor
    def inject_globals():
        return {"current_user": get_current_user(), "cat_color": cat_color, "matched_keywords": matched_keywords_for}

    from events_tool.web.routes.auth import bp as auth_bp
    from events_tool.web.routes.calendar import bp as calendar_bp
    from events_tool.web.routes.ask import bp as ask_bp
    from events_tool.web.routes.review import bp as review_bp
    from events_tool.web.routes.coverage import bp as coverage_bp
    from events_tool.web.routes.places import bp as places_bp
    from events_tool.web.routes.settings import bp as settings_bp
    from events_tool.web.routes.ics import bp as ics_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(ask_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(coverage_bp)
    app.register_blueprint(places_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(ics_bp)

    @app.route("/")
    def index():
        return redirect(url_for("calendar.month_view"))

    return app
