"""Live webcal/.ics subscription endpoint.

Deliberately NOT session-authenticated: calendar apps (Google Calendar,
Apple Calendar, etc.) poll this URL periodically with no interactive
login, so it's protected by a private, regenerable token instead — the
same pattern most calendar-subscription features use. Anyone with the
token can read (not modify) the calendar; regenerate it from Settings if
it ever leaks.
"""
from __future__ import annotations

from flask import Blueprint, Response, abort

from events_tool.ics_export import build_calendar
from events_tool.users import get_user_by_ics_token
from events_tool.web import get_store

bp = Blueprint("ics", __name__)


@bp.route("/calendar/<token>.ics")
def feed(token):
    store = get_store()
    user = get_user_by_ics_token(store.conn, token)
    if user is None:
        abort(404)

    rows = store.query(statuses=["confirmed", "attended"])
    calendar_text = build_calendar(rows)
    return Response(calendar_text, mimetype="text/calendar")
