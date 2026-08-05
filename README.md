# Events Calendar Tool

A personal, source-agnostic events discovery and calendar tool. It was built
around one problem: too many pages, groups, and newsletters to track for
things like art shows, indie film, local bands, salsa nights, gardening and
kettlebell clubs, book clubs/meetups, comedy, trivia/board games, networking
mixers, natural building workshops, and maker-space workshops. It compiles
matching events into a personal calendar you curate over time, and it
answers ad-hoc questions like *"salsa tonight,"* *"new gallery exhibitions
near Montrose,"* *"real-estate networking this week,"* or *"live jazz music
for August 1st."*

It ships seeded for Houston, TX, but city/state and the entire interest list
are just config — point it anywhere.

No paid APIs or accounts are required. It runs entirely on the Python
standard library (no `pip install` needed to use it).

## Where this is in its build

Built in two phases, by design:

- **Phase 1 (CLI + static prototype)**: the engine — data model, ingestion,
  matching, dedup, personal signals, coverage transparency — plus a CLI and
  a static, read-only HTML calendar prototype you regenerate on demand.
  Still fully supported; the CLI is what any automation (the weekly
  Routine, cron) drives under the hood.
- **Phase 2 (`events_tool.web`, this repo, today)**: a Flask web app on
  top of the exact same engine — real session-based sign-in (a single
  local account), an interactive calendar where save/attend/recategorize
  happen as real form actions (not just CLI commands), an ask/search page
  with a live-search fallback, and a live `.ics`/webcal subscription
  endpoint for Google Calendar and friends. See "Web app" below for setup.

Anywhere below that still says "for now, use the CLI" is describing a
CLI-only path that the web app has since covered with a page — both stay
supported; the web app doesn't replace the CLI, it's a UI layer on the
same store/config/discover/ask modules.

## Web app

```bash
pip install -r requirements.txt      # installs Flask
export PYTHONPATH=src
events web create-user --username you   # one-time; prompts for a password (never touches git)
events web run                          # http://127.0.0.1:5000
# or: scripts/run_web.sh --host 0.0.0.0 --port 8080
```

Pages: **Calendar** (month grid) and **Agenda** (today/week/30d/90d list,
with a List/Cards toggle), both with category and saved-only filters;
**Ask/Search** — the same local-first, explicit-date-range,
live-search-fallback flow as `events ask`, but as a form instead of file
juggling; **Review** — event cards for pending candidates; **Coverage** —
the same honest automated/researched/reference/none breakdown as `events
coverage`; **Places** — list + drag-and-drop KML/CSV import; **Settings**
— interests, sources, and your calendar subscription link.

