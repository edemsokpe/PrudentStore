/* PRUDENT TECH admin dashboard */
const API = window.PT_API ?? "";
const TK = "pt_admin_token";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const money = (n) => "GH₵ " + Number(n).toLocaleString("en-GH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmt = (d) => new Date(d).toLocaleString("en-GH", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
const slugify = (s) => s.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
const initials = (n) => esc(String(n).split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase());
const getTok = () => { try { return localStorage.getItem(TK); } catch { return null; } };
const setTok = (t) => { try { t ? localStorage.setItem(TK, t) : localStorage.removeItem(TK); } catch {} };

function toast(msg, err) {
  const t = $("#toast");
  t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.className = ""), 2200);
}

async function api(path, opts = {}) {
  const headers = {};
  const t = getTok();
  if (t) headers.Authorization = "Bearer " + t;
  let body = opts.body;
  if (body && !(body instanceof FormData) && typeof body === "object") { headers["Content-Type"] = "application/json"; body = JSON.stringify(body); }
  let r;
  try { r = await fetch(API + path, { method: opts.method || "GET", headers, body }); }
  catch { throw new Error("Cannot reach the server at " + API); }
  if (r.status === 401 && t) { setTok(null); showLogin(); throw new Error("Please log in again"); }
  if (!r.ok) {
    let msg = "Request failed (" + r.status + ")";
    try {
      const j = await r.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = j.detail.map((d) => (d.loc ? d.loc[d.loc.length - 1] + ": " : "") + String(d.msg).replace(/^Value error, /, "")).join(". ");
    } catch {}
    throw new Error(msg);
  }
  return r.json();
}

/* ---------- dialog ---------- */
const dlg = $("#dlg");
function openDlg(title, html) { $("#dlgTitle").textContent = title; $("#dlgBody").innerHTML = html; if (!dlg.open) dlg.showModal(); return $("#dlgBody"); }
function closeDlg() { if (dlg.open) dlg.close(); }
$("#dlgClose").onclick = closeDlg;
dlg.addEventListener("click", (e) => { if (e.target === dlg) closeDlg(); });

/* ---------- login ---------- */
function showLogin() { $("#shell").hidden = true; $("#login").hidden = false; }
$("#loginForm").onsubmit = async (e) => {
  e.preventDefault();
  const msg = $("#lMsg"); msg.textContent = "";
  const btn = e.target.querySelector("button"); btn.disabled = true;
  try {
    const r = await api("/auth/login", { method: "POST", body: { email: $("#lEmail").value, password: $("#lPass").value } });
    if (r.user.role !== "admin") throw new Error("This account is not an admin account");
    setTok(r.access_token);
    start();
  } catch (er) { msg.textContent = er.message; }
  btn.disabled = false;
};
$("#logout").onclick = () => { setTok(null); showLogin(); };

/* ---------- shared helpers ---------- */
const STATUS = { awaiting_payment: "Awaiting payment", placed: "Placed", packed: "Packed", shipped: "Shipped", delivered: "Delivered", cancelled: "Cancelled" };
const PAY = { pending: "Not paid", paid: "Paid", failed: "Failed", refund_needed: "Refund needed", refunded: "Refunded" };
const statusBadge = (s) => `<span class="badge ${s === "delivered" ? "solid" : s === "cancelled" ? "grey" : s === "awaiting_payment" ? "warn" : ""}">${STATUS[s] || esc(s)}</span>`;
const payBadge = (s) => `<span class="badge ${s === "paid" ? "solid" : s === "refund_needed" ? "bad" : s === "pending" ? "warn" : "grey"}">${PAY[s] || esc(s)}</span>`;
const thumb = (url, name) => `<div class="thumb">${url ? `<img src="${esc(url)}" alt="" loading="lazy">` : initials(name)}</div>`;
const nullIf = (v) => (v === "" || v == null ? null : v);

function flatCats(list, depth = 0, out = []) {
  list.forEach((c) => { out.push({ id: c.id, name: c.name, depth, parent_id: c.parent_id, slug: c.slug, image_url: c.image_url }); flatCats(c.children || [], depth + 1, out); });
  return out;
}
async function lookups() {
  const [cats, brands] = await Promise.all([api("/categories"), api("/brands")]);
  return { cats: flatCats(cats), brands };
}
const catOptions = (cats, sel, skipId) => '<option value="">None</option>' + cats.filter((c) => c.id !== skipId).map((c) => `<option value="${c.id}" ${c.id === sel ? "selected" : ""}>${"— ".repeat(c.depth)}${esc(c.name)}</option>`).join("");

/* ---------- views ---------- */
let token = 0;
const NAV = [["overview", "Overview"], ["orders", "Orders"], ["products", "Products"], ["catalog", "Categories"], ["banners", "Banners"], ["coupons", "Coupons"], ["flash", "Flash sales"], ["delivery", "Delivery fees"], ["reviews", "Reviews"], ["notifications", "Messages"], ["customers", "Customers"]];
const VIEWS = {};

