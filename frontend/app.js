/* PRUDENT TECH store: shared helpers, header, cart drawer */
const API = window.PT_API ?? "";
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => "GH₵ " + Number(n).toLocaleString("en-GH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const initials = (name) => esc(String(name).split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase());

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const t = Auth.token();
  if (t) headers.Authorization = "Bearer " + t;
  let body = opts.body;
  if (body && typeof body === "object") { headers["Content-Type"] = "application/json"; body = JSON.stringify(body); }
  const r = await fetch(API + path, { method: opts.method || "GET", headers, body });
  if (r.status === 401 && t) Auth.clear();
  if (!r.ok) {
    let msg = "Request failed (" + r.status + ")";
    try {
      const j = await r.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d) => String(d.msg).replace(/^Value error, /, "")).join(". ");
    } catch {}
    const e = new Error(msg); e.status = r.status; throw e;
  }
  return r.json();
}

/* ---------- auth ---------- */
const Auth = {
  token() { try { return localStorage.getItem("pt_token"); } catch { return null; } },
  user() { try { return JSON.parse(localStorage.getItem("pt_user")); } catch { return null; } },
  set(t, u, fresh) { try { localStorage.setItem("pt_token", t); localStorage.setItem("pt_user", JSON.stringify(u)); if (fresh) localStorage.setItem("pt_merge", "1"); } catch {} },
  clear() { try { ["pt_token", "pt_user", "pt_cart", "pt_merge"].forEach((k) => localStorage.removeItem(k)); } catch {} window.__wish = new Set(); },
  isIn() { return !!Auth.token(); },
  logout() { Auth.clear(); location.href = "index.html"; },
};
function safeNext(n) { return n && /^[\w\-.]+\.html(\?[\w\-.=&%]*)?$/.test(n) ? n : "account.html"; }

/* ---------- wishlist ---------- */
window.__wish = new Set();
function syncHearts() {
  document.querySelectorAll("[data-wish]").forEach((b) => {
    const on = window.__wish.has(+b.dataset.wish);
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", on);
  });
}
async function loadWish() {
  if (!Auth.isIn()) return;
  try { window.__wish = new Set(await api("/me/wishlist/ids")); syncHearts(); } catch {}
}
async function toggleWish(id) {
  if (!Auth.isIn()) { location.href = "login.html?next=" + encodeURIComponent(location.pathname.split("/").pop() + location.search); return; }
  const had = window.__wish.has(id);
  try {
    await api("/me/wishlist/" + id, { method: had ? "DELETE" : "PUT" });
    had ? window.__wish.delete(id) : window.__wish.add(id);
    syncHearts();
    toast(had ? "Removed from wishlist" : "Saved to wishlist");
  } catch (e) { toast(e.message); }
}

/* ---------- cart (localStorage until the cart API is built) ---------- */
const Cart = {
  get() { try { return JSON.parse(localStorage.getItem("pt_cart")) || []; } catch { return []; } },
  save(items) { try { localStorage.setItem("pt_cart", JSON.stringify(items)); } catch {} Cart.refresh(); },
  add(p, qty = 1) {
    const items = Cart.get();
    const found = items.find((i) => i.id === p.id);
    const max = p.flash && p.flash.remaining != null ? Math.min(p.stock ?? 99, p.flash.remaining) : (p.stock ?? 99);
    if (found) found.qty = Math.min(found.qty + qty, max);
    else items.push({ id: p.id, slug: p.slug, name: p.name, price: Number(p.price), thumb: p.thumbnail, stock: max, qty: Math.min(qty, max) });
    Cart.save(items);
    Cart.push(p.id, items.find((i) => i.id === p.id).qty);
    toast("Added to cart");
  },
  push(id, qty) { if (Auth.isIn()) api("/cart/items/" + id, { method: "PUT", body: { quantity: qty } }).catch(() => {}); },
  async sync() {
    if (!Auth.isIn()) return;
    try {
      if (localStorage.getItem("pt_merge")) {
        const local = Cart.get().map((i) => ({ product_id: i.id, quantity: i.qty }));
        if (local.length) await api("/cart/merge", { method: "POST", body: { items: local } });
        localStorage.removeItem("pt_merge");
      }
      const c = await api("/cart");
      Cart.save(c.items.map((i) => ({ id: i.product_id, slug: i.slug, name: i.name, price: Number(i.price), thumb: i.thumbnail, stock: i.stock, qty: i.quantity })));
    } catch {}
  },
  setQty(id, qty) {
    let items = Cart.get();
    const it = items.find((i) => i.id === id);
    if (!it) return;
    it.qty = Math.min(qty, it.stock || 99);
    const finalQty = Math.max(it.qty, 0);
    if (it.qty < 1) items = items.filter((i) => i.id !== id);
    Cart.save(items);
    Cart.push(id, finalQty);
  },
  remove(id) { Cart.save(Cart.get().filter((i) => i.id !== id)); Cart.push(id, 0); },
  count() { return Cart.get().reduce((n, i) => n + i.qty, 0); },
  total() { return Cart.get().reduce((n, i) => n + i.qty * i.price, 0); },
  refresh() {
    document.querySelectorAll(".cart-count").forEach((el) => { const n = Cart.count(); el.textContent = n || ""; el.dataset.n = n; });
    renderDrawer();
  },
};

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 1600);
}

