"""the audit, part 3: the gap between the train data and the test year. The 2026 models were trained on the events before
2025-12-29 (3 days); an event's label looks up to ~6 days ahead (alive 4 bars + 32 bars), so the last train labels used
the prices of 2026-01-01..04. Here: the same 20 models per stream with a 10-day gap; the 2026 events above the
threshold, their pool with the deployed exits, vs the 3-day gap's (dlm4_export4 / 5)."""
exec(open("dlm4_export4.py").read().split("out_streams, EV, FN = [], [], None")[0])
import importlib
exec(open("tkext.py").read().split("\nBARS = {}")[0].split("exec(open(\"pool2h.py\")")[0].replace("exec(open(\"best_money.py\")", "exec(open(\"best_money.py\")"))
exec("@njit\ndef ex" + open("tkext.py").read().split("@njit\ndef ex")[1].split("\ndef run")[0])
exec("def merged" + open("dlm4_export4.py").read().split("def merged")[1].split("out_streams, EV, FN")[0])   # best_money's merged() shadowed it
res = {}
for S in STREAMS:
    os.environ["TFH"] = str(S["tfh"]); E = importlib.import_module(S["eng"])
    X = merged(S["dr"], S["fi"]); T = X["t"]; TR = ~X["chk"] & ~X["new"]; y = np.clip(X["R"][S["ex"]], -1.5, 1.5)
    te = T >= ts(2026); ref = TR & (T >= ts(2025)) & (T < ts(2026))
    out = {}
    for gap in (3, 10):
        tr = np.flatnonzero(TR & (T < ts(2026) - gap * 86400))
        pred = np.zeros(len(T))
        for F in (X["F"], X["F33"]):
            for seed in range(10):
                m = lgb.LGBMRegressor(random_state=seed, **pr).fit(F[tr], y[tr])
                idx = np.flatnonzero(te); pred[idx] += m.predict(F[idx]) / 20
        thr = float(np.quantile(np.load(S["scf"], allow_pickle=True)["THR"].item()[2026], Q))   # the research's: the 2025 out-of-sample scores
        out[gap] = (pred, thr)
        print(S["name"], "gap", gap, "thr", round(thr, 4), "selected 2026", int((te & (pred >= thr) & ~X["usdc"]).sum()), flush=True)
    res[S["name"]] = (X, E, out)
import pickle
pickle.dump({k: {"t": v[0]["t"], "out": v[2]} for k, v in res.items()}, open("embargo.pkl", "wb"))
# the pools
BARS = {}
def evs(name, gap, S):
    X, E, out = res[name]; pred, thr = out[gap]; T = X["t"]; L_ = []
    for i in np.flatnonzero((T >= ts(2026)) & (pred >= thr) & ~X["usdc"]):
        sym = X["names"][X["sym"][i]]; s = int(X["side"][i]); t = int(T[i])
        if (sym, S["tfh"]) not in BARS:
            Tb, O, H, L, C, Vv = E.load15(sym); BARS[(sym, S["tfh"])] = (Tb, O, H, L, C, E.wilder(H, L, C, 14), {int(x): j for j, x in enumerate(Tb)})
        Tb, O, H, L, C, atr, pos = BARS[(sym, S["tfh"])]; bi = pos[t]; a = float(atr[bi])
        lv = ((L[bi] if s > 0 else H[bi]) if S["anchor"] == "wick" else C[bi]) - s * S["depth_atr"] * a
        fb = next(b for b in range(bi + 1, bi + 5) if ((L[b] <= lv) if s > 0 else (H[b] >= lv)))
        fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
        R, k, kk = ex(O, H, L, C, fb, s, fill, a, 0.4, 1.0, 0, S["tfh"])
        L_.append(dict(ft=int(Tb[fb]), nsc=-float(pred[i]), t=t, sym=sym, s=s, end=int(Tb[fb + kk]) + S["tfh"] * 3600, R=float(R), stop=float(np.clip(2 * a / fill, 0.002, 0.5))))
    return L_
for gap in (3, 10):
    ev = evs("wick4h", gap, STREAMS[0]) + evs("close2h", gap, STREAMS[1]); ev.sort(key=lambda e: (e["ft"], e["nsc"], e["t"]))
    busy, act, P = {}, [], []
    for e in ev:
        if busy.get((e["sym"], e["s"]), 0) > e["ft"]: continue
        act = [x for x in act if x[0] > e["ft"]]
        if sum(1 for x in act if x[1] == e["s"]) >= 20: continue
        busy[(e["sym"], e["s"])] = e["end"]; act.append((e["end"], e["s"])); P.append(e)
    A = np.array(sorted((e["ft"], e["end"], e["R"], e["stop"]) for e in P), float); t0, t1, R, STv = A.T
    w1 = t0 < ts(2026) + 7 * 86400
    v = sim(t0, t1, R, STv, 0, ts(2026, 10), 20, 0.04, -0.025)
    print(f"зазор {gap} дн: сделок 2026 {len(R)} {R.mean():+.3f}R; первая неделя {w1.sum()} {R[w1].mean():+.3f}R, остальное {R[~w1].mean():+.3f}R; 2026 с $100 → ${v[0]:,.0f}", flush=True)
