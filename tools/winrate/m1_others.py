"""audit of P/R, SMC, EMA like ⚡: their backtest lists (vp_bt_trades.json) re-walked on Binance 1m candles (40 coins, 10.2024
on): the fill (the limit / the touch reached 0.05% through within its hour), then minute by minute — EMA: the stop, the
partial 1/3 at +1R from the hour after the touch -> the stop to the entry, the take 4R, out after 72 h; SMC: the stop, the
take 3R, 72 h; P/R: the hard stop by a touch, the soft stop at a 1h close beyond it, the take, 48 h; R as the lists"""
import os, json, numpy as np
from common import D as ROOT
from mk import ts
from numba import njit
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
M1 = {}
for f in os.listdir(f"{ROOT}/data/1mz"):
    z = np.load(f"{ROOT}/data/1mz/{f}"); M1[f[:-4]] = (z["t"].astype(np.int64), z["o"], z["h"], z["l"], z["c"])
def bsym(gs):
    b = gs.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        if c in M1: return c, scl
    return None, None
@njit
def walk(t, o, h, l, c, k0, s, e, sl, hs, tp, pt, pf, part_from, tend, close_h, risk):
    """from the fill minute k0: -> (R, kind) kind 0 stop / 1 take / 3 time / 5 be-stop"""
    stop = hs; soft = sl; took = False; k = k0
    while k < len(c) and t[k] < tend:
        if (s > 0 and l[k] <= stop) or (s < 0 and h[k] >= stop):
            x = o[k] if (k > k0 and ((s > 0 and o[k] <= stop) or (s < 0 and o[k] >= stop))) else stop
            rest = s * (x - e) / risk; fee = (0.001 + 0.0003 * (t[k] - t[k0]) / 86400) * e / risk
            return ((pf * s * (pt - e) / risk + (1 - pf) * rest) if took else rest) - fee, (5 if took else 0)
        if pt != 0.0 and not took and t[k] >= part_from and ((s > 0 and h[k] >= pt) or (s < 0 and l[k] <= pt)):
            took = True; stop = e; soft = 0.0
        if k > k0 and ((s > 0 and h[k] >= tp) or (s < 0 and l[k] <= tp)):
            rest = s * (tp - e) / risk; fee = (0.0007 + 0.0003 * (t[k] - t[k0]) / 86400) * e / risk
            return ((pf * s * (pt - e) / risk + (1 - pf) * rest) if took else rest) - fee, 1
        if close_h > 0 and soft != 0.0 and (t[k] + 60) % (close_h * 3600) == 0 and ((s > 0 and c[k] <= soft) or (s < 0 and c[k] >= soft)):
            rest = s * (c[k] - e) / risk; fee = (0.001 + 0.0003 * (t[k] - t[k0]) / 86400) * e / risk
            return rest - fee, 0
        k += 1
    k = min(k, len(c)) - 1
    rest = s * (c[k] - e) / risk; fee = (0.001 + 0.0003 * (t[k] - t[k0]) / 86400) * e / risk
    return ((pf * s * (pt - e) / risk + (1 - pf) * rest) if took else rest) - fee, 3
for mod in ("emx", "smc", "prv"):
    rows = []; nofill = 0; n = 0
    for tr in B[mod]:
        if tr.get("r") is None: continue
        c_, scl = bsym(tr["s"])
        t0 = tr.get("f") or tr["t"]
        if not c_ or t0 < ts(2024, 10) + 86400: continue
        t, o, h, l, c = M1[c_]
        s = tr["d"]; e = tr["e"] * scl; sl = tr["sl"] * scl; tp = tr["tp"] * scl
        i0 = int(np.searchsorted(t, t0)); i1 = int(np.searchsorted(t, t0 + 3600))
        if i0 >= len(t) or t[i0] - t0 > 600: continue
        n += 1
        k0 = next((k for k in range(i0, i1) if ((l[k] <= e * 0.9995) if s > 0 else (h[k] >= e * 1.0005))), -1)
        if k0 < 0:
            nofill += 1; continue
        if mod == "emx":
            risk = abs(e - sl); pt = tr["pt"] * scl if tr.get("pt") else 0.0
            R, k = walk(t, o, h, l, c, k0, s, e, sl, sl, tp, pt, 0.33, tr["t"] + 3600, tr["t"] + 72 * 3600, 0, risk)
        elif mod == "smc":
            risk = abs(e - sl)
            R, k = walk(t, o, h, l, c, k0, s, e, sl, sl, tp, 0.0, 0.0, 0, tr["t"] + 72 * 3600, 0, risk)
        else:
            hs = tr["hs"] * scl; risk = abs(e - hs)
            R, k = walk(t, o, h, l, c, k0, s, e, sl, hs, tp, 0.0, 0.0, 0, (t0 // 3600) * 3600 + 48 * 3600, 1, risk)
        rows.append((tr["r"], R, k, int(t0)))
    a = np.array(rows)
    print(f"{mod}: сделок на минутках {n}, лимитка/касание не исполнилась бы {nofill} ({nofill / max(n, 1) * 100:.0f}%) | "
          f"список {a[:, 0].mean():+.3f}R WR {np.mean(a[:, 0] > 0)*100:.0f}% · минутки {a[:, 1].mean():+.3f}R WR {np.mean(a[:, 1] > 0)*100:.0f}% "
          f"(те же сделки; с неисполненными как 0R: {a[:, 1].sum() / max(n, 1):+.3f}R на выставленную) · |разница| > 0.1R у {np.mean(np.abs(a[:, 0] - a[:, 1]) > 0.1)*100:.0f}%", flush=True)
