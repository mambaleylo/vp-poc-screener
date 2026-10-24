"""the bundle's risk split with SMC q0.993 (v0.99.706), the v0.99.704 ⚡ rules"""
exec(open("port_smcq.py").read().split("U = [1, 1, 1, 1]")[0])
rebuild("smcq_0.993_1.0_2.0_4.npy"); U = [1, 1, 1, 1]
for rk in ([4, 2, 1.5, 0.5], [4, 2, 1.5, 1], [4, 2, 1.5, 2], [4, 3, 1.5, 0.5], [4, 1.5, 1.5, 0.5], [4, 2, 1.25, 0.75], [5, 2, 1.5, 0.5], [3.5, 2, 1.5, 0.5]):
    stats2(f"⚡{rk[0]} P/R{rk[1]} SMC{rk[2]} EMA{rk[3]}", U, rk, W_abs(-3, 22))
