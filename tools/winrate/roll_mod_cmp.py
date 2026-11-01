"""roll_mod.py's schedules side by side per module: each month's threshold = the module's q of the variant's own out-of-sample
scores over the 365 days before on the module's threshold set (the first period's in-sample ones while short; 🚀: its fixed
0.8); the picks = the judged events over it 2023-01 .. 2026-09 (no cap / dedupe — the same for every variant): a month, R,
the sum, the drawdown, R by year; the coins trained on and the never-seen ones apart. usage: roll_mod_cmp.py MOD [MOD...]"""
import sys; AV = list(sys.argv)
import os, numpy as np
import roll_mod as RM
NM = {"Y": "вся история, раз в год", "Q": "вся история, раз в 3 мес", "M0": "вся история, каждый месяц", "M12": "12 мес, каждый месяц",
      "M24": "24 мес, каждый месяц", "Q24": "24 мес, раз в 3 мес"}
ts = RM.ts
def stats(T, R, sel):
    if sel.sum() < 20: return "мало сделок"
    t = T[sel]; r = R[sel]; o = np.argsort(t); c = np.cumsum(r[o]); dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    yrs = " ".join(f"{Y}: {r[(t >= ts(Y)) & (t < ts(Y + 1))].mean():+.2f}" if ((t >= ts(Y)) & (t < ts(Y + 1))).any() else f"{Y}: —" for Y in (2023, 2024, 2025, 2026))
    return f"{sel.sum() / 45:6.1f}/мес {r.mean():+.3f}R Σ{r.sum():+7.0f}R просадка {dd:5.0f}R | {yrs}"
for MOD in AV[1:]:
    d = RM.data(MOD); T, R = d["T"], d["R"]
    for gname, trm, evm, thm in d["groups"]:
        print(f"== {MOD}: {gname}", flush=True)
        for v in NM:
            fn = f"roll_{MOD}_{v}.npz"
            if not os.path.exists(fn): continue
            z = np.load(fn); SC, INS = z["SC"], z["INS"]
            if "thr" in d:
                thr = np.full(len(T), d["thr"])
            else:
                thr = np.full(len(T), np.inf); yy, mm = 2023, 1
                while ts(yy, mm) < RM.END:
                    a = ts(yy, mm); yy, mm = (yy + 1, 1) if mm == 12 else (yy, mm + 1); b = ts(yy, mm)
                    ref = thm & (T >= a - 365 * 86400) & (T < a); x = SC[ref & np.isfinite(SC)]
                    if len(x) < 2000: x = np.r_[x, INS[ref & np.isfinite(INS)]]
                    if len(x): thr[(T >= a) & (T < b)] = np.quantile(x, d["q"])
            pk = evm & np.isfinite(SC) & (SC >= thr) & (T >= ts(2023)) & (T < RM.END) & np.isfinite(R)
            if d["unseen"] is None:
                print(f"   {NM[v]:28s} {stats(T, R, pk)}", flush=True)
            else:
                print(f"   {NM[v]:28s} обуч. монеты: {stats(T, R, pk & ~d['unseen'])}\n   {'':28s} новые монеты: {stats(T, R, pk & d['unseen'])}", flush=True)
print("roll cmp done", flush=True)
