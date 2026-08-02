# Events Calendar Tool

A personal, source-agnostic events discovery and calendar tool. It was built
around one problem: too many pages, groups, and newsletters to track for
things like art shows, indie film, local bands, salsa nights, gardening and
kettlebell clubs, book clubs/meetups, and maker-space workshops. It compiles
matching events into a personal calendar you curate over time, and it
answers ad-hoc questions like *"I want to salsa dance tonight"* or *"any new
art exhibitions near Montrose?"*

It ships seeded for Houston, TX, but city/state and the entire interest list
are just config — point it anywhere.

No paid APIs or accounts are required. It runs entirely on the Python
standard library (no `pip install` needed to use it).

## How it's put together

- **`config/profile.json`** — your hand-editable profile: location,
  interests (keyword → category), and ingestion sources. Seeded from
  `config/profile.example.json` (Houston defaults) by `events init`.
- **`data/events.db`** — a local SQLite database holding events and an
  ingestion audit log. Nothing leaves your machine.
- **Ingestion adapters** — pluggable sources that turn some feed/text into
  candidate events:
  - **RSS/iCal** (`events ingest`) — real, working, no API key. Many venues,
    galleries, and makerspaces publish a free iCal feed (WordPress's "The
    Events Calendar" plugin exposes one at `<site>/events/?ical=1`), and
    RSS/Atom is a near-universal announcement format.
  - **Manual** (`events add-event`, `events log-attended`) — type in
    something you already know about, or something you already attended.
  - **Newsletter paste** (`events extract-prompt` / `events ingest-text`) —
    see below.
  - **Future/roadmap** (`src/events_tool/ingestion/future_adapters.py`) —
    Eventbrite, Meetup, Ticketmaster, Instagram/Facebook Events. These
    require paid/authenticated APIs we don't have keys for; the classes are
    stubbed with a `NotImplementedError` documenting what each would need,
    and are not wired into the CLI.
- **Matching** — every ingested candidate is scored against your active
  interests (simple keyword matching, since your interest list *is* the
  curation mechanism); only matches are stored.
- **Review queue** — anything ingested automatically lands as a
  `candidate` by default (`events review` to confirm/reject), so noisy
  auto-ingestion doesn't silently pollute your calendar. Manual adds and
  attended-log entries go straight to `confirmed`/`attended`.
- **Query engine** — a lightweight phrase parser for ad-hoc questions
  (`events query`), plus a structured filter command (`events show`).
- **Weekly roundup** — `events roundup` selects newly-confirmed events in
  the next N days, grouped by category, and can render Markdown, HTML, or
  an `.ics` file.
- **ICS export** — `events export-ics` writes a hand-rolled, dependency-free
  RFC 5545 calendar file you can import into Google Calendar, Apple
  Calendar, Outlook, etc.

## Setup

Requires Python 3.9+. No dependencies to install for normal use.

```bash
cd Events-Calendar-Tool
export PYTHONPATH=src   # or: pip install -e . to get the `events` command

events init                          # seeds config/profile.json for Houston, TX
events init --city Austin --state TX # ...or any other city
```

(If you skip `pip install -e .`, run every command below as
`python -m events_tool.cli <command>` instead of `events <command>`.)

To run the test suite: `pip install -r requirements-dev.txt && pytest`.

## Customizing your interests and sources

Interests drive both what gets ingested and what ad-hoc queries can match
against. Edit `config/profile.json` directly, or:

```bash
events interest add "pottery class" --category maker --weight 0.8
events interest remove "meetup"
events interest list

events source add --name my-favorite-venue --type ical \
  --url "https://somevenue.example/events/?ical=1"
events source list
```

`future_flags.use_geolocation` and the reserved `--use-device-location` flag
on `events query` are placeholders for a **planned future release**: a
"find events near me" feature using device location services, with a
confirmation prompt every single time it's used. It is intentionally not
implemented yet — using it today prints a message and exits. For now, use
`--near <area name>` (e.g. `--near Montrose`) for location filtering.

## Weekly ingestion

```bash
events ingest --all              # fetch every enabled RSS/iCal source
events ingest --source my-favorite-venue
events review                    # walk pending candidates: confirm / reject / skip
```

Run `events ingest --all && events review` on whatever cadence you like —
weekly cron, a reminder, or just whenever a newsletter lands.

## Feeding in a newsletter you already subscribe to

Two paths, since the tool has no runtime LLM key of its own:

**LLM-assisted (better quality):**
```bash
events extract-prompt --file newsletter.txt --out prompt.txt
# paste prompt.txt into Claude (or any LLM chat), paste its JSON reply into response.json
events ingest-text --structured response.json
```

**Heuristic fallback (no LLM needed, lower precision):**
```bash
events ingest-text --heuristic --file newsletter.txt
```
This regex-extracts lines that contain both a recognizable date (e.g. "Aug
15" or "August 15, 2026") and a time (e.g. "7:00pm"), and only keeps ones
that match an active interest keyword. Always review these afterward.

## Logging something you already attended or already know about

```bash
events add-event --title "Salsa Night at The Continental Club" \
  --start 2026-08-05T20:00:00 --category dance \
  --location "Continental Club" --neighborhood Montrose \
  --url "https://example.org/salsa"

events log-attended --title "Indie Film Screening at 14 Pews" \
  --date 2026-07-20T19:00:00 --category film --location "14 Pews"
```

Logged/attended events feed the same calendar and inform your history —
useful context if you later want to notice patterns in what you actually go to.

## Ad-hoc queries

```bash
events query "I want to salsa dance tonight"
events query "gardening workshop" --near "no limit"
events query "any new art exhibitions" --near Montrose
```

`events show` gives structured filtering instead of phrase parsing:

```bash
events show --category art --near Montrose --from 2026-08-01 --to 2026-08-31
events show --status candidate   # same as `events review`, without the prompts
```

## Weekly roundup and calendar export

```bash
events roundup --days 7 --export md --out this_week.md
events roundup --days 7 --export html --out this_week.html
events roundup --days 7 --export ics --out this_week.ics
events export-ics --out full_calendar.ics   # all confirmed+attended events, any date
```

`roundup` marks the events it included so the next run doesn't repeat them;
pass `--no-mark-included` to preview without consuming the queue.

## Project layout

```
config/profile.example.json     Houston-seeded default profile
src/events_tool/
  cli.py                        command-line entry point
  config.py                     profile.json load/save/edit
  db.py, models.py, store.py    SQLite schema, dataclasses, query/insert API
  dedup.py                      fingerprinting so re-seen events don't duplicate
  matching.py                   interest keyword scoring
  query.py                      ad-hoc phrase parsing ("tonight", "near X", ...)
  roundup.py, digest.py         weekly selection + Markdown/HTML rendering
  ics_export.py                 dependency-free RFC 5545 writer
  ingestion/
    base.py                     SourceAdapter interface
    ics_rss_adapter.py          real RSS/iCal adapter (no API key needed)
    manual_adapter.py           add-event / log-attended
    newsletter_adapter.py       LLM-prompt + heuristic newsletter extraction
    future_adapters.py          Eventbrite/Meetup/Ticketmaster/Instagram stubs
tests/                          pytest suite, no live network calls
```
