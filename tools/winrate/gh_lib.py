"""GitHub indicators as filters on the deployed modules' trades: at each trade's entry, the states of the indicators on the
last CLOSED 4h and 1d bars (aligned to the trade's side); then each state's buckets -> avg R by year"""
import json, os, numpy as np, warnings; warnings.filterwarnings("ignore")
from common import load
from ev2_engine import agg
import ev4_engine as E
from ev3_engine import ema_, atr_, rmax, rmin, rsi_
B = json.load(open("vp_bt_trades.json"))
def dname(s):
    b = s.replace("_USDT", "USDT").replace("_", "")
    for c in (b, "1000" + b, b.replace("1000", "")):
        if os.path.exists(f"data/1h/{c}.csv"): return c
    return None
def states(O, H, L, C, V):
    n = len(C); prev = lambda x: np.concatenate([[x[0]], x[:-1]]); out = {}
    atr = atr_(H, L, C)
    st = E.ut_trail(C, atr_(H, L, C, 10), 2.0); out["ut"] = np.sign(C - st)
    sh, sl = E.sma_(H, 10), E.sma_(L, 10); hlv = np.zeros(n)
    for i in range(1, n): hlv[i] = 1 if C[i] > sh[i] else (-1 if C[i] < sl[i] else hlv[i - 1])
    out["ssl"] = hlv
    ap = (H + L + C) / 3; esa = ema_(ap, 10); d = ema_(np.abs(ap - esa), 10)
    wt1 = ema_((ap - esa) / np.maximum(0.015 * d, 1e-12), 21); out["wt"] = wt1; out["wt_x"] = wt1 - E.sma_(wt1, 4)
    bm = E.sma_(C, 20); bs = E.rstd_(C, 20); tr_ = atr_(H, L, C, 20)
    out["sqz"] = (((bm + 2 * bs) < (bm + 1.5 * tr_)) & ((bm - 2 * bs) > (bm - 1.5 * tr_))).astype(float)
    out["bbpos"] = (C - bm) / np.maximum(2 * bs, 1e-12)
    out["chand"] = E.chandelier(H, L, C, atr_(H, L, C, 22), 22, 3.0)
    hc = rmax(C, 22); wvf = (hc - L) / hc * 100; out["wvf"] = wvf / np.maximum(E.sma_(wvf, 20) + 2 * E.rstd_(wvf, 20), 1e-12)
    lc = rmin(C, 22); iw = (H - lc) / lc * 100; out["iwvf"] = iw / np.maximum(E.sma_(iw, 20) + 2 * E.rstd_(iw, 20), 1e-12)
    c4 = np.concatenate([np.full(4, np.nan), C[:-4]]); td = np.zeros(n)
    for i in range(4, n): td[i] = (td[i - 1] + 1 if td[i - 1] > 0 else 1) if C[i] < c4[i] else ((td[i - 1] - 1 if td[i - 1] < 0 else -1) if C[i] > c4[i] else 0)
    out["td"] = td   # + = down count (bullish exhaustion)
    r3 = rsi_(C, 3); out["rsi3"] = r3
    out["ewo"] = (ema_(C, 5) - ema_(C, 35)) / C * 100
    out["fisher"] = E.fisher(H, L, 9)
    hm = E.wma_(2 * E.wma_(C, 27) - E.wma_(C, 55), 7); out["hma"] = np.sign(hm - prev(hm))
    rs = ema_(rsi_(C, 14), 5); dar = ema_(ema_(np.abs(rs - prev(rs)), 27), 27) * 4.236; out["qqe"] = np.sign(rs - E.qqe_line(rs, dar))
    return out
SIGNED = {"ut", "ssl", "chand", "hma", "qqe", "wt", "wt_x", "bbpos", "ewo", "fisher"}   # x side: + = with the trade
cache = {}
def coin(sym):
    if sym in cache: return cache[sym]
    a = load(sym); T = np.array([c["time"] for c in a]); O, H, L, C, V = (np.array([c[k] for c in a]) for k in ("open", "high", "low", "close", "volume"))
    res = {}
    for tf, sec in (("4h", 14400), ("1d", 86400)):
        g = agg(T // sec, O, H, L, C); st, en = g[5], g[6]
        cv = np.cumsum(np.insert(V, 0, 0.0))
        endt = T[en - 1] + 3600   # the bar's close time
        full = (en - st) == sec // 3600
        res[tf] = (endt[full], states(g[1][full], g[2][full], g[3][full], g[4][full], (cv[en] - cv[st])[full]))
    cache[sym] = res; return res
