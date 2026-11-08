"""Hypotheses 12–16 (the user: "по порядку все") — the derivatives data as an ENTRY signal (before: only as filters), one engine.
The 210 Классика / ⚡ coins, lab-store 1h candles + the hourly metrics (open interest, the top traders' and all accounts' long /
short ratios, the taker buy/sell ratio) + the real funding. HYP=12|13|14|15|16 picks the signal:
 12 OI vs price: a new W-hour closing high while the OI fell >= x over W -> short (a rally on short covering); a new low with
    the OI down -> long. The control "cont": a new high with the OI up >= x -> long, a new low with the OI up -> short.
 13 funding extreme + the crowd: the funding (per 8 h) >= F and the accounts' long/short ratio's 30-day z >= Z (Z 0: not needed),
    optionally the price already turning (the close below the close 4 h ago) -> short; the mirror -> long.
 14 the top traders vs the crowd: over W hours the top traders' position ratio up >= x (log) and the accounts' ratio down >= x
    -> long (follow the top); the mirror -> short.
 15 an alt lagging BTC: BTC moved >= k x its ATR over h hours, the coin (its 30-day beta >= 0.7) moved <= f x beta x BTC's move
    -> in BTC's direction (the catch-up).
 16 a rally on falling volume: the close up >= k x ATR over W hours, the volume over W <= v x the W before, the mean taker
    buy/sell ratio over W <= tk -> short; the mirror (a fall on falling volume, the taker >= 2 - tk) -> long.
The signal at its onset (true now, false an hour before), in at the next hour's open; the stop m x ATR(14, 1h) from the entry;
the take T x the stop; out after H hours; the fee 0.1% + the coin's funding over the hold. One per coin & side for its hold.
The baseline: random hours, the same side, exits, period and volatility (10 buckets of ATR / price: a wider stop makes the fee
smaller in R) -> each config's "excess" R = its R minus the random entries'.
Ranked by 2023–24 only; 2025–26 never used for the choice. -> <LABSTORE>/wf/flow<HYP>.json"""
import os, json, time, itertools, calendar, numpy as np
from numba import njit
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); HYP = int(os.environ.get("HYP", "12"))
sp = json.load(open("lv/split.json")); COINS = sorted(set(sp["bot"]) | set(sp["chk"]))[:int(os.environ.get("NCOIN", "999"))]
ts = lambda y, m=1: calendar.timegm((y, m, 1, 0, 0, 0)); A0, MID, END = ts(2023), ts(2025), ts(2026, 10)
def roll_sum(x, w):
    c = np.concatenate([[0.0], np.cumsum(np.nan_to_num(x))]); o = np.full(len(x), np.nan); o[w - 1:] = c[w:] - c[:-w]; return o
def zs(x, w=720):
    m = roll_sum(x, w) / w; m2 = roll_sum(x * x, w) / w; sd = np.sqrt(np.maximum(m2 - m * m, 1e-18)); return (x - m) / sd
