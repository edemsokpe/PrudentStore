from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import flash
from ..database import get_db
from ..models import Cart, CartItem, Product, User
from ..pricing import make_quote, q
from ..schemas_shop import CartOut, MergeIn, QtyIn, QuoteIn, QuoteOut
from ..security import get_current_user

router = APIRouter(tags=["Cart"])


def _cart(db: Session, user: User) -> Cart:
    cart = db.scalar(select(Cart).where(Cart.user_id == user.id).options(selectinload(Cart.items)))
    if not cart:
        cart = Cart(user_id=user.id)
        db.add(cart)
        db.flush()
        db.refresh(cart)
    return cart


def cart_view(db: Session, user: User) -> dict:
    cart = _cart(db, user)
    ids = [i.product_id for i in cart.items]
    products = {}
    if ids:
        products = {
            p.id: p
            for p in db.scalars(select(Product).where(Product.id.in_(ids)).options(selectinload(Product.images)))
        }
    deals = flash.active_deals(db, ids)
    lines, subtotal, count = [], Decimal("0"), 0
    for ci in cart.items:
        p = products.get(ci.product_id)
        if not p or not p.is_active:
            continue
        d = deals.get(p.id)
        price = d.sale_price if d else p.price
        cap = p.stock if d is None or d.remaining is None else min(p.stock, d.remaining)
        available = p.stock > 0
        qty = min(ci.quantity, cap) if available else ci.quantity
        if available and qty < ci.quantity:
            ci.quantity = qty  # saved with the next commit, so checkout matches what the customer sees
        line_total = q(price * qty) if available else Decimal("0.00")
        if available:
            subtotal += line_total
            count += qty
        lines.append({
            "product_id": p.id, "slug": p.slug, "name": p.name, "price": price,
            "thumbnail": p.images[0].url if p.images else None,
            "stock": cap, "quantity": qty, "line_total": line_total, "available": available,
        })
    return {"items": lines, "subtotal": q(subtotal), "count": count}


@router.get("/cart", response_model=CartOut)
def get_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    view = cart_view(db, user)
    db.commit()
    return view


@router.put("/cart/items/{product_id}", response_model=CartOut)
def set_quantity(product_id: int, data: QtyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = _cart(db, user)
    item = next((i for i in cart.items if i.product_id == product_id), None)
    if data.quantity == 0:
        if item:
            db.delete(item)
    else:
        p = db.get(Product, product_id)
        if not p or not p.is_active:
            raise HTTPException(404, "Product not found")
        if p.stock < 1:
            raise HTTPException(400, "This product is out of stock")
        d = flash.active_deals(db, [product_id]).get(product_id)
        cap = p.stock if d is None or d.remaining is None else min(p.stock, d.remaining)
        qty = min(data.quantity, cap)
        if item:
            item.quantity = qty
        else:
            db.add(CartItem(cart_id=cart.id, product_id=product_id, quantity=qty))
    db.commit()
    return cart_view(db, user)


@router.delete("/cart", response_model=CartOut)
def clear_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cart = _cart(db, user)
    for i in list(cart.items):
        db.delete(i)
    db.commit()
    return cart_view(db, user)


@router.post("/cart/merge", response_model=CartOut)
def merge_cart(data: MergeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Called once after login: adds the guest cart from this device, keeping the larger quantity."""
    cart = _cart(db, user)
    existing = {i.product_id: i for i in cart.items}
    for m in data.items:
        p = db.get(Product, m.product_id)
        if not p or not p.is_active or p.stock < 1:
            continue
        qty = min(m.quantity, p.stock)
        if m.product_id in existing:
            existing[m.product_id].quantity = max(existing[m.product_id].quantity, qty)
        else:
            db.add(CartItem(cart_id=cart.id, product_id=m.product_id, quantity=qty))
    db.commit()
    return cart_view(db, user)


@router.post("/checkout/quote", response_model=QuoteOut)
def quote(data: QuoteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    view = cart_view(db, user)
    return make_quote(db, view["subtotal"], data.region, data.coupon_code)
