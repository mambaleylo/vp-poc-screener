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
BASE = dict(q=0.997, win=180, drought=None, side=1, famq=False, coins="bot", cap=20)
VARS = {
    "base": {},
    "q995": dict(q=0.995), "q99": dict(q=0.99), "q98": dict(q=0.98),
    "win30": dict(win=30), "win60": dict(win=60), "win90": dict(win=90),
    "dr14": dict(drought=(14, 0.99)), "dr21": dict(drought=(21, 0.99)), "dr10_98": dict(drought=(10, 0.98)),
    "dr7_98": dict(drought=(7, 0.98)), "dr10_97": dict(drought=(10, 0.97)), "dr14_98": dict(drought=(14, 0.98)),
    "both": dict(side=0), "famq": dict(famq=True), "c210": dict(coins="all"),
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
def outcome(i):
    if i not in RC:
        Tb, O, H, L, C_, V = bars(SYM[i]); jE = int(J[i]) + 1
        if jE + 1 >= len(C_): RC[i] = None
        else:
            p = dict(DEF); p.update(P_DEP)
            r, kk = walk2(Tb, O, H, L, C_, jE, -int(SIDE[i]), float(DA[i]), p["sk"], p["hard"], p["ctf"], p["take"], p["hold"], p["be_at"], p["be_to"],
                          p["tr_at"], p["tr_d"], p["p_at"], p["p_fr"], p["p_be"], p["lim"], p["wait"])
            RC[i] = (float(r), int(kk), int(Tb[jE]), float(O[jE]))
    return RC[i]
def build(p):
    base_ok = np.isfinite(SC) & (T >= ts(2023)) & (T < ts(2026, 10)) & ((BOT) if p["coins"] == "bot" else True)
    if p["side"]: base_ok &= (-SIDE == p["side"])
    c = np.where(base_ok)[0]
    c = c[np.array([T[i] - FIRST[SYM[i]] >= 90 * 86400 for i in c], bool)]
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
        oc = outcome(i)
        if oc is None: continue
        r, kk, t0, fill = oc
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SIDE[i]) >= p["cap"]: continue
        end = t0 + kk * 3600; busy[key] = end + 24 * 3600; act.append((end, SIDE[i])); last = t
        st = max(0.002, P_DEP["sk"] * float(DA[i]) / 100)
        out.append({"t0": t0, "t1": int(end), "r": r, "st": st, "sth": st * P_DEP["hard"] / P_DEP["sk"], "mod": "cfl", "sym": Dd["names"][SYM[i]],
                    "side": -int(SIDE[i]), "e": fill, "stream": None, "bot": bool(BOT[i])})
    return out
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
        for part in nm.split("+"): p.update(VARS[part])
        L = build(p); r = np.array([x["r"] for x in L]); t = np.array([x["t0"] for x in L]); im, gap = idle(L)
        ys = " ".join(f"{Y}: {int(((t >= ts(Y)) & (t < ts(Y + 1))).sum())} {r[(t >= ts(Y)) & (t < ts(Y + 1))].mean() if ((t >= ts(Y)) & (t < ts(Y + 1))).any() else 0:+.2f}" for Y in range(2023, 2027))
        ex = ""
        if p["coins"] == "all":
            ub = np.array([not x["bot"] for x in L]); ex = f" | невиденные {ub.sum()} {r[ub].mean() if ub.any() else 0:+.2f}R"
        print(f"{nm:12s}: {len(L)} сделок, {r.mean():+.3f}R, WR {(r > 0).mean() * 100:.0f}%, пустых месяцев {im} из 45, самая длинная пауза {gap} дн | {ys}{ex}", flush=True)
        json.dump(L, open(f"{ST}/wf/cfl_var_{nm}.json", "w"))
    print("cfl var done", flush=True)
