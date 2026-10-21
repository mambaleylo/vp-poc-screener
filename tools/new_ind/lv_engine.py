"""New indicator hunt, family 1: touches of higher-timeframe levels other than the EMAs (the EMA module's mechanism:
a limit at a level known in advance, filled on the first touch in the period). Levels from CLOSED bars only:
  day scope   : prev day high / low / mid, SMA20/50/100/200 (1d), Bollinger 20x2 upper / lower (1d)
  week scope  : prev week high / low / mid, the week's open, SMA10/20/50 (1w), Bollinger 20x2 (1w)
  month scope : prev month high / low / mid, the month's open, the year's open
Side: the level below the last 1h close -> a long at support, above -> a short at resistance. First touch per
(level, period); filled when the hour trades >= 0.1% past the level (as the EMA research). Exits re-simulated on 1h
bars (fees 0.1% + funding 0.03%/day): E0 = the EMA module's (stop 0.75 daily ATR, 1/3 off at +1R -> break-even,
take 4R, 72 h), E1 = stop 0.5 dATR, take 3R, 48 h, E2 = stop 1 dATR, take 3R, 72 h, no partial.
Features: everything known before the touch hour. Saved per coin to lv/<SYM>.npz (v1) / lv2/<SYM>.npz (+ the SMC families)."""
import sys, os, time
ARGS = sys.argv[1:]
import numpy as np
from numba import njit
from common import D
import multiprocessing as mp

FAMS = ["pdh", "pdl", "pdm", "d_sma20", "d_sma50", "d_sma100", "d_sma200", "d_bbu", "d_bbl",
        "pwh", "pwl", "pwm", "wopen", "w_sma10", "w_sma20", "w_sma50", "w_bbu", "w_bbl",
        "pmh", "pml", "pmm", "mopen", "yopen",
        "d_ema7", "d_ema14", "d_ema28", "d_ema50", "d_ema100", "d_ema200", "w_ema7", "w_ema14", "w_ema28", "w_ema50",
        "fvg4_bull", "fvg4_bear", "fvgd_bull", "fvgd_bear", "fvgw_bull", "fvgw_bear",
        "swd_low", "swd_high", "sww_low", "sww_high", "obd_bull", "obd_bear", "ob4_bull", "ob4_bear"]
SCOPE = [0] * 9 + [1] * 9 + [2] * 5 + [0] * 6 + [1] * 4 + [3, 3, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 3, 3]   # 3 = the 4h bar       # 0 day, 1 week, 2 month (yopen: per month too, first touch in the month)
EXITS = ((0.75, 4.0, 72, 1.0, 1 / 3), (0.5, 3.0, 48, 0.0, 0.0), (1.0, 3.0, 72, 0.0, 0.0))
FNAMES = ["fam", "scope", "side", "datr", "hour", "dow", "dist_prev", "travel", "r24", "r72", "r7d", "b24", "b7d", "b_e50",
          "rsi_d", "rsi_h", "d_e50", "d_e200", "pos30", "pos90", "pos365", "vol24", "conf", "ema_near", "ema_conf",
          "round", "prog", "atr_h", "wick_prev"]
OUT = f"{D}/lv2"


def load_np(sym):
    a = np.loadtxt(f"{D}/data/1h/{sym}.csv", delimiter=",", ndmin=2)
    t = a[:, 0].astype(np.int64)
    keep = np.concatenate([[True], np.diff(t) > 0])
    a = a[keep]
    return a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]


