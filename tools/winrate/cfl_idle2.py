"""Классика's quiet: a model of its own (cfl_idle.py's events in the quiet; the label = the trade's R one way, the stop 0.5 dATR at the
4h close, the take 3 / 6R, 96 h): lv_wf.scores — a yearly LightGBM on the bot coins' quiet events closed 14 days before the year
(2024 learns 2023's quiet only), the bar = q of the previous year's out-of-sample scores; the trades: in the quiet only, one per
coin & side, <= 20 a side (busy 96 h) -> per year 2024 / 2025 / 2026 (never seen): n, R, WR, and Классика's empty months it fills.
usage: run_cfl_idle.sh 2"""
import os, sys, json, numpy as np
sys.argv = ["x"]
exec(open("cfl_var.py").read().rsplit('if __name__ == "__main__":', 1)[0])
from lv_wf import scores
NEW = "dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50"
p = dict(BASE)
for part in NEW.split("+"): p = merge(p, VARS[part])
L = build(p); mon = lambda t: int(np.datetime64(int(t), "s").astype("datetime64[M]").astype(int))
cfl_months = {mon(x["t0"]) for x in L}
ALLM = list(range(mon(ts(2024)), mon(ts(2026, 10))))
TAG = os.environ.get("CFL_IDLE_TAG", ""); Z = np.load(f"{ST}/wf/cfl_idle_R{TAG}.npz"); cq = Z["idx"]
LAB = {"по тренду, тейк 6R": Z["t6_1"], "по тренду, тейк 3R": Z["t3_1"], "против, тейк 6R": Z["t6_-1"]}
Dq = dict(T=T[cq], SYM=SYM[cq], BOT=BOT[cq], SIDE=SIDE[cq], F=Dd["F"][cq].astype(np.float32))
Dq["F"][:, [E3.FNAMES.index(c) for c in ("ls_z", "tk_z", "top_z")]] = 0.0
print(f"событий в тишину: {len(cq)}; пустых месяцев Классики 2024–26: {sum(1 for m in ALLM if m not in cfl_months)} из {len(ALLM)}", flush=True)
out = {}
for ln, r in LAB.items():
    Dq["R"] = r[None, :]
    SCq, THR = scores(Dq, 0, years=(2023, 2024, 2025, 2026), mask=np.isfinite(r), seeds=2)   # 2023 learns 2022-07..12 (with CFL_FROM): 2024's bar of 2023's out-of-sample scores
    for q in (0.98, 0.99, 0.995):
        sel = []
        for Y in (2023, 2024, 2025, 2026):
            if Y not in THR: continue
            th = float(np.quantile(THR[Y], q)); yy = (Dq["T"] >= ts(Y)) & (Dq["T"] < ts(Y + 1)) & np.isfinite(SCq) & (SCq >= th) & np.isfinite(r)
            sel += list(np.where(yy)[0])
        sel = np.array(sorted(sel, key=lambda i: (Dq["T"][i], -SCq[i])), dtype=np.int64)
        busy, act, take = {}, [], []
        for i in sel:
            t = int(Dq["T"][i]); key = (Dq["SYM"][i], Dq["SIDE"][i])
            if busy.get(key, 0) > t: continue
            act = [a for a in act if a[0] > t]
            if sum(1 for a in act if a[1] == Dq["SIDE"][i]) >= 20: continue
            busy[key] = t + 96 * 3600; act.append((t + 96 * 3600, Dq["SIDE"][i])); take.append(i)
        take = np.array(take, dtype=np.int64); rr = r[take]; tt = Dq["T"][take]
        by = {Y: (int(((tt >= ts(Y)) & (tt < ts(Y + 1))).sum()), float(rr[(tt >= ts(Y)) & (tt < ts(Y + 1))].mean()) if ((tt >= ts(Y)) & (tt < ts(Y + 1))).any() else np.nan) for Y in (2023, 2024, 2025, 2026)}
        mm = {mon(t) for t in tt}; fill = sum(1 for m in ALLM if m not in cfl_months and m in mm); both = sum(1 for m in ALLM if m not in cfl_months and m not in mm)
        o = {"n": len(take), "r": round(float(rr.mean()), 3) if len(rr) else None, "wr": round(float((rr > 0).mean() * 100), 1) if len(rr) else None,
             "years": {str(k): [v[0], round(v[1], 3)] for k, v in by.items()}, "filled": fill, "still_empty": both,
             "bot": [int(Dq["BOT"][take].sum()), round(float(rr[Dq["BOT"][take]].mean()), 3) if Dq["BOT"][take].any() else None],
             "chk": [int((~Dq["BOT"][take]).sum()), round(float(rr[~Dq["BOT"][take]].mean()), 3) if (~Dq["BOT"][take]).any() else None]}
        out[f"{ln} q{q}"] = o
        print(f"{ln}, q {q}: {o['n']} сделок, {o['r']:+.2f}R, WR {o['wr']}% | " + " ".join(f"{k}: {v[0]} {v[1]:+.2f}" for k, v in o["years"].items())
              + f" | монеты бота {o['bot']}, невиденные {o['chk']} | закрыла пустых месяцев Классики {fill}, осталось {both}", flush=True)
json.dump(out, open(f"{ST}/wf/cfl_idle2{TAG}.json", "w"), indent=1)
print("cfl idle2 done", flush=True)
