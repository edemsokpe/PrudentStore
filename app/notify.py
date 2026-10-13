"""Order emails (Brevo) and SMS (Arkesel). Fire-and-forget: a failure is logged, never breaks an order."""
import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import httpx

from .config import settings
from .database import SessionLocal
from .models import NotificationLog, User

log = logging.getLogger("notify")
_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="notify")
e = html.escape


# ---------- configuration ----------
def email_enabled() -> bool:
    return bool(settings.BREVO_API_KEY and settings.MAIL_FROM_EMAIL)


def sms_enabled() -> bool:
    return bool(settings.ARKESEL_API_KEY)


def gh_phone(raw: str | None) -> str | None:
    """Ghana number to international format without '+': 0533169524 -> 233533169524."""
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("233") and len(d) == 12:
        return d
    if d.startswith("0") and len(d) == 10:
        return "233" + d[1:]
    if len(d) == 9:
        return "233" + d
    return None


# ---------- providers ----------
def send_email_now(to_email: str, to_name: str, subject: str, html_body: str, text_body: str) -> None:
    r = httpx.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json", "content-type": "application/json"},
        json={
            "sender": {"name": settings.MAIL_FROM_NAME, "email": settings.MAIL_FROM_EMAIL},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "subject": subject,
            "htmlContent": html_body,
            "textContent": text_body,
        },
        timeout=20,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"Brevo {r.status_code}: {r.text[:200]}")


def send_sms_now(phone: str, message: str) -> None:
    r = httpx.post(
        "https://sms.arkesel.com/api/v2/sms/send",
        headers={"api-key": settings.ARKESEL_API_KEY},
        json={"sender": settings.SMS_SENDER_ID, "message": message, "recipients": [phone]},
        timeout=20,
    )
    try:
        body = r.json()
        status = str(body.get("status", "success")).lower()
        invalid = any(isinstance(d, dict) and d.get("invalid numbers") for d in (body.get("data") or []))
    except Exception:
        status, invalid = "success", False
    if r.status_code >= 300 or status not in ("success", "ok"):
        raise RuntimeError(f"Arkesel {r.status_code}: {r.text[:200]}")
    if invalid:
        raise RuntimeError("Arkesel rejected the phone number as invalid")


# ---------- logging + background jobs ----------
def record(channel: str, recipient: str, event: str, status: str, error: str | None = None) -> None:
    try:
        with SessionLocal() as db:
            db.add(NotificationLog(channel=channel, recipient=recipient[:160], event=event, status=status, error=(error or None) and error[:480]))
            db.commit()
    except Exception:
        log.exception("Could not write notification log")


def _job_email(event, to_email, to_name, subject, html_body, text_body):
    if not email_enabled() or not to_email:
        return
    try:
        send_email_now(to_email, to_name, subject, html_body, text_body)
        record("email", to_email, event, "sent")
    except Exception as ex:
        log.warning("Email failed: %s", ex)
        record("email", to_email, event, "failed", str(ex))


def _job_sms(event, raw_phone, message):
    if not sms_enabled():
        return
    phone = gh_phone(raw_phone)
    if not phone:
        record("sms", str(raw_phone or "")[:160], event, "failed", "Invalid phone number")
        return
    try:
        send_sms_now(phone, message)
        record("sms", phone, event, "sent")
    except Exception as ex:
        log.warning("SMS failed: %s", ex)
        record("sms", phone, event, "failed", str(ex))


def _email(event, to_email, to_name, subject, html_body, text_body):
    _pool.submit(_job_email, event, to_email, to_name, subject, html_body, text_body)


def _sms(event, phone, message):
    _pool.submit(_job_sms, event, phone, message)


# ---------- templates ----------
def _money(x) -> str:
    return f"GH₵ {Decimal(x):,.2f}"


def _sms_money(x) -> str:
    return f"GHS {Decimal(x):,.2f}"  # the cedi sign would force costly Unicode SMS


def _snap(db, order) -> dict:
    user = db.get(User, order.user_id)
    return {
        "no": order.order_no, "total": Decimal(order.total), "subtotal": Decimal(order.subtotal),
        "delivery": Decimal(order.delivery_fee), "discount": Decimal(order.discount), "coupon": order.coupon_code,
        "items": [{"name": i.name, "qty": i.quantity, "line": Decimal(i.unit_price) * i.quantity} for i in order.items],
        "ship_name": order.ship_name, "ship_phone": order.ship_phone, "ship_city": order.ship_city,
        "ship_region": order.ship_region, "ship_street": order.ship_street,
        "email": user.email if user else None, "name": user.full_name if user else order.ship_name,
        "cod": any(p.method == "pay_on_delivery" for p in order.payments),
    }


