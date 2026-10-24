exec(open("port_expect2.py").read().split("ONE = np.ones")[0])
ix = MD == 0; w = W_of(5, 0.625, 1.25); print("⚡ mean weight", w[ix].mean().round(3), "share <5", np.mean(NO[ix] < 5).round(2))
for c in (1.0, round(float(w[ix].mean()), 3), 1.1):
    stats2(f"⚡ x{c} всегда", [1, 0, 0, 0], [4, 0, 0, 0], np.where(MD == 0, c, 1.0))
stats2("⚡ правило v703", [1, 0, 0, 0], [4, 0, 0, 0], w)
stats2("⚡ обратное (<5 x1.25, иначе x0.625)", [1, 0, 0, 0], [4, 0, 0, 0], W_of(5, 1.25, 0.625))
c = round(float(w[ix].mean()), 3)
stats2(f"связка ⚡ x{c} всегда", [1, 1, 1, 1], [4, 2, 1, 0.5], np.where(MD == 0, c, 1.0))
