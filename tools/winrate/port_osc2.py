exec(open("port_osc.py").read().split("base = W_of")[0])
base = W_of(5, 0.625, 1.25)
exec("def W_osc" + open("port_osc.py").read().split("def W_osc")[1].split("for nm, names")[0])
sc = rank_score(["wt_1d"]); ix = (MD == 0) & np.isfinite(sc)
w = W_osc(sc, 0.4, 0.6, 1.25, 0.85); print("средний множитель ⚡", (w[ix] / base[ix]).mean().round(3))
stats2("⚡ контроль ×1.04 всегда", [1, 0, 0, 0], [4, 0, 0, 0], np.where(MD == 0, base * 1.04, 1.0))
stats2("связка контроль ⚡ ×1.04", [1, 1, 1, 1], [4, 2, 1, 0.5], np.where(MD == 0, base * 1.04, 1.0))
stats2("⚡ обратное ×0.85/×1.25", [1, 0, 0, 0], [4, 0, 0, 0], W_osc(sc, 0.4, 0.6, 0.85, 1.25))
for lq, hq in ((0.3, 0.7), (0.5, 0.5), (0.33, 0.67)):
    stats2(f"связка wt {lq}/{hq} ×1.25/×0.85", [1, 1, 1, 1], [4, 2, 1, 0.5], W_osc(sc, lq, hq, 1.25, 0.85))
# the fixed cut-offs for the bot: the 40% / 60% of the signed daily wt1 over all the pool's trades, and by year
x = X["wt_1d"][(MD == 0) & np.isfinite(X["wt_1d"])]; yy = YR[(MD == 0) & np.isfinite(X["wt_1d"])]
print("порог 40%/60% все:", np.quantile(x, [0.4, 0.6]).round(2), {int(Y): np.quantile(x[yy == Y], [0.4, 0.6]).round(1).tolist() for Y in range(2022, 2027)})
