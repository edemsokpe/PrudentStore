import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User
from .reset_tokens import pw_fragment

bearer = HTTPBearer(auto_error=False)
ALGO = "HS256"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt${}${}".format(base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest, expected)
    except Exception:
        return False


def create_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)
    return jwt.encode({"sub": str(user.id), "role": user.role, "pw": pw_fragment(user.password_hash), "exp": exp}, settings.SECRET_KEY, algorithm=ALGO)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(401, "Please log in to continue")
    try:
        payload = jwt.decode(creds.credentials, settings.SECRET_KEY, algorithms=[ALGO])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, "Your session has expired. Please log in again")
    user = db.get(User, user_id)
    # "pw" ties the session to the current password: changing or resetting it logs every device out
    if not user or not user.is_active or payload.get("pw") != pw_fragment(user.password_hash):
        raise HTTPException(401, "Your session has expired. Please log in again")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin access only")
    return user


# Used so a login for an unknown email takes as long as a real one (no account guessing by timing).
DUMMY_HASH = hash_password("not-a-real-password")
