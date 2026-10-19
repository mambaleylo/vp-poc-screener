"""The backtest trades the bot lists in its tabs (vp_bt_trades.json): 📈 range breakout (day / 12h, the bot's rule,
cap 6 per side, strongest first) and Peak Reversal v3 (the 24-month quarterly walk-forward, 3 models per retrain, top 1%
per side, cap 12). Each trade: coin, side, chart, entry time / price, stop, take, exit time / price, R — re-simulated
from the bars and checked against the research's own label."""
import os, sys, json, glob, pickle, importlib, datetime as dt
import numpy as np
from common import V, load, D
from mk import ts
import nx_feat
FEE, FUND = 0.001, 0.0003
OUT = {"ver": 1, "made": int(dt.datetime.now(dt.timezone.utc).timestamp())}


def gate_sym(sym):
    b = sym[:-4]
    return (b[4:] if b.startswith("1000") else b) + "_USDT", (1000.0 if b.startswith("1000") else 1.0)


# ---------------- 📈 range breakout ----------------
def rbx_trades():
    res, bad = [], 0
    for TFH, N0, K0, ch in ((24, 20, 2.5, "1d"), (12, 30, 4.0, "12h")):
        os.environ["TFH"] = str(TFH)
        import rb_tf; importlib.reload(rb_tf)
        files = sorted(glob.glob(f"{D}/rbtf{TFH}/*.pkl"))
        ev = []
        for k, fn in enumerate(files):
            for t, s, f, x, y in pickle.load(open(fn, "rb")):
                if f["N"] == N0 and f["rg"] < K0 and f["own200"]:
                    ev.append((t, k, s, f["brk"], y))
        si, xi = rb_tf.STOPS.index(1.5), rb_tf.EXITS.index("dc20")
        ev.sort(key=lambda e: (e[0], -e[3]))
        busy, act, chosen = {}, [], []
        for t, k, s, brk, y in ev:
            r, j = float(y[si, xi, 0]), y[si, xi, 1]
            if r != r or t < ts(2021):
                continue
            if busy.get((k, s), 0) > t:
                continue
            act = [a for a in act if a[0] > t]
            if sum(1 for a in act if a[1] == s) >= 6:
                continue
            end = int(t + int(j) * TFH * 3600); busy[(k, s)] = end; act.append((end, s))
            chosen.append((t, k, s, r))
        cache = {}
        for t, k, s, lab in chosen:
            sym = os.path.basename(files[k])[:-4]
            if sym not in cache:
                cs = V._oc_agg(load(sym), TFH)
                O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
                T = np.array([c["time"] + TFH * 3600 for c in cs])
                atr = np.array([v if v is not None else np.nan for v in nx_feat._wilder(list(nx_feat._tr(list(H), list(L), list(C))), 14)])
                cache[sym] = (O, H, L, C, T, atr)
            O, H, L, C, T, atr = cache[sym]
            i = int(np.searchsorted(T, t))
            e = O[i + 1]; risk = 1.5 * atr[i]; stop = e - s * risk
            hold = rb_tf.HOLD
            kind, kx, ex = "time", hold - 1, C[i + hold]
            for q in range(hold):
                b = i + 1 + q
                if (L[b] <= stop) if s > 0 else (H[b] >= stop):
                    kind, kx, ex = "stop", q, stop; break
                lv = L[b - 20:b].min() if s > 0 else H[b - 20:b].max()
                if (C[b] < lv) if s > 0 else (C[b] > lv):
                    kind, kx, ex = "trend", q, C[b]; break
            r = (s * (ex - e) - e * FEE - e * FUND * (kx + 1) * TFH / 24) / risk
            if abs(r - lab) > 0.02:
                bad += 1
            gs, sc = gate_sym(sym)
            hh, ll = H[i - N0:i].max(), L[i - N0:i].min()
            res.append({"s": gs, "d": s, "c": ch, "t": int(T[i]), "e": round(e / sc, 10), "sl": round(stop / sc, 10), "x": int(T[i + 1 + kx]),
                        "xp": round(float(ex) / sc, 10), "r": round(float(lab), 3), "k": kind, "hh": round(hh / sc, 10), "ll": round(ll / sc, 10), "n": N0,
                        "t0": int(T[i - N0] - TFH * 3600)})
        print("rbx", ch, len(chosen), "R mismatches", bad, flush=True)
    return res


