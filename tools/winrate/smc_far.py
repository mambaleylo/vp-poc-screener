"""the causal "one level a coin & side & hour": an SMC touch is traded only when no other SMC level of its side was in reach
farther from the price at the hour's start (known then — touched or not later); the deployed exits (4h close / 2 dATR),
the honest order (smc_reach.npz)"""
exec(open("smc_cstop.py").read().split('run("касанием 1 dATR (сейчас)"')[0])
z = np.load("smc_reach.npz"); NF, NN = z["nf"], z["nn"]
assert len(NF) == len(T)
R, K, KD = variant(1.0, 2.0, 4)
idx_all = idx.copy()
def run2(nm, keep):
    global idx
    idx = idx_all[keep[idx_all]]
    sel = select(NEAR); r = R[sel]; y = yr[sel]
    ys = " ".join(f"{Y % 100}:{r[y == Y].mean():+.2f}({(y == Y).sum()})" for Y in range(2022, 2027))
    print(f"{nm:44s} сделок {len(sel):4d} {r.mean():+.3f}R WR {np.mean(r > 0)*100:.0f}% сумма {r.sum():+.0f}R | {ys}", flush=True)
    idx = idx_all
    return sel
ones = np.ones(len(T), bool)
run2("все касания (сейчас)", ones)
run2("только если дальше уровней нет", NF == 0)
run2("пропускать, если дальше >= 2 уровней", NF < 2)
run2("только если ближе есть хоть один (глубокий)", NN > 0)
run2("дальше нет и ближе есть", (NF == 0) & (NN > 0))
print("доля касаний: дальше нет", round(float(np.mean(NF[idx_all] == 0)), 3), "· ближе есть", round(float(np.mean(NN[idx_all] > 0)), 3))
