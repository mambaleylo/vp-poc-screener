"""📐 EMA improvement round (the user: "нужно улучшить индикатор ema из связки… увеличиваем количество сделок, лучше стоп и тейк…
идеи можно брать из лимиток"): the deployed v12 list (tools/winrate ema_export11.py: the yearly walk-forward scores, longs, the
filters, the nearer touch first, the stop at a 4h close 0.75 dATR, the emergency 1.5 dATR, 1/3 at +1R then breakeven, take
4R, 72 h) re-made with one thing changed per variant -> <LABSTORE>/wf/ema_var_<name>.json in the money's format (t0, t1, r,
st, sth, mod "emx", sym, side, e); tools/winrate money_ema.py judges them in the bundle's strictest money.
usage: python3 ema_var.py [names…]   (from tools/ema_model; mfeat's metrics read from the lab-store)"""
import os, sys, json, numpy as np, pandas as pd
ARGV = sys.argv[1:]   # common.py (via ema_h) resets sys.argv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "new_data"))
import ema_h as E
from mk import ts
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
d = E.d
BASE = dict(sides=(1,), q=0.96, max_e200=10.0, tf4h=False, margin4h=0.1, deep=0.2, stop=0.75, take=4.0, hold=72, pa=1.0, pf=0.33, hard_x=2.0, kh=4,
            bema=True, ls=True, cap=12, pm=0.1, xs=None)
VARS = {
    "base": {},
    "q94": dict(q=0.94), "q92": dict(q=0.92), "q90": dict(q=0.90),                       # more trades: a lower threshold
    "tf4h": dict(tf4h=True),                                                             # + the 4h touches (with the score margin)
    "shorts": dict(sides=(1, -1)),                                                       # + shorts (the filters mirrored by the side)
    "deep0": dict(deep=0.0), "deep4": dict(deep=0.4),                                    # the limit at / deeper past the EMA (⚡'s depth)
    "stop1": dict(stop=1.0), "stop05": dict(stop=0.5),                                   # the stop
    "take3": dict(take=3.0), "take6": dict(take=6.0),                                    # the take
    "nopart": dict(pf=0.0), "hold120": dict(hold=120), "hard15": dict(hard_x=1.5), "hard3": dict(hard_x=3.0),
    "kh1": dict(kh=1), "kh24": dict(kh=24),                                              # the close stop on 1h / 1d closes
    "pm0": dict(pm=0.0),                                                                 # any touch of the limit (the bot's market entry fires on it)
    "xsc": dict(xs=(1.25, 0.85)), "xsc2": dict(xs=(1.5, 0.75)),                       # the risk by the score (⚡'s o2 x0.75): top 2% of the year's scores x hi, the rest x lo
    "nols": dict(ls=False), "e200_15": dict(max_e200=15.0), "cap20": dict(cap=20),
}
side_, tf_, e200_ = d.side.values, d.tf_s.values, d.s_d_ema200.values
bema_ = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
import mfeat
_cwd = os.getcwd(); os.chdir(ST)
LS_ = mfeat.at(d.sym.values, E.T - 3600)[:, mfeat.NAMES.index("ls_d24")] * side_
os.chdir(_cwd)
_TB = {}
def tb(sym):
    if sym not in _TB:
        _TB.clear(); _TB[sym] = np.array([c["time"] for c in E.load(sym)], np.int64)
    return _TB[sym]
def sim(O, H, L, C, Tb, j, side, fill, datr, p):
    n = len(C); risk = fill * p["stop"] * datr / 100
    ssl = fill - side * risk; hsl = fill - side * p["hard_x"] * risk; tp = fill + side * p["take"] * risk; pt = fill + side * p["pa"] * risk; took = False
    e = min(n, j + p["hold"]); k = e - 1 - j; ex = C[e - 1]; kind = "time"
    for q in range(e - j):
        b = j + q
        if (side > 0 and L[b] <= hsl) or (side < 0 and H[b] >= hsl):
            gap = (side > 0 and O[b] <= hsl) or (side < 0 and O[b] >= hsl)
            ex = O[b] if (gap and q > 0) else hsl; k = q; kind = "be" if took else "hard"; break
        if p["pf"] > 0 and q > 0 and not took and ((side > 0 and H[b] >= pt) or (side < 0 and L[b] <= pt)):
            took = True; hsl = fill
        if q > 0 and ((side > 0 and H[b] >= tp) or (side < 0 and L[b] <= tp)):
            ex = tp; k = q; kind = "take"; break
        if not took and (Tb[b] + 3600) % (p["kh"] * 3600) == 0 and ((side > 0 and C[b] <= ssl) or (side < 0 and C[b] >= ssl)):
            ex = C[b]; k = q; kind = "stop"; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * fill / risk
    rest = side * (ex - fill) / risk
    return ((p["pf"] * p["pa"] + (1 - p["pf"]) * rest) if took else rest) - fee, k + 1
