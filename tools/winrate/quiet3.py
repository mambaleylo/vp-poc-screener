"""the bad-year lifters, honest lists: SMC 8h/12h on the bot's pipeline (smc812.py, exits as the deployed SMC, q 0.995;
both sides / longs only), 📈 Breakout and 🌊 Cascade (the bot's backtest lists); alone and together as modules 6..8 of the
bundle as deployed; friction -0.03R; also the last 12 months and the windows since Dec 2024 vs now"""
import numpy as np, json, warnings; warnings.filterwarnings("ignore")
exec(open("htf_money5.py").read().split("L = [(k")[0])
s8 = src.replace("nmod = np.zeros(5); rmod = np.zeros(5)", "nmod = np.zeros(8); rmod = np.zeros(8)").replace("def simx(", "def sim8(")
exec(s8)
B = np.vstack([BASE, rows("htf_bt_v1.json")])
BB = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
def lst(L, md, side=None):
    out = []
    for t in L:
        if t.get("r") is None or not t.get("x") or not t.get("e") or not t.get("sl"): continue
        if side is not None and t.get("d", 1) != side: continue
        st_ = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); sth = max(st_, abs(t["e"] - t.get("hs", t["sl"])) / t["e"])
        out.append((float(t.get("f") or t["t"]), float(t["x"]), float(t["r"]), st_, sth, 1.5, md, cid(t["s"]), 1.0, 1e18))
    return np.array(out, float)
S812 = json.load(open("smc812_S0.995.json"))
X = {"smc812": lst(S812, 5), "smc812L": lst(S812, 5, 1), "rbx": lst(BB["rbx"], 6), "cas": lst(BB["cas"], 7)}
q23 = (roll2 >= ts(2023, 1)) & (roll2 < ts(2024, 1)); rec = roll2 >= ts(2024, 12)
def go(parts, rk):
    A = np.vstack([B] + [X[p] for p in parts]); A = A[np.argsort(A[:, 0], kind="stable")]
    t0, t1, r_, st_, sth, buf, md, ci, wg, tbr = A.T; md = md.astype(np.int64); ci = ci.astype(np.int64); r_ = np.where(md != 0, r_ - 0.03, r_)
    use = np.ones(8, np.bool_); rk_ = np.array(rk, float) / 100
    f = lambda a, b: sim8(t0, t1, r_, st_, sth, buf, md, ci, use, rk_, int(np.searchsorted(t0, a)), b, 0.05, wg, 10.0, 20.0, 0.9, 20.0, tbr)
    Y = [f(s_, s_ + 365 * 86400.0) for s_ in roll2]
    return np.array([v[0] for v in Y]), np.array([v[1] for v in Y]), f(ts(2025, 10), ts(2026, 10))[0]
BASE_RK = [4.5, 3, 2.5, 2, 2.0]
ref, rd, rl = go([], BASE_RK + [0, 0, 0])
def show(nm, parts, extra):
    y, d, l = go(parts, BASE_RK + extra); q = y / ref; w = np.sort(y)[:len(y) // 10].mean()
    print(f"  {nm:34s} 10% ${np.percentile(y, 10):>6,.0f} 25% ${np.percentile(y, 25):>6,.0f} медиана ${np.median(y):>7,.0f} 90% ${np.percentile(y, 90):>8,.0f} | худшие 10% ср ${w:>6,.0f} | 2023-е мед ${np.median(y[q23]):>6,.0f} | просадка {np.median(d)*100:.0f}% (90%: {np.percentile(d, 90)*100:.0f}%) | 12 мес ${l:>8,.0f} | окон лучше {np.mean(q > 1)*100:3.0f}% с дек.24 {np.mean(q[rec] > 1)*100:3.0f}% ×{np.median(q[rec]):.2f}", flush=True)
w0 = np.sort(ref)[:len(ref) // 10].mean()
print(f"  {'как сейчас':34s} 10% ${np.percentile(ref, 10):>6,.0f} 25% ${np.percentile(ref, 25):>6,.0f} медиана ${np.median(ref):>7,.0f} 90% ${np.percentile(ref, 90):>8,.0f} | худшие 10% ср ${w0:>6,.0f} | 2023-е мед ${np.median(ref[q23]):>6,.0f} | просадка {np.median(rd)*100:.0f}% | 12 мес ${rl:>8,.0f}", flush=True)
for nm, parts, ex in (("SMC 8h/12h 1%", ["smc812"], [1, 0, 0]), ("SMC 8h/12h 2%", ["smc812"], [2, 0, 0]), ("SMC 8h/12h лонги 2%", ["smc812L"], [2, 0, 0]),
                      ("Пробой 1% + Каскад 1%", ["rbx", "cas"], [0, 1, 1]), ("Пробой 1.5% + Каскад 1.5%", ["rbx", "cas"], [0, 1.5, 1.5]),
                      ("Пробой 2% + Каскад 1%", ["rbx", "cas"], [0, 2, 1]),
                      ("SMC812L 1.5 + Пробой 1 + Каскад 1", ["smc812L", "rbx", "cas"], [1.5, 1, 1]),
                      ("SMC812L 2 + Пробой 1.5 + Каскад 1", ["smc812L", "rbx", "cas"], [2, 1.5, 1]),
                      ("SMC812L 1 + Пробой 1 + Каскад 1", ["smc812L", "rbx", "cas"], [1, 1, 1])):
    show(nm, parts, ex)
