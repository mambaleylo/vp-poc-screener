"""H17 — a module for the quiet market (the user: "1 попробуй"; the five modules besides ⚡ trade on the crash days only): fade
the edge of a narrow sideways range. On a coin's 1h candles: the calm regime — the Bollinger width (20) in the lowest q of its last
30 days AND the efficiency ratio of 48 h below er (no trend); the signal — a close beyond the band (2 sd) -> against it at the next
open; the stop s ATR(14) from the entry, the take at the band's middle (or 1 ATR), out after T bars; one trade a coin at a time;
0.10% round trip. The variants are chosen on the trades to 2024-12-31 and shown on 2025-01 .. 2026-11 (never seen by the choice).
usage: python3 h17_range.py out.json"""
import os, sys, gzip, json, glob, time, itertools, numpy as np, pandas as pd
from concurrent.futures import ProcessPoolExecutor
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); FEE = 0.0010
T_START, T_SPLIT = 1640995200, 1735689600   # 2022-01-01, 2025-01-01
GRID = list(itertools.product((1.0, 1.5, 2.0), ("mid", "atr"), (0.3, 0.5), (12, 24), (0.15, 0.25)))   # stop ATR, take, width quantile, bars, ER


def coin(sym):
    fn = f"{ST}/data/1h/{sym}.csv.gz"
    try:
        a = np.array([ln.split(",")[:5] for ln in gzip.open(fn, "rt").read().splitlines()], dtype=float)
    except Exception:
        return sym, {}
    a = a[a[:, 0] >= T_START - 60 * 86400]
    if len(a) < 3000:
        return sym, {}
    t, o, h, l, c = a.T; n = len(c)
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    atr = pd.Series(tr).rolling(14).mean().values
    mid = pd.Series(c).rolling(20).mean().values; sd = pd.Series(c).rolling(20).std(ddof=0).values
    bw = pd.Series(4 * sd / mid)
    er = (pd.Series(c).diff(48).abs() / pd.Series(c).diff().abs().rolling(48).sum()).values
    out = {}
    for q in (0.3, 0.5):
        calm_w = (bw <= bw.rolling(720).quantile(q)).values
        for e in (0.15, 0.25):
            calm = calm_w & (er < e)
            lo = calm & (c < mid - 2 * sd); hi = calm & (c > mid + 2 * sd)
            sig = np.where(lo, 1, np.where(hi, -1, 0))
            for s, tk, T in itertools.product((1.0, 1.5, 2.0), ("mid", "atr"), (12, 24)):
                res = []; i = 800
                while i < n - 1:
                    d = sig[i]
                    if not d or not np.isfinite(atr[i]) or atr[i] <= 0 or t[i] < T_START:
                        i += 1; continue
                    en = o[i + 1]; risk = s * atr[i]
                    tp = mid[i] if tk == "mid" else en + d * atr[i]
                    if d * (tp - en) < 0.3 * atr[i]:   # nothing to take
                        i += 1; continue
                    sl = en - d * risk; ex = None; j = i + 1
                    while j < min(n, i + 1 + T):
                        if (l[j] <= sl) if d > 0 else (h[j] >= sl):
                            ex = sl; break
                        if (h[j] >= tp) if d > 0 else (l[j] <= tp):
                            ex = tp; break
                        j += 1
                    if ex is None:
                        j = min(n - 1, i + T); ex = c[j]
                    res.append((int(t[i + 1]), int(d), round((d * (ex - en) - FEE * en) / risk, 4), round(risk / en * 100, 3)))
                    i = j + 1
                out[(s, tk, q, T, e)] = res
    return sym, out


if __name__ == "__main__":
    syms = sorted(os.path.basename(f)[:-7] for f in glob.glob(f"{ST}/data/1h/*.csv.gz"))
    sp = json.load(open("lv/split.json")); syms = [s for s in syms if s in set(sp["bot"]) | set(sp["chk"])]
    t0 = time.time(); allr = {g: [] for g in GRID}
    with ProcessPoolExecutor(4) as ex:
        for sym, out in ex.map(coin, syms):
            for g, r in out.items():
                allr[g] += [(sym,) + x for x in r]
    rows = []
    for g, r in allr.items():
        a = [x for x in r if x[1] < T_SPLIT]; b = [x for x in r if x[1] >= T_SPLIT]
        st = lambda v: (len(v), round(float(np.mean([x[3] for x in v])), 4) if v else 0, round(100 * float(np.mean([x[3] > 0 for x in v])), 1) if v else 0)
        rows.append({"g": g, "design": st(a), "check": st(b), "risk_pct": round(float(np.median([x[4] for x in r])), 2) if r else 0})
    rows.sort(key=lambda x: -x["design"][1])
    json.dump({"rows": rows, "best": [list(x) for x in allr[rows[0]["g"]]], "coins": len(syms)}, open(sys.argv[1], "w"), default=float)
    print(f"монет {len(syms)}, {time.time() - t0:.0f}s")
    print("стоп ATR, тейк, квантиль ширины, баров, ER | подбор ≤2024: сделок, средний R, WR | проверка 2025–26: сделок, средний R, WR | стоп, % цены")
    for x in rows[:8] + rows[-3:]:
        print(x["g"], "|", x["design"], "|", x["check"], "|", x["risk_pct"])
    print("H17 done")
