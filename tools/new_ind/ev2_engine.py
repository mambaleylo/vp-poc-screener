"""New indicator hunt, family 2: event triggers from the derivatives data and the cross-section (all on CLOSED 1h bars,
entry at the next hour's open by market):
  oi_flush   OI fell >= 4% in 4h while the price fell >= 1 daily ATR -> long (liquidations done); mirror -> short
  oi_squeeze OI fell >= 4% in 4h while the price rose >= 1 daily ATR -> short
  oi_pump    OI rose >= 10% in 4h with the price up/down >= 1 dATR -> fade (late crowd)
  crowd      long/short accounts ratio 30-day z >= 2.5 -> short; <= -2.5 -> long
  taker      taker buy/sell 24h mean z >= 3 -> short; <= -3 -> long
  funding    funding <= -0.05% -> long; >= 0.08% -> short
  resid      24h return minus beta x BTC's, z (60 days) >= 3 -> short; <= -3 -> long
  climax     hour volume >= 6x its 20-day mean, wick >= 55% of the range -> against the move
  smart      top traders' position ratio 3-day change z >= 2 while accounts' ratio z <= 0 -> long (mirror short)
One event per (family, side, coin) per 24 h. Exits: E0..E2 as lv_engine (daily ATR), E3 = the P/R style: stop 1.5 x
ATR(1h), take 3R, 48 h. Features: lv_engine's context + the event's own. Saved per coin to ev2/<SYM>.npz."""
import sys, os, time
ARGS = sys.argv[1:]
import numpy as np
from numba import njit
import lv_engine as LE
from lv_engine import load_np, agg, to_hours, wilder_atr, rsi, ema, simp
from common import D
import multiprocessing as mp

FAMS = ["oi_flush", "oi_squeeze", "oi_pump", "crowd", "taker", "funding", "resid", "climax", "smart"]
EXITS = LE.EXITS + ((1.0, 3.0, 48, 0.0, 0.0),)
FNAMES = ["fam", "side", "datr", "hour", "dow", "r4", "r24", "r72", "r7d", "b24", "b7d", "b_e50", "rsi_d", "rsi_h",
          "d_e50", "d_e200", "pos30", "pos90", "pos365", "vol24", "atr_h", "oi4", "oi24", "ls_z", "tk_z", "fund",
          "resid_z", "volx", "wick", "top_z", "ema_near"]
OUT = [f"{D}/ev2"]


def zs(x, n):
    """rolling z-score over the n values before i (i excluded)"""
    out = np.full(len(x), np.nan)
    c1 = np.cumsum(np.insert(np.nan_to_num(x), 0, 0.0)); c2 = np.cumsum(np.insert(np.nan_to_num(x) ** 2, 0, 0.0))
    for i in range(n, len(x)):
        m = (c1[i] - c1[i - n]) / n; v = (c2[i] - c2[i - n]) / n - m * m
        out[i] = (x[i] - m) / np.sqrt(v) if v > 1e-18 else 0.0
    return out


def metrics(sym, T):
    fn = f"{D}/data/metrics/{sym}.csv"
    out = {k: np.full(len(T), np.nan) for k in ("oi", "top_pos", "ls_acc", "taker")}
    if os.path.exists(fn):
        a = np.genfromtxt(fn, delimiter=",", names=True)
        if a.size > 10:
            t = a["t"].astype(np.int64); k = np.searchsorted(t, T)
            ok = (k < len(t)) & (t[np.minimum(k, len(t) - 1)] == T)
            for c in out:
                out[c][ok] = a[c][k[ok]]
    fnf = f"{D}/data/funding/{sym}.csv"
    fund = np.full(len(T), np.nan)
    if os.path.exists(fnf):
        f = np.loadtxt(fnf, delimiter=",", ndmin=2)
        if len(f):
            k = np.searchsorted(f[:, 0], T, side="right") - 1
            fund[k >= 0] = f[k[k >= 0], 1]
    out["fund"] = fund
    return out


@njit(cache=True)
def cooldown(J, S, Fm, T, gap):
    keep = np.zeros(len(J), np.bool_)
    last = {}
    for i in range(len(J)):
        key = Fm[i] * 2 + (S[i] > 0)
        if key in last and T[J[i]] - last[key] < gap:
            continue
        last[key] = T[J[i]]; keep[i] = True
    return keep


