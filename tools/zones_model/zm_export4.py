"""Strong zones v4 (v0.99.666): the same model and stop / take, the entry by one limit at the zone's FAR edge (0.2% before
it) instead of the ladder near + far (zm_x4 / zm_x5.py, the EMA lesson: the deeper fill is the better one). The bot's
set (q 0.95) +0.47R a trade vs +0.36R, x20-23 vs x10 at an equal drawdown; the check set (q 0.85) +0.33R vs +0.21R,
x1700-1900 vs x120; every year better in both. Yearly stats of the rule (busy until the real exit) -> model ver 4."""
import json, numpy as np
import zm_h as Z
from zm_x4 import labels
from zm_x2 import replay
from mk import ts
idx = Z.cand(0.95); idx = idx[np.argsort(Z.SYM[idx], kind="stable")]
R, Hh = labels(idx, p1=1.0)
tr = replay(Z.cand(0.95), R, Hh)
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
mo = json.load(open("/home/user/vp-poc-screener/vp_zones_model.json"))
assert mo["ver"] == 3
mo.update({"ver": 4, "rule": {"buf_datr": 1.0, "tp_r": 4.0, "entry": "far"}})
mo["research"]["years"] = years
json.dump(mo, open("vp_zones_model_v4.json", "w"), separators=(",", ":"))
print("trades", len(tr), "avg", round(float(r.mean()), 3), "wr", round(float((r > 0).mean() * 100), 1))
# the monthly expectation (ZM_EXPECT in the bot) from the same trades, by the exit month; 2025-26 shown
import datetime as dt
from collections import defaultdict
M = defaultdict(list)
for x in tr: M[dt.datetime.utcfromtimestamp(x[1]).strftime("%Y-%m")].append(x[2])
ms = sorted(M); sums = [sum(M[m]) for m in ms]
ent = sorted(x[0] for x in tr if x[0] >= ts(2025)); zd = len({x[0] // 86400 for x in tr if x[0] >= ts(2025)})
expect = {"months": [[m, len(M[m]), round(sum(M[m]), 1)] for m in ms if m >= "2025-01"], "all_months": len(ms),
          "pos_months": sum(1 for s in sums if s > 0), "worst": round(min(sums), 1), "best": round(max(sums), 1),
          "max_gap_d": int(round(float(np.max(np.diff(ent))) / 86400)), "zone_days_share": round(zd / ((ts(2026, 10) - ts(2025)) / 86400), 2)}
json.dump(expect, open("zm_expect_v4.json", "w"), separators=(",", ":"), ensure_ascii=False)
print(json.dumps(expect)[-160:])
