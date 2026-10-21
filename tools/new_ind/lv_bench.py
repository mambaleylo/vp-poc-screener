import json, numpy as np
import nx_h; from nx_h import pain
from mk import ts
from lv_wf import GRID
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
for k in ("emx", "prv", "rbx", "cas"):
    tr = sorted([(x["t"], x["x"], x["r"], x.get("d"), x["s"]) for x in B[k] if x["t"] >= ts(2022)])
    t0 = max(ts(2022), tr[0][0] - 86400 * 15)
    mo = (ts(2026, 10) - t0) / (30.4 * 86400); r = np.array([x[2] for x in tr])
    nx_h.rng = np.random.default_rng(7); b = pain(tr, 0.45, GRID, nb=200)
    print(f"{k}: {len(r)} {len(r)/(mo*30.4/7):.1f}/нед {r.mean():+.2f}R WR{np.mean(r>0)*100:.0f}% риск {b[0]*100:.2f}% x{b[1]**(12/mo):.2f}/год ({mo:.0f} мес)")
