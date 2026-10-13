from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, computed_field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategoryIn(BaseModel):
    name: str
    slug: str
    parent_id: int | None = None
    sort_order: int = 0


class CategoryOut(ORM):
    id: int
    name: str
    slug: str
    parent_id: int | None
    image_url: str | None
    children: list["CategoryOut"] = []


class BrandIn(BaseModel):
    name: str
    slug: str


class BrandOut(ORM):
    id: int
    name: str
    slug: str


class ImageOut(ORM):
    id: int
    url: str
    sort_order: int


class ProductIn(BaseModel):
    name: str
    slug: str
    description: str | None = None
    specs: dict = {}
    price: Decimal
    old_price: Decimal | None = None
    stock: int = 0
    sku: str | None = None
    category_id: int | None = None
    brand_id: int | None = None
    is_active: bool = True
    is_featured: bool = False


class FlashInfo(BaseModel):
    starts_at: datetime
    ends_at: datetime
    now: datetime  # server clock when this was built, so the countdown does not trust the phone's clock
    limit: int | None = None
    sold: int = 0
    remaining: int | None = None
    sold_out: bool = False


class ProductCard(ORM):
    id: int
    name: str
    slug: str
    price: Decimal
    old_price: Decimal | None
    stock: int
    rating_avg: Decimal
    rating_count: int
    images: list[ImageOut] = []
    flash: FlashInfo | None = None

    @computed_field
    @property
    def discount_percent(self) -> int:
        if self.old_price and self.old_price > self.price:
            return int(round((self.old_price - self.price) / self.old_price * 100))
        return 0

    @computed_field
    @property
    def thumbnail(self) -> str | None:
        return self.images[0].url if self.images else None


class ProductDetail(ProductCard):
    description: str | None
    specs: dict
    sku: str | None
    is_featured: bool
    category: CategoryOut | None = None
    brand: BrandOut | None = None


class ProductPage(BaseModel):
    items: list[ProductCard]
    total: int
    page: int
    size: int


# ---------- Accounts ----------
import re
from pydantic import Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _clean_email(v: str) -> str:
    v = v.strip().lower()
    if not EMAIL_RE.match(v):
        raise ValueError("Enter a valid email address")
    return v


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str
    phone: str | None = Field(default=None, max_length=30)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        return _clean_email(v)


class LoginIn(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.strip().lower()


class UserOut(ORM):
    id: int
    full_name: str
    email: str
    phone: str | None
    role: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = Field(default=None, max_length=30)


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class AddressIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    region: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=2, max_length=80)
    street: str = Field(min_length=3, max_length=255)
    is_default: bool = False


class AddressOut(ORM):
    id: int
    full_name: str
    phone: str
    region: str
    city: str
    street: str
    is_default: bool


class ForgotIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def lower_email(cls, v: str) -> str:
        return v.strip().lower()


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=2000)
    new_password: str = Field(min_length=8, max_length=128)
