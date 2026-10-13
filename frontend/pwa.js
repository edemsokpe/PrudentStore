/* PRUDENT TECH app features: service worker, "Install app" prompt, offline notice, update notice, back button. */
(function () {
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  };
  const standalone = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const DISMISS_KEY = "pt_install_dismissed";
  const FOURTEEN_DAYS = 14 * 24 * 3600 * 1000;
  let deferred = null; // the browser's install prompt (Android and desktop Chrome/Edge)
  let stack;

  function ensureStack() {
    if (!stack) { stack = document.createElement("div"); stack.className = "pwa-stack"; document.body.appendChild(stack); }
    return stack;
  }
  function card(html, extra) {
    const el = document.createElement("div");
    el.className = "pwa-card" + (extra ? " " + extra : "");
    el.innerHTML = html;
    ensureStack().appendChild(el);
    return el;
  }

  /* ---------- service worker and update notice ---------- */
  const secure = location.protocol === "https:" || ["localhost", "127.0.0.1"].includes(location.hostname);
  if ("serviceWorker" in navigator && secure) {
    let wantReload = false;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").then((reg) => {
        const announce = (worker) => {
          if (!worker || !navigator.serviceWorker.controller) return; // first install: nothing to refresh
          const el = card('<div class="grow"><b>A new version is ready</b></div><button class="btn-primary sm" id="pwaRefresh">Refresh</button>');
          el.querySelector("#pwaRefresh").onclick = () => { wantReload = true; worker.postMessage("SKIP_WAITING"); };
        };
        if (reg.waiting) announce(reg.waiting);
        reg.addEventListener("updatefound", () => {
          const w = reg.installing;
          if (w) w.addEventListener("statechange", () => { if (w.state === "installed") announce(w); });
        });
        document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") reg.update().catch(() => {}); });
      }).catch(() => {});
    });
    navigator.serviceWorker.addEventListener("controllerchange", () => { if (wantReload) location.reload(); });
  }

  /* ---------- offline notice ---------- */
  let offlineEl = null;
  function syncOnline() {
    if (!navigator.onLine && !offlineEl) {
      offlineEl = card('<div class="grow">You are offline. You can browse saved pages, but ordering needs a connection.</div>', "dark");
    } else if (navigator.onLine && offlineEl) { offlineEl.remove(); offlineEl = null; }
  }
  window.addEventListener("online", syncOnline);
  window.addEventListener("offline", syncOnline);

  /* ---------- install prompt ---------- */
  const dismissedRecently = () => Date.now() - Number(store.get(DISMISS_KEY) || 0) < FOURTEEN_DAYS;
  const canOffer = () => !standalone() && !store.get("pt_installed") && (deferred || isIOS);

  async function runInstall() {
    if (deferred) {
      deferred.prompt();
      const choice = await deferred.userChoice.catch(() => null);
      deferred = null;
      if (!choice || choice.outcome !== "accepted") store.set(DISMISS_KEY, String(Date.now()));
      return true;
    }
    return false; // iOS: there is no prompt, only instructions
  }

  function showInstallBanner() {
    if (!canOffer() || dismissedRecently() || document.querySelector(".pwa-install")) return;
    const ios = !deferred;
    const el = card(
      `<div class="grow"><b>Install PRUDENT TECH</b><span>${ios ? "Tap Share, then Add to Home Screen." : "Shop faster from your home screen."}</span></div>` +
      `<button class="btn-primary sm" id="pwaInstall">${ios ? "Got it" : "Install"}</button><button class="link-btn" id="pwaLater">Not now</button>`,
      "pwa-install"
    );
    el.querySelector("#pwaInstall").onclick = async () => { await runInstall(); if (ios) store.set(DISMISS_KEY, String(Date.now())); el.remove(); };
    el.querySelector("#pwaLater").onclick = () => { store.set(DISMISS_KEY, String(Date.now())); el.remove(); };
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e;
    syncInstallCard();
    if (isHome()) setTimeout(showInstallBanner, 8000);
  });
  window.addEventListener("appinstalled", () => {
    store.set("pt_installed", "1"); deferred = null;
    document.querySelectorAll(".pwa-install").forEach((x) => x.remove());
    syncInstallCard();
  });

  const isHome = () => (location.pathname === "/" || location.pathname.endsWith("/index.html")) && !location.search.replace("?source=pwa", "");

  /* "Install the app" card on the account page */
  function syncInstallCard() {
    const c = document.getElementById("installCard");
    if (!c) return;
    c.hidden = !canOffer();
    const btn = document.getElementById("installBtn"), msg = document.getElementById("installMsg");
    if (!btn || btn._wired) return;
    btn._wired = true;
    btn.onclick = async () => {
      if (!(await runInstall()) && msg) msg.textContent = "On iPhone or iPad: tap the Share button in Safari, then choose Add to Home Screen.";
    };
  }

  document.addEventListener("DOMContentLoaded", () => {
    syncOnline();
    syncInstallCard();
    if (isHome() && isIOS) setTimeout(showInstallBanner, 8000);

    /* An installed app has no browser back button, so give inner pages one. */
    if (standalone() && !isHome()) {
      const row = document.querySelector(".site-header .row");
      if (row) {
        const b = document.createElement("button");
        b.className = "icon-btn back-btn";
        b.setAttribute("aria-label", "Go back");
        b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>';
        b.onclick = () => (history.length > 1 ? history.back() : (location.href = "/"));
        row.insertBefore(b, row.firstChild);
      }
    }
  });
})();
