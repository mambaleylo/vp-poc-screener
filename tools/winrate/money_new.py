"""the new coins (226 not in the bot) by parts: the bot's coins + the new ones' only 4h stream / only longs / only shorts ...,
one joint pool each (dlm_pool's rules: a coin & side busy, <= 20 a side), the money as money_multi.py at 14x with the 2h
shorts x0.5 (v0.99.746). -> <LABSTORE>/wf/pool_bn_<tag>.json, wf/money_new.json + the per-year R of the new coins' part"""
import sys, os, json, collections, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_pool as DP, money_multi as M
from multiprocessing import Pool
BASE = ["train", "check", "base"]
PARTS = {"new_all": lambda st, s: True, "new_4h": lambda st, s: st == "wick4h", "new_2h": lambda st, s: st == "close2h",
         "new_long": lambda st, s: s > 0, "new_short": lambda st, s: s < 0, "new_4h_long": lambda st, s: st == "wick4h" and s > 0,
         "new_4h_short": lambda st, s: st == "wick4h" and s < 0}
def joint(keep, cap=20):
    ev = []
    for st in ("wick4h", "close2h"):
        z0 = np.load(f"{DP.ST}/wf/scores_{st}.npz", allow_pickle=True); z = {k: z0[k] for k in z0.files}
        m = np.isfinite(z["score"]) & (z["score"] >= z["thr"])
        for k in np.flatnonzero(m):
            g = str(z["grp"][k]); s = int(z["side"][k])
            if g == "new" and not keep(st, s): continue
            ev.append((int(z["t1h"][k]), -float(z["score"][k]), st, str(z["coin"][k]), s, int(z["t"][k]), float(z["fill"][k]),
                       float(z["R"][k]), int(z["kind"][k]), int(z["tout"][k]), float(z["atr"][k]), float(z["lv"][k]), g))
    ev.sort(); busy, opn, out = {}, [], []
    for t1h, nsc, st, c, s, t, fill, R, kind, tout, a, lv, g in ev:
        if busy.get((c, s), 0) > t1h: continue
        opn = [x for x in opn if x[0] > t1h]
        if sum(1 for x in opn if x[1] == s) >= cap: continue
        busy[(c, s)] = tout; opn.append((tout, s))
        out.append({"coin": c, "st": st, "side": s, "t0": t, "t1h": t1h, "fill": fill, "R": R, "kind": kind, "tout": tout, "atr": a, "score": -nsc, "grp": g,
                    "sl": fill - s * 2.0 * a, "hsl": fill - s * 3.0 * a})
    return out
def job(args):
    tag, A = args
    if tag not in M._EV: M._EV[tag] = M.build(tag)
    return tag, A, M.run(M._EV[tag], A, A + 365 * 86400, 14.0, M.W2S)
if __name__ == "__main__":
    tags = ["base"]
    for nm, keep in PARTS.items():
        P = joint(keep); json.dump(P, open(f"{DP.ST}/wf/pool_bn_{nm}.json", "w")); tags.append(f"bn_{nm}")
        by = collections.defaultdict(list)
        for x in P:
            if x["grp"] == "new": by[int(np.datetime64(x["t1h"], "s").astype("datetime64[Y]").astype(int) + 1970)].append(x["R"])
        print(f"{nm:13s} новые в пуле:", " | ".join(f"{y}: {len(v)} сд. {np.mean(v):+.3f}R" for y, v in sorted(by.items())), flush=True)
    with Pool(4) as Pl:
        res = Pl.map(job, [(t, A) for t in tags for A in M.STARTS], chunksize=1)
    R = {}
    for t, A, r in res: R.setdefault(t, {})[str(A)] = r
    json.dump(R, open(f"{DP.ST}/wf/money_new.json", "w"))
    b = np.array([R["base"][str(A)][0] for A in M.STARTS])
    for t in tags:
        E = np.array([R[t][str(A)][0] for A in M.STARTS]); dd = np.array([R[t][str(A)][3] for A in M.STARTS]); q = E / b
        print(f"{t:16s} медиана ${np.median(E):>9,.0f} худший ${E.min():>7,.0f} 2-й худший ${np.sort(E)[1]:>7,.0f} | просадка медиана {np.median(dd)*100:.0f}% худшая {dd.max()*100:.0f}% "
              f"| ликв. {sum(R[t][str(A)][4] for A in M.STARTS)} | к монетам бота: лучше в {int((q > 1.001).sum())}/12, медиана x{np.median(q):.2f}", flush=True)