def _wrap(heading: str, inner: str, button: tuple[str, str] | None = None) -> str:
    btn = (f'<p style="margin:22px 0 4px"><a href="{e(button[1])}" style="display:inline-block;background:#1a5be0;color:#ffffff;'
           f'padding:12px 22px;border-radius:10px;text-decoration:none;font-weight:bold">{e(button[0])}</a></p>') if button else ""
    return f"""<div style="background:#f3f7ff;padding:24px 12px;font-family:Arial,Helvetica,sans-serif;color:#14213d">
<div style="max-width:560px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #dbe4f5">
<div style="background:#1a5be0;color:#ffffff;padding:18px 22px;font-size:20px;font-weight:bold">PRUDENT TECH</div>
<div style="padding:22px;font-size:15px;line-height:1.55"><h2 style="margin:0 0 10px;font-size:20px;color:#0b2a6f">{e(heading)}</h2>{inner}{btn}</div></div>
<p style="text-align:center;color:#6b7a99;font-size:12px;margin:14px 0 0">You are receiving this because you have an account or an order at PRUDENT TECH.</p></div>"""


def _order_html(s: dict, heading: str, intro: str) -> str:
    rows = "".join(
        f'<tr><td style="padding:8px 0;border-bottom:1px solid #dbe4f5">{e(i["name"])} &times; {i["qty"]}</td>'
        f'<td align="right" style="padding:8px 0;border-bottom:1px solid #dbe4f5">{_money(i["line"])}</td></tr>' for i in s["items"]
    )
    disc = f'<tr><td style="padding:3px 0">Coupon {e(s["coupon"] or "")}</td><td align="right">-{_money(s["discount"])}</td></tr>' if s["discount"] else ""
    inner = (
        f'<p style="margin:0 0 14px">{intro}</p>'
        f'<p style="margin:0 0 6px;color:#6b7a99">Order <b style="color:#14213d">{e(s["no"])}</b></p>'
        f'<table width="100%" cellspacing="0" cellpadding="0" style="font-size:14px">{rows}'
        f'<tr><td style="padding:8px 0 3px">Subtotal</td><td align="right" style="padding-top:8px">{_money(s["subtotal"])}</td></tr>{disc}'
        f'<tr><td style="padding:3px 0">Delivery</td><td align="right">{_money(s["delivery"])}</td></tr>'
        f'<tr><td style="padding:8px 0;font-weight:bold;font-size:16px">Total</td><td align="right" style="font-weight:bold;font-size:16px">{_money(s["total"])}</td></tr></table>'
        f'<p style="margin:16px 0 0"><b>Delivering to</b><br>{e(s["ship_name"])}<br>{e(s["ship_street"])}, {e(s["ship_city"])}, {e(s["ship_region"])}<br>{e(s["ship_phone"])}</p>'
    )
    url = f"{settings.FRONTEND_URL.rstrip('/')}/order.html?no={s['no']}"
    return _wrap(heading, inner, ("View your order", url))


def _order_text(s: dict, heading: str, intro_text: str) -> str:
    lines = "\n".join(f"- {i['name']} x {i['qty']}: {_sms_money(i['line'])}" for i in s["items"])
    return (f"{heading}\n\n{intro_text}\n\nOrder {s['no']}\n{lines}\nTotal: {_sms_money(s['total'])}\n\n"
            f"Delivering to: {s['ship_name']}, {s['ship_street']}, {s['ship_city']}, {s['ship_region']}\n"
            f"{settings.FRONTEND_URL.rstrip('/')}/order.html?no={s['no']}")


def _safe(fn):
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except Exception:
            log.exception("Notification skipped because of an error")
    return wrapper


