"""🔗 A Markov-chain indicator (the user: "можно новый индикатор на основе его сделать попробовать"): a coin's 4 h candles as a
Markov chain — the state = the kinds of its last two 4 h moves (the close-to-close move / the previous ATR14 in 5 bins: < -1,
-1..-0.3, -0.3..0.3, 0.3..1, > 1) x the market's regime (hmm_regime.py: calm / active / panic, the filtered one known at the
bar's close) = 75 states. Per year, from the years before only (all the bot's 127 coins pooled): each state's mean move of the
next 6 bars (24 h) in ATR and its count. A bar whose state leans > THR ATR one way (n >= NMIN) -> a trade that way at the
bar's close: the stop SL ATR, take TP ATR, out after HOLD bars (4 h bars; the stop first, no take in the entry bar), costs
0.1% + funding 0.03%/day; R per the stop. The pool as the bot's: one trade a coin, at most 12 a side, the strongest lean first.
By year; the 127 coins and the 83 never-seen ones apart.
usage: python3 markov_ind.py [THR] [SL] [TP] [HOLD]   (candles: /home/user/ema211/data/1h)"""
import os, sys, json, calendar, numpy as np
D1H = os.environ.get("CANDLES", "/home/user/ema211/data/1h"); ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
THR = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3; SL = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
TP = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0; HOLD = int(sys.argv[4]) if len(sys.argv) > 4 else 12; NMIN = 300; FWD = 6
ts = lambda y: calendar.timegm((y, 1, 1, 0, 0, 0))
C127 = set(open("/home/user/ema211/c127.txt").read().replace(".csv", "").split())
HM = np.load(f"{ST}/wf/hmm_regime.npz"); HP = np.column_stack([HM["p_calm"], HM["p_act"], HM["p_panic"]])
def regime(t):   # the state known at t (the last 4 h HMM bar closed by t); -1 before the walk-forward (2022)
    i = np.searchsorted(HM["T"], t, side="right") - 1
    r = np.full(len(t), -1)
    ok = (i >= 0) & np.isfinite(HP[np.clip(i, 0, None)]).all(1)
    r[ok] = np.argmax(HP[i[ok]], 1); return r
def bars4(sym):
    a = np.loadtxt(f"{D1H}/{sym}.csv", delimiter=",", ndmin=2); t = a[:, 0].astype(np.int64); k = np.r_[True, np.diff(t) > 0]; a, t = a[k], t[k]
    g = t // 14400; st = np.flatnonzero(np.r_[True, g[1:] != g[:-1]]); en = np.r_[st[1:], len(t)]; full = (en - st) == 4
    st, en = st[full], en[full]
    T = g[st] * 14400; O = a[st, 1]; H = np.maximum.reduceat(a[:, 2], st)[: len(st)] if False else np.array([a[s:e, 2].max() for s, e in zip(st, en)])
    L = np.array([a[s:e, 3].min() for s, e in zip(st, en)]); C = a[en - 1, 4]
    return T, O, H, L, C
def atr(H, L, C, n=14):
    tr = np.maximum(H - L, np.maximum(np.abs(H - np.r_[C[0], C[:-1]]), np.abs(L - np.r_[C[0], C[:-1]]))); out = np.empty(len(tr)); out[0] = tr[0]
    for i in range(1, len(tr)): out[i] = out[i - 1] + (tr[i] - out[i - 1]) / n
    return out
EDG = np.array([-1.0, -0.3, 0.3, 1.0])
rows = []
coins = sorted(f[:-4] for f in os.listdir(D1H) if f.endswith(".csv"))
for c in coins:
    T, O, H, L, C = bars4(c)
    if len(C) < 400: continue
    A = atr(H, L, C); mv = np.r_[np.nan, np.diff(C)] / np.r_[np.nan, A[:-1]]
    b = np.digitize(mv, EDG); s2 = np.r_[0, b[:-1] * 5 + b[1:]]   # the state of bar k = (bin k-1, bin k), index k
    k = np.arange(1, len(C)); tc = T[k] + 14400; rg = regime(tc)
    okA = (A[k] > 0.004 * C[k]) & (np.r_[A[0], A[:-1]][k] > 0.004 * C[k]) & np.isfinite(mv[k])   # a flat price (ATR ~ 0, e.g. before the listing): no state
    k, tc, rg = k[okA], tc[okA], rg[okA]
    fwd = np.full(len(k), np.nan); ok = k + FWD < len(C); fwd[ok] = (C[k[ok] + FWD] - C[k[ok]]) / A[k[ok]]
    rows.append(dict(c=c, k=k, tc=tc, st=s2[k] + 25 * np.maximum(rg, 0), rg=rg, fwd=fwd, A=A[k], bars=(T, O, H, L, C)))
    if len(rows) % 50 == 0: print(len(rows), c, flush=True)
