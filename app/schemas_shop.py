from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ----- cart -----
class CartLine(BaseModel):
    product_id: int
    slug: str
    name: str
    price: Decimal
    thumbnail: str | None
    stock: int
    quantity: int
    line_total: Decimal
    available: bool


class CartOut(BaseModel):
    items: list[CartLine]
    subtotal: Decimal
    count: int


class QtyIn(BaseModel):
    quantity: int = Field(ge=0, le=99)


class MergeItem(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=99)


class MergeIn(BaseModel):
    items: list[MergeItem] = Field(max_length=100)


class QuoteIn(BaseModel):
    region: str | None = None
    coupon_code: str | None = None


class QuoteOut(BaseModel):
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    coupon_code: str | None


# ----- orders -----
class OrderCreate(BaseModel):
    address_id: int
    payment_method: Literal["pay_on_delivery", "paystack"]
    coupon_code: str | None = None


class OrderItemOut(ORM):
    product_id: int | None
    product_slug: str | None
    name: str
    image_url: str | None
    unit_price: Decimal
    quantity: int


class PaymentOut(ORM):
    method: str
    status: str
    amount: Decimal


class OrderOut(ORM):
    order_no: str
    status: str
    subtotal: Decimal
    delivery_fee: Decimal
    discount: Decimal
    total: Decimal
    coupon_code: str | None
    ship_name: str
    ship_phone: str
    ship_region: str
    ship_city: str
    ship_street: str
    created_at: datetime
    items: list[OrderItemOut]
    payments: list[PaymentOut]
    pay_by: datetime | None = None
    payment_url: str | None = None


class StatusIn(BaseModel):
    status: Literal["packed", "shipped", "delivered", "cancelled"]


class CouponIn(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    percent_off: int | None = Field(default=None, ge=1, le=100)
    amount_off: Decimal | None = Field(default=None, gt=0)
    min_order: Decimal | None = Field(default=None, ge=0)
    expires_at: datetime | None = None
    is_active: bool = True


class CouponOut(ORM):
    id: int
    code: str
    percent_off: int | None
    amount_off: Decimal | None
    min_order: Decimal | None
    expires_at: datetime | None
    is_active: bool


class ZoneOut(ORM):
    region: str
    fee: Decimal


class ZoneIn(BaseModel):
    fee: Decimal = Field(ge=0)
