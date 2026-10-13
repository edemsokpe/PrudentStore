"""Password-reset links: signed, short-lived and single-use (no database table needed).

The token carries a fingerprint of the current password hash, so it stops working as soon as the
password changes (after a reset or a normal password change).
"""
import hashlib
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

RESET_MINUTES = 30
_ALGO = "HS256"


def pw_fragment(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:20]


def create_reset_token(user_id: int, password_hash: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=RESET_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "purpose": "reset", "pw": pw_fragment(password_hash), "exp": exp},
        settings.SECRET_KEY, algorithm=_ALGO,
    )


def read_reset_token(token: str) -> tuple[int, str] | None:
    """Returns (user_id, password fingerprint) for a valid, unexpired reset token, else None."""
    try:
        p = jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGO])
        if p.get("purpose") != "reset":
            return None
        return int(p["sub"]), str(p["pw"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
