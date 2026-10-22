"""deep2 E0 q0.98: growth at an equal 1-in-10 drawdown (month-block bootstrap), per set; alone and with the deployed EMA + P/R"""
import json, numpy as np, warnings; warnings.filterwarnings("ignore")
import s15_engine as E
from s15_wf import load, select
import nx_h; from nx_h import pain
from mk import ts
D = load("s15", [E.FAMS.index("deep2")])
z = np.load("s15_sc_deep2_0.npz", allow_pickle=True); SC, THR = z["SC"], z["THR"].item()
grid = tuple(np.round(np.arange(0.0025, 0.0501, 0.0025), 4))
mo = (ts(2026, 10) - ts(2022)) / (30.4 * 86400)
def tl(sel): return [(int(D["t"][i]), int(D["t"][i] + D["K"][0][i] * 3600), float(D["R"][0][i]), 0, int(i)) for i in sel if D["t"][i] >= ts(2022)]
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
base = [(x["t"], x["x"], x["r"], 0, 0) for k in ("emx", "prv") for x in B[k] if x["t"] >= ts(2022)]
for nm, sub, tgt in (("обуч", ~D["chk"], 0.45), ("пров", D["chk"], 0.50)):
    tr = tl(select(D, 0, SC, THR, 0.98, 12, sub))
    nx_h.rng = np.random.default_rng(7); b = pain(sorted(tr), tgt, grid, nb=60)
    print(f"{nm}: {len(tr)} trades, {len(tr)/mo:.0f}/мес · риск {b[0]*100:.2f}% → x{b[1]**(12/mo):.2f}/год" if b else nm, flush=True)
