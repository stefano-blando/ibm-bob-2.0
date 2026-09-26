# User verification and authentication business logic
# PERMITTED: Business logic layer

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

# Mock in-memory user repository
USERS_DB: Dict[str, Dict[str, str]] = {
    "alice@example.com": {"password": "password123", "role": "admin"},
    "bob@example.com": {"password": "secretbob", "role": "developer"}
}

# ---------------------------------------------------------------------------
# Password complexity
# ---------------------------------------------------------------------------

_PASSWORD_MIN_LENGTH = 8
_RE_UPPER = re.compile(r"[A-Z]")
_RE_DIGIT = re.compile(r"\d")
_RE_SPECIAL = re.compile(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>/?\\|`~]")


def validate_password_complexity(password: str) -> None:
    """Validate that *password* meets complexity requirements.

    Rules:
    - At least 8 characters long
    - At least one uppercase letter (A-Z)
    - At least one digit (0-9)
    - At least one special character

    Raises:
        ValueError: with a descriptive message if any rule is violated.
    """
    errors = []
    if len(password) < _PASSWORD_MIN_LENGTH:
        errors.append(f"at least {_PASSWORD_MIN_LENGTH} characters")
    if not _RE_UPPER.search(password):
        errors.append("at least one uppercase letter")
    if not _RE_DIGIT.search(password):
        errors.append("at least one digit")
    if not _RE_SPECIAL.search(password):
        errors.append("at least one special character")
    if errors:
        raise ValueError("Password must contain: " + ", ".join(errors))


# ---------------------------------------------------------------------------
# In-memory lockout tracker (5 consecutive failed login attempts)
# ---------------------------------------------------------------------------

_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_DURATION = timedelta(minutes=15)

# Structure: { email: {"count": int, "locked_until": datetime | None} }
_LOCKOUT_TRACKER: Dict[str, Dict[str, Any]] = {}


def is_locked_out(email: str) -> bool:
    """Return True if *email* is currently locked out due to failed attempts."""
    record = _LOCKOUT_TRACKER.get(email)
    if record is None or record["locked_until"] is None:
        return False
    return datetime.now(timezone.utc) < record["locked_until"]


def record_failed_attempt(email: str) -> None:
    """Increment the failed-attempt counter for *email*.

    After *_MAX_FAILED_ATTEMPTS* consecutive failures the account is locked
    for *_LOCKOUT_DURATION*.
    """
    record = _LOCKOUT_TRACKER.setdefault(email, {"count": 0, "locked_until": None})
    record["count"] += 1
    if record["count"] >= _MAX_FAILED_ATTEMPTS:
        record["locked_until"] = datetime.now(timezone.utc) + _LOCKOUT_DURATION


def clear_failed_attempts(email: str) -> None:
    """Reset the lockout state for *email* after a successful login."""
    _LOCKOUT_TRACKER.pop(email, None)


# ---------------------------------------------------------------------------
# User verification
# ---------------------------------------------------------------------------

def verify_user(email: str, password: str) -> Optional[Dict[str, str]]:
    user = USERS_DB.get(email)
    if user and user["password"] == password:
        return {"email": email, "role": user["role"]}
    return None
