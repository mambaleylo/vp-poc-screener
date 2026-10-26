"""new hypotheses, raw rules (no model), costs 0.1% a side + funding ignored unless said; by period 2021-23 / 2024-26:
(A) CME weekend gap: BTC's Sunday 23:00 UTC price vs Friday 21:00 (CME's close) > g% -> at Monday 00:00 trade toward the
    Friday price: take there, stop the same distance beyond, hold till Friday 20:00; BTC and the 20 largest alts (BTC's gap)
(B) new listings: coins whose Binance futures history starts after 2021-06; short at the close of day D after the
    listing, stop k x the first days' daily ATR, hold H days
(C) funding extremes: |rate| >= f at a funding time -> trade against the payers from 1h before to 1h / 4h after
(D) hour of day / weekday: the mean 1h return of the bot coins by UTC hour, 2021-23 vs 2024-26 (the sign kept?)"""
import json, os, numpy as np, calendar
from lv_engine import load_np
ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
sp = json.load(open("lv/split.json")); BOTS, CHK = sp["bot"], sp["chk"]
def per(rs, tt, nm):
    rs, tt = np.asarray(rs, float), np.asarray(tt)
    a = rs[tt < ts(2024)]; b = rs[tt >= ts(2024)]
    f = lambda x: f"{x.mean()*100:+.2f}% (n {len(x)}, WR {np.mean(x > 0)*100:.0f}%)" if len(x) else "—"
    print(f"  {nm:46s} 2021-23: {f(a):28s} 2024-26: {f(b)}", flush=True)
# ---- (A) CME gap ----
print("== (A) гэп CME выходных (доход на сделку в % цены, после комиссий)")
T, O, H, L, C, V = load_np("BTCUSDT"); idx = {int(t): i for i, t in enumerate(T)}
liq = sorted(BOTS, key=lambda s: -float(np.nansum(load_np(s)[5][-24 * 90:] * load_np(s)[4][-24 * 90:])))[:20]
weeks = []
for fr in range(ts(2021, 1, 1) + 20 * 3600, ts(2026, 9, 20), 7 * 86400):   # Fridays 20:00 (the 21:00 close = the 20:00 bar's close)
    if fr % (7 * 86400) != (ts(2021, 1, 1) + 20 * 3600) % (7 * 86400): continue
    i_f, i_s = idx.get(fr), idx.get(fr + 2 * 86400 + 3 * 3600 - 3600 + 3600 * 0)   # Sunday 23:00 bar
    i_s = idx.get(fr + 51 * 3600)   # Friday 20:00 + 51h = Sunday 23:00
    if i_f is None or i_s is None: continue
    weeks.append((fr, C[i_f], C[i_s]))
for g in (1.0, 2.0, 3.0):
    for who in ("BTC", "alts"):
        rs, tt = [], []
        for fr, pf, ps in weeks:
            gap = (ps - pf) / pf * 100
            if abs(gap) < g: continue
            side = -np.sign(gap); t0 = fr + 52 * 3600; t1 = fr + 7 * 86400   # Monday 00:00 .. Friday 20:00
            for s in (["BTCUSDT"] if who == "BTC" else liq):
                Ts, Os, Hs, Ls, Cs, Vs = load_np(s) if s != "BTCUSDT" else (T, O, H, L, C, V)
                j0 = np.searchsorted(Ts, t0); j1 = np.searchsorted(Ts, t1)
                if j0 >= len(Ts) or j1 <= j0 or Ts[j0] != t0: continue
                if s == "BTCUSDT": tgt = pf; dist = abs(Os[j0] - pf)
                else:
                    jf = np.searchsorted(Ts, fr)
                    if jf >= len(Ts) or Ts[jf] != fr: continue
                    tgt = Cs[jf]; dist = abs(Os[j0] - tgt)
                if dist <= 0 or np.sign(tgt - Os[j0]) != side: continue
                e = Os[j0]; sl = e - side * dist; r = None
                for j in range(j0, j1):
                    if (side > 0 and Ls[j] <= sl) or (side < 0 and Hs[j] >= sl): r = -dist / e; break
                    if (side > 0 and Hs[j] >= tgt) or (side < 0 and Ls[j] <= tgt): r = dist / e; break
                if r is None: r = side * (Cs[j1 - 1] - e) / e
                rs.append(r - 0.002); tt.append(t0)
        per(rs, tt, f"гэп ≥{g}%, {who}")