def ev2_events(c):
    for k_, v_ in c.items(): globals()[k_] = v_
    n = c['n']
    ev = []   # (j, fam, side): the event is seen at the close of hour j, entry at the open of j+1
    def add(mask, f, s):
        for j in np.flatnonzero(np.nan_to_num(mask, nan=0).astype(bool)):
            if j + 1 < n: ev.append((j, f, s))
    add((oi4 <= np.log(0.96)) & (mv4 <= -1), 0, 1)
    add((oi4 <= np.log(0.96)) & (mv4 >= 1), 1, -1)
    add((oi4 >= np.log(1.10)) & (mv4 >= 1), 2, -1); add((oi4 >= np.log(1.10)) & (mv4 <= -1), 2, 1)
    add(ls_z >= 2.5, 3, -1); add(ls_z <= -2.5, 3, 1)
    add(tk_z >= 3, 4, -1); add(tk_z <= -3, 4, 1)
    add(fund <= -0.0005, 5, 1); add(fund >= 0.0008, 5, -1)
    add(resid_z >= 3, 6, -1); add(resid_z <= -3, 6, 1)
    add((volx >= 6) & (up_w >= 0.55) & (C > O - 1e300), 7, -1); add((volx >= 6) & (dn_w >= 0.55), 7, 1)
    add((top_z >= 2) & (lsd_z <= 0), 8, 1); add((top_z <= -2) & (lsd_z >= 0), 8, -1)
    return ev


EVENTS = [ev2_events]


_B = {}
def btc():
    if not _B:
        T, O, H, L, C, V = load_np("BTCUSDT")
        did = T // 86400; dg = agg(did, O, H, L, C)
        _B.update(T=T, C=C, did=did, dg=dg, e50=ema(dg[4], 50))
    return _B


