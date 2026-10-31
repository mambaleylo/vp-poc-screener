"""the bundle's money in 2026 (01-01 .. 10-01) hour by hour as on Binance's cross margin: ⚡ = the trades the bot's own code
made in the replay (rp_base_*.json: the 210 coins, the side cap 20, one a coin & side), P/R / SMC / EMA / HTF = their 2026
trades of the bot's backtest lists. Each hour: the exits (the R at the risk taken), then the entries in time order by the
bot's rules — one position a coin, ⚡ <= 20 open, the risk x the load (⚡: < 5 open x0.625, else x1.25) x the daily
WaveTrend (the bot's dlm_osc_mult), the open risk at the exchange stops <= 90% of the equity (scaled; under a tenth -> waits
= skipped), the margin = notional / leverage <= 90% of the free margin (scaled; none free -> skipped). The equity marked
to the hour's closes (the unrealized PnL counts in the equity and the free margin, as Binance does).
usage: money_exact.py LEV [LEV ...]"""
import sys, os, json, glob, bisect, math
import numpy as np
LEVS = [float(x) for x in sys.argv[1:]] or [5.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 75.0]
NCAPS = [0.0, 10.0, 15.0, 20.0]   # the open notional <= this x the equity (0 = no cap)
from common import V
A, B = 1767225600, 1790812800
RK = {"dlm": 4.5, "prv": 3.0, "smc": 2.5, "emx": 2.0, "htf": 2.0}
def bname(gs):
    b = gs.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        if os.path.exists(f"data/1h/{c}.csv"): return c, scl
    return None, None
H1 = {}
def h1(gs):
    if gs not in H1:
        c, scl = bname(gs)
        a = np.loadtxt(f"data/1h/{c}.csv", delimiter=",", ndmin=2, usecols=(0, 4))
        H1[gs] = (a[:, 0].astype(np.int64), a[:, 1] / scl)
    return H1[gs]
def px_at(gs, t):   # the close of the 1h candle ending at t
    T, C = h1(gs); i = bisect.bisect_right(T, t - 3600) - 1
    return float(C[i]) if i >= 0 else None
# the daily WaveTrend multiplier: the bot's own function on the daily bars
D1 = {}
def d1(gs):
    if gs not in D1:
        c, scl = bname(gs); a = np.loadtxt(f"data/1h/{c}.csv", delimiter=",", ndmin=2)
        T = a[:, 0].astype(np.int64); g = T // 86400; st = np.concatenate([[0], np.flatnonzero(g[1:] != g[:-1]) + 1]); en = np.concatenate([st[1:], [len(T)]])
        D1[gs] = [{"time": int(g[s] * 86400), "open": a[s, 1] / scl, "high": a[s:e, 2].max() / scl, "low": a[s:e, 3].min() / scl, "close": a[e - 1, 4] / scl, "volume": a[s:e, 5].sum()} for s, e in zip(st, en) if e - s == 24]
    return D1[gs]
V.bn_closed = lambda sym, tf, sec, n, now: [c for c in d1(sym) if c["time"] + 86400 <= now][-n:] if tf == "1d" else []
V.DLM_BINANCE = True; V.log_error = lambda m: None
V.dlm_model()
EV = []
for fn in sorted(glob.glob("rp_base_*.json") + glob.glob("rp_base8_*.json")):
    d_ = json.load(open(fn))
    for t in d_["trades"]:
        if t.get("status") != "CLOSED" or t.get("r") is None: continue
        t0 = int(t.get("t1h") or t["fbar"])
        if not (max(A, d_["from"]) <= t0 < min(B, d_["to"])): continue   # each chunk's own period (its 7-day warm-up is the previous chunk's)
        sth = abs(t["entry"] - (t.get("hsl") or t["sl"])) / t["entry"]; st = abs(t["entry"] - t["sl"]) / t["entry"]
        EV.append({"t0": t0 + 3600, "t1": int(t["t_out"]), "r": float(t["r"]), "st": st, "sth": sth, "mod": "dlm", "sym": t["symbol"], "side": t["side"], "e": t["entry"]})
L = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
for mod in ("prv", "smc", "emx", "htf"):
    for t in L[mod]:
        if not (A <= t["t"] < B) or not bname(t["s"])[0]: continue
        st = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); sth = max(st, abs(t["e"] - t.get("hs", t["sl"])) / t["e"])
        EV.append({"t0": int(t["t"]), "t1": int(t["x"]), "r": float(t["r"]) - 0.03, "st": st, "sth": sth, "mod": mod, "sym": t["s"], "side": t["d"], "e": t["e"]})
