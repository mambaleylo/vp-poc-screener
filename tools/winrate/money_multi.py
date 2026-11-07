"""the bundle's money over several years, hour by hour on Binance's cross margin (money_exact.py's rules): ⚡ = the walk-forward
v2 pool (dlm_pool.py: the trades the bot's rules make of the yearly models' choices), P/R / SMC / EMA / HTF = their trades of
the bot's backtest lists. 12-month windows from $200 started every quarter 2023-01 .. 2025-10; per variant the median, the
worst and the best window, the median drawdown, the liquidation hours. The leverage by Binance's real brackets of each coin
(the lab upload of 31.10.2026) within the account's cap.
usage: money_multi.py  (variants in VARIANTS; 4 processes)"""
import os, sys, json, bisect, calendar, zlib, numpy as np
from multiprocessing import Pool
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
DATA = os.path.join(ST, "data", "1h")
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
RK = {"dlm": 4.5, "prv": 3.0, "smc": 2.5, "emx": 2.0, "htf": 2.0, "cfl": 1.0}
BR = json.load(open(os.path.join(ST, "brackets.json")))
AV = {f[:-7] for f in os.listdir(DATA)}
def bn(c):   # a coin's Binance name from the bot's "X_USDT" or the Binance one
    if c in AV: return c
    b = c.replace("_USDT", "")
    for x in (b + "USDT", "1000" + b + "USDT"):
        if x in AV: return x
def lev_real(sym, notional, cap):
    b = BR.get(sym)
    if not b: return min(cap, 10.0)
    for nc, lv, mmr in b:
        if nc >= notional: return float(min(lv, cap))
    return float(min(b[-1][1], cap))
H1 = {}
def h1(sym):
    if sym not in H1:
        a = np.loadtxt(os.path.join(DATA, f"{sym}.csv.gz"), delimiter=",", ndmin=2, usecols=(0, 4))
        H1[sym] = (a[:, 0].astype(np.int64), a[:, 1])
    return H1[sym]
def px_at(sym, t):
    T, C = h1(sym); i = bisect.bisect_right(T, t - 3600) - 1
    return float(C[i]) if i >= 0 else None
def build(pool_name):
    EV = []
    for x in json.load(open(os.path.join(ST, "wf", f"pool_{pool_name}.json"))):
        st = abs(x["fill"] - x["sl"]) / x["fill"]; sth = abs(x["fill"] - x["hsl"]) / x["fill"]
        EV.append({"t0": x["t1h"] + 3600, "t1": x["tout"], "r": x["R"], "st": st, "sth": sth, "mod": "dlm", "sym": bn(x["coin"]), "side": x["side"],
                   "e": x["fill"], "stream": x["st"]})
    L = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
    for mod in ("prv", "smc", "emx", "htf", "cfl"):   # v0.99.776: + 🔄 Классика
        for t in L[mod]:
            sym = bn(t["s"])
            if not sym: continue
            scl = 1000.0 if sym.startswith("1000") and not t["s"].startswith("1000") else 1.0   # the lists keep Gate's prices
            st = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); sth = max(st, abs(t["e"] - t.get("hs", t["sl"])) / t["e"])
            EV.append({"t0": int(t["t"]), "t1": int(t["x"]), "r": float(t["r"]) - 0.03, "st": st, "sth": sth, "mod": mod, "sym": sym, "side": t["d"],
                       "e": t["e"] * scl, "stream": None, "mkt": 1 if t.get("k") == "take" else 2})   # v0.99.778: the market fills — the entry + the exit unless a take (a limit); was 1 + (r < 0): a time exit in profit missed its exit's impact
    EV.sort(key=lambda v: v["t0"])
    return EV
