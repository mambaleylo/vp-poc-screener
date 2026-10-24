"""P/R, SMC, EMA: a trade's R by how many trades of its own module were open at its entry, and by the ⚡ pool's open count"""
import json, numpy as np
d = json.load(open("vp_bt_trades.json"))
def arr(L, tk):
    t0 = np.array([float(x[tk]) for x in L]); t1 = np.array([float(x["x"]) for x in L]); R = np.array([float(x["r"]) for x in L])
    o = np.argsort(t0, kind="stable"); return t0[o], t1[o], R[o]
D0, D1, _ = arr([x for x in d["dlm"] if not x.get("chk")], "f")
def nopen(t0, t1, at):
    return np.array([int(np.sum((t0 <= a) & (t1 > a))) - 0 for a in at])
for mod in ("prv", "smc", "emx"):
    t0, t1, R = arr(d[mod], "f" if "f" in d[mod][0] else "t")
    own = np.array([int(np.sum((t0[:i] <= t0[i]) & (t1[:i] > t0[i]))) for i in range(len(t0))])
    dl = nopen(D0, D1, t0)
    yr = t0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
    q = np.percentile(own, [33, 67]); print(f"== {mod} ({len(R)}) own open terciles {q}")
    for nm, n in (("own", own), ("⚡", dl)):
        cuts = [(n < 1), (n >= 1) & (n < 3), (n >= 3)] if nm == "own" else [(n < 3), (n >= 3) & (n < 8), (n >= 8)]
        lab = ("0", "1–2", "3+") if nm == "own" else ("0–2", "3–7", "8+")
        print(" ", nm, "all:", " · ".join(f"{l}: {R[c].mean():+.3f}R WR {np.mean(R[c]>0)*100:.0f}% ({c.sum()})" for l, c in zip(lab, cuts)))
        for Y in sorted(set(yr)):
            m = yr == Y
            print("    ", Y, " · ".join(f"{l}: {R[m&c].mean() if (m&c).sum() else float('nan'):+.2f} ({(m&c).sum()})" for l, c in zip(lab, cuts)))
