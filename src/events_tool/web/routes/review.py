from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from events_tool.web import get_store
from events_tool.web.auth import login_required

bp = Blueprint("review", __name__, url_prefix="/review")


@bp.route("/")
@login_required
def review_list():
    store = get_store()
    pending = store.pending_review()
    return render_template("review.html", pending=pending)


@bp.route("/<int:event_id>/confirm", methods=["POST"])
@login_required
def confirm(event_id):
    store = get_store()
    row = store.get_by_id(event_id)
    if row is None:
        flash("That event no longer exists.", "error")
        return redirect(url_for("review.review_list"))
    store.update_status(event_id, "confirmed")
    notes = request.form.get("notes", "").strip()
    if notes:
        store.set_user_notes(event_id, notes)
    flash(f"Confirmed: {row['title']}", "success")
    return redirect(url_for("review.review_list"))


@bp.route("/<int:event_id>/reject", methods=["POST"])
@login_required
def reject(event_id):
    store = get_store()
    row = store.get_by_id(event_id)
    if row is None:
        flash("That event no longer exists.", "error")
        return redirect(url_for("review.review_list"))
    store.update_status(event_id, "rejected")
    reason = request.form.get("reason", "").strip()
    if reason:
        store.set_user_notes(event_id, reason)
    flash(f"Rejected: {row['title']}" + (f" ({reason})" if reason else ""), "success")
    return redirect(url_for("review.review_list"))