**Event cards** (Review, and Agenda's Cards view) show why an event
matched — "Matches: chess club" chips are computed live against your
*current* active interests, not stored at ingestion time, so editing an
interest later immediately changes which chips a card shows. Actions:
**Attend** / undo, **Save for later**, **Not for me** (rejects from any
status, not just candidates), and **Add to interests** — seeds a new
interest keyword from the event (defaults to its venue name) in one
click, so confirming you liked something naturally teaches the discovery
loop to find more like it. Edit or remove what it guessed from Settings
if the default keyword isn't quite right.

**Auth**: one local account (`events web create-user`), Werkzeug-hashed
password, signed-cookie session. Change your password with `events web
set-password`.

**Calendar subscription**: Settings shows a private `.ics` URL
(`/calendar/<token>.ics`) — paste it into Google Calendar / Apple
Calendar's "subscribe by URL." It's token-protected rather than
session-protected, since calendar apps poll it with no interactive login;
regenerate the token from Settings if it ever leaks. The session-signing
secret (`data/flask_secret.key`) is generated locally on first run and,
unlike `events.db`/`profile.json`, is **not** tracked in git — it's a
real security secret, not durable state worth persisting that way.

**Deploying for real**: the dev server (`events web run`) is fine for
trying this locally, but the actual next step from here is real hosting —
a VPS, a home server, or a PaaS — both because Flask's dev server says so
itself, and because this sandbox's network policy blocks the outbound
fetches the RSS/iCal adapter needs (see "Background cadence" below); nothing
about the app itself is sandbox-specific.

`wsgi.py` + the `Dockerfile` are the production path — `events web run`
never runs code beyond local testing:

```bash
docker build -t events-tool-web .
docker run -p 8000:8000 -v events-tool-data:/app/data events-tool-web
# then, once: docker exec -it <container> python -m events_tool.cli web create-user --username you
```

The `-v` volume is not optional — `data/events.db`, `config/profile.json`,
and `data/flask_secret.key` all live in `/app/data`/`/app/config` inside
the container; without a persistent mount every redeploy starts from a
blank calendar. Environment variables for a real deployment:

| Variable | Purpose |
|---|---|
| `EVENTS_TOOL_SECRET_KEY` | Session-signing secret from your platform's secrets manager, instead of the local-file fallback (Fly.io secrets, Render/Railway env vars, etc.) |
| `EVENTS_TOOL_HTTPS=1` | Marks the session cookie `Secure` — set this once you're actually behind HTTPS (any real deployment should be) |
| `EVENTS_TOOL_DB_PATH` | Point at a different DB file if `/app/data/events.db` isn't where your volume is mounted |

Any host with a persistent volume and normal (non-sandboxed) outbound
networking works — a small VPS (DigitalOcean/Hetzner/Linode) gives full
control for a few dollars a month; Fly.io or Railway give a simpler
Docker-based deploy with a free/cheap tier and persistent volumes built
in. This step needs your own account/billing on whichever you pick — it
isn't something that can be provisioned from inside this environment.

## Principles this tool holds itself to

- **Never fabricate.** No invented events, dates/times, sources, attendance,
  reviews, ratings, or testimonials — and no coverage claims broader than
  what was actually checked. Every event row is tagged with where it came
  from (`events coverage`, `events roundup` both surface this) so "this is
  from a real feed" vs. "this is a lead you pasted, unverified" is always
  visible, never blurred.
- **Source facts vs. personal signals.** An event's ingested facts
  (title, time, description, its `source_category`) are never overwritten
  by your personal edits. Corrections layer on top: `user_category`,
  `saved`, `user_notes` are separate columns from day one. `events
  recategorize` fixes a miscategorized event without touching what the
  source actually said.
- **Honest coverage, not implied completeness.** `events coverage` and the
  roundup's disclosure section distinguish four states per category:
  automated (a real feed has actually produced events here), automated
  source enabled but no hits yet, reference-only (only manual/newsletter
  entries exist), and no coverage at all. A category with zero events never
  silently reads as "nothing's happening" — it reads as "nothing's been
  checked."

## How it's put together

- **`config/profile.json`** — your hand-editable profile: location,
  interests (keyword → category), and ingestion sources. Seeded from
  `config/profile.example.json` (Houston defaults) by `events init`.
  Categories: `art, maker, music, film, books, gardening, fitness, dance,
  comedy, sports_games, natural_building, networking, other`.
- **`data/events.db`** — a local SQLite database holding events, an
  ingestion audit log, and imported places. Tracked in git (see
  "Background cadence" below) so state survives this running in an
  ephemeral container.
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
  - **Lead** (`events source add --type lead`) — a known account/page (e.g.
    an Instagram handle) worth checking by hand. No adapter fetches it, but
    it shows up in `events coverage` as a known gap, not silently missing.
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
- **Personal signals** — `events save`/`unsave` (bookmark), `events
  attend`/`unattend` (mark attended, or reverse it back to confirmed),
  `events log-experience` (your own notes on an event, kept separate from
  its source description), `events recategorize` (category correction that
  never touches the ingested fact).
- **Places** — `events places import` reads a Google My Maps KML export or
  a plain CSV of venues you already trust, as a reference list (`events
  places list`).
- **Query engine** — a lightweight phrase parser for ad-hoc questions
  (`events query`), including specific dates ("August 1st", "8/1"), relative
  ones ("tonight", "this week"), and a structured filter command (`events
  show`).
- **Weekly roundup** — `events roundup` selects newly-confirmed events in
  the next N days, grouped by category, renders Markdown/HTML/ICS, and
  always prints a coverage disclosure: what was checked, what wasn't, and a
  reminder that nothing in it is invented.
- **ICS export** — `events export-ics` writes a hand-rolled, dependency-free
  RFC 5545 calendar file you can import into Google Calendar, Apple
  Calendar, Outlook, etc. (A live webcal *subscription* endpoint, so the
  calendar updates itself instead of needing re-import, is a Phase 2 item —
  it needs a persistently-running server.)
- **Calendar prototype** (`events export-snapshot` +
  `scripts/build_calendar_artifact.py`) — a self-contained, read-only HTML
  page with month and agenda views, category/saved filters, a coverage
  panel, and an event detail drawer showing provenance and the CLI command
  to act on that event. Regenerate it any time your data changes.

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
events source add --name some-gallery-instagram --type lead \
  --url "https://instagram.com/some_gallery"   # known lead, checked manually
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
events ingest                    # fetch every enabled RSS/iCal source
events ingest --source my-favorite-venue
events review                    # walk pending candidates: confirm / reject / skip
```

Run `events ingest && events review` on whatever cadence you like. See
"Background cadence" below for how this actually runs unattended.

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
that match an active interest keyword. Always review these afterward —
both paths are tagged `user-lead-*` in `events coverage`, never presented
as independently verified.

## Organic discovery: "go find events for me"

Same two-step, prompt/structured-import shape as newsletter ingestion, but
scoped to your saved places (`events places import`) and active interests
instead of a specific text you pasted — this is how you get events without
already knowing where to look:

```bash
events discover-prompt --days 7 --out prompt.txt
# run prompt.txt through any web-search-capable LLM, save its JSON reply
events discover-import --structured response.json
```

The prompt asks the LLM to check your saved places for scheduled events
*and* run general searches for your active interests not tied to any
specific venue, but to only report an event if it found a concrete date
and a real source URL — never to infer a date from "runs every Tuesday"
unless that exact upcoming occurrence is stated directly on a page.

This source type (`assistant-researched`) carries more fabrication risk
than a newsletter you chose to paste, since the LLM is searching the open
web rather than reading text you selected — so `discover-import` holds a
stricter line than `ingest-text`: **every event must include a source
URL** (entries without one are dropped with a warning, not silently kept),
and there is no `--auto-confirm` option at all. Everything lands as a
review candidate. `events coverage` and the calendar prototype both label
these distinctly from manual/newsletter entries, not lumped in as
equally-trusted "reference" data.

## Logging something you already attended or already know about

```bash
events add-event --title "Salsa Night at The Continental Club" \
  --start 2026-08-05T20:00:00 --category dance \
  --location "Continental Club" --neighborhood Montrose \
  --url "https://example.org/salsa"

events log-attended --title "Indie Film Screening at 14 Pews" \
  --date 2026-07-20T19:00:00 --category film --location "14 Pews"
```

## Managing personal signals

```bash
events save 12                                    # bookmark
events unsave 12
events attend 12                                   # mark attended
events unattend 12                                  # reverse it (back to confirmed)
events log-experience 12 --notes "Great band, will go again"
events recategorize 12 --category dance             # fix a miscategorized event
```

`recategorize` only ever sets a `user_category` override — the original
`source_category` an ingestion adapter or manual entry recorded is always
still there (`events show` marks overridden events `(recategorized)`).

## Bringing your own leads

- **Newsletter text** — see above.
- **An event URL/details you already have** — `events add-event --url ...`.
- **A place you already trust** — `events places import --file
  mylist.kml --name "Favorite Galleries"` (export from Google My Maps:
  menu → Export to KML) or a CSV with `name,address,lat,lon,tags` columns.
  `events places list` to review what's imported. (Scraping a public Maps
  share link directly was considered and rejected: Google's unofficial page
  markup isn't a stable API and can silently break without notice.)
- **A known account/page you check yourself** — `events source add --type
  lead`, so it's tracked in `events coverage` as a real gap instead of
  invisible.

## Ad-hoc queries

```bash
events query "salsa tonight"
events query "gardening workshop" --near "no limit"
events query "new gallery exhibitions" --near Montrose
events query "real estate networking this week"
events query "live comedy shows this week"
events query "live jazz music for August 1st"
```

`events show` gives structured filtering instead of phrase parsing:

```bash
events show --category art --near Montrose --from 2026-08-01 --to 2026-08-31
events show --status candidate   # same as `events review`, without the prompts
events show --saved              # your bookmarked events
```

`events query` only ever searches what's *already* in your calendar. For
"go check if this is happening and tell me," see `events ask` below.

## Asking a specific question, with an explicit date range

```bash
events ask "find a chess club in houston"                    # defaults to --range week
events ask "live music" --range today
events ask "Formula 1 watch party" --range 30d
events ask "art opening" --range custom --from 2026-09-01T00:00:00 --to 2026-09-15T00:00:00
```

Same prompt/structured-import shape as `discover`, but scoped to one
specific question instead of a broad sweep, and — this is the important
part — **the date range is always an explicit choice** (`today` / `week`
/ `30d` / `90d` / `custom --from --to`), never something inferred from the
question's wording. That was a real bug in earlier ad hoc testing: asking
about a Formula 1 watch party silently got treated as "this week" without
ever being asked.

`events ask` checks your local calendar first (same as `events query`); if
nothing matches, it prints a research prompt:

```bash
events ask "Formula 1 watch party" --out prompt.txt
# run prompt.txt through a web-search-capable LLM, save its JSON reply
events ask-import --structured response.json
```

The reply schema has two parts: `matches` (within your requested range —
these land as review candidates like everything else) and
`next_occurrence_suggestions` (found *outside* the range — e.g. no F1 race
this week, but the next one is Aug 23). Suggestions are reported but **not
added automatically**, since they're answering a different question than
the one you asked:

```
1 suggestion(s) found OUTSIDE your requested range (not added automatically):
  [0] F1 Dutch Grand Prix Watch Party — 2026-08-23T08:00:00 @ Grand Prix Plaza - Turn 1 Lounge
      No F1 race this week - the next one is Aug 23, outside your 7-day window.
      https://...

To add one: events ask-import --structured <file> --add-suggested <index>
```

## Understanding your coverage

```bash
events coverage
```

Prints, per source: whether it's automated/enabled, lead-only, or
reference-only, and when it last ran successfully. Per category: whether
automated coverage is *confirmed* (a real feed has actually produced an
event here), an automated source is enabled but hasn't surfaced anything
yet, coverage is reference-only (manual/newsletter entries only), or there's
no coverage at all yet. `events roundup` prints the same disclosure,
scoped to its window, every time.

## Weekly roundup and calendar export

```bash
events roundup --days 7 --export md --out this_week.md
events roundup --days 7 --export html --out this_week.html
events roundup --days 7 --export ics --out this_week.ics
events export-ics --out full_calendar.ics   # all confirmed+attended events, any date
```

`roundup` marks the events it included so the next run doesn't repeat them
(pass `--no-mark-included` to preview without consuming the queue), and
always ends with the coverage disclosure described above.

### Calendar prototype (Phase 1 UI)

```bash
events export-snapshot --out data/snapshot.json
python3 scripts/build_calendar_artifact.py --snapshot data/snapshot.json --out calendar.html
```

Open `calendar.html` in a browser: month and agenda views, category/saved
filters, a coverage panel, and a detail drawer per event (source link,
provenance explanation, and the exact CLI command to save/attend/
recategorize it — this view is read-only until Phase 2's live app).

### Why a 7-day roundup window but no fixed calendar horizon

`events roundup --days N` defaults to 7 (a weekly digest), but `events show`
and the calendar prototype have no hard horizon — they display whatever is
in the database. In practice that's bounded by how far out your ingested
sources publish (most venue feeds only list ~30-60 days ahead), so a ~30-day
practical horizon emerges without the tool needing to enforce one.

## Background cadence

Two mechanisms, so this works whether or not you're using this tool inside
Claude Code:

1. **A Claude Code Routine** ("Houston Events Weekly Ingest", weekly on
   Monday) — runs `events ingest`, regenerates the roundup, and reports a
   summary (sources checked, pending-review count, uncovered categories)
   back into this session. This is the literal "background discovery
   cadence" for as long as you're working with this tool via Claude Code.
2. **`scripts/run_weekly_ingest.sh`** — the same ingest+roundup steps as a
   plain shell script, for a normal crontab/Task Scheduler entry once this
   is self-hosted outside Claude Code:
   ```
   0 8 * * 1 /path/to/Events-Calendar-Tool/scripts/run_weekly_ingest.sh >> /path/to/Events-Calendar-Tool/data/ingest.log 2>&1
   ```

**On persistence:** this runs in an ephemeral container that can be
reclaimed between sessions, so `data/events.db` and `config/profile.json`
are tracked in git — that's the durability mechanism for a private personal
repo today. If this tool ever moves to a shared or public repo, swap that
for a real hosted database instead of committing the DB file.

**On network access inside this Claude Code sandbox:** this environment's
egress policy blocks direct HTTPS fetches to arbitrary hosts outright —
confirmed against `example.com`, not just specific venue sites. Since
`events ingest`'s RSS/iCal adapter uses `urllib.request` for exactly that
kind of direct fetch, running it from *inside this sandbox* against a real
venue's feed will fail the same way (logged as an `error` status in
`events coverage`, not a silent no-op — the adapter's error handling
already surfaces this). This is a property of this specific sandboxed
session, not a bug in the adapter: the same code fetches real feeds fine
on a normal machine, VPS, or CI runner with ordinary internet access — it's
only this environment's network policy that's restrictive. The weekly
Claude Code Routine will hit the same wall for any real source configured
while it keeps running inside this sandbox; `discover-prompt`/
`discover-import` are unaffected since web search runs through a separate
managed service, not this sandbox's network policy — which is why that's
been the productive path for real events during this session.

## Future scope (not built, on purpose)

These are real product directions, deliberately deferred rather than
half-built: expansion beyond Houston (already just a config value, but
untested at scale), per-use "find events near me" via device geolocation
with a consent prompt every time, friend invitations, shared event
calendars, RSVPs, and privacy-preserving group availability. Building these
well needs real privacy design (especially the location and
friend/group-availability features) that hasn't been done yet — flagged
here rather than shipped half-considered.

## Project layout

```
config/profile.example.json     Houston-seeded default profile
templates/calendar_prototype.html   calendar prototype template (JSON placeholder)
scripts/
  build_calendar_artifact.py    injects a snapshot into the template
  run_weekly_ingest.sh          OS-cron entry point for self-hosted use
src/events_tool/
  cli.py                        command-line entry point
  config.py                     profile.json load/save/edit
  db.py, models.py, store.py    SQLite schema, dataclasses, query/insert API
  dedup.py                      fingerprinting so re-seen events don't duplicate
  matching.py                   interest keyword scoring
  query.py                      ad-hoc phrase parsing ("tonight", "August 1st", "near X", ...)
  places.py                     KML/CSV places-list import
  roundup.py, digest.py         weekly selection + Markdown/HTML rendering + coverage disclosure
  ics_export.py                 dependency-free RFC 5545 writer
  ingestion/
    base.py                     SourceAdapter interface
    ics_rss_adapter.py          real RSS/iCal adapter (no API key needed)
    manual_adapter.py           add-event / log-attended
    newsletter_adapter.py       LLM-prompt + heuristic newsletter extraction
    future_adapters.py          Eventbrite/Meetup/Ticketmaster/Instagram stubs
tests/                          pytest suite, no live network calls
```
