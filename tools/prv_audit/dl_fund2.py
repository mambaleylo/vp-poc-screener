"""neuro_model/dl_fund.py into the lab-store: the funding history (data.binance.vision, monthly) of the given coins
-> <LABSTORE>/data/funding/<SYM>.csv (t, rate).  usage: dl_fund2.py [coins...] (default: P/R's 211)"""
import os, io, sys, zipfile, urllib.request, concurrent.futures as cf
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); OUT = f"{ST}/data/funding"; os.makedirs(OUT, exist_ok=True)
B = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
months = [f"{y}-{m:02d}" for y in range(2020, 2027) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-09"]
def get(sym, mo):
    for k in range(3):
        try:
            with urllib.request.urlopen(f"{B}/{sym}/{sym}-fundingRate-{mo}.zip", timeout=60) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            return [(int(p[0]) // 1000, float(p[-1])) for p in (l.split(",") for l in z.read(z.namelist()[0]).decode().splitlines()) if p[0].isdigit()]
        except urllib.error.HTTPError as e:
            if e.code == 404: return []
        except Exception:
            pass
    return []
def coin(sym):
    fn = f"{OUT}/{sym}.csv"
    if os.path.exists(fn): return sym, -1
    rows = []
    with cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(lambda mo: get(sym, mo), months): rows += r
    rows.sort(); open(fn + ".tmp", "w").write("\n".join(f"{t},{v}" for t, v in rows)); os.replace(fn + ".tmp", fn)
    return sym, len(rows)
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if len(sys.argv) > 1: syms = sys.argv[1:]
    else:
        import re
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vp_poc_screener.py")).read()
        g = re.search(r'RESEARCH_COINS_127 = tuple\("""(.*?)"""', src, re.S).group(1).split() + re.search(r'RESEARCH_COINS_211 = RESEARCH_COINS_127 \+ tuple\("""(.*?)"""', src, re.S).group(1).split()
        syms = sorted({x for c in g for x in (c.replace("_USDT", "") + "USDT", "1000" + c.replace("_USDT", "") + "USDT") if os.path.exists(f"{ST}/data/1h/{x}.csv.gz")} | {"BTCUSDT", "ETHUSDT"})
    with cf.ThreadPoolExecutor(4) as ex:
        for s, n in ex.map(coin, syms): print(s, n, flush=True)
    print("fund done", len(os.listdir(OUT)), flush=True)