def build(p):
    for Y in (2022, 2023, 2024, 2025):
        sc_ = E.S[str(Y)]; ref_ = (E.T >= ts(Y - 1)) & (E.T < ts(Y) - 21 * 86400); E.THR[Y][p["q"]] = float(np.quantile(sc_[ref_], p["q"]))
    mask = np.isin(side_, p["sides"]) & (e200_ < p["max_e200"])
    if p["bema"]: mask &= bema_ > 0
    if p["ls"]: mask &= ~(LS_ < 0.00314)
    thr_ = np.array([E.THR[y][p["q"]] if y in E.THR else np.inf for y in E.YR])
    idx = np.where((E.YR >= 2022) & (E.SC >= thr_) & mask)[0]   # E.cand without its own pen >= 0.1 (the pen rule below)
    if p["tf4h"]:   # a 4h touch only with the score margin over the year's threshold (v0.99.644)
        thr = np.array([E.THR[y][p["q"]] if y in E.THR else np.inf for y in E.YR])
        idx = idx[(tf_[idx] != "4h") | (E.SC[idx] >= thr[idx] + p["margin4h"])]
    else:
        idx = idx[tf_[idx] != "4h"]
    idx = idx[d.pen.values[idx] >= p["pm"] + p["deep"] * d.datr.values[idx]]
    FILL = lambda i: float(d.lv.values[i]) * (1 - int(side_[i]) * p["deep"] * float(d.datr.values[i]) / 100)
    R = np.full(len(d), np.nan); K = np.zeros(len(d), np.int64); OPEN = np.full(len(d), np.nan)
    for i in idx:
        sym = d.sym.values[i]; O, H, L, C = E.bars(sym); j = int(d.j.values[i])
        R[i], K[i] = sim(O, H, L, C, tb(sym), j, int(side_[i]), FILL(i), float(d.datr.values[i]), p)
        OPEN[i] = O[j] if j < len(O) else np.nan
    near = np.full(len(d), np.inf)
    for i in idx: near[i] = side_[i] * (OPEN[i] - FILL(i)) / (d.lv.values[i] * d.datr.values[i] / 100)
    o = idx[np.lexsort((near[idx], E.T[idx]))]; busy, act, out = {}, [], []
    for i in o:   # the bot's pool: the nearer touch first, one a coin & side, at most cap a side
        t = E.T[i]; k_ = (d.sym.values[i], side_[i])
        if busy.get(k_, 0) > t or R[i] != R[i]: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == side_[i]) >= p["cap"]: continue
        end = t + K[i] * 3600; busy[k_] = end; act.append((end, side_[i]))
        fill = FILL(i); st = max(0.002, p["stop"] * float(d.datr.values[i]) / 100); sth = max(st, st * p["hard_x"])
        x = {"t0": int(t), "t1": int(end), "r": float(R[i]), "st": st, "sth": sth, "mod": "emx", "sym": str(d.sym.values[i]),
             "side": int(side_[i]), "e": fill, "stream": None}
        if p["xs"]:   # the thresholds of the year from the previous year's scores (E.THR, no look-ahead)
            x["xm"] = p["xs"][0] if E.SC[i] >= E.THR[min(E.YR[i], 2025)][0.98] else p["xs"][1]
        out.append(x)
    return out
if __name__ == "__main__":
    names = ARGV or list(VARS)
    for nm in names:
        p = dict(BASE)
        for part in nm.split("+"): p.update(VARS[part])   # "a+b": the variants combined
        L = build(p); r = np.array([x["r"] for x in L])
        yrs = " ".join(f"{Y}: {int(((np.array([x['t0'] for x in L]) >= ts(Y)) & (np.array([x['t0'] for x in L]) < ts(Y + 1))).sum())}"
                       f" {r[(np.array([x['t0'] for x in L]) >= ts(Y)) & (np.array([x['t0'] for x in L]) < ts(Y + 1))].mean():+.2f}" for Y in (2022, 2023, 2024, 2025, 2026))
        print(f"{nm:8s}: {len(L)} сделок, {r.mean():+.3f}R, WR {(r > 0).mean() * 100:.0f}% | {yrs}", flush=True)
        json.dump(L, open(f"{ST}/wf/ema_var_{nm}.json", "w"))
    print("ema var done", flush=True)
