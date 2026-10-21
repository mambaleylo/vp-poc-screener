"""Walk-forward judge for event families saved as <dir>/<SYM>.npz (t, side, R[exits], K[exits], F[, fam]):
a yearly LightGBM on the BOT coins (127) only, trained on everything closed 14 days before the year; the threshold =
the q-quantile of the bot coins' scores in the previous year (the EMA research's rule); the CHECK coins (84) are never
trained on. Trades: score >= thr, one per coin & side at a time, at most CAP per side; growth at an equal 1-in-10
drawdown (45% bot / 50% check) by month-block bootstrap, per year of the window -> x/year.
usage: lv_wf.py DIR EXIT Q CAP [mask-expr over F columns by name, e.g. "scope==0"]"""
import sys, os, json, glob
ARGS = sys.argv[1:]
import numpy as np
import lightgbm as lgb
from mk import ts
import nx_h
from nx_h import pain

def load_dir(dr, fnames):
    sp = json.load(open("lv/split.json")); bot = set(sp["bot"])
    parts = []
    for fn in sorted(glob.glob(f"{dr}/*.npz")):
        sym = os.path.basename(fn)[:-4]
        z = np.load(fn)
        if len(z["t"]) == 0: continue
        parts.append((sym, sym in bot, z))
    T = np.concatenate([z["t"] for _, _, z in parts]).astype(np.int64)
    SYM = np.concatenate([np.full(len(z["t"]), k) for k, (_, _, z) in enumerate(parts)])
    BOT = np.concatenate([np.full(len(z["t"]), b) for _, b, z in parts])
    SIDE = np.concatenate([z["side"] for _, _, z in parts]).astype(np.int64)
    R = np.concatenate([z["R"] for _, _, z in parts], axis=1)
    K = np.concatenate([z["K"] for _, _, z in parts], axis=1)
    F = np.concatenate([z["F"] for _, _, z in parts]).astype(np.float32)
    return dict(T=T, SYM=SYM, BOT=BOT, SIDE=SIDE, R=R, K=K, F=F, names=[p[0] for p in parts])

def scores(Dd, e, years=(2022, 2023, 2024, 2025, 2026), mask=None, seeds=2, params=None):
    T, F, BOT = Dd["T"], Dd["F"], Dd["BOT"]
    y = np.nan_to_num(Dd["R"][e], nan=0.0).clip(-1.2, 6.0)
    m0 = np.ones(len(T), bool) if mask is None else mask
    SC = np.full(len(T), np.nan); THR = {}
    pr = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1,
              colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
    pr.update(params or {})
    for Y in years:
        tr = m0 & BOT & (T < ts(Y) - 14 * 86400)
        if tr.sum() < 2000: continue
        sc = np.zeros(len(T))
        for s_ in range(seeds):
            sc += lgb.LGBMRegressor(random_state=s_, **pr).fit(F[tr], y[tr]).predict(F) / seeds
        te = m0 & (T >= ts(Y)) & (T < ts(Y + 1))
        SC[te] = sc[te]
        ref = m0 & BOT & (T >= ts(Y - 1)) & (T < ts(Y) - 14 * 86400)
        # v2: the previous year's OUT-OF-SAMPLE scores when there are any (in-sample ones are inflated by the fit)
        prev_oos = ref & np.isfinite(SC)
        THR[Y] = SC[prev_oos] if prev_oos.sum() >= 200 else sc[ref]
    return SC, THR

def select(Dd, e, SC, THR, q, cap, sub):
    T, SIDE, SYM, K = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["K"][e]
    yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T]) if "YR" not in Dd else Dd["YR"]
    Dd["YR"] = yr
    thr = np.array([np.quantile(THR[Y], q) if Y in THR else np.inf for Y in range(1970, 2030)])
    ok = sub & np.isfinite(SC) & (SC >= thr[np.clip(yr - 1970, 0, 59)])
    idx = np.where(ok)[0]
    o = idx[np.lexsort((-SC[idx], T[idx]))]
    busy, act, out = {}, [], []
    for i in o:
        t = T[i]; key = (SYM[i], SIDE[i])
        if busy.get(key, 0) > t: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= cap: continue
        end = t + int(K[i]) * 3600; busy[key] = end; act.append((end, SIDE[i])); out.append(i)
    return np.array(out, dtype=np.int64)

GRID = tuple(np.round(np.arange(0.0025, 0.1001, 0.0025), 4))
def judge(Dd, e, sel, target, t0=None, nb=200, seed=7):
    T, R, K = Dd["T"], Dd["R"][e], Dd["K"][e]
    t0 = t0 or ts(2022)
    sel = sel[T[sel] >= t0]
    if len(sel) < 20: return None
    tr = sorted([(int(T[i]), int(T[i] + K[i] * 3600), float(R[i]), int(Dd["SIDE"][i]), int(i)) for i in sel])
    mo = (ts(2026, 10) - t0) / (30.4 * 86400)
    r = np.array([x[2] for x in tr])
    nx_h.rng = np.random.default_rng(seed)
    b = pain(tr, target, GRID, nb=nb)
    yrs = {Y: float(r[(np.array([x[0] for x in tr]) >= ts(Y)) & (np.array([x[0] for x in tr]) < ts(Y + 1))].mean()) for Y in range(2022, 2027)}
    return dict(n=len(r), wk=len(r) / (mo * 30.4 / 7), R=float(r.mean()), wr=float(np.mean(r > 0)),
                f=b[0] if b else 0, x=b[1] if b else 0, xy=(b[1] ** (12 / mo)) if b else 0, yrs=yrs)

def fmt(nm, a, b):
    def one(s):
        if not s: return "—"
        return (f"{s['n']:4d} {s['wk']:4.1f}/нед {s['R']:+.2f}R WR{s['wr']*100:3.0f}% риск {s['f']*100:4.2f}% x{s['xy']:5.2f}/год"
                + " [" + " ".join(f"{v:+.2f}" if v == v else "  —  " for v in s["yrs"].values()) + "]")
    return f"{nm:34s} бот: {one(a)} | проверка: {one(b)}"

if __name__ == "__main__":
    dr, e, q, cap = ARGS[0], int(ARGS[1]), float(ARGS[2]), int(ARGS[3])
    import lv_engine as LE
    Dd = load_dir(dr, LE.FNAMES)
    mask = None
    if len(ARGS) > 4:
        env = {nm: Dd["F"][:, k] for k, nm in enumerate(LE.FNAMES)}
        mask = eval(ARGS[4], {"np": np}, env)
    SC, THR = scores(Dd, e, mask=mask)
    sub = np.ones(len(Dd["T"]), bool) if mask is None else mask
    a = judge(Dd, e, select(Dd, e, SC, THR, q, cap, sub & Dd["BOT"]), 0.45)
    b = judge(Dd, e, select(Dd, e, SC, THR, q, cap, sub & ~Dd["BOT"]), 0.50)
    print(fmt(f"{dr} E{e} q{q} cap{cap} {ARGS[4] if len(ARGS) > 4 else ''}", a, b), flush=True)
