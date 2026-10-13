import asyncio
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (registers tables)
from .config import check_production_settings, settings
from .database import Base, SessionLocal, engine, get_db
from .expiry import expiry_loop
from .pricing import seed_delivery_zones
from .routers import (
    account, admin_catalog, admin_notify, admin_shop, auth, banners, cart, categories,
    orders, payments, products, reviews,
)
from .routers import flash as flash_routes

log = logging.getLogger("app")
mimetypes.add_type("application/manifest+json", ".webmanifest")
check_production_settings()  # stops the live site from starting with unsafe settings

Base.metadata.create_all(bind=engine)
with SessionLocal() as _db:
    seed_delivery_zones(_db)

PROD = settings.is_production
MAX_BODY = settings.MAX_BODY_MB * 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(expiry_loop())
    yield
    task.cancel()


# On the live site the interactive API pages are hidden, so strangers cannot browse the API map.
app = FastAPI(
    title="PRUDENT TECH Store", version="1.0.0", lifespan=lifespan,
    docs_url=None if PROD else "/docs", redoc_url=None, openapi_url=None if PROD else "/openapi.json",
)

# The store and the API are served from the same address, so CORS is only needed when the pages are
# opened from another address (for example a local test server). "*" is ignored on the live site.
_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
if PROD and "*" in _origins:
    _origins = []
app.add_middleware(
    CORSMiddleware, allow_origins=_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def protect(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY:
        return JSONResponse({"detail": f"That upload is too large (limit {settings.MAX_BODY_MB} MB)"}, status_code=413)
    response = await call_next(request)
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if PROD:
        h["Strict-Transport-Security"] = "max-age=31536000"
    if request.url.path in ("/sw.js", "/manifest.webmanifest"):
        h["Cache-Control"] = "no-cache"  # phones must always check for a newer service worker
    if h.get("content-type", "").startswith("application/json"):
        h["Cache-Control"] = "no-store"  # account, cart and order data must never be cached
    return response


app.include_router(categories.router)
app.include_router(products.router)
app.include_router(banners.router)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(payments.router)
app.include_router(admin_shop.router)
app.include_router(admin_catalog.router)
app.include_router(reviews.router)
app.include_router(admin_notify.router)
app.include_router(flash_routes.router)


@app.get("/health", include_in_schema=False)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception:
        log.exception("Health check failed")
        return JSONResponse({"ok": False}, status_code=503)


# The storefront and the admin dashboard (frontend/ folder) are served by this same app.
# Mounted last, so every API route above wins; pages end in .html and never clash with API paths.
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="site")