/* Overview */
VIEWS.overview = async (el) => {
  const [o, recent] = await Promise.all([api("/admin/overview"), api("/admin/orders?size=6")]);
  const toProcess = (o.by_status.placed || 0) + (o.by_status.packed || 0);
  el.innerHTML = `
    <div class="cards">
      <div class="card"><div class="k">Revenue (paid)</div><div class="v">${money(o.revenue)}</div></div>
      <div class="card"><div class="k">Orders today</div><div class="v">${o.orders_today}</div></div>
      <div class="card ${toProcess ? "alert" : ""}"><div class="k">To pack or ship</div><div class="v">${toProcess}</div></div>
      <div class="card"><div class="k">Awaiting payment</div><div class="v">${o.by_status.awaiting_payment || 0}</div></div>
      <div class="card"><div class="k">Customers</div><div class="v">${o.customers}</div></div>
      <div class="card"><div class="k">Active products</div><div class="v">${o.products}</div></div>
    </div>
    ${o.refunds_needed ? `<div class="note bad">${o.refunds_needed} payment(s) need a refund. Refund them in your Paystack dashboard, then contact the customer.</div>` : ""}
    <div class="panel"><h2>Recent orders</h2><div id="rec"></div><a href="#/orders">See all orders</a></div>
    <div class="panel"><h2>Low stock (5 or fewer)</h2>${o.low_stock.length ? o.low_stock.map((p) => `<div class="kv"><a href="#/products">${esc(p.name)}</a><b>${p.stock} left</b></div>`).join("") : '<div class="empty" style="padding:8px">All products have enough stock.</div>'}</div>`;
  const rec = $("#rec", el);
  rec.innerHTML = recent.length ? recent.map((x, i) => `<div class="row click" data-i="${i}"><div class="grow"><div class="ttl">${esc(x.order_no)} · ${esc(x.ship_name)}</div><div class="sub">${fmt(x.created_at)}</div></div><div class="right"><b>${money(x.total)}</b><div>${statusBadge(x.status)}</div></div></div>`).join("") : '<div class="empty">No orders yet.</div>';
  $$(".row", rec).forEach((r) => (r.onclick = () => openOrder(recent[+r.dataset.i], () => route())));
};

/* Orders */
function openOrder(o, reload) {
  const NEXT = { placed: ["packed", "Mark as packed"], packed: ["shipped", "Mark as shipped"], shipped: ["delivered", "Mark as delivered"] };
  const canCancel = ["awaiting_payment", "placed", "packed"].includes(o.status);
  const body = openDlg("Order " + o.order_no, `
    ${o.payments.some((p) => p.status === "refund_needed") ? '<div class="note bad">This order has a payment that needs a refund.</div>' : ""}
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">${statusBadge(o.status)}<span class="sub">Placed ${fmt(o.created_at)}</span></div>
    <div class="panel" style="padding:4px 12px">${o.items.map((i) => `<div class="row" style="padding:10px 0">${thumb(i.image_url, i.name)}<div class="grow"><div class="ttl">${esc(i.name)}</div><div class="sub">Qty ${i.quantity} × ${money(i.unit_price)}</div></div><b>${money(i.unit_price * i.quantity)}</b></div>`).join("")}</div>
    <div class="kv"><span>Subtotal</span><span>${money(o.subtotal)}</span></div>
    ${+o.discount ? `<div class="kv"><span>Coupon ${esc(o.coupon_code || "")}</span><span>-${money(o.discount)}</span></div>` : ""}
    <div class="kv"><span>Delivery</span><span>${money(o.delivery_fee)}</span></div>
    <div class="kv total"><span>Total</span><span>${money(o.total)}</span></div>
    <h2 style="font-size:15px;margin:14px 0 4px">Deliver to</h2>
    <div>${esc(o.ship_name)}<br>${esc(o.ship_street)}, ${esc(o.ship_city)}, ${esc(o.ship_region)}<br><a href="tel:${esc(o.ship_phone)}">${esc(o.ship_phone)}</a></div>
    <h2 style="font-size:15px;margin:14px 0 4px">Payment</h2>
    ${o.payments.length ? o.payments.map((p) => `<div class="kv"><span>${p.method === "pay_on_delivery" ? "Pay on delivery" : "Paystack (MoMo or card)"}</span>${payBadge(p.status)}</div>`).join("") : "<div class='sub'>No payment started</div>"}
    <div class="msg err" id="oMsg" role="alert"></div>
    <div class="actions">
      ${NEXT[o.status] ? `<button class="btn" id="next">${NEXT[o.status][1]}</button>` : ""}
      ${canCancel ? '<button class="btn danger" id="cancelO">Cancel order</button>' : ""}
    </div>`);
  const act = async (status, btn) => {
    btn.disabled = true;
    try { await api(`/admin/orders/${o.order_no}/status`, { method: "PUT", body: { status } }); toast("Order updated"); closeDlg(); reload(); }
    catch (e) { $("#oMsg", body).textContent = e.message; btn.disabled = false; }
  };
  const n = $("#next", body); if (n) n.onclick = () => act(NEXT[o.status][0], n);
  const c = $("#cancelO", body); if (c) c.onclick = () => confirm("Cancel this order? Stock will be returned.") && act("cancelled", c);
}

VIEWS.orders = async (el) => {
  let status = "", page = 1, list = [];
  const FILTERS = [["", "All"], ["awaiting_payment", "Awaiting payment"], ["placed", "Placed"], ["packed", "Packed"], ["shipped", "Shipped"], ["delivered", "Delivered"], ["cancelled", "Cancelled"]];
  el.innerHTML = `<div class="chips" id="chips">${FILTERS.map((f) => `<button class="chip ${f[0] === "" ? "on" : ""}" data-s="${f[0]}">${f[1]}</button>`).join("")}</div><div class="toolbar"><span class="sub" style="flex:1;color:var(--pt-muted)">Unpaid online orders are cancelled automatically and their stock is returned.</span><button class="btn ghost sm" id="expire">Cancel expired now</button></div><div class="rows" id="rows"></div><button class="btn ghost more" id="more" hidden>Load more</button>`;
  const draw = () => {
    $("#rows", el).innerHTML = list.length ? list.map((x, i) => `<div class="row click" data-i="${i}"><div class="grow"><div class="ttl">${esc(x.order_no)} · ${esc(x.ship_name)}</div><div class="sub">${fmt(x.created_at)} · ${x.items.reduce((n, i) => n + i.quantity, 0)} item(s)</div></div><div class="right"><b>${money(x.total)}</b><div>${statusBadge(x.status)} ${x.payments.length ? payBadge(x.payments[x.payments.length - 1].status) : ""}</div></div></div>`).join("") : '<div class="empty">No orders here.</div>';
    $$("#rows .row", el).forEach((r) => (r.onclick = () => openOrder(list[+r.dataset.i], () => load(true))));
  };
  async function load(reset) {
    if (reset) { page = 1; list = []; }
    const d = await api(`/admin/orders?${status ? "status=" + status + "&" : ""}page=${page}&size=30`);
    list = list.concat(d); draw(); $("#more", el).hidden = d.length < 30;
  }
  $$("#chips .chip", el).forEach((b) => (b.onclick = () => { status = b.dataset.s; $$("#chips .chip", el).forEach((x) => x.classList.toggle("on", x === b)); load(true); }));
  $("#more", el).onclick = () => { page++; load(false); };
  $("#expire", el).onclick = async (e) => {
    e.target.disabled = true;
    try { const r = await api("/admin/orders/expire-now", { method: "POST" }); toast(r.cancelled ? r.cancelled + " expired order(s) cancelled" : "No expired orders"); await load(true); }
    catch (er) { toast(er.message, true); }
    e.target.disabled = false;
  };
  await load(true);
};

