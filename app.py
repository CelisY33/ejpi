# e^jπ (calculadora para celular): el mismo núcleo (aparato.Aparato) dentro del navegador con Pyodide.
# El hilo de JS manda teclas; aquí se aplican y se devuelve qué dibujar (listas de trazos por fila).
import json
import os
import sys

sys.path.insert(0, "/home/pyodide/lib")
from tnsestudio.calc import layout as L          # noqa: E402
from tnsestudio.calc import rows as R            # noqa: E402
from tnsestudio.calc.aparato import Aparato      # noqa: E402
from tnsestudio.calc.pretty import from_linear   # noqa: E402

DATA = "/tmp/tnsdata"
PX = 19.0                 # tamaño de letra del historial (px CSS)
PX_LINE = 21.0
PAD = 4.0


class Fonts:
    """Anchos de letra medidos en el navegador (a 100 px) para DejaVu Serif."""

    def __init__(self, table):
        self.t = table
        self._cache = {}

    def metrics(self, px, italic=False, bold=False):
        key = ("b" if bold else "") + ("i" if italic else "") or "r"
        tab = self.t.get(key) or self.t["r"]
        dflt = tab.get("default", 60.0)
        f = px / 100.0
        cache = self._cache

        class M:
            def horizontalAdvance(_, s):
                k = (key, s)
                w = cache.get(k)
                if w is None:
                    w = sum(tab.get(c, dflt) for c in s)
                    cache[k] = w
                return w * f
        return M()


class Rec:
    """Lienzo de layout.py que anota los trazos para dibujarlos en un <canvas> del navegador."""

    def __init__(self):
        self.ops = []

    def text(self, x, y, s, px, italic, bold, color):
        self.ops.append(["t", round(x, 2), round(y, 2), s, round(px, 2), int(bool(italic)), int(bool(bold)), color])

    def line(self, x1, y1, x2, y2, color, width):
        self.ops.append(["l", round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2), color, round(width, 2)])

    def rect(self, x, y, w, h, color, width, dash=False):
        self.ops.append(["r", round(x, 2), round(y, 2), round(w, 2), round(h, 2), color, round(width, 2), int(dash)])

    def path(self, path, color, width):
        self.ops.append(["p", [[round(v, 2) if isinstance(v, float) else v for v in op] for op in path.ops],
                         color, round(width, 2)])


FONTS = None
AP = None
_hist_cache = {}
_last_hist_sig = None
_carets = []
_line_origin = (0.0, 0.0)


def draw(row, px=PX, color="#23252B", readonly=True, top=True):
    lay = L.layout(row, px, color, top=top, readonly=readonly, fonts=FONTS)
    rec = Rec()
    lay.paint(rec, PAD, PAD + lay.a)
    return {"w": round(lay.w + 2 * PAD, 2), "h": round(lay.a + lay.d + 2 * PAD, 2), "ops": rec.ops}


def boot(table_json, state_json, line_text, ajustes_json):
    global FONTS, AP
    FONTS = Fonts(json.loads(table_json))
    os.makedirs(DATA, exist_ok=True)
    if state_json:
        with open(os.path.join(DATA, "estado.json"), "w", encoding="utf-8") as fh:
            fh.write(state_json)
    aj = json.loads(ajustes_json) if ajustes_json else None
    AP = Aparato(DATA, aj if not state_json else None)
    if line_text:
        AP.ed.insertRow(from_linear(line_text))
    return render(True)


def _hist():
    out = []
    for e in AP.calc.historial:
        k = id(e)
        d = _hist_cache.get(k)
        if d is None or d[0] is not e:
            ins = draw(e.entrada)
            if e.error:
                outs = [draw(R.Row(list('"Error: ' + e.error + '"')), color="#B3261E")]
            else:
                outs = [draw(f) for f in (e.filas or [R.Row()])]
            hint = draw(e.pista, px=PX * 0.8, color="#6B7080") if e.pista is not None else None
            try:
                txt = [R.to_plain(e.entrada)] + ([("Error: " + e.error)] if e.error else
                                                 [R.to_plain(f) for f in (e.filas or [R.Row()])])
            except Exception:  # noqa: BLE001
                txt = []
            d = (e, {"in": ins, "outs": outs, "hint": hint, "err": bool(e.error), "txt": txt})
            _hist_cache[k] = d
        out.append(d[1])
    alive = {id(e) for e in AP.calc.historial}
    for k in [k for k in _hist_cache if k not in alive]:
        del _hist_cache[k]
    return out


def _line():
    global _carets
    ed = AP.ed
    lay = L.layout(ed._root, PX_LINE, "#23252B", top=True, fonts=FONTS)
    rec = Rec()
    x0, y0 = PAD, PAD + max(lay.a, 0.74 * PX_LINE)
    lay.paint(rec, x0, y0)
    cars = []
    lay.carets(x0, y0, cars)
    _carets = cars
    cx, ct, cb = x0, y0 - 0.74 * PX_LINE, y0 + 0.24 * PX_LINE
    row, idx = ed._cur
    for r, i, x, t, b in cars:
        if r is row and i == idx:
            cx, ct, cb = x, t, b
            break
    sel = None
    s = ed.selection()
    if s:
        rc = R.sel_rect(cars, s, y0 - lay.a, y0 + lay.d)
        if rc:
            sel = [round(v, 2) for v in rc]
    h = max(lay.a, 0.74 * PX_LINE) + max(lay.d, 0.24 * PX_LINE) + 2 * PAD
    return {"w": round(lay.w + 2 * PAD, 2), "h": round(h, 2), "ops": rec.ops,
            "caret": [round(cx, 2), round(ct, 2), round(cb, 2)], "sel": sel,
            "hm": bool(ed.historyMode), "empty": len(ed._root) == 0, "text": ed.text()}


