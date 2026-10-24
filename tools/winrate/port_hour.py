exec(open("port_osc3.py").read().split('print("медиана wt')[0])
w704 = W_abs(-3, 22); hh = ((T0 // 3600) % 24).astype(int)
U, RK = [1, 1, 1, 1], [4, 2, 1, 0.5]
stats2("v704", U, RK, w704)
for up, dn in ((1.25, 0.95), (1.5, 0.9)):
    w = w704.copy(); ix = MD == 0; w[ix] *= np.where((hh[ix] >= 4) & (hh[ix] < 8), up, dn)
    print("ср", (w[ix] / w704[ix]).mean().round(3), end=" "); stats2(f"⚡ 04-08 UTC ×{up}, иначе ×{dn}", U, RK, w)
w = w704.copy(); ix = MD == 0; w[ix] *= 1.03; stats2("контроль ⚡ ×1.03", U, RK, w)
