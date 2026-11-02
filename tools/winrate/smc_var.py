"""🧱 SMC improvement round (the user: "сделай полную проверку и попытку улучшить по smc", as the EMA one): the deployed
list (smc_export5.py + v0.99.719's break-even: the yearly walk-forward scores, q 0.993 of the previous year's out-of-sample
scores, the 127 bot coins, the bot's reach filter |px - lv| <= 1.5 dATR at the hour's start, the nearer level first, one a
coin & side, at most 12 a side; the stop 1 dATR at a 4h close, the emergency 2x by a touch, take 3R, the stop to the entry
after +2R, 96 h) re-made with one thing changed per variant ("a+b" combines) -> <LABSTORE>/wf/smc_var_<name>.json in the
money's format; tools/winrate money_ema.py MOD=smc judges them in the bundle's money.
The walk = the bot's _cs_walk (the emergency stop first, the break-even / partial from the 2nd hour, no take in the entry hour,
the close stop only before the break-even). usage (in the lab dir with lv2/, lv2_t0/, smc_sc.npz, smc_sc_t0.npz):
python3 smc_var.py [names…]"""
import os, sys, json, glob, types, numpy as np, warnings; warnings.filterwarnings("ignore")
ARGV = sys.argv[1:]; sys.argv = ["x"]
sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))
from numba import njit
from lv_wf import load_dir, ts
import lv_engine as LE
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
BASE = dict(ev="lv2", q=0.993, reach=1.5, stop=1.0, hard=2.0, take=3.0, hold=96, kh=4, be=2.0, pf=0.0, cap=12, sides=(1, -1),
            deep=0.0, fams=None, xs=None, coins="bot")
VARS = {
    "base": {},
    "t0": dict(ev="lv2_t0"),                                                           # any touch (the bot's market entry fires on it)
    "q99": dict(q=0.99), "q985": dict(q=0.985), "q995": dict(q=0.995),                 # the threshold: more / fewer trades
    "reach1": dict(reach=1.0), "reach25": dict(reach=2.5), "noreach": dict(reach=99.0),
    "stop075": dict(stop=0.75), "stop15": dict(stop=1.5), "hard15": dict(hard=1.5), "hard3": dict(hard=3.0),
    "take2": dict(take=2.0), "take4": dict(take=4.0), "take5": dict(take=5.0), "take6": dict(take=6.0),
    "hold72": dict(hold=72), "hold144": dict(hold=144), "kh1": dict(kh=1), "kh24": dict(kh=24),
    "be0": dict(be=0.0), "be1": dict(be=1.0), "be3": dict(be=3.0), "part1": dict(be=1.0, pf=0.33),   # EMA's 1/3 at +1R
    "deep02": dict(deep=0.2), "deep04": dict(deep=0.4),                                # the limit past the level (EMA's / ⚡'s lesson)
    "longs": dict(sides=(1,)), "shorts": dict(sides=(-1,)), "cap20": dict(cap=20), "cap8": dict(cap=8),
    "no4h": dict(fams=("fvgd", "fvgw", "swd", "sww", "obd")), "nofvg4": dict(fams=("fvgd", "fvgw", "swd", "sww", "obd", "ob4")),
    "xsc": dict(xs=(1.3, 0.8)),                                                        # the risk by the score (top half of the picks x1.3)
    "c210": dict(coins="all"),                                                         # + the 83 check coins ⚡ trades (never trained on)
}
DD = {}
def events(dr):
    if dr in DD: return DD[dr]
    D = load_dir(dr, LE.FNAMES); LV, J, DT = [], [], []
    for fn in sorted(glob.glob(f"{dr}/*.npz")):
        z = np.load(fn)
        if len(z["t"]) == 0: continue
        LV.append(z["lv"]); J.append(z["j"]); DT.append(z["datr"])
    D["LV"], D["J"], D["DATR"] = np.concatenate(LV), np.concatenate(J).astype(np.int64), np.concatenate(DT)
    z = np.load("smc_sc.npz" if dr == "lv2" else "smc_sc_t0.npz", allow_pickle=True); D["SC"] = z["SC"]; D["THR"] = z["THR"].item()
    D["fam"] = D["F"][:, 0].astype(int)
    D["yr"] = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in D["T"]])
    DD[dr] = D; return D
BARS = {}
def bars(name):
    if name not in BARS:
        if len(BARS) > 40: BARS.clear()
        BARS[name] = LE.load_np(name)
    return BARS[name]
