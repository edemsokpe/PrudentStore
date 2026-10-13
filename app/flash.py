"""Flash-sale pricing. The sale price is applied on top of the normal price when read; products are never edited."""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FlashRedemption, FlashSale, FlashSaleItem, Product
from .schemas import FlashInfo


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Deal:
    item_id: int
    sale_id: int
    sale_price: Decimal
    starts_at: datetime
    ends_at: datetime
    limit: int | None
    sold: int

    @property
    def remaining(self) -> int | None:
        return None if self.limit is None else max(self.limit - self.sold, 0)


def active_deals(db: Session, product_ids, lock: bool = False) -> dict[int, Deal]:
    """Live, not-sold-out flash deals for these products (the lowest price wins if several overlap)."""
    ids = list({i for i in product_ids})
    if not ids:
        return {}
    t = utcnow()
    stmt = (
        select(FlashSaleItem, FlashSale)
        .join(FlashSale, FlashSale.id == FlashSaleItem.sale_id)
        .join(Product, Product.id == FlashSaleItem.product_id)
        .where(
            FlashSaleItem.product_id.in_(ids),
            FlashSale.is_active.is_(True), FlashSale.starts_at <= t, FlashSale.ends_at > t,
            FlashSaleItem.sale_price < Product.price,  # ignore a deal that is no longer a discount
        )
        .order_by(FlashSaleItem.id)
    )
    if lock:
        stmt = stmt.with_for_update(of=FlashSaleItem)
    best: dict[int, Deal] = {}
    for item, sale in db.execute(stmt).all():
        d = Deal(item.id, sale.id, item.sale_price, sale.starts_at, sale.ends_at, item.quantity_limit, item.sold)
        if d.remaining == 0:
            continue
        cur = best.get(item.product_id)
        if cur is None or d.sale_price < cur.sale_price:
            best[item.product_id] = d
    return best


def info(d: Deal, now: datetime | None = None, sold_out: bool = False) -> FlashInfo:
    return FlashInfo(starts_at=d.starts_at, ends_at=d.ends_at, now=now or utcnow(), limit=d.limit,
                     sold=d.sold, remaining=d.remaining, sold_out=sold_out)


def apply(db: Session, cards: list) -> list:
    """Show flash prices on product cards or details (ProductCard / ProductDetail objects)."""
    deals = active_deals(db, [c.id for c in cards])
    now = utcnow()
    for c in cards:
        d = deals.get(c.id)
        if d:
            c.old_price = max(c.old_price or c.price, c.price)
            c.price = d.sale_price
            c.flash = info(d, now)
    return cards


def release(db: Session, order) -> None:
    """Give flash-sale units back when an order is cancelled."""
    for r in db.scalars(select(FlashRedemption).where(FlashRedemption.order_id == order.id)).all():
        item = db.get(FlashSaleItem, r.item_id)
        if item:
            item.sold = max(0, item.sold - r.quantity)
        db.delete(r)
