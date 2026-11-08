import os, numpy as np, time
def clus(name, rows, per="w"):
    """rows: (t, R, side) -> R by week/month: the number of clusters, their mean, t over clusters, the share of plus clusters; per period"""
    key = (lambda t: t // (7 * 86400)) if per == "w" else (lambda t: time.gmtime(t).tm_year * 12 + time.gmtime(t).tm_mon)
    MID = 1735689600
    for lab, f in (("2023–24", lambda t: t < MID), ("2025–26", lambda t: t >= MID)):
        g = {}
        for t, r, s in rows:
            if f(t): g.setdefault(key(t), []).append(r)
        m = np.array([np.mean(v) for v in g.values()])
        if len(m) < 3: print(name, lab, "мало"); continue
        print(f"{name} {lab}: сделок {sum(len(v) for v in g.values())}, {'недель' if per == 'w' else 'месяцев'} {len(m)}, средний R по ним {m.mean():+.3f}, t {m.mean() / (m.std() / np.sqrt(len(m))):.2f}, в плюсе {np.mean(m > 0) * 100:.0f}%, "
              f"худш. {m.min():+.2f}, лучш. {m.max():+.2f}", flush=True)
# H13
os.environ["HYP"] = "13"
src = open("flowsig.py").read(); src = src[:src.index("SG = {12:")].replace("@njit(cache=True)", "@njit")
exec(compile(src, "fs", "exec"))
for P in (dict(F=0.001, Z=1.5, stall=1), dict(F=0.001, Z=0.0, stall=1), dict(F=0.0006, Z=1.5, stall=1)):
    for m, Tk, Hh in ((3.0, 1.5, 72), (3.0, 3.0, 72), (6.0, 1.5, 72)):
        rows = []; side = {1: [], -1: []}
        for sym in COINS:
            if sym not in DATA: continue
            d = DATA[sym]
            with np.errstate(all="ignore"): lg, sh = signals(d, P)
            lg = onset(lg); sh = onset(sh); win = (d["T"] >= A0) & (d["T"] < END)
            idx = np.concatenate([np.where(lg & win)[0], np.where(sh & win)[0]]); sd = np.concatenate([np.ones((lg & win).sum()), -np.ones((sh & win).sum())])
            o = np.argsort(idx, kind="stable"); idx = idx[o].astype(np.int64); sd = sd[o].astype(np.int64)
            R = run(d["O"], d["H"], d["L"], d["C"], d["atr"], d["F"], idx, sd, m, Tk, Hh)
            for q in np.where(R == R)[0]:
                rows.append((int(d["T"][idx[q]]), float(R[q]), int(sd[q]))); side[int(sd[q])].append(float(R[q]))
        print(f"\nH13 {P} m{m} T{Tk} H{Hh}: лонги {len(side[1])} R {np.mean(side[1]):+.3f}, шорты {len(side[-1])} R {np.mean(side[-1]) if side[-1] else 0:+.3f}", flush=True)
        clus("  по неделям", rows, "w")
        clus("  только лонги", [r for r in rows if r[2] > 0], "w")
print("clus done", flush=True)
