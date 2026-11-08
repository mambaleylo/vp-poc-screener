"""dl_metrics.py into the lab-store (data.binance.vision, the host the network allows): the 211 P/R / lv coins + BTC, ETH
-> <LABSTORE>/data/metrics/<SYM>.csv (t, oi, oiv, top_acc, top_pos, ls_acc, taker; the hour's last 5-min values, the mean taker)"""
import os, sys, re, glob
HERE = os.path.dirname(os.path.abspath(__file__)); ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
src = open(os.path.join(HERE, "dl_metrics.py")).read()
src = src.replace('B = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/daily/metrics"',
                  'B = "https://data.binance.vision/data/futures/um/daily/metrics"').replace('OUT = "data/metrics"', f'OUT = "{ST}/data/metrics"')
src = src.split("syms = sorted(")[0]
exec(src)
if __name__ == "__main__":
    import multiprocessing as mp, json
    sp = json.load(open(os.path.join(HERE, "..", "winrate", "lv", "split.json")))
    syms = sys.argv[1:] or sorted(set(sp["bot"] + sp["check"] + ["BTCUSDT", "ETHUSDT"]))   # or the coins given
    with mp.Pool(6) as p:
        for s, n in p.imap_unordered(coin, syms):
            print(s, n, flush=True)
    print("metrics done", len(os.listdir(OUT)), flush=True)
