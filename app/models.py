from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import (
    String, Text, Integer, Numeric, Boolean, DateTime, ForeignKey, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .config import settings
from .database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------- Accounts ----------
class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="customer")  # customer | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    addresses: Mapped[list["Address"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Address(Base):
    __tablename__ = "addresses"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30))
    region: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(80))
    street: Mapped[str] = mapped_column(String(255))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User] = relationship(back_populates="addresses")


# ---------- Catalog ----------
class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    image_url: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    children: Mapped[list["Category"]] = relationship()


class Brand(Base):
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)


class Product(Base, TimestampMixin):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    slug: Mapped[str] = mapped_column(String(280), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    specs: Mapped[dict] = mapped_column(JSONB, default=dict)  # {"RAM": "8GB", "Storage": "256GB"}
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    sku: Mapped[str | None] = mapped_column(String(60), unique=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), index=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False)
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category | None] = relationship()
    brand: Mapped[Brand | None] = relationship()
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.sort_order"
    )
    variants: Mapped[list["Variant"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductImage(Base):
    __tablename__ = "product_images"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    r2_key: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    product: Mapped[Product] = relationship(back_populates="images")


class Variant(Base):
    __tablename__ = "variants"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(120))  # e.g. "Black / 128GB"
    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    product: Mapped[Product] = relationship(back_populates="variants")


# ---------- Shopping ----------
class Wishlist(Base):
    __tablename__ = "wishlists"
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))


class Cart(Base):
    __tablename__ = "carts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    items: Mapped[list["CartItem"]] = relationship(back_populates="cart", cascade="all, delete-orphan")


class CartItem(Base):
    __tablename__ = "cart_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("carts.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("variants.id", ondelete="SET NULL"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    cart: Mapped[Cart] = relationship(back_populates="items")


class Coupon(Base):
    __tablename__ = "coupons"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    percent_off: Mapped[int | None] = mapped_column(Integer)
    amount_off: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    min_order: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Order(Base, TimestampMixin):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_no: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="placed")  # placed|packed|shipped|delivered|cancelled
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    coupon_code: Mapped[str | None] = mapped_column(String(40))
    ship_name: Mapped[str] = mapped_column(String(120))
    ship_phone: Mapped[str] = mapped_column(String(30))
    ship_region: Mapped[str] = mapped_column(String(80))
    ship_city: Mapped[str] = mapped_column(String(80))
    ship_street: Mapped[str] = mapped_column(String(255))
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="order", cascade="all, delete-orphan")

    @property
    def pay_by(self) -> datetime | None:
        """Deadline for paying an online order, or None when it does not apply."""
        m = settings.ORDER_PAYMENT_TIMEOUT_MINUTES
        if self.status != "awaiting_payment" or m <= 0 or not self.created_at:
            return None
        return self.created_at + timedelta(minutes=m)


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255))  # snapshot at purchase time
    image_url: Mapped[str | None] = mapped_column(String(500))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity: Mapped[int] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped["Product | None"] = relationship()

    @property
    def product_slug(self) -> str | None:
        return self.product.slug if self.product else None


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(30))  # pay_on_delivery | momo | card
    provider_ref: Mapped[str | None] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|paid|failed|refunded
    order: Mapped[Order] = relationship(back_populates="payments")


class Review(Base, TimestampMixin):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("user_id", "product_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # 1-5
    title: Mapped[str | None] = mapped_column(String(150))
    body: Mapped[str | None] = mapped_column(Text)
    verified_purchase: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------- Marketing ----------
class Banner(Base):
    __tablename__ = "banners"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    image_url: Mapped[str] = mapped_column(String(500))
    link: Mapped[str | None] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DeliveryZone(Base):
    __tablename__ = "delivery_zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(80), unique=True)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(10))  # email | sms
    recipient: Mapped[str] = mapped_column(String(160))
    event: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(10))  # sent | failed
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class FlashSale(Base):
    __tablename__ = "flash_sales"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    items: Mapped[list["FlashSaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")


class FlashSaleItem(Base):
    __tablename__ = "flash_sale_items"
    __table_args__ = (UniqueConstraint("sale_id", "product_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("flash_sales.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity_limit: Mapped[int | None] = mapped_column(Integer)  # None = limited only by stock
    sold: Mapped[int] = mapped_column(Integer, default=0)
    sale: Mapped[FlashSale] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class FlashRedemption(Base):
    """Which order bought how many units at a flash price, so a cancelled order can give them back."""
    __tablename__ = "flash_redemptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("flash_sale_items.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer)
