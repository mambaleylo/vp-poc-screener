"""Peak Reversal: coin auto-selection by the coin's own past years (no peeking) for a few rules"""
import glob, numpy as np
from prv_build import CONFIGS, LABELS
PC = {fn.split("/")[-1][:-4]: np.load(fn) for fn in sorted(glob.glob("prv/*.npz"))}
def yr(y):
    a = (y - 2020) * 12
    return slice(a, min(a + 12, 6 * 12 + 9))
WK = {y: (52.14 if y < 2026 else 39.0) for y in range(2020, 2027)}
def idx(tf, b, mult, kind, sk, tk, hd):
    return CONFIGS.index((tf, b, mult, kind)), LABELS.index((sk, tk, hd))
RULES = {"бот: 1ч EMA20 ×2 фитиль, стоп 1, тейк 2R, 48": idx("1h", ("EMA", 20), 2.0, "wick", 1.0, 2.0, 48),
         "бот: 4ч EMA20 ×2 фитиль, стоп 1, тейк 2R, 48": idx("4h", ("EMA", 20), 2.0, "wick", 1.0, 2.0, 48),
         "4ч EMA14 ×1.5 возврат, стоп 2, тейк к средней, 24": idx("4h", ("EMA", 14), 1.5, "reent", 2.0, "mid", 24),
         "1ч SMA20 ×1.5 фитиль, стоп 2, тейк 2R, 24": idx("1h", ("SMA", 20), 1.5, "wick", 2.0, 2.0, 24)}
for nm, (ci, li) in RULES.items():
    for min_n, min_avg in ((None, None), (30, 0.0), (30, 0.1), (50, 0.15)):
        line = []
        for y in (2022, 2023, 2024, 2025):
            n = s = 0
            for sym, z in PC.items():
                N, S = z["N"][ci, li], z["S"][ci, li]
                if min_n is not None:
                    pn = N[:(y - 2020) * 12].sum(); ps = S[:(y - 2020) * 12].sum()
                    if pn < min_n or ps / pn < min_avg:
                        continue
                ys = [yr(y)] if y < 2025 else [yr(2025), yr(2026)]
                n += sum(N[q].sum() for q in ys); s += sum(S[q].sum() for q in ys)
            wk = WK[y] if y < 2025 else WK[2025] + WK[2026]
            line.append(f"{y if y < 2025 else '2025–26'}: {s / n if n else 0:+.2f}R {n / wk:.0f}/нед")
        tag = "все монеты" if min_n is None else f"монеты с прошлым ≥{min_n} сд. и >{min_avg}R"
        print(f"{nm} · {tag}: " + " | ".join(line), flush=True)
