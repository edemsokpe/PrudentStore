# Putting PRUDENT TECH Store online (Render + Neon + Cloudflare R2)

One GitHub repo, one Render web service. It serves the store, the admin dashboard (`/admin/`) and the API from the same address, so there is no separate frontend site and no CORS setup.

## 1. GitHub
Push this folder to a **private** repo. `.gitignore` keeps your `.env` out. Never commit keys.

## 2. Neon (database)
Create a project and copy the connection string (it ends with `?sslmode=require`). Paste it as `DATABASE_URL` as it is. Tables are created automatically on the first start.

## 3. Cloudflare R2 (images)
- Keep the bucket from development, or make a new one, with public access.
- `r2.dev` links work for testing but Cloudflare rate-limits them. For the live shop, connect a custom domain to the bucket and use that as `R2_PUBLIC_URL`.

## 4. Render
New > Web Service > your repo (or use `render.yaml`).
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips "*"`
- Health check path: `/health`
- Environment variables (see `.env.example`): `ENV=production`, `SECRET_KEY` (a long random value), `DATABASE_URL`, `FRONTEND_URL` (your Render address, no trailing slash), the five `R2_*` values, and later `PAYSTACK_SECRET_KEY`, `BREVO_API_KEY`, `MAIL_FROM_EMAIL`, `ARKESEL_API_KEY`, `SMS_SENDER_ID`, `ADMIN_NOTIFY_EMAIL`, `ADMIN_NOTIFY_PHONE`.
- On the live site the app refuses to start if `SECRET_KEY` is short or `FRONTEND_URL` still points to localhost. Read the Render log if a deploy fails.
- `/docs` is hidden when `ENV=production`.

## 5. Create your admin account
From your own computer, pointing at the live database (PowerShell):
```
$env:DATABASE_URL="your-neon-connection-string"
python create_admin.py
```
(macOS/Linux: `DATABASE_URL="..." python create_admin.py`.) Then open `https://your-site/admin/` and log in.

## 6. Switch on real payments, email and SMS
- **Paystack:** finish business verification, then put the **live** secret key in `PAYSTACK_SECRET_KEY`. In the Paystack dashboard set the webhook URL to `https://your-site/payments/paystack/webhook`. The log warns you if a test key is still in use.
- **Brevo:** verify your sending domain (SPF and DKIM records) so emails do not land in spam.
- **Arkesel:** get the sender ID approved and keep SMS credit topped up.
- In the dashboard open **Messages** and press the two test buttons.

## 7. Free plan warning (read before launching)
Render's free web service goes to sleep after 15 minutes without visitors and takes about a minute to wake up. While it sleeps, the unpaid-order cleanup does not run and the first customer waits. Options:
- Upgrade the service to the paid Starter plan (about $7 a month, check Render's pricing page). This is what I recommend for a real shop.
- Or use a free uptime monitor (for example UptimeRobot) to open `https://your-site/health` every 5 minutes. A single always-on free service fits inside Render's 750 free hours a month, but this is a workaround.
Neon's free database does not expire like Render's free Postgres does.

## 8. Smoke test after the first deploy
1. `https://your-site/health` shows `{"ok": true}`.
2. Log in to `/admin/`. Add a category and a product with images.
3. Open the store on your phone. Browse, search, open the product.
4. Create a customer account. Add to cart, check out with **pay on delivery**. Check the email and SMS arrive.
5. In admin, move the order through packed, shipped, delivered. Check the customer can leave a review.
6. Try **Mobile Money** with Paystack (test key first), including paying and cancelling.
7. Try "Forgot password".
8. Place an order and cancel it: the stock should come back.

## 9. Backups
Export the database regularly (replace the address with your Neon string):
```
pg_dump "your-neon-connection-string" -Fc -f backup-YYYY-MM-DD.dump
```
Keep copies somewhere other than your laptop. R2 images are not in this dump, so keep the bucket safe too.

## 10. Later: database migrations
The app creates missing tables on start, which is fine for launch. It does not change existing tables. The first time you need a new column, set up Alembic (`alembic stamp head` for the existing database) instead of editing tables by hand.