def run(sym):
    fn = f"{OUT[0]}/{sym}.npz"
    if os.path.exists(fn):
        return sym, -1
    T, O, H, L, C, V = load_np(sym)
    n = len(T)
    if n < 24 * 90:
        return sym, 0
    did = T // 86400
    dg = agg(did, O, H, L, C); dpi = np.searchsorted(dg[0], did)
    dC = dg[4]
    datr = to_hours(wilder_atr(dg[2], dg[3], dC) / dC * 100, dpi)
    M = metrics(sym, T)
    b = btc()
    bj = np.clip(np.searchsorted(b["T"], T, side="right") - 1, 0, len(b["T"]) - 1)
    bC = b["C"][bj]
    def lr(x, k):
        o = np.full(len(x), np.nan); o[k:] = np.log(x[k:] / x[:-k]); return o
    r24, b24r = lr(C, 24), lr(bC, 24)
    # beta over 60 days of hourly returns, from closed data
    r1, b1 = lr(C, 1), lr(bC, 1)
    cxy = np.cumsum(np.insert(np.nan_to_num(r1 * b1), 0, 0)); cyy = np.cumsum(np.insert(np.nan_to_num(b1 * b1), 0, 0))
    W = 24 * 60
    beta = np.full(n, 1.0)
    beta[W:] = (cxy[W:n] - cxy[:n - W]) / np.maximum(cyy[W:n] - cyy[:n - W], 1e-12)
    beta = np.clip(beta, 0, 3)
    resid = r24 - beta * b24r
    resid_z = np.full(n, np.nan)
    # z of the residual vs its own 60-day history sampled daily (overlapping 24h windows)
    sd = np.full(n, np.nan)
    c2 = np.cumsum(np.insert(np.nan_to_num(resid) ** 2, 0, 0))
    sd[W:] = np.sqrt((c2[W:n] - c2[:n - W]) / W)
    resid_z = resid / np.where(sd > 0, sd, np.nan)
    oi = M["oi"]
    oi4, oi24 = lr(oi, 4), lr(oi, 24)
    ls_z = zs(M["ls_acc"], 24 * 30)
    tk = np.convolve(np.nan_to_num(M["taker"], nan=1.0), np.ones(24) / 24, mode="full")[:n]
    tk_z = zs(tk, 24 * 30)
    top_d = lr(M["top_pos"], 72); top_z = zs(top_d, 24 * 30)
    ls_d = lr(M["ls_acc"], 72); lsd_z = zs(ls_d, 24 * 30)
    fund = M["fund"]
    vm = np.convolve(V, np.ones(480) / 480, mode="full")[:n]
    volx = np.full(n, np.nan); volx[481:] = V[481:] / np.maximum(vm[480:-1], 1e-12)
    rng_ = H - L
    up_w = (H - np.maximum(O, C)) / np.where(rng_ > 0, rng_, np.nan)
    dn_w = (np.minimum(O, C) - L) / np.where(rng_ > 0, rng_, np.nan)
    mv4 = (C - np.roll(C, 4)) / C * 100 / datr; mv4[:4] = np.nan
    ev = EVENTS[0](locals())
    if not ev:
        return sym, 0
    ev.sort()
    J = np.array([e[0] for e in ev]); Fm = np.array([e[1] for e in ev]); S = np.array([e[2] for e in ev])
    ok = np.isfinite(datr[J]) & (datr[J] >= 0.1) & (J > 24 * 30)
    J, Fm, S = J[ok], Fm[ok], S[ok]
    keep = cooldown(J, S, Fm, T, 86400)
    J, Fm, S = J[keep], Fm[keep], S[keep]
    m = len(J)
    if m == 0:
        return sym, 0
    jE = J + 1; fill = O[jE]
    atr_h = wilder_atr(H, L, C) / C * 100
    R = np.zeros((len(EXITS), m), np.float32); K = np.zeros((len(EXITS), m), np.int32)
    for e, (a, tk_, hd, pa, pf) in enumerate(EXITS):
        for i in range(m):
            ah = float(atr_h[J[i]])
            dd = float(datr[J[i]]) if (e < 3 or not (ah > 0.05)) else 1.5 * ah
            R[e, i], K[e, i] = simp(O, H, L, C, int(jE[i]), int(S[i]), float(fill[i]), dd, a, tk_, hd, pa, pf)
    F = np.zeros((m, len(FNAMES)), np.float32)
    px = C[J]; dat = datr[J]; dpx = dat / 100 * px
    F[:, 0] = Fm; F[:, 1] = S; F[:, 2] = dat; F[:, 3] = (T[J] // 3600) % 24; F[:, 4] = (did[J] + 3) % 7
    def ret(k):
        a_ = np.maximum(J - k, 0); return (C[J] / C[a_] - 1) * 100
    F[:, 5] = S * ret(4); F[:, 6] = S * ret(24); F[:, 7] = S * ret(72); F[:, 8] = S * ret(168)
    F[:, 9] = S * (bC[J] / bC[np.maximum(J - 24, 0)] - 1) * 100; F[:, 10] = S * (bC[J] / bC[np.maximum(J - 168, 0)] - 1) * 100
    bdi = np.maximum(np.searchsorted(b["dg"][0], b["did"][bj[J]]) - 1, 0); be = b["e50"][bdi]
    F[:, 11] = np.where(np.isfinite(be), S * (b["dg"][4][bdi] / be - 1) * 100, 0)
    F[:, 12] = S * (np.nan_to_num(to_hours(rsi(dC), dpi)[J], nan=50) - 50); F[:, 13] = S * (rsi(C)[J] - 50)
    e50 = to_hours(ema(dC, 50), dpi)[J]; e200 = to_hours(ema(dC, 200), dpi)[J]
    F[:, 14] = np.nan_to_num(S * (px - e50) / dpx); F[:, 15] = np.nan_to_num(S * (px - e200) / dpx)
    kd = dpi[J] - 1
    for c_, w in ((16, 30), (17, 90), (18, 365)):
        hh = np.array([dg[2][max(0, k - w + 1):k + 1].max() if k >= 0 else np.nan for k in kd])
        ll = np.array([dg[3][max(0, k - w + 1):k + 1].min() if k >= 0 else np.nan for k in kd])
        pos = np.where(hh > ll, (px - ll) / np.where(hh > ll, hh - ll, 1), 0.5)
        F[:, c_] = np.where(S > 0, pos, 1 - pos)
    cv = np.cumsum(np.insert(V, 0, 0.0))
    v24 = cv[J + 1] - cv[np.maximum(J - 23, 0)]; v20 = (cv[J + 1] - cv[np.maximum(J - 479, 0)]) / 20
    F[:, 19] = np.log((v24 + 1e-9) / (v20 + 1e-9))
    F[:, 20] = np.nan_to_num(atr_h[J] / np.maximum(dat, 1e-9))
    F[:, 21] = S * np.nan_to_num(oi4[J]) * 100; F[:, 22] = S * np.nan_to_num(oi24[J]) * 100
    F[:, 23] = S * np.nan_to_num(ls_z[J]); F[:, 24] = S * np.nan_to_num(tk_z[J]); F[:, 25] = S * np.nan_to_num(fund[J]) * 1e4
    F[:, 26] = S * np.nan_to_num(resid_z[J]); F[:, 27] = np.nan_to_num(np.log(np.maximum(volx[J], 1e-6)))
    F[:, 28] = np.nan_to_num(np.where(S > 0, dn_w[J], up_w[J])); F[:, 29] = S * np.nan_to_num(top_z[J])
    emas = [to_hours(ema(dC, k), dpi)[J] for k in (7, 14, 28, 50, 100, 200)]
    ed = np.abs(np.array(emas) - px) / dpx
    F[:, 30] = np.nan_to_num(np.nanmin(np.where(np.isfinite(ed), ed, 99), 0), nan=99).clip(0, 20)
    np.savez_compressed(fn, t=T[J], j=J, fam=Fm, side=S, datr=dat, R=R, K=K, F=F)
    return sym, m


if __name__ == "__main__":
    os.makedirs(OUT[0], exist_ok=True)
    import json
    sp = json.load(open(f"{D}/lv/split.json"))
    syms = ARGS or (sp["bot"] + sp["chk"])
    t0 = time.time()
    if len(syms) == 1:
        print(run(syms[0]), time.time() - t0)
    else:
        with mp.Pool(3) as pool:
            for k, (s, m) in enumerate(pool.imap_unordered(run, syms)):
                if k % 30 == 0:
                    print(k, s, m, round(time.time() - t0), flush=True)
    print("done", round(time.time() - t0))
