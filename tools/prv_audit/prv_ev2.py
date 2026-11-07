"""prv_ev.py on the lab-store's candles (the old research folder with its data is gone): Binance 1h of the 211 P/R coins
from <LABSTORE>/data/1h/*.csv.gz; the funding history from <LABSTORE>/data/funding (dl_fund2.py, data.binance.vision).
-> <LABSTORE>/prv_ev/<SYM>.npz.  usage: prv_ev2.py [coins...]"""
import sys, os, gzip, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "neuro_model")); sys.path.insert(0, HERE)
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
import common


C1H = os.environ.get("PRV_C1H")   # another 1h candles folder (<SYM>.csv, e.g. tools/ema_model/data/1h: to the month's end) — the monthly retrain
OUT = os.environ.get("PRV_OUT", ST)   # the events' root (<OUT>/prv_ev); the funding stays <LABSTORE>/data/funding


def load(sym, tf="1h"):
    fn = f"{C1H}/{sym}.csv" if C1H else f"{ST}/data/1h/{sym}.csv.gz"
    if not os.path.exists(fn):
        return None
    out, last = [], None
    for line in (open(fn) if C1H else gzip.open(fn, "rt")):
        p = line.split(",")
        t = int(float(p[0]))
        if last is not None and t <= last:
            continue
        last = t
        out.append({"time": t, "open": float(p[1]), "high": float(p[2]), "low": float(p[3]), "close": float(p[4]), "volume": float(p[5])})
    return out


common.load = load; common.D = ST
import nx_build
nx_build.D = ST   # the funding: <LABSTORE>/data/funding (dl_fund2.py)
import prv_ev as PE
PE.load = load; PE.D = OUT; os.makedirs(f"{OUT}/prv_ev", exist_ok=True)


def coins211():
    src = open(os.path.join(HERE, "..", "..", "vp_poc_screener.py")).read()
    g = re.search(r'RESEARCH_COINS_127 = tuple\("""(.*?)"""', src, re.S).group(1).split() + re.search(r'RESEARCH_COINS_211 = RESEARCH_COINS_127 \+ tuple\("""(.*?)"""', src, re.S).group(1).split()
    out = []
    for c in g:
        b = c.replace("_USDT", "")
        for x in (b + "USDT", "1000" + b + "USDT"):
            if os.path.exists(f"{C1H}/{x}.csv" if C1H else f"{ST}/data/1h/{x}.csv.gz"):
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
