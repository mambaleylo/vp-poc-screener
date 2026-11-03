"""📏 HTF improvement round (the user: "для htf ещё тоже полную проверку, новые гипотезы для увеличения количества сделок,
винрейта и среднего r"): the deployed rule (htf_export_k24.py: the long first touches of the HTF levels 0.1% through — the
bot's trigger —, taken when either model "o" / "n" is above q 0.995 of its previous year's out-of-sample scores, the 127 bot
coins, the reach |px - lv| <= 1.5 dATR at the hour's start, the nearer level first, one a coin, at most 12; the stop 1 dATR
at a 1d close, the emergency 3x by a touch, take 3R, 96 h) re-made with one thing changed per variant ("a+b" combines) ->
<LABSTORE>/wf/htf_var_<name>.json in the money's format (money_ema.py MOD=htf judges them).
The walk = the bot's _cs_walk (smc_var.walk). Scores: htf_sc.py's htf_o_sc.npz / htf_n_sc.npz (in the lab dir).
usage: python3 htf_var.py [names…]"""
import os, sys, json, glob, types, numpy as np, warnings; warnings.filterwarnings("ignore")
ARGV = sys.argv[1:]; sys.argv = ["x"]
sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))
from lv_wf import load_dir, ts
import lv_engine as LE
from smc_var import walk
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
BASE = dict(q=0.995, how="or", reach=1.5, stop=1.0, hard=3.0, take=3.0, hold=96, kh=24, be=0.0, pf=0.0, cap=12, sides=(1,),
            deep=0.0, scopes=None, xs=None, coins="bot", d26=False, y0=2023)
VARS = {
    "base": {}, "d26": dict(d26=True),                                                 # 2026 by the bot's own two models and thr
    "q993": dict(q=0.993), "q99": dict(q=0.99), "q997": dict(q=0.997),                # more / fewer trades
    "and": dict(how="and"), "onlyo": dict(how="o"), "onlyn": dict(how="n"),           # which model decides
    "reach1": dict(reach=1.0), "reach25": dict(reach=2.5),
    "stop075": dict(stop=0.75), "stop15": dict(stop=1.5), "hard2": dict(hard=2.0), "hard4": dict(hard=4.0),
    "take2": dict(take=2.0), "take4": dict(take=4.0), "take5": dict(take=5.0),
    "hold72": dict(hold=72), "hold144": dict(hold=144), "kh4": dict(kh=4), "kh1": dict(kh=1),
    "be2": dict(be=2.0), "be1": dict(be=1.0), "part1": dict(be=1.0, pf=0.33),         # SMC's break-even / EMA's partial
    "deep02": dict(deep=0.2), "deep04": dict(deep=0.4),                                # the limit below the level (EMA's lesson)
    "shorts": dict(sides=(1, -1)),                                                     # + the shorts by model "o"
    "cap20": dict(cap=20), "cap8": dict(cap=8),
    "day": dict(scopes=(0,)), "noday": dict(scopes=(1, 2)),                            # the day levels only / the week & month only
    "xsc": dict(xs=(1.3, 0.8)), "c210": dict(coins="all"),
}
D = {}
def data():
    if D: return D
    Dd = load_dir("lv2", LE.FNAMES); LV, J, DT = [], [], []
    for fn in sorted(glob.glob("lv2/*.npz")):
        z = np.load(fn)
        if len(z["t"]) == 0: continue
        LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
    Dd["LV"], Dd["J"], Dd["DATR"] = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
    Dd["fam"] = Dd["F"][:, 0].astype(int)
    Dd["yr"] = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in Dd["T"]])
    for k in ("o", "n"):
        z = np.load(f"htf_{k}_sc.npz", allow_pickle=True); Dd["SC" + k] = z["SC"]; Dd["THR" + k] = z["THR"].item()
    D.update(Dd); return D
def pct(SCx, THRx, yr):
    p = np.full(len(SCx), np.nan)
    for Y, v in THRx.items():
        m = (yr == Y) & np.isfinite(SCx)
        if m.any(): p[m] = np.searchsorted(np.sort(v), SCx[m]) / len(v)
    return p
BARS = {}
def bars(name):
    if name not in BARS:
        if len(BARS) > 40: BARS.clear()
        BARS[name] = LE.load_np(name)
    return BARS[name]
