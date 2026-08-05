from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from events_tool import config as config_mod
from events_tool.models import CATEGORIES
from events_tool.users import get_user, regenerate_ics_token
from events_tool.web import get_store
from events_tool.web.auth import login_required

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/")
@login_required
def settings_view():
    profile = config_mod.load_profile()
    store = get_store()
    user = get_user(store.conn)
    ics_url = url_for("ics.feed", token=user.ics_token, _external=True) if user else None
    return render_template("settings.html", profile=profile, categories=CATEGORIES, ics_url=ics_url)


@bp.route("/interests/add", methods=["POST"])
@login_required
def add_interest():
    profile = config_mod.load_profile()
    keyword = request.form.get("keyword", "").strip()
    category = request.form.get("category", "other")
    weight = request.form.get("weight", "1.0")
    if keyword:
        try:
            weight_f = float(weight)
        except ValueError:
            weight_f = 1.0
        config_mod.add_interest(profile, keyword, category, weight_f)
        config_mod.save_profile(profile)
        flash(f"Added interest: {keyword} → {category}", "success")
    return redirect(url_for("settings.settings_view"))


@bp.route("/interests/remove", methods=["POST"])
@login_required
def remove_interest():
    profile = config_mod.load_profile()
    keyword = request.form.get("keyword", "")
    if config_mod.remove_interest(profile, keyword):
        config_mod.save_profile(profile)
        flash(f"Removed interest: {keyword}", "success")
    return redirect(url_for("settings.settings_view"))


@bp.route("/sources/add", methods=["POST"])
@login_required
def add_source():
    profile = config_mod.load_profile()
    name = request.form.get("name", "").strip()
    source_type = request.form.get("type", "lead")
    url = request.form.get("url", "").strip()
    enabled = request.form.get("enabled") == "1"
    if name:
        config_mod.add_source(profile, name, source_type, url, enabled=enabled)
        config_mod.save_profile(profile)
        flash(f"Added source: {name} ({source_type})", "success")
    return redirect(url_for("settings.settings_view"))


@bp.route("/sources/remove", methods=["POST"])
@login_required
def remove_source():
    profile = config_mod.load_profile()
    name = request.form.get("name", "")
    if config_mod.remove_source(profile, name):
        config_mod.save_profile(profile)
        flash(f"Removed source: {name}", "success")
    return redirect(url_for("settings.settings_view"))


@bp.route("/ics-token/regenerate", methods=["POST"])
@login_required
def regenerate_token():
    store = get_store()
    user = get_user(store.conn)
    if user:
        regenerate_ics_token(store.conn, user.id)
        flash("Calendar subscription link regenerated — update it wherever you subscribed.", "success")
    return redirect(url_for("settings.settings_view"))
