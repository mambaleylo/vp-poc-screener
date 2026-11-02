"""the universal liquidity cut (the user: "гибкую систему, с разным шагом урезания, чтобы работала всегда, универсальным модулем"):
the strictest money (money_arm2, the header's rule) with the square-root impact of every market fill ("slip=1": the coin's daily
volatility x sqrt(the position / the daily turnover)) and the cut steps ("liq=", money_arm2.liq_g: above each share of the
coin's hourly turnover the position grows at that rate), from $100 / $10k / $100k — a year, every 3rd window, K runs dropping
5% of the trades (the money's noise); the year's multiple: the median, the bad 1-in-10; the drawdown.
usage: ALLSUF=_clr money_liq.py [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125"; K = int(ARGV[0]) if ARGV else 2; STARTS = X.STARTS[::3]; EQ = (100.0, 1e4, 1e5)
VARS = {"как считали (без проскальзывания)": "", "без урезания, с проскальзыванием": "|slip=1",
        "шаги 1:0.5 / 2:0.25 / 4:0": "|slip=1|liq=1:0.5/2:0.25/4:0", "строже 0.5:0.5 / 1:0.25 / 2:0": "|slip=1|liq=0.5:0.5/1:0.25/2:0",
        "мягче 2:0.5 / 4:0.25 / 8:0": "|slip=1|liq=2:0.5/4:0.25/8:0", "потолок 2%": "|slip=1|liq=2:0", "потолок 5%": "|slip=1|liq=5:0"}
if os.environ.get("ROUND2"):   # the second round: around the 5% cap, more noise runs, and twice the impact (the stops on thin coins)
    VARS = {}
    for sl_ in ("1", "2"):
        VARS.update({f"[×{sl_}] без урезания": f"|slip={sl_}", f"[×{sl_}] потолок 3%": f"|slip={sl_}|liq=3:0", f"[×{sl_}] потолок 5%": f"|slip={sl_}|liq=5:0",
                     f"[×{sl_}] потолок 8%": f"|slip={sl_}|liq=8:0", f"[×{sl_}] 3:0.5 / 6:0": f"|slip={sl_}|liq=3:0.5/6:0",
                     f"[×{sl_}] 4:0.5 / 8:0.25 / 12:0": f"|slip={sl_}|liq=4:0.5/8:0.25/12:0"})
_D = {}
def _init(D): _D.update(D)
def job(a):
    v, k, e0, A = a
    return v, k, e0, A, MA2.run(_D[(k, "or")], _D[(k, "ot")], A, A + 365 * 86400, RULE + VARS[v], 1, eq0=e0)
if __name__ == "__main__":
    base = MA2.orders(); OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(100 + k); D[(k, "or")] = [o for o in base if rng.random() >= 0.05]; D[(k, "ot")] = [v for v in OT if rng.random() >= 0.05]
    jobs = [(v, k, e0, A) for v in VARS for k in range(K) for e0 in EQ for A in STARTS]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=4)
    R = {}
    for v, k, e0, A, r in res: R.setdefault((v, e0), []).append((r[0] / e0, r[1]))
    out = {}
    print("\nвариант | со $100: год ×медиана (плохой) просадка | с $10k | с $100k", flush=True)
    for v in VARS:
        cells = []
        for e0 in EQ:
            x = np.array([a for a, _ in R[(v, e0)]]); dd = np.array([b for _, b in R[(v, e0)]])
            cells.append(f"×{np.median(x):,.1f} (×{np.percentile(x, 10):,.2f}) {np.median(dd) * 100:.0f}%")
            out.setdefault(v, {})[str(int(e0))] = {"p50": float(np.median(x)), "p10": float(np.percentile(x, 10)), "dd": float(np.median(dd))}
        print(f"{v} | " + " | ".join(cells), flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_liq{os.environ.get('ROUND2', '') and '2'}.json", "w"), indent=1)
    print("money liq done", flush=True)
