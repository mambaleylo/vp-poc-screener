"""how many ⚡ fills the bot would miss with the limit armed DLM_ARM_ATR from the price (the bot polls every 5 s; a level
reached and left inside one poll gap is not caught): on Binance's 1-min candles of a sample of the filled orders (2025-11 ..
2026-10, dlm_allorders.py), the first minute within ARM of the level that also reaches the level, opening farther than ARM,
closing back above it (long; mirrored for a short) — a wick through and back within a minute -> "likely missed". Also the
ones that close through the level by more than DLM_THROUGH_ATR (0.3, the bot gives those up). usage: arm_miss1m.py [N]"""
import sys, os, io, zipfile, json, numpy as np, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_multi as M
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
CACHE = os.environ.get("M1CACHE", "/tmp/claude-0/-home-user-vp-poc-screener/591d3753-67a7-5ebe-97a8-1553972a4a6c/scratchpad/m1")
os.makedirs(CACHE, exist_ok=True)
URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/klines/{s}/1m/{s}-1m-{m}.zip"
def m1(sym, month):
    fn = os.path.join(CACHE, f"{sym}-{month}.npy")
    if os.path.exists(fn): return np.load(fn)
    try:
        raw = urllib.request.urlopen(URL.format(s=sym, m=month), timeout=60).read()
    except Exception as e:
        print("no 1m", sym, month, e); np.save(fn, np.zeros((0, 5))); return np.zeros((0, 5))
    z = zipfile.ZipFile(io.BytesIO(raw)); txt = z.read(z.namelist()[0]).decode().splitlines()
    rows = [l.split(",")[:5] for l in txt if l and l[0].isdigit()]
    a = np.array(rows, float); a[:, 0] //= 1000; np.save(fn, a); return a
rng = np.random.default_rng(3)
O = []
for st in ("wick4h", "close2h"):
    z0 = np.load(f"{M.ST}/wf/allorders_{st}.npz", allow_pickle=True); z = {k: z0[k] for k in z0.files}
    ii = np.flatnonzero(z["filled"] & (z["t1h"] >= 1761955200) & (z["t1h"] < 1793491200))
    for k in rng.choice(ii, N // 2, replace=False):
        O.append({k_: (z[k_][k].item() if hasattr(z[k_][k], "item") else z[k_][k]) for k_ in ("coin", "t", "side", "lv", "atr", "t1h", "R")} | {"st": st})
ARMS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0)
res = {x: [0, 0] for x in ARMS}; n = 0; per = []
for o in O:
    month = str(np.datetime64(int(o["t1h"]), "s").astype("datetime64[M]"))
    a = m1(o["coin"], month)
    if not len(a): continue
    w = a[(a[:, 0] >= o["t"]) & (a[:, 0] < o["t1h"] + 3600)]
    if not len(w): continue
    s, lv, at = o["side"], o["lv"], o["atr"]
    dist_lo = s * ((w[:, 3] if s > 0 else w[:, 2]) - lv) / at   # the minute's nearest point to the level (<= 0: reached)
    dist_op = s * (w[:, 1] - lv) / at; dist_cl = s * (w[:, 4] - lv) / at
    t = np.flatnonzero(dist_lo <= 0)
    if not len(t): continue
    n += 1; t = t[0]; flags = {}
    for x in res:
        first_near = np.flatnonzero(dist_lo <= x)[0]
        if first_near == t and dist_op[t] > x:   # came from beyond the arming distance and reached the level in one minute
            if dist_cl[t] > 0: res[x][0] += 1; flags[x] = 1   # and closed back: a wick through and back — likely missed
            elif dist_cl[t] < -0.3: res[x][1] += 1; flags[x] = 2   # closed far through: the bot gives it up
    per.append({"coin": o["coin"], "t": int(o["t"]), "side": int(o["side"]), "st": o["st"], "R": float(o["R"]), "miss": {str(k): v for k, v in flags.items()}})
print(f"filled orders checked on 1m: {n}")
Rall = np.array([p_["R"] for p_ in per])
for x, (wk, far) in res.items():
    rm = [p_["R"] for p_ in per if str(x) in p_["miss"]]
    print(f"   armed at {x} ATR: a wick through and back in a minute {wk} ({wk / n * 100:.1f}%), > 0.3 ATR through {far} ({far / n * 100:.1f}%) | the missed ones' R {np.mean(rm) if rm else float('nan'):+.3f} (all {Rall.mean():+.3f})")
json.dump(per, open(f"{M.ST}/wf/arm_miss1m.json", "w"))
