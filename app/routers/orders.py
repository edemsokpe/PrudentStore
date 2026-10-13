import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import flash, notify, paystack
from ..config import settings
from ..database import get_db
from ..models import Address, Cart, FlashRedemption, FlashSaleItem, Order, OrderItem, Payment, Product, User
from ..pricing import make_quote, q
from ..schemas_shop import OrderCreate, OrderOut
from ..security import get_current_user

router = APIRouter(prefix="/orders", tags=["Orders"])
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _order_no(db: Session) -> str:
    while True:
        no = "PT" + "".join(secrets.choice(ALPHABET) for _ in range(8))
        if not db.scalar(select(Order.id).where(Order.order_no == no)):
            return no


def load_order(db: Session, order_no: str, user: User | None = None) -> Order:
    stmt = select(Order).where(Order.order_no == order_no).options(selectinload(Order.items), selectinload(Order.payments))
    if user is not None:
        stmt = stmt.where(Order.user_id == user.id)
    order = db.scalar(stmt)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


def restore_stock(db: Session, order: Order):
    flash.release(db, order)
    pids = sorted({i.product_id for i in order.items if i.product_id})
    if not pids:
        return
    products = {
        p.id: p
        for p in db.scalars(select(Product).where(Product.id.in_(pids)).order_by(Product.id).with_for_update())
    }
    for it in order.items:
        if it.product_id in products:
            products[it.product_id].stock += it.quantity


def start_paystack(db: Session, order: Order, email: str) -> str:
    ref = f"{order.order_no}-{uuid.uuid4().hex[:8]}"
    url = paystack.initialize(
        email, order.total, ref, f"{settings.FRONTEND_URL.rstrip('/')}/order.html?no={order.order_no}"
    )
    db.add(Payment(order_id=order.id, method="paystack", provider_ref=ref, amount=order.total, status="pending"))
    db.commit()
    return url


@router.post("", response_model=OrderOut)
def create_order(data: OrderCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if data.payment_method == "paystack" and not paystack.enabled():
        raise HTTPException(400, "Online payment is not available yet. Choose pay on delivery.")
    addr = db.get(Address, data.address_id)
    if not addr or addr.user_id != user.id:
        raise HTTPException(400, "Choose a delivery address")

    cart = db.scalar(select(Cart).where(Cart.user_id == user.id).options(selectinload(Cart.items)))
    if not cart or not cart.items:
        raise HTTPException(400, "Your cart is empty")

    ids = sorted({i.product_id for i in cart.items})
    products = {
        p.id: p
        for p in db.scalars(select(Product).where(Product.id.in_(ids)).order_by(Product.id).with_for_update())
    }

    deals = flash.active_deals(db, ids, lock=True)
    order_items, subtotal = [], q(0)
    for ci in cart.items:
        p = products.get(ci.product_id)
        if not p or not p.is_active:
            raise HTTPException(400, "An item in your cart is no longer available. Remove it and try again.")
        if p.stock < ci.quantity:
            left = f"Only {p.stock} left" if p.stock > 0 else "Out of stock"
            raise HTTPException(400, f"{left}: {p.name}. Update your cart and try again.")
        d = deals.get(p.id)
        if d and d.remaining is not None and ci.quantity > d.remaining:
            raise HTTPException(400, f"Only {d.remaining} left at the flash sale price: {p.name}. Update your cart and try again.")
        price = d.sale_price if d else p.price
        subtotal += q(price * ci.quantity)
        order_items.append((p, ci.quantity, price, d))

    pricing = make_quote(db, subtotal, addr.region, data.coupon_code)
    order = Order(
        order_no=_order_no(db),
        user_id=user.id,
        status="placed" if data.payment_method == "pay_on_delivery" else "awaiting_payment",
        subtotal=pricing["subtotal"],
        delivery_fee=pricing["delivery_fee"],
        discount=pricing["discount"],
        total=pricing["total"],
        coupon_code=pricing["coupon_code"],
        ship_name=addr.full_name, ship_phone=addr.phone, ship_region=addr.region,
        ship_city=addr.city, ship_street=addr.street,
    )
    for p, qty, price, d in order_items:
        order.items.append(OrderItem(
            product_id=p.id, name=p.name, unit_price=price, quantity=qty,
            image_url=p.images[0].url if p.images else None,
        ))
        p.stock -= qty
    if data.payment_method == "pay_on_delivery":
        order.payments.append(Payment(method="pay_on_delivery", amount=order.total, status="pending"))
    db.add(order)
    db.flush()
    for p, qty, price, d in order_items:
        if d:
            db.get(FlashSaleItem, d.item_id).sold += qty
            db.add(FlashRedemption(order_id=order.id, item_id=d.item_id, quantity=qty))
    for ci in list(cart.items):
        db.delete(ci)
    db.commit()

    url = None
    if data.payment_method == "paystack":
        try:
            url = start_paystack(db, order, user.email)
        except Exception:
            db.rollback()  # order stays "awaiting_payment"; the customer can retry from the order page
    order = load_order(db, order.order_no, user)
    if data.payment_method == "pay_on_delivery":
        notify.order_confirmed(db, order)
    out = OrderOut.model_validate(order)
    out.payment_url = url
    return out


@router.get("", response_model=list[OrderOut])
def my_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Order).where(Order.user_id == user.id)
        .options(selectinload(Order.items), selectinload(Order.payments))
        .order_by(Order.id.desc())
    ).all()


@router.get("/{order_no}", response_model=OrderOut)
def get_order(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return load_order(db, order_no, user)


@router.post("/{order_no}/pay", response_model=OrderOut)
def pay_now(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = load_order(db, order_no, user)
    if order.status != "awaiting_payment":
        raise HTTPException(400, "This order does not need payment")
    if not paystack.enabled():
        raise HTTPException(400, "Online payment is not available yet")
    try:
        url = start_paystack(db, order, user.email)
    except Exception:
        db.rollback()
        raise HTTPException(502, "Could not start payment. Please try again in a moment.")
    out = OrderOut.model_validate(load_order(db, order_no, user))
    out.payment_url = url
    return out


@router.post("/{order_no}/cancel", response_model=OrderOut)
def cancel_order(order_no: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = load_order(db, order_no, user)
    if order.status not in ("awaiting_payment", "placed"):
        raise HTTPException(400, "This order can no longer be cancelled. Contact support.")
    if any(p.status == "paid" for p in order.payments):
        raise HTTPException(400, "This order is already paid. Contact support to cancel and get a refund.")
    restore_stock(db, order)
    order.status = "cancelled"
    for p in order.payments:
        if p.status == "pending":
            p.status = "failed"
    db.commit()
    return load_order(db, order_no, user)
