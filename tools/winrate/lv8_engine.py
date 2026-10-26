"""New indicator hunt, family 8: the SMC module's own structures (lv_engine.smc_levels: FVG, swing, order block) on the
timeframes it does not trade: 2h, 8h, 12h, 3d (it trades 4h / 1d / 1w) -- more trades of the same kind. Levels from
CLOSED bars (to_hours shift 1); first touch per (level, the TF bar); filled >= 0.1% past it; exits / features / format:
lv_engine's. lv8/<SYM>.npz"""

import numpy as np
from numba import njit
src = open("lv_engine.py").read()
pre, post = src.split("def run(sym):")
exec(pre.replace("@njit(cache=True)", "@njit"))   # everything of lv_engine but its run (FAMS / SCOPE / OUT replaced below)
TF8 = (("2h", 7200), ("8h", 28800), ("12h", 43200), ("3d", 259200))
FAMS = [f"{k}{tf}" for tf, _ in TF8 for k in ("fvg_bull", "fvg_bear", "sw_low", "sw_high", "ob_bull", "ob_bear")]
SCOPE = [3] * 6 + [0] * 18
OUT = f"{D}/lv8"


@njit(cache=True)
def vprof(pid, H, L, V, nb):
    """per period (consecutive equal pid): POC, VAH, VAL of its 1h bars"""
    n = len(pid); out_p = []; poc = []; vah = []; val = []
    i = 0
    while i < n:
        k = i
        while k < n and pid[k] == pid[i]:
            k += 1
        lo = L[i:k].min(); hi = H[i:k].max()
        out_p.append(pid[i])
        if not (hi > lo):
            poc.append(np.nan); vah.append(np.nan); val.append(np.nan); i = k; continue
        w = (hi - lo) / nb; prof = np.zeros(nb)
        for b in range(i, k):
            if not (H[b] > L[b]):
                q = min(nb - 1, int((L[b] - lo) / w)); prof[q] += V[b]; continue
            b0 = min(nb - 1, int((L[b] - lo) / w)); b1 = min(nb - 1, int((H[b] - lo) / w))
            for q in range(b0, b1 + 1):
                ql, qh = lo + q * w, lo + (q + 1) * w
                ov = min(qh, H[b]) - max(ql, L[b])
                if ov > 0:
                    prof[q] += V[b] * ov / (H[b] - L[b])
        pq = int(np.argmax(prof)); tot = prof.sum(); a = pq; c = pq; acc = prof[pq]
        while acc < 0.7 * tot and (a > 0 or c < nb - 1):
            up = prof[c + 1] if c < nb - 1 else -1.0; dn = prof[a - 1] if a > 0 else -1.0
            if up >= dn:
                c += 1; acc += prof[c]
            else:
                a -= 1; acc += prof[a]
        poc.append(lo + (pq + 0.5) * w); vah.append(lo + (c + 1) * w); val.append(lo + a * w)
        i = k
    return np.array(out_p), np.array(poc), np.array(vah), np.array(val)


@njit(cache=True)
def fibs(H, L, atr, k, minatr):
    """per bar (closed): the golden-pocket (0.618) level of the last confirmed impulse -> (up_level, dn_level)"""
    n = len(H); up = np.full(n, np.nan); dn = np.full(n, np.nan)
    ph_i = -1; pl_i = -1
    for i in range(2 * k, n):
        c = i - k   # a pivot at c is confirmed at i
        isH = True; isL = True
        for j in range(c - k, c + k + 1):
            if j != c:
                if H[j] >= H[c]: isH = False
                if L[j] <= L[c]: isL = False
        if isH: ph_i = c
        if isL: pl_i = c
        if ph_i >= 0 and pl_i >= 0:
            hi, lo = H[ph_i], L[pl_i]
            a = atr[i]
            if hi > lo and a == a and (hi - lo) >= minatr * a:
                if ph_i > pl_i:   # the last move up: low -> high
                    up[i] = hi - 0.618 * (hi - lo)
                else:
                    dn[i] = lo + 0.618 * (hi - lo)
    return up, dn

