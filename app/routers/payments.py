import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import notify, paystack
from ..database import get_db
from ..models import Order, Payment, User
from ..security import get_current_user

router = APIRouter(prefix="/payments/paystack", tags=["Payments"])


def settle(db: Session, payment: Payment, data: dict) -> None:
    """Apply a Paystack transaction result. Safe to call many times for the same payment."""
    if payment.status == "paid":
        return
    order = db.get(Order, payment.order_id)
    confirmed = False
    status = data.get("status")
    if status == "success":
        if data.get("amount") != paystack.pesewas(payment.amount) or data.get("currency") != "GHS":
            payment.status = "failed"  # amount mismatch: never mark paid
        elif order.status == "cancelled" or any(p.status == "paid" for p in order.payments if p.id != payment.id):
            payment.status = "refund_needed"  # paid after cancel, or paid twice
        else:
            payment.status = "paid"
            if order.status == "awaiting_payment":
                order.status = "placed"
                confirmed = True
    elif status in ("failed", "abandoned", "reversed"):
        payment.status = "failed"
    db.commit()
    if confirmed:
        notify.order_confirmed(db, order, paid=True)


@router.get("/verify")
def verify_payment(reference: str = Query(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.scalar(select(Payment).where(Payment.provider_ref == reference).with_for_update())
    order = db.get(Order, payment.order_id) if payment else None
    if not payment or order.user_id != user.id:
        raise HTTPException(404, "Payment not found")
    if payment.status == "pending":
        try:
            settle(db, payment, paystack.verify(reference))
        except Exception:
            raise HTTPException(502, "Could not confirm the payment yet. Refresh this page in a moment.")
    return {"order_no": order.order_no, "payment_status": payment.status, "order_status": order.status}


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if not paystack.valid_signature(raw, request.headers.get("x-paystack-signature")):
        raise HTTPException(401, "Invalid signature")
    event = json.loads(raw)
    if event.get("event") == "charge.success":
        data = event.get("data", {})
        payment = db.scalar(select(Payment).where(Payment.provider_ref == data.get("reference")).with_for_update())
        if payment:
            settle(db, payment, data)
    return {"ok": True}
