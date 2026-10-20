"""strong zones: the trades whose first limit was crossed at once (the price already in / past the zone at the scan's
next open, or within the first hour) vs the rest — on the deployed label G_1.0_R4.0, bot set q 0.95 / check q 0.85"""
import numpy as np
import zm_h as Z
from common import load
OFF = 0.2
d = Z.d
idx_all = np.where(~np.isnan(Z.SC) & (Z.SC >= Z.T85) & (Z.T >= Z.ts(2022)))[0]
inst_open = np.zeros(len(d), bool); inst_1h = np.zeros(len(d), bool)
cache = {}
for k in idx_all:
    sym = Z.SYM[k]
    if sym not in cache:
        cs = load(sym); cache[sym] = ({c["time"]: n for n, c in enumerate(cs)}, cs)
    pos, cs = cache[sym]
    i = pos.get(int(Z.T[k]))
    if i is None: continue
    s = Z.SIDE[k]; lo, hi = float(d.lo.values[k]), float(d.hi.values[k])
    near = hi if s > 0 else lo
    l1 = near * (1 + s * OFF / 100)
    c = cs[i]
    inst_open[k] = (c["open"] <= l1) if s > 0 else (c["open"] >= l1)
    inst_1h[k] = (c["low"] <= l1) if s > 0 else (c["high"] >= l1)
np.savez("zm_inst.npz", inst_open=inst_open, inst_1h=inst_1h)
for q in (0.95, 0.85):
    c = Z.cand(q); print(f"\n== q{q}: кандидатов {len(c)}, цена уже в/за зоной на открытии {inst_open[c].mean()*100:.1f}%, лимитка взята в первый час {inst_1h[c].mean()*100:.1f}%")
    lab = "G_1.0_R4.0"
    Z.line("все (как бот)", Z.replay(c, lab), q)
    Z.line("без «уже в/за зоной»", Z.replay(Z.cand(q, ~inst_open), lab), q)
    Z.line("только «уже в/за зоной»", Z.replay(Z.cand(q, inst_open), lab), q)
    Z.line("без «взята в первый час»", Z.replay(Z.cand(q, ~inst_1h), lab), q)
    Z.line("только «взята в первый час»", Z.replay(Z.cand(q, inst_1h), lab), q)
