// e^jπ: el núcleo de la calculadora (Python + SymPy con Pyodide) corre en este hilo aparte,
// así la pantalla no se congela mientras calcula y "Cancelar" puede cortar el cálculo (terminate).
import { loadPyodide } from "./py/pyodide.mjs";

let py = null, action = null;

// Los .zip / .whl: en GitHub Pages se sirven tal cual; en el artefacto van como texto base64 (.b64.txt)
// y aquí se decodifican para Pyodide.
const realFetch = self.fetch.bind(self);
function b64bytes(t) {
  t = t.replace(/\s+/g, "");
  if (Uint8Array.fromBase64) return Uint8Array.fromBase64(t);
  const s = atob(t), out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}
self.fetch = async (input, init) => {
  const url = typeof input === "string" ? input : (input && input.url) || String(input);
  const clean = url.split("#")[0].split("?")[0];
  if (/\.(zip|whl)$/.test(clean)) {
    const raw = await realFetch(input, init).catch(() => null);   // en GitHub Pages están tal cual
    if (raw && raw.ok && !/text\/html/.test(raw.headers.get("Content-Type") || "")) return raw;
    const r = await realFetch(clean + ".b64.txt");                  // en el artefacto, como texto base64
    if (!r.ok) return r;
    const bytes = b64bytes(await r.text());
    return new Response(bytes, { status: 200, headers: { "Content-Type": "application/octet-stream" } });
  }
  return realFetch(input, init);
};
const say = (o) => self.postMessage(o);

async function init(m) {
  const t0 = performance.now();
  say({ type: "progress", text: "Cargando Python…", p: 0.1 });
  py = await loadPyodide({ indexURL: new URL("./py/", import.meta.url).href });
  say({ type: "progress", text: "Cargando SymPy y NumPy…", p: 0.45 });
  await py.loadPackage(["numpy", "sympy", "mpmath"], { messageCallback: () => {}, errorCallback: () => {} });
  say({ type: "progress", text: "Preparando la calculadora…", p: 0.8 });
  const [zip, src] = await Promise.all([
    fetch(new URL("./tns.zip", import.meta.url)).then((r) => r.arrayBuffer()),
    fetch(new URL("./app.py", import.meta.url)).then((r) => r.text()),
  ]);
  py.unpackArchive(new Uint8Array(zip), "zip", { extractDir: "/home/pyodide/lib" });
  py.runPython(src);
  action = py.globals.get("action");
  const boot = py.globals.get("boot");
  const st = boot(m.table, m.state || "", m.line || "", m.ajustes || "");
  say({ type: "ready", st, ms: Math.round(performance.now() - t0) });
}

self.onmessage = async (ev) => {
  const m = ev.data;
  try {
    if (m.type === "init") {
      await init(m);
    } else if (m.type === "action") {
      const st = action(JSON.stringify(m.a));
      say({ type: "render", st, id: m.id });
    }
  } catch (e) {
    say({ type: "error", id: m.id, text: String((e && e.message) || e), fatal: m.type === "init" });
  }
};
