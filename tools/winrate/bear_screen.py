"""a bear-market module, the first screen (the user: модуль для медвежьего рынка — 2022 rested on ⚡ alone, the drawdown 88%):
simple daily rules on the bot's 210 coins (Binance 1h candles made into UTC days), the trades' R by year and in the bundle's
bad months: (A) short the 20-day low's break while BTC is below its daily EMA50 (out: a close above the 10-day high or 20
days; the risk 2 ATR(14)); (B) short the rally to the EMA20 in a downtrend (BTC and the coin below their EMA50, the day's high
reaches the EMA20, the close below it; stop 1.5 ATR, take 3R, 10 days); (C) the control — long the 20-day high's break
while BTC is above its EMA50. Fees 0.1% a trade + funding 0.03% a day. -> the table, <LABSTORE>/wf/bear_screen.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); C = json.load(open(f"{ST}/feat_coins.json"))
def daily(bsym):
    T, O, H, L, Cc, V = DE.load1h(bsym); d = T // 86400; u, i0 = np.unique(d, return_index=True); e = np.r_[i0[1:], len(T)]
    return u * 86400, O[i0], np.maximum.reduceat(H, i0), np.minimum.reduceat(L, i0), Cc[e - 1]
def ema(x, n):
    k = 2 / (n + 1); o = np.empty(len(x)); a = x[0]
    for i, v in enumerate(x): a += k * (v - a); o[i] = a
    return o
def atr(H, L, Cc, n=14):
    tr = np.maximum(H[1:] - L[1:], np.maximum(abs(H[1:] - Cc[:-1]), abs(L[1:] - Cc[:-1]))); tr = np.r_[H[0] - L[0], tr]
    o = np.full(len(tr), np.nan); a = tr[:n].mean(); o[n - 1] = a
    for i in range(n, len(tr)): a = (a * (n - 1) + tr[i]) / n; o[i] = a
    return o
BT, BO, BH, BL, BC = daily("BTCUSDT"); BE = ema(BC, 50); btc_dn = dict(zip(BT, BC < BE))
FEE, FUND = 0.001, 0.0003
def walk(T, O, H, L, Cc, i, s, risk, stop, take, hold, trail=None):
    """from day i+1's open: s the side; the stop / take in price; trail: the n-day opposite extreme's close exit"""
    e = O[i + 1]; sl = e - s * stop; tp = e + s * take if take else None
    for q in range(i + 1, min(len(T), i + 1 + hold)):
        if (s < 0 and H[q] >= sl) or (s > 0 and L[q] <= sl): x = sl; break
        if tp is not None and ((s < 0 and L[q] <= tp) or (s > 0 and H[q] >= tp)): x = tp; break
        if trail and q - trail >= 0:
            ref = H[q - trail:q].max() if s < 0 else L[q - trail:q].min()
            if (s < 0 and Cc[q] > ref) or (s > 0 and Cc[q] < ref): x = Cc[q]; break
    else:
        q = min(len(T), i + 1 + hold) - 1; x = Cc[q]
    days = q - i
    return (s * (x - e) - (FEE + FUND * days) * e) / risk, T[i + 1], T[q] + 86400
out = {"A": [], "B": [], "C": []}
for c in C["base"]:
    try: T, O, H, L, Cc = daily(c)
    except Exception: continue
    if len(T) < 120: continue
    A = atr(H, L, Cc); E20, E50 = ema(Cc, 20), ema(Cc, 50); busy = {"A": 0, "B": 0, "C": 0}
    for i in range(60, len(T) - 2):
        if not np.isfinite(A[i]): continue
        dn = btc_dn.get(T[i]);
        if dn is None: continue
        lo20, hi20 = L[i - 20:i].min(), H[i - 20:i].max()
        if dn and Cc[i] < lo20 and T[i] >= busy["A"]:
            r, t0, t1 = walk(T, O, H, L, Cc, i, -1, 2 * A[i], 2 * A[i], None, 20, trail=10); out["A"].append((c, int(t0), int(t1), float(r))); busy["A"] = t1
        if dn and Cc[i] < E50[i] and H[i] >= E20[i] > Cc[i] and T[i] >= busy["B"]:
            r, t0, t1 = walk(T, O, H, L, Cc, i, -1, 1.5 * A[i], 1.5 * A[i], 4.5 * A[i], 10); out["B"].append((c, int(t0), int(t1), float(r))); busy["B"] = t1
        if (not dn) and Cc[i] > hi20 and T[i] >= busy["C"]:
            r, t0, t1 = walk(T, O, H, L, Cc, i, 1, 2 * A[i], 2 * A[i], None, 20, trail=10); out["C"].append((c, int(t0), int(t1), float(r))); busy["C"] = t1
json.dump(out, open(f"{ST}/wf/bear_screen.json", "w"))
# the bundle's bad months: ⚡'s pool R a month (the walk-forward pool) as the proxy
P = json.load(open(f"{ST}/wf/pool_base.json")); pm = {}
for x in P: m_ = str(np.datetime64(x["t1h"], "s").astype("datetime64[M]")); pm[m_] = pm.get(m_, 0) + x["R"]
bad = sorted(pm, key=pm.get)[:8]
nm = {"A": "шорт пробоя 20-дн. минимума (BTC < EMA50)", "B": "шорт отскока к EMA20 в нисходящем тренде", "C": "контроль: лонг пробоя 20-дн. максимума"}
for k, v in out.items():
    r = np.array([x[3] for x in v]); y = np.array([int(np.datetime64(x[1], "s").astype("datetime64[Y]").astype(int) + 1970) for x in v])
    mo = np.array([str(np.datetime64(x[1], "s").astype("datetime64[M]")) for x in v])
    rb = r[np.isin(mo, bad)]
    print(f"{nm[k]}: {len(r)} сделок, {r.mean():+.3f}R, WR {(r > 0).mean() * 100:.0f}% | по годам " + " ".join(f"{yy}:{r[y == yy].mean():+.2f}({(y == yy).sum()})" for yy in range(2021, 2027) if (y == yy).any())
          + f" | в 8 худших месяцев ⚡: {len(rb)} сделок {rb.mean() if len(rb) else 0:+.3f}R, сумма {rb.sum():+.0f}R", flush=True)
print("худшие месяцы ⚡:", bad, flush=True)
print("bear done", flush=True)
