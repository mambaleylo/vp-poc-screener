"""the order churn of the bot's ⚡ arming on Binance's 1-min candles (the user: "проверяем всё" — does the new arming at
0.6 / off at 1.0 ATR with the room by the score put and pull the limits too often for Binance's limits?): the busiest
days of 2025-11 .. 2026-09 (the most ⚡ orders alive at once, dlm_allorders.py), every alive order minute by minute as
_dlm_arm does it (the bot polls every 5 s — a minute's high / low stand for its polls): armed when within ARM ATR (its
limit + the stop + the take: 3 orders), off when a minute closes beyond DIS ATR (3 cancels + an order query), one limit a
coin (a nearer one by 0.25 ATR swaps), at most 20 armed (the priority rule: a higher one bumps the lowest). The requests
a minute / an hour vs Binance's limits (orders 1200 a minute / 300 in 10 s, request weight 2400 a minute).
usage: churn_1m.py [N_DAYS] -> the table"""
import sys, os, io, zipfile, json, numpy as np, urllib.request, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_multi as M
ND = int(sys.argv[1]) if len(sys.argv) > 1 else 3
CACHE = os.environ.get("M1CACHE", "/tmp/claude-0/-home-user-vp-poc-screener/591d3753-67a7-5ebe-97a8-1553972a4a6c/scratchpad/m1")
URL = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/klines/{s}/1m/{s}-1m-{m}.zip"
def m1(sym, month):
    fn = os.path.join(CACHE, f"{sym}-{month}.npy")
    if os.path.exists(fn): return np.load(fn)
    try:
        raw = urllib.request.urlopen(URL.format(s=sym, m=month), timeout=90).read()
    except Exception as e:
        np.save(fn, np.zeros((0, 5))); return np.zeros((0, 5))
    z = zipfile.ZipFile(io.BytesIO(raw)); txt = z.read(z.namelist()[0]).decode().splitlines()
    a = np.array([l.split(",")[:5] for l in txt if l and l[0].isdigit()], float); a[:, 0] //= 1000; np.save(fn, a); return a
O = []
for st in ("wick4h", "close2h"):
    z0 = np.load(f"{M.ST}/wf/allorders_{st}.npz", allow_pickle=True); z = {k: z0[k] for k in z0.files}; bs = 14400 if st == "wick4h" else 7200
    for k in np.flatnonzero((z["t"] >= M.ts(2025, 11)) & (z["t"] < M.ts(2026, 10))):
        O.append({"coin": str(z["coin"][k]), "t": int(z["t"][k]), "until": int(z["t"][k]) + 4 * bs, "side": int(z["side"][k]), "lv": float(z["lv"][k]),
                  "atr": float(z["atr"][k]), "prio": float(z["score"][k]) / float(z["thr"][k]),
                  "tout": int(z["tout"][k]) if z["filled"][k] else 0})
days = collections.Counter()
for o in O:
    for d in range(o["t"] // 86400, o["until"] // 86400 + 1): days[d] += 1
busy = [d for d, _ in days.most_common(ND)]
print("the busiest days:", [str(np.datetime64(d * 86400, "s").astype("datetime64[D]")) + f" ({days[d]} orders)" for d in busy], flush=True)
RULES = {"сейчас (0.6 / 1.0, приоритет)": (0.6, 1.0, True), "до v0.99.753 (1.0 / 1.6)": (1.0, 1.6, False)}
for d in busy:
    A, B = d * 86400, (d + 1) * 86400
    act = [o for o in O if o["t"] < B and o["until"] > A]
    data = {}
    for c in {o["coin"] for o in act}:
        month = str(np.datetime64(A, "s").astype("datetime64[M]")); a = m1(c, month)
        if len(a): data[c] = {int(r[0]): r for r in a if A <= r[0] < B}
    print(f"== {np.datetime64(A, 's').astype('datetime64[D]')}: orders {len(act)}, coins with 1m {len(data)}", flush=True)
    for nm, (ARM, DIS, PRIO) in RULES.items():
        armed = {}; done = set(); pos = {}; ev = collections.Counter(); per_min = []   # pos: the coin -> the position's end
        for mt in range(A, B, 60):
            req = 0
            for c in [c for c, e in pos.items() if e <= mt]: del pos[c]
            for i in [i for i in armed if mt >= act[i]["until"]]: del armed[i]; req += 4; ev["снятие (срок)"] += 1
            want = []
            for i, o in enumerate(act):
                if i in done or not (o["t"] <= mt < o["until"]): continue
                r = data.get(o["coin"], {}).get(mt)
                if r is None: continue
                s, lv, a_ = o["side"], o["lv"], o["atr"]; hi, lo, cl = r[2], r[3], r[4]
                near = ((lo - lv) if s > 0 else (lv - hi)) / a_ <= ARM; touch = (lo <= lv) if s > 0 else (hi >= lv); far = s * (cl - lv) / a_ > DIS
                if i in armed:
                    if touch:
                        del armed[i]; done.add(i); ev["исполнение"] += 1; req += 2; pos[o["coin"]] = max(o["tout"], mt + 3600)
                    elif far: del armed[i]; req += 4; ev["снятие (ушла цена)"] += 1
                    continue
                if near and o["coin"] not in pos: want.append((i, touch, s * (cl - lv) / a_, cl))
            want.sort(key=(lambda w: -act[w[0]]["prio"]) if PRIO else (lambda w: w[2]))   # the bot: by the priority (now) / the distance (before)
            for i, touch, di, cl in want:
                o = act[i]
                if i in armed or o["coin"] in pos: continue
                same = [j for j in armed if act[j]["coin"] == o["coin"]]
                if same:
                    j = same[0]; dj = act[j]["side"] * (cl - act[j]["lv"]) / act[j]["atr"]
                    if dj > di + 0.25: del armed[j]; req += 4; ev["замена ближней"] += 1
                    else: continue
                if len(armed) + len(pos) >= 20:
                    if not PRIO or not armed: continue
                    low = min(armed, key=lambda j: act[j]["prio"])
                    if act[low]["prio"] >= o["prio"]: continue
                    del armed[low]; req += 4; ev["вытеснение"] += 1
                armed[i] = 1; req += 4; ev["выставление"] += 1   # the limit + the stop + the take + the leverage
                if touch:
                    del armed[i]; done.add(i); ev["исполнение"] += 1; req += 2; pos[o["coin"]] = max(o["tout"], mt + 3600)
            per_min.append(req)
        pm = np.array(per_min)
        print(f"   {nm:30s} запросов за день {pm.sum():5d}, в минуту: среднее {pm.mean():.1f}, максимум {pm.max()}, 99% {np.percentile(pm, 99):.0f} | "
              + ", ".join(f"{k} {v}" for k, v in ev.most_common()), flush=True)
print("churn done", flush=True)
