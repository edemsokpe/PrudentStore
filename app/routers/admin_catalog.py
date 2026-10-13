from datetime import datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Banner, Brand, Order, Payment, Product, User
from ..schemas import ImageOut
from ..security import require_admin
from ..validators import clean_link

router = APIRouter(prefix="/admin", tags=["Admin: dashboard data"], dependencies=[Depends(require_admin)])


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AdminProduct(ORM):
    id: int
    name: str
    slug: str
    description: str | None
    specs: dict
    price: Decimal
    old_price: Decimal | None
    stock: int
    sku: str | None
    category_id: int | None
    brand_id: int | None
    is_active: bool
    is_featured: bool
    images: list[ImageOut] = []


class AdminProductPage(BaseModel):
    items: list[AdminProduct]
    total: int


@router.get("/products", response_model=AdminProductPage)
def admin_products(
    q: str | None = None,
    low_stock: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    stmt = select(Product)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if low_stock:
        stmt = stmt.where(Product.stock <= 5)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(
        stmt.options(selectinload(Product.images)).order_by(Product.id.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return {"items": items, "total": total}


@router.get("/products/{product_id}", response_model=AdminProduct)
def admin_product(product_id: int, db: Session = Depends(get_db)):
    p = db.scalar(select(Product).where(Product.id == product_id).options(selectinload(Product.images)))
    if not p:
        raise HTTPException(404, "Product not found")
    return p


# ---------- overview ----------
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    revenue = db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "paid"))
    by_status = {s: n for s, n in db.execute(select(Order.status, func.count()).group_by(Order.status)).all()}
    start_today = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)
    low = db.execute(
        select(Product.id, Product.name, Product.stock)
        .where(Product.is_active.is_(True), Product.stock <= 5)
        .order_by(Product.stock, Product.id)
        .limit(10)
    ).all()
    return {
        "revenue": float(revenue),
        "orders_total": sum(by_status.values()),
        "orders_today": db.scalar(select(func.count()).select_from(Order).where(Order.created_at >= start_today)),
        "by_status": by_status,
        "customers": db.scalar(select(func.count()).select_from(User).where(User.role == "customer")),
        "products": db.scalar(select(func.count()).select_from(Product).where(Product.is_active.is_(True))),
        "refunds_needed": db.scalar(select(func.count()).select_from(Payment).where(Payment.status == "refund_needed")),
        "low_stock": [{"id": r[0], "name": r[1], "stock": r[2]} for r in low],
    }


# ---------- customers ----------
@router.get("/customers")
def customers(q: str | None = None, page: int = Query(1, ge=1), size: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    counts = select(Order.user_id, func.count().label("n"), func.coalesce(func.sum(Order.total), 0).label("spent")).where(
        Order.status != "cancelled"
    ).group_by(Order.user_id).subquery()
    stmt = (
        select(User, func.coalesce(counts.c.n, 0), func.coalesce(counts.c.spent, 0))
        .outerjoin(counts, counts.c.user_id == User.id)
        .where(User.role == "customer")
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like), User.phone.ilike(like)))
    rows = db.execute(stmt.order_by(User.id.desc()).offset((page - 1) * size).limit(size)).all()
    return [
        {"id": u.id, "full_name": u.full_name, "email": u.email, "phone": u.phone,
         "is_active": u.is_active, "created_at": u.created_at, "orders": n, "spent": float(spent)}
        for u, n, spent in rows
    ]


@router.put("/customers/{user_id}/active")
def set_customer_active(user_id: int, active: bool, db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u or u.role != "customer":
        raise HTTPException(404, "Customer not found")
    u.is_active = active
    db.commit()
    return {"ok": True, "is_active": u.is_active}


# ---------- banners ----------
class BannerAdmin(ORM):
    id: int
    title: str
    image_url: str
    link: str | None
    sort_order: int
    is_active: bool


class BannerEdit(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    link: str | None = None
    sort_order: int = 0
    is_active: bool = True

    @field_validator("link")
    @classmethod
    def safe_link(cls, v):
        return clean_link(v)


@router.get("/banners", response_model=list[BannerAdmin])
def admin_banners(db: Session = Depends(get_db)):
    return db.scalars(select(Banner).order_by(Banner.sort_order, Banner.id)).all()


@router.put("/banners/{banner_id}", response_model=BannerAdmin)
def edit_banner(banner_id: int, data: BannerEdit, db: Session = Depends(get_db)):
    b = db.get(Banner, banner_id)
    if not b:
        raise HTTPException(404, "Banner not found")
    b.title, b.link, b.sort_order, b.is_active = data.title, data.link, data.sort_order, data.is_active
    db.commit()
    db.refresh(b)
    return b


# ---------- brands ----------
@router.delete("/brands/{brand_id}")
def delete_brand(brand_id: int, db: Session = Depends(get_db)):
    b = db.get(Brand, brand_id)
    if not b:
        raise HTTPException(404, "Brand not found")
    db.delete(b)
    db.commit()
    return {"ok": True}
