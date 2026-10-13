"""Cancels unpaid online orders after a timeout and returns their stock."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import notify, paystack
from .config import settings
from .database import SessionLocal
from .models import Order
from .routers.orders import restore_stock
from .routers.payments import settle

log = logging.getLogger("expiry")


def expire_unpaid_orders(batch: int = 50) -> int:
    """Cancel 'awaiting_payment' orders older than the timeout. Returns how many were cancelled.

    Before cancelling, every pending Paystack payment is checked with Paystack, so a customer who paid
    but never came back to the site keeps their order. If Paystack cannot be reached, the order is
    left alone and checked again on the next run.
    """
    if settings.ORDER_PAYMENT_TIMEOUT_MINUTES <= 0:
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.ORDER_PAYMENT_TIMEOUT_MINUTES)
    cancelled = 0
    with SessionLocal() as db:
        orders = db.scalars(
            select(Order)
            .where(Order.status == "awaiting_payment", Order.created_at < cutoff)
            .options(selectinload(Order.items), selectinload(Order.payments))
            .order_by(Order.id)
            .limit(batch)
            .with_for_update(skip_locked=True)
        ).all()
        for order in orders:
            try:
                if paystack.enabled():
                    pending = [p for p in order.payments if p.method == "paystack" and p.status == "pending" and p.provider_ref]
                    for pay in pending:
                        try:
                            data = paystack.verify(pay.provider_ref)
                        except httpx.HTTPStatusError as e:
                            if e.response.status_code != 404:  # 404 = Paystack never saw this payment
                                raise
                            continue
                        settle(db, pay, data)  # marks the order placed if the customer did pay
                db.refresh(order, with_for_update=True)
                if order.status != "awaiting_payment":
                    db.commit()
                    continue
                restore_stock(db, order)
                order.status = "cancelled"
                for p in order.payments:
                    if p.status == "pending":
                        p.status = "failed"
                db.commit()
                notify.order_status(db, order, "cancelled", reason="we did not receive your payment in time")
                cancelled += 1
            except Exception:
                db.rollback()
                log.exception("Could not expire order %s", order.order_no)
    return cancelled


async def expiry_loop():
    while True:
        try:
            n = await asyncio.to_thread(expire_unpaid_orders)
            if n:
                log.info("Cancelled %s unpaid order(s)", n)
        except Exception:
            log.exception("Expiry run failed")
        await asyncio.sleep(max(60, settings.EXPIRY_CHECK_SECONDS))
