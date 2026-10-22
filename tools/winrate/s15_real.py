"""Robustness of a selected 15m family (default deep2, exit E0): the walk-forward trades re-simulated on Binance 1m bars
(40 coins, 2024-10 .. 2026-09) — the stop / take order inside a 15m bar exactly, and stricter fills:
  A  as the 15m engine (fill on touch, maker entry + maker take, taker stop / time)
  B  the limit fills only when the price trades 0.05% THROUGH it
  C  B + every fee taker (0.05% a side)
  D  B + 0.05% slippage on the stop
usage: s15_real.py FAM EXIT Q"""
import sys
ARG = sys.argv[1:]
import os, json, numpy as np, warnings; warnings.filterwarnings("ignore")
import s15_engine as E
from s15_wf import load, scores, select
from mk import ts
fam, e, q = (ARG + ["deep2", "0", "0.98"])[:3]; e = int(e); q = float(q)
D = load("s15", [E.FAMS.index(fam)])
if os.path.exists(f"s15_sc_{fam}_{e}.npz"):
    z = np.load(f"s15_sc_{fam}_{e}.npz", allow_pickle=True); SC, THR = z["SC"], z["THR"].item()
else:
    SC, THR = scores(D, e); np.savez(f"s15_sc_{fam}_{e}.npz", SC=SC, THR=np.array(THR, dtype=object))
TK, ST, HD = E.EXITS[e]
W = {"deep2": 4, "deep3": 4, "bb": 1, "ema_pb": 2, "vwap2": 1, "sweep": 0}[fam]
avail = {f[:-4] for f in os.listdir("data/1mz")}
out = {k: [] for k in "ABCD"}; base = []; nfill = {"A": 0, "B": 0}; tot = 0
for setname, sub in (("train", ~D["chk"]), ("check", D["chk"])):
    sel = select(D, e, SC, THR, q, 12, sub)
    sel = sel[D["t"][sel] >= ts(2024, 10)]
    by = {}
    for i in sel: by.setdefault(D["names"][D["sym"][i]], []).append(i)
    for sym, idx in by.items():
        if sym not in avail: continue
        T15, O15, H15, L15, C15, V15 = E.load15(sym); atr15 = E.wilder(H15, L15, C15, 14)
        z = np.load(f"data/1mz/{sym}.npz"); t1, o1, h1, l1, c1 = z["t"], z["o"], z["h"], z["l"], z["c"]
        zz = np.load(f"s15/{sym}.npz"); pos = {(int(t), int(s), int(f)): k for k, (t, s, f) in enumerate(zip(zz["t"], zz["side"], zz["fam"]))}
        for i in idx:
            t = int(D["t"][i]); s = int(D["side"][i]); k = pos.get((t, s, E.FAMS.index(fam)))
            if k is None: continue
            bi = int(zz["i"][k]); a = float(atr15[bi]); c0 = float(C15[bi])
            if fam in ("deep2", "deep3"): lv = c0 - s * (2.0 if fam == "deep2" else 3.0) * a
            else: lv = c0 - s * float(zz["F"][k][E.FNAMES.index("depth")]) * a
            j0 = np.searchsorted(t1, T15[bi] + 900); j1 = j0 + W * 15
            if j1 + HD * 15 >= len(t1) or t1[j0] != T15[bi] + 900: continue
            tot += 1; base.append(float(D["R"][e][i]))
            for mode in "AB":
                thr_ = lv if mode == "A" else lv * (1 - s * 0.0005)
                hit = np.flatnonzero((l1[j0:j1] <= thr_) if s > 0 else (h1[j0:j1] >= thr_))
                if not len(hit): continue
                f = j0 + int(hit[0]); fill = min(lv, o1[f]) if s > 0 else max(lv, o1[f])
                nfill[mode] += 1
                risk = ST * a; sl = fill - s * risk; tp = fill + s * TK * a
                end = min(len(c1), f + HD * 15); ex = c1[end - 1]; kind = "time"; kk = end - 1 - f
                for b in range(f, end):
                    if (l1[b] <= sl) if s > 0 else (h1[b] >= sl):
                        ex = o1[b] if (b > f and ((o1[b] <= sl) if s > 0 else (o1[b] >= sl))) else sl; kind = "stop"; kk = b - f; break
                    if b > f and ((h1[b] >= tp) if s > 0 else (l1[b] <= tp)):
                        ex = tp; kind = "take"; kk = b - f; break
                fund = 0.0003 * (kk + 1) / 1440 * fill
                def R(fin, fout, slip=0.0):
                    x = ex - s * slip * fill if kind == "stop" else ex
                    return (s * (x - fill) - (fin + fout) * fill - fund) / risk
                if mode == "A":
                    out["A"].append((R(0.0002, 0.0002 if kind == "take" else 0.0005), kind == "take", setname))
                else:
                    out["B"].append((R(0.0002, 0.0002 if kind == "take" else 0.0005), kind == "take", setname))
                    out["C"].append((R(0.0005, 0.0005), kind == "take", setname))
                    out["D"].append((R(0.0002, 0.0002 if kind == "take" else 0.0005, 0.0005), kind == "take", setname))
print(f"{fam} E{e} q{q}: {tot} selected trades on the 40 coins with 1m data (2024-10+); 15m engine: WR? avg {np.mean(base):+.3f}R")
print(f"   filled: on touch {nfill['A']} ({nfill['A']/max(tot,1)*100:.0f}%), trade-through 0.05% {nfill['B']} ({nfill['B']/max(tot,1)*100:.0f}%)")
for k, nm in (("A", "1m, fill on touch"), ("B", "1m, fill 0.05% through"), ("C", "B + all fees taker"), ("D", "B + 0.05% stop slippage")):
    for st in ("train", "check"):
        rr = [x for x in out[k] if x[2] == st]
        if rr:
            r = np.array([x[0] for x in rr]); w = np.array([x[1] for x in rr])
            print(f"   {nm:26s} {st:5s} n {len(r):5d} WR {w.mean()*100:3.0f}% avg {r.mean():+.3f}R  sum {r.sum():+.0f}R")
