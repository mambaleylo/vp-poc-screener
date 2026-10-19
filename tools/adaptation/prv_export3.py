"""Peak Reversal v3 (the adaptation study, ad_wf.py): the same rule (stop 1.5 ATR, take 3R, 48 bars, top 1% per side),
the model trained on the LAST 24 MONTHS only and retrained every quarter. The yearly stats = that scheme's
walk-forward (3 models per retrain, per quarter, 2023-01 .. 2026-09); the export = 3 models per side on the last 24
months, the threshold from the last 12 months' scores.
Ver 3 (v0.99.639): the model still learns the 1.5 ATR / 3R outcome, but the trades run with a stop of 3.0 ATR and the
take at the same place (4.5 ATR = 1.5R) — fewer losses and a smaller drawdown for a bit less profit (the user's choice).
The exit label comes from pr_lab2.py (prv_lab3.npz, "s30_t45").
v0.99.641 (ver 4): the stop by the CLOSE of the trade's bar at 3 ATR and a hard stop at 6 ATR on the exchange (75 of 110
stops were wicks that closed back); R per the hard stop (the sizing risk); the label from pr_lab_cs.py. And the BTC filter — no entry against a market move: a long when BTC fell more than BTCF % over the last 24 h,
a short when it rose more (the feature "b_r24"); a filtered signal takes no slot."""
import os, json, datetime as dt
SK, TK, Q, WIN, STEP = 1.5, 3.0, 0.99, 24, 3
XSK, XTK, XHS = 3.0, 1.5, 6.0   # the stop by close (ATR), the take (R of that stop), the hard stop (ATR)
BTCF = 4.0              # the BTC filter, % over 24 h against the trade
import numpy as np, lightgbm as lgb
from mk import ts
from lgbpure import export
import prv_wf as W
def month_add(t, k):
    d = dt.datetime.fromtimestamp(int(t), dt.timezone.utc)
    m = d.month - 1 + k
    return int(dt.datetime(d.year + m // 12, m % 12 + 1, 1, tzinfo=dt.timezone.utc).timestamp())
lab = W.lab_of(SK, TK)
xlab = np.load(f"{W.D}/prv_lab_cs.npz")["cs"].astype(float)
xlab = np.where(np.abs(xlab) > 20, np.nan, xlab)
GAP = 10 * 86400
def mdl(seed):
    return lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1,
                             colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=seed)
def fit3(tr_mask, s):
    ok = tr_mask & (W.SD == s) & ~np.isnan(lab)
    return [mdl(seed).fit(W.X[ok], lab[ok].clip(-1.5, TK + 1)) for seed in range(3)]
def score(ms, idx):
    return sum(m.predict(W.X[idx]) for m in ms) / len(ms)
if os.environ.get("WF", "1") == "1":
    sel = []
    t0, end = ts(2023), ts(2026, 10)
    while t0 < end:
        t1 = min(month_add(t0, STEP), end)
        tr = (W.T < t0 - GAP) & (W.T >= month_add(t0, -WIN) - GAP)
        ref = (W.T >= month_add(t0, -12) - GAP) & (W.T < t0 - GAP)
        te = (W.T >= t0) & (W.T < t1)
        for s in (1, -1):
            ms = fit3(tr, s)
            ri, ti = np.where(ref & (W.SD == s))[0], np.where(te & (W.SD == s))[0]
            thr = float(np.quantile(score(ms, ri), Q))
            ok_btc = W.SD[ti] * W.F["b_r24"][ti] > -BTCF
            sel.append(ti[(score(ms, ti) >= thr) & ok_btc])
        print("quarter", dt.datetime.fromtimestamp(t0, dt.timezone.utc).strftime("%Y-%m"), flush=True)
        t0 = t1
    out = sorted(W.replay(np.concatenate(sel), xlab))
    years = {}
    for y in (2023, 2024, 2025):
        rs = np.array([r for e, r in out if (ts(y) <= e < ts(y + 1)) or (y == 2025 and e >= ts(2026))])
        c = np.cumsum(rs); dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], c])) - np.concatenate([[0], c])))
        years[str(y)] = {"n": len(rs), "avg": round(float(rs.mean()), 3), "wk": round(len(rs) / W.wk(y), 1), "sum": round(float(rs.sum()), 1),
                         "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}
        print(y, years[str(y)], flush=True)
    json.dump(years, open(f"{W.D}/prv3_years.json", "w"))
years = json.load(open(f"{W.D}/prv3_years.json"))
tmax = int(W.T.max())
full = (W.T < tmax - GAP) & (W.T >= month_add(tmax, -WIN) - GAP)
last = W.T >= tmax - 365 * 86400
models, thr = {}, {}
for s in (1, -1):
    ms = fit3(full, s)
    models[str(s)] = [export(m.booster_, W.NAMES)["trees"] for m in ms]
    w = np.where(last & (W.SD == s))[0]
    thr[str(s)] = round(float(np.quantile(score(ms, w), Q)), 6)
    print("side", s, "thr", thr[str(s)], flush=True)
out = {"ver": 4, "kind": "prv_v3", "feats": W.NAMES, "models": models, "thr": thr, "q": Q, "basis": ["EMA", 20], "band": 1.5,
       "rule": {"stop_atr": XSK, "take_r": XTK, "hold_bars": 48, "hard_atr": XHS, "stop_close": True}, "label_rule": {"stop_atr": SK, "take_r": TK}, "btc_filter": BTCF, "side_cap": 12, "trained_to": tmax,
       "train": {"window_months": WIN, "retrain_months": STEP, "from": int(month_add(tmax, -WIN))},
       "research": {"coins": 127, "cap": 12, "q": Q, "years": years, "scheme": "окно 24 мес, переобучение раз в 3 мес"}}
json.dump(out, open(f"{W.D}/vp_prv_model.json", "w"), separators=(",", ":"))
print("KB", os.path.getsize(f"{W.D}/vp_prv_model.json") // 1024, flush=True)
