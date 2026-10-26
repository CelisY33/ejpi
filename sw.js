// e^jπ: service worker para usarla sin internet y que se actualice sola.
//  - Python, SymPy, NumPy y las letras (py/, fonts/) no cambian: se guardan una vez y se usan de la memoria.
//  - La calculadora en sí (index.html, worker.js, app.py, tns.zip, menu.json): primero se pide a internet
//    (así llegan los cambios apenas se suben) y si no hay conexión se usa la copia guardada.
const BIG = "tnscalc-pyodide-314.0.7";
const APP = "tnscalc-app";
const APP_FILES = ["./", "index.html", "worker.js", "app.py", "tns.zip", "menu.json", "manifest.webmanifest",
  "icons/icon-180.png", "icons/icon-192.png", "icons/icon-512.png"];
const BIG_FILES = ["py/pyodide.mjs", "py/pyodide.asm.mjs", "py/pyodide.asm.wasm", "py/pyodide-lock.json",
  "py/python_stdlib.zip", "py/numpy-2.4.6-cp314-cp314-pyemscripten_2026_0_wasm32.whl",
  "py/sympy-1.14.0-py3-none-any.whl", "py/mpmath-1.4.1-py3-none-any.whl",
  "fonts/DejaVuSerif.ttf", "fonts/DejaVuSerif-Italic.ttf", "fonts/DejaVuSerif-Bold.ttf",
  "fonts/DejaVuSerif-BoldItalic.ttf", "fonts/DejaVuMathTeXGyre.ttf", "fonts/DejaVuSans.ttf"];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil((async () => {
    const big = await caches.open(BIG);
    for (const f of BIG_FILES) if (!(await big.match(f))) await big.add(f);
    const app = await caches.open(APP);
    await app.addAll(APP_FILES.map((f) => new Request(f, { cache: "reload" })));
  })());
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== BIG && k !== APP) await caches.delete(k);
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (/\/(py|fonts)\//.test(url.pathname)) {
    e.respondWith((async () => {
      const c = await caches.open(BIG);
      const hit = await c.match(url.pathname.replace(/^.*?\/(py|fonts)\//, "$1/")) || await c.match(req, { ignoreSearch: true });
      if (hit) return hit;
      const r = await fetch(req);
      if (r.ok) c.put(req, r.clone());
      return r;
    })());
    return;
  }
  e.respondWith((async () => {
    const c = await caches.open(APP);
    try {
      const r = await fetch(req, { cache: "no-cache" });
      if (r.ok) c.put(req, r.clone());
      return r;
    } catch (err) {
      const hit = await c.match(req, { ignoreSearch: true }) || (req.mode === "navigate" ? await c.match("index.html") : null);
      if (hit) return hit;
      throw err;
    }
  })());
});
