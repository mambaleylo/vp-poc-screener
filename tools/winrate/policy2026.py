"""the orders of one coin & side (a 4h and a 2h one can stand together; the price reaches the nearer one first and its
trade blocks the deeper one) — policies decided when an order is made (causal), on every order the bot's scans made in
the replays (replay693_*.json: filled or not), 1h touches (the nearer level first in an hour), the v0.99.690 exits,
one position a coin, 20 a side, 20 positions; money from $100 at 4%, cautious. usage: policy2026.py GLOB"""
import sys; AV = list(sys.argv)
import os, json, glob, numpy as np
os.environ["TFH"] = "4"
exec(open("best_money.py").read().split("za = np.load")[0])
import s23_engine as E4, s21h2_engine as E2, s19h_engine as E1
from numba import njit
exec("@njit\ndef ex" + open("tkext.py").read().split("@njit\ndef ex")[1].split("\ndef run")[0])
def bname(gs):
    b = gs.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        if os.path.exists(f"s23_4h/{c}.npz") or os.path.exists(f"s23_4hx/{c}.npz"): return c, scl
BARS, H1 = {}, {}
def bars(gs, bs):
    if (gs, bs) not in BARS:
        c, scl = bname(gs); T, O, H, L, C, V = (E2 if bs == 7200 else E4).load15(c); BARS[(gs, bs)] = (T.astype(np.int64), O / scl, H / scl, L / scl, C / scl)
    return BARS[(gs, bs)]
def h1(gs):
    if gs not in H1:
        c, scl = bname(gs); T, O, H, L, C, V = E1.load15(c); H1[gs] = (T.astype(np.int64), O / scl, H / scl, L / scl)
    return H1[gs]
OR = []
for f in sorted(glob.glob(AV[1] if len(AV) > 1 else "replay693_[0-9].json")):
    d_ = json.load(open(f)); OR += [o for o in d_["orders"] if d_["from"] <= o["t0"] < d_["to"]]
OR.sort(key=lambda o: (o["t0"], -o["score"]))
for o in OR:
    T, O, H, L = h1(o["symbol"]); s, lv, a = o["side"], o["lv"], o["atr"]
    i, j = int(np.searchsorted(T, o["t0"])), int(np.searchsorted(T, o["until"]))
    o["ft1"] = None
    for b in range(i, j):
        if (L[b] <= lv) if s > 0 else (H[b] >= lv):
            o["ft1"] = int(T[b]); o["d1"] = s * (O[b] - lv) / a; break
    if o["ft1"] is None: continue
    Tb, Ob, Hb, Lb, Cb = bars(o["symbol"], o["bs"]); fb = int(np.searchsorted(Tb, o["ft1"] // o["bs"] * o["bs"]))
    fill = min(lv, Ob[fb]) if s > 0 else max(lv, Ob[fb])
    R, k, kk = ex(Ob, Hb, Lb, Cb, fb, s, fill, a, 0.4, 1.0, 0, o["bs"] // 3600)
    o.update(end=int(Tb[min(len(Tb) - 1, fb + kk)]) + o["bs"], R=float(R), stp=float(np.clip(2 * a / fill, 0.002, 0.5)))
print("orders", len(OR), "touched", sum(o["ft1"] is not None for o in OR), flush=True)
def run(policy, streams=("wick4h", "close2h")):
    alive = {}   # (coin, side) -> the orders kept, by the policy at their making
    kept = []
    for o in OR:
        if o["st"] not in streams: continue
        k = (o["symbol"], o["side"])
        cur = [x for x in alive.get(k, []) if x["until"] > o["t0"] and (x["ft1"] is None or x["ft1"] >= o["t0"])]   # still waiting at this scan
        if policy == "both":
            cur.append(o)
        elif policy == "best_score":
            if all(o["score"] > x["score"] for x in cur): cur = [o]
        elif policy == "deeper":
            if all(o["side"] * (x["lv"] - o["lv"]) > 0 for x in cur): cur = [o]   # a lower long / a higher short
        elif policy == "first":
            if not cur: cur = [o]
        elif policy == "prio4h":   # a 4h order: kept, the waiting 2h ones go; a 2h order: kept only with no 4h one waiting
            if o["st"] == "wick4h": cur = [x for x in cur if x["st"] == "wick4h"] + [o]
            elif not any(x["st"] == "wick4h" for x in cur): cur.append(o)
        alive[k] = cur
        if o in cur: kept.append(o)
    drop = {id(x) for x in OR} - {id(x) for x in kept}
    # a kept order dropped later by a better one: dropped from that moment (only if not touched before)
    ev = sorted([(o["ft1"], o["d1"], -o["score"], id(o), o) for o in kept if o["ft1"] is not None])
    final = {}
    for k in alive: pass
    # who replaced whom: re-walk to find each kept order's cancel time
    cancel = {}
    alive = {}
    for o in OR:
        if o["st"] not in streams or id(o) in drop: continue
        k = (o["symbol"], o["side"])
        cur = [x for x in alive.get(k, []) if x["until"] > o["t0"] and (x["ft1"] is None or x["ft1"] >= o["t0"])]
        if policy == "prio4h":
            if o["st"] == "wick4h":
                for x in cur:
                    if x["st"] != "wick4h": cancel[id(x)] = o["t0"]
                cur = [x for x in cur if x["st"] == "wick4h"] + [o]
            else:
                cur.append(o)
        elif policy != "both":
            for x in cur: cancel[id(x)] = o["t0"]
            cur = [o]
        else:
            cur.append(o)
        alive[k] = cur
    real, out = [], []
    for ft, d1, _, _, o in ev:
        if id(o) in cancel and cancel[id(o)] <= ft: continue
        real[:] = [x for x in real if x["end"] > ft]
        if any(x["symbol"] == o["symbol"] for x in real): continue
        if len(real) >= 20 or sum(1 for x in real if x["side"] == o["side"]) >= 20: continue
        real.append(o); out.append(o)
    return out
def money(lst, nm):
    P = np.array(sorted((o["ft1"], o["end"], o["R"], o["stp"]) for o in lst), float); t0, t1, R, STv = P.T
    A = t0.min(); v = sim(t0, t1, R, STv, 0, t0.max() + 1, 20, 0.04, -0.025); vh = sim(t0, t1, R, STv, 0, t0.max() + 1, 20, 0.04, -0.04)
    y3 = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 91 * 86400.0, 20, 0.04, -0.025)[0] for s_ in np.arange(A, t0.max() - 91 * 86400, 7 * 86400.0)])
    print(f"{nm:40s} сделок {len(R):4d} {R.mean():+.3f}R WR {np.mean(R > 0)*100:.0f}% | весь период $100 → ${v[0]:,.0f} (просадка {v[1]*100:.0f}%, жёстко ${vh[0]:,.0f}) | 3 мес медиана ${np.median(y3):,.0f} хуже 10% ${np.percentile(y3, 10):,.0f}", flush=True)
for pol, nm in (("prio4h", "4ч в приоритете (2ч только без 4ч)"), ("both", "обе стоят, первая по касанию (сейчас)"), ("best_score", "на монету одна: лучшая оценка"), ("deeper", "на монету одна: глубже"), ("first", "на монету одна: первая")):
    money(run(pol), nm)
money(run("both", ("wick4h",)), "только 4ч")
money(run("both", ("close2h",)), "только 2ч")
