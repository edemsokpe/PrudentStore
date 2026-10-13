import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from .. import notify, ratelimit
from ..config import settings
from ..database import get_db
from ..models import User
from ..reset_tokens import RESET_MINUTES, create_reset_token, pw_fragment, read_reset_token
from ..schemas import RegisterIn, LoginIn, TokenOut, UserOut, ProfileIn, PasswordIn, ForgotIn, ResetIn
from ..security import DUMMY_HASH, hash_password, verify_password, create_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenOut)
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    rl = f"register:{ratelimit.client_ip(request)}"
    ratelimit.check(rl, 10, 3600)
    ratelimit.hit(rl)
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise HTTPException(400, "An account with this email already exists")
    user = User(
        full_name=data.full_name.strip(),
        email=data.email,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role="customer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    notify.welcome(user.email, user.full_name)
    return {"access_token": create_token(user), "user": user}


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = ratelimit.client_ip(request)
    ip_key, acct_key = f"login-ip:{ip}", f"login:{ip}:{data.email}"
    ratelimit.check(ip_key, 40, 900)    # 40 tries per 15 minutes from one address
    ratelimit.check(acct_key, 8, 900)   # 8 wrong passwords per 15 minutes for one account from one address
    ratelimit.hit(ip_key)
    user = db.scalar(select(User).where(User.email == data.email))
    if user and user.is_active:
        ok = verify_password(data.password, user.password_hash)
    else:
        verify_password(data.password, DUMMY_HASH)
        ok = False
    if not ok:
        ratelimit.hit(acct_key)
        raise HTTPException(401, "Incorrect email or password")
    ratelimit.clear(acct_key)
    return {"access_token": create_token(user), "user": user}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserOut)
def update_me(data: ProfileIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.full_name = data.full_name.strip()
    user.phone = data.phone
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password")
def change_password(data: PasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    notify.password_changed(user.email, user.full_name)
    return {"ok": True, "access_token": create_token(user)}  # new token: this device stays logged in, others are logged out


# ---------- forgot / reset password ----------
_last_request: dict[str, float] = {}


@router.post("/forgot")
def forgot_password(data: ForgotIn, request: Request, db: Session = Depends(get_db)):
    """Always answers the same way, so nobody can use it to find out who has an account."""
    rl = f"forgot:{ratelimit.client_ip(request)}"
    ratelimit.check(rl, 10, 3600)
    ratelimit.hit(rl)
    if not notify.email_enabled():
        raise HTTPException(503, "Password reset by email is not available yet. Please contact the shop.")
    now = time.monotonic()
    if len(_last_request) > 2000:
        _last_request.clear()
    if now - _last_request.get(data.email, -999) >= 60:  # at most one email per address per minute
        _last_request[data.email] = now
        user = db.scalar(select(User).where(User.email == data.email))
        if user and user.is_active:
            link = f"{settings.FRONTEND_URL.rstrip('/')}/reset.html?token={create_reset_token(user.id, user.password_hash)}"
            notify.password_reset(user.email, user.full_name, link, RESET_MINUTES)
    return {"ok": True}


@router.post("/reset")
def reset_password(data: ResetIn, request: Request, db: Session = Depends(get_db)):
    rl = f"reset:{ratelimit.client_ip(request)}"
    ratelimit.check(rl, 20, 3600)
    ratelimit.hit(rl)
    bad = HTTPException(400, "This reset link is invalid or has expired. Please request a new one.")
    parsed = read_reset_token(data.token)
    if not parsed:
        raise bad
    user = db.get(User, parsed[0])
    if not user or not user.is_active or pw_fragment(user.password_hash) != parsed[1]:
        raise bad
    user.password_hash = hash_password(data.new_password)
    db.commit()
    notify.password_changed(user.email, user.full_name)
    return {"ok": True}
