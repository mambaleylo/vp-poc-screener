"""📈 Breakout (rbx, virtual so far) into the Binance bundle: the strictest money (money_arm2.run, the bot's settings at 17x)
with the breakout's backtest list (644 trades 2021-2026, the stop's R, its partial and break-even in the list's R) at
1 / 2 / 3% — 144 windows 2023-2025 (2 seeds) and the 2022 windows. -> the table"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_arm2 as MA2, money_multi as M, money_expect as X, money_params as MP
from multiprocessing import Pool
F = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=17"
def rbx():
    out = []
    for t in json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))["rbx"]:
        sym = M.bn(t["s"])
        if not sym: continue
        scl = 1000.0 if sym.startswith("1000") and not t["s"].startswith("1000") else 1.0; st = max(0.002, abs(t["e"] - t["sl"]) / t["e"])
        out.append({"t0": int(t["f"]), "t1": int(t["x"]), "r": float(t["r"]) - 0.03, "st": st, "sth": st, "mod": "rbx", "sym": sym, "side": t["d"], "e": t["e"] * scl, "stream": None})
    return out
RISK = [0, 1.0, 2.0, 3.0]
_D = {}
def _init(D): _D.update(D)
def job(a):
    rk, sd, A, B, w = a
    OT = _D["ot"] + (_D["rbx"] if rk else [])
    return rk, sd, A, w, MA2.run(_D["or" + w], OT, A, B, F, sd, rk=dict(MP.rk(emx=3.0), rbx=rk or 0.0))
if __name__ == "__main__":
    D = {"or": MA2.orders(), "ot": [v for v in M.build("base") if v["mod"] != "dlm"], "rbx": rbx()}
    D["or22"] = MA2.orders("_y2022")
    W22 = [(M.ts(2022, m), M.ts(2022, m) + 182 * 86400) for m in range(1, 8)]
    jobs = [(rk, sd, A, A + 365 * 86400, "") for rk in RISK for sd in (1, 2) for A in X.STARTS] + [(rk, sd, A, B, "22") for rk in RISK for sd in (1, 2) for A, B in W22]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=6)
    R = {}
    for rk, sd, A, w, v in res: R.setdefault((rk, w), {}).setdefault(A, []).append(v)
    b = np.array([np.mean([x[0] for x in R[(0, "")][A]]) for A in X.STARTS])
    for rk in RISK:
        E = np.array([np.mean([x[0] for x in R[(rk, "")][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[(rk, "")][A]]) for A in X.STARTS])
        E22 = np.array([np.mean([x[0] for x in R[(rk, "22")][A]]) for A, _ in W22])
        print(f"📈 Пробой {rk}%: 2023-25 плохой ${np.percentile(E, 10):,.0f} обычный ${np.median(E):,.0f} просадка {np.median(dd)*100:.0f}% лучше в {int((E > b * 1.001).sum())}/144 | 2022 6 мес.: худшее ${E22.min():,.0f} медиана ${np.median(E22):,.0f}", flush=True)
    print("rbx done", flush=True)