/* Products */
VIEWS.products = async (el) => {
  let q = "", low = false, page = 1, list = [], total = 0;
  el.innerHTML = `
    <div class="toolbar"><input type="search" id="q" placeholder="Search by name or SKU" aria-label="Search products"><label class="check"><input type="checkbox" id="low"> Low stock</label><button class="btn" id="add">Add product</button></div>
    <div class="rows" id="rows"></div><button class="btn ghost more" id="more" hidden>Load more</button>`;
  const draw = () => {
    $("#rows", el).innerHTML = list.length ? list.map((p, i) => `<div class="row click" data-i="${i}">${thumb(p.images[0]?.url, p.name)}<div class="grow"><div class="ttl">${esc(p.name)}</div><div class="sub">${p.stock} in stock${p.sku ? " · " + esc(p.sku) : ""}</div></div><div class="right"><b>${money(p.price)}</b><div>${p.is_active ? "" : '<span class="badge grey">Hidden</span> '}${p.stock < 1 ? '<span class="badge bad">Out of stock</span>' : p.stock <= 5 ? '<span class="badge warn">Low</span>' : ""}</div></div></div>`).join("") : '<div class="empty">No products found.</div>';
    $$("#rows .row", el).forEach((r) => (r.onclick = () => productForm(list[+r.dataset.i], () => load(true))));
    $("#more", el).hidden = list.length >= total;
  };
  async function load(reset) {
    if (reset) { page = 1; list = []; }
    const d = await api(`/admin/products?page=${page}&size=30&low_stock=${low}${q ? "&q=" + encodeURIComponent(q) : ""}`);
    list = list.concat(d.items); total = d.total; draw();
  }
  let t; $("#q", el).oninput = (e) => { clearTimeout(t); t = setTimeout(() => { q = e.target.value.trim(); load(true); }, 300); };
  $("#low", el).onchange = (e) => { low = e.target.checked; load(true); };
  $("#add", el).onclick = () => productForm(null, () => load(true));
  $("#more", el).onclick = () => { page++; load(false); };
  await load(true);
};

