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



# ================================================================ gráficos (la misma escena que el PC)
class _G:
    scene = None
    vp = None
    geo = {}
    special = []
    editing = None
    hover = None
    msg = None
    dirty = True


def _ext():
    e = getattr(AP.calc, "engine", None)
    if e is None:
        return {}, {}, {}
    return dict(e.funcs), dict(e.names), dict(e.vars)


def gboot(state_json, w, h):
    from tnsestudio.graph import geom
    from tnsestudio.graph.model import Scene
    Scene.ext = staticmethod(_ext)
    sc = Scene()
    _G.scene = sc
    _G.vp = geom.Viewport(sc, w, h)
    _G.vp.standard()
    try:
        st = json.loads(state_json) if state_json else {}
    except ValueError:
        st = {}
    for d in st.get("objects", []):
        try:
            o = sc.add(d.get("text", ""), color=d.get("color"), name=d.get("name"), visible=d.get("visible", True),
                       extra={"min": d.get("min"), "max": d.get("max"), "step": d.get("step")})
            if d.get("auto"):
                o.auto_name = True
        except Exception:  # noqa: BLE001
            pass
    if st.get("objects"):
        sc.rebuild()
    v = st.get("view")
    if v and len(v) == 4 and all(isinstance(t, (int, float)) for t in v):
        _G.vp.cx, _G.vp.cy, _G.vp.sx, _G.vp.sy = v
    _G.vp.pi_mode = st.get("pi", "auto")
    _G.vp.grid = st.get("grid", True)
    _G.dirty = True


def _gsave():
    vp = _G.vp
    return json.dumps({"objects": [o.to_json() for o in _G.scene.objs], "view": [vp.cx, vp.cy, vp.sx, vp.sy],
                       "pi": vp.pi_mode, "grid": vp.grid}, ensure_ascii=False)


def _r(a):
    import numpy as np
    a = np.asarray(a, float).ravel()
    return [round(float(t), 1) for t in a]


def _thin(L, tol=0.6):
    """Saca puntos que casi no cambian el dibujo (a menos de tol px de la recta entre vecinos)."""
    import numpy as np
    L = np.asarray(L, float)
    if len(L) < 4:
        return L
    d = np.hypot(np.diff(L[:, 0]), np.diff(L[:, 1]))
    keep = [0]
    acc = 0.0
    for i in range(1, len(L) - 1):
        acc += d[i - 1]
        if acc >= tol * 1.5:
            p0, p1, p2 = L[keep[-1]], L[i], L[i + 1]
            v = p2 - p0
            n = np.hypot(*v)
            dev = abs(v[0] * (p1[1] - p0[1]) - v[1] * (p1[0] - p0[0])) / n if n > 0 else acc
            if dev > tol * 0.25 or acc > 6:
                keep.append(i)
                acc = 0.0
    keep.append(len(L) - 1)
    return L[keep]


def _enc_geo(o, g):
    import base64
    import numpy as np
    if not g:
        return None
    out = {}
    if "lines" in g:
        out["lines"] = [_r(_thin(L)) for L in g["lines"] if len(L) > 1]
    if "segs" in g and len(g["segs"]):
        out["segs"] = _r(g["segs"])
    if "mask" in g:
        M = g["mask"]
        out["mask"] = base64.b64encode(np.packbits(M.astype(np.uint8), axis=None).tobytes()).decode()
        out["mw"], out["mh"], out["step"] = int(M.shape[1]), int(M.shape[0]), g["step"]
        out["dash"] = bool(g.get("dash"))
    if "poly" in g:
        out["poly"] = _r(g["poly"])
        out["label"] = _r(g["label"])
        out["text"] = g.get("text", "")
    if "pt" in g:
        out["pt"] = _r(g["pt"])
        out["drag"] = bool(o.data.get("drag"))
    if "arrow" in g:
        out["arrow"] = _r([g["arrow"][0], g["arrow"][1]])
    if o.kind == "tangent" and "at" in o.data:
        out["at"] = _r(_G.vp.to_px(*o.data["at"]))
    return out


