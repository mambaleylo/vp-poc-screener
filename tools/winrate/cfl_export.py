"""🔄 Классика наоборот v1 export: the 2026 walk-forward model on the flipped E2 label (the classic indicator events of
ev3_engine, the ev2 features without ls_z / tk_z / top_z — the live bot cannot rebuild their 30-day z), LightGBM x2
seeds with lv_wf's params, trained on the bot coins' events closed 14 days before 2026 — exactly the model that scored
the 2026 trades of the research (checked against fc_red_sc.npz). The rolling threshold's seed: per day (UTC) the count of
the bot coins' scored events and their 300 best scores, the 194 days before the export; the bot adds its own days.
The backtest list: the rolling rule (q 0.997 of the scores of the 180 days ending 14 days before) 2023-26, bot coins,
>= 90 days after the listing, cap 12 a side, one per coin & side, the score order within the hour."""
import sys, json, glob, math, numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
sys.argv = ["x"]
import lv_engine as LE, ev3_engine as E3, ev2_engine as E2
from lv_wf import load_dir, ts
from lgbpure import export
from bt_trades import gate_sym
Dd = load_dir("ev3", E3.FNAMES); T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]; F = Dd["F"]
J, DA = [], []
for fn in sorted(glob.glob("ev3/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    J.append(z["j"]); DA.append(z["datr"])
J, DA = np.concatenate(J).astype(np.int64), np.concatenate(DA)
ZERO = ["ls_z", "tk_z", "top_z"]
F[:, [E2.FNAMES.index(c) for c in ZERO]] = 0.0
z = np.load("fc_RF.npz"); RF, KF = z["RF"], z["KF"]
ref = np.load("fc_red_sc.npz", allow_pickle=True)["SC"]
MASK = T >= ts(2021); CUT = ts(2026) - 14 * 86400
pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1,
          colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
y = np.nan_to_num(RF, nan=0.0).clip(-1.2, 6.0)
tr = MASK & BOT & (T < CUT)
sc = np.zeros(len(T)); trees = []
for s_ in range(2):
    m = lgb.LGBMRegressor(random_state=s_, **pr).fit(F[tr], y[tr]); trees.append(export(m.booster_, E2.FNAMES)["trees"]); sc += m.predict(F) / 2
chk = MASK & (T >= ts(2026))
print("обучено на", int(tr.sum()), "| 2026 событий", int(chk.sum()), "| max|оценка − walk-forward| =", float(np.nanmax(np.abs(sc[chk] - ref[chk]))), flush=True)
# the rolling threshold's seed: the bot coins' events of the 194 days before the export, per UTC day: n and the 300 best
NOW = ts(2026, 10)
seed = {}
m_ = BOT & MASK & (T >= NOW - 194 * 86400) & (T < NOW)
for d in np.unique(T[m_] // 86400):
    v = np.sort(sc[m_ & (T // 86400 == d)])[::-1]
    seed[str(int(d))] = [int(len(v)), [round(float(x), 5) for x in v[:300]]]
def thr_at(t, scores_by_day, q=0.997, win=180, lag=14):
    hi = (t // 86400) - lag; lo = hi - win
    n = 0; top = []
    for d, (k, v) in scores_by_day.items():
        if lo <= int(d) < hi: n += k; top += v
    if n < 300: return None
    rank = int(math.floor((1 - q) * (n - 1)))   # numpy's linear quantile: between the (n-1)q-th and the next; the bot takes the same
    top.sort(reverse=True)
    pos = q * (n - 1); i0 = int(math.floor(pos)); fr = pos - i0   # ascending index i0
    a = top[n - 1 - i0] if n - 1 - i0 < len(top) else None; b = top[n - 2 - i0] if 0 <= n - 2 - i0 < len(top) else a
    return None if a is None else a + fr * ((b if b is not None else a) - a)
# the backtest list (the rolling rule; the threshold from the per-day tops — checked against numpy's exact quantile)
D0 = ts(2021, 1) // 86400
allbot = BOT & MASK & np.isfinite(ref)
byday = {}
for d in np.unique(T[allbot] // 86400):
    v = np.sort(ref[allbot & (T // 86400 == d)])[::-1]; byday[str(int(d))] = [int(len(v)), [float(x) for x in v[:300]]]
tt = T[allbot]; ss = ref[allbot]; o = np.argsort(tt); tt, ss = tt[o], ss[o]
mism = 0; days = {}
for d in range(ts(2023) // 86400, NOW // 86400):
    hi = (d - 14) * 86400; lo = hi - 180 * 86400; a, b = np.searchsorted(tt, lo), np.searchsorted(tt, hi)
    ex = float(np.quantile(ss[a:b], 0.997)) if b - a >= 300 else np.inf
    mine = thr_at(d * 86400, byday); mine = np.inf if mine is None else mine
    days[d] = ex
    if not (abs(ex - mine) < 1e-9 or (np.isinf(ex) and np.isinf(mine))): mism += 1
print("порог по дням: расхождений с точным квантилем", mism, flush=True)
age0 = {}
cand = np.where(BOT & np.isfinite(ref) & (T >= ts(2023)))[0]
cand = cand[ref[cand] >= np.array([days.get(int(t // 86400), np.inf) for t in T[cand]])]
def walk(O, H, L, C, jE, s, fill, datr, hold=72):
    risk = fill * datr / 100; stop = fill - s * risk; tp = fill + s * 3 * risk
    e = min(len(C), jE + hold); k = e - 1 - jE; ex = C[e - 1]; kind = "time"
    for q in range(e - jE):
        b = jE + q
        if (s > 0 and L[b] <= stop) or (s < 0 and H[b] >= stop):
            gap = (s > 0 and O[b] <= stop) or (s < 0 and O[b] >= stop); ex = O[b] if (gap and q > 0) else stop; k = q; kind = "stop"; break
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            ex = tp; k = q; kind = "take"; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * fill / risk
    return s * (ex - fill) / risk - fee, k + 1, kind, ex, stop, tp
info = {}
for k in sorted(set(SYM[cand])):
    Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
    for i in cand[SYM[cand] == k]:
        if T[i] - Tb[0] < 90 * 86400: continue
        jE = int(J[i]) + 1
        if jE >= len(C): continue
        r, nb, kind, ex, stop, tp = walk(O, H, L, C, jE, -int(SIDE[i]), float(O[jE]), float(DA[i]))
        info[i] = (r, nb, kind, ex, stop, tp, float(O[jE]))
c2 = np.array(sorted(info), np.int64)
oo = c2[np.lexsort((-ref[c2], T[c2]))]
busy, act, sel = {}, [], []
for i in oo:
    t = T[i]; key = (SYM[i], SIDE[i])
    if busy.get(key, 0) > t: continue
    act = [a for a in act if a[0] > t]
    if sum(1 for a in act if a[1] == SIDE[i]) >= 12: continue
    end = t + int(info[i][1]) * 3600; busy[key] = end; act.append((end, SIDE[i])); sel.append(i)
out = []
for i in sel:
    r, nb, kind, ex, stop, tp, fill = info[i]; gs, scl = gate_sym(Dd["names"][SYM[i]]); fm = E3.FAMS[int(F[i, 0])]
    out.append({"s": gs, "d": -int(SIDE[i]), "c": "1h", "tf": fm.split("_")[-1], "lvl": fm, "t": int(T[i]) + 3600, "e": round(fill / scl, 10),
                "sl": round(stop / scl, 10), "tp": round(tp / scl, 10), "x": int(T[i]) + 3600 + int(nb) * 3600, "xp": round(ex / scl, 10), "r": round(float(r), 3), "k": kind})
out.sort(key=lambda x: x["t"])
rr = np.array([x["r"] for x in out]); tt2 = np.array([x["t"] for x in out]); years = {}
for Y in range(2023, 2027):
    m = (tt2 >= ts(Y)) & (tt2 < ts(Y + 1))
    if m.any(): years[str(Y)] = {"n": int(m.sum()), "avg": round(float(rr[m].mean()), 3), "wr": round(float((rr[m] > 0).mean() * 100), 1), "sum": round(float(rr[m].sum()), 1)}
print("список", len(out), "ср.R", round(float(rr.mean()), 3), "WR", round(float((rr > 0).mean() * 100), 1), years, flush=True)
sp = json.load(open("lv/split.json"))
M = {"ver": 1, "feats": E2.FNAMES, "zero": ZERO, "fams": E3.FAMS, "coins": sp["bot"], "models": trees, "trained_to": int(CUT),
     "rule": {"q": 0.997, "win_d": 180, "lag_d": 14, "stop_datr": 1.0, "take_r": 3.0, "hold_h": 72, "cooldown_h": 24, "min_age_d": 90, "side_cap": 12},
     "seed": seed, "seed_to": int(NOW),
     "research": {"years": years, "avg": round(float(rr.mean()), 3), "wr": round(float((rr > 0).mean() * 100), 1), "n": len(out),
                  "check": {"avg": 0.20, "wr": None}, "check_coins": 84}}
json.dump(M, open("vp_cfl_model.json", "w"), separators=(",", ":")); json.dump(out, open("cfl_bt_v1.json", "w"), separators=(",", ":"))
print("файл модели", len(json.dumps(M)) // 1024, "КБ")
