"""a walk-forward variant (cas_sel_<TAG>.npz) vs the baseline: the rule now and take 2.5R / cap 8, fine risk grid"""
import os, sys
ARG = sys.argv[1]; os.environ["CAS_SEL"] = ARG
import numpy as np
from cas_hyp import trades, ts
from nx_h import pain
from wr_eval import streaks
GB = tuple(np.round(np.arange(0.005, 0.061, 0.0025), 4)); GC = tuple(np.round(np.arange(0.001, 0.0201, 0.0005), 4))
for nm, kw in (("тейк 2R, до 12", {}), ("тейк 2.5R, до 8", dict(take_r=2.5, cap=8))):
    out = []
    for q, tg, g in ((0.995, 0.45, GB), (0.98, 0.50, GC)):
        tr = [x for x in trades(q, **kw) if x[0] >= ts(2022)]; r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr])
        yrs = " ".join(f"{r[(t >= ts(y)) & (t < ts(y + 1))].mean():+.2f}" for y in range(2022, 2027))
        b = pain(tr, tg, g, nb=400)
        out.append(f"{r.mean():+.3f} n{len(r)} WR{np.mean(r > 0)*100:.0f}% подряд{streaks(tr)[0]} [{yrs}] " + (f"{b[0]*100:.2f}% x{b[1]:.1f}" if b else "—"))
    print(f"{ARG:22s} {nm:16s} бот: {out[0]}\n{'':39s} проверка: {out[1]}", flush=True)
