// Where the store's API lives.
// "" means the same address as this page, which is how the live site (and `uvicorn app.main:app`) works.
// If you open the pages from another local server (for example `python -m http.server 5500`), the API is on port 8000.
window.PT_API = window.PT_API ?? (["5500", "5501"].includes(location.port) ? "http://127.0.0.1:8000" : "");
