"""Single local user account management for the Phase 2 web app.

This is a personal tool, not a multi-tenant product — one account exists.
Real login/session still matters (outcome: "signed-in user"), it's just
that account creation is a deliberate CLI step (`events web create-user`),
not a public signup form. Password hashing uses Werkzeug's implementation
(PBKDF2/scrypt depending on version) rather than rolling anything custom.
"""
from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash


@dataclass
class User:
    id: int
    username: str
    password_hash: str
    ics_token: str
    created_at: str


def get_user(conn: sqlite3.Connection) -> Optional[User]:
    """Returns the single user account, or None if not created yet."""
    row = conn.execute("SELECT * FROM users LIMIT 1").fetchone()
    return User(**dict(row)) if row else None


def create_user(conn: sqlite3.Connection, username: str, password: str) -> User:
    if get_user(conn) is not None:
        raise ValueError("a user account already exists — this tool supports a single local account")
    password_hash = generate_password_hash(password)
    ics_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO users (username, password_hash, ics_token, created_at) VALUES (?, ?, ?, ?)",
        (username, password_hash, ics_token, now),
    )
    conn.commit()
    return get_user(conn)


def verify_password(user: User, password: str) -> bool:
    return check_password_hash(user.password_hash, password)


def set_password(conn: sqlite3.Connection, user_id: int, new_password: str) -> None:
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), user_id),
    )
    conn.commit()


def regenerate_ics_token(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute("UPDATE users SET ics_token = ? WHERE id = ?", (token, user_id))
    conn.commit()
    return token


def get_user_by_ics_token(conn: sqlite3.Connection, token: str) -> Optional[User]:
    row = conn.execute("SELECT * FROM users WHERE ics_token = ?", (token,)).fetchone()
    return User(**dict(row)) if row else None