# ---- (B) new listings ----
print("== (B) шорт новых листингов (доход на сделку в % цены, после комиссий)")
newc = []
for s in BOTS + CHK:
    Ts = load_np(s)[0]
    if Ts[0] >= ts(2021, 6): newc.append(s)
print(f"  монет с листингом после 06.2021: {len(newc)}")
for D_ in (1, 3, 7):
    for Hd, k in ((7, 2.0), (14, 2.0), (30, 3.0), (30, 99.0)):
        rs, tt = [], []
        for s in newc:
            Ts, Os, Hs, Ls, Cs, Vs = load_np(s)
            j0 = D_ * 24
            if len(Cs) < j0 + Hd * 24 + 1: continue
            e = Cs[j0 - 1]; rng = (Hs[:j0].max() - Ls[:j0].min()) / max(D_, 1)
            sl = e + k * rng; x = None
            for j in range(j0, j0 + Hd * 24):
                if Hs[j] >= sl: x = sl; break
            if x is None: x = Cs[j0 + Hd * 24 - 1]
            rs.append((e - x) / e - 0.002); tt.append(Ts[j0])
        per(rs, tt, f"шорт с дня {D_}, держим {Hd} д, стоп {'нет' if k > 50 else f'{k}×дн.размах'}")
# ---- (C) funding extremes ----
print("== (C) экстремальный фандинг (против платящих), доход в % цены после комиссий")
for f in (0.0005, 0.001, 0.002):
    for hold in (1, 4, 8):
        rs, tt = [], []
        for s in BOTS:
            fn = f"data/funding/{s}.csv"
            if not os.path.exists(fn): continue
            fd = np.loadtxt(fn, delimiter=",", ndmin=2)
            if not len(fd): continue
            Ts, Os, Hs, Ls, Cs, Vs = load_np(s)
            for tf_, rate in fd:
                if abs(rate) < f: continue
                tf_ = int(tf_); j0 = np.searchsorted(Ts, tf_ - 3600); j1 = np.searchsorted(Ts, tf_ + hold * 3600)
                if j0 >= len(Ts) or j1 >= len(Ts) or Ts[j0] != tf_ - 3600: continue
                side = -np.sign(rate); r = side * (Os[j1] - Os[j0]) / Os[j0] + abs(rate) - 0.002   # the funding received at tf_
                rs.append(r); tt.append(tf_)
        per(rs, tt, f"|фандинг| ≥ {f*100:.2f}%, с −1ч до +{hold}ч")
# ---- (D) hour of day ----
print("== (D) средняя доходность часа (монеты бота, % за час), знак держится?")
M = np.zeros((2, 24)); N = np.zeros((2, 24)); W = np.zeros((2, 7)); NW = np.zeros((2, 7))
for s in BOTS:
    Ts, Os, Hs, Ls, Cs, Vs = load_np(s); r = Cs / Os - 1; p = (Ts >= ts(2024)).astype(int); m = Ts >= ts(2021)
    np.add.at(M, (p[m], (Ts[m] // 3600) % 24), r[m]); np.add.at(N, (p[m], (Ts[m] // 3600) % 24), 1)
    np.add.at(W, (p[m], ((Ts[m] // 86400) + 3) % 7), r[m]); np.add.at(NW, (p[m], ((Ts[m] // 86400) + 3) % 7), 1)
A = M / N * 100
print("  час UTC:  " + " ".join(f"{h:5d}" for h in range(24)))
print("  2021-23:  " + " ".join(f"{x:+.2f}" for x in A[0]))
print("  2024-26:  " + " ".join(f"{x:+.2f}" for x in A[1]))
print(f"  совпал знак в {int(np.sum(np.sign(A[0]) == np.sign(A[1])))} из 24 часов; корреляция {np.corrcoef(A[0], A[1])[0, 1]:+.2f}")
B_ = W / NW * 100; print("  дни пн..вс 2021-23: " + " ".join(f"{x:+.3f}" for x in B_[0]) + " | 2024-26: " + " ".join(f"{x:+.3f}" for x in B_[1]))
