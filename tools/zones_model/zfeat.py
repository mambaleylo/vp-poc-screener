"""Stage B features — pure Python (the same code will run in the bot). Bars are lists of dicts
(time/open/high/low/close/volume), closed, oldest first. Signed so that + favours the zone's side."""
import math

def _ema(vals, n):
    k = 2 / (n + 1)
    e = vals[0]
    for v in vals[1:]:
        e += k * (v - e)
    return e

def _rsi(C, n=14):
    if len(C) < n + 2:
        return 50.0
    g = l = 0.0
    for i in range(1, n + 1):
        d = C[i] - C[i - 1]
        g += max(d, 0); l += max(-d, 0)
    g /= n; l /= n
    for i in range(n + 1, len(C)):
        d = C[i] - C[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        l = (l * (n - 1) + max(-d, 0)) / n
    return 100.0 if l == 0 else 100 - 100 / (1 + g / l)

def _atr(B, n=14):
    if len(B) < 2:
        return 0.0
    trs = [max(B[i]["high"] - B[i]["low"], abs(B[i]["high"] - B[i - 1]["close"]), abs(B[i]["low"] - B[i - 1]["close"]))
           for i in range(max(1, len(B) - n), len(B))]
    return sum(trs) / len(trs)

def _ret(C, k):
    return (C[-1] / C[-1 - k] - 1) * 100 if len(C) > k and C[-1 - k] > 0 else 0.0

def _clip(v, a=-50.0, b=50.0):
    return max(a, min(b, v))

def snap_feats(h1, d1, btc_h1, btc_d1):
    """coin / market state at the snapshot (shared by its candidates); unsigned"""
    C = [b["close"] for b in h1]
    D = [b["close"] for b in d1]
    px = C[-1]
    datr = _atr(d1, 14) / px * 100 if d1 else 0.0
    a1 = _atr(h1, 48) / px * 100
    f = {"r24": _ret(C, 24), "r72": _ret(C, 72), "r7d": _ret(C, 168), "r20d": _ret(C, 479) if len(C) > 479 else _ret(C, len(C) - 1),
         "rsi1": _rsi(C[-200:]), "rsi4": _rsi([C[i] for i in range(len(C) - 1, -1, -4)][::-1][-200:]), "rsi_d": _rsi(D[-200:]) if len(D) > 20 else 50.0,
         "datr": datr, "volreg": (a1 * math.sqrt(24)) / datr if datr else 1.0}
    for n in (20, 50, 200):
        f[f"ema{n}"] = (px / _ema(D[-3 * n:], n) - 1) * 100 / (datr or 1) if len(D) >= n else 0.0
    for n in (30, 90, 365):
        seg = d1[-n:]
        if len(seg) >= min(n, 20):
            hh, ll = max(b["high"] for b in seg), min(b["low"] for b in seg)
            f[f"pos{n}"] = (px - ll) / (hh - ll) if hh > ll else 0.5
        else:
            f[f"pos{n}"] = 0.5
    V = [b["volume"] for b in h1]
    f["vol24"] = math.log((sum(V[-24:]) / 24 + 1e-12) / (sum(V) / len(V) + 1e-12)) if V else 0.0
    BC = [b["close"] for b in btc_h1] if btc_h1 else []
    BD = [b["close"] for b in btc_d1] if btc_d1 else []
    f["b24"] = _ret(BC, 24) if BC else 0.0
    f["b7d"] = _ret(BC, 168) if BC else 0.0
    f["b_ema50"] = (BD[-1] / _ema(BD[-150:], 50) - 1) * 100 if len(BD) >= 50 else 0.0
    f["b_datr"] = _atr(btc_d1, 14) / BD[-1] * 100 if len(BD) > 15 else 0.0
    f["rs7"] = f["r7d"] - f["b7d"]
    f["rs20"] = f["r20d"] - (_ret(BC, 479) if len(BC) > 479 else 0.0)
    return f

SIGNED = ("r24", "r72", "r7d", "r20d", "ema20", "ema50", "ema200", "b24", "b7d", "b_ema50", "rs7", "rs20")

def _round_in(lo, hi):
    """a round price inside the zone: 1/2/5 x 10^k at the zone's scale"""
    mid = (lo + hi) / 2
    if mid <= 0:
        return 0.0
    k = math.floor(math.log10(mid))
    best = 0.0
    for scale, w in ((10 ** k, 1.0), (10 ** k / 2, 0.7), (10 ** k / 10, 0.4)):
        q = math.ceil(lo / scale) * scale
        if q <= hi:
            best = max(best, w)
    return best

def cand_feats(c, h1, d1, sf, cands_all):
    """per candidate; c: {"side","lo","hi","tf","atr",...}; sf: snap_feats"""
    sg = 1 if c["side"] == "long" else -1
    lo, hi = c["lo"], c["hi"]
    px = h1[-1]["close"]
    datr_px = sf["datr"] / 100 * px or 1e-12
    near_edge = hi if sg > 0 else lo
    far_edge = lo if sg > 0 else hi
    f = {"side": float(sg), "d_dist": (sg * (px - near_edge)) / datr_px, "d_width": (hi - lo) / datr_px,
         "round": _round_in(lo, hi)}
    for k in SIGNED:
        f["s_" + k] = sg * sf[k]
    for k in ("rsi1", "rsi4", "rsi_d"):
        f["s_" + k] = (sf[k] - 50) * sg
    for n in (30, 90, 365):
        f["s_pos" + str(n)] = sf["pos" + str(n)] if sg > 0 else 1 - sf["pos" + str(n)]
    # freshness on the daily+1h history: entries into the zone since the last clear departure (> 1 datr away)
    bars = d1[-365:]
    entries, last_touch, dep_max, swept = 0, None, 0.0, 0
    away = False
    for i, b in enumerate(bars):
        inside = (b["low"] <= hi and b["high"] >= lo)
        if inside:
            if away:
                entries += 1
            away = False
            last_touch = i
            if (sg > 0 and b["low"] < far_edge and b["close"] > far_edge) or (sg < 0 and b["high"] > far_edge and b["close"] < far_edge):
                swept += 1
        else:
            dist = (b["low"] - hi) if sg > 0 else (lo - b["high"])
            if dist > datr_px:
                away = True
            if last_touch is not None:
                dep_max = max(dep_max, dist / datr_px) if i - last_touch <= 10 else dep_max
    f["d_entries"] = math.log1p(entries)
    f["d_age_touch"] = math.log1p(len(bars) - last_touch) if last_touch is not None else 7.0
    f["d_dep"] = min(dep_max, 30.0)
    f["d_swept"] = math.log1p(swept)
    # broken through (a daily close beyond the far edge) in the last 90 days
    f["d_broken90"] = float(sum(1 for b in d1[-90:] if (b["close"] < far_edge if sg > 0 else b["close"] > far_edge)))
    # confluence: other candidates (other charts) overlapping
    conf = 0
    for o in cands_all:
        if o is c or o["side"] != c["side"]:
            continue
        if min(o["hi"], hi) - max(o["lo"], lo) > 0:
            conf += 1
    f["conf"] = float(conf)
    # the zone vs the 365d extreme: how far beyond the zone the year's low (long) lies
    if d1:
        ext = min(b["low"] for b in d1[-365:]) if sg > 0 else max(b["high"] for b in d1[-365:])
        f["d_to_ext"] = (sg * (far_edge - ext)) / datr_px
    else:
        f["d_to_ext"] = 0.0
    return {k: round(_clip(float(v), -1e3, 1e3), 4) for k, v in f.items()}
