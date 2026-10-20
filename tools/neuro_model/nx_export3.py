"""Neuro v3 (v0.99.650): the same model, the rule from nx_hyp*.py — ADX < 30, BTC's last hour not more than 1% against
the trade, out after 24 h (stop 1 ATR, take 3R) -> vp_neuro_model.json ver 3 with the walk-forward yearly stats."""
import json, numpy as np
import nx_h as N
from mk import ts
F = N.F
ev = []
for s in (1, -1): ev += N.build(0.995, (F["adx"] < 30) & (s * F["b_r1"] > -1), sides=(s,), hold=24)
ev.sort()
r = np.array([x[2] for x in ev]); t = np.array([x[0] for x in ev])
years = {}
for Y in (2022, 2023, 2024, 2025):
    m = (t >= ts(Y)) & (t < (ts(Y + 1) if Y < 2025 else ts(2027))); rs = r[m]
    o = sorted([x for x, mm in zip(ev, m) if mm], key=lambda x: x[1]); c = np.cumsum([x[2] for x in o])
    dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c])) if len(c) else 0.0
    wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / 604800
    years[str(Y)] = {"n": int(m.sum()), "avg": round(float(rs.mean()), 3), "wk": round(float(m.sum() / wk), 1), "sum": round(float(rs.sum()), 1),
                     "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}
    print(Y, years[str(Y)], flush=True)
mo = json.load(open(f"{N.D}/vp_neuro_model.v2.json"))
mo.update({"ver": 3, "rule": {"stop_atr": 1.0, "take_r": 3.0, "hold_h": 24}, "max_adx": 30.0, "btc_1h": 1.0})
mo["research"]["years"] = years
mo["research"]["filters"] = "ADX < 30, BTC за час не против сделки > 1%, 24 ч"
json.dump(mo, open(f"{N.D}/vp_neuro_model.json", "w"), separators=(",", ":"))
print("trades", len(ev), "avg", round(float(r.mean()), 3))
