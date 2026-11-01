"""prv_ev.py on the lab-store's candles (the old research folder with its data is gone): Binance 1h of the 211 P/R coins
from <LABSTORE>/data/1h/*.csv.gz; the funding history is not in the store (and the network policy denies Binance) ->
the Neuro funding features are empty (NaN) — the models of this round are trained without them, and so must the bot's be.
-> <LABSTORE>/prv_ev/<SYM>.npz.  usage: prv_ev2.py [coins...]"""
import sys, os, gzip, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "neuro_model")); sys.path.insert(0, HERE)
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
import common


def load(sym, tf="1h"):
    fn = f"{ST}/data/1h/{sym}.csv.gz"
    if not os.path.exists(fn):
        return None
    out, last = [], None
    for line in gzip.open(fn, "rt"):
        p = line.split(",")
        t = int(float(p[0]))
        if last is not None and t <= last:
            continue
        last = t
        out.append({"time": t, "open": float(p[1]), "high": float(p[2]), "low": float(p[3]), "close": float(p[4]), "volume": float(p[5])})
    return out


common.load = load; common.D = ST
import prv_ev as PE
PE.load = load; PE.D = ST


def coins211():
    src = open(os.path.join(HERE, "..", "..", "vp_poc_screener.py")).read()
    g = re.search(r'RESEARCH_COINS_127 = tuple\("""(.*?)"""', src, re.S).group(1).split() + re.search(r'RESEARCH_COINS_211 = RESEARCH_COINS_127 \+ tuple\("""(.*?)"""', src, re.S).group(1).split()
    out = []
    for c in g:
        b = c.replace("_USDT", "")
        for x in (b + "USDT", "1000" + b + "USDT"):
            if os.path.exists(f"{ST}/data/1h/{x}.csv.gz"):
                out.append(x); break
    return sorted(set(out))


if __name__ == "__main__":
    import multiprocessing as mp
    syms = sys.argv[1:] or coins211()
    print(len(syms), "coins", flush=True)
    with mp.Pool(int(os.environ.get("NP", 4))) as p:
        for res in p.imap_unordered(PE.run, syms):
            print(*res, flush=True)
    print("prv ev done", flush=True)
