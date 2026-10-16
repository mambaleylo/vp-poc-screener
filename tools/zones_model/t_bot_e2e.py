import sys, json, types, time as _time, numpy as np, pandas as pd, lightgbm as lgb, random
from common import V as vp, load, D
from mk import feats, ts
from lgbpure import export
import pyarrow.parquet as pq
LAB = "G_1.0_R3.0"
cols = pq.ParquetFile(f"{D}/all.parquet").schema.names
d = pd.read_parquet(f"{D}/all.parquet", columns=[c for c in cols if c.split("_")[0] not in ("L", "C", "G")] + [LAB])
F = feats(d)
X = d[F].values.astype(np.float32)
y = np.nan_to_num(d[LAB].values, nan=0).clip(-1.2, 6)
idx = np.random.RandomState(0).choice(len(X), 150000, replace=False)
mdl = lgb.LGBMRegressor(n_estimators=150, learning_rate=0.05, num_leaves=15, min_child_samples=500, verbose=-1, n_jobs=4).fit(X[idx], y[idx])
mjs = {"ver": vp.ZM_MODEL_VER, "rule": {"buf_datr": 1.0, "tp_r": 3.0}, "feats": F, "models": [export(mdl.booster_, F)["trees"]], "thr": -100.0}
json.dump(mjs, open(f"{D}/test_model.json", "w"))
vp.ZM_MODEL_FILE = f"{D}/test_model.json"
vp._ZM["model"] = None
# ---- the exchange replaced by Binance history
CS = {}
def bars(sym, tf):
    k = (sym, tf)
    if k not in CS:
        h1 = load(sym.replace("_", ""))
        CS[k] = h1 if tf == "1h" else vp._oc_agg(h1, {"4h": 4, "1d": 24, "15m": 1, "1m": 1}[tf])
    return CS[k]
def fake_range(sym, tf, a, b):
    return [c for c in bars(sym, tf) if a <= c["time"] <= b]
vp.get_candles_range = fake_range
NOW = [0]
vp.time = types.SimpleNamespace(**{k: getattr(_time, k) for k in ("sleep", "strftime", "gmtime", "localtime", "monotonic", "perf_counter")}, time=lambda: NOW[0])
vp.zones_save = lambda *a, **k: None
msgs = []
vp.zones_notify = lambda t, **k: msgs.append(t)
vp.notify_trade_result = lambda *a, **k: msgs.append(("result", a))
random.seed(5)
checked = bad = 0
for sym in ("SOLUSDT", "LINKUSDT", "DOGEUSDT"):
    gsym = sym.replace("USDT", "_USDT")
    vp._own_top_syms = lambda n=None, g=gsym: [g]
    sub = d[d.sym == sym]
    for i in random.sample(sorted(set(sub.i.values)), 4):
        rows = sub[sub.i == i]
        T0 = int(rows.t.iloc[0])
        NOW[0] = T0
        vp.ZONES["zones"] = []
        vp.zm_scan_once()
        zs = [z for z in vp.ZONES["zones"] if z.get("zm")]
        pr = mdl.predict(rows[F].values.astype(np.float32))
        for z in zs:
            r_side = rows[rows.side_s == z["side"]]
            p_side = pr[(rows.side_s == z["side"]).values]
            j = int(np.argmax(p_side))
            exp_sc, exp_lab = float(p_side[j]), r_side[LAB].values[j]
            ok_sc = abs(exp_sc - z["zm_score"]) < 0.01
            # ---- the ladder replayed by the bot's own monitor code
            p = vp.zones_params()
            for step in range(15 * 24):
                NOW[0] = T0 + step * 3600 + 3599
                c_last = [c for c in bars(gsym, "1h") if c["time"] + 3600 <= NOW[0]][-1]
                vp._zones_ladder_tick([z], NOW[0], p, {"_px": {gsym: c_last["close"]}, "_ax": {}})
                if (z.get("trade") or {}).get("status") not in ("PENDING", "OPEN"):
                    break
            tr = z["trade"]
            got = tr.get("pnl_r")
            exp = None if exp_lab != exp_lab else float(exp_lab)
            ok_r = (got is None and exp is None) or (got is not None and exp is not None and abs(got - exp) < 0.05)
            checked += 1
            if not (ok_sc and ok_r):
                bad += 1
            print(f"{sym} {z['side']:5s} score bot {z['zm_score']:+.3f} research {exp_sc:+.3f} | R bot {got} research {exp} {tr['status']} {tr.get('result')} {'OK' if ok_sc and ok_r else 'MISMATCH'}")
print("checked", checked, "mismatches", bad)
print("messages sample:", [m for m in msgs if isinstance(m, str)][:2])
