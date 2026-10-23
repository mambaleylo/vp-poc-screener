"""lab after v0.99.689: a third ⚡ stream next to the deployed 4h wick + 2h close-2ATR, pooled as the bot trades them
(every order stands, the first of a coin & side to fill is the trade, 20 a side), money at 20 positions"""
exec(open("pool2h.py").read().split("W4 = stream")[0].replace(
    "lv = ((L[bi] if s > 0 else H[bi]) if anchor == \"wick\" else C[bi]) - s * depth * a",
    "lv = ((L[bi] if s > 0 else H[bi]) if anchor == \"wick\" else C[bi]) - s * depth * (float(A28[bi]) if anchor == \"a28\" else a)").replace(
    "Tb, H, L, C, atr, pos = cache[sym]; bi", "Tb, H, L, C, atr, pos, A28 = cache[sym]; bi").replace(
    "cache[sym] = (Tb, H, L, C, E.wilder(H, L, C, 14), {int(x): j for j, x in enumerate(Tb)})",
    "cache[sym] = (Tb, H, L, C, E.wilder(H, L, C, 14), {int(x): j for j, x in enumerate(Tb)}, E.wilder(H, L, C, 28))"))
exec(open("pool2h.py").read().split("def pool(evs)")[1].split("roll = np.arange")[0].join(["def pool(evs)", ""]))
W4 = stream("s23_4h", 2, 0, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, 0.99)
C2 = stream("s21h2", 0, 1, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, 0.99)
C3 = {"2ч тень 1ATR": lambda: stream("s21h2", 2, 1, "s26_s21h2_wick1_1.npz", "s21h2_engine", 2, "wick", 1.0, 0.99),
      "4ч закр 2ATR": lambda: stream("s20h4", 0, 1, "s26_s20h4_d2_1.npz", "s20h4_engine", 4, "close", 2.0, 0.99),
      "4ч закр 2ATR28": lambda: stream("s20h4", 3, 1, "s26_s20h4_d2a28_1.npz", "s20h4_engine", 4, "a28", 2.0, 0.99),
      "4ч тень 0.75": lambda: stream("s23_4h", 1, 0, "s26_s23_4h_w075_0.npz", "s23_engine", 4, "wick", 0.75, 0.99),
      "4ч тень 1.25": lambda: stream("s23_4h", 3, 0, "s26_s23_4h_w125_0.npz", "s23_engine", 4, "wick", 1.25, 0.99),
      "1ч тень 1ATR": lambda: stream("s19h", 2, 1, "s26_s19h_wick1_1.npz", "s19h_engine", 1, "wick", 1.0, 0.99),
      "1ч закр 2ATR28": lambda: stream("s19h", 3, 1, "s26_s19h_d2a28_1.npz", "s19h_engine", 1, "a28", 2.0, 0.99)}
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
def show(nm, evs):
    P = pool(evs); t0, t1, R, STv = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    yr = (t0 // 31557600 + 1970).astype(int)
    by = " ".join(f"{y_}:{R[yr == y_].mean():+.2f}" for y_ in range(2022, 2027))
    print(f"{nm:28s} n{len(R)} {R.mean():+.3f}R [{by}] | 4%: медиана ${np.median(y[:, 0]):,.0f} 10% ${np.percentile(y[:, 0], 10):,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}%/{np.percentile(y[:, 1], 90)*100:.0f}% | жёстко ${np.median(yh):,.0f}", flush=True)
show("4ч тень + 2ч закр (сейчас)", W4 + C2)
for k, f in C3.items():
    try:
        ev = f(); show(f"  + {k}", W4 + C2 + ev)
    except Exception as e:
        print(k, "ошибка", repr(e)[:200], flush=True)
