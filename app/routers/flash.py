from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..flash import Deal, info, utcnow
from ..models import FlashSale, FlashSaleItem, Product
from ..schemas import ProductCard
from ..security import require_admin

router = APIRouter(tags=["Flash sales"])


# ---------- public ----------
@router.get("/flash")
def current_flash(db: Session = Depends(get_db)):
    """Sales running now (with their products) and the next scheduled one."""
    t = utcnow()
    sales = db.scalars(
        select(FlashSale)
        .where(FlashSale.is_active.is_(True), FlashSale.starts_at <= t, FlashSale.ends_at > t)
        .order_by(FlashSale.ends_at)
        .options(selectinload(FlashSale.items).selectinload(FlashSaleItem.product).selectinload(Product.images))
    ).all()
    active = []
    for s in sales:
        cards = []
        for it in sorted(s.items, key=lambda i: i.id):
            p = it.product
            if not p or not p.is_active or it.sale_price >= p.price:
                continue
            card = ProductCard.model_validate(p)
            deal = Deal(it.id, s.id, it.sale_price, s.starts_at, s.ends_at, it.quantity_limit, it.sold)
            sold_out = deal.remaining == 0 or p.stock < 1
            if not sold_out:  # a sold-out deal shows the normal price, because that is what it would cost
                card.old_price = max(card.old_price or card.price, card.price)
                card.price = it.sale_price
            card.flash = info(deal, t, sold_out=sold_out)
            cards.append(card.model_dump(mode="json"))
        if cards:
            active.append({"id": s.id, "title": s.title, "starts_at": s.starts_at, "ends_at": s.ends_at, "items": cards})
    nxt = db.scalar(
        select(FlashSale).where(FlashSale.is_active.is_(True), FlashSale.starts_at > t).order_by(FlashSale.starts_at).limit(1)
    )
    return {
        "server_time": t,
        "active": active,
        "upcoming": {"title": nxt.title, "starts_at": nxt.starts_at} if nxt else None,
    }


# ---------- admin ----------
class FlashItemIn(BaseModel):
    product_id: int
    sale_price: Decimal = Field(gt=0)
    quantity_limit: int | None = Field(default=None, ge=1)


class FlashIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    starts_at: datetime
    ends_at: datetime
    is_active: bool = True
    items: list[FlashItemIn] = Field(min_length=1, max_length=60)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _status(s: FlashSale) -> str:
    t = utcnow()
    if not s.is_active:
        return "off"
    if t < s.starts_at:
        return "scheduled"
    return "ended" if t >= s.ends_at else "live"


def _out(s: FlashSale) -> dict:
    return {
        "id": s.id, "title": s.title, "starts_at": s.starts_at, "ends_at": s.ends_at,
        "is_active": s.is_active, "status": _status(s),
        "items": [
            {"product_id": i.product_id, "name": i.product.name, "price": i.product.price,
             "sale_price": i.sale_price, "quantity_limit": i.quantity_limit, "sold": i.sold}
            for i in sorted(s.items, key=lambda x: x.id)
        ],
    }


def _load(db: Session, sale_id: int) -> FlashSale:
    s = db.scalar(
        select(FlashSale).where(FlashSale.id == sale_id)
        .options(selectinload(FlashSale.items).selectinload(FlashSaleItem.product))
    )
    if not s:
        raise HTTPException(404, "Flash sale not found")
    return s


def _validate(db: Session, data: FlashIn) -> dict[int, Product]:
    if _aware(data.ends_at) <= _aware(data.starts_at):
        raise HTTPException(400, "The end time must be after the start time")
    ids = [i.product_id for i in data.items]
    if len(set(ids)) != len(ids):
        raise HTTPException(400, "A product can only be added once")
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))}
    for it in data.items:
        p = products.get(it.product_id)
        if not p:
            raise HTTPException(400, "One of the products no longer exists")
        if it.sale_price >= p.price:
            raise HTTPException(400, f"The flash price for {p.name} must be lower than its normal price (GH₵ {p.price:.2f})")
    return products


@router.get("/admin/flash", dependencies=[Depends(require_admin)])
def list_flash(db: Session = Depends(get_db)):
    sales = db.scalars(
        select(FlashSale).order_by(FlashSale.starts_at.desc())
        .options(selectinload(FlashSale.items).selectinload(FlashSaleItem.product))
    ).all()
    return [_out(s) for s in sales]


@router.post("/admin/flash", dependencies=[Depends(require_admin)])
def create_flash(data: FlashIn, db: Session = Depends(get_db)):
    _validate(db, data)
    s = FlashSale(title=data.title.strip(), starts_at=_aware(data.starts_at), ends_at=_aware(data.ends_at), is_active=data.is_active)
    for it in data.items:
        s.items.append(FlashSaleItem(product_id=it.product_id, sale_price=it.sale_price, quantity_limit=it.quantity_limit))
    db.add(s)
    db.commit()
    return _out(_load(db, s.id))


@router.put("/admin/flash/{sale_id}", dependencies=[Depends(require_admin)])
def update_flash(sale_id: int, data: FlashIn, db: Session = Depends(get_db)):
    s = _load(db, sale_id)
    _validate(db, data)
    s.title, s.starts_at, s.ends_at, s.is_active = data.title.strip(), _aware(data.starts_at), _aware(data.ends_at), data.is_active
    existing = {i.product_id: i for i in s.items}
    wanted = {i.product_id for i in data.items}
    for pid, item in existing.items():
        if pid not in wanted:
            db.delete(item)
    for it in data.items:
        row = existing.get(it.product_id)
        if row:
            if it.quantity_limit is not None and it.quantity_limit < row.sold:
                raise HTTPException(400, f"{row.product.name}: {row.sold} already sold, so the limit cannot be lower than that")
            row.sale_price, row.quantity_limit = it.sale_price, it.quantity_limit
        else:
            s.items.append(FlashSaleItem(product_id=it.product_id, sale_price=it.sale_price, quantity_limit=it.quantity_limit))
    db.commit()
    db.expire_all()
    return _out(_load(db, sale_id))


@router.delete("/admin/flash/{sale_id}", dependencies=[Depends(require_admin)])
def delete_flash(sale_id: int, db: Session = Depends(get_db)):
    s = _load(db, sale_id)
    db.delete(s)
    db.commit()
    return {"ok": True}
