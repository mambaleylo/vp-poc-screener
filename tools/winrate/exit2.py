"""lab after v0.99.690: the exits around the deployed take rule (2 ATR, back to tkn ATR once the price dips n ATR before
+1 ATR): the stop's size, a stop moved after +1 ATR (the "locked" trades), the take after the dip, the far take, the
hold of the locked / pulled trades. Bar level, the worst order inside a bar; the pool as the bot trades it; money at
20 positions x 4%, 12-month windows started weekly 2024–26 from $100 (cautious / harsh), fixed starts"""
exec(open("tkext.py").read().split("\nBARS = {}")[0])
BARS = {}
EV = events("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0) + events("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0)
@njit
def ex2(O, H, L, C, f, s, fill, a, n, tkn, tk2, stp, lockstop, hb, hn, hf, tfh):
    """-> R per the INITIAL stop (the position is sized by it), kind (0 stop / 1 near take / 2 far take / 3 time / 4 the moved stop), bars"""
    N = len(C); risk = stp * a; sl = fill - s * risk; mae = 0.0; ext = False; pulled = False
    tp1 = fill + s * a; tpn = fill + s * tkn * a; tp2 = fill + s * tk2 * a
    q = 0
    while f + q < N:
        b = f + q
        adv = (fill - L[b]) if s > 0 else (H[b] - fill)
        if (s > 0 and L[b] <= sl) or (s < 0 and H[b] >= sl):
            gap = (s > 0 and O[b] <= sl) or (s < 0 and O[b] >= sl)
            x = O[b] if (gap and q > 0) else sl
            return (s * (x - fill) - (0.0007 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, 4 if (ext and lockstop < stp) else 0, q
        if ext:
            if (s > 0 and H[b] >= tp2) or (s < 0 and L[b] <= tp2):
                return (s * (tp2 - fill) - (0.0004 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, 2, q
        elif pulled:
            if q > 0 and ((s > 0 and H[b] >= tpn) or (s < 0 and L[b] <= tpn)):
                return (s * (tpn - fill) - (0.0004 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, 1, q
        elif q > 0 and ((s > 0 and H[b] >= tp1) or (s < 0 and L[b] <= tp1)):
            if max(mae, adv) < n * a:
                ext = True
                if lockstop < stp:
                    sl = fill - s * lockstop * a
                    if (s > 0 and L[b] <= sl) or (s < 0 and H[b] >= sl):   # the worst order: the dip after the touch
                        return (s * (sl - fill) - (0.0007 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, 4, q
            else:   # the touch bar dipped n first (unknown order): the near take — at 1 ATR here (the bot's take then was 2 ATR
                x = tp1 if tkn >= 1.0 else tpn   # until the dip; a near take below 1 ATR is reached on the way up, a higher one not)
                if tkn > 1.0:
                    pulled = True
                else:
                    return (s * (x - fill) - (0.0004 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, 1, q
        if adv > mae: mae = adv
        if not ext and mae >= n * a: pulled = True
        h = hf if ext else (hn if pulled else hb)
        if q + 1 >= h:
            return (s * (C[b] - fill) - (0.0007 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, 3, q
        q += 1
    b = N - 1
    return (s * (C[b] - fill) - (0.0007 + 0.0003 * (q + 1) * tfh / 24) * fill) / risk, 3, b - f
def run2(p):
    rows = []
    for v in EV:
        Tb, O, H, L, C, atr, pos = BARS[(v["sym"], v["tfh"])]
        R, k, kk = ex2(O, H, L, C, v["fb"], v["s"], v["fill"], v["a"], p["n"], p["tkn"], p["tk2"], p["stp"], p["ls"], p["hb"], p["hn"], p["hf"], v["tfh"])
        rows.append((v["ft"], v["nsc"], v["t"], v["sym"], v["s"], int(Tb[min(len(Tb) - 1, v["fb"] + kk)]) + v["tfh"] * 3600, R,
                     float(np.clip(p["stp"] * v["a"] / v["fill"], 0.002, 0.5)), k))
    rows.sort(key=lambda x: (x[0], x[1], x[2])); busy, act, P = {}, [], []
    for ft, nsc, t, sym, s, end, R, st, k in rows:
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= 20: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st, k))
    P.sort(key=lambda x: x[0]); return np.array(P, float)
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
BASE = dict(n=0.4, tkn=1.0, tk2=2.0, stp=2.0, ls=99.0, hb=32, hn=32, hf=32)
def show(nm, **kw):
    p = dict(BASE, **kw); P = run2(p); t0, t1, R, STv, K = P[:, 0], P[:, 1], P[:, 2], P[:, 3], P[:, 4]
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    fx = []
    for st in ((2024, 1), (2024, 7), (2025, 1), (2025, 4), (2025, 7), (2025, 10)):
        s_ = ts(*st); v = sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0 if st < (2025, 10) else ts(2026, 10), 20, 0.04, -0.025)
        fx.append(f"{st[0] % 100}.{st[1]:02d}→${v[0]:,.0f}")
    print(f"{nm:40s} n{len(R)} {R.mean():+.3f}R WR {np.isin(K, (1, 2)).mean()*100:.0f}% | медиана ${np.median(y[:, 0]):,.0f} 10% ${np.percentile(y[:, 0], 10):,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}%/{np.percentile(y[:, 1], 90)*100:.0f}% | жёстко ${np.median(yh):,.0f} | " + " ".join(fx), flush=True)
show("СЕЙЧАС (v0.99.690)")
print("== стоп")
for v in (1.5, 2.5, 3.0): show(f"стоп {v} ATR", stp=v)
print("== стоп после +1 ATR (у сделок с тейком 2 ATR)")
for v in (1.5, 1.0, 0.5): show(f"стоп переносится на −{v} ATR", ls=v)
print("== тейк после отката")
for v in (0.5, 0.75, 1.25, 1.5): show(f"после отката тейк {v} ATR", tkn=v)
print("== дальний тейк")
for v in (1.75, 2.25, 2.5, 3.0): show(f"дальний тейк {v} ATR", tk2=v)
print("== время")
for v in (48, 64): show(f"сделки с тейком 2 ATR держать {v} свечей", hf=v)
for v in (16, 24): show(f"сделки с тейком 2 ATR держать {v} свечей", hf=v)
for v in (8, 16, 24, 48): show(f"после отката держать {v} свечей", hn=v)
for v in (16, 24, 48): show(f"все сделки держать {v} свечей", hb=v, hn=v, hf=v)
