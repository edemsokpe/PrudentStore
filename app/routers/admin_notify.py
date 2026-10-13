from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import notify
from ..config import settings
from ..database import get_db
from ..models import NotificationLog
from ..security import require_admin

router = APIRouter(prefix="/admin/notifications", tags=["Admin: notifications"], dependencies=[Depends(require_admin)])


@router.get("")
def status_and_log(db: Session = Depends(get_db)):
    rows = db.scalars(select(NotificationLog).order_by(NotificationLog.id.desc()).limit(100)).all()
    return {
        "email_enabled": notify.email_enabled(),
        "sms_enabled": notify.sms_enabled(),
        "admin_email": settings.ADMIN_NOTIFY_EMAIL or None,
        "admin_phone": settings.ADMIN_NOTIFY_PHONE or None,
        "sender_id": settings.SMS_SENDER_ID,
        "items": [
            {"id": r.id, "channel": r.channel, "recipient": r.recipient, "event": r.event,
             "status": r.status, "error": r.error, "created_at": r.created_at}
            for r in rows
        ],
    }


@router.post("/test")
def send_test(channel: Literal["email", "sms"]):
    """Send a test message to the admin email or phone from .env and report the provider's answer."""
    if channel == "email":
        if not notify.email_enabled():
            raise HTTPException(400, "Email is not set up. Add BREVO_API_KEY and MAIL_FROM_EMAIL to .env and restart.")
        if not settings.ADMIN_NOTIFY_EMAIL:
            raise HTTPException(400, "Add ADMIN_NOTIFY_EMAIL to .env and restart.")
        to, fn = settings.ADMIN_NOTIFY_EMAIL, lambda: notify.send_email_now(
            settings.ADMIN_NOTIFY_EMAIL, "Admin", "PRUDENT TECH test email",
            "<p>This is a test email from your PRUDENT TECH store. Email is working.</p>",
            "This is a test email from your PRUDENT TECH store. Email is working.")
    else:
        if not notify.sms_enabled():
            raise HTTPException(400, "SMS is not set up. Add ARKESEL_API_KEY to .env and restart.")
        phone = notify.gh_phone(settings.ADMIN_NOTIFY_PHONE)
        if not phone:
            raise HTTPException(400, "Add a valid ADMIN_NOTIFY_PHONE (like 0533169524) to .env and restart.")
        to, fn = phone, lambda: notify.send_sms_now(phone, "PRUDENT TECH: test SMS. Your store SMS is working.")
    try:
        fn()
    except Exception as ex:
        notify.record(channel, to, "test", "failed", str(ex))
        raise HTTPException(502, f"The provider refused the message: {ex}")
    notify.record(channel, to, "test", "sent")
    return {"ok": True, "sent_to": to}
