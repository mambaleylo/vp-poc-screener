"""🧠 Neuro round 4: the model retrained on the v0.99.663 rule's label (nx_sel_lim.py) vs the deployed one, the same rule"""
import numpy as np
import nx_h as N
from nx_x2 import build
S0 = N.S; S1 = dict(np.load(f"{N.D}/nx_sel_lim.npz"))
for q in (0.995, 0.98):
    print(f"\n=== Нейро q{q}", flush=True)
    N.S = S0; N.line("внедрённая модель (v663)", sorted(build(q)), q)
    N.S = S1; N.line("переобученная на метке лимитки", sorted(build(q)), q)
    N.line("переобученная, без фильтра ADX", sorted(build(q, adx=999)), q)
for q in (0.99, 0.997):
    N.S = S1
    thr = {}
    print(f"--- переобученная, порог q{q} (пересчёт по прошлому году)", flush=True)