print("монет", len(rows), flush=True)
def walk(O, H, L, C, j, s, a):   # enter at C[j], the next bars
    e = C[j]; risk = SL * a; stp = e - s * risk; tp = e + s * TP * a; n = len(C); end = min(n - 1, j + HOLD)
    if j + HOLD >= n: return None, None
    for q in range(j + 1, end + 1):
        if (s > 0 and L[q] <= stp) or (s < 0 and H[q] >= stp):
            x = O[q] if ((s > 0 and O[q] <= stp) or (s < 0 and O[q] >= stp)) else stp; k_ = q - j; break
        if (s > 0 and H[q] >= tp) or (s < 0 and L[q] <= tp):
            x = tp; k_ = q - j; break
    else:
        x = C[end]; k_ = end - j
    return s * (x - e) / risk - (0.001 + 0.0003 * k_ / 6) * e / risk, int(k_)
res = {}
for Y in range(2022, 2027):
    tr_s, tr_f = [], []
    for r in rows:
        m = (r["c"] in C127) & (r["tc"] < ts(Y) - FWD * 14400 - 86400) & np.isfinite(r["fwd"]) & (r["rg"] >= 0)
        tr_s.append(r["st"][m]); tr_f.append(r["fwd"][m])
    s_, f_ = np.concatenate(tr_s), np.concatenate(tr_f)
    if len(s_) < 20000:
        # before the HMM's years: no regime -> skip the year
        continue
    cnt = np.bincount(s_, minlength=75); mean = np.bincount(s_, weights=f_, minlength=75) / np.maximum(cnt, 1)
    lean = np.where(cnt >= NMIN, mean, 0.0)
    cand = []
    for r in rows:
        m = (r["tc"] >= ts(Y)) & (r["tc"] < ts(Y + 1)) & (r["rg"] >= 0)
        for i in np.flatnonzero(m & (np.abs(lean[r["st"]]) > THR)):
            cand.append((int(r["tc"][i]), -abs(lean[r["st"][i]]), r["c"], int(np.sign(lean[r["st"][i]])), int(r["k"][i]), float(r["A"][i]), r["bars"]))
    cand.sort(key=lambda x: (x[0], x[1])); busy, act, out = {}, [], []
    for t, sc, c, s, j, a, (T, O, H, L, C) in cand:
        if busy.get(c, 0) > t: continue
        act = [x for x in act if x[0] > t]
        if sum(1 for x in act if x[1] == s) >= 12: continue
        R, k_ = walk(O, H, L, C, j, s, a)
        if R is None: continue
        end = t + k_ * 14400; busy[c] = end; act.append((end, s)); out.append((t, c, s, R))
    for grp, keep in (("127", lambda c: c in C127), ("83 невиденных", lambda c: c not in C127)):
        rr = np.array([x[3] for x in out if keep(x[1])]); ss = np.array([x[2] for x in out if keep(x[1])])
        if len(rr):
            print(f"{Y} {grp}: {len(rr)} сделок, {rr.mean():+.3f}R, WR {(rr > 0).mean() * 100:.0f}%, лонги {int((ss > 0).sum())} {rr[ss > 0].mean() if (ss > 0).any() else 0:+.2f}R, "
                  f"шорты {int((ss < 0).sum())} {rr[ss < 0].mean() if (ss < 0).any() else 0:+.2f}R", flush=True)
    top = np.argsort(-np.abs(lean))[:4]
    print(f"   {Y}: сильнейшие состояния", [(int(z) // 25, int(z) % 25 // 5, int(z) % 5, round(float(lean[z]), 2), int(cnt[z])) for z in top], flush=True)
    res[Y] = out
print(f"markov done THR {THR} SL {SL} TP {TP} HOLD {HOLD}", flush=True)
