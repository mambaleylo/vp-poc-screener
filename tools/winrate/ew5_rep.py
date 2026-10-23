"""ew5.py report: the setups by (zigzag k, Fibo entry, target, RSI divergence, wave overlap) — mean R, WR, by year; usage: ew5_rep.py ew5_<TFH>.pkl"""
import sys, pickle, numpy as np, pandas as pd
AV = list(sys.argv)
df = pd.DataFrame(pickle.load(open(AV[1], "rb")), columns=["sym", "t", "s", "k", "f", "tp", "div", "ovl", "R", "w", "rr"])
df["y"] = pd.to_datetime(df["t"], unit="s").dt.year
chk = set(sorted(df["sym"].unique())[2::3]); df["chk"] = df["sym"].isin(chk)
rows = []
for key, g in df.groupby(["k", "f", "tp", "div", "ovl"]):
    if len(g) < 60: continue
    by = g.groupby("y")["R"].mean()
    rows.append((g["R"].mean(), key, len(g), g["w"].mean(), g["rr"].median(), g[g["chk"]]["R"].mean(), " ".join(f"{y}:{v:+.2f}" for y, v in by.items() if y >= 2021)))
rows.sort(key=lambda x: -x[0])
print("всего сетапов", df.groupby(["k", "div", "ovl"]).size().to_dict() if len(AV) > 2 else "")
for m, (k, f, tp, dv, ov), n, wr, rr, mc, by in rows[:12]:
    print(f"zz {k} · откат {f} · цель {tp:11s} · див {'да' if dv else 'нет'} · 4-я в 1-ю {'да' if ov else 'нет'}: n{n:5d} WR {wr*100:3.0f}% RR~{rr:.1f} {m:+.3f}R (пров {mc:+.3f}) [{by}]")
