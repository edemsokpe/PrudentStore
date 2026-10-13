# PRUDENT TECH Store

Testing on your PC step by step: see `TESTING.md`. Putting it online: see `DEPLOY.md`.


## Setup (no Docker)
1. Create the database in your local PostgreSQL:  `createdb prudent_store`
2. `python -m venv venv` then activate it
3. `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and fill in your values
5. `uvicorn app.main:app --reload`
6. Open http://127.0.0.1:8000/docs

## Admin routes
Admin routes need an admin login. Create the admin once: `python create_admin.py`.
Then in /docs call POST /auth/login, copy `access_token`, click Authorize and paste it.

## R2
- Create a bucket, enable public access (r2.dev URL or custom domain), put the URL in R2_PUBLIC_URL.
- Create an API token with Object Read & Write for that bucket.

## Test flow
1. POST /categories  {"name":"Phones","slug":"phones"}
2. POST /products    {"name":"Infinix Hot 40","slug":"infinix-hot-40","price":1850,"old_price":2200,"stock":10,"category_id":1,"specs":{"RAM":"8GB"}}
3. POST /products/1/images  (choose image files)
4. GET /products?q=infinix&sort=price_asc

## Storefront (step 2)
Open `frontend/index.html` through a local server (not by double-click):
`cd frontend && python -m http.server 5500` then visit http://127.0.0.1:5500
If your API is not at http://127.0.0.1:8000, add `<script>window.PT_API="https://your-api-url"</script>` before `app.js`.
Cart is stored in the browser for now; it moves to the database in the checkout step.
Banners: POST /banners (multipart: title, link, sort_order, file) with the X-Admin-Key header.
New product filters: `on_sale=true`, `sort=discount`.

## Accounts (step 3)
- Add `SECRET_KEY` to your `.env` (see `.env.example`) and `pip install -r requirements.txt` (adds PyJWT).
- `ADMIN_API_KEY` is no longer used. Admin routes now need an admin login (see above).
- Customer endpoints: /auth/register, /auth/login, /auth/me, /auth/change-password, /me/addresses, /me/wishlist.
- Pages: login.html (log in and sign up), account.html (profile, addresses, password), wishlist.html.

## Cart and checkout (step 4)
- `.env`: add `FRONTEND_URL` (where the storefront runs), `PAYSTACK_SECRET_KEY` (leave empty to allow pay on delivery only) and `DEFAULT_DELIVERY_FEE`. Run `pip install -r requirements.txt` (adds httpx). New tables are created on startup.
- Delivery fees are seeded for the 16 regions with placeholders (GH₵ 25 Greater Accra, GH₵ 45 elsewhere). Set your real fees with `PUT /admin/delivery/{region}`.
- Paystack: use your TEST secret key first (Paystack dashboard > Settings > API Keys). After paying, Paystack sends the customer back to `FRONTEND_URL/order.html`, which confirms the payment with the server. For live use, also set the webhook URL in the Paystack dashboard to `https://YOUR-API/payments/paystack/webhook`.
- Admin APIs: `/admin/orders` (list, `PUT /admin/orders/{order_no}/status` with packed, shipped, delivered or cancelled), `/admin/coupons`, `/admin/stats`.
- Pages: checkout.html, order.html, orders.html. Guest carts merge into your account at login.

## Admin dashboard (step 5)
Open `http://127.0.0.1:5500/admin/` (same static server as the store) and log in with your admin account (`python create_admin.py`).
It manages orders, products (with images and specs), categories and brands, banners, coupons, delivery fees and customers.
If the API is not at http://127.0.0.1:8000, add `<script>window.PT_API="https://your-api-url"</script>` before `admin.js`.
Keep the admin address private; the API enforces admin-only access either way.

## Reviews and ratings (step 6)
- Only customers whose order was marked **delivered** can review that product (one review per product, editable). Every review shows a "Verified purchase" tag.
- Product ratings are recalculated on every review change and show as stars on cards and the product page.
- Delivered orders show a "Rate this product" link. Admins can remove reviews under Reviews in the dashboard.
- No new tables or settings: just restart the API.

## Unpaid order expiry (step 7)
- Online orders left unpaid are cancelled automatically after `ORDER_PAYMENT_TIMEOUT_MINUTES` (default 60) and their stock goes back on sale. Set it to 0 to turn this off.
- The server checks every `EXPIRY_CHECK_SECONDS` (default 300). Before cancelling, it asks Paystack whether the customer actually paid, so paid orders are never cancelled. If Paystack is unreachable, the order is kept and checked again later.
- If a customer pays on an old Paystack link after the order was cancelled, the payment is flagged **Refund needed** (shown on the dashboard Overview) so you can refund it in Paystack.
- The order page shows a live "pay within N minutes" notice. Admins can run the cleanup now from Orders > Cancel expired now.
- This runs inside the API process. If you run several API workers, it is still safe (orders are locked while processed).

