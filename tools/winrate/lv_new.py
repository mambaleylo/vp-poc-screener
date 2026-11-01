"""SMC / HTF on more coins: the research engine's levels (lv_engine.run -> lv2/<coin>.npz) on the bot's 210 and the 226 new
Binance coins; their 2026 touches (Jan..Oct — the deployed models trained before 2026: out of sample for every coin) scored
by the deployed models (treevec = the bot's zm_tree_pred), the bot's filters (the module's families / side, in reach at
the hour's start: |price - level| <= 1.5 dATR), one position a coin, the side cap; the exits of the model's rule (the
stop at the stop_close_h close 1 dATR, the emergency hard_x dATR, take 3R, 96 h; SMC's break-even not modelled). The
trades' R of the bot's coins vs the new ones. -> <LABSTORE>/wf/lv_new_<mod>.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "new_ind"))
import lv_engine as LE, treevec as TV
from numba import njit
from multiprocessing import Pool
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); C = json.load(open(f"{ST}/feat_coins.json"))
A0, A1 = 1767225600, 1793491200   # 2026-01-01 .. 2026-11-01
def build(c):
    try:
        if not os.path.exists(f"{LE.OUT}/{c}.npz"): LE.run(c)
        return c, True
    except Exception as e:
        return c, repr(e)[:120]
@njit(cache=True)
def wk(O, H, L, C, Tb, j, s, fill, datr, hard_a, take, hold, kh):
    risk = fill * datr / 100; ssl = fill - s * risk; hsl = fill - s * hard_a * risk; tp = fill + s * take * risk
    n = len(C); e = min(n, j + hold)
    for q in range(e - j):
        b = j + q
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return s * (x - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 0
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            return s * (tp - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 1
        if (Tb[b] + 3600) % (kh * 3600) == 0 and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return s * (C[b] - fill) / risk - (0.001 + 0.0003 * (q + 1) / 24) * fill / risk, q + 1, 4
    b = e - 1
    return s * (C[b] - fill) / risk - (0.001 + 0.0003 * (e - j) / 24) * fill / risk, e - j, 3
def module(mod):
    m = json.load(open(f"/home/user/vp-poc-screener/vp_{mod}_model.json")); fams = m["fams"]
    want = {(fams.index(f) if isinstance(f, str) else int(f)) for f in m["smc_fams" if mod == "smc" else "htf_fams"]}   # names (SMC) or indices (HTF)
    rule = m["rule"]; cap = int(m.get("side_cap") or 12)
    ev = []
    for grp in ("base", "new"):
        for c in C[grp]:
            fn = f"{LE.OUT}/{c}.npz"
            if not os.path.exists(fn): continue
            z0 = np.load(fn); z = {k: z0[k] for k in z0.files}
            k = np.flatnonzero((z["t"] >= A0) & (z["t"] < A1) & np.isin(z["fam"], list(want)) & ((z["side"] > 0) if mod == "htf" else True))
            if not len(k): continue
            T, O, H, L, Cc, Vv = LE.load_np(c); J = z["j"][k].astype(int)
            px = np.where(J >= 1, Cc[np.maximum(J - 1, 0)], np.nan); lv = z["lv"][k]; datr = z["datr"][k]
            reach = np.abs(px - lv) / px * 100 <= float(rule.get("reach_datr", 1.5)) * datr
            k = k[reach]; J = J[reach]
            if not len(k): continue
            X = z["F"][k].astype(float)
            if mod == "smc":
                sc = TV.model_score(m["models"], X); keep = sc >= m["thr"]
            else:
                so = TV.model_score(m["models_o"], X); sn = TV.model_score(m["models_n"], X); sc = np.maximum(so / m["thr_o"], sn / m["thr_n"]); keep = sc >= 1.0
            for i, jj, s_ in zip(k[keep], J[keep], sc[keep]):
                s = int(z["side"][i]); R, q, kd = wk(O, H, L, Cc, T, int(jj), s, float(z["lv"][i]), float(z["datr"][i]), float(rule["hard_x"]), float(rule["take_r"]),
                                                       int(rule["hold_h"]), int(rule["stop_close_h"]))
                ev.append({"coin": c, "grp": grp, "t": int(z["t"][i]), "tout": int(T[min(len(T) - 1, jj + q - 1)]) + 3600, "side": s, "R": float(R), "kind": int(kd),
                           "lv": float(z["lv"][i]), "datr": float(z["datr"][i]), "hard": float(rule["hard_x"]), "score": float(s_)})
    ev.sort(key=lambda e: (e["t"], -e["score"]))
    busy, opn, out = {}, [], []
    for e in ev:   # one position a coin, the side cap
        if busy.get(e["coin"], 0) > e["t"]: continue
        opn = [x for x in opn if x[0] > e["t"]]
        if sum(1 for x in opn if x[1] == e["side"]) >= cap: continue
        busy[e["coin"]] = e["tout"]; opn.append((e["tout"], e["side"])); out.append(e)
    json.dump(out, open(f"{ST}/wf/lv_new_{mod}.json", "w"))
    for g in ("base", "new"):
        r = np.array([e["R"] for e in out if e["grp"] == g])
        print(f"{mod} {g}: {len(r)} trades 2026, {r.mean() if len(r) else float('nan'):+.3f}R, WR {(r > 0).mean() * 100 if len(r) else 0:.0f}%", flush=True)
if __name__ == "__main__":
    os.makedirs(LE.OUT, exist_ok=True)
    with Pool(4) as P:
        bad = [x for x in P.map(build, C["base"] + C["new"], chunksize=4) if x[1] is not True]
    print("lv2 built; failed:", len(bad), bad[:5], flush=True)
    for mod in ("smc", "htf"): module(mod)
    print("lv_new done", flush=True)
