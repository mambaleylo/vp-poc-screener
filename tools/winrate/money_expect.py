"""the header's yearly expectation (EXPECT_YEAR) on the restored lab: a year from $100, 12-month windows started every week
2023-02 .. 2025-10 (as port_expect.py did), money_multi.py's money (the walk-forward ⚡ pool, cross margin, the real
brackets) at the bot's 14x with the 2h shorts x0.5 (v0.99.746): ⚡ alone / + P/R, SMC, EMA / + HTF -> p10, p50, p90, the
median drawdown, the last 12 months. -> <LABSTORE>/wf/money_expect.json"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import money_multi as M
from multiprocessing import Pool
KINDS = {"dlm": {"dlm"}, "bundle": {"dlm", "prv", "smc", "emx"}, "bundle_htf": {"dlm", "prv", "smc", "emx", "htf"}}
W0, W1 = M.ts(2023, 2, 1), M.ts(2025, 10, 31)
STARTS = list(range(W0, W1 + 1, 7 * 86400))
LAST = M.ts(2025, 10, 31)   # the last 12 months the data has: Nov 2025 .. Oct 2026
def job(a):
    kind, A = a
    if kind not in M._EV: M._EV[kind] = [v for v in M.build("base") if v["mod"] in KINDS[kind]]
    return kind, A, M.run(M._EV[kind], A, A + 365 * 86400, 14.0, M.W2S, eq0=100.0)
if __name__ == "__main__":
    with Pool(4) as P:
        res = P.map(job, [(k, A) for k in KINDS for A in STARTS + [LAST]], chunksize=4)
    R = {}
    for k, A, r in res: R.setdefault(k, {})[A] = r
    out = {}
    for k in KINDS:
        E = np.array([R[k][A][0] for A in STARTS]); dd = np.array([R[k][A][3] for A in STARTS])
        out[k] = {"p10": int(np.percentile(E, 10)), "p50": int(np.median(E)), "p90": int(np.percentile(E, 90)), "dd": int(round(np.median(dd) * 100)),
                  "last12": int(R[k][LAST][0]), "n": len(STARTS), "liq": int(sum(R[k][A][4] for A in STARTS))}
        print(k, out[k], flush=True)
    json.dump(out, open(os.path.join(M.ST, "wf", "money_expect.json"), "w"), indent=1)
