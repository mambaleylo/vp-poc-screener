import os, sys, numpy as np, time
os.environ["HYP"] = "15"
src = open("flowsig.py").read()
src = src[:src.index("SG = {12:")].replace("@njit(cache=True)", "@njit")
exec(compile(src, "flowsig_part", "exec"))
P = dict(k=5.0, h=1, f=0.5); ev = {}
for sym in COINS:
    if sym not in DATA: continue
    d = DATA[sym]
    with np.errstate(all="ignore"): lg, sh = signals(d, P)
    lg = onset(lg); sh = onset(sh); win = (d["T"] >= A0) & (d["T"] < END)
    for s, msk in ((1, lg & win), (-1, sh & win)):
        idx = np.where(msk)[0].astype(np.int64)
        if not len(idx): continue
        R = run(d["O"], d["H"], d["L"], d["C"], d["atr"], d["F"], idx, np.full(len(idx), s, dtype=np.int64), 3.0, 1.5, 24)
        for q in range(len(idx)):
            if R[q] == R[q]:
                t = int(d["T"][idx[q]]); ev.setdefault((t, s), []).append((sym, R[q]))
j = {int(t): q for q, t in enumerate(BTC["T"])}
print("час (UTC) | сторона | монет | средний R | ход BTC за час, % | BTC за следующие 24ч, %")
tot = []
for (t, s), v in sorted(ev.items()):
    q = j[t]; mv = (BTC["C"][q] / BTC["O"][q] - 1) * 100; nx = (BTC["C"][min(q + 24, len(BTC["C"]) - 1)] / BTC["C"][q] - 1) * 100
    r = np.mean([x[1] for x in v]); tot.append(r)
    print(time.strftime("%Y-%m-%d %H:%M", time.gmtime(t)), "|", "лонг" if s > 0 else "шорт", "|", len(v), "|", f"{r:+.2f}", "|", f"{mv:+.2f}", "|", f"{nx:+.2f}")
print("событий:", len(tot), "среднее по событиям:", round(float(np.mean(tot)), 3), "медиана:", round(float(np.median(tot)), 3), "в плюсе:", sum(x > 0 for x in tot))