@njit(cache=True)
def smc7(O, H, L, C, atr, kind, side):
    """per TF bar k: the nearest untouched level after bar k closed (below the close for side +1, above for -1)"""
    n = len(C); out = np.full(n, np.nan)
    act = np.full(4 * n + 4, np.nan); na = 0
    pend_a = np.full(n, np.nan); pend_b = np.full(n, np.nan); pend_t = np.zeros(n, np.int64); npd = 0
    piv = np.full(n, np.nan); np_ = 0
    for k in range(n):
        for q in range(na):
            v = act[q]
            if v == v:
                if (side > 0 and L[k] <= v) or (side < 0 and H[k] >= v):
                    act[q] = np.nan
        if kind == 0:
            # pivots break when the price trades through them
            for q in range(np_):
                v = piv[q]
                if v == v and ((side > 0 and L[k] < v) or (side < 0 and H[k] > v)):
                    piv[q] = np.nan
            if k >= 6:
                i = k - 3; ok = True
                for z in range(i - 3, i + 4):
                    if side > 0 and L[z] < L[i]: ok = False
                    if side < 0 and H[z] > H[i]: ok = False
                if ok:
                    v = L[i] if side > 0 else H[i]
                    a = atr[k]
                    for q in range(np_):
                        w = piv[q]
                        if w == w and abs(w - v) <= 0.15 * a:
                            act[na] = min(w, v) if side > 0 else max(w, v); na += 1
                            piv[q] = np.nan
                            break
                    piv[np_] = v; np_ += 1
        else:
            # pending zones: (a = the edge that becomes the level, b = the edge a close must cross)
            if kind == 1 and k >= 2:
                if side > 0 and H[k] < L[k - 2]:      # a bear FVG [H[k], L[k-2]]; closed above L[k-2] -> support at L[k-2]
                    pend_a[npd] = L[k - 2]; pend_b[npd] = L[k - 2]; pend_t[npd] = k; npd += 1
                if side < 0 and L[k] > H[k - 2]:      # a bull FVG [H[k-2], L[k]]; closed below H[k-2] -> resistance at H[k-2]
                    pend_a[npd] = H[k - 2]; pend_b[npd] = H[k - 2]; pend_t[npd] = k; npd += 1
            if kind == 2 and k >= 3:
                i = k - 2
                if side > 0 and C[i] > O[i] and L[i] - C[k] >= 1.0 * atr[k] and H[k] < L[i]:   # a bear OB (up candle)
                    pend_a[npd] = H[i]; pend_b[npd] = H[i]; pend_t[npd] = k; npd += 1
                if side < 0 and C[i] < O[i] and C[k] - H[i] >= 1.0 * atr[k] and L[k] > H[i]:   # a bull OB (down candle)
                    pend_a[npd] = L[i]; pend_b[npd] = L[i]; pend_t[npd] = k; npd += 1
            for q in range(npd):
                v = pend_b[q]
                if v == v and pend_t[q] < k:
                    if k - pend_t[q] > 100:
                        pend_b[q] = np.nan; continue
                    if (side > 0 and C[k] > v) or (side < 0 and C[k] < v):
                        act[na] = pend_a[q]; na += 1; pend_b[q] = np.nan
        best = np.nan
        for q in range(na):
            v = act[q]
            if v == v:
                if side > 0 and v < C[k] and (not (best == best) or v > best): best = v
                if side < 0 and v > C[k] and (not (best == best) or v < best): best = v
        out[k] = best
    return out


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
    lv_of = {}; p_of = {}
    for tag, sec in TF8:
        pid = (T + (0 if sec < 86400 * 2 else 0)) // sec
        g_ = agg(pid, O, H, L, C); pi_ = np.searchsorted(g_[0], pid)
        at_ = wilder_atr(g_[2], g_[3], g_[4])
        for kind, nm in ((0, ("fvg_bull", "fvg_bear")), (1, ("sw_low", "sw_high")), (2, ("ob_bull", "ob_bear"))):
            for side_, sn in ((1, nm[0]), (-1, nm[1])):
                lv_of[f"{sn}{tag}"] = to_hours(smc_levels(g_[1], g_[2], g_[3], g_[4], at_, kind, side_), pi_)
                p_of[f"{sn}{tag}"] = pi_
    wst = T[wg[5]][wpi]; mst = T[mg[5]][mpi]
    for f, nm in enumerate(FAMS):
        LV[f] = lv_of[nm]
        P[f] = p_of[nm]
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
