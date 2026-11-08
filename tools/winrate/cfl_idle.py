"""A module for Классика's quiet times (the user: "нужно разработать индикатор, который во времена простоев будет хорошо работать,
чтобы не делить маржу но и торговать"): the quiet = what the bot knows live — no Классика trade open and its last entry >= 14
days ago (v0.99.781's rule's own list). Every ev3 event (12 classic indicators x 4h / 1d, the 210 coins) in the quiet, both ways:
against the signal (Классика's way) and with it; the exits: the stop 0.5 dATR at the 4h close (the emergency 1.0), the take 3 / 6R,
96 h. By family x the signal's side x the way: n, R, WR in 2023–24 and 2025–26 (a group kept only if positive in both); and the
deployed model's score deciles in the quiet. -> <LABSTORE>/wf/cfl_idle.json. usage: run_cfl_idle.sh"""
import os, sys, json, numpy as np
sys.argv = ["x"]
exec(open("cfl_var.py").read().rsplit('if __name__ == "__main__":', 1)[0])
NEW = "dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50"
p = dict(BASE)
for part in NEW.split("+"): p = merge(p, VARS[part])
L = build(p); E0 = np.array(sorted(x["t0"] for x in L)); SPANS = sorted((x["t0"], x["t1"]) for x in L)
print(f"Классика (v0.99.781): {len(L)} сделок", flush=True)
def quiet(t):   # no open trade at t and the last entry >= 14 days before
    k = np.searchsorted(E0, t, side="right") - 1
    if k >= 0 and t - E0[k] < 14 * 86400: return False
    return not any(a <= t < b for a, b in SPANS[max(0, k - 40):k + 1])
c = np.where(np.isfinite(SC) & (T >= ts(2023)) & (T < ts(2026, 10)))[0]
c = c[np.array([T[i] - FIRST[SYM[i]] >= 90 * 86400 for i in c], bool)]
Q = np.array([quiet(int(T[i])) for i in c], bool); cq = c[Q]
print(f"событий 2023–26: {len(c)}, в тишину {len(cq)} ({Q.mean() * 100:.0f}%)", flush=True)
EXS = {"t3": {"sk": 0.5, "hard": 1.0, "ctf": 4, "take": 3.0, "hold": 96}, "t6": {"sk": 0.5, "hard": 1.0, "ctf": 4, "take": 6.0, "hold": 96}}
def walk_dir(i, ex, way):   # way -1: against the signal (Классика), +1: with it
    Tb, O, H, L_, C_, V = bars(SYM[i]); jE = int(J[i]) + 1
    if jE + 1 >= len(C_): return np.nan
    q = dict(DEF); q.update(ex)
    r, kk = walk2(Tb, O, H, L_, C_, jE, way * int(SIDE[i]), float(DA[i]), q["sk"], q["hard"], q["ctf"], q["take"], q["hold"], q["be_at"], q["be_to"],
                  q["tr_at"], q["tr_d"], q["p_at"], q["p_fr"], q["p_be"], q["lim"], q["wait"])
    return float(r)
R = {}
for en, ex in EXS.items():
    for way in (-1, 1):
        R[(en, way)] = np.array([walk_dir(i, ex, way) for i in cq]); print("готово", en, way, flush=True)
A = T[cq] < ts(2025); fam = FAM[cq]; sd = SIDE[cq]
out = {"n_quiet": int(len(cq)), "groups": []}
print("семейство | сигнал | как | выход | 2023–24: n, R, WR | 2025–26: n, R, WR", flush=True)
for f in sorted(set(fam)):
    for s in (1, -1):
        for way in (-1, 1):
            for en in EXS:
                r = R[(en, way)]; m = (fam == f) & (sd == s) & np.isfinite(r)
                if m.sum() < 60: continue
                a, b = m & A, m & ~A
                if a.sum() < 25 or b.sum() < 25: continue
                g = {"fam": E3.FAMS[int(f)], "sig": int(s), "way": way, "ex": en, "a": [int(a.sum()), round(float(r[a].mean()), 3), round(float((r[a] > 0).mean() * 100), 1)],
                     "b": [int(b.sum()), round(float(r[b].mean()), 3), round(float((r[b] > 0).mean() * 100), 1)]}
                out["groups"].append(g)
                if g["a"][1] > 0.1 and g["b"][1] > 0.1:
                    print(f"✔ {g['fam']} | {'покупка' if s > 0 else 'продажа'} | {'против' if way < 0 else 'по сигналу'} | {en} | {g['a']} | {g['b']}", flush=True)
# the deployed model's score in the quiet (against, t6): deciles by 2023–24's bars
r = R[("t6", -1)]; s_ = SC[cq]; qs = np.quantile(s_[A], np.linspace(0.1, 0.9, 9)); d = np.digitize(s_, qs)
print("оценка модели (против, тейк 6R) по децилям: 2023–24", [round(float(r[(d == k) & A].mean()), 2) for k in range(10)], "| 2025–26", [round(float(r[(d == k) & ~A].mean()), 2) for k in range(10)], flush=True)
r = R[("t6", 1)]
print("то же, по сигналу:                         2023–24", [round(float(r[(d == k) & A].mean()), 2) for k in range(10)], "| 2025–26", [round(float(r[(d == k) & ~A].mean()), 2) for k in range(10)], flush=True)
json.dump(out, open(f"{ST}/wf/cfl_idle.json", "w"))
np.savez(f"{ST}/wf/cfl_idle_R.npz", idx=cq, **{f"{k[0]}_{k[1]}": v for k, v in R.items()})
print("cfl idle done", flush=True)
