"""extra context of the same cascade events (cas_ev.py order): chop (whole-cascade crosses in the last 48 bars),
the cross bar (range / ATR, body share, close past the near EMA / ATR, close past the far EMA / ATR), EMA28 slope
over 12 bars, the 4h cascade (order, close vs its top / bottom), crosses the same way in the last 48 bars"""
import os, sys, numpy as np, multiprocessing as mp
ARGS = sys.argv[1:]
from common import load, D
from cas_ev import ema, NS
NAMES2 = ["chop48", "same48", "bar_rng", "body", "past_far", "past_near", "sl28", "h4_order", "h4_pos", "h4_width"]
def run(sym):
    fn = f"{D}/cas2/{sym}.npz"
    if os.path.exists(fn): return sym, -1
    z = np.load(f"{D}/cas/{sym}.npz"); Fe = z["F"]
    cs = load(sym)
    O = np.array([c["open"] for c in cs]); H = np.array([c["high"] for c in cs]); L = np.array([c["low"] for c in cs]); C = np.array([c["close"] for c in cs])
    T = np.array([c["time"] + 3600 for c in cs])
    E = np.stack([ema(C, n) for n in NS]); TOP, BOT = E.max(0), E.min(0)
    tr = np.maximum(H[1:] - L[1:], np.maximum(abs(H[1:] - C[:-1]), abs(L[1:] - C[:-1]))); tr = np.r_[H[0] - L[0], tr]
    atr = np.full(len(C), np.nan); a = tr[:14].mean()
    for i in range(14, len(C)): a = (a * 13 + tr[i]) / 14; atr[i] = a
    up = (C > TOP) & (np.r_[False, C[:-1] <= TOP[:-1]]); dn = (C < BOT) & (np.r_[False, C[:-1] >= BOT[:-1]])
    cu, cd = np.r_[0, np.cumsum(up)], np.r_[0, np.cumsum(dn)]
    # 4h bars from 1h by open time (UTC 00/04/…); the last COMPLETE one closed by the event's close
    t0 = np.array([c["time"] for c in cs]); g4 = t0 // 14400
    starts = np.r_[0, np.where(np.diff(g4) != 0)[0] + 1]; ends = np.r_[starts[1:], len(cs)]
    C4 = C[ends - 1]; T4 = g4[starts] * 14400 + 14400   # the 4h bar's close time
    full = (ends - starts) == 4
    E4 = np.stack([ema(C4, n) for n in NS]); TOP4, BOT4 = E4.max(0), E4.min(0)
    H4 = np.array([H[a:b].max() for a, b in zip(starts, ends)]); L4 = np.array([L[a:b].min() for a, b in zip(starts, ends)])
    tr4 = np.maximum(H4[1:] - L4[1:], np.maximum(abs(H4[1:] - C4[:-1]), abs(L4[1:] - C4[:-1]))); tr4 = np.r_[H4[0] - L4[0], tr4]
    atr4 = np.full(len(C4), np.nan); a = tr4[:14].mean()
    for i in range(14, len(C4)): a = (a * 13 + tr4[i]) / 14; atr4[i] = a
    pos = {int(t): i for i, t in enumerate(T)}
    rows = []
    for t, s in zip(Fe[:, 0], Fe[:, 1]):
        i = pos[int(t)]; s = int(s); a = atr[i]
        j = np.searchsorted(T4, T[i], side="right") - 1          # the last 4h bar closed by T[i]
        while j >= 0 and not full[j]: j -= 1
        rg = H[i] - L[i]
        bull4 = np.all(np.diff(E4[::-1, j]) > 0); bear4 = np.all(np.diff(E4[::-1, j]) < 0)
        o4 = (1.0 if bull4 else (-1.0 if bear4 else 0.0)) * s
        p4 = s * (C4[j] - (TOP4[j] if s > 0 else BOT4[j])) / atr4[j] if j >= 0 and atr4[j] == atr4[j] else 0.0
        rows.append([(cu[i] - cu[i - 48]) + (cd[i] - cd[i - 48]), (cu[i] - cu[i - 48]) if s > 0 else (cd[i] - cd[i - 48]),
                     rg / a, s * (C[i] - O[i]) / rg if rg > 0 else 0.0,
                     s * (C[i] - (TOP[i] if s > 0 else BOT[i])) / a, s * (C[i] - (BOT[i] if s > 0 else TOP[i])) / a,
                     s * (E[4, i] - E[4, i - 12]) / a, o4, p4, (TOP4[j] - BOT4[j]) / atr4[j] if j >= 0 and atr4[j] == atr4[j] else 0.0])
    np.savez_compressed(fn, F2=np.array(rows, dtype=np.float32))
    return sym, len(rows)
if __name__ == "__main__":
    os.makedirs(f"{D}/cas2", exist_ok=True)
    syms = ARGS or sorted(f[:-4] for f in os.listdir(f"{D}/cas"))
    with mp.Pool(2) as p:
        for r in p.imap_unordered(run, syms): print(*r, flush=True)
