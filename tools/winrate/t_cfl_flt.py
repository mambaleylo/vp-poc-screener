"""v0.99.781 — 🔄 Классика's filters: (1) cfl_flt_ok on the rule's bars (pos90 < 0.7536, atr_h > 0.2207, d_e50 < 0.7366), the
edges and a missing value fail as in the lab (NaN compares false); (2) the scan: of two candidates over the threshold the filtered
one is not opened, the other one is; the threshold's score store still gets both (the lab's threshold is of every event)"""
import math
from common import V
ok = True
def chk(nm, c):
    global ok
    print(("OK  " if c else "FAIL") + " " + nm); ok &= bool(c)
V.CFL_MODEL_FILE = "/home/user/vp-poc-screener/vp_cfl_model.json"; V._CFL["model"] = None
m = V.cfl_model(); r = m["rule"]
chk(f"в правиле 3 фильтра: {r.get('flt')}", [f[0] for f in r.get("flt") or []] == ["pos90", "atr_h", "d_e50"])
I = {n: V.CFL_FNAMES.index(n) for n in ("pos90", "atr_h", "d_e50")}
def f_(pos90=0.5, atr_h=0.5, d_e50=0.1):
    x = [0.0] * len(V.CFL_FNAMES); x[I["pos90"]], x[I["atr_h"]], x[I["d_e50"]] = pos90, atr_h, d_e50; return x
chk("обычный сигнал проходит", V.cfl_flt_ok(r, f_()))
chk("у вершины 90-дневного диапазона — нет", not V.cfl_flt_ok(r, f_(pos90=0.80)))
chk("ровно на границе pos90 — нет (как в лабе: строго меньше)", not V.cfl_flt_ok(r, f_(pos90=0.7536)))
chk("тихий час — нет", not V.cfl_flt_ok(r, f_(atr_h=0.1)))
chk("далеко над EMA50 — нет", not V.cfl_flt_ok(r, f_(d_e50=1.0)))
chk("нет значения (NaN) — нет", not V.cfl_flt_ok(r, f_(atr_h=float("nan"))))
chk("правило без фильтров — всё проходит", V.cfl_flt_ok({}, f_(pos90=0.99)))
# (2) the scan, the data mocked: A passes, B is at the top of its range; both over the threshold
A, B = m["thr_coins"][0], m["thr_coins"][1]
FX = {A: f_(), B: f_(pos90=0.9)}
for x in FX.values(): x[2] = 4.0   # datr
V.cfl_threshold = lambda m_, t, q=None: 0.6 if q is not None else 0.9
V.cfl_klines = lambda bsym, iv, n: ([1], [1.0], [1.0], [1.0], [1.0], [1.0])
V.cfl_tf_events_at = lambda h4, d1, t: [1]
V.cfl_oi = lambda b: None; V.cfl_funding = lambda b: None; V.heartbeat = lambda *a, **k: None; V.time.sleep = lambda s: None
V._CFL["first"] = {c: 0 for c in m["coins"]}
V.cfl_coin_events = lambda bsym, t_close, m_, *a: [(0, -1, FX[bsym])] if bsym in FX else []
V.cfl_score = lambda m_, f: 0.95
added = []; V.cfl_add_score = lambda day, sc: added.append(sc)
opened = []
V.cfl_open = lambda c, t_close, m_: opened.append(c["bsym"]) or True
V._CFL["trades"] = [{"t_in": 10 ** 10, "status": "CLOSED"}]
V.cfl_save = lambda: None
V.cfl_scan(int(V.time.time()) // 14400 * 14400)
chk(f"скан: открыта только прошедшая фильтры ({opened}), в порог попали обе оценки ({len(added)})", opened == [A] and len(added) == 2)
print("t_cfl_flt OK" if ok else "t_cfl_flt FAIL")
