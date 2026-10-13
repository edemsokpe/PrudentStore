from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, selectinload
from .. import flash
from ..database import get_db
from ..models import Product, ProductImage
from ..schemas import ProductIn, ProductCard, ProductDetail, ProductPage, ImageOut
from ..security import require_admin
from ..storage import upload_image, delete_image

router = APIRouter(prefix="/products", tags=["Products"])

SORTS = {
    "newest": Product.created_at.desc(),
    "price_asc": Product.price.asc(),
    "price_desc": Product.price.desc(),
    "rating": Product.rating_avg.desc(),
    "discount": ((Product.old_price - Product.price) / Product.old_price).desc().nullslast(),
}


def _check_unique(db: Session, data: ProductIn, exclude_id: int | None = None):
    q = select(Product.id).where(Product.slug == data.slug)
    if exclude_id:
        q = q.where(Product.id != exclude_id)
    if db.scalar(q):
        raise HTTPException(400, "This slug is already used by another product")
    if data.sku:
        q = select(Product.id).where(Product.sku == data.sku)
        if exclude_id:
            q = q.where(Product.id != exclude_id)
        if db.scalar(q):
            raise HTTPException(400, "This SKU is already used by another product")


@router.get("", response_model=ProductPage)
def list_products(
    q: str | None = None,
    category_id: int | None = None,
    brand_id: int | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    in_stock: bool = False,
    featured: bool = False,
    on_sale: bool = False,
    sort: str = "newest",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=60),
    db: Session = Depends(get_db),
):
    stmt = select(Product).where(Product.is_active.is_(True))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.description.ilike(like)))
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if brand_id:
        stmt = stmt.where(Product.brand_id == brand_id)
    if min_price is not None:
        stmt = stmt.where(Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
    if in_stock:
        stmt = stmt.where(Product.stock > 0)
    if featured:
        stmt = stmt.where(Product.is_featured.is_(True))
    if on_sale:
        stmt = stmt.where(Product.old_price.is_not(None), Product.old_price > Product.price)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(
        stmt.options(selectinload(Product.images))
        .order_by(SORTS.get(sort, SORTS["newest"]))
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    cards = flash.apply(db, [ProductCard.model_validate(i) for i in items])
    return {"items": cards, "total": total, "page": page, "size": size}


@router.get("/{slug}", response_model=ProductDetail)
def get_product(slug: str, db: Session = Depends(get_db)):
    p = db.scalar(
        select(Product)
        .where(Product.slug == slug, Product.is_active.is_(True))
        .options(selectinload(Product.images), selectinload(Product.category), selectinload(Product.brand))
    )
    if not p:
        raise HTTPException(404, "Product not found")
    return flash.apply(db, [ProductDetail.model_validate(p)])[0]


@router.post("", response_model=ProductDetail, dependencies=[Depends(require_admin)])
def create_product(data: ProductIn, db: Session = Depends(get_db)):
    _check_unique(db, data)
    p = Product(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/{product_id}", response_model=ProductDetail, dependencies=[Depends(require_admin)])
def update_product(product_id: int, data: ProductIn, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    _check_unique(db, data, exclude_id=product_id)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{product_id}", dependencies=[Depends(require_admin)])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    for img in p.images:
        delete_image(img.r2_key)
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/{product_id}/images", response_model=list[ImageOut], dependencies=[Depends(require_admin)])
def add_images(product_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    start = len(p.images)
    new = []
    for i, f in enumerate(files):
        key, url = upload_image(f, folder="products")
        img = ProductImage(product_id=p.id, r2_key=key, url=url, sort_order=start + i)
        db.add(img)
        new.append(img)
    db.commit()
    for img in new:
        db.refresh(img)
    return new


@router.delete("/images/{image_id}", dependencies=[Depends(require_admin)])
def remove_image(image_id: int, db: Session = Depends(get_db)):
    img = db.get(ProductImage, image_id)
    if not img:
        raise HTTPException(404, "Image not found")
    delete_image(img.r2_key)
    db.delete(img)
    db.commit()
    return {"ok": True}
