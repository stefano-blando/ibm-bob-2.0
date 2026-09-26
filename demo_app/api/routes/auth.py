# Authentication & Login Endpoints
# PERMITTED: API Router layer

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import demo_app.core.config as _config
from demo_app.services.user_service import verify_user

# Maximum consecutive failed attempts before the account is temporarily locked.
MAX_FAILED_ATTEMPTS = 5
# Lock duration in minutes after exceeding MAX_FAILED_ATTEMPTS.
LOCKOUT_MINUTES = 15


def _get_db_path() -> str:
    """Derive the SQLite file path from DATABASE_URL (``sqlite:///./path``)."""
    return _config.DATABASE_URL.replace("sqlite:///", "")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_get_db_path(), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    return conn


def _is_locked(email: str) -> bool:
    """Return True if *email* is currently under a rate-limit lockout."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT locked_until FROM rate_limits WHERE email = ?", (email,)
        ).fetchone()
    if row is None or row["locked_until"] is None:
        return False
    raw = row["locked_until"]
    locked_until = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < locked_until


def _record_failure(email: str) -> None:
    """Increment the failed-attempt counter and set a lockout if the threshold is reached."""
    now = datetime.now(timezone.utc).isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO rate_limits (email, failed_attempts, last_failed_at)
            VALUES (?, 1, ?)
            ON CONFLICT(email) DO UPDATE SET
                failed_attempts = failed_attempts + 1,
                last_failed_at  = excluded.last_failed_at
            """,
            (email, now),
        )
        conn.execute(
            """
            UPDATE rate_limits
            SET locked_until = datetime(last_failed_at, ? || ' minutes')
            WHERE email = ? AND failed_attempts >= ?
            """,
            (str(LOCKOUT_MINUTES), email, MAX_FAILED_ATTEMPTS),
        )
        conn.commit()


def _clear_failures(email: str) -> None:
    """Reset the rate-limit record after a successful login."""
    with _get_conn() as conn:
        conn.execute(
            "DELETE FROM rate_limits WHERE email = ?", (email,)
        )
        conn.commit()


def login_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    """Authenticate a user and return a session token.

    Args:
        payload: A dictionary containing the login credentials.
            Expected keys:
                - ``email`` (str): The user's email address.
                - ``password`` (str): The user's plain-text password.

    Returns:
        On success:      ``{"token": str, "status": 200}``
        On locked:       ``{"error": str, "status": 429}``
        On bad creds:    ``{"error": str, "status": 401}``
    """
    email: str = payload.get("email", "")
    password: str = payload.get("password", "")

    if _is_locked(email):
        return {"error": "Account temporarily locked due to too many failed attempts", "status": 429}

    user = verify_user(email, password)
    if not user:
        _record_failure(email)
        return {"error": "Invalid credentials", "status": 401}

    _clear_failures(email)
    return {"token": f"token-{email}", "status": 200}
