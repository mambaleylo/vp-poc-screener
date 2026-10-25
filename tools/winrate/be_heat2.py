"""break-even for P/R / SMC / EMA to free the open-risk room: each backtest trade walked on its 1h candles from the entry —
the first hour whose high (long) reaches the entry + X x its stop distance -> from the next hour the stop at the entry
(the open risk of it 0 from then); the price back at the entry before its exit -> out at ~0 (-0.03R fees) there, else
its own result. -> be_heat.json {X: {module: {(t, r): (t_be, r_new, x_new)}}}"""
import json, os, numpy as np
B = json.load(open("/tmp/claude-0/-home-user-vp-poc-screener/591d3753-67a7-5ebe-97a8-1553972a4a6c/scratchpad/bt_old.json"))   # the list before v0.99.719
H = {}
NORM = lambda x: x.replace("_USDT", "").replace("USDT", "").replace("1000", "")
def h1(sym):
    if sym not in H:
        b = sym.replace("_USDT", "")
        for c in (b + "USDT", "1000" + b + "USDT", b.replace("1000", "") + "USDT"):
            f = f"data/1h/{c}.csv"
            if os.path.exists(f):
                a = np.loadtxt(f, delimiter=",", ndmin=2); scl = 1000.0 if c.startswith("1000") and not b.startswith("1000") else 1.0
                H[sym] = (a[:, 0].astype(np.int64), a[:, 2] / scl, a[:, 3] / scl); break
        else:
            H[sym] = None
    return H[sym]
out = {}
for X in (2.0,):
    out[X] = {}
    for mod in ("prv", "smc", "emx"):
        res = {}; n = nb = nz = 0
        for t in B[mod]:
            if t.get("r") is None or not t.get("x") or not t.get("e") or not t.get("sl"): continue
            d = h1(t["s"])
            if d is None: continue
            T, Hh, Ll = d; s = t["d"]; e = t["e"]; risk = abs(e - t["sl"]); start = int(t.get("f") or t["t"]); x = int(t["x"])
            if mod == "emx" and t.get("part"): continue   # EMA's partial already moves its stop to the entry
            i0, i1 = int(np.searchsorted(T, start)), int(np.searchsorted(T, x))
            tb = None
            for i in range(i0 + 1, i1):   # v2: from the hour after the touch (the bot's _cs_walk: k > 0)
                if (Hh[i] >= e + X * risk) if s > 0 else (Ll[i] <= e - X * risk):
                    tb = int(T[i]) + 3600; break
            n += 1
            if tb is None or tb >= x: continue
            nb += 1; j0 = int(np.searchsorted(T, tb)); hit = None
            for i in range(j0, i1):
                if (Ll[i] <= e) if s > 0 else (Hh[i] >= e):
                    hit = int(T[i]) + 3600; break
            if hit is not None and hit < x:
                ex_ = e   # out at the entry (a gap through it: the bar's open — rare, ignored)
                rr = -(0.001 + 0.0003 * ((hit - start) / 3600) / 24) * e / risk   # the bot's SMC_FEE / SMC_FUND
                nz += 1; res[f"{NORM(t['s'])}_{int(t.get('f') or t['t'])}_{round(t['r'], 2)}"] = (tb, round(rr, 3), hit)
            else:
                res[f"{NORM(t['s'])}_{int(t.get('f') or t['t'])}_{round(t['r'], 2)}"] = (tb, t["r"], x)
        R0 = np.array([t["r"] for t in B[mod] if t.get("r") is not None])
        print(f"+{X}R {mod}: {n} trades, reached {nb}, back to the entry {nz}; R {R0.mean():+.3f} -> " +
              f"{(R0.sum() + sum(v[1] - t_r for k, v in res.items() for t_r in [float(k.split('_')[-1])])) / len(R0):+.3f}", flush=True)
        out[X][mod] = res
json.dump({str(k): v for k, v in out.items()}, open("be_heat2.json", "w"))
