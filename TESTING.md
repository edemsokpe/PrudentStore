# Testing PRUDENT TECH Store on your PC (Windows + VS Code)

Everything runs from one server. You need Python 3.10 or newer (`python --version`), PostgreSQL running on your PC (pgAdmin), and VS Code with the Python extension. The internet is only needed for the steps marked (internet).

## 1. Open the project
1. Unzip into `C:\PRUDENT_TECH_PROJECTS\prudent_store`.
2. VS Code: File > Open Folder > choose that folder.
3. Terminal > New Terminal (PowerShell opens at the project folder).

## 2. Create an empty database
pgAdmin: right-click Databases > Create > Database > name it `prudent_store` > Save.
Do not use `students_db`; that one belongs to My_Project and already has a different `students` table.

## 3. Virtual environment and packages
```
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
- If PowerShell refuses to activate: run `Set-ExecutionPolicy -Scope Process Bypass`, then activate again (or use `venv\Scripts\activate.bat` in Command Prompt).
- In VS Code press Ctrl+Shift+P > "Python: Select Interpreter" > pick the one inside `venv`.
- Your pip uses the local wheelhouse with no internet. If pip says "No matching distribution found for X", that package is missing from `C:\PRUDENT_TECH_PROJECTS\Wheelhouse`. On a computer with internet and the same Python version, run `pip download -r requirements.txt -d Wheelhouse` and copy the new files into your wheelhouse folder, then run the install again. This project needs: fastapi, uvicorn, sqlalchemy, psycopg2-binary, pydantic-settings, python-multipart, boto3, PyJWT, httpx (and their dependencies).

## 4. Settings
```
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Open `.env` and set:
- `DATABASE_URL` : put your PostgreSQL password in place of YOUR_PASSWORD.
- `SECRET_KEY` : paste the long value printed above.
- Leave the `R2_...` sample lines as they are for now. The server starts with them; only picture uploads need real keys (internet).
- Leave `PAYSTACK_SECRET_KEY`, `BREVO_API_KEY` and `ARKESEL_API_KEY` empty. Pay on delivery works, email and SMS stay off.

## 5. Start the server
```
uvicorn app.main:app --reload
```
Success looks like `Application startup complete.` The tables are created automatically: in pgAdmin, right-click `prudent_store` > Refresh, then open Schemas > public > Tables (about 30 tables, and `delivery_zones` already holds the 16 regions).

If it fails:
| Message | Fix |
|---|---|
| `password authentication failed` | Wrong password in DATABASE_URL |
| `database "prudent_store" does not exist` | Do step 2 |
| `Field required` (pydantic ValidationError) | A line is missing or misspelled in `.env` |
| `No module named ...` | The venv is not active (step 3) |
| `Address already in use` | Another program uses port 8000; stop it or add `--port 8001` |

## 6. Quick checks (browser)
- http://127.0.0.1:8000/health shows `{"ok":true}`
- http://127.0.0.1:8000/ is the store (empty at first)
- http://127.0.0.1:8000/docs lists the API (only while ENV=development)

## 7. Create your admin account
Open a second terminal (the server keeps running in the first), activate the venv, then:
```
python create_admin.py
```
Enter an email, name and password (8+ characters).

## 8. Fill the store (http://127.0.0.1:8000/admin/)
1. Log in. Overview opens.
2. Categories: add "Phones". Brands (same page): add "Infinix".
3. Products > Add product: price 1850, old price 2200, stock 10, category and brand, a couple of specs. Pictures need internet and real R2 keys; without them the card shows the product's initials.
4. Coupons: create `WELCOME10`, 10 percent, minimum spend 100.
5. Delivery fees: check the 16 regions and set your real fees.

## 9. Shop as a customer
Use a private browser window so the admin login stays separate.
1. Home page: the product shows with a -16% badge. Try search, open the product, add to cart, change quantity in the cart drawer.
2. Create an account (Account icon > Create account). The cart you built as a guest should still be there.
3. Account > add a delivery address.
4. Checkout: apply `WELCOME10`, change the address region and watch the delivery fee change, choose Pay on delivery, Place order. The order page says Placed.
5. Admin > Orders: open it, press Mark as packed, then shipped, then delivered.
6. Customer side: the order tracker shows Delivered. Open the product > Write a review > post it. Stars appear on the product.
7. Stock: the product's stock went down by the quantity ordered. Place another order and cancel it: the stock comes back.
8. Log out > Forgot your password? (the page works, but the email needs Brevo and internet).

## 10. Flash sale
Admin > Flash sales > Create: start now, end in 1 hour, add the product with a flash price of 1500 and a limit of 2.
- Home page shows the Flash sale strip with a counting-down timer; the product page shows a banner and the 1500 price.
- Add 3 to the cart: it is trimmed to 2. Order it, then cancel it: the 2 units return.
- Edit the sale and set the end time to a minute from now: after it ends the price returns to normal by itself.

## 11. Needs internet or keys (test these later)
- Pictures, banners, category images: real R2 keys in `.env`.
- Paystack: set `PAYSTACK_SECRET_KEY=sk_test_...`. Checkout > Mobile Money or card opens Paystack; after you pay you land back on the order page, which confirms the payment. Paystack cannot call your PC's webhook; that is normal, the return page does the confirming.
- Email and SMS: Brevo and Arkesel keys, then Admin > Messages > send the two test messages. Without keys, orders still work and Messages lists the failures.

## 12. Installable app (PWA)
Open http://127.0.0.1:8000/ in Chrome (localhost counts as secure). F12 > Application > Manifest and Service Workers should show no errors, and an install icon appears in the address bar.

## 13. Try it on your phone (same Wi-Fi)
Stop the server (Ctrl+C), then:
```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
Run `ipconfig`, note the IPv4 address (for example 192.168.1.20), allow the Windows Firewall prompt, and open `http://192.168.1.20:8000` on the phone. Shopping and ordering work; installing as an app needs HTTPS, so that part is tested after hosting.

## 14. Start again from zero
Stop the server, then in pgAdmin right-click `prudent_store` > Delete, create it again (step 2) and restart the server. Tables are recreated. Run `python create_admin.py` again.

## 15. Ready for hosting when
- Steps 5 to 10 all pass.
- `.env` is not in your Git repository (`.gitignore` already skips it).
- You have the Neon database link, R2 keys and a new SECRET_KEY ready. Then follow `DEPLOY.md`.