def _disp_row(o):
    try:
        return draw(from_linear(_G.scene.display_text(o)), px=16, color=o.color if not o.error else "#B3261E")
    except Exception:  # noqa: BLE001
        return draw(R.Row(list(o.text or "?")), px=16)


def gframe():
    from tnsestudio.graph import geom
    from tnsestudio.graph.model import fmt_num
    sc, vp = _G.scene, _G.vp
    vp.ensure_scale()
    geo = {}
    for o in sc.objs:
        if not o.visible or o.error or o.kind == "slider":
            continue
        try:
            geo[id(o)] = geom.geom(vp, o)
        except Exception:  # noqa: BLE001
            geo[id(o)] = None
    _G.geo = geo
    try:
        _G.special = geom.specials(vp)
    except Exception:  # noqa: BLE001
        _G.special = []
    objs = []
    for o in sc.objs:
        d = {"id": id(o), "name": o.name, "kind": o.kind, "color": o.color, "visible": o.visible,
             "error": o.error, "sel": o is vp.selected, "edit": o is _G.editing, "row": _disp_row(o)}
        if o.kind == "slider":
            d["slider"] = {"value": o.data.get("value", 1.0), "min": o.data.get("min", -5.0),
                           "max": o.data.get("max", 5.0), "step": o.data.get("step", 0.1),
                           "text": fmt_num(o.data.get("value", 1.0))}
        g = geo.get(id(o))
        if g is not None:
            d["geo"] = _enc_geo(o, g)
        objs.append(d)
    sp_ = []
    for x, y, t in _G.special:
        px, py = vp.to_px(x, y)
        sp_.append([round(px, 1), round(py, 1), "%s (%s, %s)" % (t, fmt_num(x), fmt_num(y))])
    out = {"view": [vp.cx, vp.cy, vp.sx, vp.sy, vp.w, vp.h], "pi": bool(geom.pi_axis(vp)), "pimode": vp.pi_mode,
           "grid": vp.grid, "objs": objs, "special": sp_, "hover": _G.hover, "msg": _G.msg,
           "editing": _G.editing.name if _G.editing is not None else None, "save": _gsave()}
    _G.msg = None
    return out


def _gobj(i):
    for o in _G.scene.objs:
        if id(o) == i:
            return o
    return None