def render(force=False):
    global _last_hist_sig
    sig = tuple(id(e) for e in AP.calc.historial)
    st = {"line": _line(), "sel": AP.sel, "msg": AP.mensaje, "mode": AP.calc.ajustes.short(),
          "ajustes": dict(AP.calc.ajustes.__dict__)}
    if force or sig != _last_hist_sig:
        st["hist"] = _hist()
        _last_hist_sig = sig
    try:
        with open(os.path.join(DATA, "estado.json"), encoding="utf-8") as fh:
            st["estado"] = fh.read()
    except OSError:
        pass
    return json.dumps(st, ensure_ascii=False)


# plantillas de las funciones por unidad (como en el PC: zpu( -> zpu(□_Ω,_V,_VA))
PU_TPL = {"bases": "(|_VA,_V)", "zbase": "(|_V,_VA)", "ibase": "(|_VA,_V)", "zpu": "(|_Ω,_V,_VA)",
          "pu": "(|,)", "frompu": "(|,)", "cambiobase": "(|,_V,_VA,_V,_VA)", "newbase": "(|,_V,_VA,_V,_VA)"}
CONV_FUNCS = {"conj", "real", "imag", "angle", "abs", "factor", "expand", "propfrac", "getnum", "getdenom",
              "comdenom", "approxfraction", "tcollect", "texpand", "cfactor", "round", "ipart", "fpart",
              "sign", "floor", "ceiling", "det", "ref", "rref", "norm", "rownorm", "colnorm", "trace",
              "eigvl", "eigvc", "unitv", "dim", "rowdim", "coldim", "min", "max", "mean", "median", "sum",
              "product", "stdevsamp", "varsamp", "stdevpop", "varpop", "sorta", "sortd", "cumulativesum",
              "deltalist", "approx", "exact"}


def _has_prev():
    return any(e.error is None and e.filas for e in AP.calc.historial)


def _menu_insert(s):
    """Lo mismo que el menú del PC: real(|) con la línea vacía usa Ans gris; ▸Rect solo = Ans▸Rect."""
    import re
    ed = AP.ed
    empty = len(ed._root) == 0
    if "|" in s:
        if empty and s.startswith("▸"):
            ed.insertText("Ans")
        m = re.fullmatch(r"([A-Za-z][A-Za-z0-9]*)\(\|\)", s)
        if m and m.group(1).lower() in PU_TPL:
            ed.insertText(m.group(1) + PU_TPL[m.group(1).lower()])
            return
        ed.insertText(s)
        if m and empty and m.group(1).lower() in CONV_FUNCS and _has_prev():
            ed.setGhost()
    elif s.startswith("▸") or s in ("ᵀ", "!"):
        ed.insertRow(R.Row([s]))
        if empty and _has_prev():
            ed._cur = (ed._root, 0)
            ed.setGhost()
    else:
        ed.insertRow(R.Row(list(s)))


def action(msg_json):
    m = json.loads(msg_json)
    t = m.get("t")
    ed = AP.ed
    if t == "key":
        AP.tecla(m["k"], m.get("text", ""), ctrl=m.get("ctrl", False), shift=m.get("shift", False))
    elif t == "seq":                      # varias teclas seguidas (sin( = s, i, n, ( como en la TI)
        for k in m["keys"]:
            AP.tecla(k.get("k", "text"), k.get("text", ""), ctrl=k.get("ctrl", False), shift=k.get("shift", False))
    elif t == "menu":
        AP._set_sel(None)
        _menu_insert(m["s"])
    elif t == "paste":
        AP._set_sel(None)
        ed.pasteText(m.get("s", ""))
    elif t == "system":
        AP._set_sel(None)
        ed.insertSystem(m.get("n", 2), m.get("fn", "solve"), m.get("vars", "x,y"))
    elif t == "addRow":
        ed.addRow(column=m.get("column", False))
    elif t == "insert":                   # plantilla con | donde queda el cursor: "solve(|,x)"
        AP._set_sel(None)
        ed.insertText(m["s"])
    elif t == "box":
        AP._set_sel(None)
        ed.insertBox(m["kind"])
    elif t == "power":
        AP._set_sel(None)
        ed.insertPower(m.get("base", "ℯ"))
    elif t == "clear":
        AP._set_sel(None)
        ed.clear()
    elif t == "undo":
        AP.deshacer()
    elif t == "redo":
        AP.rehacer()
    elif t == "tapHist":                  # toque en el historial: elige; otro toque en lo mismo, pega
        i = m["i"]
        if AP.sel == i:
            AP.tecla("enter")
        else:
            AP._set_sel(i)
    elif t == "tapLine":
        AP._set_sel(None)
        best = R._nearest(_carets, m["x"], m["y"])
        if best:
            ed.solidGhost()
            ed._anchor = None
            ed._cur = best
            ed._changed()
    elif t == "mode":
        if hasattr(AP.calc.ajustes, m["k"]):
            setattr(AP.calc.ajustes, m["k"], m["v"])
            AP.calc.guardar()
    elif t == "clearHist":
        AP.calc.limpiar()
    return render(t in ("mode",))
