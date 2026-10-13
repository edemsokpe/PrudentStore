from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import notify
from ..database import get_db
from ..models import Coupon, DeliveryZone, Order
from ..schemas_shop import CouponIn, CouponOut, OrderOut, StatusIn, ZoneIn, ZoneOut
from ..security import require_admin
from .orders import load_order, restore_stock

router = APIRouter(tags=["Admin: orders, coupons, delivery"])

NEXT_STATUS = {"placed": "packed", "packed": "shipped", "shipped": "delivered"}


# ----- orders -----
@router.get("/admin/orders", response_model=list[OrderOut], dependencies=[Depends(require_admin)])
def all_orders(status: str | None = None, page: int = Query(1, ge=1), size: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    stmt = select(Order).options(selectinload(Order.items), selectinload(Order.payments)).order_by(Order.id.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    return db.scalars(stmt.offset((page - 1) * size).limit(size)).all()


@router.post("/admin/orders/expire-now", dependencies=[Depends(require_admin)])
def expire_now():
    """Run the unpaid-order cleanup immediately."""
    from ..expiry import expire_unpaid_orders
    return {"cancelled": expire_unpaid_orders()}


@router.get("/admin/orders/{order_no}", response_model=OrderOut, dependencies=[Depends(require_admin)])
def one_order(order_no: str, db: Session = Depends(get_db)):
    return load_order(db, order_no)


@router.put("/admin/orders/{order_no}/status", response_model=OrderOut, dependencies=[Depends(require_admin)])
def set_status(order_no: str, data: StatusIn, db: Session = Depends(get_db)):
    order = load_order(db, order_no)
    if data.status == "cancelled":
        if order.status not in ("awaiting_payment", "placed", "packed"):
            raise HTTPException(400, f"A {order.status} order cannot be cancelled")
        restore_stock(db, order)
        order.status = "cancelled"
        for p in order.payments:
            if p.status == "pending":
                p.status = "failed"
            elif p.status == "paid":
                p.status = "refund_needed"
    else:
        if NEXT_STATUS.get(order.status) != data.status:
            raise HTTPException(400, f"Cannot move an order from {order.status} to {data.status}")
        order.status = data.status
        if data.status == "delivered":
            for p in order.payments:
                if p.method == "pay_on_delivery" and p.status == "pending":
                    p.status = "paid"
    db.commit()
    fresh = load_order(db, order_no)
    notify.order_status(db, fresh, data.status)
    return fresh


@router.get("/admin/stats", dependencies=[Depends(require_admin)])
def stats(db: Session = Depends(get_db)):
    rows = db.execute(select(Order.status, func.count(), func.coalesce(func.sum(Order.total), 0)).group_by(Order.status)).all()
    return {r[0]: {"orders": r[1], "total": float(r[2])} for r in rows}


# ----- coupons -----
@router.get("/admin/coupons", response_model=list[CouponOut], dependencies=[Depends(require_admin)])
def list_coupons(db: Session = Depends(get_db)):
    return db.scalars(select(Coupon).order_by(Coupon.id.desc())).all()


@router.post("/admin/coupons", response_model=CouponOut, dependencies=[Depends(require_admin)])
def create_coupon(data: CouponIn, db: Session = Depends(get_db)):
    if bool(data.percent_off) == bool(data.amount_off):
        raise HTTPException(400, "Set either percent_off or amount_off, not both")
    if db.scalar(select(Coupon.id).where(func.lower(Coupon.code) == data.code.lower())):
        raise HTTPException(400, "This code already exists")
    c = Coupon(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/admin/coupons/{coupon_id}", dependencies=[Depends(require_admin)])
def delete_coupon(coupon_id: int, db: Session = Depends(get_db)):
    c = db.get(Coupon, coupon_id)
    if not c:
        raise HTTPException(404, "Coupon not found")
    db.delete(c)
    db.commit()
    return {"ok": True}


# ----- delivery fees -----
@router.get("/delivery/fees", response_model=list[ZoneOut])
def delivery_fees(db: Session = Depends(get_db)):
    return db.scalars(select(DeliveryZone).order_by(DeliveryZone.region)).all()


@router.put("/admin/delivery/{region}", response_model=ZoneOut, dependencies=[Depends(require_admin)])
def set_fee(region: str, data: ZoneIn, db: Session = Depends(get_db)):
    z = db.scalar(select(DeliveryZone).where(DeliveryZone.region == region))
    if not z:
        z = DeliveryZone(region=region, fee=data.fee)
        db.add(z)
    else:
        z.fee = data.fee
    db.commit()
    db.refresh(z)
    return z
