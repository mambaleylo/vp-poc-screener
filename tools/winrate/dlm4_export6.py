"""⚡ v0.99.691 export (dlm4_export6.py): as v0.99.690's, the fills of the pool ordered by the 1h bar of the touch (the
audit: by the fill bar's open a 4h order won over a 2h one the price reached hours earlier — pool1h.py). ⚡ v0.99.690 export — the same two streams and models as v0.99.689 (dlm4_export4.py), a new exit (the user's idea,
tkext.py / tkext_1m.py): the take starts at 2 ATR; if the price goes 0.4 ATR against the trade before it has reached
+1 ATR, the take comes back to 1 ATR; the stop 2 ATR, out after 32 bars. Bar level: the touch bar's dip counts (the worst
order), the far take only from the bar after the +1 ATR touch. The model file gets the rule in each stream and the new
research numbers; the backtest list = the pool as the bot trades it, 2025 on."""
import os, json, numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("tkext.py").read().split("\nBARS = {}")[0])
exec("@njit\ndef ex" + open("tkext.py").read().split("@njit\ndef ex")[1].split("\ndef run")[0])
from bt_trades import gate_sym
NPULL, FAR = 0.4, 2.0
BARS = {}
EV = events("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0) + events("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0)
# the chk / new flags (unseen coins) for the years table
def unseen_set(dr):   # the check coins (every 3rd of the sorted 127, s15_wf.load) and the new ones
    import glob
    syms = [os.path.basename(f)[:-4] for f in sorted(glob.glob(f"{dr}/*.npz"))]
    return set(syms[2::3]) | {os.path.basename(f)[:-4] for f in glob.glob(f"{dr}x/*.npz")}
UN = {4: unseen_set("s23_4h"), 2: unseen_set("s21h2")}
rows = []
for v in EV:
    Tb, O, H, L, C, atr, pos = BARS[(v["sym"], v["tfh"])]
    R, k, kk = ex(O, H, L, C, v["fb"], v["s"], v["fill"], v["a"], NPULL, FAR - 1.0, 0, v["tfh"])
    s, fill, a = v["s"], v["fill"], v["a"]
    xp = {1: fill + s * a, 2: fill + s * FAR * a}.get(int(k))
    if xp is None:
        if k == 3: xp = float(C[min(len(C), v["fb"] + 32) - 1])
        else:
            b = v["fb"] + kk; sl = fill - s * 2 * a
            xp = float(O[b]) if (kk > 0 and ((O[b] <= sl) if s > 0 else (O[b] >= sl))) else sl
    rows.append(dict(v, end=int(Tb[v["fb"] + kk]) + v["tfh"] * 3600, r=float(R), k={0: "stop", 1: "take", 2: "take2", 3: "time"}[int(k)], xp=xp,
                     t1=int(Tb[pos[v["t"]] + 1]), un=v["sym"] in UN[v["tfh"]], stop=float(np.clip(2 * a / fill, 0.002, 0.5)),
                     st="wick4h" if v["tfh"] == 4 else "close2h"))
import s19h_engine as E1
H1 = {}
def touch1h(sym, ft, bs, s, lv):
    if sym not in H1:
        T, O, H, L, C, V = E1.load15(sym); H1[sym] = (T, H, L)
    T, H, L = H1[sym]; i = int(np.searchsorted(T, ft)); j = int(np.searchsorted(T, ft + bs))
    for b in range(i, j):
        if (L[b] <= lv) if s > 0 else (H[b] >= lv): return int(T[b])
    return ft
for e in rows: e["ft1"] = touch1h(e["sym"], e["ft"], e["tfh"] * 3600, e["s"], e["lv"])
rows.sort(key=lambda e: (e["ft1"], e["nsc"], e["t"]))
busy, act, pool = {}, [], []
for e in rows:
    if busy.get((e["sym"], e["s"]), 0) > e["ft1"]: continue
    act = [x for x in act if x[0] > e["ft1"]]
    if sum(1 for x in act if x[1] == e["s"]) >= 20: continue
    busy[(e["sym"], e["s"])] = e["end"]; act.append((e["end"], e["s"])); pool.append(e)
