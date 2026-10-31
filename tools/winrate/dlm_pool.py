"""⚡ pool v2: the walk-forward scores (dlm_wf.py) -> the trades the bot would make: both streams' orders above their year's
threshold, by the touch hour (then the higher score), a coin & side busy while its trade is open, <= 20 open a side;
coin groups: base (the bot's 210) / new (226). -> <LABSTORE>/wf/pool_<group>.json + the per-year table"""
import sys, os, json, numpy as np, calendar, collections
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
def pool(groups, cap=20):
    ev = []
    for st in ("wick4h", "close2h"):
        z0 = np.load(f"{ST}/wf/scores_{st}.npz", allow_pickle=True); z = {k: z0[k] for k in z0.files}   # read once (an NpzFile unpacks on every access)
        m = np.isfinite(z["score"]) & (z["score"] >= z["thr"]) & np.isin(z["grp"], groups)
        for k in np.flatnonzero(m):
            ev.append((int(z["t1h"][k]), -float(z["score"][k]), st, str(z["coin"][k]), int(z["side"][k]), int(z["t"][k]), float(z["fill"][k]),
                       float(z["R"][k]), int(z["kind"][k]), int(z["tout"][k]), float(z["atr"][k]), float(z["lv"][k]), str(z["grp"][k])))
    ev.sort()
    busy, opn, out = {}, [], []
    for t1h, nsc, st, c, s, t, fill, R, kind, tout, a, lv, g in ev:
        if busy.get((c, s), 0) > t1h: continue
        opn = [x for x in opn if x[0] > t1h]
        if sum(1 for x in opn if x[1] == s) >= cap: continue
        busy[(c, s)] = tout; opn.append((tout, s))
        out.append({"coin": c, "st": st, "side": s, "t0": t, "t1h": t1h, "fill": fill, "R": R, "kind": kind, "tout": tout, "atr": a, "score": -nsc, "grp": g,
                    "sl": fill - s * 2.0 * a, "hsl": fill - s * 3.0 * a})
    return out
def table(P, nm):
    by = collections.defaultdict(list)
    for x in P: by[int(np.datetime64(x["t1h"], "s").astype("datetime64[Y]").astype(int) + 1970)].append(x["R"])
    print(nm, " | ".join(f"{y}: {len(v)} сд. WR {np.mean(np.array(v) > 0)*100:.0f}% {np.mean(v):+.3f}R" for y, v in sorted(by.items())), flush=True)
if __name__ == "__main__":
    for nm, groups in (("base", ["train", "check", "base"]), ("check", ["check"]), ("new", ["new"]), ("base+new", ["train", "check", "base", "new"])):
        P = pool(groups); table(P, f"{nm:9s}")
        json.dump(P, open(f"{ST}/wf/pool_{nm}.json", "w"))