async function productForm(p, done) {
  const { cats, brands } = await lookups();
  const isNew = !p;
  const specs = Object.entries(p?.specs || {});
  const body = openDlg(isNew ? "Add product" : "Edit product", `
    <form class="form" id="pf" novalidate>
      <label>Name<input id="fName" required value="${esc(p?.name || "")}"></label>
      <div class="grid2">
        <label>Slug (web address)<input id="fSlug" required value="${esc(p?.slug || "")}"></label>
        <label>SKU (optional)<input id="fSku" value="${esc(p?.sku || "")}"></label>
      </div>
      <div class="grid2">
        <label>Category<select id="fCat">${catOptions(cats, p?.category_id)}</select></label>
        <label>Brand<select id="fBrand"><option value="">None</option>${brands.map((b) => `<option value="${b.id}" ${b.id === p?.brand_id ? "selected" : ""}>${esc(b.name)}</option>`).join("")}</select></label>
      </div>
      <div class="grid2">
        <label>Price (GH₵)<input id="fPrice" type="number" step="0.01" min="0" required value="${p ? p.price : ""}"></label>
        <label>Old price (GH₵, shows a discount)<input id="fOld" type="number" step="0.01" min="0" value="${p?.old_price ?? ""}"></label>
      </div>
      <label>Stock<input id="fStock" type="number" min="0" step="1" required value="${p ? p.stock : 0}"></label>
      <label>Description<textarea id="fDesc">${esc(p?.description || "")}</textarea></label>
      <div><b style="font-size:13px">Specifications</b><div id="specs" style="margin-top:6px"></div><button type="button" class="linkbtn" id="addSpec">Add a specification</button></div>
      <div><b style="font-size:13px">Images</b>
        <div class="imgs" id="imgs" style="margin:6px 0">${(p?.images || []).map((im) => `<div class="im" data-id="${im.id}"><img src="${esc(im.url)}" alt=""><button type="button" aria-label="Delete image">×</button></div>`).join("")}</div>
        <input type="file" id="fFiles" accept="image/jpeg,image/png,image/webp" multiple>
        <div class="sub" style="color:var(--pt-muted);font-size:12px;margin-top:4px">JPEG, PNG or WEBP, up to 5 MB each. The first image is the main photo.</div>
      </div>
      <label class="check"><input type="checkbox" id="fActive" ${p?.is_active === false ? "" : "checked"}> Show in store</label>
      <label class="check"><input type="checkbox" id="fFeat" ${p?.is_featured ? "checked" : ""}> Featured</label>
      <div class="msg err" id="pMsg" role="alert"></div>
      <div class="actions"><button class="btn" type="submit" id="save">${isNew ? "Add product" : "Save changes"}</button>${isNew ? "" : '<button type="button" class="btn danger" id="del">Delete</button>'}</div>
    </form>`);

  const specBox = $("#specs", body);
  const addSpec = (k = "", v = "") => {
    const d = document.createElement("div"); d.className = "spec-row";
    d.innerHTML = `<input placeholder="e.g. RAM" aria-label="Specification name" value="${esc(k)}"><input placeholder="e.g. 8GB" aria-label="Specification value" value="${esc(v)}"><button type="button" class="linkbtn danger" aria-label="Remove">Remove</button>`;
    $("button", d).onclick = () => d.remove(); specBox.appendChild(d);
  };
  specs.forEach(([k, v]) => addSpec(k, v)); if (!specs.length) addSpec();
  $("#addSpec", body).onclick = () => addSpec();

  let slugTouched = !isNew;
  $("#fSlug", body).oninput = () => (slugTouched = true);
  $("#fName", body).oninput = (e) => { if (!slugTouched) $("#fSlug", body).value = slugify(e.target.value); };

  $$("#imgs .im button", body).forEach((b) => (b.onclick = async () => {
    const box = b.parentElement;
    if (!confirm("Delete this image?")) return;
    try { await api("/products/images/" + box.dataset.id, { method: "DELETE" }); box.remove(); toast("Image deleted"); } catch (e) { toast(e.message, true); }
  }));

  const del = $("#del", body);
  if (del) del.onclick = async () => {
    if (!confirm(`Delete "${p.name}" and its images? This cannot be undone.`)) return;
    try { await api("/products/" + p.id, { method: "DELETE" }); toast("Product deleted"); closeDlg(); done(); } catch (e) { $("#pMsg", body).textContent = e.message; }
  };

  $("#pf", body).onsubmit = async (e) => {
    e.preventDefault();
    const msg = $("#pMsg", body); msg.textContent = "";
    const price = parseFloat($("#fPrice", body).value);
    if (!$("#fName", body).value.trim() || !$("#fSlug", body).value.trim()) return (msg.textContent = "Enter a name and a slug");
    if (isNaN(price) || price < 0) return (msg.textContent = "Enter a valid price");
    const files = [...$("#fFiles", body).files];
    if (files.some((f) => f.size > 5 * 1024 * 1024)) return (msg.textContent = "Each image must be 5 MB or smaller");
    const specsObj = {};
    $$(".spec-row", specBox).forEach((r) => { const [k, v] = $$("input", r); if (k.value.trim()) specsObj[k.value.trim()] = v.value.trim(); });
    const payload = {
      name: $("#fName", body).value.trim(), slug: slugify($("#fSlug", body).value), description: nullIf($("#fDesc", body).value.trim()),
      specs: specsObj, price, old_price: nullIf($("#fOld", body).value) === null ? null : parseFloat($("#fOld", body).value),
      stock: parseInt($("#fStock", body).value || "0", 10), sku: nullIf($("#fSku", body).value.trim()),
      category_id: nullIf($("#fCat", body).value) === null ? null : +$("#fCat", body).value,
      brand_id: nullIf($("#fBrand", body).value) === null ? null : +$("#fBrand", body).value,
      is_active: $("#fActive", body).checked, is_featured: $("#fFeat", body).checked,
    };
    const btn = $("#save", body); btn.disabled = true;
    try {
      const saved = await api(isNew ? "/products" : "/products/" + p.id, { method: isNew ? "POST" : "PUT", body: payload });
      if (files.length) {
        const fd = new FormData(); files.forEach((f) => fd.append("files", f));
        try { await api(`/products/${saved.id}/images`, { method: "POST", body: fd }); }
        catch (er) { toast("Product saved, but images failed: " + er.message, true); closeDlg(); done(); return; }
      }
      toast(isNew ? "Product added" : "Product saved"); closeDlg(); done();
    } catch (er) { msg.textContent = er.message; btn.disabled = false; }
  };
}

/* Categories and brands */
VIEWS.catalog = async (el) => {
  const { cats, brands } = await lookups();
  el.innerHTML = `
    <div class="toolbar"><h2 style="margin:0;font-size:16px;flex:1">Categories</h2><button class="btn" id="addCat">Add category</button></div>
    <div class="rows" id="cats">${cats.length ? cats.map((c) => `<div class="row"><div style="width:${c.depth * 18}px;flex:none"></div>${thumb(c.image_url, c.name)}<div class="grow"><div class="ttl">${esc(c.name)}</div><div class="sub">${esc(c.slug)}</div></div><button class="btn ghost sm" data-e="${c.id}">Edit</button><button class="linkbtn danger" data-d="${c.id}">Delete</button></div>`).join("") : '<div class="empty">No categories yet.</div>'}</div>
    <div class="toolbar" style="margin-top:22px"><h2 style="margin:0;font-size:16px;flex:1">Brands</h2></div>
    <div class="panel"><form class="toolbar" id="brandForm" style="margin:0 0 8px"><input type="text" id="bName" placeholder="Brand name" aria-label="Brand name" required><button class="btn" type="submit">Add brand</button></form>
    <div id="brands">${brands.length ? brands.map((b) => `<div class="kv"><span>${esc(b.name)}</span><button class="linkbtn danger" data-b="${b.id}">Delete</button></div>`).join("") : '<div class="empty" style="padding:8px">No brands yet.</div>'}</div></div>`;
  const reload = () => route();
  $("#addCat", el).onclick = () => catForm(null, cats, reload);
  $$("[data-e]", el).forEach((b) => (b.onclick = () => catForm(cats.find((c) => c.id === +b.dataset.e), cats, reload)));
  $$("[data-d]", el).forEach((b) => (b.onclick = async () => { if (!confirm("Delete this category? Its products will become uncategorised.")) return; try { await api("/categories/" + b.dataset.d, { method: "DELETE" }); toast("Category deleted"); reload(); } catch (e) { toast(e.message, true); } }));
  $$("[data-b]", el).forEach((b) => (b.onclick = async () => { if (!confirm("Delete this brand?")) return; try { await api("/admin/brands/" + b.dataset.b, { method: "DELETE" }); reload(); } catch (e) { toast(e.message, true); } }));
  $("#brandForm", el).onsubmit = async (e) => { e.preventDefault(); const name = $("#bName", el).value.trim(); try { await api("/brands", { method: "POST", body: { name, slug: slugify(name) } }); toast("Brand added"); reload(); } catch (er) { toast(er.message, true); } };
};

