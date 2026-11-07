"""What a trade's risk becomes at a balance (the user: "если на балансе 300000 то какой процент на вход будет?"): every
backtest trade of the bundle as the bot sizes it (the module's risk % at its stop) through the header's liquidity cut
(liq=4:0.5/8:0.25/12:0 of the coin's median hourly turnover) and the square-root impact (slip=1) -> per module and balance:
the median risk % left, the share of trades cut, the slippage in R per trade (all its market fills) and in % of the balance.
The open-risk room and the margin are left out (they cut further when many trades are open). usage: ALLSUF=_clr liq_at_balance.py"""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
RISK = {"dlm": 4.0, "prv": 3.75, "smc": 3.125, "emx": 3.75, "htf": 2.5, "cfl": 2.0}
NAME = {"dlm": "⚡ Лимитки", "prv": "P/R", "smc": "SMC", "emx": "EMA", "htf": "HTF", "cfl": "Классика"}
LS = MA2.liq_steps("4:0.5/8:0.25/12:0"); BAL = (10000, 50000, 100000, 300000, 1000000)
base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
T = [dict(o, mod="dlm", t0=o["t"] + 3600) for o in base + o2 if o.get("filled", True)] + [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf_cfl"] - {"dlm"}]
print("сделок", len(T), flush=True)
print("модуль | баланс | риск на вход: медиана (номинал) | 25% сделок ниже | урезано сделок | проскальзывание за сделку, R | то же, % баланса", flush=True)
for mod in ("dlm", "prv", "smc", "emx", "htf", "cfl"):
    L = [v for v in T if v["mod"] == mod]
    for E in BAL:
        eff, cut, slR, slB = [], 0, [], []
        for v in L:
            r = RISK[mod] * v.get("xm", 1.0); st = float(v["st"])
            V_, s_ = MA2.liq_at(v["sym"], int(v.get("t0") or v["t"] + 3600))
            if not V_: continue
            notional = E * r / 100 / st; p_ = notional / V_; q_ = MA2.liq_g(p_, LS); k = q_ / p_ if p_ > 0 else 1.0
            r2 = r * k; n2 = notional * k; cut += k < 0.999
            imp = (s_ * (n2 / (24 * V_)) ** 0.5) if s_ else 0.0
            nm = v["mkt"] if "mkt" in v else 2
            eff.append(r2); slR.append(nm * imp / st); slB.append(nm * imp / st * r2)
        eff = np.array(eff)
        print(f"{NAME[mod]} | ${E:,} | {np.median(eff):.2f}% ({RISK[mod]:g}%) | {np.percentile(eff, 25):.2f}% | {cut / len(eff) * 100:.0f}% | {np.median(slR):.3f} | {np.median(slB):.3f}%", flush=True)
print("liq at balance done", flush=True)
