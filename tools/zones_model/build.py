"""Stage A: the bot's own candidates (oc_candidates_mtf) + its 23 features on Binance 1h history,
every 48h per coin; labels = the ladder replay for each take (bot rules)."""
import sys, os, json, time, pickle, bisect
ARGS = sys.argv[1:]
from common import V, load, coins, D
import multiprocessing as mp
STEP = 48
HOLD = 14 * 24
TPS = V.ZONES_OC_TPS
BTC = None

def build_coin(sym):
    out_fn = f"{D}/ds/{sym}.pkl"
    if os.path.exists(out_fn):
        return sym, -1
    cs = load(sym)
    if not cs or len(cs) < 24 * 140:
        return sym, 0
    btc = V._oc_btc_series(load("BTCUSDT"))
    rows = []
    t0 = time.time()
    # index of a gap-free history start: Binance data is continuous; aligned snapshots every STEP h
    for i in range(24 * 130, len(cs) - HOLD, STEP):
        t = cs[i]["time"]
        win = cs[i - V.ZONES_OWN_BARS:i] if i >= V.ZONES_OWN_BARS else cs[:i]
        fut = cs[i:i + HOLD]
        bv = V._oc_btc_ctx(btc, t)
        by_tf = [(h, V._oc_agg(cs[max(0, i - h * (n + 1)):i], h)[-n:]) for h, n in V.OC_TF_BARS]
        for c in V.oc_candidates_mtf(by_tf):
            rs = []
            for tp in TPS:
                r = V.zone_ladder_sim(fut, V._oc_group(c), tp, t, t + HOLD * 3600)
                rs.append(None if not r else (round(r["r"], 4), round((r["t_out"] - r["t_in"]) / 86400, 3), r["result"][0], r["filled"]))
            x = V._oc_vec(c, V.oc_ctx_feats(win, c, bv))
            rows.append({"i": i, "t": t, "side": c["side"], "lo": c["lo"], "hi": c["hi"], "tf": c.get("tf", 1),
                         "rank": c["f"]["rank"], "atr": c["atr"], "x": [round(v, 5) for v in x], "r": rs})
    os.makedirs(f"{D}/ds", exist_ok=True)
    with open(out_fn, "wb") as f:
        pickle.dump(rows, f)
    return sym, len(rows), round(time.time() - t0)

if __name__ == "__main__":
    syms = ARGS or coins()
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(build_coin, syms):
            print(*res, flush=True)
