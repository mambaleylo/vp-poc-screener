"""Peak Reversal audit, part 2: rule filters and a model on the band events (walk-forward, top q per side,
one trade per coin & side for its hold, at most 12 per side)"""
import os, sys, glob, json
ARGS = sys.argv[1:]
import numpy as np, lightgbm as lgb
from mk import ts
from common import D
import nx_feat
from prv_ev import STOPS, TAKES, BAND_NAMES
NAMES = BAND_NAMES + nx_feat.NAMES
Xs, Ys, Ts, Ss = [], [], [], []
for k, fn in enumerate(sorted(glob.glob(f"{D}/prv_ev/*.npz"))):
    z = np.load(fn)
    if len(z["t"]):
        Xs.append(z["X"]); Ys.append(z["Y"]); Ts.append(z["t"]); Ss.append(np.full(len(z["t"]), k, dtype=np.int16))
X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts); SY = np.concatenate(Ss)
Y = np.where(np.abs(Y) > 20, np.nan, Y)
F = {n: X[:, i] for i, n in enumerate(NAMES)}
SD = F["side"].astype(int); TF = F["tf"].astype(int)
print("events", len(T), flush=True)
YRS = (2021, 2022, 2023, 2024, 2025)
def yr_mask(y):
    return (T >= ts(y)) & (T < (ts(y + 1) if y < 2025 else ts(2027)))
def wk(y):
    return ((ts(y + 1) if y < 2025 else ts(2026, 10)) - ts(y)) / (7 * 86400)
def replay(sel, lab, cap=12):
    o = sel[np.argsort(T[sel], kind="stable")]
    busy, act, out = {}, [], []
    for j in o:
        t = T[j]; key = (SY[j], SD[j])
        if busy.get(key, 0) > t:
            continue
        act = [a for a in act if a[0] > t]
        if cap and sum(1 for a in act if a[1] == SD[j]) >= cap:
            continue
        end = t + 48 * TF[j] * 3600
        busy[key] = end; act.append((end, SD[j]))
        if lab[j] == lab[j]:
            out.append((end, float(lab[j])))
    return out
def fmt(out, y):
    if not out:
        return "—"
    out.sort(); rs = np.array([r for _, r in out]); c = np.cumsum(rs)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
    return f"{rs.mean():+.2f}R×{len(rs) / wk(y):.0f}/нед dd{dd:.0f}"
def lab_of(sk, tk):
    return Y[:, STOPS.index(sk), TAKES.index(tk)]
MODE = ARGS[0] if ARGS else ("filters" if __name__ == "__main__" else "none")
if MODE == "filters":
    base = (F["depth"] >= 2.0)   # the bot: a wick touch of the x2 band
    flt = {
        "бот: касание ×2 (без фильтров)": base,
        "+ флэт: ADX < 20": base & (F["adx"] < 20),
        "+ сильный тренд: ADX > 30": base & (F["adx"] > 30),
        "+ по тренду дня (цена с той стороны EMA200 дня)": base & (F["side"] * F["dd_e200"] > 0),
        "+ против тренда дня": base & (F["side"] * F["dd_e200"] < 0),
        "+ сжатие (BB уже канала)": base & (F["squeeze"] < 1.0),
        "+ уже возврат внутрь (закрытие обратно)": base & (F["reent"] > 0),
        "+ закрытие за полосой": base & (F["close_out"] > 0),
        "+ глубоко: ×3 и дальше": F["depth"] >= 3.0,
        "+ RSI крайний (<25 лонг / >75 шорт)": base & (((F["side"] > 0) & (F["rsi14"] < 25)) | ((F["side"] < 0) & (F["rsi14"] > 75))),
        "+ BTC по направлению сделки за 24ч": base & (F["side"] * F["b_r24"] > 0),
        "+ длинная тень в сторону возврата (>0.4)": base & (F["wick"] > 0.4),
        "+ объём всплеск (vol_z > 2)": base & (F["vol_z"] > 2),
    }
    for (sk, tk) in ((1.0, 2.0), (1.5, 2.0), (1.5, "mid")):
        lab = lab_of(sk, tk)
        print(f"\n== фильтры: стоп {sk} ATR, тейк {tk} (48 баров), 1ч и 4ч вместе ==", flush=True)
        for nm, m in flt.items():
            line = [fmt(replay(np.where(m & yr_mask(y))[0], lab), y) for y in YRS]
            print(f"{nm:52s} " + " | ".join(f"{y}: {s}" for y, s in zip(YRS, line)), flush=True)
elif MODE == "model":
    rules = [r.split("_") for r in ARGS[1:]] or [["1.0", "2.0"], ["1.5", "2.0"], ["1.5", "mid"], ["1.0", "1.0"], ["1.5", "3.0"]]
    for r in rules:
        sk = float(r[0]) if r[0] != "ext" else "ext"; tk = float(r[1]) if r[1] != "mid" else "mid"
        lab = lab_of(sk, tk)
        res = {q: [] for q in (0.9, 0.95, 0.98, 0.99)}
        for y in (2022, 2023, 2024, 2025):
            tr = T < ts(y) - 10 * 86400
            ref = (T >= ts(y - 1)) & (T < ts(y) - 10 * 86400)
            te = yr_mask(y)
            sc = np.full(len(T), -9.0)
            for s in (1, -1):
                ok = tr & (SD == s) & ~np.isnan(lab)
                m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                      colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=1).fit(X[ok], lab[ok].clip(-1.5, 4))
                w = (SD == s) & (ref | te)
                sc[w] = m.predict(X[w])
            for q in res:
                sel = []
                for s in (1, -1):
                    thr = float(np.quantile(sc[ref & (SD == s)], q))
                    sel.append(np.where(te & (SD == s) & (sc >= thr))[0])
                res[q].append(fmt(replay(np.concatenate(sel), lab), y))
        for q, v in res.items():
            print(f"модель, стоп {sk} тейк {tk}, топ {100 - q * 100:.0f}%: " + " | ".join(f"{y}: {s}" for y, s in zip((2022, 2023, 2024, 2025), v)), flush=True)
