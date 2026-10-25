"""⚡ on the 152 new coins (replay_nc_*.json, the bot's own code over 2026, the model trained to 2025-12-29): the bundle
from $100 over 2026-01 .. 2026-10 (the only months with the new coins' trades), with / without them; the v0.99.712 rules"""
exec(open("port_w712.py").read().split("U = [1, 1, 1, 1]")[0])
rebuild("smcqx_0.993_3.0_96_1.0_2.0_4.npy", "emaqr_0.96_1.5_4.npy")
OLD = np.array(np.stack([T0, T1, R, ST, STH, BUF, MD, CID], 1))
new = []
for w in range(8):
    j = json.load(open(f"replay_nc_{w}.json"))
    for t in j["trades"]:
        tf = t.get("fbar") or t["t0"]
        if not (j["from"] <= tf < j["to"]) or t.get("r") is None: continue
        e = float(t["entry"]); st = max(0.002, abs(e - t["sl"]) / e); sth = max(st, abs(e - (t.get("hsl") or t["sl"])) / e)
        new.append((float(t.get("t1h") or t["fbar"]), float(t["t_out"]), float(t["r"]), st, sth, 1.25, 0, cid(t["symbol"])))
print("new-coin trades", len(new))
def setup(with_new):
    global NO, base, xw
    A_ = np.array(sorted(list(map(tuple, OLD)) + (new if with_new else [])), float); setrows(A_)
    NO = np.zeros(len(T0), np.int64); dl = np.flatnonzero(MD == 0)
    for k_, i in enumerate(dl):
        prev = dl[:k_]; NO[i] = int(np.sum((T0[prev] <= T0[i]) & (T1[prev] > T0[i])))
    base = W_of(5, 0.625, 1.25); xw = col("wt_1d")
def win(nm, use, rk):
    use = np.array(use, np.bool_); rk = np.array(rk, float) / 100; WG = W_abs(-3, 22); out = []
    for (y, m) in ((2026, 1), (2026, 2), (2026, 3), (2026, 4)):
        s_ = ts(y, m); v = simp(T0, T1, R, ST, STH, BUF, MD, CID, use, rk, int(np.searchsorted(T0, s_)), ts(2026, 10), 0.05, WG)
        out.append(f"с {m:02d}.26: ${v[0]:>6,.0f} просадка {v[1]*100:.0f}% (⚡ {int(v[2][0])} сд)")
    print(f"{nm:40s} " + " | ".join(out), flush=True)

NEWC = {r_[7] for r_ in new}; NEWK = {(r_[0], r_[7]) for r_ in new}
setup(True)
isnew = np.array([(T0[i], CID[i]) in NEWK and MD[i] == 0 for i in range(len(T0))])
_W = W_abs
for k in (0.5, 0.25):
    def W_abs(lo, hi, k=k): w = _W(lo, hi); w[isnew] *= k; return w
    win(f"связка, новые монеты x{k}", [1, 1, 1, 1], [4, 2, 1.5, 1])
W_abs = _W
for rk in (3, 2.5):
    win(f"связка +152, ⚡ {rk}%", [1, 1, 1, 1], [rk, 2, 1.5, 1])
# a market-wide clustering check: the new trades' R shuffled in time
rng = np.random.default_rng(1); Rk = R.copy()
for t_ in range(3):
    R = Rk.copy(); idx = np.flatnonzero(isnew); R[idx] = rng.permutation(Rk[idx])
    win(f"связка +152, R новых перемешан #{t_}", [1, 1, 1, 1], [4, 2, 1.5, 1])
R = Rk
