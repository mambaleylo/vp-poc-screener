"""win rate & losing streaks: shared stats for trade lists [(t_in, t_out, R, side, id)] — the average, WR, the longest
losing run by exit time, how many runs of 8+ losses, and the growth at an equal 1-in-10 drawdown; a 'pause' rule"""
import numpy as np
from nx_h import pain
from mk import ts
def streaks(tr):
    o = sorted(tr, key=lambda x: x[1]); run, runs = 0, []
    for x in o:
        if x[2] < 0: run += 1
        else:
            if run: runs.append(run)
            run = 0
    if run: runs.append(run)
    return max(runs or [0]), sum(1 for r in runs if r >= 8)
def pause(tr, L):
    """skip a new trade while the last L closed trades (by the time of this entry, virtual ones too) all lost"""
    o = sorted(tr, key=lambda x: x[0]); closed = sorted(tr, key=lambda x: x[1]); out = []; j = 0; hist = []
    for x in o:
        while j < len(closed) and closed[j][1] <= x[0]: hist.append(closed[j][2]); j += 1
        if len(hist) >= L and all(r < 0 for r in hist[-L:]): continue
        out.append(x)
    return out
def stats(nm, tr, f0, target=0.45, grid=None):
    tr = [x for x in tr if x[0] >= f0]
    r = np.array([x[2] for x in tr]); wk = (ts(2026, 10) - f0) / 604800
    mx, n8 = streaks(tr)
    grid = grid or tuple(np.round(np.arange(0.0025, 0.081, 0.0025), 4))
    b = pain(tr, target, grid, nb=300)
    print(f"{nm:46s} {len(r):5d} {len(r)/wk:4.1f}/нед {r.mean():+.3f}R WR {np.mean(r > 0)*100:3.0f}% | подряд макс {mx:2d}, серий 8+: {n8:2d} | "
          + (f"{b[0]*100:.2f}%: x{b[1]:.1f}" if b else "—"), flush=True)