function catForm(c, cats, done) {
  const body = openDlg(c ? "Edit category" : "Add category", `
    <form class="form" id="cf" novalidate>
      <label>Name<input id="cName" required value="${esc(c?.name || "")}"></label>
      <label>Slug<input id="cSlug" required value="${esc(c?.slug || "")}"></label>
      <div class="grid2"><label>Parent category<select id="cParent">${catOptions(cats, c?.parent_id, c?.id)}</select></label>
      <label>Sort order<input id="cSort" type="number" value="0"></label></div>
      <label>Image (shown in the store's category bubbles)<input type="file" id="cFile" accept="image/jpeg,image/png,image/webp"></label>
      <div class="msg err" id="cMsg" role="alert"></div>
      <div class="actions"><button class="btn" type="submit">${c ? "Save changes" : "Add category"}</button></div>
    </form>`);
  let touched = !!c;
  $("#cSlug", body).oninput = () => (touched = true);
  $("#cName", body).oninput = (e) => { if (!touched) $("#cSlug", body).value = slugify(e.target.value); };
  $("#cf", body).onsubmit = async (e) => {
    e.preventDefault();
    const payload = { name: $("#cName", body).value.trim(), slug: slugify($("#cSlug", body).value), parent_id: nullIf($("#cParent", body).value) === null ? null : +$("#cParent", body).value, sort_order: parseInt($("#cSort", body).value || "0", 10) };
    try {
      const saved = await api(c ? "/categories/" + c.id : "/categories", { method: c ? "PUT" : "POST", body: payload });
      const f = $("#cFile", body).files[0];
      if (f) { const fd = new FormData(); fd.append("file", f); await api(`/categories/${saved.id}/image`, { method: "POST", body: fd }); }
      toast("Category saved"); closeDlg(); done();
    } catch (er) { $("#cMsg", body).textContent = er.message; }
  };
}

/* Banners */
VIEWS.banners = async (el) => {
  const list = await api("/admin/banners");
  el.innerHTML = `<div class="toolbar"><div style="flex:1" class="sub">Banners slide across the top of the store home page. Wide images work best (about 1600 × 600).</div><button class="btn" id="addB">Add banner</button></div>
  <div class="rows">${list.length ? list.map((b) => `<div class="row"><div class="thumb wide"><img src="${esc(b.image_url)}" alt=""></div><div class="grow"><div class="ttl">${esc(b.title)}</div><div class="sub">${b.link ? esc(b.link) : "No link"} · order ${b.sort_order}</div></div><label class="check"><input type="checkbox" data-t="${b.id}" ${b.is_active ? "checked" : ""}> Live</label><button class="btn ghost sm" data-e="${b.id}">Edit</button><button class="linkbtn danger" data-d="${b.id}">Delete</button></div>`).join("") : '<div class="empty">No banners yet.</div>'}</div>`;
  const reload = () => route();
  const put = (b, patch) => api("/admin/banners/" + b.id, { method: "PUT", body: { title: b.title, link: b.link, sort_order: b.sort_order, is_active: b.is_active, ...patch } });
  $$("[data-t]", el).forEach((c) => (c.onchange = async () => { try { await put(list.find((b) => b.id === +c.dataset.t), { is_active: c.checked }); toast(c.checked ? "Banner is live" : "Banner hidden"); } catch (e) { toast(e.message, true); c.checked = !c.checked; } }));
  $$("[data-d]", el).forEach((b) => (b.onclick = async () => { if (!confirm("Delete this banner?")) return; try { await api("/banners/" + b.dataset.d, { method: "DELETE" }); reload(); } catch (e) { toast(e.message, true); } }));
  $$("[data-e]", el).forEach((b) => (b.onclick = () => {
    const x = list.find((i) => i.id === +b.dataset.e);
    const body = openDlg("Edit banner", `<form class="form" id="bf"><label>Title<input id="bT" required value="${esc(x.title)}"></label><label>Link (optional)<input id="bL" value="${esc(x.link || "")}" placeholder="index.html?category=1"></label><label>Sort order<input id="bO" type="number" value="${x.sort_order}"></label><div class="msg err" id="bMsg"></div><div class="actions"><button class="btn" type="submit">Save changes</button></div></form>`);
    $("#bf", body).onsubmit = async (e) => { e.preventDefault(); try { await put(x, { title: $("#bT", body).value.trim(), link: nullIf($("#bL", body).value.trim()), sort_order: parseInt($("#bO", body).value || "0", 10) }); toast("Banner saved"); closeDlg(); reload(); } catch (er) { $("#bMsg", body).textContent = er.message; } };
  }));
  $("#addB", el).onclick = () => {
    const body = openDlg("Add banner", `<form class="form" id="bf"><label>Title<input id="bT" required></label><label>Link (optional)<input id="bL" placeholder="index.html?category=1"></label><label>Sort order<input id="bO" type="number" value="0"></label><label>Image<input type="file" id="bF" accept="image/jpeg,image/png,image/webp" required></label><div class="msg err" id="bMsg"></div><div class="actions"><button class="btn" type="submit">Add banner</button></div></form>`);
    $("#bf", body).onsubmit = async (e) => {
      e.preventDefault();
      const f = $("#bF", body).files[0];
      if (!f) return ($("#bMsg", body).textContent = "Choose an image");
      const fd = new FormData(); fd.append("title", $("#bT", body).value.trim()); fd.append("sort_order", $("#bO", body).value || "0");
      if ($("#bL", body).value.trim()) fd.append("link", $("#bL", body).value.trim());
      fd.append("file", f);
      try { await api("/banners", { method: "POST", body: fd }); toast("Banner added"); closeDlg(); reload(); } catch (er) { $("#bMsg", body).textContent = er.message; }
    };
  };
};