def load(sym):
    a = np.loadtxt(f"{ST}/data/1h/{sym}.csv.gz", delimiter=",", ndmin=2); t = a[:, 0].astype(np.int64); k = np.concatenate([[True], np.diff(t) > 0]); a = a[k]
    T, O, H, L, C, V = a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
    met = {k: np.full(len(T), np.nan) for k in ("oi", "top_pos", "ls_acc", "taker")}
    fn = f"{ST}/data/metrics/{sym}.csv"
    if os.path.exists(fn):
        m = np.genfromtxt(fn, delimiter=",", names=True)
        if m.size > 10:
            mt = m["t"].astype(np.int64); j = np.searchsorted(mt, T); ok = (j < len(mt)) & (mt[np.minimum(j, len(mt) - 1)] == T)
            for k in met: met[k][ok] = m[k][j[ok]]
    fr = np.zeros(len(T)); f8 = np.full(len(T), np.nan); ff = f"{ST}/data/funding/{sym}.csv"
    if os.path.exists(ff) and os.path.getsize(ff) > 0:
        f = np.loadtxt(ff, delimiter=",", ndmin=2); ft = (f[:, 0].astype(np.int64) // 3600) * 3600
        iv = np.diff(np.concatenate([[ft[0] - 8 * 3600], ft])) / 3600.0; iv = np.clip(iv, 1, 8)
        j = np.searchsorted(T, ft); ok = (j < len(T)) & (T[np.minimum(j, len(T) - 1)] == ft); fr[j[ok]] += f[ok, 1]
        # the last known rate per 8 h at each hour's close (the settlement at the hour's start is known)
        k = np.searchsorted(ft, T, side="right") - 1; g = k >= 0; f8[g] = f[k[g], 1] * 8 / iv[k[g]]
    pc = np.concatenate([[C[0]], C[:-1]]); tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    atr = np.empty(len(C)); a_ = tr[0]
    for i in range(len(C)): a_ = tr[i] if i == 0 else (a_ * 13 + tr[i]) / 14; atr[i] = a_
    return dict(T=T, O=O, H=H, L=L, C=C, V=V, atr=atr, F=np.concatenate([[0.0], np.cumsum(fr)]), f8=f8, **met)
@njit(cache=True)
def run(O, H, L, C, atr, F, idx, sides, m, take, hold):
    """the trades of one coin: idx (signal bars, sorted), sides; -> R, entry bar, side (nan R = skipped)"""
    n = len(idx); R = np.full(n, np.nan); busy_l = -1; busy_s = -1
    for q in range(n):
        i = idx[q]; s = sides[q]
        if i + 2 >= len(C): continue
        if (s > 0 and i < busy_l) or (s < 0 and i < busy_s): continue
        e = O[i + 1]; risk = m * atr[i]
        if e <= 0 or risk < 0.001 * e: continue   # a flat, dead hour (ATR ~0) -> a huge R from nothing
        stop = e - s * risk; tp = e + s * take * risk; last = min(len(C) - 1, i + hold); ex = C[last]; bo = last
        for b in range(i + 1, last + 1):
            if (s > 0 and L[b] <= stop) or (s < 0 and H[b] >= stop):
                ex = O[b] if ((s > 0 and O[b] <= stop) or (s < 0 and O[b] >= stop)) else stop; bo = b; break
            if (s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp):
                ex = O[b] if ((s > 0 and O[b] >= tp) or (s < 0 and O[b] <= tp)) else tp; bo = b; break
        fund = F[bo + 1] - F[i + 1]   # the settlements in the entry hour .. the exit hour
        R[q] = (s * (ex - e) - e * 0.001 - s * fund * e) / risk
        if s > 0: busy_l = bo
        else: busy_s = bo
    return R
DATA = {}
for sym in COINS + ["BTCUSDT"]:
    try: DATA[sym] = load(sym)
    except Exception as ex: print("нет", sym, ex)
BTC = DATA["BTCUSDT"]
print(f"гипотеза {HYP}; монет: {len(DATA) - 1}", flush=True)
def onset(c):
    c = np.nan_to_num(c.astype(float)) > 0; p = np.concatenate([[False], c[:-1]]); return c & ~p
def signals(d, P):
    """-> (long mask, short mask) at bar closes"""
    C, V, T = d["C"], d["V"], d["T"]; n = len(C)
    if HYP == 12:
        W, x, mode = P["W"], P["x"], P["mode"]
        hi = np.full(n, False); lo = np.full(n, False)
        mx = np.lib.stride_tricks.sliding_window_view(C, W).max(1); mn = np.lib.stride_tricks.sliding_window_view(C, W).min(1)
        hi[W - 1:] = C[W - 1:] >= mx; lo[W - 1:] = C[W - 1:] <= mn
        doi = np.full(n, np.nan); doi[W:] = np.log(d["oi"][W:] / d["oi"][:-W])
        if mode == "fade": return lo & (doi <= -x), hi & (doi <= -x)
        return hi & (doi >= x), lo & (doi >= x)
    if HYP == 13:
        Fq, Z, stall = P["F"], P["Z"], P["stall"]
        z = zs(d["ls_acc"]); dn = np.full(n, False); up = np.full(n, False); dn[4:] = C[4:] < C[:-4]; up[4:] = C[4:] > C[:-4]
        sh = (d["f8"] >= Fq) & ((z >= Z) if Z > 0 else True) & (dn if stall else True)
        lg = (d["f8"] <= -Fq) & ((z <= -Z) if Z > 0 else True) & (up if stall else True)
        return lg, sh
    if HYP == 14:
        W, x = P["W"], P["x"]
        dt = np.full(n, np.nan); dc = np.full(n, np.nan)
        dt[W:] = np.log(d["top_pos"][W:] / d["top_pos"][:-W]); dc[W:] = np.log(d["ls_acc"][W:] / d["ls_acc"][:-W])
        return (dt >= x) & (dc <= -x), (dt <= -x) & (dc >= x)
    if HYP == 15:
        k, h, f = P["k"], P["h"], P["f"]
        j = np.searchsorted(BTC["T"], T); ok = (j < len(BTC["T"])) & (BTC["T"][np.minimum(j, len(BTC["T"]) - 1)] == T); j = np.minimum(j, len(BTC["T"]) - 1)
        cb = np.where(ok, BTC["C"][j], np.nan); ab = np.where(ok, BTC["atr"][j], np.nan)
        rb = np.full(n, np.nan); rc = np.full(n, np.nan); rb[1:] = np.log(cb[1:] / cb[:-1]); rc[1:] = np.log(C[1:] / C[:-1])
        w = 720; sb = roll_sum(rb, w); sc = roll_sum(rc, w); sbc = roll_sum(rb * rc, w); sbb = roll_sum(rb * rb, w)
        beta = (sbc - sb * sc / w) / np.maximum(sbb - sb * sb / w, 1e-18); beta = np.concatenate([[np.nan], beta[:-1]])   # known before the move
        mb = np.full(n, np.nan); mc = np.full(n, np.nan); mva = np.full(n, np.nan)
        mb[h:] = np.log(cb[h:] / cb[:-h]); mc[h:] = np.log(C[h:] / C[:-h]); mva[h:] = (cb[h:] - cb[:-h]) / ab[:-h]
        exp = beta * mb; okb = beta >= 0.7
        return okb & (mva >= k) & (mc <= f * exp), okb & (mva <= -k) & (mc >= f * exp)
    if HYP == 16:
        W, k, v, tk = P["W"], P["k"], P["v"], P["tk"]
        mv = np.full(n, np.nan); mv[W:] = (C[W:] - C[:-W]) / d["atr"][:-W]
        vs = roll_sum(V, W); vr = np.full(n, np.nan); vr[W:] = vs[W:] / np.maximum(vs[:-W], 1e-12)
        tkm = roll_sum(d["taker"], W) / W
        return (mv <= -k) & (vr <= v) & (tkm >= 2 - tk), (mv >= k) & (vr <= v) & (tkm <= tk)
SG = {12: dict(W=(24, 72), x=(0.03, 0.08, 0.15), mode=("fade", "cont")),
      13: dict(F=(0.0003, 0.0006, 0.001), Z=(0.0, 1.5, 2.5), stall=(0, 1)),
      14: dict(W=(24, 72), x=(0.03, 0.06, 0.12)),
      15: dict(k=(3.0, 5.0), h=(1, 2), f=(0.0, 0.25, 0.5)),
      16: dict(W=(24, 72), k=(4.0, 8.0), v=(0.7, 1.0), tk=(1.0, 0.95))}[HYP]
EX = dict(m=(3.0, 6.0), T=(1.5, 3.0), H=(6, 24, 72))
# the baseline: random hours per coin, the same exits
rng = np.random.default_rng(HYP)
BASE = {}   # (m, T, H, side, late) -> (the ATR% bucket edges, the random entries' mean R per bucket): the signal vs random hours of the same volatility
for m, Tk, Hh in itertools.product(*EX.values()):
    acc = {}
    for sym in COINS:
        if sym not in DATA: continue
        d = DATA[sym]; cand = np.where((d["T"] >= A0) & (d["T"] < END))[0]
        if len(cand) < 400: continue
        idx = np.sort(rng.choice(cand, 300, replace=False))
        for s in (1, -1):
            R = run(d["O"], d["H"], d["L"], d["C"], d["atr"], d["F"], idx, np.full(len(idx), s), m, Tk, Hh)
            g = R == R; ap = d["atr"][idx] / d["C"][idx]; late = d["T"][idx] >= MID
            for lt in (False, True):
                k = g & (late == lt); a_ = acc.setdefault((s, lt), [[], []]); a_[0] += list(ap[k]); a_[1] += list(R[k])
    for (s, lt), (ap, R) in acc.items():
        ap = np.array(ap); R = np.array(R); ed = np.quantile(ap, np.linspace(0, 1, 11)[1:-1]); b = np.searchsorted(ed, ap)
        BASE[(m, Tk, Hh, s, lt)] = (ed, np.array([R[b == q].mean() for q in range(10)]), float(R.mean()))
def base(m, Tk, Hh, s_, late, ap):
    o = np.empty(len(s_))
    for s in (1, -1):
        for lt in (False, True):
            k = (s_ == s) & (late == lt)
            if k.any(): ed, mu, _ = BASE[(m, Tk, Hh, s, lt)]; o[k] = mu[np.searchsorted(ed, ap[k])]
    return o
print("случайные входы (стоп ATR, тейк, часов): лонг 2023–24 / 2025–26, шорт 2023–24 / 2025–26:", flush=True)
for m, Tk, Hh in itertools.product(*EX.values()):
    print(f"  m{m} T{Tk} H{Hh}: {BASE[(m, Tk, Hh, 1, False)][2]:+.3f} / {BASE[(m, Tk, Hh, 1, True)][2]:+.3f}, {BASE[(m, Tk, Hh, -1, False)][2]:+.3f} / {BASE[(m, Tk, Hh, -1, True)][2]:+.3f}", flush=True)
res = []
for pv in itertools.product(*SG.values()):
    P = dict(zip(SG.keys(), pv)); EVS = {}
    for sym in COINS:
        if sym not in DATA: continue
        d = DATA[sym]
        with np.errstate(all="ignore"): lg, sh = signals(d, P)
        lg = onset(lg); sh = onset(sh); win = (d["T"] >= A0) & (d["T"] < END)
        idx = np.concatenate([np.where(lg & win)[0], np.where(sh & win)[0]]); sd = np.concatenate([np.ones((lg & win).sum()), -np.ones((sh & win).sum())])
        o = np.argsort(idx, kind="stable"); EVS[sym] = (idx[o].astype(np.int64), sd[o].astype(np.int64))
    for m, Tk, Hh in itertools.product(*EX.values()):
        ra, rb, xa, xb, yy, nl, ns = [], [], [], [], {}, 0, 0
        for sym, (idx, sd) in EVS.items():
            if not len(idx): continue
            d = DATA[sym]; R = run(d["O"], d["H"], d["L"], d["C"], d["atr"], d["F"], idx, sd, m, Tk, Hh)
            g = R == R; R = R[g]; t = d["T"][idx[g]]; s_ = sd[g]; late = t >= MID
            b = base(m, Tk, Hh, s_, late, d["atr"][idx[g]] / d["C"][idx[g]])
            ra += list(R[~late]); rb += list(R[late]); xa += list(R[~late] - b[~late]); xb += list(R[late] - b[late])
            yr = (t // 86400 // 365.2425 + 1970).astype(int)
            for y in np.unique(yr): yy.setdefault(int(y), []).extend(R[yr == y])
            nl += int((s_ > 0).sum()); ns += int((s_ < 0).sum())
        if len(ra) >= 30 and len(rb) >= 30:
            al = np.array(ra + rb); xl = np.array(xa + xb)
            res.append(dict(P=P, m=m, T=Tk, H=Hh, a=[len(ra), round(float(np.mean(ra)), 3)], b=[len(rb), round(float(np.mean(rb)), 3)],
                            xa=round(float(np.mean(xa)), 3), xb=round(float(np.mean(xb)), 3),
                            t=round(float(xl.mean() / (xl.std() / np.sqrt(len(xl)))), 2), ls=[nl, ns],
                            Y={y: [len(v), round(float(np.mean(v)), 2)] for y, v in sorted(yy.items())}))
    print("  сигнал", P, "готов", flush=True)
res.sort(key=lambda x: -x["xa"])
ok2 = [x for x in res if x["xa"] > 0 and x["xb"] > 0]
print(f"\n=== гипотеза {HYP}: конфигураций {len(res)} | сверх случайных в 2023–24: {sum(x['xa'] > 0 for x in res)} | в обоих: {len(ok2)} | "
      f"в обоих и сам R > 0 в обоих: {sum(x['a'][1] > 0 and x['b'][1] > 0 for x in ok2)}", flush=True)
print("топ-20 по 2023–24 (сверх случайных) | сигнал | стоп ATR, тейк, часов | 2023–24 n,R | 2025–26 n,R | сверх случайных 23–24 / 25–26 | t | лонгов, шортов | по годам", flush=True)
for x in res[:20]: print(f"{x['P']} | m{x['m']} T{x['T']} H{x['H']} | {x['a']} | {x['b']} | {x['xa']:+.3f} / {x['xb']:+.3f} | {x['t']} | {x['ls']} | {x['Y']}", flush=True)
if len(res) > 2:
    print(f"связь (сверх случайных) 2023–24 и 2025–26: {np.corrcoef([x['xa'] for x in res], [x['xb'] for x in res])[0, 1]:.2f}; "
          f"медиана 2023–24 {np.median([x['xa'] for x in res]):+.3f}, 2025–26 {np.median([x['xb'] for x in res]):+.3f}", flush=True)
for key in SG:
    print(f"по {key}: " + "; ".join(f"{v}: {np.median([x['xa'] for x in res if x['P'][key] == v]):+.3f} / {np.median([x['xb'] for x in res if x['P'][key] == v]):+.3f}"
                                    for v in SG[key] if any(x['P'][key] == v for x in res)), flush=True)
json.dump(res, open(f"{ST}/wf/flow{HYP}.json", "w"), default=str)
print(f"flow{HYP} done", flush=True)