def build(p, detail=False):
    d = data(); T, SIDE, SYM, LV, J, DATR, fam, yr = d["T"], d["SIDE"], d["SYM"], d["LV"], d["J"], d["DATR"], d["fam"], d["yr"]
    key = ("P", p["q"])
    if key not in d: d[key] = (pct(d["SCo"], d["THRo"], yr), pct(d["SCn"], d["THRn"], yr))
    Po, Pn = d[key]; Po, Pn = np.nan_to_num(Po, nan=-1), np.nan_to_num(Pn, nan=-1)
    po, pn = Po >= p["q"], (Pn >= p["q"]) & (SIDE > 0)
    if p["d26"]:   # 2026: the bot's own two models against their own thr
        if "S26" not in d:
            import treevec as TV
            M = json.load(open(os.path.join(ROOT, "vp_htf_model.json")))
            w = np.flatnonzero((fam <= 22) & (T >= ts(2026))); so = np.full(len(T), -9.0); sn = np.full(len(T), -9.0)
            so[w] = TV.model_score(M["models_o"], d["F"][w].astype(float)); sn[w] = TV.model_score(M["models_n"], d["F"][w].astype(float))
            d["S26"] = (so >= float(M["thr_o"]), sn >= float(M["thr_n"]))
        y26 = T >= ts(2026); po = np.where(y26, d["S26"][0], po); pn = np.where(y26, d["S26"][1] & (SIDE > 0), pn)
    PASS = {"or": po | pn, "and": po & pn, "o": po, "n": pn}[p["how"]]
    ok = (fam <= 22) & (d["BOT"] if p["coins"] == "bot" else True) & PASS & (T >= ts(p["y0"])) & np.isin(SIDE, p["sides"]) & np.isfinite(DATR)
    if p["scopes"]: ok &= np.isin(np.array(LE.SCOPE)[fam], p["scopes"])
    idx = np.where(ok)[0]
    FILL = LV * (1 - SIDE * p["deep"] * DATR / 100)
    R = np.full(len(T), np.nan); K = np.zeros(len(T), np.int64); INFO = {}; OPEN = np.full(len(T), np.nan); PX = np.full(len(T), np.nan)
    for k_ in sorted(set(SYM[idx])):
        Tb, O, H, L, C, V = bars(d["names"][k_])
        for i in idx[SYM[idx] == k_]:
            j = int(J[i]); OPEN[i] = O[j]; PX[i] = C[j - 1] if j >= 1 else np.nan; f = FILL[i]
            if p["deep"] > 0 and not ((SIDE[i] > 0 and L[j] <= f) or (SIDE[i] < 0 and H[j] >= f)): continue
            R[i], K[i], kd, ex, qb = walk(O, H, L, C, Tb, j, int(SIDE[i]), f, f * p["stop"] * DATR[i] / 100, p["hard"], p["take"], p["hold"], p["kh"], p["be"], p["pf"])
            INFO[i] = (("be2" if qb >= 0 else "hard") if kd == 0 else {1: "take", 3: "time", 4: "stop"}[kd], float(ex))
    idx = idx[np.abs(PX[idx] - LV[idx]) / PX[idx] * 100 <= p["reach"] * DATR[idx]]   # the bot's arm filter
    NEAR = SIDE * (OPEN - FILL) / (LV * DATR / 100)
    o = idx[np.lexsort((NEAR[idx], T[idx]))]; busy, act, out = {}, [], []
    for i in o:   # the bot's pool: the nearer level first, one a coin (& side), at most cap a side
        t = T[i]; key_ = (SYM[i], SIDE[i])
        if busy.get(key_, 0) > t or R[i] != R[i]: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= p["cap"]: continue
        end = t + int(K[i]) * 3600; busy[key_] = end; act.append((end, SIDE[i]))
        st = max(0.002, p["stop"] * float(DATR[i]) / 100)
        x = {"t0": int(t), "t1": int(end), "r": float(R[i]), "st": st, "sth": st * p["hard"], "mod": "htf", "sym": d["names"][SYM[i]],
             "side": int(SIDE[i]), "e": float(FILL[i]), "stream": None}
        if detail: x.update({"kind": INFO[i][0], "ex": INFO[i][1], "lvl": LE.FAMS[fam[i]], "risk": float(FILL[i] * p["stop"] * DATR[i] / 100),
                             "by": ("o" if po[i] else "") + ("n" if pn[i] else "")})
        if p["xs"]: x["xm"] = p["xs"][0] if max(Po[i], Pn[i]) >= 1 - (1 - p["q"]) / 2 else p["xs"][1]
        out.append(x)
    return out
if __name__ == "__main__":
    for nm in (ARGV or list(VARS)):
        p = dict(BASE)
        for part in nm.split("+"): p.update(VARS[part])
        L = build(p); r = np.array([x["r"] for x in L]); t = np.array([x["t0"] for x in L])
        ys = " ".join(f"{Y}: {int(((t >= ts(Y)) & (t < ts(Y + 1))).sum())} {r[(t >= ts(Y)) & (t < ts(Y + 1))].mean() if ((t >= ts(Y)) & (t < ts(Y + 1))).any() else 0:+.2f}" for Y in range(2023, 2027))
        print(f"{nm:12s}: {len(L)} сделок, {r.mean():+.3f}R, WR {(r > 0).mean() * 100:.0f}% | {ys}", flush=True)
        json.dump(L, open(f"{ST}/wf/htf_var_{nm}.json", "w"))
    print("htf var done", flush=True)
