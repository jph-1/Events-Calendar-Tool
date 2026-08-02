"""Render a roundup (category -> list of event rows) as Markdown or HTML.

Plain f-string templates — no Jinja dependency, matching the rest of the
tool's zero-runtime-dependency goal.
"""
from __future__ import annotations

from datetime import datetime


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