/* Coupons */
VIEWS.coupons = async (el) => {
  const list = await api("/admin/coupons");
  const expired = (c) => c.expires_at && new Date(c.expires_at) < new Date();
  el.innerHTML = `<div class="toolbar"><div style="flex:1" class="sub">Customers enter these codes at checkout.</div><button class="btn" id="addC">Create coupon</button></div>
  <div class="rows">${list.length ? list.map((c) => `<div class="row"><div class="grow"><div class="ttl">${esc(c.code)}</div><div class="sub">${c.percent_off ? c.percent_off + "% off" : money(c.amount_off) + " off"}${c.min_order ? " · min spend " + money(c.min_order) : ""}${c.expires_at ? " · expires " + new Date(c.expires_at).toLocaleDateString("en-GH", { day: "numeric", month: "short", year: "numeric" }) : ""}</div></div>${expired(c) ? '<span class="badge grey">Expired</span>' : c.is_active ? '<span class="badge solid">Active</span>' : '<span class="badge grey">Off</span>'}<button class="linkbtn danger" data-d="${c.id}">Delete</button></div>`).join("") : '<div class="empty">No coupons yet.</div>'}</div>`;
  $$("[data-d]", el).forEach((b) => (b.onclick = async () => { if (!confirm("Delete this coupon?")) return; try { await api("/admin/coupons/" + b.dataset.d, { method: "DELETE" }); route(); } catch (e) { toast(e.message, true); } }));
  $("#addC", el).onclick = () => {
    const body = openDlg("Create coupon", `<form class="form" id="cpf" novalidate>
      <label>Code<input id="kCode" required placeholder="WELCOME10" style="text-transform:uppercase"></label>
      <div class="grid2"><label>Discount type<select id="kType"><option value="percent">Percent off</option><option value="amount">Fixed amount off (GH₵)</option></select></label><label>Value<input id="kVal" type="number" min="1" step="0.01" required></label></div>
      <div class="grid2"><label>Minimum spend (GH₵, optional)<input id="kMin" type="number" min="0" step="0.01"></label><label>Expires on (optional)<input id="kExp" type="date"></label></div>
      <div class="msg err" id="kMsg" role="alert"></div><div class="actions"><button class="btn" type="submit">Create coupon</button></div></form>`);
    $("#cpf", body).onsubmit = async (e) => {
      e.preventDefault();
      const v = parseFloat($("#kVal", body).value), pct = $("#kType", body).value === "percent";
      if (isNaN(v) || v <= 0) return ($("#kMsg", body).textContent = "Enter a discount value");
      if (pct && (v > 100 || !Number.isInteger(v))) return ($("#kMsg", body).textContent = "Percent must be a whole number from 1 to 100");
      const exp = $("#kExp", body).value;
      const payload = { code: $("#kCode", body).value.trim().toUpperCase(), percent_off: pct ? v : null, amount_off: pct ? null : v, min_order: $("#kMin", body).value ? parseFloat($("#kMin", body).value) : null, expires_at: exp ? new Date(exp + "T23:59:59").toISOString() : null, is_active: true };
      try { await api("/admin/coupons", { method: "POST", body: payload }); toast("Coupon created"); closeDlg(); route(); } catch (er) { $("#kMsg", body).textContent = er.message; }
    };
  };
};

/* Flash sales */
const toLocalInput = (iso) => { const d = new Date(iso), p = (n) => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };
const FLASH_BADGE = { live: '<span class="badge solid">Live</span>', scheduled: '<span class="badge warn">Scheduled</span>', ended: '<span class="badge grey">Ended</span>', off: '<span class="badge grey">Off</span>' };

VIEWS.flash = async (el) => {
  const list = await api("/admin/flash");
  el.innerHTML = `<div class="toolbar"><div style="flex:1;color:var(--pt-muted)" class="sub">Flash sales cut prices for a limited time. Prices go back to normal by themselves when a sale ends.</div><button class="btn" id="addF">Create flash sale</button></div>
  <div class="rows">${list.length ? list.map((s, i) => `<div class="row click" data-i="${i}"><div class="grow"><div class="ttl">${esc(s.title)}</div><div class="sub">${fmt(s.starts_at)} to ${fmt(s.ends_at)} · ${s.items.length} product(s) · ${s.items.reduce((n, x) => n + x.sold, 0)} sold</div></div>${FLASH_BADGE[s.status] || ""}</div>`).join("") : '<div class="empty">No flash sales yet.</div>'}</div>`;
  $("#addF", el).onclick = () => flashForm(null, () => route());
  $$(".row.click", el).forEach((r) => (r.onclick = () => flashForm(list[+r.dataset.i], () => route())));
};

