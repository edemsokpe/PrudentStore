from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Order, OrderItem, Product, Review, User
from ..security import get_current_user, require_admin

router = APIRouter(tags=["Reviews"])


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(default=None, max_length=150)
    body: str | None = Field(default=None, max_length=2000)

    @field_validator("title", "body")
    @classmethod
    def blank_to_none(cls, v):
        v = (v or "").strip()
        return v or None


def author_name(full_name: str) -> str:
    parts = full_name.strip().split()
    if not parts:
        return "Customer"
    return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0].upper()}."


def review_dict(r: Review, full_name: str) -> dict:
    return {
        "id": r.id, "rating": r.rating, "title": r.title, "body": r.body,
        "author": author_name(full_name), "verified_purchase": r.verified_purchase, "created_at": r.created_at,
    }


def has_received(db: Session, user_id: int, product_id: int) -> bool:
    return bool(db.scalar(
        select(Order.id)
        .join(OrderItem, OrderItem.order_id == Order.id)
        .where(Order.user_id == user_id, Order.status == "delivered", OrderItem.product_id == product_id)
        .limit(1)
    ))


def recompute(db: Session, product_id: int):
    avg, cnt = db.execute(
        select(func.coalesce(func.avg(Review.rating), 0), func.count()).where(Review.product_id == product_id)
    ).one()
    p = db.get(Product, product_id)
    if p:
        p.rating_avg = Decimal(str(avg)).quantize(Decimal("0.01"))
        p.rating_count = cnt


# ---------- public ----------
@router.get("/reviews/product/{slug}")
def product_reviews(slug: str, page: int = Query(1, ge=1), size: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    p = db.scalar(select(Product).where(Product.slug == slug, Product.is_active.is_(True)))
    if not p:
        raise HTTPException(404, "Product not found")
    dist = {str(i): 0 for i in range(1, 6)}
    for rating, n in db.execute(select(Review.rating, func.count()).where(Review.product_id == p.id).group_by(Review.rating)).all():
        dist[str(rating)] = n
    total = sum(dist.values())
    rows = db.execute(
        select(Review, User.full_name).join(User, User.id == Review.user_id)
        .where(Review.product_id == p.id)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .offset((page - 1) * size).limit(size)
    ).all()
    return {
        "avg": float(p.rating_avg), "count": total, "distribution": dist, "total": total,
        "items": [review_dict(r, name) for r, name in rows],
    }


# ---------- customer ----------
@router.get("/reviews/mine/{product_id}")
def my_review(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.scalar(select(Review).where(Review.user_id == user.id, Review.product_id == product_id))
    return {
        "can_review": bool(r) or has_received(db, user.id, product_id),
        "review": review_dict(r, user.full_name) if r else None,
    }


@router.post("/reviews/product/{product_id}")
def save_review(product_id: int, data: ReviewIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Product, product_id):
        raise HTTPException(404, "Product not found")
    r = db.scalar(select(Review).where(Review.user_id == user.id, Review.product_id == product_id))
    if not r and not has_received(db, user.id, product_id):
        raise HTTPException(403, "Only customers who have received this product can review it")
    if r:
        r.rating, r.title, r.body = data.rating, data.title, data.body
    else:
        r = Review(user_id=user.id, product_id=product_id, rating=data.rating, title=data.title, body=data.body, verified_purchase=True)
        db.add(r)
    db.flush()
    recompute(db, product_id)
    db.commit()
    db.refresh(r)
    return review_dict(r, user.full_name)


@router.delete("/reviews/mine/{product_id}")
def delete_my_review(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.scalar(select(Review).where(Review.user_id == user.id, Review.product_id == product_id))
    if r:
        db.delete(r)
        db.flush()
        recompute(db, product_id)
        db.commit()
    return {"ok": True}


# ---------- admin ----------
@router.get("/admin/reviews", dependencies=[Depends(require_admin)])
def admin_reviews(page: int = Query(1, ge=1), size: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Review, User.full_name, User.email, Product.name, Product.slug)
        .join(User, User.id == Review.user_id).join(Product, Product.id == Review.product_id)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .offset((page - 1) * size).limit(size)
    ).all()
    return [
        {**review_dict(r, name), "author_full": name, "email": email, "product_name": pname, "product_slug": pslug}
        for r, name, email, pname, pslug in rows
    ]


@router.delete("/admin/reviews/{review_id}", dependencies=[Depends(require_admin)])
def admin_delete_review(review_id: int, db: Session = Depends(get_db)):
    r = db.get(Review, review_id)
    if not r:
        raise HTTPException(404, "Review not found")
    pid = r.product_id
    db.delete(r)
    db.flush()
    recompute(db, pid)
    db.commit()
    return {"ok": True}