def run(EV, A, B, cap=20.0, wf=None, eq0=200.0, heat=0.9, side_cap=20, rk_=None, load=(5, 0.625, 1.25)):
    """one window [A, B): the equity at B (open trades marked), cut / skipped, the hourly drawdown, the liquidation hours"""
    cash = eq0; opn = []; i = bisect.bisect_left([v["t0"] for v in EV], A); cut = skip = 0; peak = eq0; mdd = 0.0; liq = 0; mmx = 0.0
    for h in range(A, B, 3600):
        for o in [o for o in opn if o["t1"] <= h]:
            cash += o["rd"] * o["r"]; opn.remove(o)
        upnl = 0.0
        for o in opn:
            p = px_at(o["sym"], h)
            if p: upnl += o["side"] * (p - o["e"]) / o["e"] * o["notional"]
        eq = cash + upnl
        if eq <= 0: return 0.0, cut, skip, 1.0, liq + 1, mmx
        peak = max(peak, eq); mdd = max(mdd, 1 - eq / peak)
        mm = sum(o["notional"] for o in opn) * 0.01; mmx = max(mmx, mm / eq)
        if opn and eq <= mm: liq += 1
        while i < len(EV) and EV[i]["t0"] <= h:
            v = EV[i]; i += 1
            if v["t0"] < h - 3600: continue
            if any(o["sym"] == v["sym"] for o in opn): continue
            if v["mod"] == "dlm" and sum(1 for o in opn if o["mod"] == "dlm") >= side_cap: continue   # the bot: DLM_MAX_POS 20 at once (and 20 a side)
            rk = (rk_ or RK)[v["mod"]] / 100
            if v["mod"] == "dlm":
                rk *= load[1] if sum(1 for o in opn if o["mod"] == "dlm") < load[0] else load[2]
            if wf: rk *= wf(v)
            rd = eq * rk; hn = rd * v["sth"] / v["st"]; room = heat * eq - sum(o["heat"] for o in opn)
            if hn > room:
                if room < hn * 0.1: skip += 1; continue
                rd *= room / hn; cut += 1
            notional = rd / v["st"]; mg = notional / lev_real(v["sym"], notional, cap)
            free = eq - sum(o["mg"] for o in opn)
            if mg > 0.9 * free:
                if free <= 1: skip += 1; continue
                k = 0.9 * free / mg; rd *= k; notional *= k; mg *= k; cut += 1
            opn.append({"t1": v["t1"], "r": v["r"], "rd": rd, "heat": rd * v["sth"] / v["st"], "mg": mg, "notional": notional, "sym": v["sym"],
                        "mod": v["mod"], "side": v["side"], "e": v["e"]})
    upnl = 0.0
    for o in opn:
        p = px_at(o["sym"], B)
        if p: upnl += o["side"] * (p - o["e"]) / o["e"] * o["notional"]
    return cash + upnl, cut, skip, mdd, liq, mmx
STARTS = [ts(y, m) for y in (2023, 2024, 2025) for m in (1, 4, 7, 10)]
W2S = lambda v: 0.5 if v.get("stream") == "close2h" and v["side"] < 0 else 1.0
W27 = lambda v: (0.7 if v.get("stream") == "close2h" else 1.0) * (0.7 if v["mod"] == "dlm" and v["side"] < 0 else 1.0)
VARIANTS = [("10x, монеты бота", "base", 10.0, None), ("20x, монеты бота", "base", 20.0, None), ("без лимита, монеты бота", "base", 125.0, None),
            ("20x, бот + новые", "base+new", 20.0, None), ("20x, 2ч-шорты x0.5", "base", 20.0, "W2S"), ("20x, 2ч и шорты x0.7", "base", 20.0, "W27")]
_EV = {}
def job(args):
    nm, pool, cap, wfn, A = args
    if pool not in _EV: _EV[pool] = build(pool)
    return nm, A, run(_EV[pool], A, A + 365 * 86400, cap, {"W2S": W2S, "W27": W27}.get(wfn))
if __name__ == "__main__":
    jobs = [(nm, pool, cap, wfn, A) for nm, pool, cap, wfn in VARIANTS for A in STARTS]
    with Pool(4) as P:
        res = P.map(job, jobs, chunksize=1)
    R = {}
    for nm, A, r in res: R.setdefault(nm, {})[A] = r
    json.dump({nm: {str(A): r for A, r in v.items()} for nm, v in R.items()}, open(os.path.join(ST, "wf", "money_multi.json"), "w"))
    base = R["20x, монеты бота"]
    for nm, v in R.items():
        E = np.array([v[A][0] for A in STARTS]); dd = np.array([v[A][3] for A in STARTS]); lq = sum(v[A][4] for A in STARTS)
        q = E / np.array([base[A][0] for A in STARTS])
        print(f"{nm:26s} год с $200: медиана ${np.median(E):>9,.0f} худший ${E.min():>8,.0f} лучший ${E.max():>10,.0f} | просадка медиана {np.median(dd)*100:.0f}% худшая {dd.max()*100:.0f}% "
              f"| ликв. часов {lq} | к 20x: лучше в {int((q > 1.001).sum())} из {len(q)}, медиана x{np.median(q):.2f}", flush=True)
        print("    по стартам:", " ".join(f"{np.datetime64(A, 's').astype('datetime64[M]')}:{v[A][0]:,.0f}" for A in STARTS), flush=True)