const ICON = {
  cart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2 3h3l2.7 12.4a2 2 0 0 0 2 1.6h7.6a2 2 0 0 0 2-1.5L21 8H6"/></svg>',
  home: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>',
  user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
  heart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-8-5.2-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 5.8-8 11-8 11z"/></svg>',
  grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
};

function mountChrome(active) {
  const q = new URLSearchParams(location.search).get("q") || "";
  document.body.insertAdjacentHTML("afterbegin", `
    <header class="site-header"><div class="wrap">
      <div class="row">
        <a class="logo" href="index.html">PRUDENT <span>TECH</span></a>
        <form class="search" action="index.html" role="search">
          <input name="q" value="${esc(q)}" placeholder="Search products" aria-label="Search products" autocomplete="off">
          <button type="submit">Search</button>
        </form>
        <a class="icon-btn" href="account.html" aria-label="Account">${ICON.user}</a>
        <button class="icon-btn" id="cartBtn" aria-label="Open cart">${ICON.cart}<span class="cart-count"></span></button>
      </div>
    </div></header>`);
  document.body.insertAdjacentHTML("beforeend", `
    <nav class="bottom-nav" aria-label="Main">
      <a href="index.html" class="${active === "home" ? "on" : ""}">${ICON.home}Home</a>
      <a href="index.html#categories">${ICON.grid}Categories</a>
      <button id="cartBtn2">${ICON.cart}Cart<span class="cart-count"></span></button>
      <a href="account.html" class="${active === "account" ? "on" : ""}">${ICON.user}Account</a>
    </nav>
    <div class="scrim" id="scrim"></div>
    <aside class="drawer" id="drawer" aria-label="Cart" aria-hidden="true">
      <header><h2>Your cart</h2><button class="link-btn" id="closeCart">Close</button></header>
      <div class="items" id="cartItems"></div>
      <footer id="cartFoot"></footer>
    </aside>
    <div class="toast" id="toast" role="status"></div>`);
  const open = () => { $("#drawer").classList.add("open"); $("#scrim").classList.add("open"); $("#drawer").setAttribute("aria-hidden", "false"); };
  const close = () => { $("#drawer").classList.remove("open"); $("#scrim").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); };
  $("#cartBtn").onclick = open; $("#cartBtn2").onclick = open;
  $("#closeCart").onclick = close; $("#scrim").onclick = close;
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  Cart.refresh();
  loadWish();
  Cart.sync();
}

function renderDrawer() {
  const box = $("#cartItems");
  if (!box) return;
  const items = Cart.get();
  if (!items.length) {
    box.innerHTML = '<div class="empty">Your cart is empty.<br>Add a product to see it here.</div>';
    $("#cartFoot").innerHTML = "";
    return;
  }
  box.innerHTML = items.map((i) => `
    <div class="citem">
      <div class="thumb">${i.thumb ? `<img src="${esc(i.thumb)}" alt="">` : initials(i.name)}</div>
      <div class="info">
        <a href="product.html?slug=${encodeURIComponent(i.slug)}">${esc(i.name)}</a>
        <div class="price" style="font-size:14px">${money(i.price)}</div>
        <div class="qty">
          <button data-dec="${i.id}" aria-label="Decrease quantity">−</button><b>${i.qty}</b><button data-inc="${i.id}" aria-label="Increase quantity">+</button>
        </div>
        <button class="rm" data-rm="${i.id}">Remove</button>
      </div>
    </div>`).join("");
  $("#cartFoot").innerHTML = `
    <div class="total-row"><span>Subtotal</span><span>${money(Cart.total())}</span></div>
    <button class="btn-primary" id="goCheckout">Checkout</button>
    <small>Delivery fee and coupons are added at checkout.</small>`;
  $("#goCheckout").onclick = () => { location.href = Auth.isIn() ? "checkout.html" : "login.html?next=checkout.html"; };
  box.querySelectorAll("[data-inc]").forEach((b) => (b.onclick = () => Cart.setQty(+b.dataset.inc, (Cart.get().find((i) => i.id === +b.dataset.inc)?.qty || 0) + 1)));
  box.querySelectorAll("[data-dec]").forEach((b) => (b.onclick = () => Cart.setQty(+b.dataset.dec, (Cart.get().find((i) => i.id === +b.dataset.dec)?.qty || 0) - 1)));
  box.querySelectorAll("[data-rm]").forEach((b) => (b.onclick = () => Cart.remove(+b.dataset.rm)));
}

