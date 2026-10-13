import hashlib
import hmac
from decimal import Decimal

import httpx

from .config import settings

BASE = "https://api.paystack.co"


def enabled() -> bool:
    return bool(settings.PAYSTACK_SECRET_KEY)


def _headers():
    return {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}


def pesewas(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).to_integral_value())


def initialize(email: str, amount: Decimal, reference: str, callback_url: str) -> str:
    r = httpx.post(
        f"{BASE}/transaction/initialize",
        headers=_headers(),
        json={
            "email": email,
            "amount": pesewas(amount),
            "currency": "GHS",
            "reference": reference,
            "callback_url": callback_url,
            "channels": ["mobile_money", "card"],
        },
        timeout=20,
    )
    r.raise_for_status()
    body = r.json()
    if not body.get("status"):
        raise RuntimeError(body.get("message", "Paystack error"))
    return body["data"]["authorization_url"]


def verify(reference: str) -> dict:
    r = httpx.get(f"{BASE}/transaction/verify/{reference}", headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json()["data"]


def valid_signature(raw_body: bytes, header: str | None) -> bool:
    if not header or not settings.PAYSTACK_SECRET_KEY:
        return False
    expected = hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, header)
