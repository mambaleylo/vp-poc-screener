"""the ⚡ engine v2 over the coin set: the bot's 210 (RESEARCH_COINS_211 without USDC) + the 226 new ones (>= 50M $ a month in
2026, history from 2025-10) -> <LABSTORE>/feat/<stream>/<SYM>.npz. usage: dlm_build.py PART NPARTS"""
import sys, os, json, numpy as np, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as E
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
W, NW = int(sys.argv[1]), int(sys.argv[2])
from common import V
avail = {f[:-7] for f in os.listdir(E.DATA)}
def bn(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in avail: return c
base = sorted({bn(c) for c in V.RESEARCH_COINS_211 if c != "USDC_USDT" and bn(c)})
U = json.load(open(os.path.join(ST, "universe.json")))
new = sorted({r[0] for r in U if not r[1] and r[2] <= 1759276800 and r[3] >= 1790812800 - 3 * 86400 and r[4] >= 50e6})
coins = base + [c for c in new if c not in base]
json.dump({"base": base, "new": [c for c in new if c not in base]}, open(os.path.join(ST, "feat_coins.json"), "w"))
mine = (base if os.environ.get("BASE_ONLY") else coins)[W::NW]   # BASE_ONLY=1: the bot's 210 only (the new charts' check)
for st in os.environ.get("STREAMS", "wick4h,close2h").split(","):
    os.makedirs(f"{ST}/feat/{st}", exist_ok=True)
    B = E.btc_ctx(st)
    t0 = time.time()
    for k, c in enumerate(mine):
        fn = f"{ST}/feat/{st}/{c}.npz"
        if os.path.exists(fn): continue
        try:
            r = E.coin(c, st, B)
        except Exception as e:
            print("ERR", st, c, repr(e)[:200], flush=True); continue
        if r is None: r = {"t": np.zeros(0, np.int64)}
        np.savez_compressed(fn + ".tmp.npz", **r); os.replace(fn + ".tmp.npz", fn)
    print(W, st, len(mine), f"{time.time() - t0:.0f}s", flush=True)