function flashForm(sale, done) {
  const now = new Date(); now.setSeconds(0, 0);
  let items = (sale?.items || []).map((i) => ({ ...i }));
  const body = openDlg(sale ? "Edit flash sale" : "Create flash sale", `
    <form class="form" id="ff" novalidate>
      <label>Title<input id="fTitle" required value="${esc(sale?.title || "Flash sale")}"></label>
      <div class="grid2">
        <label>Starts<input id="fStart" type="datetime-local" required value="${sale ? toLocalInput(sale.starts_at) : toLocalInput(now)}"></label>
        <label>Ends<input id="fEnd" type="datetime-local" required value="${sale ? toLocalInput(sale.ends_at) : toLocalInput(new Date(now.getTime() + 86400000))}"></label>
      </div>
      <label class="check"><input type="checkbox" id="fOn" ${sale?.is_active === false ? "" : "checked"}> Turned on</label>
      <div><b style="font-size:13px">Products in this sale</b>
        <div id="fItems" style="margin:8px 0"></div>
        <input type="search" id="fSearch" placeholder="Search a product to add" aria-label="Search products to add">
        <div id="fResults" class="rows" style="margin-top:6px" hidden></div>
      </div>
      <div class="msg err" id="fMsg" role="alert"></div>
      <div class="actions"><button class="btn" type="submit">${sale ? "Save changes" : "Create flash sale"}</button>${sale ? '<button type="button" class="btn danger" id="fDel">Delete</button>' : ""}</div>
    </form>`);

  const drawItems = () => {
    $("#fItems", body).innerHTML = items.length ? items.map((it, i) => `<div class="row" style="padding:10px 0;align-items:flex-end;flex-wrap:wrap"><div class="grow" style="min-width:160px"><div class="ttl">${esc(it.name)}</div><div class="sub">Normal price ${money(it.price)}${it.sold ? " · " + it.sold + " sold" : ""}</div></div><label style="width:120px">Flash price<input type="number" step="0.01" min="0" data-p="${i}" value="${it.sale_price ?? ""}"></label><label style="width:110px">Limit<input type="number" min="1" step="1" placeholder="No limit" data-l="${i}" value="${it.quantity_limit ?? ""}"></label><button type="button" class="linkbtn danger" data-r="${i}">Remove</button></div>`).join("") : '<div class="empty" style="padding:10px">No products yet. Search below to add some.</div>';
    $$("[data-p]", body).forEach((x) => (x.oninput = () => (items[+x.dataset.p].sale_price = x.value)));
    $$("[data-l]", body).forEach((x) => (x.oninput = () => (items[+x.dataset.l].quantity_limit = x.value)));
    $$("[data-r]", body).forEach((x) => (x.onclick = () => { items.splice(+x.dataset.r, 1); drawItems(); }));
  };
  drawItems();

  let t;
  $("#fSearch", body).oninput = (e) => {
    clearTimeout(t);
    const q = e.target.value.trim(), box = $("#fResults", body);
    if (!q) { box.hidden = true; return; }
    t = setTimeout(async () => {
      try {
        const d = await api("/admin/products?size=8&q=" + encodeURIComponent(q));
        box.hidden = false;
        box.innerHTML = d.items.length ? d.items.map((p, i) => `<div class="row click" data-a="${i}"><div class="grow"><div class="ttl">${esc(p.name)}</div><div class="sub">${money(p.price)} · ${p.stock} in stock</div></div><span class="linkbtn">Add</span></div>`).join("") : '<div class="empty" style="padding:10px">No products found.</div>';
        $$("[data-a]", box).forEach((r) => (r.onclick = () => {
          const p = d.items[+r.dataset.a];
          if (items.some((x) => x.product_id === p.id)) return toast("Already added", true);
          items.push({ product_id: p.id, name: p.name, price: p.price, sale_price: "", quantity_limit: "", sold: 0 });
          box.hidden = true; $("#fSearch", body).value = ""; drawItems();
        }));
      } catch (er) { toast(er.message, true); }
    }, 300);
  };

  const del = $("#fDel", body);
  if (del) del.onclick = async () => {
    if (!confirm("Delete this flash sale? Prices go back to normal straight away.")) return;
    try { await api("/admin/flash/" + sale.id, { method: "DELETE" }); toast("Flash sale deleted"); closeDlg(); done(); } catch (er) { $("#fMsg", body).textContent = er.message; }
  };

  $("#ff", body).onsubmit = async (e) => {
    e.preventDefault();
    const msg = $("#fMsg", body); msg.textContent = "";
    const s = $("#fStart", body).value, en = $("#fEnd", body).value;
    if (!$("#fTitle", body).value.trim()) return (msg.textContent = "Enter a title");
    if (!s || !en) return (msg.textContent = "Choose the start and end times");
    if (new Date(en) <= new Date(s)) return (msg.textContent = "The end time must be after the start time");
    if (!items.length) return (msg.textContent = "Add at least one product");
    for (const it of items) { const p = parseFloat(it.sale_price); if (isNaN(p) || p <= 0) return (msg.textContent = "Enter a flash price for " + it.name); if (p >= Number(it.price)) return (msg.textContent = "The flash price for " + it.name + " must be lower than " + money(it.price)); }
    const payload = {
      title: $("#fTitle", body).value.trim(), starts_at: new Date(s).toISOString(), ends_at: new Date(en).toISOString(), is_active: $("#fOn", body).checked,
      items: items.map((it) => ({ product_id: it.product_id, sale_price: parseFloat(it.sale_price), quantity_limit: it.quantity_limit === "" || it.quantity_limit == null ? null : parseInt(it.quantity_limit, 10) })),
    };
    const btn = e.target.querySelector("button[type=submit]"); btn.disabled = true;
    try { await api(sale ? "/admin/flash/" + sale.id : "/admin/flash", { method: sale ? "PUT" : "POST", body: payload }); toast("Flash sale saved"); closeDlg(); done(); }
    catch (er) { msg.textContent = er.message; btn.disabled = false; }
  };
}

/* Delivery fees */
VIEWS.delivery = async (el) => {
  const zones = await api("/delivery/fees");
  el.innerHTML = `<div class="note">Set the delivery fee for each region. Customers see this fee at checkout.</div><div class="rows">${zones.map((z) => `<div class="row fee-row"><div class="grow ttl">${esc(z.region)}</div><span>GH₵</span><input type="number" min="0" step="0.01" value="${z.fee}" aria-label="Fee for ${esc(z.region)}" data-r="${esc(z.region)}"><button class="btn sm" data-s="${esc(z.region)}">Save</button></div>`).join("")}</div>`;
  $$("[data-s]", el).forEach((b) => (b.onclick = async () => {
    const inp = $(`input[data-r="${CSS.escape(b.dataset.s)}"]`, el);
    const fee = parseFloat(inp.value);
    if (isNaN(fee) || fee < 0) return toast("Enter a valid fee", true);
    try { await api("/admin/delivery/" + encodeURIComponent(b.dataset.s), { method: "PUT", body: { fee } }); toast("Saved " + b.dataset.s); } catch (e) { toast(e.message, true); }
  }));
};

