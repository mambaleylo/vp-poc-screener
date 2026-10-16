"""EMA research: every first touch of EMA n on TF per period (entry at the EMA), features, the label grid."""
import sys, os, pickle, time, math, bisect
ARGS = sys.argv[1:]
import numpy as np
from common import V, load, D
from er_ind import TFS, EMAS, TF_I, ema_series, atr_series, rsi_series
import multiprocessing as mp
STOPS = (0.5, 1.0, 2.0, 3.0)        # daily ATR beyond the entry
TAKES = (1.0, 1.5, 2.0, 3.0)        # x the risk
HOLDS = (2, 7, 21)                  # days
FEE, FUND = 0.001, 0.0003           # round trip; funding per day (cost, both sides)
OUT = f"{D}/er"
_BTC = {}

def period_end(tf, ps):
    return ps + {"4h": 4 * 3600, "1d": 86400}[tf] if tf in ("4h", "1d") else V.emw_next_period(ps, tf)

def tf_bars(cs):
    daily = V._oc_agg(cs, 24)
    return {"4h": V._oc_agg(cs, 4), "1d": daily, "1w": V.emw_bars(daily, "1w"), "1M": V.emw_bars(daily, "1M")}, daily

def series(cs):
    B, daily = tf_bars(cs)
    S = {}
    for tf in TFS:
        bs = B[tf]
        C = [b["close"] for b in bs]
        S[tf] = {"bars": bs, "t": [b["time"] for b in bs], "end": [period_end(tf, b["time"]) for b in bs], "C": C,
                 "ema": {n: ema_series(C, n) for n in EMAS[tf]}, "atr": atr_series(bs, 14), "rsi": rsi_series(C, 14)}
    dC = S["1d"]["C"]
    S["1d"]["ema_ctx"] = {50: ema_series(dC, 50), 200: ema_series(dC, 200)}
    S["1w"]["ema_ctx"] = {21: ema_series(S["1w"]["C"], 21)}
    S["h1_rsi"] = rsi_series([c["close"] for c in cs], 14)
    return S

def last_closed(S, tf, t):
    """index of the last TF bar closed by time t (-1 none)"""
    return bisect.bisect_right(S[tf]["end"], t) - 1

def btc():
    if not _BTC:
        cs = load("BTCUSDT")
        _BTC["cs"] = cs
        _BTC["t"] = [c["time"] for c in cs]
        _BTC["S"] = series(cs)
    return _BTC

def _ret(C, j, k):
    return (C[j - 1] / C[j - 1 - k] - 1) * 100 if j - 1 - k >= 0 and C[j - 1 - k] > 0 else 0.0

def _round_near(lv):
    if lv <= 0:
        return 0.0
    lo, hi = lv * 0.997, lv * 1.003
    k = math.floor(math.log10(lv))
    for scale, w in ((10 ** k, 1.0), (10 ** k / 2, 0.7), (10 ** k / 10, 0.4)):
        q = math.ceil(lo / scale) * scale
        if q <= hi:
            return w
    return 0.0

