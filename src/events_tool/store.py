"""EventStore: the read/write API over the SQLite events table.

Every insert goes through dedup.fingerprint() so re-ingesting the same feed,
or seeing the same event mentioned in a newsletter and an iCal feed, doesn't
create duplicate calendar entries — the second insert is recognized as a
repeat and skipped (its ingestion_log count is bumped instead).

Category correction (`set_user_category`), bookmarking (`set_saved`), and
personal notes (`set_user_notes`) are personal signals layered on top of a
row's ingested facts (source_category, description, etc.) — they are always
applied as separate columns, never by mutating the original fact columns.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from events_tool.dedup import fingerprint
from events_tool.models import VALID_STATUSES, IngestionRun, Place, RawEventCandidate

# category effective value used throughout: a personal correction wins over
# the ingested fact, without the ingested fact ever being overwritten.
_CATEGORY_EXPR = "COALESCE(user_category, source_category)"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EventStore:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # -- writes ---------------------------------------------------------

    def insert_candidate(
        self,
        candidate: RawEventCandidate,
        category: str,
        city: str,
        state: str,
        status: str = "candidate",
        verification: str = "user-manual",
    ) -> tuple[Optional[int], bool]:
        """Insert a RawEventCandidate. Returns (event_id, was_new).

        If the event's fingerprint already exists, no new row is written;
        (existing_id, False) is returned so callers can count it as deduped.
        `category` here is always the *ingested* source_category — user
        corrections happen later via set_user_category(), never at insert time.
        """
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {status}")
        key = fingerprint(candidate.title, candidate.start_dt or "", candidate.location_name)
        existing = self.conn.execute(
            "SELECT id FROM events WHERE dedup_key = ?", (key,)
        ).fetchone()
        if existing:
            return existing["id"], False

        now = _now()
        cur = self.conn.execute(
            """
            INSERT INTO events (
                title, description, source_category, user_category, start_dt, end_dt,
                location_name, address, city, state, neighborhood,
                lat, lon, url, source_name, source_type, external_uid,
                dedup_key, status, verification, saved, user_notes, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '', ?, ?)
            """,
            (
                candidate.title,
                candidate.description,
                category,
                candidate.start_dt or "",
                candidate.end_dt,
                candidate.location_name,
                candidate.address,
                city,
                state,
                candidate.neighborhood,
                None,
                None,
                candidate.url,
                candidate.source_name,
                candidate.source_type,
                candidate.external_uid,
                key,
                status,
                verification,
                now,
                now,
            ),
        )
        self.conn.commit()
        return cur.lastrowid, True

    def update_status(self, event_id: int, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {status}")
        self.conn.execute(
            "UPDATE events SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), event_id),
        )
        self.conn.commit()

    def set_user_category(self, event_id: int, category: Optional[str]) -> None:
        """Apply (or clear, if category is None) a personal category
        correction. The original ingested source_category is untouched."""
        self.conn.execute(
            "UPDATE events SET user_category = ?, updated_at = ? WHERE id = ?",
            (category, _now(), event_id),
        )
        self.conn.commit()

    def set_saved(self, event_id: int, saved: bool) -> None:
        self.conn.execute(
            "UPDATE events SET saved = ?, updated_at = ? WHERE id = ?",
            (1 if saved else 0, _now(), event_id),
        )
        self.conn.commit()

    def set_user_notes(self, event_id: int, notes: str) -> None:
        self.conn.execute(
            "UPDATE events SET user_notes = ?, updated_at = ? WHERE id = ?",
            (notes, _now(), event_id),
        )
        self.conn.commit()

    def mark_roundup_included(self, event_ids: list[int]) -> None:
        if not event_ids:
            return
        now = _now()
        placeholders = ",".join("?" for _ in event_ids)
        self.conn.execute(
            f"UPDATE events SET roundup_included_at = ? WHERE id IN ({placeholders})",
            [now, *event_ids],
        )
        self.conn.commit()

    def log_ingestion_run(self, run: IngestionRun) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO ingestion_log (source_name, run_at, items_found, items_added, items_deduped, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run.source_name, run.run_at, run.items_found, run.items_added, run.items_deduped, run.status, run.notes),
        )
        self.conn.commit()
        return cur.lastrowid

    def insert_place(self, place: Place) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO places (name, address, lat, lon, tags, list_name, source, imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (place.name, place.address, place.lat, place.lon, place.tags, place.list_name, place.source, place.imported_at),
        )
        self.conn.commit()
        return cur.lastrowid

    # -- reads ------------------------------------------------------------

    def get_by_id(self, event_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            f"SELECT *, {_CATEGORY_EXPR} AS category FROM events WHERE id = ?", (event_id,)
        ).fetchone()

    def query(
        self,
        category: Optional[str] = None,
        near: Optional[str] = None,
        keyword: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        status: Optional[str] = None,
        statuses: Optional[list[str]] = None,
        saved_only: bool = False,
    ) -> list[sqlite3.Row]:
        clauses = []
        params: list = []

        if category:
            clauses.append(f"{_CATEGORY_EXPR} = ?")
            params.append(category)
        if near:
            clauses.append("(neighborhood LIKE ? OR location_name LIKE ? OR address LIKE ? OR city LIKE ?)")
            like = f"%{near}%"
            params.extend([like, like, like, like])
        if keyword:
            clauses.append("(title LIKE ? OR description LIKE ?)")
            like = f"%{keyword}%"
            params.extend([like, like])
        if date_from:
            clauses.append("start_dt >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("start_dt <= ?")
            params.append(date_to)
        if status:
            clauses.append("status = ?")
            params.append(status)
        elif statuses:
            placeholders = ",".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        if saved_only:
            clauses.append("saved = 1")

        sql = f"SELECT *, {_CATEGORY_EXPR} AS category FROM events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY start_dt ASC"

        return self.conn.execute(sql, params).fetchall()

    def pending_review(self) -> list[sqlite3.Row]:
        return self.query(status="candidate")

    def upcoming_roundup_candidates(self, since_iso: str, until_iso: str) -> list[sqlite3.Row]:
        """Confirmed/attended events in [since, until] not yet included in a roundup."""
        sql = f"""
            SELECT *, {_CATEGORY_EXPR} AS category FROM events
            WHERE status IN ('confirmed', 'attended')
              AND start_dt >= ? AND start_dt <= ?
              AND roundup_included_at IS NULL
            ORDER BY start_dt ASC
        """
        return self.conn.execute(sql, (since_iso, until_iso)).fetchall()

    def category_counts(self, verification: Optional[str] = None) -> dict[str, int]:
        if verification:
            sql = f"SELECT {_CATEGORY_EXPR} AS category, COUNT(*) AS n FROM events WHERE verification = ? GROUP BY category"
            rows = self.conn.execute(sql, (verification,)).fetchall()
        else:
            sql = f"SELECT {_CATEGORY_EXPR} AS category, COUNT(*) AS n FROM events GROUP BY category"
            rows = self.conn.execute(sql).fetchall()
        return {row["category"]: row["n"] for row in rows}

    def last_ingestion_by_source(self) -> dict[str, sqlite3.Row]:
        sql = """
            SELECT source_name, MAX(run_at) AS last_run_at, status
            FROM ingestion_log
            GROUP BY source_name
        """
        return {row["source_name"]: row for row in self.conn.execute(sql).fetchall()}

    def places(self, list_name: Optional[str] = None) -> list[sqlite3.Row]:
        if list_name:
            return self.conn.execute(
                "SELECT * FROM places WHERE list_name = ? ORDER BY name", (list_name,)
            ).fetchall()
        return self.conn.execute("SELECT * FROM places ORDER BY list_name, name").fetchall()