/* Reviews */
VIEWS.reviews = async (el) => {
  const list = await api("/admin/reviews?size=50");
  const stars = (n) => "★".repeat(n) + "☆".repeat(5 - n);
  el.innerHTML = list.length ? `<div class="rows">${list.map((r) => `<div class="row" style="align-items:flex-start"><div class="grow"><div class="ttl">${esc(r.product_name)}</div><div class="sub" style="color:var(--pt-blue-600);font-size:14px">${stars(r.rating)}</div>${r.title ? `<div style="font-weight:700;margin-top:4px">${esc(r.title)}</div>` : ""}${r.body ? `<div style="margin-top:2px;white-space:pre-line">${esc(r.body)}</div>` : ""}<div class="sub" style="margin-top:4px">${esc(r.author_full)} · ${esc(r.email)} · ${fmt(r.created_at)}</div></div><button class="linkbtn danger" data-d="${r.id}">Delete</button></div>`).join("")}</div>` : '<div class="empty">No reviews yet. Customers can review products after delivery.</div>';
  $$("[data-d]", el).forEach((b) => (b.onclick = async () => { if (!confirm("Delete this review? The product rating will be recalculated.")) return; try { await api("/admin/reviews/" + b.dataset.d, { method: "DELETE" }); toast("Review deleted"); route(); } catch (e) { toast(e.message, true); } }));
};

/* Messages (email and SMS) */
VIEWS.notifications = async (el) => {
  const d = await api("/admin/notifications");
  const badge = (on) => on ? '<span class="badge solid">Ready</span>' : '<span class="badge warn">Not set up</span>';
  el.innerHTML = `
    <div class="cards">
      <div class="card"><div class="k">Email (Brevo)</div><div class="v" style="font-size:16px">${badge(d.email_enabled)}</div></div>
      <div class="card"><div class="k">SMS (Arkesel)</div><div class="v" style="font-size:16px">${badge(d.sms_enabled)}</div></div>
      <div class="card"><div class="k">New-order alerts go to</div><div class="v" style="font-size:14px;font-weight:700">${d.admin_email ? esc(d.admin_email) : "No email set"}<br>${d.admin_phone ? esc(d.admin_phone) : "No phone set"}</div></div>
    </div>
    ${!d.email_enabled || !d.sms_enabled ? '<div class="note">Add the missing keys to your <b>.env</b> file and restart the API. Orders still work without them; customers just get no messages.</div>' : ""}
    <div class="toolbar"><button class="btn ghost" id="tEmail">Send test email</button><button class="btn ghost" id="tSms">Send test SMS</button><span class="sub" style="color:var(--pt-muted)">Tests go to the alert email and phone in .env. SMS sender ID: ${esc(d.sender_id)}</span></div>
    <div class="rows">${d.items.length ? d.items.map((m) => `<div class="row"><div class="grow"><div class="ttl">${m.channel === "sms" ? "SMS" : "Email"} · ${esc(m.event.replace(/_/g, " "))}</div><div class="sub">${esc(m.recipient)} · ${fmt(m.created_at)}</div>${m.error ? `<div class="sub" style="color:var(--danger)">${esc(m.error)}</div>` : ""}</div>${m.status === "sent" ? '<span class="badge solid">Sent</span>' : '<span class="badge bad">Failed</span>'}</div>`).join("") : '<div class="empty">No messages sent yet.</div>'}</div>`;
  const test = (id, channel) => ($(id, el).onclick = async (ev) => {
    ev.target.disabled = true;
    try { const r = await api("/admin/notifications/test?channel=" + channel, { method: "POST" }); toast("Test sent to " + r.sent_to); route(); }
    catch (er) { toast(er.message, true); ev.target.disabled = false; }
  });
  test("#tEmail", "email"); test("#tSms", "sms");
};

/* Customers */
VIEWS.customers = async (el) => {
  let q = "";
  el.innerHTML = `<div class="toolbar"><input type="search" id="q" placeholder="Search by name, email or phone" aria-label="Search customers"></div><div class="rows" id="rows"></div>`;
  async function load() {
    const list = await api("/admin/customers?size=100" + (q ? "&q=" + encodeURIComponent(q) : ""));
    $("#rows", el).innerHTML = list.length ? list.map((c) => `<div class="row"><div class="grow"><div class="ttl">${esc(c.full_name)}</div><div class="sub">${esc(c.email)}${c.phone ? " · " + esc(c.phone) : ""}</div><div class="sub">Joined ${new Date(c.created_at).toLocaleDateString("en-GH", { day: "numeric", month: "short", year: "numeric" })}</div></div><div class="right"><b>${money(c.spent)}</b><div class="sub">${c.orders} order(s)</div></div><button class="btn ${c.is_active ? "danger" : "ghost"} sm" data-u="${c.id}" data-a="${c.is_active ? "0" : "1"}">${c.is_active ? "Block" : "Unblock"}</button></div>`).join("") : '<div class="empty">No customers found.</div>';
    $$("[data-u]", el).forEach((b) => (b.onclick = async () => {
      if (b.dataset.a === "0" && !confirm("Block this customer from logging in?")) return;
      try { await api(`/admin/customers/${b.dataset.u}/active?active=${b.dataset.a === "1"}`, { method: "PUT" }); load(); } catch (e) { toast(e.message, true); }
    }));
  }
  let t; $("#q", el).oninput = (e) => { clearTimeout(t); t = setTimeout(() => { q = e.target.value.trim(); load(); }, 300); };
  await load();
};

/* ---------- router ---------- */
async function route() {
  const name = (location.hash.replace("#/", "") || "overview");
  const key = VIEWS[name] ? name : "overview";
  $("#nav").innerHTML = NAV.map(([k, label]) => `<a href="#/${k}" class="${k === key ? "on" : ""}">${label}</a>`).join("");
  $("#title").textContent = NAV.find((n) => n[0] === key)[1];
  const el = $("#view"), my = ++token;
  el.innerHTML = '<div class="empty">Loading…</div>';
  const box = document.createElement("div");
  try { await VIEWS[key](box); }
  catch (e) { if (my === token) el.innerHTML = `<div class="note bad">${esc(e.message)}</div>`; return; }
  if (my === token) { el.innerHTML = ""; el.appendChild(box); }
}
window.addEventListener("hashchange", () => { closeDlg(); route(); });

async function start() {
  if (!getTok()) return showLogin();
  try {
    const me = await api("/auth/me");
    if (me.role !== "admin") throw new Error("not admin");
  } catch { setTok(null); return showLogin(); }
  $("#login").hidden = true; $("#shell").hidden = false;
  route();
}
start();
