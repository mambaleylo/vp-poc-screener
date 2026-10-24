"""⚡: a trade's R by how many pool trades were open at its entry (all of the pool, no money sim), by year"""
exec(open("dynrisk.py").read().split("def run(")[0])
o = np.argsort(T0_, kind="stable"); t0, t1, R = T0_[o], T1_[o], R_[o]
nopen = np.zeros(len(t0), np.int64)
for i in range(len(t0)):
    nopen[i] = int(np.sum((t0[:i] <= t0[i]) & (t1[:i] > t0[i])))
yr = (t0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
for Y in range(2022, 2027):
    m = yr == Y
    b = [(nopen < 3), (nopen >= 3) & (nopen < 8), (nopen >= 8)]
    print(Y, " · ".join(f"{nm}: {R[m & bb].mean():+.3f}R WR {np.mean(R[m & bb] > 0)*100:.0f}% ({(m & bb).sum()})" for nm, bb in zip(("открыто 0–2", "3–7", "8+"), b)), flush=True)
m = yr >= 2022
print("все", " · ".join(f"{nm}: {R[m & bb].mean():+.3f}R ({(m & bb).sum()})" for nm, bb in zip(("0–2", "3–7", "8+"), [(nopen < 3), (nopen >= 3) & (nopen < 8), (nopen >= 8)])))
