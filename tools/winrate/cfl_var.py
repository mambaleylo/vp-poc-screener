"""🔄 Классика наоборот — the regularity round (the user: "отличные результаты, надо его взять в работу, но мне не нравится
количество сделок, а именно по 2 или 3 месяца простоев… пачку гипотез"): the deployed rule (cfl_export.py v0.99.741: the
walk-forward scores fc_red_sc.npz, the rolling threshold q 0.997 of the bot coins' scores of the 180 days ending 14 days
before, longs only = against the bearish signals, >= 90 days after the listing, the bot coins; the stop 0.75 dATR at the 1d
close, the emergency 1.5 dATR, take 4R, 96 h; one a coin & side, cap 20, the score order within the hour) with one thing
changed per variant ("a+b" combines):
  q (the threshold), win (its window, days), drought=D/q2 (no trade for D days -> the threshold q2 until one), side (0 both,
  -1 shorts), famq (a threshold per indicator family), coins "all" (+ the 83 check coins, never trained on)
-> per variant: trades, R, WR, idle months, the longest pause; <LABSTORE>/wf/cfl_var_<name>.json in the money's format.
usage (tools/winrate, after run_cfl_repro.sh): python3 cfl_var.py [names…]   (run_cflvar.sh: under the watchdog)"""
import os, sys, json, numpy as np
ARGV = sys.argv[1:]
exec(open("cfl_lab3.py").read().rsplit('if __name__ == "__main__":', 1)[0])
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
TAG = os.environ.get("CFL_TAG", "")   # CFL_SC=roll_cfl_Q.npz CFL_TAG=_Q: another retrain schedule's scores (roll_mod.py cfl VAR)
if os.environ.get("CFL_SC"):
    SC = np.load(os.environ["CFL_SC"])["SC"]
    mk = BOT & (T >= ts(2021)) & np.isfinite(SC); tt, ss = T[mk], SC[mk]; o = np.argsort(tt); tt, ss = tt[o], ss[o]
BASE = dict(q=0.997, win=180, drought=None, side=1, famq=False, coins="bot", cap=20, tfs=None, ex={}, cool=24, flt=None, xm=None)
VARS = {
    "base": {},
    "q995": dict(q=0.995), "q99": dict(q=0.99), "q98": dict(q=0.98),
    "win30": dict(win=30), "win60": dict(win=60), "win90": dict(win=90),
    "dr14": dict(drought=(14, 0.99)), "dr21": dict(drought=(21, 0.99)), "dr10_98": dict(drought=(10, 0.98)),
    "dr7_98": dict(drought=(7, 0.98)), "dr10_97": dict(drought=(10, 0.97)), "dr14_98": dict(drought=(14, 0.98)),
    "both": dict(side=0), "famq": dict(famq=True), "c210": dict(coins="all"),
    # round 2 (v0.99.776: the deployed A = dr14+c210 + one of these): the exits / the entry, as the other modules' lessons
    "be2": dict(ex={"be_at": 2.0}), "be1": dict(ex={"be_at": 1.0}), "part1": dict(ex={"p_at": 1.0, "p_fr": 1 / 3, "p_be": True}),
    "take3": dict(ex={"take": 3.0}), "take5": dict(ex={"take": 5.0}), "take6": dict(ex={"take": 6.0}),
    "hold72": dict(ex={"hold": 72}), "hold144": dict(ex={"hold": 144}), "ctf4": dict(ex={"ctf": 4}),
    "stop1": dict(ex={"sk": 1.0, "hard": 2.0}), "stop05": dict(ex={"sk": 0.5, "hard": 1.0}), "hard3": dict(ex={"hard": 2.25}),
    "lim025": dict(ex={"lim": 0.25, "wait": 4}), "lim05": dict(ex={"lim": 0.5, "wait": 8}),
    "only4h": dict(tfs="4h"), "only1d": dict(tfs="1d"), "cap10": dict(cap=10), "cap30": dict(cap=30),
    # round 3: the stop x take grid (sk dATR at the 1d close, take R of it, the emergency hard dATR), the trail, the half, more trades
    **{f"s{sk}t{tk}": dict(ex={"sk": sk, "hard": round(2 * sk, 3), "take": float(tk)}) for sk in (0.5, 0.75, 1.0, 1.25) for tk in (3, 4, 5, 6, 8)},
    "hd15": dict(ex={"hard": 1.125}), "hd3": dict(ex={"hard": 2.25}),
    "tr2": dict(ex={"tr_at": 2.0, "tr_d": 1.5}), "tr3": dict(ex={"tr_at": 3.0, "tr_d": 1.5}), "tr2n": dict(ex={"tr_at": 2.0, "tr_d": 1.5, "take": 0.0}),
    "half2": dict(ex={"p_at": 2.0, "p_fr": 0.5, "p_be": True}), "ctf12": dict(ex={"ctf": 12}),
    "hold48": dict(ex={"hold": 48}), "hold120": dict(ex={"hold": 120}), "hold168": dict(ex={"hold": 168}),
    "dr7": dict(drought=(7, 0.99)), "dr10": dict(drought=(10, 0.99)), "dr14_985": dict(drought=(14, 0.985)),
    "shortsq": dict(side=0, q=0.997),
    # round 6 (v0.99.777's rule B = dr14+c210+cap30+s0.5t6+ctf4 + one of these): more trades, a tighter stop, the pause after a
    # coin's exit, the market's regime (the event's own features), the risk by the signal's strength (money_arm2's per-trade "xm")
    "cap40": dict(cap=40), "cap50": dict(cap=50),
    "s0.4t6": dict(ex={"sk": 0.4, "hard": 0.8, "take": 6.0}), "s0.4t8": dict(ex={"sk": 0.4, "hard": 0.8, "take": 8.0}),
    "s0.5t7": dict(ex={"sk": 0.5, "hard": 1.0, "take": 7.0}),
    "cool0": dict(cool=0), "cool12": dict(cool=12), "cool48": dict(cool=48),
    "btcup": dict(flt=("b_e50", 1)), "btcdn": dict(flt=("b_e50", -1)), "e200up": dict(flt=("d_e200", 1)), "e200dn": dict(flt=("d_e200", -1)),
    "fundneg": dict(flt=("fund", -1)),
    "xtop": dict(xm="top"), "xdr": dict(xm="dr"),
    # round 8 — cfl_filt.py's filters (the bars from 2023–24's trades only, each lifting both 2023–24 and 2025–26)
    "fpos90": dict(flt=("pos90", "<", 0.7536)), "fatrh": dict(flt=("atr_h", ">", 0.2207)), "fde50": dict(flt=("d_e50", "<", 0.7366)),
    "fpos365": dict(flt=("pos365", "<", 0.9344)), "fdatr": dict(flt=("datr", "<", 8.469)), "fb7d": dict(flt=("b7d", ">", -19.27)),
    "fdow": dict(flt=("dow", ">", 0.5)), "fema": dict(flt=("ema_near", ">", 0.0509)),
}
TH = {}
def thr(q, win):
    if (q, win) not in TH: TH[(q, win)] = thr_days(q, win)
    return TH[(q, win)]