def features(S, cs, Ch, Vh, j, tf, n, b, side, lv, bt):
    """everything known before the touch hour j (closed 1h bars < j, TF bars < b, the period's hours before j)"""
    T = S[tf]
    px = Ch[j - 1]
    kd = last_closed(S, "1d", cs[j]["time"])
    dS = S["1d"]
    if kd < 20 or dS["atr"][kd] is None:
        return None
    datr = dS["atr"][kd] / dS["C"][kd] * 100
    if datr < 0.1:
        return None   # a dead coin (no daily range)
    dpx = datr / 100 * px
    A = T["atr"][b - 1]
    if not A or A <= 0 or dpx <= 0:
        return None
    k0 = cs_index(cs, T["t"][b])
    lows = [x["low"] for x in T["bars"][max(0, b - 3):b]] + [cs[i]["low"] for i in range(k0, j)]
    highs = [x["high"] for x in T["bars"][max(0, b - 3):b]] + [cs[i]["high"] for i in range(k0, j)]
    ext = min(lows) if side < 0 else max(highs)
    f = {"tf": float(TF_I[tf]), "n": math.log(n), "side": float(side)}
    f["rise3"] = abs(lv - ext) / A
    f["rise3_d"] = abs(lv - ext) / dpx
    op = cs[k0]["open"]
    f["rise_live"] = abs(lv - op) / A
    vals = [T["ema"][m][b - 1] for m in EMAS[tf] if T["ema"][m][b - 1] is not None]
    pc = T["C"][b - 1]
    f["n_emas"] = float(len(vals))
    f["beyond"] = float(sum(1 for v in vals if (v > pc if side < 0 else v < pc)))   # EMAs on the far side of the price
    f["beyond_sh"] = f["beyond"] / len(vals) if vals else 0.0
    e = T["ema"][n]
    f["slope"] = (-side) * (e[b - 1] - e[b - 4]) / A if b >= 4 and e[b - 4] is not None else 0.0
    f["dist_prev"] = side * (pc - lv) / A
    since = 0
    for k in range(b - 1, max(-1, b - 201), -1):
        if e[k] is None:
            break
        if (T["C"][k] > e[k]) if side < 0 else (T["C"][k] < e[k]):
            break
        since += 1
    f["since"] = math.log1p(since)
    f["touches20"] = float(sum(1 for k in range(max(0, b - 20), b) if e[k] is not None and T["bars"][k]["low"] <= e[k] <= T["bars"][k]["high"]))
    r = T["rsi"][b - 1]
    f["s_rsi_tf"] = ((r if r is not None else 50.0) - 50) * (-side)
    rd = dS["rsi"][kd]
    f["s_rsi_d"] = ((rd if rd is not None else 50.0) - 50) * (-side)
    rh = S["h1_rsi"][j - 1]
    f["s_rsi_h"] = ((rh if rh is not None else 50.0) - 50) * (-side)
    for m in (50, 200):
        ev = dS["ema_ctx"][m][kd]
        f[f"s_d_ema{m}"] = side * (px - ev) / dpx if ev else 0.0
    kw = last_closed(S, "1w", cs[j]["time"])
    ew = S["1w"]["ema_ctx"][21][kw] if kw >= 0 else None
    f["s_w_ema21"] = side * (px / ew - 1) * 100 if ew else 0.0
    for nm, k in (("r24", 24), ("r72", 72), ("r7d", 168)):
        f["s_" + nm] = side * _ret(Ch, j, k)
    # BTC at the same hour
    bj = bisect.bisect_left(bt["t"], cs[j]["time"])
    bC = [c["close"] for c in bt["cs"][max(0, bj - 200):bj]]
    f["s_b24"] = side * _ret(bC, len(bC), 24) if len(bC) > 25 else 0.0
    f["s_b7d"] = side * _ret(bC, len(bC), 168) if len(bC) > 169 else 0.0
    bkd = last_closed(bt["S"], "1d", cs[j]["time"])
    be = bt["S"]["1d"]["ema_ctx"][50][bkd] if bkd >= 0 else None
    f["s_b_ema50"] = side * (bt["S"]["1d"]["C"][bkd] / be - 1) * 100 if be else 0.0
    f["s_rs7"] = f["s_r7d"] - f["s_b7d"]
    dd = dS["bars"]
    for m in (30, 90, 365):
        seg = dd[max(0, kd - m + 1):kd + 1]
        hh, ll = max(x["high"] for x in seg), min(x["low"] for x in seg)
        pos = (px - ll) / (hh - ll) if hh > ll else 0.5
        f[f"s_pos{m}"] = pos if side > 0 else 1 - pos
    f["datr"] = datr
    f["atr_tf"] = A / px * 100
    v24 = sum(Vh[max(0, j - 24):j])
    v20 = sum(Vh[max(0, j - 480):j]) / 20 if j > 24 else 0
    f["vol24"] = math.log((v24 + 1e-9) / (v20 + 1e-9)) if v20 > 0 else 0.0
    conf, near = 0, 99.0
    for tf2 in TFS:
        k2 = last_closed(S, tf2, cs[j]["time"]) if tf2 != tf else b - 1
        if k2 < 0:
            continue
        for m in EMAS[tf2]:
            if tf2 == tf and m == n:
                continue
            v = S[tf2]["ema"][m][k2]
            if v is None:
                continue
            dz = abs(v - lv) / dpx
            near = min(near, dz)
            conf += dz <= 0.3
    f["conf"] = float(conf)
    f["near"] = min(near, 20.0)
    f["prog"] = (cs[j]["time"] - T["t"][b]) / (T["end"][b] - T["t"][b])
    f["round"] = _round_near(lv)
    return {k: round(float(v), 5) for k, v in f.items()}

