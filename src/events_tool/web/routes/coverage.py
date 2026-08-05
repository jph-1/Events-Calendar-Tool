"""Coverage dashboard — same honest-transparency logic as `events coverage`
on the CLI, just rendered as a page instead of printed text."""
from __future__ import annotations

from flask import Blueprint, render_template

from events_tool.models import CATEGORIES
from events_tool.web import get_profile, get_store
from events_tool.web.auth import login_required

bp = Blueprint("coverage", __name__, url_prefix="/coverage")


@bp.route("/")
@login_required
def coverage_view():
    profile = get_profile()
    store = get_store()

    counts = store.category_counts()
    automated_counts = store.category_counts(verification="automated-source")
    researched_counts = store.category_counts(verification="assistant-researched")
    last_runs = store.last_ingestion_by_source()
    has_enabled_automated_source = any(s.enabled and s.type in ("ical", "rss") for s in profile.sources)

    categories = []
    for category in CATEGORIES:
        n = counts.get(category, 0)
        n_automated = automated_counts.get(category, 0)
        n_researched = researched_counts.get(category, 0)
        has_interest = any(i.category == category and i.active for i in profile.interests)
        if not has_interest and n == 0:
            continue
        if n_automated > 0:
            state, label = "automated", f"Automated coverage confirmed — {n_automated} event(s) seen from a real feed"
        elif has_enabled_automated_source:
            state, label = "partial", "An automated source is enabled, but hasn't surfaced anything here yet"
        elif n_researched > 0:
            state, label = "researched", f"{n_researched} event(s) from web search — unverified, review before relying on them"
        elif n > 0:
            state, label = "reference", "Reference-only, from manual/newsletter entries"
        else:
            state, label = "none", "No coverage yet"
        categories.append({"category": category, "count": n, "state": state, "label": label})

    sources = []
    for s in profile.sources:
        run = last_runs.get(s.name)
        if s.type in ("ical", "rss"):
            kind = "automated" if s.enabled else "automated (disabled)"
        elif s.type == "lead":
            kind = "lead-only"
        else:
            kind = "reference"
        sources.append({"name": s.name, "type": s.type, "kind": kind, "last_run": run["last_run_at"] if run else None, "last_status": run["status"] if run else None})

    return render_template("coverage.html", categories=categories, sources=sources, location=profile.location)
