"""Render a roundup (category -> list of event rows) as Markdown or HTML.

Plain f-string templates — no Jinja dependency, matching the rest of the
tool's zero-runtime-dependency goal.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def _format_when(start_dt: str) -> str:
    try:
        dt = datetime.fromisoformat(start_dt)
        date_part = f"{dt.strftime('%a %b')} {dt.day}"
        if dt.hour or dt.minute:
            return f"{date_part}, {dt.strftime('%I:%M %p').lstrip('0')}"
        return date_part
    except ValueError:
        return start_dt


def render_markdown(grouped: dict[str, list], title: str = "Weekly Activities Roundup") -> str:
    lines = [f"# {title}", ""]
    if not grouped:
        lines.append("No newly confirmed events in this window.")
        return "\n".join(lines) + "\n"

    for category in sorted(grouped.keys()):
        lines.append(f"## {category.title()}")
        lines.append("")
        for row in grouped[category]:
            when = _format_when(row["start_dt"])
            where = f" — {row['location_name']}" if row["location_name"] else ""
            lines.append(f"- **{row['title']}** ({when}){where}")
            if row["url"]:
                lines.append(f"  {row['url']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(grouped: dict[str, list], title: str = "Weekly Activities Roundup") -> str:
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'>",
        f"<title>{title}</title>",
        "</head><body>",
        f"<h1>{title}</h1>",
    ]
    if not grouped:
        parts.append("<p>No newly confirmed events in this window.</p>")
    else:
        for category in sorted(grouped.keys()):
            parts.append(f"<h2>{category.title()}</h2><ul>")
            for row in grouped[category]:
                when = _format_when(row["start_dt"])
                where = f" &mdash; {row['location_name']}" if row["location_name"] else ""
                link = f" <a href='{row['url']}'>details</a>" if row["url"] else ""
                parts.append(f"<li><strong>{row['title']}</strong> ({when}){where}{link}</li>")
            parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def render_coverage_text(store, profile, window_days: int = 7) -> str:
    """The 'what was checked, what was not' disclosure that must accompany
    any roundup or coverage view — this is the single source of truth for
    that disclosure so the CLI, the weekly Routine's report, and (later) the
    web app all say exactly the same thing about what's automated vs. a
    known-but-unchecked lead vs. reference-only.
    """
    since = (datetime.now() - timedelta(days=window_days)).isoformat(timespec="seconds")
    last_runs = store.last_ingestion_by_source()
    automated_sources = [s for s in profile.sources if s.type in ("ical", "rss")]
    lead_sources = [s for s in profile.sources if s.type == "lead"]

    lines = ["Coverage: what this roundup checked"]
    if automated_sources:
        for s in automated_sources:
            run = last_runs.get(s.name)
            if not s.enabled:
                lines.append(f"  {s.name}: disabled, not checked")
            elif run and run["last_run_at"] >= since:
                lines.append(f"  {s.name}: checked automatically (last run {run['last_run_at']}, status {run['status']})")
            elif run:
                lines.append(
                    f"  {s.name}: enabled, but last checked {run['last_run_at']} "
                    f"(older than this window — run `events ingest` again)"
                )
            else:
                lines.append(f"  {s.name}: enabled, but never checked yet — run `events ingest`")
    else:
        lines.append("  No automated (RSS/iCal) sources configured yet.")

    if lead_sources:
        lines.append("  Known leads NOT automatically checked (no working adapter yet):")
        for s in lead_sources:
            lines.append(f"    {s.name} -> {s.url or '(no url)'} — {s.notes or 'check manually'}")

    lines.append(
        "  This roundup contains only events from real ingested sources, your own manual "
        "entries, or newsletter text you supplied yourself — nothing here is invented."
    )
    return "\n".join(lines) + "\n"