_IDX = {}
def cs_index(cs, t):
    return bisect.bisect_left(_IDX["t"], t)

def labels(O, H, L, C, j, side, fill, datr):
    """the grid: stop a daily ATR past the fill, take R x the risk, out after h days; R net of fees & funding"""
    out = []
    n = len(C)
    for a in STOPS:
        risk = fill * a * datr / 100
        stop = fill - side * risk
        e = min(n, j + 24 * max(HOLDS))
        Hs, Ls = H[j:e], L[j:e]
        hit_s = (Ls <= stop) if side > 0 else (Hs >= stop)
        ks = int(np.argmax(hit_s)) if hit_s.any() else -1
        for R in TAKES:
            tp = fill + side * R * risk
            hit_t = (Hs >= tp) if side > 0 else (Ls <= tp)
            hit_t[0] = False                       # the entry hour: only the stop counts (conservative)
            kt = int(np.argmax(hit_t)) if hit_t.any() else -1
            for h in HOLDS:
                lim = min(len(Hs), 24 * h)
                s_ = ks if 0 <= ks < lim else -1
                t_ = kt if 0 <= kt < lim else -1
                if s_ >= 0 and (t_ < 0 or s_ <= t_):
                    k = s_
                    gap = (O[j + k] <= stop) if side > 0 else (O[j + k] >= stop)
                    ex = O[j + k] if (gap and k > 0) else stop
                elif t_ >= 0:
                    k, ex = t_, tp
                else:
                    k = lim - 1
                    ex = C[j + k]
                days = (k + 1) / 24
                r = side * (ex - fill) / risk - (FEE + FUND * days) * fill / risk
                out.append((round(float(r), 4), int(k + 1)))
    return out

def run(sym):
    fn = f"{OUT}/{sym}.pkl"
    if os.path.exists(fn):
        return sym, -1
    t0 = time.time()
    cs = load(sym)
    if not cs or len(cs) < 24 * 120:
        return sym, 0
    _IDX["t"] = [c["time"] for c in cs]
    S = series(cs)
    bt = btc()
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    Ch = [c["close"] for c in cs]; Vh = [c["volume"] for c in cs]
    rows = []
    for tf in TFS:
        T = S[tf]
        for b in range(1, len(T["bars"])):
            k0 = cs_index(cs, T["t"][b])
            k1 = bisect.bisect_left(_IDX["t"], T["end"][b])
            if k1 - k0 < 1 or k0 < 24 * 30:
                continue
            op = O[k0]
            for n in EMAS[tf]:
                lv = T["ema"][n][b - 1]
                if lv is None or op == lv:
                    continue
                side = 1 if op > lv else -1
                hit = (L[k0:k1] <= lv) if side > 0 else (H[k0:k1] >= lv)
                if not hit.any():
                    continue
                j = k0 + int(np.argmax(hit))
                if j + 24 * 2 >= len(cs):
                    continue          # (the limit sits at the EMA from the period's open: the first hour counts too)
                fill = lv
                f = features(S, cs, Ch, Vh, j, tf, n, b, side, lv, bt)
                if f is None:
                    continue
                rows.append({"t": int(cs[j]["time"]), "j": j, "tf": tf, "n": n, "side": side, "lv": lv, "f": f,
                             "lab": labels(O, H, L, C, j, side, fill, f["datr"])})
    os.makedirs(OUT, exist_ok=True)
    pickle.dump(rows, open(fn, "wb"))
    return sym, len(rows), round(time.time() - t0)

if __name__ == "__main__":
    syms = ARGS or sorted(f[:-4] for f in os.listdir(f"{D}/data/1h"))
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(run, syms):
            print(*res, flush=True)
