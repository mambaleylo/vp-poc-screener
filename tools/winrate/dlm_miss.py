"""⚡'s never-filled limits as a module of their own (the user: "как можно с такого огромного количества не исполненных
сделок поиметь пользу? отдельный индикатор со своими настройками?"): every order over its stream's threshold 2023-2026
(money_arm2.orders). (A) the near miss: the price came within d ATR of the level within the order's life without the touch
-> the market entry at the next 1h open (the bounce off the level seen); (B) the model's side at the market: the entry at
the order's own start (no limit). The ⚡ exits (the take 1.2, the close stop 1.75, the emergency 3 ATR, 32 bars) from the
entry; by year, by the order's score (prio = score / the threshold) -> the table, <LABSTORE>/wf/dlm_miss_<v>.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, dlm_engine as DE
TAKE, SOFT, HARD = 1.2, 1.75, 3.0
YRS = (2023, 2024, 2025, 2026); WK = {2023: 52, 2024: 52, 2025: 52, 2026: 43}


def year(t):
    return int(1970 + (t / 86400 + 0.5) / 365.2425)


def entries(OR, mode, d=0.3):
    """-> [(order, the entry hour)] : "near" — the next 1h bar after the first near miss (no touch before), "mkt" — the start"""
    out = []
    for o in OR:
        c = o["coin"]
        if c not in MA2.H1: MA2.H1[c] = DE.load1h(c)
        T1, O1, Hh, Ll, C1, V1 = MA2.H1[c]
        i0, i1 = int(np.searchsorted(T1, o["t"])), int(np.searchsorted(T1, o["until"]))
        if i1 <= i0 or i1 >= len(T1): continue
        if mode == "mkt":
            out.append((o, i0)); continue
        s, lv, a = o["side"], o["lv"], o["atr"]
        for i in range(i0, i1):
            if (Ll[i] <= lv) if s > 0 else (Hh[i] >= lv): break   # touched: the ⚡ limit filled, not ours
            gap = ((Ll[i] - lv) if s > 0 else (lv - Hh[i])) / a
            if gap <= d:
                out.append((o, i + 1)); break
    return out


def mwalk(T1, O1, Hh, Ll, C1, i, s, a, bs, ch):
    """fill_walk's trade from a market entry at the open of 1h bar i (its fill rule would take the chart bar's open) -> (R, t_out) or None"""
    e = O1[i]; sl = e - s * SOFT * a; hsl = e - s * HARD * a; tp = e + s * TAKE * a; risk = SOFT * a
    end = T1[i] // bs * bs + DE.HOLD * bs; q = 0; b = i; res = -1; ex = 0.0
    while b < len(T1) and T1[b] < end:
        if (Ll[b] <= hsl) if s > 0 else (Hh[b] >= hsl):
            ex = O1[b] if (q > 0 and ((O1[b] <= hsl) if s > 0 else (O1[b] >= hsl))) else hsl; res = 0; break
        if q > 0 and ((Hh[b] >= tp) if s > 0 else (Ll[b] <= tp)):
            ex = tp; res = 1; break
        if (T1[b] + 3600) % (ch * 3600) == 0 and ((C1[b] <= sl) if s > 0 else (C1[b] >= sl)):
            ex = C1[b]; res = 4; break
        q += 1; b += 1
    if res < 0:
        if b > i and T1[b - 1] + 3600 >= end:
            b -= 1; ex = C1[b]; res = 3; q = b - i
        else:
            return None
    fee = (DE.FEE_OUT + (DE.FEE_TAKE if res == 1 else DE.FEE_OUT) + DE.FUND * (q + 1) / 24) * e   # a taker entry
    return (s * (ex - e) - fee) / risk, int(T1[b] + 3600), float(e)


def trades(OR, mode, d=0.3):
    out = []
    for o, i in entries(OR, mode, d):
        T1, O1, Hh, Ll, C1, V1 = MA2.H1[o["coin"]]; p = DE.STREAMS[o["stream"]]
        w = mwalk(T1, O1, Hh, Ll, C1, i, o["side"], o["atr"], p["hh"] * 3600, p["ch"])
        if not w: continue
        r, t1, e = w
        out.append({"t0": int(T1[i]), "t1": t1, "r": float(r), "st": SOFT * o["atr"] / e, "sth": HARD * o["atr"] / e, "mod": "dmiss",
                    "sym": o["sym"], "side": o["side"], "e": e, "stream": o["stream"], "prio": o["prio"], "was": o["filled"], "coin": o["coin"]})
    out.sort(key=lambda v: v["t0"]); return out


def table(name, tr):
    rows = []
    for lo, hi, lab in ((0, 9e9, "все"), (0, 1.1, "оценка < 1.1 порога"), (1.1, 1.3, "1.1–1.3"), (1.3, 9e9, "≥ 1.3")):
        x = [v for v in tr if lo <= v["prio"] < hi]
        if not x: continue
        by = {Y: [v["r"] for v in x if year(v["t0"]) == Y] for Y in YRS}
        rows.append(f"   {lab:22s} " + " ".join(f"{Y}: {np.mean(by[Y]):+.3f}R ({len(by[Y]) / WK[Y]:.0f}/нед)" if by[Y] else f"{Y}: —" for Y in YRS))
    print(f"{name}: {len(tr)} сделок, {np.mean([v['r'] for v in tr]):+.3f}R\n" + "\n".join(rows), flush=True)


if __name__ == "__main__":
    OR = MA2.orders()
    for name, mode, d in (("А. почти дошла ≤0.1 ATR", "near", 0.1), ("А. почти дошла ≤0.2 ATR", "near", 0.2), ("А. почти дошла ≤0.3 ATR", "near", 0.3),
                          ("А. почти дошла ≤0.5 ATR", "near", 0.5), ("Б. по рынку на старте лимитки", "mkt", 0)):
        tr = trades(OR, mode, d)
        table(name, tr)
        json.dump(tr, open(f"{M.ST}/wf/dlm_miss_{mode}{d:g}.json", "w"))
    print("miss done", flush=True)
