"""The deployed modules' backtest lists (vp_bt_trades.json, bot coins) with and without the SMC trades (walk-forward,
bot coins): growth per year at an equal 1-in-10 drawdown of 45%, one risk per trade for the whole list."""
import json, numpy as np, sys
import nx_h; from nx_h import pain
from mk import ts
from lv_wf import GRID
q = sys.argv[1] if len(sys.argv) > 1 else "0.99"
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
S = json.load(open("smc_trades.json"))[f"{q}_bot"]
def tl(lst): return [(x["t"], x["x"], x["r"], x.get("d"), x["s"]) for x in lst if x["t"] >= ts(2022)]
def run(nm, tr, seeds=(7, 8, 9)):
    tr = sorted(tr); mo = (ts(2026, 10) - ts(2022)) / (30.4 * 86400); r = np.array([x[2] for x in tr]); xs = []
    for sd in seeds:
        nx_h.rng = np.random.default_rng(sd); b = pain(tr, 0.45, GRID, nb=200); xs.append((b[0], b[1] ** (12 / mo)) if b else (0, 0))
    print(f"{nm:28s} {len(tr):5d} {len(tr)/(mo*30.4/7):4.1f}/нед {r.mean():+.2f}R | риск ~{np.mean([a for a,_ in xs])*100:.2f}% x/год " + " ".join(f"{b:.2f}" for _, b in xs), flush=True)
smc = tl(S)
run("SMC", smc)
run("EMA (бот)", tl(B["emx"])); run("EMA + SMC", tl(B["emx"]) + smc)
run("P/R (бот)", tl(B["prv"])); run("P/R + SMC", tl(B["prv"]) + smc)
run("EMA + P/R", tl(B["emx"]) + tl(B["prv"])); run("EMA + P/R + SMC", tl(B["emx"]) + tl(B["prv"]) + smc)
