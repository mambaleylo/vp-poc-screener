"""Классика's quiet — a rule without a model (cfl_idle.py's groups positive in 2022-07..2024 and 2025–26): in the quiet only (no
Классика trade open, its last entry >= 14 days ago), the stop 0.5 dATR at the 4h close (the emergency 1.0), the take 6R, 96 h,
one per coin & side, <= CAP a side. Rules: K = Keltner breakout up 1d (a long with it); KS = K + Supertrend flip up 1d (a long with
it); KSN = KS + NR7 up 1d (a short against it) + RSI divergence down 4h (a short with it). -> <LABSTORE>/wf/cfl_var_<NEW>+idle<RULE>.json
= Классика's own list + these (one list: they share its room, never at once). usage: run_cfl_idle.sh cfl_idle3.py"""
import os, sys, json, numpy as np
sys.argv = ["x"]
exec(open("cfl_var.py").read().rsplit('if __name__ == "__main__":', 1)[0])
NEW = "dr14+c210+cap30+s0.5t6+ctf4+s0.4t8+q995+fpos90+fatrh+fde50"
p = dict(BASE)
for part in NEW.split("+"): p = merge(p, VARS[part])
L = build(p); E0 = np.array(sorted(x["t0"] for x in L)); SPANS = sorted((x["t0"], x["t1"]) for x in L)
def quiet(t):
    k = np.searchsorted(E0, t, side="right") - 1
    if k >= 0 and t - E0[k] < 14 * 86400: return False
    return not any(a <= t < b for a, b in SPANS[max(0, k - 40):k + 1])
F_ = {f: k for k, f in enumerate(E3.FAMS)}
RULES = {"K": [("kelt_brk_1d", 1, 1)], "KS": [("kelt_brk_1d", 1, 1), ("st_flip_1d", 1, 1)],
         "KSN": [("kelt_brk_1d", 1, 1), ("st_flip_1d", 1, 1), ("nr7_1d", 1, -1), ("rsi_div_4h", -1, 1)]}   # (family, the signal's side, the way)
EX = dict(DEF); EX.update({"sk": 0.5, "hard": 1.0, "ctf": 4, "take": 6.0, "hold": 96}); CAP = int(os.environ.get("IDLE_CAP", 10))
base = np.isfinite(SC) & (T >= ts(2023)) & (T < ts(2026, 10))
for rn, groups in RULES.items():
    c = []
    for f, s, way in groups:
        m = np.where(base & (FAM == F_[f]) & (SIDE == s))[0]
        c += [(int(i), way) for i in m if T[i] - FIRST[SYM[i]] >= 90 * 86400]
    c.sort(key=lambda x: T[x[0]])
    busy, act, out = {}, [], []
    for i, way in c:
        t = int(T[i])
        if not quiet(t): continue
        sd = way * int(SIDE[i]); key = (SYM[i], sd)
        if busy.get(key, 0) > t: continue
        Tb, O, H, L_, C_, V = bars(SYM[i]); jE = int(J[i]) + 1
        if jE + 1 >= len(C_): continue
        r, kk = walk2(Tb, O, H, L_, C_, jE, sd, float(DA[i]), EX["sk"], EX["hard"], EX["ctf"], EX["take"], EX["hold"], EX["be_at"], EX["be_to"],
                      EX["tr_at"], EX["tr_d"], EX["p_at"], EX["p_fr"], EX["p_be"], EX["lim"], EX["wait"])
        if r != r: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == sd) >= CAP: continue
        t0 = int(Tb[jE]); end = t0 + int(kk) * 3600; busy[key] = end + 24 * 3600; act.append((end, sd))
        st = max(0.002, EX["sk"] * float(DA[i]) / 100)
        out.append({"t0": t0, "t1": end, "r": float(r), "st": st, "sth": st * EX["hard"] / EX["sk"], "mod": "cfl", "sym": Dd["names"][SYM[i]],
                    "side": sd, "e": float(O[jE]), "stream": None, "bot": bool(BOT[i]), "idle": rn})
    r = np.array([x["r"] for x in out]); t = np.array([x["t0"] for x in out]); hh = np.array([(x["t1"] - x["t0"]) / 3600 for x in out])
    ys = " ".join(f"{Y}: {int(((t >= ts(Y)) & (t < ts(Y + 1))).sum())} {r[(t >= ts(Y)) & (t < ts(Y + 1))].mean():+.2f}" for Y in (2023, 2024, 2025, 2026) if ((t >= ts(Y)) & (t < ts(Y + 1))).any())
    allL = sorted(L + out, key=lambda x: x["t0"]); im, gap = idle(allL)
    print(f"тишина {rn}: {len(out)} сделок, {r.mean():+.3f}R, WR {(r > 0).mean() * 100:.0f}%, держится в среднем {hh.mean():.0f} ч (макс {hh.max():.0f}) | {ys} | "
          f"вместе с Классикой: пустых месяцев {im} из 45, самая длинная пауза {gap} дн", flush=True)
    json.dump(allL, open(f"{ST}/wf/cfl_var_{NEW}+idle{rn}.json", "w"))
print("cfl idle3 done", flush=True)
