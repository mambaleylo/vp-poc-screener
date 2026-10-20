"""Strong zones v3 (v0.99.651): the same model, the stop 1.0 daily ATR past the zone (was 0.75), take 4R — the yearly
walk-forward stats of that rule (zm_h.py) into vp_zones_model.json ver 3."""
import json, numpy as np
import zm_h as Z
from mk import ts
LAB = "G_1.0_R4.0"
tr = Z.replay(Z.cand(0.95), LAB)
r = np.array([x[2] for x in tr]); t = np.array([x[0] for x in tr]); h = np.array([(x[1] - x[0]) / 86400 for x in tr])
years = {}
for Y in (2022, 2023, 2024, 2025):
    m = (t >= ts(Y)) & (t < (ts(Y + 1) if Y < 2025 else ts(2027))); rs = r[m]
    o = sorted([x for x, mm in zip(tr, m) if mm], key=lambda x: x[1]); c = np.cumsum([x[2] for x in o])
    dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c])) if len(c) else 0.0
    wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / 604800
    years[str(Y)] = {"n": int(m.sum()), "avg": round(float(rs.mean()), 3), "sum": round(float(rs.sum()), 1), "dd": round(dd, 1),
                     "wk": round(float(m.sum() / wk), 1), "wr": round(float((rs > 0).mean() * 100), 1), "days": round(float(h[m].mean()), 1)}
    print(Y, years[str(Y)], flush=True)
mo = json.load(open(f"{Z.D}/vp_zones_model.v2.json"))
mo.update({"ver": 3, "rule": {"buf_datr": 1.0, "tp_r": 4.0}, "exit_lab": LAB})
mo["research"]["years"] = years
json.dump(mo, open(f"{Z.D}/vp_zones_model.json", "w"), separators=(",", ":"))
print("trades", len(tr), "avg", round(float(r.mean()), 3), "wr", round(float((r > 0).mean() * 100), 1))