/* ---------- countdown (uses the server clock offset, not the phone's clock) ---------- */
function startCountdown(el, targetIso, offsetMs, onEnd) {
  const target = new Date(targetIso).getTime();
  const pad = (n) => String(n).padStart(2, "0");
  const tick = () => {
    let s = Math.floor((target - (Date.now() + offsetMs)) / 1000);
    if (s <= 0) { el.textContent = "00:00:00"; clearInterval(id); if (onEnd) onEnd(); return; }
    const d = Math.floor(s / 86400); s %= 86400;
    el.textContent = (d ? d + "d " : "") + pad(Math.floor(s / 3600)) + ":" + pad(Math.floor((s % 3600) / 60)) + ":" + pad(s % 60);
  };
  const id = setInterval(tick, 1000);
  tick();
  return id;
}

/* ---------- stars ---------- */
const starsBar = (avg) => `<span class="stars-bar" role="img" aria-label="${Number(avg).toFixed(1)} out of 5 stars"><i style="width:${Math.max(0, Math.min(100, (Number(avg) / 5) * 100))}%">★★★★★</i>★★★★★</span>`;

/* ---------- product card ---------- */
window.__products = {};
function productCard(p) {
  window.__products[p.id] = p;
  const out = p.stock < 1;
  const stars = p.rating_count ? `<div class="stars">${starsBar(p.rating_avg)} (${p.rating_count})</div>` : "";
  const fl = p.flash;
  const flashBits = !fl ? "" : fl.sold_out ? '<div class="stock-note out">Flash deal sold out</div>'
    : `<div class="flash-tag">Flash sale</div>${fl.limit ? `<div class="fbar" role="img" aria-label="${fl.sold} of ${fl.limit} sold"><i style="width:${Math.min(100, (fl.sold / fl.limit) * 100)}%"></i></div><div class="stock-note">${fl.remaining} left at this price</div>` : ""}`;
  const note = out ? '<div class="stock-note out">Out of stock</div>' : p.stock <= 5 ? `<div class="stock-note">Only ${p.stock} left</div>` : "";
  return `
  <article class="pcard">
    <a href="product.html?slug=${encodeURIComponent(p.slug)}" class="img">${p.thumbnail ? `<img loading="lazy" src="${esc(p.thumbnail)}" alt="${esc(p.name)}">` : initials(p.name)}</a>
    <button class="heart" data-wish="${p.id}" aria-label="Save to wishlist" aria-pressed="false">${ICON.heart}</button>
    ${p.discount_percent ? `<span class="badge-discount">-${p.discount_percent}%</span>` : ""}
    <div class="body">
      <a href="product.html?slug=${encodeURIComponent(p.slug)}" class="name">${esc(p.name)}</a>
      <div><span class="price">${money(p.price)}</span></div>
      ${p.old_price && p.discount_percent ? `<div class="old">${money(p.old_price)}</div>` : ""}
      ${flashBits}${stars}${note}
      <button class="add" data-add="${p.id}" ${out ? "disabled" : ""}>${out ? "Out of stock" : "Add to cart"}</button>
    </div>
  </article>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-add]");
  if (b) { const p = window.__products[+b.dataset.add]; if (p) Cart.add(p); }
  const w = e.target.closest("[data-wish]");
  if (w) toggleWish(+w.dataset.wish);
});
let _hs; new MutationObserver(() => { clearTimeout(_hs); _hs = setTimeout(syncHearts, 50); }).observe(document.documentElement, { childList: true, subtree: true });


/* ---------- orders helpers ---------- */
const STATUS = { awaiting_payment: "Awaiting payment", placed: "Placed", packed: "Packed", shipped: "Shipped", delivered: "Delivered", cancelled: "Cancelled" };
const fmtDate = (d) => new Date(d).toLocaleDateString("en-GH", { day: "numeric", month: "short", year: "numeric" });
