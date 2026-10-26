"""classic indicators (ev3) — the original side and the opposite side with a ROLLING threshold: an event is taken when
its walk-forward score >= q of the out-of-sample scores (bot coins, same family) of the D days ending 14 days before it
(causal; the yearly threshold left 2023 empty: the 2022 bear scores set it too high). cap 12 a side, one per coin & side,
the score order within an hour (as lv_wf.select). By year, bot / check coins; lists for the money -> fc_<side>_<D>_<q>.json"""
import sys, json, glob, numpy as np, warnings; warnings.filterwarnings("ignore")
sys.argv = ["x"]
import lv_engine as LE, ev3_engine as E3
from lv_wf import load_dir, ts
from bt_trades import gate_sym
Dd = load_dir("ev3", E3.FNAMES); T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]
J, DA = [], []
for fn in sorted(glob.glob("ev3/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    J.append(z["j"]); DA.append(z["datr"])
J, DA = np.concatenate(J).astype(np.int64), np.concatenate(DA)
SCo = np.load("div_ev3_3690_sc.npz", allow_pickle=True)["SC"]; SCf = np.load("flip_ev3_классика_sc.npz", allow_pickle=True)["SC"]
Ro, Ko = Dd["R"][2], Dd["K"][2]
RF = np.full(len(T), np.nan); KF = np.zeros(len(T), np.int64)
cand = np.where(np.isfinite(SCf) & (T >= ts(2022)))[0]
D0 = ts(2021, 1) // 86400; ND = ts(2026, 11) // 86400 - D0
def daily_thr(SC, q, D):
    m = np.isfinite(SC) & BOT; tt = T[m]; ss = SC[m]; o = np.argsort(tt); tt, ss = tt[o], ss[o]
    thr = np.full(ND, np.inf)
    for d in range(ND):
        hi = (D0 + d) * 86400 - 14 * 86400; lo = hi - D * 86400
        a, b = np.searchsorted(tt, lo), np.searchsorted(tt, hi)
        if b - a >= 300: thr[d] = np.quantile(ss[a:b], q)
    return thr
# the opposite side's outcome for the candidates only (the ones that may pass)
need = set()
def pick(SC, R, K, q, D, flip):
    thr = daily_thr(SC, q, D); di = (T // 86400 - D0).clip(0, ND - 1)
    ok = np.isfinite(SC) & (SC >= thr[di]) & (T >= ts(2023))
    idx = np.where(ok)[0]
    if flip:
        for k in sorted(set(SYM[idx])):
            Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
            for i in idx[SYM[idx] == k]:
                if np.isfinite(RF[i]): continue
                jE = int(J[i]) + 1
                if jE < len(C): RF[i], KF[i] = LE.simp(O, H, L, C, jE, -int(SIDE[i]), float(O[jE]), float(DA[i]), 1.0, 3.0, 72, 0.0, 0.0)
        R, K = RF, KF
    o = idx[np.lexsort((-SC[idx], T[idx]))]
    busy, act, out = {}, [], []
    for i in o:
        if not np.isfinite(R[i]): continue
        t = T[i]; key = (SYM[i], SIDE[i])
        if busy.get(key, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= 12: continue
        end = t + int(K[i]) * 3600; busy[key] = end; act.append((end, SIDE[i])); out.append(i)
    s = np.array(out, np.int64); r = R[s]; b = BOT[s]; y = (T[s].astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
    nm = f"{'обратная' if flip else 'прямая  '} скольз.{D}д q{q}"
    print(f"  {nm:26s} сделок {len(s):4d} {r.mean():+.3f}R WR {np.mean(r > 0)*100:3.0f}% | бота {r[b].mean():+.2f}({b.sum()}) контр. {r[~b].mean():+.2f}({(~b).sum()}) | "
          + " ".join(f"{Y % 100}:{r[y == Y].mean():+.2f}({(y == Y).sum()})" for Y in range(2023, 2027) if (y == Y).any()), flush=True)
    for tag, sub in (("", s[BOT[s]]), ("_chk", s[~BOT[s]])):
        js = []
        for i in sub:
            gs, scl = gate_sym(Dd["names"][SYM[i]]); t0 = int(T[i]) + 3600
            js.append({"s": gs, "d": int(-SIDE[i] if flip else SIDE[i]), "t": t0, "x": t0 + int(K[i]) * 3600, "e": 1.0, "sl": 1.0 - float(DA[i]) / 100, "r": float(R[i]), "fam": int(Dd["F"][i, 0])})
        json.dump(js, open(f"fc_{'f' if flip else 'o'}_{D}_{q}{tag}.json", "w"))
    return s

for D in (120, 180, 240):
    for q in (0.993, 0.995, 0.997):
        pick(SCf, None, None, q, D, True)