P = np.array([(e["ft1"], e["end"], e["r"], e["stop"]) for e in pool], float); P = P[np.argsort(P[:, 0], kind="stable")]
np.save("pool691.npy", P)
t0, t1, R, STv = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
m6 = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 182 * 86400.0, 20, 0.04, -0.025)[0] for s_ in roll])
money = {"pos": 20, "risk": 4.0, "year_median": int(np.median(y[:, 0])), "year_p10": int(np.percentile(y[:, 0], 10)), "harsh_median": int(np.median(yh)),
         "dd": int(round(np.median(y[:, 1]) * 100)), "m6_below": int(round((m6 < 100).mean() * 100)), "m6_median": int(np.median(m6))}
years = {}
for e in pool:
    part = "unseen" if e["un"] else "train"; Y = str(1970 + e["ft"] // 31557600)
    d = years.setdefault(part, {}).setdefault(Y, {"n": 0, "sum": 0.0, "w": 0, "st": {}}); d["n"] += 1; d["sum"] += e["r"]; d["w"] += e["k"] in ("take", "take2")
    d["st"][e["st"]] = d["st"].get(e["st"], 0) + 1
for part in years:
    for Y, d in years[part].items():
        mo = ((ts(int(Y) + 1) if int(Y) < 2026 else ts(2026, 10)) - ts(int(Y))) / (30.4 * 86400)
        years[part][Y] = {"n": d["n"], "avg": round(d["sum"] / d["n"], 3), "wr": round(d["w"] / d["n"] * 100, 1), "pm": round(d["n"] / mo, 1), "streams": d["st"]}
un = [e for e in pool if e["un"]]; h = [e for e in un if e["ft"] >= ts(2025, 10)]
W = lambda e: e["k"] in ("take", "take2")
out = []
for e in pool:
    if e["ft"] < ts(2025): continue
    gs, scl = gate_sym(e["sym"]); s, a, fill = e["s"], e["a"], e["fill"]
    out.append({"s": gs, "d": s, "c": f"{e['tfh']}h", "st": e["st"], "t": e["t1"], "lv": round(e["lv"] / scl, 10), "e": round(fill / scl, 10),
                "sl": round((fill - s * 2 * a) / scl, 10), "tp": round((fill + s * (FAR if e["k"] == "take2" else 1.0) * a) / scl, 10),
                "tp2": round((fill + s * FAR * a) / scl, 10), "tp1": round((fill + s * a) / scl, 10),
                "f": e["ft"], "x": e["end"], "xp": round(e["xp"] / scl, 10), "r": round(e["r"], 3), "k": "take" if e["k"] == "take2" else e["k"],
                "far": e["k"] == "take2", "chk": e["un"]})
out.sort(key=lambda x: x["t"])
json.dump(out, open("dlm_bt_v691.json", "w"), separators=(",", ":"))
M = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json"))
for S in M["streams"]:
    S.update({"take_atr": 1.0, "far_take_atr": FAR, "pull_atr": NPULL})
M["research"].update({"years": years, "money": money, "exit": {"far_take_atr": FAR, "pull_atr": NPULL, "m1": {"base": 0.198, "new": 0.259, "n": 1159}},
                      "unseen": {"wr": round(np.mean([W(e) for e in un]) * 100), "avg": round(float(np.mean([e["r"] for e in un])), 3),
                                 "last12_wr": round(np.mean([W(e) for e in h]) * 100), "last12_avg": round(float(np.mean([e["r"] for e in h])), 3)}})
M["research"]["m1"] = {"wr": 74, "avg_through": 0.26}
M["research"]["order"] = "1h"   # v0.99.691 — the pool by the touch's 1h bar
json.dump(M, open("vp_dlm_model_v691.json", "w"), separators=(",", ":"))
print("pool", len(pool), f"{R.mean():+.3f}R", json.dumps(money), "bt list", len(out), "avg", round(np.mean([x["r"] for x in out]), 3),
      "wr", round(np.mean([x["k"] == "take" for x in out]) * 100, 1), "far", sum(x["far"] for x in out))
print(json.dumps(M["research"]["unseen"]), json.dumps(years.get("unseen")))
