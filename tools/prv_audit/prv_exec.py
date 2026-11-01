"""P/R's own trades (the bot's backtest list: its deployed model's choices, 2023-2026) walked again with other executions on
the same 1h candles: the check (the deployed rule re-walked = the list's R), the market entry, the take 6 ATR, both; the
money with each list in place of the list's P/R in the bundle (the strictest money, 144 windows x 2 seeds)"""
import os, sys, json, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "winrate"))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import prv_lab as PL
import money_arm2 as MA2, money_multi as M, money_expect as X_
from multiprocessing import Pool
V = {"сейчас (перепроход)": (0.3, 3, 3.0, 6.0, 4.5, 48, 0.0), "вход по рынку": (0.0, 1, 3.0, 6.0, 4.5, 48, 0.0),
     "тейк 6 ATR": (0.3, 3, 3.0, 6.0, 6.0, 48, 0.0), "рынок + тейк 6 ATR": (0.0, 1, 3.0, 6.0, 6.0, 48, 0.0),
     "тейк 5.25 ATR": (0.3, 3, 3.0, 6.0, 5.25, 48, 0.0)}
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"
_D = {}
def job(a):
    v, sd, A = a
    pr = _D["list"] if v == "список бота" else _D[v]
    return v, sd, A, MA2.run(_D["or"], sorted(_D["ot0"] + pr, key=lambda x: x["t0"]), A, A + 365 * 86400, F, sd)
if __name__ == "__main__":
    L = json.load(open(os.path.join(HERE, "..", "..", "vp_bt_trades.json")))["prv"]
    cache = {}; lists = {v: [] for v in V}; diff = []
    for t in L:
        sym = M.bn(t["s"])
        if not sym: continue
        scl = 1000.0 if sym.startswith("1000") and not t["s"].startswith("1000") else 1.0
        if sym not in cache: cache[sym] = PL.load1h(sym)
        T, O, H, Lw, C = cache[sym]
        i = int(np.searchsorted(T, t["t"] - 3600))
        if i >= len(T) or T[i] != t["t"] - 3600: continue
        s = int(t["d"]); a = abs(t["sl"] - t["e"]) * scl / 3.0
        for v, p in V.items():
            r, b = PL.walk(O, H, Lw, C, i, s, a, *p)
            if v.startswith("сейчас"): diff.append(abs(r - t["r"]) if r == r else 9.0)
            if r == r:
                e = O[i + 1] if p[0] == 0 else C[i]
                lists[v].append({"t0": int(t["t"]), "t1": int(t["t"] + b * 3600), "r": float(r) - 0.03, "st": 6 * a / e, "sth": 6 * a / e, "mod": "prv", "sym": sym,
                                 "side": s, "e": float(e), "stream": None, "y": int(1970 + (t["t"] / 86400 + 0.5) / 365.2425)})
    d = np.array(diff)
    print(f"проверка: {len(d)} сделок списка, перепроход совпал (±0.01R) у {np.mean(d < 0.01) * 100:.0f}%, (±0.05R) у {np.mean(d < 0.05) * 100:.0f}%", flush=True)
    print("вариант | 2023 | 2024 | 2025 | 2026 | всего", flush=True)
    for v, tr in lists.items():
        cells = [f"{np.mean([x['r'] + 0.03 for x in tr if x['y'] == Y]):+.2f}R ({sum(1 for x in tr if x['y'] == Y)})" for Y in (2023, 2024, 2025, 2026)]
        print(f"{v} | " + " | ".join(cells) + f" | {np.mean([x['r'] + 0.03 for x in tr]):+.3f}R, {len(tr)} сделок", flush=True)
    _D.update({"or": MA2.orders(), "ot0": [v for v in M.build("base") if v["mod"] in X_.KINDS["bundle_htf"] - {"dlm", "prv"}],
               "list": [v for v in M.build("base") if v["mod"] == "prv"], **lists})
    VARS = ["список бота"] + list(V)
    with Pool(4) as Pl:
        res = Pl.map(job, [(v, sd, A) for v in VARS for sd in (1, 2) for A in X_.STARTS], chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R["список бота"][A]]) for A in X_.STARTS])
    print("деньги | обычный год | плохой год | просадка медиана | в плохом окне | лучше списка бота", flush=True)
    for v in VARS:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X_.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X_.STARTS])
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)}", flush=True)
    print("prv exec done", flush=True)