# ---------- public API (call inside a request; never raises) ----------
@_safe
def order_confirmed(db, order, paid: bool = False) -> None:
    """Customer confirmation + an alert to the shop owner. Call when an order becomes 'placed'."""
    s = _snap(db, order)
    total, total_sms = _money(s["total"]), _sms_money(s["total"])
    if paid:
        heading = "Payment received"
        intro_html = f"Thank you! We received your payment of <b>{total}</b>. We are getting your order ready."
        intro_text = f"Thank you! We received your payment of {total_sms}. We are getting your order ready."
        sms = f"PRUDENT TECH: Payment received for order {s['no']} ({total_sms}). Thank you! We are preparing it."
    else:
        heading = "Order confirmed"
        intro_html = f"Thank you for your order! You will pay <b>{total}</b> when it is delivered."
        intro_text = f"Thank you for your order! You will pay {total_sms} when it is delivered."
        sms = f"PRUDENT TECH: Order {s['no']} confirmed. Total {total_sms}, pay on delivery. Thank you!"
    _email("order_confirmed", s["email"], s["name"], f"{heading}: order {s['no']}", _order_html(s, heading, intro_html), _order_text(s, heading, intro_text))
    _sms("order_confirmed", s["ship_phone"], sms)

    # alert for the owner
    n = sum(i["qty"] for i in s["items"])
    pay = "paid online" if paid else "pay on delivery"
    alert = f"New order {s['no']}: {total_sms}, {n} item(s), {pay}, {s['ship_region']}. Phone {s['ship_phone']}."
    if settings.ADMIN_NOTIFY_EMAIL:
        _email("admin_new_order", settings.ADMIN_NOTIFY_EMAIL, "Admin", f"New order {s['no']}",
               _wrap("New order", f"<p>{e(alert)}</p>", ("Open dashboard", settings.FRONTEND_URL.rstrip("/") + "/admin/")), alert)
    if settings.ADMIN_NOTIFY_PHONE:
        _sms("admin_new_order", settings.ADMIN_NOTIFY_PHONE, alert)


@_safe
def order_status(db, order, status: str, reason: str | None = None) -> None:
    """Customer message when an order is packed, shipped, delivered or cancelled."""
    if status not in ("packed", "shipped", "delivered", "cancelled"):
        return
    s = _snap(db, order)
    no = s["no"]
    if status == "packed":
        heading, line, sms = "We are packing your order", "Your order is packed and will be handed to our rider soon.", None
    elif status == "shipped":
        heading, line = "Your order is on its way", f"Your order is on its way to {s['ship_city']}. Please keep your phone on so our rider can reach you."
        sms = f"PRUDENT TECH: Order {no} is on its way to {s['ship_city']}. Keep your phone on for our rider."
    elif status == "delivered":
        heading, line = "Order delivered", "Your order has been delivered. Thank you for shopping with us! You can rate your items in your account."
        sms = f"PRUDENT TECH: Order {no} delivered. Thank you for shopping with us! Rate your items in your account."
    else:
        heading = "Order cancelled"
        line = "Your order was cancelled." + (f" Reason: {reason}." if reason else "") + " Contact us if you think this is a mistake."
        sms = None
    _email(f"order_{status}", s["email"], s["name"], f"{heading}: order {no}", _order_html(s, heading, e(line)), _order_text(s, heading, line))
    if sms:
        _sms(f"order_{status}", s["ship_phone"], sms)


@_safe
def welcome(to_email: str, name: str) -> None:
    first = (name or "there").split()[0]
    inner = (f"<p>Hi {e(first)}, your account is ready. Browse phones, laptops and accessories, save items you like, "
             "and track your orders any time.</p>")
    _email("welcome", to_email, name, "Welcome to PRUDENT TECH", _wrap("Welcome to PRUDENT TECH", inner, ("Start shopping", settings.FRONTEND_URL.rstrip("/") + "/index.html")),
           f"Hi {first}, your PRUDENT TECH account is ready. Start shopping: {settings.FRONTEND_URL.rstrip('/')}/index.html")


@_safe
def password_reset(to_email: str, name: str, link: str, minutes: int) -> None:
    first = (name or "there").split()[0]
    inner = (f"<p>Hi {e(first)}, we received a request to reset your password. The button below works for "
             f"{minutes} minutes and can be used once.</p>"
             "<p style=\"color:#6b7a99\">If you did not ask for this, you can ignore this email. Your password will not change.</p>")
    text = (f"Hi {first}, we received a request to reset your PRUDENT TECH password.\n\n"
            f"Choose a new password here (valid for {minutes} minutes, one use): {link}\n\n"
            "If you did not ask for this, ignore this email. Your password will not change.")
    _email("password_reset", to_email, name, "Reset your PRUDENT TECH password",
           _wrap("Reset your password", inner, ("Choose a new password", link)), text)


@_safe
def password_changed(to_email: str, name: str) -> None:
    first = (name or "there").split()[0]
    forgot = settings.FRONTEND_URL.rstrip("/") + "/forgot.html"
    inner = (f"<p>Hi {e(first)}, the password on your PRUDENT TECH account was just changed.</p>"
             "<p>If this was you, there is nothing more to do. If it was not you, reset your password now and contact us.</p>")
    text = (f"Hi {first}, the password on your PRUDENT TECH account was just changed. "
            f"If this was not you, reset it now: {forgot}")
    _email("password_changed", to_email, name, "Your PRUDENT TECH password was changed",
           _wrap("Your password was changed", inner, ("Reset my password", forgot)), text)
