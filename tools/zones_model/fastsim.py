"""numpy replay of the bot's ladder (zones_ladder_step semantics: fills at the limit / the open after a gap,
the stop first, the take only against fills from before the candle), 2 legs: the near and the far edge."""
import numpy as np
FEE = 0.001

def _first(mask, start=0):
    if start >= len(mask):
        return -1
    k = np.argmax(mask[start:])
    return start + k if mask[start + k] else -1

def ladder(O, H, L, C, s, near, far, off, buf_pct, tp_mode, tp_val):
    """O,H,L,C: future bars (numpy). Returns (r, bars_held, res, filled) or None (no fill).
    tp_mode: 'pct' (tp_val % from the average) or 'R' (tp_val x the average's distance to the stop)"""
    l1, l2 = near * (1 + s * off / 100), far * (1 + s * off / 100)
    sl = far * (1 - s * buf_pct / 100)
    if s > 0:
        f1 = _first(L <= l1)
        if f1 < 0:
            return None
        f2 = _first(L <= l2, f1)
        fill1 = min(l1, O[f1])
        hit_sl = L <= sl
    else:
        f1 = _first(H >= l1)
        if f1 < 0:
            return None
        f2 = _first(H >= l2, f1)
        fill1 = max(l1, O[f1])
        hit_sl = H >= sl
    fill2 = None if f2 < 0 else (min(l2, O[f2]) if s > 0 else max(l2, O[f2]))
    def tp_of(avg):
        return avg * (1 + s * tp_val / 100) if tp_mode == "pct" else avg + s * tp_val * abs(avg - sl)
    n = len(H)
    end2 = f2 if f2 >= 0 else n
    # phase A: bars f1 .. end2-1 with only leg1 (tp not on bar f1); plus bar f2 itself (stop, then tp vs leg1)
    tpA = tp_of(fill1)
    hit_tpA = (H >= tpA) if s > 0 else (L <= tpA)
    res = None
    a_end = min(n, (f2 + 1) if f2 >= 0 else n)
    for_stop = hit_sl[f1:a_end]
    ks = np.argmax(for_stop) if for_stop.any() else -1
    tp_rng = hit_tpA[f1 + 1:a_end]
    kt = (np.argmax(tp_rng) + 1) if tp_rng.any() else -1
    if ks >= 0 and (kt < 0 or ks <= kt):
        j = f1 + ks
        fills = [fill1] + ([fill2] if f2 >= 0 and j >= f2 else [])
        gap = (O[j] <= sl) if s > 0 else (O[j] >= sl)
        ex, res, jj = (O[j] if gap else sl), "L", j
    elif kt >= 0:
        j = f1 + kt
        fills = [fill1] + ([fill2] if f2 >= 0 and j >= f2 else [])
        ex, res, jj = tpA, "W", j
    if res is None and f2 >= 0 and f2 + 1 < n:
        avg = (fill1 + fill2) / 2
        tpB = tp_of(avg)
        hit_tpB = (H >= tpB) if s > 0 else (L <= tpB)
        st = hit_sl[f2 + 1:]
        tt = hit_tpB[f2 + 1:]
        ks = np.argmax(st) if st.any() else -1
        kt = np.argmax(tt) if tt.any() else -1
        fills = [fill1, fill2]
        if ks >= 0 and (kt < 0 or ks <= kt):
            j = f2 + 1 + ks
            gap = (O[j] <= sl) if s > 0 else (O[j] >= sl)
            ex, res, jj = (O[j] if gap else sl), "L", j
        elif kt >= 0:
            ex, res, jj = tpB, "W", f2 + 1 + kt
    if res is None:
        fills = [fill1] + ([fill2] if f2 >= 0 else [])
        ex, res, jj = C[-1], "T", n - 1
    denom = (s * (l1 - sl) + s * (l2 - sl)) or 1e-12
    gross = sum(s * (ex - f) for f in fills)
    r = (gross - FEE * sum(fills)) / denom
    return (round(float(r), 4), int(jj - f1 + 1), res, len(fills), int(f1))