@njit(cache=True)
def walk(O, H, L, C, Tb, j, s, fill, risk, hard, take, hold, kh, be, pf):
    """the bot's _cs_walk on the 1h candles from the touch hour j -> R (per the stop's risk, less the costs), hours"""
    n = len(C); hs = fill - s * hard * risk; ssl = fill - s * risk; tp = fill + s * take * risk; took = False
    e = min(n, j + hold); ex = C[e - 1]; k = e - 1 - j
    for q in range(e - j):
        b = j + q
        if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
            gap = (s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs)
            ex = O[b] if (gap and q > 0) else hs; k = q; break
        if be > 0 and q > 0 and not took and ((s > 0 and H[b] - fill >= be * risk) or (s < 0 and fill - L[b] >= be * risk)):
            took = True; hs = fill
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            ex = tp; k = q; break
        if kh > 0 and not took and (Tb[b] + 3600) % (kh * 3600) == 0 and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            ex = C[b]; k = q; break
    rest = s * (ex - fill) / risk
    r = (pf * be + (1 - pf) * rest) if (took and pf > 0) else rest
    return r - (0.001 + 0.0003 * (k + 1) / 24) * fill / risk, k + 1
def build(p):
    D = events(p["ev"]); T, SIDE, SYM, LV, J, DATR, fam, SC, yr = D["T"], D["SIDE"], D["SYM"], D["LV"], D["J"], D["DATR"], D["fam"], D["SC"], D["yr"]
    thr = np.array([np.quantile(D["THR"][Y], p["q"]) if Y in D["THR"] else np.inf for Y in range(1970, 2030)])
    ok = (fam >= 33) & (D["BOT"] if p["coins"] == "bot" else True) & np.isfinite(SC) & (SC >= thr[np.clip(yr - 1970, 0, 59)]) & (T >= ts(2022)) & np.isin(SIDE, p["sides"])
    if p["fams"]: ok &= np.isin(np.array([LE.FAMS[f].split("_")[0] for f in range(len(LE.FAMS))])[fam], p["fams"])
    idx = np.where(ok)[0]
    FILL = LV * (1 - SIDE * p["deep"] * DATR / 100)
    R = np.full(len(T), np.nan); K = np.zeros(len(T), np.int64); OPEN = np.full(len(T), np.nan); PX = np.full(len(T), np.nan)
    for k_ in sorted(set(SYM[idx])):
        Tb, O, H, L, C, V = bars(D["names"][k_])
        for i in idx[SYM[idx] == k_]:
            j = int(J[i]); OPEN[i] = O[j]; PX[i] = C[j - 1] if j >= 1 else np.nan
            f = FILL[i]
            if p["deep"] > 0 and not ((SIDE[i] > 0 and L[j] <= f) or (SIDE[i] < 0 and H[j] >= f)): continue   # the deeper limit not reached
            R[i], K[i] = walk(O, H, L, C, Tb, j, int(SIDE[i]), f, f * p["stop"] * DATR[i] / 100, p["hard"], p["take"], p["hold"], p["kh"], p["be"], p["pf"])
    idx = idx[np.abs(PX[idx] - LV[idx]) / PX[idx] * 100 <= p["reach"] * DATR[idx]]   # the bot's arm filter
    NEAR = SIDE * (OPEN - FILL) / (LV * DATR / 100)
    o = idx[np.lexsort((NEAR[idx], T[idx]))]; busy, act, out = {}, [], []
    for i in o:   # the bot's pool: the nearer level first, one a coin & side, at most cap a side
        t = T[i]; key = (SYM[i], SIDE[i])
        if busy.get(key, 0) > t or R[i] != R[i]: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= p["cap"]: continue
        end = t + int(K[i]) * 3600; busy[key] = end; act.append((end, SIDE[i]))
        st = max(0.002, p["stop"] * float(DATR[i]) / 100)
        x = {"t0": int(t), "t1": int(end), "r": float(R[i]), "st": st, "sth": st * p["hard"], "mod": "smc", "sym": D["names"][SYM[i]],
             "side": int(SIDE[i]), "e": float(FILL[i]), "stream": None, "bot": bool(D["BOT"][i])}
        if p["xs"]: x["xm"] = p["xs"][0] if SC[i] >= thr[yr[i] - 1970] + 0.0 and SC[i] >= np.quantile(D["THR"][yr[i]], 1 - (1 - p["q"]) / 2) else p["xs"][1]
        out.append(x)
    return out
if __name__ == "__main__":
    for nm in (ARGV or list(VARS)):
        p = dict(BASE)
        for part in nm.split("+"): p.update(VARS[part])
        L = build(p); r = np.array([x["r"] for x in L]); t = np.array([x["t0"] for x in L])
        ys = " ".join(f"{Y}: {int(((t >= ts(Y)) & (t < ts(Y + 1))).sum())} {r[(t >= ts(Y)) & (t < ts(Y + 1))].mean() if ((t >= ts(Y)) & (t < ts(Y + 1))).any() else 0:+.2f}" for Y in range(2022, 2027))
        print(f"{nm:10s}: {len(L)} сделок, {r.mean():+.3f}R, WR {(r > 0).mean() * 100:.0f}% | {ys}", flush=True)
        json.dump(L, open(f"{ST}/wf/smc_var_{nm}.json", "w"))
    print("smc var done", flush=True)
