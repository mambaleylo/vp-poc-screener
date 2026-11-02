"""The cards' "2025–26" row split in two (the user: "обучились на 25, 26 год уже другой, а так все в кучу"): a model file's
research.years["2025"] (2025-01 .. the data's end, scored by the model trained before 2025) -> "2025" and "2026", re-counted
from the module's backtest list (vp_bt_trades.json) — only when the list's 2025+ trades are exactly that row's (the count and
the sum agree), else the file is left as it is. n, avg, wk (a week = 7 days; 2026 up to END), sum, dd (by exit), wr.
usage: split_years.py mod:model_file …   e.g. emx:vp_ema_model.json cas:vp_cas_model.json prv:vp_prv_model.json"""
import sys, json, calendar, numpy as np
ROOT = "/home/user/vp-poc-screener"
ts = lambda y, m=1: calendar.timegm((y, m, 1, 0, 0, 0))
END = ts(2026, 10)   # the lists' and the research's end (the 1h data till 2026-09)
def stats(L, a, b):
    L = [x for x in L if a <= x["t"] < b]
    if not L: return {"n": 0, "avg": 0, "wk": 0, "sum": 0, "dd": 0, "wr": 0}
    r = np.array([x["r"] for x in L]); o = np.array([x["r"] for x in sorted(L, key=lambda x: x.get("x", x["t"]))]); c = np.cumsum(o)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    return {"n": len(r), "avg": round(float(r.mean()), 3), "wk": round(len(r) / ((min(b, END) - a) / 604800), 1), "sum": round(float(r.sum()), 1),
            "dd": round(dd, 1), "wr": round(float((r > 0).mean() * 100), 1)}
if __name__ == "__main__":
    BT = json.load(open(f"{ROOT}/vp_bt_trades.json"))
    for arg in sys.argv[1:]:
        mod, fn = arg.split(":"); m = json.load(open(f"{ROOT}/{fn}")); ys = m["research"]["years"]; old = ys.get("2025")
        if "2026" in ys or not old: print(f"{fn}: уже раздельно / нет 2025"); continue
        L = BT[mod]; tail = [x for x in L if x["t"] >= ts(2025)]
        if len(tail) != old["n"] or abs(sum(x["r"] for x in tail) - old["sum"]) > 0.5 + 0.01 * abs(old["sum"]):
            print(f"{fn}: список ({len(tail)}, {sum(x['r'] for x in tail):.1f}R) не сходится со строкой 2025–26 ({old['n']}, {old['sum']}R) — не трогаю"); continue
        a, b = stats(L, ts(2025), ts(2026)), stats(L, ts(2026), ts(2027))
        ys["2025"], ys["2026"] = a, b
        json.dump(m, open(f"{ROOT}/{fn}", "w"), separators=(",", ":"))
        print(f"{fn}: 2025–26 {old['n']} сделок {old['avg']:+}R -> 2025: {a['n']} {a['avg']:+}R WR {a['wr']}% · 2026: {b['n']} {b['avg']:+}R WR {b['wr']}%")
