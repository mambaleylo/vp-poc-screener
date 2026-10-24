"""the daily WaveTrend rule for SMC (as ⚡: against the trade -> more) and EMA / P/R (with the trade -> more), on top of v0.99.704"""
exec(open("port_osc3.py").read().split('print("медиана wt')[0])
G2 = json.load(open("gh_states.json"))
GM = {(MOD[r["mod"]], cid(r["s"]), round(r["te"])): r for r in G2}
WTo = np.array([GM.get((int(MD[i]), int(CID[i]), round(float(T0[i]))), {}).get("wt_1d", np.nan) if MD[i] != 0 else np.nan for i in range(len(T0))])
print("найдено", {k: np.isfinite(WTo[MD == k]).mean().round(2) for k in (1, 2, 3)})
w704 = W_abs(-3, 22)
def add(w, md, against, with_):
    w = w.copy(); ix = (MD == md) & np.isfinite(WTo); w[ix] *= np.where(WTo[ix] <= -3, against, np.where(WTo[ix] >= 22, with_, 1.0)); return w
U, RK = [1, 1, 1, 1], [4, 2, 1, 0.5]
stats2("v704", U, RK, w704)
stats2("SMC против ×1.25, по ходу ×0.85", U, RK, add(w704, 2, 1.25, 0.85))
stats2("EMA против ×0.85, по ходу ×1.25", U, RK, add(w704, 3, 0.85, 1.25))
stats2("P/R против ×0.85, по ходу ×1.25", U, RK, add(w704, 1, 0.85, 1.25))
stats2("SMC + EMA", U, RK, add(add(w704, 2, 1.25, 0.85), 3, 0.85, 1.25))
stats2("SMC + EMA + P/R", U, RK, add(add(add(w704, 2, 1.25, 0.85), 3, 0.85, 1.25), 1, 0.85, 1.25))
stats2("контроль: SMC ×1.05, EMA ×1.1, P/R ×1.07", U, RK, add(add(add(w704, 2, 1.05, 1.05), 3, 1.1, 1.1), 1, 1.07, 1.07))
