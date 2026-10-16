# the bot-side feature code (zm_bot.py) on the raw candles must reproduce the research table
import math, os, threading, bisect, numpy as np, pandas as pd, random
from common import V, load, D
ns = {"math": math, "os": os, "threading": threading, "__file__": "x.py"}
exec(open(f"{D}/zm_bot.py").read(), ns)
import pyarrow.parquet as pq
from mk import feats
cols = pq.ParquetFile(f"{D}/all.parquet").schema.names
keep = [c for c in cols if c.split("_")[0] not in ("L", "C", "G")]
d = pd.read_parquet(f"{D}/all.parquet", columns=keep)
F = feats(d)
random.seed(1)
btc = load("BTCUSDT"); bt = [c["time"] for c in btc]; bd = V._oc_agg(btc, 24); bdt = [c["time"] for c in bd]
btc_ser = V._oc_btc_series(btc)
worst = 0
for sym in ("SOLUSDT", "DOGEUSDT", "1000PEPEUSDT"):
    cs = load(sym); d1_all = V._oc_agg(cs, 24); dt_ = [c["time"] for c in d1_all]
    sub = d[d.sym == sym]
    for i in random.sample(sorted(set(sub.i.values)), 15):
        rows = sub[sub.i == i]
        t = cs[i]["time"]
        h1 = cs[max(0, i - 480):i]
        kd = bisect.bisect_right(dt_, t - 86400); d1 = d1_all[max(0, kd - 400):kd]
        kb = bisect.bisect_left(bt, t); bh1 = btc[max(0, kb - 480):kb]
        kbd = bisect.bisect_right(bdt, t - 86400); bd1 = bd[max(0, kbd - 400):kbd]
        # the bot: candidates from the 1h / 4h / 1d bars it fetches (here aggregated from 1h, as Gate draws them)
        by_tf = [(h, V._oc_agg(cs[max(0, i - h * (n + 1)):i], h)[-n:]) for h, n in V.OC_TF_BARS]
        cands = V.oc_candidates_mtf(by_tf)
        sf = ns["zm_snap_feats"](h1, d1, bh1, bd1)
        bv = V._oc_btc_ctx(btc_ser, t)
        for c in cands:
            x = [round(v, 5) for v in V._oc_vec(c, V.oc_ctx_feats(h1, c, bv))]
            cf = ns["zm_cand_feats"](c, h1, d1, sf, cands)
            vec = dict(zip(list(V._OWN_FEATS) + list(V._OC_CTX_FEATS), x)); vec.update(cf)
            r = rows[(rows.side_s == c["side"]) & (np.isclose(rows.lo, c["lo"], rtol=1e-6)) & (np.isclose(rows.hi, c["hi"], rtol=1e-6))]
            if not len(r):
                print("candidate not in table", sym, i, c["side"], c["lo"]); continue
            a = np.array([vec[f] for f in F], dtype=np.float64); b = r[F].values[0].astype(np.float64)
            diff = np.abs(a - b) / (1 + np.abs(b))
            if diff.max() > 1e-3:
                j = int(diff.argmax()); print("DIFF", sym, i, F[j], a[j], b[j])
            worst = max(worst, diff.max())
print("worst relative diff", worst)
