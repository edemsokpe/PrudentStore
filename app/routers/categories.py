from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Category, Brand
from ..schemas import CategoryIn, CategoryOut, BrandIn, BrandOut
from ..security import require_admin
from ..storage import upload_image

router = APIRouter(tags=["Categories & Brands"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    """Top-level categories with their subcategories nested."""
    return db.scalars(
        select(Category).where(Category.parent_id.is_(None)).order_by(Category.sort_order, Category.name)
    ).all()


@router.post("/categories", response_model=CategoryOut, dependencies=[Depends(require_admin)])
def create_category(data: CategoryIn, db: Session = Depends(get_db)):
    if db.scalar(select(Category.id).where(Category.slug == data.slug)):
        raise HTTPException(400, "This slug is already used by another category")
    cat = Category(**data.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.put("/categories/{cat_id}", response_model=CategoryOut, dependencies=[Depends(require_admin)])
def update_category(cat_id: int, data: CategoryIn, db: Session = Depends(get_db)):
    cat = db.get(Category, cat_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    if data.parent_id == cat_id:
        raise HTTPException(400, "A category cannot be its own parent")
    clash = db.scalar(select(Category.id).where(Category.slug == data.slug, Category.id != cat_id))
    if clash:
        raise HTTPException(400, "This slug is already used by another category")
    for k, v in data.model_dump().items():
        setattr(cat, k, v)
    db.commit()
    db.refresh(cat)
    return cat


@router.post("/categories/{cat_id}/image", response_model=CategoryOut, dependencies=[Depends(require_admin)])
def set_category_image(cat_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    cat = db.get(Category, cat_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    _, url = upload_image(file, folder="categories")
    cat.image_url = url
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/categories/{cat_id}", dependencies=[Depends(require_admin)])
def delete_category(cat_id: int, db: Session = Depends(get_db)):
    cat = db.get(Category, cat_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    db.delete(cat)
    db.commit()
    return {"ok": True}


@router.get("/brands", response_model=list[BrandOut])
def list_brands(db: Session = Depends(get_db)):
    return db.scalars(select(Brand).order_by(Brand.name)).all()


@router.post("/brands", response_model=BrandOut, dependencies=[Depends(require_admin)])
def create_brand(data: BrandIn, db: Session = Depends(get_db)):
    if db.scalar(select(Brand.id).where((Brand.name == data.name) | (Brand.slug == data.slug))):
        raise HTTPException(400, "This brand already exists")
    brand = Brand(**data.model_dump())
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand
