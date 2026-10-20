"""finalists on a fine risk grid: take x cap, the bot's set (q 0.995, 1-in-10 dd 45%) and the check set (q 0.98, 50%)"""
import os, sys, numpy as np
from cas_hyp import trades, ts
from nx_h import pain
GB = tuple(np.round(np.arange(0.005, 0.061, 0.0025), 4)); GC = tuple(np.round(np.arange(0.001, 0.0201, 0.0005), 4))
def ev(nm, **kw):
    out = []
    for q, tg, g in ((0.995, 0.45, GB), (0.98, 0.50, GC)):
        tr = [x for x in trades(q, **kw) if x[0] >= ts(2022)]; r = np.array([x[2] for x in tr])
        b = pain(tr, tg, g, nb=400)
        out.append(f"{r.mean():+.3f} n{len(r)} " + (f"{b[0]*100:.2f}% x{b[1]:.1f}" if b else "—"))
    print(f"{nm:28s} бот: {out[0]:28s} | проверка: {out[1]}", flush=True)
for tk in (2.0, 2.5, 3.0):
    for cap in (6, 8, 10, 12):
        ev(f"тейк {tk}R, не больше {cap}", take_r=tk, cap=cap)
