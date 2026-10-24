"""the bundle's risk split re-tuned with the v703 ⚡ load rule and the honest close-stop lists"""
exec(open("port_expect2.py").read().split("ONE = np.ones")[0])
W = W_of(5, 0.625, 1.25); U = [1, 1, 1, 1]
for rk in ([4, 2, 1, 0.5], [4, 1, 1, 0.5], [4, 3, 1, 0.5], [4, 2, 0.5, 0.5], [4, 2, 2, 0.5], [4, 2, 1, 1], [4, 2, 1, 2], [4, 2, 2, 1],
           [4, 3, 2, 1], [4, 1, 2, 1], [3, 2, 1, 0.5], [3, 2, 2, 1], [5, 2, 1, 0.5], [4, 2, 1.5, 0.75], [4, 2.5, 1.5, 1]):
    stats2(f"⚡{rk[0]} P/R{rk[1]} SMC{rk[2]} EMA{rk[3]}", U, rk, W)
