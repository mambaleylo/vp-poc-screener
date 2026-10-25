"""⚡ risk by the model's score: the trades of a higher score (vs the same stream's trades of the EARLIER years — causal)
-> more risk; R by score tercile per year, then the bundle's money (the v0.99.712 rules x the score weight)"""
exec(open("port_w712.py").read().split("U = [1, 1, 1, 1]")[0])
rebuild("smcqx_0.993_3.0_96_1.0_2.0_4.npy", "emaqr_0.96_1.5_4.npy")
SCm = {}
for p in PC: SCm[(int(p[0]), cid(p[5]["sym"]))] = (-float(p[5]["key"][2]), int(p[5]["tfh"]))
SCR = np.full(len(T0), np.nan); TF = np.zeros(len(T0), np.int64)
for i in range(len(T0)):
    if MD[i] == 0:
        v = SCm.get((int(T0[i]), int(CID[i])))
        if v: SCR[i], TF[i] = v
YR = T0.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
print("⚡ rows", int((MD == 0).sum()), "with a score", int(np.isfinite(SCR).sum()), flush=True)
PCT = np.full(len(T0), np.nan)   # the causal percentile: vs the same stream's earlier years
for tf in (2, 4):
    for Y in range(2022, 2027):
        cur = (MD == 0) & (TF == tf) & (YR == Y) & np.isfinite(SCR); past = (MD == 0) & (TF == tf) & (YR < Y) & np.isfinite(SCR)
        if past.sum() < 50: continue
        ref = np.sort(SCR[past]); PCT[cur] = np.searchsorted(ref, SCR[cur]) / len(ref)
ok = np.isfinite(PCT)
print("with a causal percentile", int(ok.sum()))
for Y in range(2023, 2027):
    m = ok & (YR == Y)
    if m.sum() < 30: continue
    lo, mid, hi = m & (PCT < 1 / 3), m & (PCT >= 1 / 3) & (PCT < 2 / 3), m & (PCT >= 2 / 3)
    print(f"  {Y}: низ {R[lo].mean():+.3f} ({lo.sum()}) · сер {R[mid].mean():+.3f} ({mid.sum()}) · верх {R[hi].mean():+.3f} ({hi.sum()})")
for q_ in (0.5, 0.8, 0.9):
    m = ok & (PCT >= q_); print(f"  выше {q_:.0%} прошлых: {R[m].mean():+.3f} ({m.sum()}) vs остальные {R[ok & ~(PCT >= q_)].mean():+.3f}")
WB = W_abs(-3, 22)
def wsc(lo_k, hi_k, cut_lo=1 / 3, cut_hi=2 / 3):
    w = WB.copy(); f = np.where(PCT < cut_lo, lo_k, np.where(PCT >= cut_hi, hi_k, 1.0)); w[ok] *= f[ok]; return w
U = [1, 1, 1, 1]; RK = [4, 2, 1.5, 1]
stats2("сейчас (v0.99.712)", U, RK, WB)
for lo_k, hi_k in ((0.8, 1.25), (0.7, 1.3), (1.0, 1.25), (0.8, 1.0), (0.6, 1.5)):
    stats2(f"оценка: низ x{lo_k}, верх x{hi_k}", U, RK, wsc(lo_k, hi_k))
stats2("оценка: выше 80% прошлых x1.5", U, RK, wsc(1.0, 1.5, 0.0, 0.8))
print("fin")
