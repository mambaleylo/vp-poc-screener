"""every ⚡ order of the bot 2023-2026 scored by the DEPLOYED trees (vp_dlm_model.json, its own threshold per stream) — the
bot as it is, for the money (money_arm2.orders(suf="_dep")); the trees flattened and walked in numba (the bot's zm_tree_pred:
a nan goes the node's default side, x <= thr left). The deployed model was trained to 2025-12-29: 2026 is out of sample,
2023-2025 in its training (an upper bound there). -> <LABSTORE>/wf/allorders_<stream>_dep.npz"""
import os, sys, json, time, numpy as np
from numba import njit
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE, treevec as TV
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
MJ = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json")); A0 = 1672531200   # 2023-01-01
C = json.load(open(f"{ST}/feat_coins.json"))
@njit(cache=True)
def walk(X, Fa, Ta, NLa, La, Ra, Va, roots, nmod, per):
    out = np.zeros(len(X))
    for r in range(len(X)):
        s = 0.0
        for k in range(len(roots)):
            i = roots[k]
            while Fa[i] >= 0:
                v = X[r, Fa[i]]
                if v != v: i = La[i] if NLa[i] else Ra[i]
                elif v <= Ta[i]: i = La[i]
                else: i = Ra[i]
            s += Va[i]
        out[r] = s / nmod
    return out
def pack(models):
    Fa, Ta, NLa, La, Ra, Va, roots = [], [], [], [], [], [], []; off = 0
    for m in models:
        for t in m:
            F, T, NL, L, R, V = TV.flat(t); roots.append(off)
            Fa.append(F); Ta.append(T); NLa.append(NL); La.append(np.where(L >= 0, L + off, -1)); Ra.append(np.where(R >= 0, R + off, -1)); Va.append(V); off += len(F)
    c = np.concatenate
    return c(Fa).astype(np.int64), c(Ta), c(NLa), c(La).astype(np.int64), c(Ra).astype(np.int64), c(Va), np.array(roots, np.int64), len(models)
for S in MJ["streams"]:
    stream = S["name"]; P = pack(S["models"]); p = DE.STREAMS[stream]; bs = p["hh"] * 3600; B = DE.btc_ctx(stream); t0 = time.time()
    out = {k: [] for k in ("coin", "t", "side", "lv", "atr", "score", "thr", "filled", "t1h", "fill", "R", "kind", "tout", "grp")}
    for k, c in enumerate(C["base"]):
        h1 = DE.load1h(c); ev = DE.features(c, stream, B, h1)
        if ev is None: continue
        tsc = ev["t"] + bs; ii = np.flatnonzero(tsc >= A0)
        if not len(ii): continue
        sc = walk(np.ascontiguousarray(ev["f"][ii].astype(np.float64)), *P[:7], P[7], 0)
        ok = sc >= S["thr"]; ii, sc = ii[ok], sc[ok]
        if not len(ii): continue
        T1, O1, H1, L1, C1, V1 = h1
        fl, t1h, fill, R, kind, tout = DE.fill_walk(T1, O1, H1, L1, C1, tsc[ii], ev["side"][ii].astype(np.int64), ev["lv"][ii], ev["atr"][ii], bs, p["ch"],
                                                    DE.ALIVE, DE.HOLD, S["take_atr"], S["stop_atr"], S["hard_stop_atr"], DE.FEE_IN, DE.FEE_TAKE, DE.FEE_OUT, DE.FUND)
        for key, v in (("coin", np.full(len(ii), c)), ("t", tsc[ii]), ("side", ev["side"][ii]), ("lv", ev["lv"][ii]), ("atr", ev["atr"][ii]), ("score", sc),
                       ("thr", np.full(len(ii), S["thr"])), ("filled", fl), ("t1h", t1h), ("fill", fill), ("R", R), ("kind", kind), ("tout", tout), ("grp", np.full(len(ii), "base"))):
            out[key].append(v)
        if k % 30 == 0: print(stream, k, c, f"{time.time() - t0:.0f}s", flush=True)
    O = {k: np.concatenate(v) for k, v in out.items()}; np.savez_compressed(f"{ST}/wf/allorders_{stream}_dep.npz", **O)
    fr = O["filled"].astype(bool); yr = (O["t"] / 86400 / 365.2425 + 1970).astype(int)
    print(f"{stream}: ордеров {len(fr)}, исполнено {fr.sum()}, R {np.nanmean(O['R'][fr]):+.3f}; " + " ".join(f"{Y}: {np.nanmean(O['R'][fr & (yr == Y)]):+.3f} ({(fr & (yr == Y)).sum()})" for Y in (2023, 2024, 2025, 2026)), flush=True)
print("allorders dep done", flush=True)
