import numpy as np
import zm_h as Z
inst = np.load("zm_inst.npz")["inst_1h"]
for lab in ("G_1.0_R4.0", "G_1.0_R3.0", "G_1.0_R2.0", "G_1.0_R1.5", "G_0.75_R2.0", "G_0.75_R1.5", "G_1.5_R2.0", "G_2.0_R1.5"):
    for q in (0.95, 0.85):
        tr = Z.replay(Z.cand(q), lab); hrs = np.array([(x[1] - x[0]) / 3600 for x in tr])
        Z.line(f"{lab} q{q} ~{np.median(hrs):.0f}ч (медиана), {np.mean(hrs < 72)*100:.0f}% за 3 дня", tr, q)
