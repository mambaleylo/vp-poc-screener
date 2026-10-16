"""Confirmation entries at a zone (numpy). Long zone [lo, hi] below the price (short mirrored).
mode 'rej':   after the first touch of the near edge, the first candle (within W bars of the touch) that
              closes back beyond the near edge -> enter at its close; stop = the extreme since the touch
              (or the far edge, whichever is farther) +- buf.
mode 'sweep': the price trades beyond the far edge, then a candle closes back inside/above it within W
              bars -> enter at its close; stop = the sweep's extreme +- buf.
The setup is invalid once a candle closes beyond far edge + inv (in datr units) before the trigger.
Exit: take = k x risk, stop, or time (hold bars after the entry). Fees in R. Returns dict or None."""
import numpy as np
FEE = 0.001

def _first(mask, start=0):
    if start >= len(mask):
        return -1
    seg = mask[start:]
    k = int(np.argmax(seg))
    return start + k if seg[k] else -1

def conf(O, H, L, C, s, lo, hi, mode, W, buf_pct, k_list, hold, wait=336, inv_px=None):
    n = min(len(C), wait)
    if s > 0:
        near, far = hi, lo
        X = -L; Y = -H; Cl = C; Op = O   # work in "long" orientation via sign flip below
    # orient: for short, mirror prices (p -> -p)
    if s < 0:
        O_, H_, L_, C_ = -O, -L, -H, -C
        near, far = -lo, -hi
    else:
        O_, H_, L_, C_ = O, H, L, C
    inv = far - (inv_px if inv_px is not None else 0)
    touch = _first(L_[:n] <= near)
    if touch < 0:
        return None
    if mode in ("rej", "rejt"):
        # invalid if a close below inv happens before the trigger
        j = -1
        for b in range(touch, min(n, touch + W + 1)):
            if C_[b] < inv:
                return None
            if C_[b] > near:
                j = b
                break
        if j < 0:
            return None
        ext = L_[touch:j + 1].min()
        stop = (min(ext, far) if mode == "rej" else ext) * (1 - buf_pct / 100)
    else:   # sweep
        sw = _first(L_[:n] < far, touch)
        if sw < 0:
            return None
        j = -1
        for b in range(sw, min(n, sw + W + 1)):
            if C_[b] > far:
                j = b
                break
            if C_[b] < far - 3 * (near - far + 1e-12):
                return None   # ran away
        if j < 0:
            return None
        ext = L_[sw:j + 1].min()
        stop = ext * (1 - buf_pct / 100)
    entry = C_[j]
    risk = entry - stop
    if risk <= 0:
        return None
    fee_r = FEE * abs(entry) / risk
    out = []
    e0, e1 = j + 1, min(len(C_), j + 1 + hold)
    if e0 >= e1:
        return None
    Ls, Hs = L_[e0:e1], H_[e0:e1]
    ks = _first(Ls <= stop)
    for k in k_list:
        tp = entry + k * risk
        kt = _first(Hs >= tp)
        if ks >= 0 and (kt < 0 or ks <= kt):
            gap = O_[e0 + ks] <= stop
            ex = O_[e0 + ks] if gap else stop
            r, res, held = (ex - entry) / risk, "L", ks + 1
        elif kt >= 0:
            r, res, held = k, "W", kt + 1
        else:
            r, res, held = (C_[e1 - 1] - entry) / risk, "T", e1 - e0
        out.append((round(float(r - fee_r), 4), int(held), res))
    return {"j": int(j), "risk_pct": round(float(risk / abs(entry) * 100), 3), "out": out}