def gaction(m):
    """Acciones del gráfico; devuelve True si hay que mandar el dibujo de nuevo."""
    import re
    from tnsestudio.graph import geom
    from tnsestudio.graph.model import fmt_num
    t = m["t"]
    sc, vp = _G.scene, _G.vp
    _G.hover = None
    if t == "gView":
        vp.w, vp.h = float(m.get("w", vp.w)), float(m.get("h", vp.h))
        if m.get("sx"):
            vp.cx, vp.cy, vp.sx, vp.sy = float(m["cx"]), float(m["cy"]), float(m["sx"]), float(m["sy"])
    elif t == "gEnter":
        text = AP.ed.text().strip()
        if re.match(r"^\s*bode\s*\(", text, re.I):
            _G.msg = "Bode todavía no está en el celular (sí en TNS Estudio del PC)."
            return True
        if not text:
            if _G.editing is not None:
                if vp.selected is _G.editing:
                    vp.selected = None
                sc.remove(_G.editing)
                _G.editing = None
            return True
        if _G.editing is not None:
            o = _G.editing
            sc.replace(o, text)
            _G.editing = None
        else:
            o = sc.add(text)
        AP.ed.clear()
        if o.error and not o.error.startswith("¿"):
            _G.msg = o.error
        vp.selected = o if o.kind != "slider" and not o.error else None
    elif t == "gEdit":
        o = _gobj(m["id"])
        if o is not None:
            _G.editing = o
            AP._set_sel(None)
            AP.ed.clear()
            AP.ed.insertRow(from_linear(o.text))
    elif t == "gCancelEdit":
        _G.editing = None
        AP.ed.clear()
    elif t == "gSel":
        o = _gobj(m["id"])
        vp.selected = None if (o is None or o.kind == "slider" or vp.selected is o) else o
        if o is not None and o.error:
            _G.msg = o.error
    elif t == "gToggle":
        o = _gobj(m["id"])
        if o is not None:
            o.visible = not o.visible
            sc.version += 1
    elif t == "gDel":
        o = _gobj(m["id"])
        if o is not None:
            if vp.selected is o:
                vp.selected = None
            if _G.editing is o:
                _G.editing = None
            sc.remove(o)
    elif t == "gColor":
        o = _gobj(m["id"])
        if o is not None:
            o.color = m["color"]
            sc.version += 1
    elif t == "gSlider":
        o = _gobj(m["id"])
        if o is not None:
            sc.set_slider(o, float(m["value"]))
    elif t == "gSliderRange":
        o = _gobj(m["id"])
        if o is not None:
            for k in ("min", "max", "step"):
                if k in m:
                    o.data[k] = float(m[k])
    elif t == "gPoint":
        o = _gobj(m["id"])
        if o is not None and o.kind == "point":
            x, y = vp.to_world(float(m["x"]), float(m["y"]))
            st = geom.snap_step(vp)
            x, y = round(x / st) * st, round(y / st) * st
            sx_, sy_ = fmt_num(x, 6).replace("−", "-"), fmt_num(y, 6).replace("−", "-")
            o.text = ("(%s,%s)" % (sx_, sy_)) if o.auto_name else "%s=(%s,%s)" % (o.name, sx_, sy_)
            o.row = None
            sc.rebuild()
    elif t == "gHit":
        mx, my = float(m["x"]), float(m["y"])
        h = geom.hit(vp, _G.geo, _G.special, mx, my, radius=14)
        if h and h[0] in ("curve", "region", "phasor", "point"):
            vp.selected = h[1]
        elif h is None:
            vp.selected = None
            x, y = vp.to_world(mx, my)
            _G.hover = [mx, my, "(%s, %s)" % (fmt_num(x), fmt_num(y)), "#5F6673"]
            return True
        hv = geom.hover(vp, h)
        if hv:
            _G.hover = [round(hv[0], 1), round(hv[1], 1), hv[2], hv[3]]
    elif t == "gFit":
        r = geom.fit(vp)
        if r is None:
            vp.standard()
        else:
            vp.cx, vp.cy, vp.sx, vp.sy = r
    elif t == "gStd":
        vp.standard()
    elif t == "gPi":
        vp.pi_mode = {"auto": "on", "on": "off"}.get(vp.pi_mode, "auto")
    elif t == "gGrid":
        vp.grid = not vp.grid
    elif t == "gRefresh":
        sc.rebuild()
    elif t == "gClear":
        vp.selected = None
        _G.editing = None
        sc.clear()
    elif t == "gPlot":                      # desde el historial de la calculadora: "Graficar"
        o = sc.add(m["s"])
        if o.error and not o.error.startswith("¿"):
            _G.msg = o.error
        vp.selected = o if o.kind != "slider" and not o.error else None
    return True

def action(msg_json):
    m = json.loads(msg_json)
    t = m.get("t")
    ed = AP.ed
    if t and t.startswith("g") and _G.scene is not None and t != "gBoot":
        try:
            gaction(m)
        except Exception as e:  # noqa: BLE001
            _G.msg = "No pude hacer eso (%s)" % str(e)[:120]
        st = json.loads(render(False))
        st["g"] = gframe()
        return json.dumps(st, ensure_ascii=False)
    if t == "gBoot":
        gboot(m.get("state", ""), m.get("w", 360), m.get("h", 480))
        st = json.loads(render(False))
        st["g"] = gframe()
        return json.dumps(st, ensure_ascii=False)
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
