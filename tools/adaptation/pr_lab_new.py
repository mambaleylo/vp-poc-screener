"""P/R night round 2: exit labels on top of v0.99.662 (the limit 0.3 ATR / 3 h, the stop by the 1h close 3 ATR, hard 6 ATR,
take 4.5 ATR, 48 bars, R per the hard stop) with key=value overrides: take soft hard hold lim limw lock_at lock_to
(after +lock_at ATR the hard stop moves to +lock_to ATR) early_k early_r (out at bar early_k's close if below early_r ATR)
ARGV: out_name key=value ..."""
import os, sys, glob, numpy as np
ARGV = sys.argv[1:]
from numba import njit
from common import V, load, D
FEE, FUND = 0.001, 0.0003
OUTN = ARGV[0]
P = dict(take=4.5, soft=3.0, hard=6.0, hold=48, lim=0.3, limw=3, lock_at=0.0, lock_to=0.0, early_k=0, early_r=0.0)
for kv in ARGV[1:]:
    k, v = kv.split("="); P[k] = float(v)
@njit(cache=True)
def lab(O, H, L, C, idx, sd, atr, take, soft, hard, hold, lim, limw, lock_at, lock_to, early_k, early_r, out, kind, kbar):
    for j in range(len(idx)):
        i = idx[j]; s = sd[j]; a = atr[j]
        if i < 0 or i + hold + 1 + limw > len(O) or a != a:
            out[j] = np.nan; kind[j] = -1; kbar[j] = -1; continue
        e = O[i + 1]
        if lim > 0:
            lv = O[i + 1] - s * lim * a; f = -1
            for w in range(limw):
                b = i + 1 + w
                if (s > 0 and L[b] <= lv) or (s < 0 and H[b] >= lv): f = b; break
            if f < 0:
                out[j] = np.nan; kind[j] = -1; kbar[j] = -1; continue
            e = min(lv, O[f]) if s > 0 else max(lv, O[f]); i = f - 1
        risk = hard * a; hs = e - s * hard * a; ss = e - s * soft * a; tp = e + s * take * a
        locked = False
        k = hold - 1; ex = C[i + hold]; kd = 3
        for q in range(hold):
            b = i + 1 + q
            if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
                gap = q > 0 and ((s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs))
                k = q; ex = O[b] if gap else hs; kd = 0; break
            if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp):
                k = q; ex = tp; kd = 2; break
            if (s > 0 and C[b] <= ss) or (s < 0 and C[b] >= ss):
                k = q; ex = C[b]; kd = 1; break
            if early_k > 0 and q == early_k - 1 and s * (C[b] - e) < early_r * a:
                k = q; ex = C[b]; kd = 5; break
            if lock_at > 0 and not locked and s * ((H[b] if s > 0 else L[b]) - e) >= lock_at * a:
                locked = True; hs = e + s * lock_to * a; ss = e - s * 1e9
        fee = (e * FEE + e * FUND * (k + 1) / 24) / risk
        out[j] = s * (ex - e) / risk - fee; kind[j] = kd; kbar[j] = k
res, kinds, kbars = [], [], []
for fn in sorted(glob.glob(f"{D}/prv_ev_new/*.npz")):
    z = np.load(fn); t = z["t"]
    if not len(t): continue
    X = z["X"]; tf = X[:, 0].astype(int); sd = X[:, 1].astype(np.int64)
    cs = load(os.path.basename(fn)[:-4])
    o = np.full(len(t), np.nan); kk = np.full(len(t), -1, dtype=np.int64); kb = np.full(len(t), -1, dtype=np.int64)
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    T = np.array([c["time"] for c in cs]); A = np.array([a if a else np.nan for a in V.neuro_atr_series(cs, 14)])
    m = np.where(tf == 1)[0]
    i = np.searchsorted(T, t[m] - 3600); i = np.where((i < len(T)) & (T[np.minimum(i, len(T) - 1)] == t[m] - 3600), i, -1)
    out = np.empty(len(m)); kd = np.empty(len(m), dtype=np.int64); kq = np.empty(len(m), dtype=np.int64)
    lab(O, H, L, C, i.astype(np.int64), sd[m], A[np.maximum(i, 0)], P["take"], P["soft"], P["hard"], int(P["hold"]), P["lim"], int(P["limw"]),
        P["lock_at"], P["lock_to"], int(P["early_k"]), P["early_r"], out, kd, kq); o[m] = out; kk[m] = kd; kb[m] = kq
    res.append(o); kinds.append(kk); kbars.append(kb)
np.savez(f"{D}/{OUTN}.npz", cs=np.concatenate(res).astype(np.float32), kind=np.concatenate(kinds).astype(np.int8), k=np.concatenate(kbars).astype(np.int16))
print("done", OUTN, flush=True)
