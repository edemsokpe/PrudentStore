from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from ..database import get_db
from ..models import Banner
from ..security import require_admin
from ..storage import upload_image
from ..validators import clean_link

router = APIRouter(prefix="/banners", tags=["Banners"])


class BannerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    image_url: str
    link: str | None
    sort_order: int


@router.get("", response_model=list[BannerOut])
def list_banners(db: Session = Depends(get_db)):
    return db.scalars(
        select(Banner).where(Banner.is_active.is_(True)).order_by(Banner.sort_order, Banner.id)
    ).all()


@router.post("", response_model=BannerOut, dependencies=[Depends(require_admin)])
def create_banner(
    title: str = Form(...),
    link: str | None = Form(None),
    sort_order: int = Form(0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        link = clean_link(link)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _, url = upload_image(file, folder="banners")
    b = Banner(title=title, link=link, sort_order=sort_order, image_url=url)
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


@router.delete("/{banner_id}", dependencies=[Depends(require_admin)])
def delete_banner(banner_id: int, db: Session = Depends(get_db)):
    b = db.get(Banner, banner_id)
    if not b:
        raise HTTPException(404, "Banner not found")
    db.delete(b)
    db.commit()
    return {"ok": True}