## Email and SMS (step 8)
Messages sent automatically: welcome email (sign-up), order confirmed (email + SMS), payment received (email + SMS),
packed (email), shipped (email + SMS), delivered (email + SMS), cancelled or expired (email). You also get an email and SMS alert for every new order.

Setup (all optional; without keys the store works but sends nothing):
1. Email: create a free Brevo account, verify your sender address, create an API key. Put `BREVO_API_KEY` and `MAIL_FROM_EMAIL` in `.env`.
2. SMS: create an Arkesel account, register your sender ID (up to 11 letters/numbers), buy SMS credit, create an API key. Put `ARKESEL_API_KEY` and `SMS_SENDER_ID` in `.env`.
3. Set `ADMIN_NOTIFY_EMAIL` and `ADMIN_NOTIFY_PHONE` to receive new-order alerts.
4. Restart the API, open the dashboard > Messages and press "Send test email" and "Send test SMS".
The Messages page also lists the last 100 messages and any provider errors.
Customer SMS goes to the phone number entered on the delivery address. SMS uses "GHS" instead of the cedi sign so each message stays cheap.

## Password reset (step 9)
- "Forgot your password?" on the login page sends a reset link by email (needs the Brevo email setup above). The link works for 30 minutes and only once; it also stops working if the password changes another way.
- The reply never reveals whether an email has an account, and each address can request one link per minute.
- After a reset or a password change, the customer gets a "your password was changed" email, and old devices must log in again only when their token expires (tokens last 7 days; set a shorter ACCESS_TOKEN_MINUTES if you want).
- If email is not set up, the page tells the customer to contact the shop.
- Pages: forgot.html, reset.html. No new tables or settings.

## Flash sales (step 10)
- Dashboard > Flash sales > Create: pick a start and end time, add products with a flash price (must be lower than the normal price) and an optional quantity limit.
- While a sale is live the flash price shows everywhere (home page "flash" strip with a countdown, product page, cart, wishlist) and is what customers are charged. When it ends, or the limit sells out, prices return to normal by themselves; product prices are never edited.
- Countdowns use the server's clock, so a wrong phone clock cannot show a wrong time.
- Cancelled or expired orders give their flash units back. If a cart holds more than the flash quantity left, the cart is trimmed to what is left.
- New pages: flash.html. New tables are created on startup.

## Run everything from one server (updated)
The store, the admin dashboard and the API are now served together, so locally you only need:
`uvicorn app.main:app --reload` and open http://127.0.0.1:8000/ (store) and http://127.0.0.1:8000/admin/ (dashboard). The separate `python -m http.server 5500` is no longer needed (it still works).
Putting it online: see `DEPLOY.md`.

## Go-live hardening (step 11)
- Login, sign-up and password-reset requests are rate-limited (8 wrong passwords per 15 minutes per account and address). Unknown emails take as long to reject as real ones.
- Changing or resetting a password logs every other device out.
- With `ENV=production`: unsafe settings stop the app from starting, `/docs` is hidden, HSTS is on, and CORS "*" is ignored.
- All pages get anti-framing and no-sniff headers; account, cart and order data is never cached; uploads over `MAX_BODY_MB` (30) are refused; banner links cannot be `javascript:`.
- `/health` for Render's health check.

## Installable app / PWA (step 12)
- Customers can install the store on their phone's home screen (Android Chrome shows an Install banner; iPhone users are told to use Share > Add to Home Screen; there is also an "Install the app" card on the account page). It opens full screen with the PRUDENT TECH icon, and inner pages get a back button.
- Files: `frontend/manifest.webmanifest`, `sw.js` (service worker), `pwa.js`, `offline.html`, `icons/`.
- Offline: the app opens instantly and shows a friendly page with no connection. Pages and product lists customers already viewed stay browsable. Accounts, carts, orders, payments and the admin dashboard are never saved, and ordering needs a connection.
- It needs HTTPS (Render provides it) or `localhost`. Pages opened from a plain `http://192.168...` address will not install.
- After you change store files, edit `VERSION` in `sw.js` (for example `"v2"`) so phones clear their saved copies. Without a bump, online customers still get fresh pages (network first), but the change is safer with it.
- Test in Chrome: DevTools > Application > Manifest and Service Workers, then Lighthouse > "Progressive Web App".
