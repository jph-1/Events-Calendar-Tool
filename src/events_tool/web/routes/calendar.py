"""Month and agenda calendar views, plus the per-event action routes
(save/unsave/attend/unattend/recategorize/notes) that make this a real,
interactive calendar rather than the read-only Phase 1 prototype."""
from __future__ import annotations

import calendar as calendar_module
from datetime import date, datetime, timedelta

from flask import Blueprint, redirect, render_template, request, url_for

from events_tool.models import CATEGORIES
from events_tool.web import get_profile, get_store
from events_tool.web.auth import login_required

bp = Blueprint("calendar", __name__, url_prefix="/calendar")


def _parse_events_by_day(rows):
    by_day: dict[str, list] = {}
    for row in rows:
        day_key = row["start_dt"][:10]
        by_day.setdefault(day_key, []).append(row)
    return by_day


@bp.route("/")
@login_required
def month_view():
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month

    store = get_store()
    active_categories = request.args.getlist("category") or None
    saved_only = request.args.get("saved") == "1"

    first_of_month = date(year, month, 1)
    last_day = calendar_module.monthrange(year, month)[1]
    last_of_month = date(year, month, last_day)
    grid_start = first_of_month - timedelta(days=(first_of_month.weekday() + 1) % 7)  # Sunday-start grid

    rows = store.query(
        date_from=grid_start.isoformat(),
        date_to=(grid_start + timedelta(days=41)).isoformat() + "T23:59:59",
        statuses=["confirmed", "attended"],
        saved_only=saved_only,
    )
    if active_categories:
        rows = [r for r in rows if r["category"] in active_categories]

    by_day = _parse_events_by_day(rows)

    weeks = []
    cursor = grid_start
    for _ in range(6):
        week = []
        for _ in range(7):
            key = cursor.isoformat()
            week.append(
                {
                    "date": cursor,
                    "in_month": cursor.month == month,
                    "is_today": cursor == today,
                    "events": sorted(by_day.get(key, []), key=lambda r: r["start_dt"]),
                }
            )
            cursor += timedelta(days=1)
        weeks.append(week)

    prev_month = (first_of_month - timedelta(days=1)).replace(day=1)
    next_month = (last_of_month + timedelta(days=1))

    category_counts = {}
    for r in rows:
        category_counts[r["category"]] = category_counts.get(r["category"], 0) + 1

    return render_template(
        "calendar_month.html",
        weeks=weeks,
        month_name=first_of_month.strftime("%B %Y"),
        prev_year=prev_month.year,
        prev_month=prev_month.month,
        next_year=next_month.year,
        next_month=next_month.month,
        today_year=today.year,
        today_month=today.month,
        categories=CATEGORIES,
        active_categories=set(active_categories or []),
        saved_only=saved_only,
        category_counts=category_counts,
    )


@bp.route("/agenda")
@login_required
def agenda_view():
    store = get_store()
    range_choice = request.args.get("range", "week")
    now = datetime.now()
    ranges = {
        "today": (now.replace(hour=0, minute=0, second=0, microsecond=0), now.replace(hour=23, minute=59, second=59)),
        "week": (now, now + timedelta(days=7)),
        "30d": (now, now + timedelta(days=30)),
        "90d": (now, now + timedelta(days=90)),
    }
    date_from, date_to = ranges.get(range_choice, ranges["week"])

    active_categories = request.args.getlist("category") or None
    saved_only = request.args.get("saved") == "1"

    rows = store.query(
        date_from=date_from.isoformat(timespec="seconds"),
        date_to=date_to.isoformat(timespec="seconds"),
        statuses=["confirmed", "attended"],
        saved_only=saved_only,
    )
    if active_categories:
        rows = [r for r in rows if r["category"] in active_categories]

    groups = []
    last_day = None
    for row in sorted(rows, key=lambda r: r["start_dt"]):
        day_key = row["start_dt"][:10]
        if day_key != last_day:
            groups.append({"date": row["start_dt"][:10], "events": []})
            last_day = day_key
        groups[-1]["events"].append(row)

    return render_template(
        "calendar_agenda.html",
        groups=groups,
        range_choice=range_choice,
        categories=CATEGORIES,
        active_categories=set(active_categories or []),
        saved_only=saved_only,
    )


@bp.route("/event/<int:event_id>")
@login_required
def event_detail(event_id):
    store = get_store()
    row = store.get_by_id(event_id)
    if row is None:
        return render_template("not_found.html", kind="event"), 404
    return render_template("event_detail.html", event=row, categories=CATEGORIES)


def _redirect_back():
    next_url = request.form.get("next") or request.referrer or url_for("calendar.month_view")
    return redirect(next_url)


@bp.route("/event/<int:event_id>/save", methods=["POST"])
@login_required
def save_event(event_id):
    get_store().set_saved(event_id, True)
    return _redirect_back()


@bp.route("/event/<int:event_id>/unsave", methods=["POST"])
@login_required
def unsave_event(event_id):
    get_store().set_saved(event_id, False)
    return _redirect_back()


@bp.route("/event/<int:event_id>/attend", methods=["POST"])
@login_required
def attend_event(event_id):
    get_store().update_status(event_id, "attended")
    return _redirect_back()


@bp.route("/event/<int:event_id>/unattend", methods=["POST"])
@login_required
def unattend_event(event_id):
    get_store().update_status(event_id, "confirmed")
    return _redirect_back()


@bp.route("/event/<int:event_id>/recategorize", methods=["POST"])
@login_required
def recategorize_event(event_id):
    category = request.form.get("category")
    if category:
        get_store().set_user_category(event_id, category)
    return _redirect_back()


@bp.route("/event/<int:event_id>/notes", methods=["POST"])
@login_required
def set_notes(event_id):
    notes = request.form.get("notes", "")
    get_store().set_user_notes(event_id, notes)
    return _redirect_back()