FT = {}
def thr_fam(q, win):
    """a threshold per indicator family: the family's own bot-coin scores of the window"""
    if (q, win) in FT: return FT[(q, win)]
    out = {}
    for f in sorted(set(FAM)):
        m = BOT & (T >= ts(2021)) & np.isfinite(SC) & (FAM == f); t_, s_ = T[m], SC[m]; o = np.argsort(t_); t_, s_ = t_[o], s_[o]
        for d in range(ts(2023) // 86400 - 1, ts(2026, 10) // 86400 + 1):
            hi = (d - 14) * 86400; lo = hi - win * 86400; a, b = np.searchsorted(t_, lo), np.searchsorted(t_, hi)
            out[(f, d)] = float(np.quantile(s_[a:b], q)) if b - a >= 100 else np.inf
    FT[(q, win)] = out; return out
P_DEP = dict(sk=0.75, hard=1.5, ctf=24, take=4.0, hold=96)
RC = {}
def outcome(i, ex=None):
    key = (i, tuple(sorted((ex or {}).items())))
    if key not in RC:
        Tb, O, H, L, C_, V = bars(SYM[i]); jE = int(J[i]) + 1
        if jE + 1 >= len(C_): RC[key] = None
        else:
            p = dict(DEF); p.update(P_DEP); p.update(ex or {})
            r, kk = walk2(Tb, O, H, L, C_, jE, -int(SIDE[i]), float(DA[i]), p["sk"], p["hard"], p["ctf"], p["take"], p["hold"], p["be_at"], p["be_to"],
                          p["tr_at"], p["tr_d"], p["p_at"], p["p_fr"], p["p_be"], p["lim"], p["wait"])
            RC[key] = (float(r), int(kk), int(Tb[jE]), float(O[jE])) if r == r else None   # a limit not filled: none
    return RC[key]
def build(p):
    base_ok = np.isfinite(SC) & (T >= ts(2023)) & (T < ts(2026, 10)) & ((BOT) if p["coins"] == "bot" else True)
    if p["side"]: base_ok &= (-SIDE == p["side"])
    c = np.where(base_ok)[0]
    c = c[np.array([T[i] - FIRST[SYM[i]] >= 90 * 86400 for i in c], bool)]
    if p["tfs"]: c = c[np.array([E3.FAMS[int(FAM[i])].endswith("_" + p["tfs"]) for i in c], bool)]
    for f_ in ([p["flt"]] if p.get("flt") and isinstance(p["flt"][0], str) else (p.get("flt") or [])):   # round 6: the event's own feature (the bot has it: CFL_FNAMES)
        v_ = Dd["F"][c, E3.FNAMES.index(f_[0])]   # (name, +1/-1): its sign; (name, ">"/"<", x): a bar; "hour"/"dow" too
        c = c[(v_ * f_[1]) > 0] if len(f_) == 2 else c[(v_ > f_[2]) if f_[1] == ">" else (v_ < f_[2])]
    day = (T[c] // 86400).astype(np.int64)
    if p["famq"]:
        ft = thr_fam(p["q"], p["win"]); th1 = np.array([ft.get((int(FAM[i]), int(d_)), np.inf) for i, d_ in zip(c, day)])
    else:
        t1 = thr(p["q"], p["win"]); th1 = np.array([t1.get(int(d_), np.inf) for d_ in day])
    if p["drought"]:
        t2 = thr(p["drought"][1], p["win"]); th2 = np.array([t2.get(int(d_), np.inf) for d_ in day])
        c, th1, th2 = c[SC[c] >= th2], th1[SC[c] >= th2], th2[SC[c] >= th2]
    else:
        c = c[SC[c] >= th1]; th1 = th1[:len(c)] if len(th1) == len(c) else None
    o = np.lexsort((-SC[c], T[c])); c = c[o]
    if p["drought"]: th1 = th1[o]
    busy, act, out, last = {}, [], [], None
    for n_, i in enumerate(c):
        t = int(T[i])
        if p["drought"] and SC[i] < th1[n_] and not (last is None or t - last >= p["drought"][0] * 86400): continue   # the lower bar only after D idle days
        key = (SYM[i], SIDE[i])
        if busy.get(key, 0) > t: continue
        oc = outcome(i, p["ex"])
        if oc is None: continue
        r, kk, t0, fill = oc
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= p["cap"]: continue
        end = t0 + kk * 3600; busy[key] = end + int(p.get("cool", 24)) * 3600; act.append((end, SIDE[i])); last = t
        sk_, hd_ = p["ex"].get("sk", P_DEP["sk"]), p["ex"].get("hard", P_DEP["hard"])
        st = max(0.002, sk_ * float(DA[i]) / 100)
        out.append({"t0": t0, "t1": int(end), "r": r, "st": st, "sth": st * hd_ / sk_, "mod": "cfl", "sym": Dd["names"][SYM[i]],
                    "side": -int(SIDE[i]), "e": fill, "stream": None, "bot": bool(BOT[i]), "i": int(i)})
        if p.get("xm") == "top":   # the strongest (over the q 0.999 bar of the same window) at 1.5x the risk
            out[-1]["xm"] = 1.5 if SC[i] >= thr(0.999, p["win"]).get(int(T[i] // 86400), np.inf) else 1.0
        elif p.get("xm") == "dr":   # the drought's own (under the main bar) at half the risk
            out[-1]["xm"] = 0.5 if (p["drought"] and SC[i] < th1[n_]) else 1.0
    return out
def merge(p, v):
    """a variant on top of p: its exit settings join p's (not replace them), so "cap30+s0.5t6+ctf4" keeps all three"""
    q = dict(p); q.update({k: x for k, x in v.items() if k not in ("ex", "flt")})
    if "ex" in v: q["ex"] = {**p.get("ex", {}), **v["ex"]}
    if "flt" in v:   # the filters add up
        L_ = lambda f: [] if not f else ([f] if isinstance(f[0], str) else list(f))
        q["flt"] = L_(p.get("flt")) + L_(v["flt"])
    return q
def idle(L):
    t = np.array(sorted(x["t0"] for x in L))
    if len(t) < 2: return 99, 999
    import collections
    mo = collections.Counter(np.datetime64(int(x), "s").astype("datetime64[M]") for x in t)
    allm = np.arange(np.datetime64("2023-01"), np.datetime64("2026-10"))
    return int(sum(1 for m in allm if mo.get(m, 0) == 0)), int(np.diff(np.r_[ts(2023), t, ts(2026, 10)]).max() // 86400)
if __name__ == "__main__":
    for nm in (ARGV or list(VARS)):
        p = dict(BASE)
        for part in nm.split("+"): p = merge(p, VARS[part])
        L = build(p); r = np.array([x["r"] for x in L]); t = np.array([x["t0"] for x in L]); im, gap = idle(L)
        ys = " ".join(f"{Y}: {int(((t >= ts(Y)) & (t < ts(Y + 1))).sum())} {r[(t >= ts(Y)) & (t < ts(Y + 1))].mean() if ((t >= ts(Y)) & (t < ts(Y + 1))).any() else 0:+.2f}" for Y in range(2023, 2027))
        ex = ""
        if p["coins"] == "all":
            ub = np.array([not x["bot"] for x in L]); ex = f" | невиденные {ub.sum()} {r[ub].mean() if ub.any() else 0:+.2f}R"
        print(f"{nm:12s}: {len(L)} сделок, {r.mean():+.3f}R, WR {(r > 0).mean() * 100:.0f}%, пустых месяцев {im} из 45, самая длинная пауза {gap} дн | {ys}{ex}", flush=True)
        json.dump(L, open(f"{ST}/wf/cfl_var_{nm}{TAG}.json", "w"))
    print("cfl var done", flush=True)
