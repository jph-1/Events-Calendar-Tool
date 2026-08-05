"""Ask/search page: local-first, with a copy/paste live-search fallback.

The web app has the same no-runtime-search-capability constraint as the
CLI (see events_tool.ask's module docstring) — this route can't itself
call out to the web. When the local calendar has nothing, it renders the
research prompt for the user to run through any web-search-capable LLM,
and a form to paste the structured JSON reply back in.
"""
from __future__ import annotations

import json

from flask import Blueprint, flash, render_template, request

from events_tool.ask import RANGE_CHOICES, build_ask_prompt, parse_ask_response, resolve_range
from events_tool.query import parse_query
from events_tool.web import get_profile, get_store
from events_tool.web.auth import login_required

bp = Blueprint("ask", __name__, url_prefix="/ask")


@bp.route("/", methods=["GET"])
@login_required
def ask_view():
    text = request.args.get("text", "").strip()
    range_choice = request.args.get("range", "week")
    custom_from = request.args.get("from") or None
    custom_to = request.args.get("to") or None

    context = {"text": text, "range_choice": range_choice, "range_choices": RANGE_CHOICES, "custom_from": custom_from, "custom_to": custom_to}

    if not text:
        return render_template("ask.html", **context)

    profile = get_profile()
    store = get_store()

    try:
        date_from, date_to, range_label = resolve_range(range_choice, custom_from=custom_from, custom_to=custom_to)
    except ValueError as exc:
        flash(str(exc), "error")
        return render_template("ask.html", **context)

    parsed = parse_query(text, profile.interests, near=None)
    rows = store.query(
        category=parsed.category,
        keyword=parsed.keywords[0] if parsed.keywords and not parsed.category else None,
        date_from=date_from.isoformat(timespec="seconds"),
        date_to=date_to.isoformat(timespec="seconds"),
        statuses=["confirmed", "attended"],
    )

    if rows:
        context["results"] = rows
        context["range_label"] = range_label
        return render_template("ask.html", **context)

    prompt = build_ask_prompt(text, profile.location.city, profile.location.state, date_from, date_to, range_label)
    context["prompt"] = prompt
    context["range_label"] = range_label
    context["no_local_results"] = True
    return render_template("ask.html", **context)


@bp.route("/import", methods=["POST"])
@login_required
def ask_import():
    profile = get_profile()
    store = get_store()
    text = request.form.get("text", "ask")
    reply_json = request.form.get("reply_json", "")

    try:
        matches, suggestions, warnings = parse_ask_response(reply_json, source_name=f"ask-web:{text}")
    except (ValueError, json.JSONDecodeError) as exc:
        flash(f"Couldn't parse that as valid JSON: {exc}", "error")
        return render_template(
            "ask.html",
            text=text,
            range_choice=request.form.get("range", "week"),
            range_choices=RANGE_CHOICES,
            no_local_results=True,
            prompt=request.form.get("prompt", ""),
        )

    added = 0
    for candidate, category in matches:
        _, was_new = store.insert_candidate(
            candidate, category, profile.location.city, profile.location.state,
            status="candidate", verification="assistant-researched",
        )
        if was_new:
            added += 1

    if added:
        flash(f"Added {added} match(es) to your review queue.", "success")
    if warnings:
        flash(f"{len(warnings)} entries skipped (missing title/date/url).", "warning")

    return render_template(
        "ask.html",
        text=text,
        range_choice=request.form.get("range", "week"),
        range_choices=RANGE_CHOICES,
        suggestions=suggestions,
        matches_added=added,
    )


@bp.route("/add-suggestion", methods=["POST"])
@login_required
def add_suggestion():
    profile = get_profile()
    store = get_store()

    from events_tool.models import RawEventCandidate

    candidate = RawEventCandidate(
        title=request.form.get("title", ""),
        description=request.form.get("description", ""),
        start_dt=request.form.get("start_dt", ""),
        end_dt=request.form.get("end_dt") or None,
        location_name=request.form.get("location_name", ""),
        address=request.form.get("address", ""),
        neighborhood=request.form.get("neighborhood", ""),
        url=request.form.get("url", ""),
        source_name="ask-web:suggestion",
        source_type="assistant-research",
    )
    category = request.form.get("category", "other")
    event_id, was_new = store.insert_candidate(
        candidate, category, profile.location.city, profile.location.state,
        status="candidate", verification="assistant-researched",
    )
    flash(f"Added '{candidate.title}' to your review queue." if was_new else f"'{candidate.title}' was already in your calendar.", "success")
    return render_template("ask.html", text="", range_choice="week", range_choices=RANGE_CHOICES)