EV.sort(key=lambda v: v["t0"])
print("сделок 2026:", {m: sum(1 for v in EV if v["mod"] == m) for m in RK}, flush=True)
import zlib
BR = json.load(open("brackets.json"))
def bn_of(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in BR: return c
def lev_real(sym, notional, cap):   # the coin's bracket at this size (Binance's leverageBracket), within the account's cap
    b = BR.get(bn_of(sym) or "")
    if not b: return min(cap, 10.0)
    for nc, lv, mmr in b:
        if nc >= notional: return float(min(lv, cap))
    return float(min(b[-1][1], cap))
def capped(sym, frac): return frac > 0 and zlib.crc32(sym.encode()) % 1000 < frac * 1000   # a fixed share of the coins at 10x max
def run(lev, eq0=200.0, ncap=0.0, frac10=0.0, real=False):
    cash = eq0; opn = []; i = 0; cut = skip = 0; peak = eq0; mdd = 0.0; months = {}; nfree = 0; mm_max = 0.0; liq = 0; not_max = 0.0
    for h in range(A, B + 45 * 86400, 3600):
        # exits whose hour ended
        for o in [o for o in opn if o["t1"] <= h]:
            cash += o["rd"] * o["r"]; opn.remove(o)
        # the equity marked to this hour's closes
        upnl = 0.0
        for o in opn:
            p = px_at(o["sym"], h)
            if p: upnl += o["side"] * (p - o["e"]) / o["e"] * o["notional"]
        eq = cash + upnl
        mm = sum(o["notional"] for o in opn) * 0.01   # Binance's maintenance margin of the small brackets ~0.5–1.5%: 1%
        if eq > 0:
            mm_max = max(mm_max, mm / eq); not_max = max(not_max, sum(o["notional"] for o in opn) / eq)
        if opn and eq <= mm: liq += 1
        peak = max(peak, eq); mdd = max(mdd, 1 - eq / peak) if peak > 0 else mdd
        if (h - A) % (86400 * 30) == 0: months[(h - A) // (86400 * 30)] = eq
        while i < len(EV) and EV[i]["t0"] <= h:
            v = EV[i]; i += 1
            if v["t0"] < h - 3600 or h >= B: continue
            if any(o["sym"] == v["sym"] for o in opn): continue
            if v["mod"] == "dlm" and sum(1 for o in opn if o["mod"] == "dlm") >= 20: continue
            rk = RK[v["mod"]] / 100
            if v["mod"] == "dlm":
                nd = sum(1 for o in opn if o["mod"] == "dlm")
                rk *= (0.625 if nd < 5 else 1.25) * V.dlm_osc_mult(v["sym"], v["side"], v["t0"])
            rd = eq * rk; hn = rd * v["sth"] / v["st"]; room = 0.9 * eq - sum(o["heat"] for o in opn)
            if hn > room:
                if room < hn * 0.1: skip += 1; continue
                rd *= room / hn; cut += 1
            notional = rd / v["st"]
            if ncap > 0:   # the open notional capped (the account's maintenance margin ~1% of it)
                nroom = ncap * eq - sum(o["notional"] for o in opn)
                if nroom < notional * 0.1: skip += 1; continue
                if notional > nroom: k = nroom / notional; rd *= k; notional *= k; cut += 1
            lv_ = lev_real(v["sym"], notional, lev) if real else (min(lev, 10.0) if capped(v["sym"], frac10) else lev)
            mg = notional / lv_
            free = eq - sum(o["mg"] for o in opn)
            if mg > 0.9 * free:
                if free <= 1: skip += 1; nfree += 1; continue
                k = 0.9 * free / mg; rd *= k; notional *= k; mg *= k; cut += 1; nfree += 1
            opn.append({"t1": v["t1"], "r": v["r"], "rd": rd, "heat": rd * v["sth"] / v["st"], "mg": mg, "notional": notional, "sym": v["sym"], "mod": v["mod"], "side": v["side"], "e": v["e"]})
            if eq <= 1: break
    return cash, cut, skip, nfree, mdd, months, mm_max, liq, not_max
print("== реальные плечи монет (Binance), потолок аккаунта", flush=True)
for capx in (10.0, 20.0, 125.0):
    E, cut, skip, nfree, mdd, mo, mmx, liq, nmx = run(capx, real=True)
    print(f"потолок {capx:>4.0f}x: ${E:>10,.0f} | урезано {cut}, пропущено {skip} (из них маржа {nfree}) | просадка {mdd*100:.0f}% | открыто до x{nmx:.1f}, поддерж. маржа до {mmx*100:.0f}%, часов в ликвидации {liq} | по месяцам " + " ".join(f"{v:,.0f}" for k, v in sorted(mo.items())), flush=True)
print("== часть монет с потолком 10x (остальные 20x)", flush=True)
for fr in (0.25, 0.5):
    E, cut, skip, nfree, mdd, mo, mmx, liq, nmx = run(20.0, frac10=fr)
    print(f"{fr*100:.0f}% монет по 10x: ${E:>10,.0f} | урезано {cut}, пропущено {skip} (из них маржа {nfree}) | просадка {mdd*100:.0f}% | поддерж. маржа до {mmx*100:.0f}%, часов в ликвидации {liq}", flush=True)
for ncap in NCAPS:
  print(f"== потолок открытого: {'нет' if not ncap else f'x{ncap:.0f} счёта'}", flush=True)
  for lev in (LEVS if not ncap else [20.0, 50.0]):
    E, cut, skip, nfree, mdd, mo, mmx, liq, nmx = run(lev, ncap=ncap)
    print(f"плечо {lev:>4.0f}x: с $200 на 01.01.2026 -> ${E:>10,.0f} к 01.10 | урезано {cut}, пропущено {skip} (из них маржа {nfree}) | просадка (почасовая, с незакрытыми) {mdd*100:.0f}% | открыто до x{nmx:.1f} счёта, поддерж. маржа до {mmx*100:.0f}% счёта, часов в ликвидации {liq} | по месяцам "
          + " ".join(f"{v:,.0f}" for k, v in sorted(mo.items())), flush=True)
