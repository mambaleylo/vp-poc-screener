"""📏 HTF execution audit on Binance 1-min candles (data.binance.vision), every trade of the deployed rule (the OR of the
two models at q0.995, long only, the bot coins): the touch minute (low <= level x 0.999 = the bot's trigger), the entry
at the market — (a) the level (the research), (b) min(level x 0.999, that minute's close), (c) that minute's close (a
late poll; > 1R worse -> skipped, the bot's 'late' rule) — plus 0.05% spread / slippage on (b)/(c); the exits walked
minute by minute (the emergency stop 3R by a touch, the take 3R by a touch from the next minute, the soft stop at the
close of a 4h candle, out at 96 h): R vs the research's 1h walk"""
import os, io, zipfile, urllib.request, json, numpy as np, concurrent.futures as cf
from bt_trades import gate_sym
B1 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/daily/klines"
os.makedirs("data/1m", exist_ok=True)
def m1(sym, day):
    fn = f"data/1m/{sym}_{day}.npy"
    if os.path.exists(fn): return np.load(fn)
    try:
        with urllib.request.urlopen(f"{B1}/{sym}/1m/{sym}-1m-{day}.zip", timeout=60) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        rows = [l.split(",") for l in z.read(z.namelist()[0]).decode().splitlines() if l[:1].isdigit()]
        a = np.array([[int(x[0]) // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in rows])
    except Exception:
        a = np.zeros((0, 5))
    np.save(fn, a); return a
sp = json.load(open("lv/split.json")); INV = {}
for s in sp["bot"]:
    gs, scl = gate_sym(s); INV[gs] = (s, scl)
L = json.load(open("htfS_ИЛИ_q0.995.json"))
day = lambda t: np.datetime64(int(t), "s").astype("datetime64[D]").astype(str)
need = {(INV[x["s"]][0], day(t)) for x in L for t in range(x["t"], x["t"] + 97 * 3600, 86400)} | {(INV[x["s"]][0], day(x["t"] + 96 * 3600)) for x in L}
with cf.ThreadPoolExecutor(16) as ex:
    list(ex.map(lambda a: m1(*a), sorted(need)))
print("дней минуток", len(need), flush=True)
out = []
for x in L:
    sym, scl = INV[x["s"]]
    lv, sl, hs = x["e"] * scl, x["sl"] * scl, x["hs"] * scl; risk = lv - sl; tp = lv + 3 * risk
    days = sorted({day(t) for t in range(x["t"], x["t"] + 97 * 3600, 86400)} | {day(x["t"] + 96 * 3600)})
    a = np.concatenate([m1(sym, d) for d in days]) if days else np.zeros((0, 5))
    if len(a) == 0: out.append(None); continue
    a = a[(a[:, 0] >= x["t"]) & (a[:, 0] < x["t"] + 96 * 3600)]
    T, O, H, Lo, C = a.T
    hr = np.flatnonzero((T < x["t"] + 3600) & (Lo <= lv * 0.999))
    if not len(hr): out.append(("nofill", x["r"])); continue
    m = int(hr[0])
    fills = {"a": lv, "b": min(lv * 0.999, C[m]) * 1.0005, "c": C[m] * 1.0005}
    res = {"r1h": x["r"]}
    for k_, f in fills.items():
        if k_ == "c" and f - lv > risk: res[k_] = None; continue
        ex_, kk = None, None
        for i in range(m, len(T)):
            if Lo[i] <= hs:
                ex_ = O[i] if (i > m and O[i] <= hs) else hs; kk = i; break
            if i > m and H[i] >= tp:
                ex_ = tp; kk = i; break
            if (T[i] + 60) % 14400 == 0 and C[i] <= sl:
                ex_ = C[i]; kk = i; break
        if ex_ is None: kk = len(T) - 1; ex_ = C[kk]
        hrs = (T[kk] - x["t"]) / 3600 + 1
        res[k_] = (ex_ - f) / risk - (0.001 + 0.0003 * hrs / 24) * f / risk
    res["slip_b"] = (fills["b"] - lv) / risk; res["slip_c"] = (fills["c"] - lv) / risk
    res["min_in_hour"] = int((T[m] - x["t"]) // 60); res["y"] = int(np.datetime64(int(x["t"]), "s").astype("datetime64[Y]").astype(int) + 1970)
    out.append(res)
ok = [o for o in out if isinstance(o, dict)]
print("сделок", len(L), "проверено на минутках", len(ok), "нет минуток", sum(o is None for o in out), "минутки не подтвердили вход", sum(isinstance(o, tuple) for o in out))
for k_ in ("r1h", "a", "b", "c"):
    v = np.array([o[k_] for o in ok if o.get(k_) is not None])
    print(f"  {k_:4s} n{len(v)} ср.R {v.mean():+.3f} WR {(v > 0).mean()*100:.0f}% | " + " ".join(f"{Y % 100}:{np.mean([o[k_] for o in ok if o['y'] == Y and o.get(k_) is not None]):+.2f}" for Y in range(2023, 2027)))
print("  поздних (c хуже на >1R, пропуск):", sum(o["c"] is None for o in ok))
sb = np.array([o["slip_b"] for o in ok]); sc = np.array([o["slip_c"] for o in ok])
print(f"  проскальзывание входа в R: (b) медиана {np.median(sb):+.3f} | (c) медиана {np.median(sc):+.3f}, 90% {np.percentile(sc, 90):+.3f}, макс {sc.max():+.3f}")
d = np.array([o["a"] - o["r1h"] for o in ok])
print(f"  выход по минуткам минус по часам (вход = уровень): ср {d.mean():+.3f}R, медиана {np.median(d):+.3f}, сделок где |разн|>0.1R: {(np.abs(d) > 0.1).sum()}")