def month_id(T):
    dd = (T // 86400).astype("datetime64[D]")
    return dd.astype("datetime64[M]").astype(np.int64), dd.astype("datetime64[Y]").astype(np.int64)


def agg(pid, O, H, L, C):
    """period aggregates in order of appearance: ids, open, high, low, close, first hour index"""
    ch = np.flatnonzero(np.diff(pid)) + 1
    st = np.concatenate([[0], ch]); en = np.concatenate([ch, [len(pid)]])
    return (pid[st], O[st], np.maximum.reduceat(H, st), np.minimum.reduceat(L, st), C[en - 1], st, en)


def sma(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0)); out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def rstd(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        out[i] = x[i - n + 1:i + 1].std()
    return out


def ema(x, n):
    out = np.empty(len(x)); k = 2 / (n + 1); e = x[0]
    for i in range(len(x)):
        e = x[i] if i == 0 else e + k * (x[i] - e); out[i] = e
    out[:min(len(x), n - 1)] = np.nan
    return out


def wilder_atr(H, L, C, n=14):
    pc = np.concatenate([[C[0]], C[:-1]])
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    out = np.full(len(C), np.nan)
    if len(C) > n:
        a = tr[:n].mean(); out[n - 1] = a
        for i in range(n, len(C)):
            a = (a * (n - 1) + tr[i]) / n; out[i] = a
    return out


def rsi(C, n=14):
    d = np.diff(C, prepend=C[0]); up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    out = np.full(len(C), 50.0); au = up[1:n + 1].mean() if len(C) > n else 0; ad = dn[1:n + 1].mean() if len(C) > n else 0
    for i in range(n + 1, len(C)):
        au = (au * (n - 1) + up[i]) / n; ad = (ad * (n - 1) + dn[i]) / n
        out[i] = 100 - 100 / (1 + au / ad) if ad > 0 else 100.0
    return out


def to_hours(per_val, pidx, shift=1):
    """value of the period `shift` before the hour's own period (closed bars only)"""
    k = pidx - shift
    out = np.full(len(pidx), np.nan)
    ok = k >= 0
    out[ok] = per_val[k[ok]]
    return out


@njit(cache=True)
def detect(T, O, H, L, C, LV, P):
    """first touch per (family, period): returns (j, fam, side)"""
    nf, n = LV.shape
    out_j = []; out_f = []; out_s = []
    for f in range(nf):
        last_p = -1; done = False
        for j in range(1, n):
            p = P[f, j]
            if p != last_p:
                last_p = p; done = False
            if done:
                continue
            lv = LV[f, j]
            if not (lv == lv) or lv <= 0:
                continue
            pc = C[j - 1]
            if pc > lv:
                if O[j] <= lv:
                    done = True; continue
                if L[j] <= lv * 0.999:
                    out_j.append(j); out_f.append(f); out_s.append(1); done = True
            elif pc < lv:
                if O[j] >= lv:
                    done = True; continue
                if H[j] >= lv * 1.001:
                    out_j.append(j); out_f.append(f); out_s.append(-1); done = True
    return np.array(out_j), np.array(out_f), np.array(out_s)


@njit(cache=True)
def simp(O, H, L, C, j, side, fill, datr, a, take, hold, pa, pf):
    n = len(C); risk = fill * a * datr / 100
    stop = fill - side * risk; tp = fill + side * take * risk; took = False
    e = min(n, j + hold); k = e - 1 - j; ex = C[e - 1]
    for q in range(e - j):
        b = j + q
        if (side > 0 and L[b] <= stop) or (side < 0 and H[b] >= stop):
            gap = (side > 0 and O[b] <= stop) or (side < 0 and O[b] >= stop)
            ex = O[b] if (gap and q > 0) else stop; k = q; break
        if q > 0:
            fav = ((H[b] - fill) if side > 0 else (fill - L[b])) / risk
            if pa > 0 and not took and fav >= pa:
                took = True; stop = fill
            if fav >= take:
                ex = tp; k = q; break
    fee = (0.001 + 0.0003 * (k + 1) / 24) * fill / risk
    rest = side * (ex - fill) / risk
    if not took:
        return rest - fee, k + 1
    return pf * pa + (1 - pf) * rest - fee, k + 1


@njit(cache=True)
def smc_levels(O, H, L, C, atr, kind, side):
    """per TF bar k: the nearest untouched SMC level after bar k closed (below the close for side +1, above for -1).
    kind 0 = fair-value gap (bull: low[i] > high[i-2], level = low[i]; bear: high[i] < low[i-2], level = high[i]),
    1 = swing (pivot 3 bars each side, confirmed 3 bars later), 2 = order block (the last opposite candle before
    a move of >= 1.5 ATR in 2 bars; level = its far edge: the high of a down candle for longs)."""
    n = len(C); out = np.full(n, np.nan)
    act = np.full(n, np.nan); na = 0
    for k in range(n):
        # touches remove levels (the first touch is the trade)
        for q in range(na):
            v = act[q]
            if v == v:
                if (side > 0 and L[k] <= v) or (side < 0 and H[k] >= v):
                    act[q] = np.nan
        if kind == 0 and k >= 2:
            if side > 0 and L[k] > H[k - 2]:
                act[na] = L[k]; na += 1
            if side < 0 and H[k] < L[k - 2]:
                act[na] = H[k]; na += 1
        if kind == 1 and k >= 6:
            i = k - 3
            if side > 0:
                ok = True
                for z in range(i - 3, i + 4):
                    if L[z] < L[i]: ok = False
                if ok:
                    lo_after = L[i + 1:k + 1].min()
                    if lo_after > L[i]:
                        act[na] = L[i]; na += 1
            else:
                ok = True
                for z in range(i - 3, i + 4):
                    if H[z] > H[i]: ok = False
                if ok:
                    hi_after = H[i + 1:k + 1].max()
                    if hi_after < H[i]:
                        act[na] = H[i]; na += 1
        if kind == 2 and k >= 3:
            i = k - 2
            if side > 0 and C[i] < O[i] and C[k] - H[i] >= 1.0 * atr[k] and L[k] > H[i]:
                act[na] = H[i]; na += 1
            if side < 0 and C[i] > O[i] and L[i] - C[k] >= 1.0 * atr[k] and H[k] < L[i]:
                act[na] = L[i]; na += 1
        best = np.nan
        for q in range(na):
            v = act[q]
            if v == v:
                if side > 0 and v < C[k] and (not (best == best) or v > best): best = v
                if side < 0 and v > C[k] and (not (best == best) or v < best): best = v
        out[k] = best
    return out


def _round_near(lv):
    if lv <= 0:
        return 0.0
    k = np.floor(np.log10(lv))
    for scale, w in ((10 ** k, 1.0), (10 ** k / 2, 0.7), (10 ** k / 10, 0.4)):
        q = np.ceil(lv * 0.997 / scale) * scale
        if q <= lv * 1.003:
            return w
    return 0.0


_BTC = {}


def btc_ctx():
    if not _BTC:
        T, O, H, L, C, V = load_np("BTCUSDT")
        did = T // 86400
        dg = agg(did, O, H, L, C)
        e50 = ema(dg[4], 50)
        _BTC.update(T=T, C=C, did=did, dg=dg, e50=e50)
    return _BTC


def run(sym):
    fn = f"{OUT}/{sym}.npz"
    if os.path.exists(fn):
        return sym, -1
    T, O, H, L, C, V = load_np(sym)
    n = len(T)
    if n < 24 * 60:
        return sym, 0
    did = T // 86400
    wid = (did + 3) // 7
    mid, yid = month_id(T)
    # period aggregates and hour -> period index
    out = {}
    hid = T // 14400
    for nm, pid in (("d", did), ("w", wid), ("m", mid), ("y", yid), ("h4", hid)):
        g = agg(pid, O, H, L, C)
        pidx = np.searchsorted(g[0], pid)
        out[nm] = (g, pidx)
    (dg, dpi), (wg, wpi), (mg, mpi), (yg, ypi), (hg, hpi) = out["d"], out["w"], out["m"], out["y"], out["h4"]
    dC, wC = dg[4], wg[4]
    datr_d = wilder_atr(dg[2], dg[3], dC) / dC * 100
    LV = np.full((len(FAMS), n), np.nan); P = np.zeros((len(FAMS), n), np.int64)
    lv_of = {
        "pdh": to_hours(dg[2], dpi), "pdl": to_hours(dg[3], dpi), "pdm": to_hours((dg[2] + dg[3]) / 2, dpi),
        "d_sma20": to_hours(sma(dC, 20), dpi), "d_sma50": to_hours(sma(dC, 50), dpi), "d_sma100": to_hours(sma(dC, 100), dpi),
        "d_sma200": to_hours(sma(dC, 200), dpi),
        "d_bbu": to_hours(sma(dC, 20) + 2 * rstd(dC, 20), dpi), "d_bbl": to_hours(sma(dC, 20) - 2 * rstd(dC, 20), dpi),
        "pwh": to_hours(wg[2], wpi), "pwl": to_hours(wg[3], wpi), "pwm": to_hours((wg[2] + wg[3]) / 2, wpi),
        "wopen": wg[1][wpi], "w_sma10": to_hours(sma(wC, 10), wpi), "w_sma20": to_hours(sma(wC, 20), wpi),
        "w_sma50": to_hours(sma(wC, 50), wpi),
        "w_bbu": to_hours(sma(wC, 20) + 2 * rstd(wC, 20), wpi), "w_bbl": to_hours(sma(wC, 20) - 2 * rstd(wC, 20), wpi),
        "pmh": to_hours(mg[2], mpi), "pml": to_hours(mg[3], mpi), "pmm": to_hours((mg[2] + mg[3]) / 2, mpi),
        "mopen": mg[1][mpi], "yopen": yg[1][ypi],
    }
    for k_ in (7, 14, 28, 50, 100, 200):
        lv_of[f"d_ema{k_}"] = to_hours(ema(dC, k_), dpi)
    for k_ in (7, 14, 28, 50):
        lv_of[f"w_ema{k_}"] = to_hours(ema(wC, k_), wpi)
    for tag, g_, pi_ in (("4", hg, hpi), ("d", dg, dpi), ("w", wg, wpi)):
        at_ = wilder_atr(g_[2], g_[3], g_[4]); at_ = np.nan_to_num(at_, nan=np.inf)
        for side_, nmb in ((1, "bull"), (-1, "bear")):
            if f"fvg{tag}_{nmb}" in FAMS:
                lv_of[f"fvg{tag}_{nmb}"] = to_hours(smc_levels(g_[1], g_[2], g_[3], g_[4], at_, 0, side_), pi_)
            if f"ob{tag}_{nmb}" in FAMS:
                lv_of[f"ob{tag}_{nmb}"] = to_hours(smc_levels(g_[1], g_[2], g_[3], g_[4], at_, 2, side_), pi_)
        for side_, nmb in ((1, "low"), (-1, "high")):
            if f"sw{tag}_{nmb}" in FAMS:
                lv_of[f"sw{tag}_{nmb}"] = to_hours(smc_levels(g_[1], g_[2], g_[3], g_[4], at_, 1, side_), pi_)
    # a period's own open is only a level once the period has started and the price has left it: skip the first 6 hours
    for f, nm in enumerate(FAMS):
        LV[f] = lv_of[nm]
        P[f] = (dpi, wpi, mpi, hpi)[SCOPE[f]]
    wst = T[wg[5]][wpi]; mst = T[mg[5]][mpi]; yst = T[yg[5]][ypi]
    LV[FAMS.index("wopen")][T - wst < 6 * 3600] = np.nan
    LV[FAMS.index("mopen")][T - mst < 6 * 3600] = np.nan
    LV[FAMS.index("yopen")][T - yst < 24 * 3600] = np.nan
    # daily ATR of the last closed day for every hour
    dat_h = to_hours(datr_d, dpi)
    J, Fm, S = detect(T, O, H, L, C, LV, P)
    if len(J) == 0:
        return sym, 0
    ok = np.isfinite(dat_h[J]) & (dat_h[J] >= 0.1)
    J, Fm, S = J[ok], Fm[ok], S[ok]
    m = len(J)
    lvv = LV[Fm, J]
    R = np.zeros((len(EXITS), m), np.float32); K = np.zeros((len(EXITS), m), np.int32)
    for e, (a, tk, hd, pa, pf) in enumerate(EXITS):
        for i in range(m):
            R[e, i], K[e, i] = simp(O, H, L, C, int(J[i]), int(S[i]), float(lvv[i]), float(dat_h[J[i]]), a, tk, hd, pa, pf)
    # ---- features ----
    F = np.zeros((m, len(FNAMES)), np.float32)
    px = C[J - 1]; dat = dat_h[J]; dpx = dat / 100 * px
    F[:, 0] = Fm; F[:, 1] = np.array(SCOPE)[Fm]; F[:, 2] = S; F[:, 3] = dat
    F[:, 4] = (T[J] // 3600) % 24; F[:, 5] = (did[J] + 3) % 7
    F[:, 6] = S * (px - lvv) / dpx
    hst = T[hg[5]][hpi]
    pst = np.where(F[:, 1] == 0, T[dg[5]][dpi[J]], np.where(F[:, 1] == 1, wst[J], np.where(F[:, 1] == 3, hst[J], mst[J])))
    jst = np.searchsorted(T, pst)
    F[:, 7] = S * (O[jst] - lvv) / dpx
    def ret(k):
        a = np.maximum(J - 1 - k, 0); return (C[J - 1] / C[a] - 1) * 100
    F[:, 8] = S * ret(24); F[:, 9] = S * ret(72); F[:, 10] = S * ret(168)
    b = btc_ctx()
    bj = np.clip(np.searchsorted(b["T"], T[J]) - 1, 169, len(b["T"]) - 1)
    F[:, 11] = S * (b["C"][bj] / b["C"][bj - 24] - 1) * 100
    F[:, 12] = S * (b["C"][bj] / b["C"][bj - 168] - 1) * 100
    bdi = np.searchsorted(b["dg"][0], b["did"][bj]) - 1
    be = b["e50"][np.maximum(bdi, 0)]
    F[:, 13] = np.where(np.isfinite(be), S * (b["dg"][4][np.maximum(bdi, 0)] / be - 1) * 100, 0)
    rd = to_hours(rsi(dC), dpi)[J]; F[:, 14] = S * (np.nan_to_num(rd, nan=50) - 50)
    F[:, 15] = S * (rsi(C)[J - 1] - 50)
    e50 = to_hours(ema(dC, 50), dpi)[J]; e200 = to_hours(ema(dC, 200), dpi)[J]
    F[:, 16] = np.nan_to_num(S * (px - e50) / dpx); F[:, 17] = np.nan_to_num(S * (px - e200) / dpx)
    kd = dpi[J] - 1
    for c_, w in ((18, 30), (19, 90), (20, 365)):
        hh = np.array([dg[2][max(0, k - w + 1):k + 1].max() if k >= 0 else np.nan for k in kd])
        ll = np.array([dg[3][max(0, k - w + 1):k + 1].min() if k >= 0 else np.nan for k in kd])
        pos = np.where(hh > ll, (px - ll) / np.where(hh > ll, hh - ll, 1), 0.5)
        F[:, c_] = np.where(S > 0, pos, 1 - pos)
    cv = np.cumsum(np.insert(V, 0, 0.0))
    v24 = cv[J] - cv[np.maximum(J - 24, 0)]; v20 = (cv[J] - cv[np.maximum(J - 480, 0)]) / 20
    F[:, 21] = np.log((v24 + 1e-9) / (v20 + 1e-9))
    allv = LV[:, J]   # every family's level at the touch hour
    F[:, 22] = (np.abs(allv - lvv) / dpx <= 0.3).sum(0) - 1
    # the EMA module's levels (closed 1d / 1w EMAs 7..200): the nearest, and how many within 0.3 dATR
    emas = [to_hours(ema(dC, k), dpi)[J] for k in (7, 14, 28, 50, 100, 200)] + [to_hours(ema(wC, k), wpi)[J] for k in (7, 14, 28, 50)]
    ed = np.abs(np.array(emas) - lvv) / dpx
    F[:, 23] = np.nan_to_num(np.nanmin(np.where(np.isfinite(ed), ed, 99), 0), nan=99).clip(0, 20)
    F[:, 24] = (np.nan_to_num(ed, nan=99) <= 0.3).sum(0)
    F[:, 25] = [_round_near(v) for v in lvv]
    plen = np.where(F[:, 1] == 0, 86400, np.where(F[:, 1] == 1, 7 * 86400, np.where(F[:, 1] == 3, 14400, 30 * 86400)))
    F[:, 26] = (T[J] - pst) / plen
    atr_h = wilder_atr(H, L, C)
    F[:, 27] = np.nan_to_num(atr_h[J - 1] / px * 100 / np.maximum(dat, 1e-9))
    F[:, 28] = S * ((np.minimum(O[J - 1], C[J - 1]) - L[J - 1]) - (H[J - 1] - np.maximum(O[J - 1], C[J - 1]))) / dpx
    np.savez_compressed(fn, t=T[J], j=J, fam=Fm, side=S, lv=lvv, datr=dat, R=R, K=K, F=F)
    return sym, m


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    import json
    sp = json.load(open(f"{D}/lv/split.json"))
    syms = ARGS or (sp["bot"] + sp["chk"])
    t0 = time.time()
    if len(syms) == 1:
        print(run(syms[0]), time.time() - t0)
    else:
        with mp.Pool(4) as pool:
            for k, (s, m) in enumerate(pool.imap_unordered(run, syms)):
                if k % 20 == 0:
                    print(k, s, m, round(time.time() - t0), flush=True)
    print("done", round(time.time() - t0))
