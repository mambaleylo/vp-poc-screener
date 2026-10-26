"""money: the bundle as deployed + 📏 HTF variants of htf_lab5s.py (with friction -0.03R a trade; the windows since Dec 2024;
the header's way without friction too). Weights: 'W' = the both-models trades x2 risk."""
import numpy as np, warnings, json, sys; warnings.filterwarnings("ignore")
exec(open("htf_money5.py").read().split("L = [(k")[0])
def rowsw(fn, w2=1.0):
    L = json.load(open(fn)); out = []
    for t in L:
        st_ = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); sth = max(st_, abs(t["e"] - t["hs"]) / t["e"])
        out.append((float(t["t"]), float(t["x"]), float(t["r"]), st_, sth, 1.5, 4, cid(t["s"]), w2 if t.get("by") == 2 else 1.0, 1e18))
    return np.array(out, float)
V = ["B0", "H144", "T4H144", "K24", "C20", "P", "PC20", "T4C20", "T4PC20", "T4K12PC20", "Q993C20", "E04", "E06", "E04C20"]
for fr in (True, False):
    b, bd, bl, b26 = wins(BASE, [4.5, 3, 2.5, 2, 0], fr)
    ref = None
    print(f"== {'с трением −0.03R' if fr else 'как в шапке'}: без HTF медиана ${np.median(b):,.0f} 10% ${np.percentile(b, 10):,.0f} | 12 мес ${bl:,.0f}", flush=True)
    for nm in V:
        for rk, w2 in ((1.5, 1.0), (1.25, 2.0)) if nm in ("B0", "P", "T4PC20", "T4K12PC20") else ((1.5, 1.0),):
            R4 = rowsw(f"htf5_{nm}.json", w2)
            y, dd, l, l26 = wins(np.vstack([BASE, R4]), [4.5, 3, 2.5, 2, rk], fr); q = y / b
            if nm == "B0" and w2 == 1.0: ref = y
            qr = y / ref
            print(f"  {nm:10s} {rk}%{' обе×2' if w2 > 1 else '      '}: медиана ${np.median(y):>7,.0f} 10% ${np.percentile(y, 10):>6,.0f} просадка {np.median(dd)*100:.0f}% (90%: {np.percentile(dd, 90)*100:.0f}%) | 12 мес ${l:>8,.0f} 2026 ${l26:>7,.0f} | против бота: окон лучше {np.mean(qr > 1)*100:3.0f}% ×{np.median(qr):.2f} с дек.24 {np.mean(qr[recent] > 1)*100:3.0f}% ×{np.median(qr[recent]):.2f} худш ×{qr.min():.2f}", flush=True)