# ---------------- Peak Reversal v3 ----------------
def prv_trades():
    import lightgbm as lgb
    import prv_wf as W
    SK, TK, Q, WIN, STEP, GAP = 1.5, 3.0, 0.99, 24, 3, 10 * 86400
    XSK, XTK, XHS = 3.0, 1.5, 6.0   # the traded rule (prv_export3.py ver 4): stop 3 ATR on the bar's close, hard stop 6 ATR
    BTCF = 4.0               # v0.99.641: no entry when BTC moved more than this % against the trade over 24 h
    BTCF1 = 1.0              # v0.99.642: ... or more than this % over the last hour
    lab = W.lab_of(SK, TK)
    xlab = np.load(f"{D}/prv_lab_cs.npz")["cs"].astype(float); xlab = np.where(np.abs(xlab) > 20, np.nan, xlab)
    def month_add(t, k):
        d = dt.datetime.fromtimestamp(int(t), dt.timezone.utc); m = d.month - 1 + k
        return int(dt.datetime(d.year + m // 12, m % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())
    def mdl(seed):
        return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                                 colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=seed)
    sel, scs = [], []
    t0, end = ts(2023), ts(2026, 10)
    while t0 < end:
        t1 = min(month_add(t0, STEP), end)
        tr = (W.T < t0 - GAP) & (W.T >= month_add(t0, -WIN) - GAP)
        ref = (W.T >= month_add(t0, -12) - GAP) & (W.T < t0 - GAP)
        te = (W.T >= t0) & (W.T < t1)
        for s in (1, -1):
            ok = tr & (W.SD == s) & ~np.isnan(lab)
            ms = [mdl(seed).fit(W.X[ok], lab[ok].clip(-1.5, TK + 1)) for seed in range(3)]
            ri, ti = np.where(ref & (W.SD == s))[0], np.where(te & (W.SD == s))[0]
            thr = float(np.quantile(sum(m.predict(W.X[ri]) for m in ms) / 3, Q))
            sc = sum(m.predict(W.X[ti]) for m in ms) / 3
            ok = (sc >= thr) & (W.SD[ti] * W.F["b_r24"][ti] > -BTCF) & (W.SD[ti] * W.F["b_r1"][ti] > -BTCF1)
            sel.append(ti[ok]); scs.append(sc[ok])
        print("quarter", dt.datetime.fromtimestamp(t0, dt.timezone.utc).strftime("%Y-%m"), flush=True)
        t0 = t1
    sel = np.concatenate(sel); scs = np.concatenate(scs)
    o = sel[np.lexsort((-scs, W.T[sel]))]
    busy, act, chosen = {}, [], []
    for j in o:
        t = W.T[j]; key = (W.SY[j], W.SD[j])
        if busy.get(key, 0) > t:
            continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == W.SD[j]) >= 12:
            continue
        e_ = t + 48 * W.TF[j] * 3600
        busy[key] = e_; act.append((e_, W.SD[j]))
        if xlab[j] == xlab[j]:
            chosen.append(j)
    files = sorted(glob.glob(f"{D}/prv_ev/*.npz"))
    syms = [os.path.basename(f)[:-4] for f in files if len(np.load(f)["t"])]
    cache, res, bad = {}, [], 0
    for j in chosen:
        sym = syms[int(W.SY[j])]; tf = int(W.TF[j]); s = int(W.SD[j]); t = int(W.T[j])
        if (sym, tf) not in cache:
            h1 = load(sym); cs = h1 if tf == 1 else V._oc_agg(h1, 4)
            O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
            T = np.array([c["time"] + tf * 3600 for c in cs])
            atr = np.array([a if a else np.nan for a in V.neuro_atr_series(cs, 14)])
            cache[(sym, tf)] = (O, H, L, C, T, atr)
        O, H, L, C, T, atr = cache[(sym, tf)]
        i = int(np.searchsorted(T, t))
        e = O[i + 1]; stop = e - s * XSK * atr[i]; tp = e + s * XTK * XSK * atr[i]; hs = e - s * XHS * atr[i]; risk = XHS * atr[i]
        kind, kx, ex = "time", 47, C[i + 48]
        for q in range(48):
            b = i + 1 + q
            if (L[b] <= hs) if s > 0 else (H[b] >= hs):
                kind, kx, ex = "hard", q, hs; break
            if (H[b] >= tp) if s > 0 else (L[b] <= tp):
                kind, kx, ex = "take", q, tp; break
            if (C[b] <= stop) if s > 0 else (C[b] >= stop):
                kind, kx, ex = "stop", q, C[b]; break
        r = (s * (ex - e) - e * FEE - e * FUND * (kx + 1) * tf / 24) / risk
        if abs(r - float(xlab[j])) > 0.02:
            bad += 1
        gs, scl = gate_sym(sym)
        res.append({"s": gs, "d": s, "c": f"{tf}h", "t": t, "e": round(e / scl, 10), "sl": round(stop / scl, 10), "tp": round(tp / scl, 10), "hs": round(hs / scl, 10),
                    "x": int(T[i + 1 + kx]), "xp": round(float(ex) / scl, 10), "r": round(float(xlab[j]), 3), "k": kind})
    print("prv", len(res), "R mismatches", bad, flush=True)
    return res


if __name__ == "__main__":
    OUT["rbx"] = rbx_trades()
    OUT["prv"] = prv_trades() if "noprv" not in sys.argv else []
    json.dump(OUT, open(f"{D}/vp_bt_trades.json", "w"), separators=(",", ":"))
    print("KB", os.path.getsize(f"{D}/vp_bt_trades.json") // 1024)
