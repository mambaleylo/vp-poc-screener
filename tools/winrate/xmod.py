"""the bundle's own signals as indicators of each other: at each P/R / SMC / EMA / ⚡ trade's entry — the ⚡ fills of the
same / the other side in the last 6 / 24 h (the research pool, known at their 15m close), the other modules' entries of the
same / the other side in the last 24 / 72 h, the same coin's other-module signal in the last 72 h, the trades open in the
same side over all modules; the hour / weekday. Per feature: terciles by year, then a walk-forward weight (the past years
pick the side) -> the test years' weighted R vs plain"""
import json, numpy as np, collections
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
z = np.load("dlm_fills.npz"); FT, FS = z["te"].astype(np.int64), z["side"]; o = np.argsort(FT); FT, FS = FT[o], FS[o]
norm = lambda s: s.replace("_USDT", "").replace("USDT", "").replace("1000", "")
T = []   # (module, entry, exit, side, coin, R)
for mod, tk in (("prv", "t"), ("smc", "t"), ("emx", "t"), ("dlm", "f")):
    for t in B[mod]:
        if t.get("r") is None or not t.get("x"): continue
        if mod == "dlm" and t.get("chk"): continue
        T.append((mod, int(t.get(tk) or t["t"]), int(t["x"]), int(t["d"]), norm(t["s"]), float(t["r"])))
T.sort(key=lambda x: x[1])
ent = collections.defaultdict(list)
for m, a, b, s, c, r in T: ent[m].append((a, b, s, c))
def cnt_fills(t, s, h, same=True):
    i0, i1 = np.searchsorted(FT, t - h * 3600, side="right"), np.searchsorted(FT, t, side="right")
    x = FS[i0:i1]; return int(np.sum(x == s)) if same else int(np.sum(x == -s))
rows = []
for m, a, b, s, c, r in T:
    if m == "dlm": continue
    f = {"mod": m, "R": r, "y": int(np.datetime64(a, "s").astype("datetime64[Y]").astype(int) + 1970)}
    f["dlm_same_6h"] = cnt_fills(a, s, 6); f["dlm_opp_6h"] = cnt_fills(a, s, 6, False)
    f["dlm_same_24h"] = cnt_fills(a, s, 24); f["dlm_opp_24h"] = cnt_fills(a, s, 24, False)
    oth = [x for mm, lst in ent.items() if mm not in (m, "dlm") for x in lst]
    f["oth_same_72h"] = sum(1 for (a2, b2, s2, c2) in oth if a - 72 * 3600 < a2 <= a and s2 == s)
    f["oth_opp_72h"] = sum(1 for (a2, b2, s2, c2) in oth if a - 72 * 3600 < a2 <= a and s2 == -s)
    f["coin_oth_72h"] = sum(s2 for mm, lst in ent.items() if mm != m for (a2, b2, s2, c2) in lst if c2 == c and a - 72 * 3600 < a2 <= a) * s   # + = the same side
    f["open_same"] = sum(1 for mm, lst in ent.items() if mm != m for (a2, b2, s2, c2) in lst if a2 <= a < b2 and s2 == s)
    f["open_opp"] = sum(1 for mm, lst in ent.items() if mm != m for (a2, b2, s2, c2) in lst if a2 <= a < b2 and s2 == -s)
    f["hour"] = (a % 86400) // 3600; f["wday"] = int((a // 86400 + 3) % 7)
    rows.append(f)
json.dump(rows, open("xmod.json", "w"))
keys = [k for k in rows[0] if k not in ("mod", "R", "y")]
UP, DN = 1.25, 0.8
for mod in ("prv", "smc", "emx"):
    rr = [x for x in rows if x["mod"] == mod]; R = np.array([x["R"] for x in rr]); Y = np.array([x["y"] for x in rr])
    print(f"== {mod} ({len(rr)}) {R.mean():+.3f}R")
    for k in keys:
        x = np.array([q[k] for q in rr], float)
        if k in ("hour", "wday"): continue
        q1, q2 = np.quantile(x, [1 / 3, 2 / 3])
        lo, hi = x <= q1, x > q2
        if q1 == q2: lo, hi = x <= q1, x > q1
        if lo.sum() < 30 or hi.sum() < 30: continue
        yd = [(y, R[hi & (Y == y)].mean() - R[lo & (Y == y)].mean()) for y in sorted(set(Y)) if (hi & (Y == y)).sum() >= 8 and (lo & (Y == y)).sum() >= 8]
        d = R[hi].mean() - R[lo].mean()
        # walk-forward: each test year's weight side from the earlier years' difference
        num = den = base = 0.0; tested = 0
        for ty in sorted(set(Y)):
            past = Y < ty
            if (hi & past).sum() < 20 or (lo & past).sum() < 20: continue
            sg = np.sign(R[hi & past].mean() - R[lo & past].mean()); te = Y == ty
            w = np.ones(te.sum()); xx = x[te]
            good, bad = ((xx > q2), (xx <= q1)) if sg > 0 else ((xx <= q1), (xx > q2))
            if q1 == q2: good, bad = ((xx > q1), (xx <= q1)) if sg > 0 else ((xx <= q1), (xx > q1))
            w[good] = UP; w[bad] = DN; num += (w * R[te]).sum() / w.mean(); base += R[te].sum(); tested += te.sum()
        wf = (num - base) / tested if tested else 0
        print(f"  {k:13s} низ {R[lo].mean():+.2f} ({lo.sum()}) · верх {R[hi].mean():+.2f} ({hi.sum()}) | по годам " + " ".join(f"{y}:{v:+.2f}" for y, v in yd) + f" | вперёд {wf:+.3f}R/сд на {tested}")
    hr = np.array([q["hour"] for q in rr]); wd = np.array([q["wday"] for q in rr])
    print("  часы (UTC, по 4):", " ".join(f"{4*g:02d}:{R[hr // 4 == g].mean():+.2f}({(hr // 4 == g).sum()})" for g in range(6)))
    print("  дни (Пн..Вс):", " ".join(f"{R[wd == g].mean():+.2f}({(wd == g).sum()})" for g in range(7)))
