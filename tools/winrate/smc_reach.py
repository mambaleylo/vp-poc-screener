"""for the causal "one level a coin & side & hour" policy: for every SMC touch event (lv2, fam >= 33) the other SMC levels
of the same side IN REACH at the hour's start (the bot's arm filter: |px - lv| <= 1.5 daily ATR, px = the last 1h close),
touched or not: how many are farther from the price than this one, how many nearer. -> smc_reach.npz (per event, the
lv2 order of load_dir)"""
import os, glob, inspect, numpy as np
import lv_engine as LE
src = inspect.getsource(LE.run)
body = src.split("    J, Fm, S = detect(T, O, H, L, C, LV, P)")[0]
body = body.replace("def run(sym):", "def levels(sym):").replace('''    fn = f"{OUT}/{sym}.npz"
    if os.path.exists(fn):
        return sym, -1
''', "")
exec(body.replace("from", "from") + "\n    return T, C, LV, dat_h\n", LE.__dict__)
SIDE_OF = np.array([0] * 33 + [1 if (n.endswith("bull") or n.endswith("low")) else -1 for n in LE.FAMS[33:]])
NF, NN = [], []
for fn in sorted(glob.glob("lv2/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    sym = os.path.basename(fn)[:-4]
    T, C, LV, dat = LE.levels(sym)
    j = z["j"].astype(int); s = z["side"].astype(int); lv = z["lv"]
    nf = np.zeros(len(j), np.int16); nn = np.zeros(len(j), np.int16)
    for k in range(len(j)):
        if z["fam"][k] < 33: continue
        px = C[j[k] - 1]; d = dat[j[k]]
        if not np.isfinite(d) or d <= 0: continue
        reach = 1.5 * d / 100 * px
        others = LV[33:, j[k]]; sides = SIDE_OF[33:]
        m = np.isfinite(others) & (sides == s[k]) & (np.abs(px - others) <= reach) & ((s[k] * (px - others)) > 0)
        dist = s[k] * (px - others[m]); my = s[k] * (px - lv[k])
        nf[k] = int(np.sum(dist > my * 1.0001)); nn[k] = int(np.sum(dist < my * 0.9999))
    NF.append(nf); NN.append(nn)
    print(sym, len(j), flush=True) if len(NF) % 40 == 0 else None
np.savez("smc_reach.npz", nf=np.concatenate(NF), nn=np.concatenate(NN))
print("done", sum(len(a) for a in NF))
