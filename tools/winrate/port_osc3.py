exec(open("port_osc2.py").read().split("sc = rank_score")[0])
xw = X["wt_1d"]
def W_abs(lo, hi, up=1.25, dn=0.85):
    w = base.copy(); ok = (MD == 0) & np.isfinite(xw); f = np.where(xw <= lo, up, np.where(xw >= hi, dn, 1.0)); w[ok] *= f[ok]; return w
print("медиана wt по ⚡", np.nanmedian(xw[MD == 0]).round(1))
for lo, hi in ((-3, 22), (10, 10), (0, 0), (5, 15), (-10, 30)):
    w = W_abs(lo, hi); print("ср.множ", (w[MD == 0] / base[MD == 0]).mean().round(3), end=" ")
    stats2(f"связка wt1d ≤{lo} ×1.25, ≥{hi} ×0.85", [1, 1, 1, 1], [4, 2, 1, 0.5], w)
w = W_abs(-3, 22); stats2("⚡ один wt1d ≤-3 ×1.25, ≥22 ×0.85", [1, 0, 0, 0], [4, 0, 0, 0], w)
w = W_abs(10, 10); stats2("⚡ один wt1d <10 ×1.25, иначе ×0.85", [1, 0, 0, 0], [4, 0, 0, 0], w)
