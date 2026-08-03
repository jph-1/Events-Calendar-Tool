"""Command-line entry point for events_tool.

Run `python -m events_tool.cli --help` (or use the `events` wrapper script)
to see the full command surface. See README.md for a walkthrough.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from events_tool import config as config_mod
from events_tool import db as db_mod
from events_tool import places as places_mod
from events_tool.digest import render_coverage_text, render_html, render_markdown
from events_tool.ics_export import build_calendar
from events_tool.ingestion.ics_rss_adapter import IcsRssAdapter
from events_tool.ingestion.manual_adapter import build_candidate
from events_tool.ingestion.newsletter_adapter import (
    build_extraction_prompt,
    heuristic_extract,
    parse_structured_response,
)
from events_tool.matching import score_candidate
from events_tool.models import CATEGORIES, IngestionRun, Place
from events_tool.query import parse_query
from events_tool.roundup import mark_included, select_roundup
from events_tool.store import EventStore


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _get_store() -> EventStore:
    return EventStore(db_mod.get_connection())


def _print_event_row(row, show_status: bool = True) -> None:
    when = row["start_dt"]
    where = f" @ {row['location_name']}" if row["location_name"] else ""
    neighborhood = f" [{row['neighborhood']}]" if row["neighborhood"] else ""
    status = f" ({row['status']})" if show_status else ""
    saved = " ★" if row["saved"] else ""
    override = " (recategorized)" if row["user_category"] else ""
    print(
        f"  #{row['id']} {when}{status}{saved} — {row['title']} "
        f"[{row['category']}{override}] [{row['verification']}]{where}{neighborhood}"
    )
    if row["url"]:
        print(f"      {row['url']}")
    if row["user_notes"]:
        print(f"      note: {row['user_notes']}")


# -- command handlers -----------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else config_mod.DEFAULT_PROFILE_PATH
    try:
        config_mod.init_profile(city=args.city, state=args.state, path=path, force=args.force)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Created profile for {args.city}, {args.state} at {path}")
    print("Edit it directly, or use `events interest add` / `events source add` to customize.")
    return 0


def cmd_interest(args: argparse.Namespace) -> int:
    profile = config_mod.load_profile()
    if args.interest_action == "add":
        if args.category not in CATEGORIES:
            print(f"warning: '{args.category}' is not one of the standard categories ({', '.join(CATEGORIES)})", file=sys.stderr)
        config_mod.add_interest(profile, args.keyword, args.category, args.weight)
        config_mod.save_profile(profile)
        print(f"Added interest: {args.keyword} -> {args.category} (weight {args.weight})")
    elif args.interest_action == "remove":
        removed = config_mod.remove_interest(profile, args.keyword)
        config_mod.save_profile(profile)
        print("Removed." if removed else f"No interest matching '{args.keyword}' found.")
    elif args.interest_action == "list":
        for i in profile.interests:
            flag = "" if i.active else " (inactive)"
            print(f"  {i.keyword} -> {i.category} (weight {i.weight}){flag}")
    return 0


def cmd_source(args: argparse.Namespace) -> int:
    profile = config_mod.load_profile()
    if args.source_action == "add":
        config_mod.add_source(profile, args.name, args.type, args.url, enabled=not args.disabled)
        config_mod.save_profile(profile)
        print(f"Added source: {args.name} ({args.type}) -> {args.url}")
    elif args.source_action == "remove":
        removed = config_mod.remove_source(profile, args.name)
        config_mod.save_profile(profile)
        print("Removed." if removed else f"No source named '{args.name}' found.")
    elif args.source_action == "list":
        for s in profile.sources:
            flag = "enabled" if s.enabled else "disabled"
            print(f"  {s.name} [{s.type}, {flag}] -> {s.url}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    profile = config_mod.load_profile()
    store = _get_store()

    if args.source:
        sources = [s for s in profile.sources if s.name == args.source]
        if not sources:
            print(f"error: no source named '{args.source}'", file=sys.stderr)
            return 1
    else:
        sources = [s for s in profile.sources if s.enabled]

    total_found = total_added = total_deduped = 0
    for source in sources:
        if source.type not in ("ical", "rss"):
            print(f"skipping {source.name}: type '{source.type}' has no automated adapter (use ingest-text, add-event, or check it manually)")
            continue
        adapter = IcsRssAdapter(name=source.name, url=source.url)
        try:
            candidates = adapter.fetch()
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, run continues
            print(f"error fetching {source.name}: {exc}", file=sys.stderr)
            store.log_ingestion_run(
                IngestionRun(None, source.name, _now_iso(), 0, 0, 0, "error", str(exc))
            )
            continue

        found = len(candidates)
        added = deduped = 0
        for candidate in candidates:
            match = score_candidate(candidate, profile.interests)
            if not match.matched:
                continue
            status = "confirmed" if args.auto_confirm else "candidate"
            _, was_new = store.insert_candidate(
                candidate,
                match.category,
                profile.location.city,
                profile.location.state,
                status=status,
                verification="automated-source",
            )
            if was_new:
                added += 1
            else:
                deduped += 1

        store.log_ingestion_run(
            IngestionRun(None, source.name, _now_iso(), found, added, deduped, "ok")
        )
        print(f"{source.name}: {found} found, {added} added, {deduped} already known")
        total_found += found
        total_added += added
        total_deduped += deduped

    print(f"Total: {total_found} found, {total_added} added, {total_deduped} deduped")
    return 0


def cmd_extract_prompt(args: argparse.Namespace) -> int:
    profile = config_mod.load_profile()
    text = Path(args.file).read_text(encoding="utf-8")
    prompt = build_extraction_prompt(text, profile.interests)
    if args.out:
        Path(args.out).write_text(prompt, encoding="utf-8")
        print(f"Wrote prompt to {args.out}. Paste its contents into an LLM chat, then save the reply as JSON.")
    else:
        print(prompt)
    return 0


def cmd_ingest_text(args: argparse.Namespace) -> int:
    profile = config_mod.load_profile()
    store = _get_store()

    if args.structured:
        json_text = Path(args.structured).read_text(encoding="utf-8")
        candidates = parse_structured_response(json_text)
        source_name = "newsletter-structured"
        verification = "user-lead-structured"
    else:
        text = Path(args.file).read_text(encoding="utf-8")
        candidates = heuristic_extract(text)
        source_name = "newsletter-heuristic"
        verification = "user-lead-heuristic"

    found = len(candidates)
    added = deduped = 0
    for candidate in candidates:
        match = score_candidate(candidate, profile.interests)
        if not match.matched and not args.structured:
            # Heuristic path has no keyword filter of its own; require an interest match.
            continue
        category = match.category if match.matched else "other"
        status = "confirmed" if args.auto_confirm else "candidate"
        _, was_new = store.insert_candidate(
            candidate,
            category,
            profile.location.city,
            profile.location.state,
            status=status,
            verification=verification,
        )
        if was_new:
            added += 1
        else:
            deduped += 1

    store.log_ingestion_run(IngestionRun(None, source_name, _now_iso(), found, added, deduped, "ok"))
    print(f"{source_name}: {found} extracted, {added} added, {deduped} already known")
    print("Reminder: these are user-provided leads, not independently verified — review before relying on them.")
    return 0


def cmd_add_event(args: argparse.Namespace) -> int:
    profile = config_mod.load_profile()
    store = _get_store()
    candidate = build_candidate(
        title=args.title,
        start_dt=args.start,
        end_dt=args.end or "",
        description=args.description or "",
        location_name=args.location or "",
        address=args.address or "",
        neighborhood=args.neighborhood or "",
        url=args.url or "",
    )
    event_id, was_new = store.insert_candidate(
        candidate,
        args.category,
        profile.location.city,
        profile.location.state,
        status="confirmed",
        verification="user-manual",
    )
    print(f"{'Added' if was_new else 'Already tracked as'} event #{event_id}: {args.title}")
    return 0


def cmd_log_attended(args: argparse.Namespace) -> int:
    profile = config_mod.load_profile()
    store = _get_store()
    candidate = build_candidate(
        title=args.title,
        start_dt=args.date,
        description=args.notes or "",
        location_name=args.location or "",
    )
    event_id, was_new = store.insert_candidate(
        candidate,
        args.category or "other",
        profile.location.city,
        profile.location.state,
        status="attended",
        verification="user-manual",
    )
    print(f"{'Logged' if was_new else 'Already logged'} attended event #{event_id}: {args.title}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    store = _get_store()
    pending = store.pending_review()
    if not pending:
        print("No pending candidates to review.")
        return 0
    for row in pending:
        _print_event_row(row)
        answer = input("  confirm / reject / skip? [c/r/s]: ").strip().lower()
        if answer.startswith("c"):
            store.update_status(row["id"], "confirmed")
            print("  -> confirmed")
        elif answer.startswith("r"):
            store.update_status(row["id"], "rejected")
            print("  -> rejected")
        else:
            print("  -> skipped")
    return 0


def cmd_recategorize(args: argparse.Namespace) -> int:
    store = _get_store()
    row = store.get_by_id(args.event_id)
    if not row:
        print(f"error: no event #{args.event_id}", file=sys.stderr)
        return 1
    if args.category not in CATEGORIES:
        print(f"warning: '{args.category}' is not one of the standard categories ({', '.join(CATEGORIES)})", file=sys.stderr)
    store.set_user_category(args.event_id, args.category)
    print(
        f"Recategorized #{args.event_id} '{row['title']}': {row['source_category']} -> {args.category} "
        f"(personal override; the original source category is kept for reference)"
    )
    return 0


def cmd_save(args: argparse.Namespace) -> int:
    store = _get_store()
    row = store.get_by_id(args.event_id)
    if not row:
        print(f"error: no event #{args.event_id}", file=sys.stderr)
        return 1
    store.set_saved(args.event_id, True)
    print(f"Saved #{args.event_id}: {row['title']}")
    return 0


def cmd_unsave(args: argparse.Namespace) -> int:
    store = _get_store()
    row = store.get_by_id(args.event_id)
    if not row:
        print(f"error: no event #{args.event_id}", file=sys.stderr)
        return 1
    store.set_saved(args.event_id, False)
    print(f"Unsaved #{args.event_id}: {row['title']}")
    return 0


def cmd_attend(args: argparse.Namespace) -> int:
    store = _get_store()
    row = store.get_by_id(args.event_id)
    if not row:
        print(f"error: no event #{args.event_id}", file=sys.stderr)
        return 1
    store.update_status(args.event_id, "attended")
    print(f"Marked #{args.event_id} as attended: {row['title']}")
    return 0


def cmd_unattend(args: argparse.Namespace) -> int:
    store = _get_store()
    row = store.get_by_id(args.event_id)
    if not row:
        print(f"error: no event #{args.event_id}", file=sys.stderr)
        return 1
    if row["status"] != "attended":
        print(f"#{args.event_id} is not marked attended (status: {row['status']}); nothing to reverse.", file=sys.stderr)
        return 1
    store.update_status(args.event_id, "confirmed")
    print(f"Reversed attendance for #{args.event_id}: {row['title']} (back to confirmed)")
    return 0


def cmd_log_experience(args: argparse.Namespace) -> int:
    store = _get_store()
    row = store.get_by_id(args.event_id)
    if not row:
        print(f"error: no event #{args.event_id}", file=sys.stderr)
        return 1
    store.set_user_notes(args.event_id, args.notes)
    print(f"Logged your notes on #{args.event_id}: {row['title']}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    if getattr(args, "use_device_location", False):
        print(
            "'find events near me' via device location services is planned for a future "
            "release (it will ask you to confirm location access each time you use it). "
            "For now, use --near <area name> instead.",
            file=sys.stderr,
        )
        return 2
    profile = config_mod.load_profile()
    store = _get_store()
    parsed = parse_query(args.text, profile.interests, near=args.near)

    rows = store.query(
        category=parsed.category,
        near=None if parsed.near_unlimited else parsed.near,
        keyword=parsed.keywords[0] if parsed.keywords and not parsed.category else None,
        date_from=parsed.date_from,
        date_to=parsed.date_to,
        statuses=["confirmed", "attended"],
    )

    if not rows:
        print(f"No matching events found for: \"{args.text}\"")
        if parsed.category:
            print(f"(searched category: {parsed.category})")
        return 0

    print(f"Found {len(rows)} event(s) for: \"{args.text}\"")
    for row in rows:
        _print_event_row(row, show_status=False)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store = _get_store()
    rows = store.query(
        category=args.category,
        near=args.near,
        date_from=args.date_from,
        date_to=args.date_to,
        status=args.status,
        saved_only=args.saved,
    )
    if not rows:
        print("No events match those filters.")
        return 0
    for row in rows:
        _print_event_row(row)
    return 0


def cmd_roundup(args: argparse.Namespace) -> int:
    store = _get_store()
    profile = config_mod.load_profile()
    grouped = select_roundup(store, days=args.days)

    if args.export == "md":
        content = render_markdown(grouped)
    elif args.export == "html":
        content = render_html(grouped)
    else:
        content = None

    if content is not None:
        out_path = Path(args.out) if args.out else Path(f"roundup.{args.export}")
        out_path.write_text(content, encoding="utf-8")
        print(f"Wrote {args.export} digest to {out_path}")
    elif args.export == "ics":
        all_rows = [row for rows in grouped.values() for row in rows]
        calendar_text = build_calendar(all_rows)
        out_path = Path(args.out) if args.out else Path("roundup.ics")
        out_path.write_text(calendar_text, encoding="utf-8")
        print(f"Wrote ICS calendar to {out_path}")
    else:
        print(render_markdown(grouped))

    if not args.no_mark_included:
        mark_included(store, grouped)

    print()
    print(render_coverage_text(store, profile, window_days=args.days))
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    profile = config_mod.load_profile()
    store = _get_store()
    counts = store.category_counts()
    automated_counts = store.category_counts(verification="automated-source")
    last_runs = store.last_ingestion_by_source()
    has_enabled_automated_source = any(s.enabled and s.type in ("ical", "rss") for s in profile.sources)

    print(f"Coverage report for {profile.location.city}, {profile.location.state}")
    print()
    print("Sources:")
    for s in profile.sources:
        run = last_runs.get(s.name)
        if s.type in ("ical", "rss"):
            kind = "automated" if s.enabled else "automated (disabled)"
        elif s.type == "lead":
            kind = "lead-only (manual check needed)"
        else:
            kind = "reference (manual/newsletter intake)"
        last = f", last run {run['last_run_at']}" if run else ", never run"
        print(f"  {s.name} [{s.type}] -> {kind}{last}")

    print()
    print("Categories:")
    for category in CATEGORIES:
        n = counts.get(category, 0)
        n_automated = automated_counts.get(category, 0)
        has_interest = any(i.category == category and i.active for i in profile.interests)
        if not has_interest and n == 0:
            continue
        if n_automated > 0:
            coverage = f"automated coverage confirmed ({n_automated} event(s) seen from a real feed)"
        elif has_enabled_automated_source:
            coverage = "an automated source is enabled, but hasn't surfaced any events in this category yet"
        elif n > 0:
            coverage = "reference-only (from manual/newsletter entries, no live source)"
        else:
            coverage = "NO COVERAGE YET — no source and no events; add a source or events manually"
        print(f"  {category}: {n} event(s) — {coverage}")

    return 0


def cmd_places_import(args: argparse.Namespace) -> int:
    store = _get_store()
    text = Path(args.file).read_text(encoding="utf-8")
    file_format = args.format or ("kml" if args.file.lower().endswith(".kml") else "csv")
    raw_places = places_mod.parse_places_file(text, file_format)

    now = _now_iso()
    added = 0
    for rp in raw_places:
        store.insert_place(
            Place(
                id=None,
                name=rp.name,
                address=rp.address,
                lat=rp.lat,
                lon=rp.lon,
                tags=rp.tags,
                url=rp.url,
                list_name=args.name,
                source=file_format,
                imported_at=now,
            )
        )
        added += 1
    print(f"Imported {added} place(s) into list '{args.name}'")
    return 0


def cmd_places_list(args: argparse.Namespace) -> int:
    store = _get_store()
    rows = store.places(list_name=args.list)
    if not rows:
        print("No places imported yet. Use `events places import`.")
        return 0
    for row in rows:
        coords = f" ({row['lat']}, {row['lon']})" if row["lat"] is not None else ""
        tags = f" [{row['tags']}]" if row["tags"] else ""
        print(f"  [{row['list_name']}] {row['name']}{coords} — {row['address']}{tags}")
        if row["url"]:
            print(f"      {row['url']}")
    return 0


def cmd_export_json(args: argparse.Namespace) -> int:
    store = _get_store()
    rows = store.query(status=args.status) if args.status else store.query(statuses=["confirmed", "attended"])
    events = [dict(row) for row in rows]
    Path(args.out).write_text(json.dumps(events, indent=2), encoding="utf-8")
    print(f"Wrote {len(events)} events to {args.out}")
    return 0


def cmd_export_snapshot(args: argparse.Namespace) -> int:
    """Bundle events + a coverage summary into one JSON file, for the
    read-only calendar prototype view (Artifact). Distinct from export-json,
    which is a plain events dump."""
    store = _get_store()
    profile = config_mod.load_profile()

    rows = store.query(statuses=["confirmed", "attended"])
    events = [dict(row) for row in rows]

    counts = store.category_counts()
    automated_counts = store.category_counts(verification="automated-source")
    last_runs = store.last_ingestion_by_source()
    has_enabled_automated_source = any(s.enabled and s.type in ("ical", "rss") for s in profile.sources)

    categories = []
    for category in CATEGORIES:
        n = counts.get(category, 0)
        n_automated = automated_counts.get(category, 0)
        has_interest = any(i.category == category and i.active for i in profile.interests)
        if not has_interest and n == 0:
            continue
        if n_automated > 0:
            coverage = "automated"
        elif has_enabled_automated_source:
            coverage = "automated-source-enabled-no-hits"
        elif n > 0:
            coverage = "reference-only"
        else:
            coverage = "none"
        categories.append({"category": category, "count": n, "coverage": coverage})

    sources = []
    for s in profile.sources:
        run = last_runs.get(s.name)
        sources.append(
            {
                "name": s.name,
                "type": s.type,
                "enabled": s.enabled,
                "url": s.url,
                "notes": s.notes,
                "last_run_at": run["last_run_at"] if run else None,
                "last_run_status": run["status"] if run else None,
            }
        )

    snapshot = {
        "generated_at": _now_iso(),
        "location": {"city": profile.location.city, "state": profile.location.state},
        "events": events,
        "categories": categories,
        "sources": sources,
    }
    Path(args.out).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"Wrote snapshot ({len(events)} events) to {args.out}")
    return 0


def cmd_export_ics(args: argparse.Namespace) -> int:
    store = _get_store()
    statuses = ["confirmed", "attended"] if not args.all else None
    rows = store.query(statuses=statuses) if statuses else store.query()
    calendar_text = build_calendar(rows)
    Path(args.out).write_text(calendar_text, encoding="utf-8")
    print(f"Wrote {len(rows)} events to {args.out}")
    return 0


# -- argument parser -------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="events", description="Personal, source-agnostic events discovery and calendar tool.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a new profile (seeded from the Houston example).")
    p_init.add_argument("--city", default="Houston")
    p_init.add_argument("--state", default="TX")
    p_init.add_argument("--path", default=None)
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_interest = sub.add_parser("interest", help="Manage your interest keywords/categories.")
    interest_sub = p_interest.add_subparsers(dest="interest_action", required=True)
    p_int_add = interest_sub.add_parser("add")
    p_int_add.add_argument("keyword")
    p_int_add.add_argument("--category", required=True)
    p_int_add.add_argument("--weight", type=float, default=1.0)
    p_int_add.set_defaults(func=cmd_interest)
    p_int_rm = interest_sub.add_parser("remove")
    p_int_rm.add_argument("keyword")
    p_int_rm.set_defaults(func=cmd_interest)
    p_int_list = interest_sub.add_parser("list")
    p_int_list.set_defaults(func=cmd_interest)

    p_source = sub.add_parser("source", help="Manage ingestion sources (RSS/iCal feeds, or manual 'leads').")
    source_sub = p_source.add_subparsers(dest="source_action", required=True)
    p_src_add = source_sub.add_parser("add")
    p_src_add.add_argument("--name", required=True)
    p_src_add.add_argument("--type", required=True, choices=["rss", "ical", "manual", "newsletter", "lead"])
    p_src_add.add_argument("--url", default="")
    p_src_add.add_argument("--disabled", action="store_true")
    p_src_add.set_defaults(func=cmd_source)
    p_src_rm = source_sub.add_parser("remove")
    p_src_rm.add_argument("--name", required=True)
    p_src_rm.set_defaults(func=cmd_source)
    p_src_list = source_sub.add_parser("list")
    p_src_list.set_defaults(func=cmd_source)

    p_ingest = sub.add_parser("ingest", help="Fetch configured RSS/iCal sources and add matching events as candidates.")
    p_ingest.add_argument("--source", default=None, help="Ingest only this source (by name); default: all enabled sources.")
    p_ingest.add_argument("--auto-confirm", action="store_true", help="Skip the review queue; insert matches as confirmed.")
    p_ingest.set_defaults(func=cmd_ingest)

    p_prompt = sub.add_parser("extract-prompt", help="Render an LLM extraction prompt for a pasted newsletter file.")
    p_prompt.add_argument("--file", required=True)
    p_prompt.add_argument("--out", default=None)
    p_prompt.set_defaults(func=cmd_extract_prompt)

    p_ingest_text = sub.add_parser("ingest-text", help="Import events from a newsletter: structured LLM JSON or heuristic fallback.")
    group = p_ingest_text.add_mutually_exclusive_group(required=True)
    group.add_argument("--structured", help="Path to structured JSON (from extract-prompt's LLM reply).")
    group.add_argument("--heuristic", action="store_true", help="Use the regex-only fallback extractor.")
    p_ingest_text.add_argument("--file", help="Newsletter text file (required with --heuristic).")
    p_ingest_text.add_argument("--auto-confirm", action="store_true")
    p_ingest_text.set_defaults(func=cmd_ingest_text)

    p_add_event = sub.add_parser("add-event", help="Manually add an event you already know about.")
    p_add_event.add_argument("--title", required=True)
    p_add_event.add_argument("--start", required=True, help="ISO 8601, e.g. 2026-08-15T19:00:00")
    p_add_event.add_argument("--end", default=None)
    p_add_event.add_argument("--category", required=True)
    p_add_event.add_argument("--description", default=None)
    p_add_event.add_argument("--location", default=None)
    p_add_event.add_argument("--address", default=None)
    p_add_event.add_argument("--neighborhood", default=None)
    p_add_event.add_argument("--url", default=None)
    p_add_event.set_defaults(func=cmd_add_event)

    p_log = sub.add_parser("log-attended", help="Log an event you already attended.")
    p_log.add_argument("--title", required=True)
    p_log.add_argument("--date", required=True, help="ISO 8601 date/time")
    p_log.add_argument("--category", default=None)
    p_log.add_argument("--location", default=None)
    p_log.add_argument("--notes", default=None)
    p_log.set_defaults(func=cmd_log_attended)

    p_review = sub.add_parser("review", help="Interactively confirm/reject pending candidate events.")
    p_review.set_defaults(func=cmd_review)

    p_recat = sub.add_parser("recategorize", help="Correct an event's category without altering the ingested source fact.")
    p_recat.add_argument("event_id", type=int)
    p_recat.add_argument("--category", required=True)
    p_recat.set_defaults(func=cmd_recategorize)

    p_save = sub.add_parser("save", help="Bookmark an event.")
    p_save.add_argument("event_id", type=int)
    p_save.set_defaults(func=cmd_save)

    p_unsave = sub.add_parser("unsave", help="Remove a bookmark.")
    p_unsave.add_argument("event_id", type=int)
    p_unsave.set_defaults(func=cmd_unsave)

    p_attend = sub.add_parser("attend", help="Mark an event as attended.")
    p_attend.add_argument("event_id", type=int)
    p_attend.set_defaults(func=cmd_attend)

    p_unattend = sub.add_parser("unattend", help="Reverse an attendance mark (back to confirmed).")
    p_unattend.add_argument("event_id", type=int)
    p_unattend.set_defaults(func=cmd_unattend)

    p_log_exp = sub.add_parser("log-experience", help="Attach your own notes to an event, separate from its source description.")
    p_log_exp.add_argument("event_id", type=int)
    p_log_exp.add_argument("--notes", required=True)
    p_log_exp.set_defaults(func=cmd_log_experience)

    p_query = sub.add_parser("query", help='Ask for events in plain language, e.g. "salsa dancing tonight".')
    p_query.add_argument("text")
    p_query.add_argument("--near", default=None, help='Neighborhood/area filter, or "no limit" for unlimited radius.')
    p_query.add_argument(
        "--use-device-location",
        action="store_true",
        help="Reserved for a future release: 'find events near me' via device location services, "
        "with a confirmation prompt every time it's used. Not implemented yet.",
    )
    p_query.set_defaults(func=cmd_query)

    p_show = sub.add_parser("show", help="List events with structured filters.")
    p_show.add_argument("--category", default=None)
    p_show.add_argument("--near", default=None)
    p_show.add_argument("--from", dest="date_from", default=None)
    p_show.add_argument("--to", dest="date_to", default=None)
    p_show.add_argument("--status", default=None, choices=["candidate", "confirmed", "attended", "rejected"])
    p_show.add_argument("--saved", action="store_true", help="Only show bookmarked events.")
    p_show.set_defaults(func=cmd_show)

    p_roundup = sub.add_parser("roundup", help="Generate the weekly activities roundup, with a coverage disclosure.")
    p_roundup.add_argument("--days", type=int, default=7)
    p_roundup.add_argument("--export", choices=["md", "html", "ics"], default=None)
    p_roundup.add_argument("--out", default=None)
    p_roundup.add_argument("--no-mark-included", action="store_true", help="Don't mark these events as already-roundup'd.")
    p_roundup.set_defaults(func=cmd_roundup)

    p_coverage = sub.add_parser("coverage", help="Show what's automated, reference-only, lead-only, or uncovered, by category.")
    p_coverage.set_defaults(func=cmd_coverage)

    p_places = sub.add_parser("places", help="Manage your imported 'preferred places' lists (e.g. from Google Maps).")
    places_sub = p_places.add_subparsers(dest="places_action", required=True)
    p_places_import = places_sub.add_parser("import", help="Import a KML (Google My Maps export) or CSV places list.")
    p_places_import.add_argument("--file", required=True)
    p_places_import.add_argument("--name", required=True, help="A label for this list, e.g. 'Favorite Galleries'.")
    p_places_import.add_argument("--format", choices=["kml", "csv"], default=None, help="Defaults to inferring from the file extension.")
    p_places_import.set_defaults(func=cmd_places_import)
    p_places_list = places_sub.add_parser("list")
    p_places_list.add_argument("--list", dest="list", default=None, help="Filter to one imported list by name.")
    p_places_list.set_defaults(func=cmd_places_list)

    p_export_json = sub.add_parser("export-json", help="Export events as JSON (e.g. for the calendar prototype view).")
    p_export_json.add_argument("--out", required=True)
    p_export_json.add_argument("--status", default=None, choices=["candidate", "confirmed", "attended", "rejected"])
    p_export_json.set_defaults(func=cmd_export_json)

    p_export_snapshot = sub.add_parser("export-snapshot", help="Bundle events + coverage summary as JSON for the calendar prototype view.")
    p_export_snapshot.add_argument("--out", required=True)
    p_export_snapshot.set_defaults(func=cmd_export_snapshot)

    p_export = sub.add_parser("export-ics", help="Export events to an .ics file for import into any calendar app.")
    p_export.add_argument("--out", required=True)
    p_export.add_argument("--all", action="store_true", help="Include candidate/rejected events too (default: confirmed+attended only).")
    p_export.set_defaults(func=cmd_export_ics)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest-text" and args.heuristic and not args.file:
        parser.error("--heuristic requires --file")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
