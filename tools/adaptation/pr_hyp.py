"""P/R filter hypotheses on the saved walk-forward scores (pr_sel.py) with the deployed exits (stop by close 3 ATR,
hard 6 ATR, take 4.5 ATR; R per the hard stop). A filter acts before the slots (a skipped signal takes none); one
trade per coin & side until it exits, at most CAP open per side. q 0.99 = the bot; q 0.95 = the check set."""
import sys, numpy as np, datetime as dt
ARGS = sys.argv[1:]
import prv_wf as W
from mk import ts
L = np.load(f"{W.D}/prv_lab_cs.npz"); R = L["cs"].astype(float); R = np.where(np.abs(R) > 20, np.nan, R); KIND = L["kind"]; KB = L["k"].astype(int)
S = np.load(f"{W.D}/prv_sel.npz"); IDX, SC, T99, T95 = S["idx"], S["sc"], S["t99"], S["t95"]
F = W.F; SD, T, TF, SY = W.SD, W.T, W.TF, W.SY
# market breadth: the share of coins with a band event of the same side at the same close time
key = T.astype(np.int64) * 2 + (SD > 0)
u, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
BR = cnt[inv] / 127.0
END = T + (KB + 1) * TF * 3600
def replay(cand, cap=12, per_hour=None):
    o = cand[np.lexsort((-SC_OF[cand], T[cand]))]
    busy, act, out, hour_n = {}, [], [], {}
    for j in o:
        t = T[j]; k = (SY[j], SD[j])
        if busy.get(k, 0) > t or R[j] != R[j]: continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == SD[j]) >= cap: continue
        if per_hour:
            hk = (t, SD[j])
            if hour_n.get(hk, 0) >= per_hour: continue
            hour_n[hk] = hour_n.get(hk, 0) + 1
        busy[k] = END[j]; act.append((END[j], SD[j])); out.append(j)
    return np.array(out, dtype=int)
SC_OF = np.full(len(T), -9.0); SC_OF[IDX] = SC
rng = np.random.default_rng(1)
def port(tr, f, ev):
    eq, peak, dd, risk = 1.0, 1.0, 0.0, {}
    for _, k, i in ev:
        if k == 0: risk[i] = eq * f
        else:
            eq += risk.pop(i) * R[tr[i]]; peak = max(peak, eq); dd = max(dd, 1 - eq / peak)
            if eq <= 0.02: return 0.0, 1.0
    return eq, dd
def boots(tr, nb=300):
    mon = {}
    for i, j in enumerate(tr): mon.setdefault(int(T[j]) // (30 * 86400), []).append(i)
    bl = list(mon.values()); out = []
    for _ in range(nb):
        ev, base = [], 0
        for b in rng.choice(len(bl), len(bl)):
            idx = bl[b]; t0 = min(T[tr[i]] for i in idx)
            ev += [(base + T[tr[i]] - t0, 0, i) for i in idx] + [(base + END[tr[i]] - t0, 1, i) for i in idx]; base += 40 * 86400
        out.append(sorted(ev, key=lambda e: (e[0], -e[1])))
    return out
def stat(name, tr, f):
    r = R[tr]; order = tr[np.argsort(END[tr], kind="stable")]
    run = w = 0
    for j in order: run = run + 1 if KIND[j] in (0, 1) else 0; w = max(w, run)
    yrs = " ".join(f"{r[(T[tr] >= ts(y)) & (T[tr] < ts(y + 1))].mean():+.2f}" for y in (2023, 2024, 2025, 2026))
    bs = boots(tr); rr = [port(tr, f, b) for b in bs]; xs = np.array([a[0] for a in rr]); ds = np.array([a[1] for a in rr])
    print(f"{name:46s} {len(tr):5d} {r.mean():+.3f} {np.mean(r > 0) * 100:3.0f}% серия {w:2d} | {yrs} | {f*100:.1f}%: x{np.median(xs):6.1f} dd {np.median(ds)*100:3.0f}/{np.quantile(ds, .9)*100:3.0f}%", flush=True)
if __name__ == "__main__":
    q = ARGS[0] if ARGS else "99"
    base = IDX[SC >= (T99 if q == "99" else T95)]
    f = 0.05 if q == "99" else 0.01
    b24, b4, b1 = SD * F["b_r24"], SD * F["b_r4"], SD * F["b_r1"]
    btc = b24 > -4
    print(f"== q {q}: сделок, ср.R, WR, серия стопов | 2023 2024 2025 2026 | рост и просадка (обычная / 1 из 10)")
    H = [("без фильтров", base, {}), ("фильтр BTC 24ч 4% (в боте)", base[btc[base]], {})]
    for lim in (2, 3):
        H.append((f"BTC 24ч 4% + BTC 4ч против > {lim}%", base[(btc & (b4 > -lim))[base]], {}))
    H.append(("BTC 24ч 4% + BTC 1ч против > 1%", base[(btc & (b1 > -1))[base]], {}))
    for br in (0.10, 0.20, 0.30):
        H.append((f"BTC + широта рынка < {br:.0%} монет", base[(btc & (BR < br))[base]], {}))
        H.append((f"только широта < {br:.0%}", base[(BR < br)[base]], {}))
    H.append(("BTC + монета за 24ч не упала/выросла > 15%", base[(btc & (SD * F["roc24"] > -15))[base]], {}))
    H.append(("BTC + по тренду дня (EMA200)", base[(btc & (SD * F["dd_e200"] > 0))[base]], {}))
    H.append(("BTC + против тренда дня", base[(btc & (SD * F["dd_e200"] < 0))[base]], {}))
    H.append(("BTC + ADX < 30", base[(btc & (F["adx"] < 30))[base]], {}))
    H.append(("BTC + BTC выше EMA50 для лонга / ниже для шорта", base[(btc & (SD * F["b_e50"] > 0))[base]], {}))
    for ph in (1, 2, 3):
        H.append((f"BTC + не больше {ph} входов в одну сторону за час", base[btc[base]], {"per_hour": ph}))
    for cap in (6, 4):
        H.append((f"BTC + не больше {cap} открытых в сторону", base[btc[base]], {"cap": cap}))
    for nm, cand, kw in H:
        stat(nm, replay(cand, **kw), f)
