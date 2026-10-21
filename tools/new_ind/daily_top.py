"""Regular selection: every UTC day the best K events by the walk-forward score (with a floor = the q-quantile of the
previous year's OOS scores), one per coin & side at a time, cap per side; vs the plain threshold. Per set: trades per
month, weeks with a trade, win rate, R, growth at the equal 1-in-10 drawdown."""
import sys
ARG = sys.argv[1:]
import json, collections, numpy as np, warnings; warnings.filterwarnings("ignore")
from lv_wf import *
import lv_engine as LE
dr, scf, mexp = ARG[0], ARG[1], ARG[2]
Dd = load_dir(dr, LE.FNAMES)
env = {nm: Dd["F"][:, k] for k, nm in enumerate(LE.FNAMES)}
mask = eval(mexp, {"np": np}, env)
z = np.load(scf, allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
e = 2; T, SIDE, SYM, K = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["K"][e]
yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T])
def floor(q): return np.array([np.quantile(THR[Y], q) if Y in THR else np.inf for Y in range(1970, 2030)])[np.clip(yr - 1970, 0, 59)]
def sel_daily(sub, qf, kday, cap=12):
    ok = sub & np.isfinite(SC) & (SC >= floor(qf)) & (T >= ts(2022))
    idx = np.where(ok)[0]; o = idx[np.lexsort((-SC[idx], T[idx]))]
    busy, act, out, day_n = {}, [], [], collections.Counter()
    for i in o:
        t = T[i]; key = (SYM[i], SIDE[i]); d = t // 86400
        if day_n[d] >= kday or busy.get(key, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= cap: continue
        end = t + int(K[i]) * 3600; busy[key] = end; act.append((end, SIDE[i])); out.append(i); day_n[d] += 1
    return np.array(out, dtype=np.int64)
mo = (ts(2026, 10) - ts(2022)) / (30.4 * 86400); nw = int((ts(2026, 10) - ts(2022)) / (7 * 86400))
def line(nm, sel, tgt):
    if len(sel) < 20: print(nm, "—"); return
    r = Dd["R"][e][sel]; wk = len(set((T[sel] // (7 * 86400)).tolist()))
    j = judge(Dd, e, sel, tgt)
    print(f"{nm:34s} {len(sel)/mo:5.1f}/мес недель {wk/nw*100:3.0f}% WR {np.mean(r>0)*100:3.0f}% {r.mean():+.2f}R  риск {j['f']*100:.2f}% x{j['xy']:.2f}/год", flush=True)
for setn, sub, tgt in (("бот", mask & Dd["BOT"], 0.45), ("проверка", mask & ~Dd["BOT"], 0.50)):
    line(f"{setn} порог q0.99", select(Dd, e, SC, THR, 0.99, 12, sub), tgt)
    for qf in (0.95, 0.97, 0.98):
        for kd in (1, 2, 3):
            line(f"{setn} день top{kd} пол q{qf}", sel_daily(sub, qf, kd), tgt)
