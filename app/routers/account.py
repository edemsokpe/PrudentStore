from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload
from .. import flash
from ..database import get_db
from ..models import Address, Product, User, Wishlist
from ..schemas import AddressIn, AddressOut, ProductCard
from ..security import get_current_user

router = APIRouter(prefix="/me", tags=["My account"])


# ---------- addresses ----------
def _own_address(db: Session, user: User, address_id: int) -> Address:
    a = db.get(Address, address_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Address not found")
    return a


def _make_default(db: Session, user: User, address: Address):
    db.execute(update(Address).where(Address.user_id == user.id).values(is_default=False))
    address.is_default = True


@router.get("/addresses", response_model=list[AddressOut])
def list_addresses(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(Address).where(Address.user_id == user.id).order_by(Address.is_default.desc(), Address.id.desc())
    ).all()


@router.post("/addresses", response_model=AddressOut)
def add_address(data: AddressIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    has_any = db.scalar(select(Address.id).where(Address.user_id == user.id))
    addr = Address(**data.model_dump(exclude={"is_default"}), user_id=user.id)
    db.add(addr)
    db.flush()
    if data.is_default or not has_any:
        _make_default(db, user, addr)
    db.commit()
    db.refresh(addr)
    return addr


@router.put("/addresses/{address_id}", response_model=AddressOut)
def update_address(address_id: int, data: AddressIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    addr = _own_address(db, user, address_id)
    for k, v in data.model_dump(exclude={"is_default"}).items():
        setattr(addr, k, v)
    if data.is_default:
        _make_default(db, user, addr)
    db.commit()
    db.refresh(addr)
    return addr


@router.post("/addresses/{address_id}/default", response_model=AddressOut)
def set_default_address(address_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    addr = _own_address(db, user, address_id)
    _make_default(db, user, addr)
    db.commit()
    db.refresh(addr)
    return addr


@router.delete("/addresses/{address_id}")
def delete_address(address_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    addr = _own_address(db, user, address_id)
    was_default = addr.is_default
    db.delete(addr)
    db.flush()
    if was_default:
        nxt = db.scalar(select(Address).where(Address.user_id == user.id).order_by(Address.id.desc()))
        if nxt:
            nxt.is_default = True
    db.commit()
    return {"ok": True}


# ---------- wishlist ----------
@router.get("/wishlist", response_model=list[ProductCard])
def get_wishlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.scalars(
        select(Product)
        .join(Wishlist, Wishlist.product_id == Product.id)
        .where(Wishlist.user_id == user.id, Product.is_active.is_(True))
        .options(selectinload(Product.images))
        .order_by(Wishlist.id.desc())
    ).all()
    return flash.apply(db, [ProductCard.model_validate(i) for i in items])


@router.get("/wishlist/ids", response_model=list[int])
def wishlist_ids(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Wishlist.product_id).where(Wishlist.user_id == user.id)).all()


@router.put("/wishlist/{product_id}")
def add_to_wishlist(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Product, product_id):
        raise HTTPException(404, "Product not found")
    exists = db.scalar(select(Wishlist.id).where(Wishlist.user_id == user.id, Wishlist.product_id == product_id))
    if not exists:
        db.add(Wishlist(user_id=user.id, product_id=product_id))
        db.commit()
    return {"ok": True}


@router.delete("/wishlist/{product_id}")
def remove_from_wishlist(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.scalar(select(Wishlist).where(Wishlist.user_id == user.id, Wishlist.product_id == product_id))
    if row:
        db.delete(row)
        db.commit()
    return {"ok": True}
