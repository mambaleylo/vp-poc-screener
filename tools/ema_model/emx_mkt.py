"""📐 EMA v0.99.667 rule, the user: "исполнять по рынку: проверку на Binance, исполнение у нас". The deep limit is only
watched on Binance (the touch hour's 1-min candles, data.binance.vision); when a 1-min low reaches it, the trade is opened
at the market on Gate — taken here as Binance's close of that minute (+ lag minutes). The stop / take / partial stay at the
plan's prices; R per the real risk (entry - stop). Bot's set (q 0.97) and the check set (q 0.90), 2022-26."""
import os, io, zipfile, urllib.request, datetime as dt, numpy as np, pandas as pd, concurrent.futures as cf
import ema_h as E
from ema_core import outcomes
import mfeat
from wr_eval import stats
from mk import ts
d = E.d; side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
LS = mfeat.at(d.sym.values, E.T - 3600)[:, mfeat.NAMES.index("ls_d24")] * side
base = (side > 0) & (e200 < 10) & (tf != "4h") & (bema > 0) & ~(LS < 0.00314)
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
def walk(O, H, L, C, j, s, e, sl, tp, pt, mins, k0):
    """from minute k0 of the touch hour (1-min bars `mins`), then the 1h bars from j+1; 72 h; the stop first, the partial
    1/3 at pt -> the stop to e, the take; R per (e - sl)"""
    risk = s * (e - sl); st = sl; took = False
    if risk <= 0: return None
    def step(lo, hi, op, first):
        nonlocal st, took
        if (s > 0 and lo <= st) or (s < 0 and hi >= st):
            return ("stop", op if (not first and ((s > 0 and op <= st) or (s < 0 and op >= st))) else st)
        if not took and ((s > 0 and hi >= pt) or (s < 0 and lo <= pt)): took = True; st = e
        if (s > 0 and hi >= tp) or (s < 0 and lo <= tp): return ("take", tp)
        return None
    res = None; hours = 1
    for q in range(k0 + 1, len(mins)):
        res = step(mins[q, 3], mins[q, 2], mins[q, 1], False)
        if res: break
    b = j + 1
    while res is None and b < min(len(C), j + 72):
        res = step(L[b], H[b], O[b], False); hours += 1
        if res is None: b += 1
    if res is None: res = ("time", C[min(len(C) - 1, j + 71)])
    ex = res[1]; rest = s * (ex - e) / risk
    pr = s * (pt - e) / risk
    fee = (0.001 + 0.0003 * hours / 24) * e / risk
    return ((0.33 * pr + 0.67 * rest) if took else rest) - fee
def run(q, lag):
    idx = E.cand(q, base); R, K, KD = outcomes(idx, deep=0.2); tr = E.replay(idx, R, K)
    out = []
    for i in tr:
        sym = d.sym.values[i]; s = int(side[i]); dr = float(d.datr.values[i]); j = int(d.j.values[i]); t0 = int(E.T[i])
        fill = float(d.lv.values[i]) * (1 - s * 0.2 * dr / 100); risk0 = fill * 0.75 * dr / 100
        sl, tp, pt = fill - s * risk0, fill + s * 4 * risk0, fill + s * risk0
        if lag is None: out.append((t0, t0 + int(K[i]) * 3600, float(R[i]), s, int(i))); continue
        day = dt.datetime.utcfromtimestamp(t0).strftime("%Y-%m-%d"); a = m1(sym, day)
        if not len(a): continue
        mins = a[(a[:, 0] >= t0) & (a[:, 0] < t0 + 3600)]
        hit = np.where((mins[:, 3] <= fill) if s > 0 else (mins[:, 2] >= fill))[0]
        if not len(hit): continue
        k0 = min(len(mins) - 1, int(hit[0]) + lag); e = mins[k0, 4]
        O, H, L, C = E.bars(sym)
        r = walk(O, H, L, C, j, s, e, sl, tp, pt, mins, k0)
        if r is not None: out.append((t0, t0 + int(K[i]) * 3600, float(r), s, int(i)))
    return out
if __name__ == "__main__":
    # prefetch the days in parallel
    need = set()
    for q in (0.97, 0.90):
        idx = E.cand(q, base); R, K, KD = outcomes(idx, deep=0.2)
        for i in E.replay(idx, R, K): need.add((d.sym.values[i], dt.datetime.utcfromtimestamp(int(E.T[i])).strftime("%Y-%m-%d")))
    with cf.ThreadPoolExecutor(24) as ex: list(ex.map(lambda x: m1(*x), sorted(need)))
    print("1m days", len(need), flush=True)
    for q, nm, tg in ((0.97, "бот", 0.45), (0.90, "проверка", 0.50)):
        print(f"\n=== EMA {nm} q{q}", flush=True)
        for lab, lag in (("лимитка (бэктест)", None), ("по рынку: закрытие минуты касания", 0), ("по рынку, +1 мин", 1), ("по рынку, +2 мин", 2), ("по рынку, +5 мин", 5)):
            stats(lab, run(q, lag), ts(2022), tg)
