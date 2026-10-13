from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Coupon, DeliveryZone

REGIONS = ["Greater Accra", "Ashanti", "Western", "Western North", "Central", "Eastern", "Volta", "Oti",
           "Northern", "Savannah", "North East", "Upper East", "Upper West", "Bono", "Bono East", "Ahafo"]
ZERO = Decimal("0.00")


def q(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def seed_delivery_zones(db: Session):
    """Placeholder fees (GH₵). Change them with PUT /admin/delivery/{region}."""
    if db.scalar(select(DeliveryZone.id)):
        return
    for r in REGIONS:
        db.add(DeliveryZone(region=r, fee=Decimal("25.00") if r == "Greater Accra" else Decimal("45.00")))
    db.commit()


def delivery_fee(db: Session, region: str) -> Decimal:
    z = db.scalar(select(DeliveryZone).where(DeliveryZone.region == region))
    return q(z.fee) if z else q(Decimal(str(settings.DEFAULT_DELIVERY_FEE)))


def find_coupon(db: Session, code: str, subtotal: Decimal):
    c = db.scalar(select(Coupon).where(func.lower(Coupon.code) == code.strip().lower()))
    if not c or not c.is_active:
        raise HTTPException(400, "This coupon code is not valid")
    if c.expires_at and c.expires_at < datetime.now(timezone.utc):
        raise HTTPException(400, "This coupon has expired")
    if c.min_order and subtotal < c.min_order:
        raise HTTPException(400, f"Spend at least GH₵ {c.min_order:.2f} to use this coupon")
    if c.percent_off:
        d = subtotal * Decimal(c.percent_off) / Decimal(100)
    elif c.amount_off:
        d = Decimal(c.amount_off)
    else:
        d = ZERO
    return c, q(min(d, subtotal))


def make_quote(db: Session, subtotal: Decimal, region: str | None, coupon_code: str | None) -> dict:
    fee = delivery_fee(db, region) if region else ZERO
    discount, code = ZERO, None
    if coupon_code and coupon_code.strip():
        c, discount = find_coupon(db, coupon_code, subtotal)
        code = c.code
    return {
        "subtotal": q(subtotal),
        "delivery_fee": fee,
        "discount": discount,
        "total": q(subtotal - discount + fee),
        "coupon_code": code,
    }
