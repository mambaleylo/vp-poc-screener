"""SMC levels (lv2 fam >= 33, both sides, exit E2): yearly walk-forward scores saved once; the selected trades (q, cap)
dumped for the portfolio checks; a per-family / per-side / per-TF breakdown."""
import sys, json, numpy as np, warnings; warnings.filterwarnings("ignore")
from lv_wf import *
import lv_engine as LE
Dd = load_dir("lv2", LE.FNAMES)
F = Dd["F"]; fam = F[:, 0].astype(int); e = 2
mask = fam >= 33
import os
if os.path.exists("smc_sc.npz"):
    z = np.load("smc_sc.npz", allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
else:
    SC, THR = scores(Dd, e, mask=mask)
    np.savez("smc_sc.npz", SC=SC, THR=np.array(THR, dtype=object))
out = {}
for q in (0.99, 0.995):
    for nm, sub in (("bot", Dd["BOT"]), ("chk", ~Dd["BOT"])):
        sel = select(Dd, e, SC, THR, q, 12, mask & sub)
        sel = sel[Dd["T"][sel] >= ts(2022)]
        R = Dd["R"][e][sel]
        out[f"{q}_{nm}"] = [dict(s=Dd["names"][Dd["SYM"][i]], t=int(Dd["T"][i]), x=int(Dd["T"][i] + Dd["K"][e][i] * 3600), d=int(Dd["SIDE"][i]),
                                 fam=LE.FAMS[fam[i]], r=float(Dd["R"][e][i])) for i in sel]
        print(f"q{q} {nm}: {len(sel)} trades {R.mean():+.2f}R")
        for f_ in sorted(set(fam[sel])):
            m = fam[sel] == f_
            print(f"   {LE.FAMS[f_]:10s} {m.sum():4d} {R[m].mean():+.2f}R  longs {np.sum(Dd['SIDE'][sel][m] > 0)}")
json.dump(out, open("smc_trades.json", "w"))
