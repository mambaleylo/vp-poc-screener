"""🔄 Классика наоборот lab: the deployed rolling rule (2026 scores fc_red_sc, q of the 180 days ending 14 before, bot
coins' scores) with variants: exits (take, hold, stop, break-even), sides, indicator families, q, cap, the entry an hour
later. Bot coins (cap shared among them) and check coins (their own cap) separately; per year."""
import sys, json, glob, math, numpy as np, warnings; warnings.filterwarnings("ignore")
sys.argv = ["x"]
from numba import njit
import lv_engine as LE, ev3_engine as E3
from lv_wf import load_dir, ts
Dd = load_dir("ev3", E3.FNAMES); T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]; FAM = Dd["F"][:, 0].astype(int)
J, DA = [], []
for fn in sorted(glob.glob("ev3/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    J.append(z["j"]); DA.append(z["datr"])
J, DA = np.concatenate(J).astype(np.int64), np.concatenate(DA)
SC = np.load("fc_red_sc.npz", allow_pickle=True)["SC"]
mk = BOT & (T >= ts(2021)) & np.isfinite(SC); tt, ss = T[mk], SC[mk]; o = np.argsort(tt); tt, ss = tt[o], ss[o]
def thr_days(q, win=180):
    out = {}
    for d in range(ts(2023) // 86400 - 1, ts(2026, 10) // 86400 + 1):
        hi = (d - 14) * 86400; lo = hi - win * 86400; a, b = np.searchsorted(tt, lo), np.searchsorted(tt, hi)
        out[d] = float(np.quantile(ss[a:b], q)) if b - a >= 300 else np.inf
    return out
FIRST = {}
for k in range(len(Dd["names"])):
    FIRST[k] = int(LE.load_np(Dd["names"][k])[0][0])
@njit(cache=True)
def walk(O, H, L, C, jE, s, datr, sk, take, hold, be_at):
    fill = O[jE]; risk = fill * sk * datr / 100; stop = fill - s * risk; tp = fill + s * take * risk; be = False
    e = min(len(C), jE + hold); k = e - 1 - jE; ex = C[e - 1]
    for q in range(e - jE):
        b = jE + q
        st_ = fill if be else stop
        if (s > 0 and L[b] <= st_) or (s < 0 and H[b] >= st_):
            gap = (s > 0 and O[b] <= st_) or (s < 0 and O[b] >= st_); ex = O[b] if (gap and q > 0) else st_; k = q; break
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)):
            ex = tp; k = q; break
        if be_at > 0 and s * (C[b] - fill) >= be_at * risk: be = True
    return s * (ex - fill) / risk - (0.001 + 0.0003 * (k + 1) / 24) * fill / risk, k + 1
BARS = {}
def bars(k):
    if k not in BARS:
        if len(BARS) > 40: BARS.clear()
        BARS[k] = LE.load_np(Dd["names"][k])
    return BARS[k]
TH = {}
def run(nm, q=0.997, sk=1.0, take=3.0, hold=72, be_at=0.0, delay=0, side=0, fams=None, cap=12, quiet=False):
    if q not in TH: TH[q] = thr_days(q)
    th = TH[q]
    res = []
    for grp in (True, False):
        c = np.where((BOT == grp) & np.isfinite(SC) & (T >= ts(2023)) & (T < ts(2026, 10)))[0]
        c = c[SC[c] >= np.array([th.get(int(t // 86400), np.inf) for t in T[c]])]
        c = c[np.array([T[i] - FIRST[SYM[i]] >= 90 * 86400 for i in c], bool)]
        if side: c = c[-SIDE[c] == side]
        if fams is not None: c = c[np.isin(FAM[c], fams)]
        R, K = {}, {}
        for k in sorted(set(SYM[c])):
            Tb, O, H, L, C, V = bars(k)
            for i in c[SYM[c] == k]:
                jE = int(J[i]) + 1 + delay
                if jE + 1 < len(C): R[i], K[i] = walk(O, H, L, C, jE, -int(SIDE[i]), float(DA[i]), sk, take, hold, be_at)
        cc = np.array([i for i in c if i in R], np.int64)
        oo = cc[np.lexsort((-SC[cc], T[cc]))]
        busy, act, sel = {}, [], []
        for i in oo:
            t = T[i]; key = (SYM[i], SIDE[i])
            if busy.get(key, 0) > t: continue
            act = [a for a in act if a[0] > t]
            if sum(1 for a in act if a[1] == SIDE[i]) >= cap: continue
            end = t + (int(K[i]) + delay) * 3600; busy[key] = end; act.append((end, SIDE[i])); sel.append(i)
        sel = np.array(sel, np.int64); r = np.array([R[i] for i in sel]); y = (T[sel].astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
        res.append((sel, r, y))
    (sb, rb, yb), (sc_, rc, yc) = res
    if not quiet:
        print(f"  {nm:34s} бот n {len(rb):3d} {rb.mean():+.3f}R WR {np.mean(rb > 0)*100:3.0f}% ΣR/год {rb.sum() / 3.75:+5.1f} | контр. n {len(rc):3d} {rc.mean():+.3f}R | "
              + " ".join(f"{Y % 100}:{rb[yb == Y].mean():+.2f}" for Y in range(2023, 2027) if (yb == Y).any()), flush=True)
    return sb, rb
if __name__ == "__main__":
    print("== база (как в боте)"); run("B0 бот: q0.997, 1 dATR, 3R, 72ч")
    print("== выходы")
    for tk in (2.0, 2.5, 4.0): run(f"тейк {tk}R", take=tk)
    for hd in (48, 96): run(f"держим {hd}ч", hold=hd)
    for sk in (0.75, 1.5): run(f"стоп {sk} dATR", sk=sk)
    run("стоп 1.5, тейк 2R", sk=1.5, take=2.0)
    for be in (1.0, 1.5): run(f"безубыток после +{be}R", be_at=be)
    print("== стороны")
    run("только лонги", side=1); run("только шорты", side=-1)
    print("== семейства")
    f4 = [i for i, f in enumerate(E3.FAMS) if f.endswith("4h")]
    run("только 4ч", fams=f4)
    weak = [E3.FAMS.index(f) for f in ("nr7_4h", "nr7_1d", "rsi_div_4h", "rsi_div_1d")]
    run("без NR7 и дивергенций RSI", fams=[i for i in range(len(E3.FAMS)) if i not in weak])
    run("только 4ч, без NR7 / RSI", fams=[i for i in f4 if i not in weak])
    print("== порог / лимит")
    for q in (0.995, 0.998): run(f"q{q}", q=q)
    for cp in (6, 20): run(f"лимит {cp}", cap=cp)
    print("== задержка входа")
    run("вход через час", delay=1); run("вход через 2 часа", delay=2)
