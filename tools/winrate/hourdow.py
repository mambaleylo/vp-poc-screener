"""Hypothesis 9 (the user picked it): the hour / the weekday per module — the backtest lists as the bot trades (vp_bt_trades.json:
⚡, P/R, SMC, EMA, HTF, Классика): the entry's UTC 4h block and weekday; the bins dropped = those with a negative mean R in 2023–24
(n >= 20); the check: 2025–26 (never used): the mean R and the sum kept vs all, the trades dropped. -> printed + hourdow.json"""
import json, calendar, numpy as np, time
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
ts = lambda y: calendar.timegm((y, 1, 1, 0, 0, 0)); DOW = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
out = {}
for mod, nm in (("dlm", "⚡ Лимитки"), ("prv", "P/R"), ("smc", "SMC"), ("emx", "EMA"), ("htf", "HTF"), ("cfl", "Классика")):
    L = [x for x in B[mod] if ts(2023) <= int(x["t"]) < ts(2027)]
    t = np.array([int(x["t"]) for x in L]); r = np.array([float(x["r"]) for x in L]); A = t < ts(2025)
    hb = (t % 86400) // 14400; dw = np.array([time.gmtime(int(x)).tm_wday for x in t])
    res = {}
    for kind, key, lab in (("hour", hb, lambda k: f"{k * 4:02d}–{k * 4 + 4:02d}"), ("dow", dw, lambda k: DOW[k])):
        bad = [k for k in sorted(set(key)) if ((key == k) & A).sum() >= 20 and r[(key == k) & A].mean() < 0]
        keep = ~np.isin(key, bad); Bm = ~A
        res[kind] = {"bad": [lab(k) for k in bad], "train_all": round(float(r[A].mean()), 3), "train_keep": round(float(r[A & keep].mean()), 3),
                     "test_all": round(float(r[Bm].mean()), 3), "test_keep": round(float(r[Bm & keep].mean()), 3) if (Bm & keep).any() else None,
                     "test_sum_all": round(float(r[Bm].sum()), 1), "test_sum_keep": round(float(r[Bm & keep].sum()), 1), "test_drop": int((Bm & ~keep).sum()),
                     "test_n": int(Bm.sum()), "test_dropped_r": round(float(r[Bm & ~keep].mean()), 3) if (Bm & ~keep).any() else None}
        o = res[kind]
        print(f"{nm:11s} {('час UTC' if kind == 'hour' else 'день'):7s} | убрать по 2023–24: {', '.join(o['bad']) or '—':22s} | 2025–26: "
              f"R {o['test_all']:+.3f} -> {o['test_keep'] if o['test_keep'] is not None else float('nan'):+.3f}, сумма {o['test_sum_all']} -> {o['test_sum_keep']}, "
              f"убрано {o['test_drop']} из {o['test_n']} (их R {o['test_dropped_r'] if o['test_dropped_r'] is not None else '—'})", flush=True)
    out[mod] = res
json.dump(out, open("/home/user/vp-lab-store/wf/hourdow.json", "w"), indent=1)
