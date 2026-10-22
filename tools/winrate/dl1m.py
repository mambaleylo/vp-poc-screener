"""1m Binance USDT-M klines (the S3 mirror of data.binance.vision), 2024-10 .. 2026-09, for the most liquid coins:
data/1mz/<SYM>.npz with t (int64 s) and o, h, l, c, qv (float32 / float64 quote volume)"""
import os, io, zipfile, urllib.request, concurrent.futures as cf, numpy as np, sys
B = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/klines"
COINS = """BTC ETH SOL XRP DOGE BNB ADA AVAX LINK SUI 1000PEPE TRX LTC DOT NEAR APT ARB OP WIF INJ TIA SEI ENA WLD FET
ORDI ONDO AAVE UNI FIL ETC BCH ATOM 1000BONK JUP TON PENDLE LDO CRV GALA""".split()
OUT = "data/1mz"; os.makedirs(OUT, exist_ok=True)
months = [f"{y}-{m:02d}" for y in (2024, 2025, 2026) for m in range(1, 13) if "2024-10" <= f"{y}-{m:02d}" <= "2026-09"]
def get(sym, mo):
    url = f"{B}/{sym}/1m/{sym}-1m-{mo}.zip"
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            a = np.genfromtxt(io.BytesIO(z.read(z.namelist()[0])), delimiter=",", usecols=(0, 1, 2, 3, 4, 7), invalid_raise=False)
            a = a[np.isfinite(a[:, 0])]
            return a
        except Exception:
            pass
    return None
def coin(c):
    sym = c + "USDT"; fn = f"{OUT}/{sym}.npz"
    if os.path.exists(fn): return c, -1
    parts = []
    with cf.ThreadPoolExecutor(6) as ex:
        for a in ex.map(lambda mo: get(sym, mo), months):
            if a is not None and len(a): parts.append(a)
    if not parts: return c, 0
    a = np.concatenate(parts); a = a[np.argsort(a[:, 0])]
    t = (a[:, 0] // 1000).astype(np.int64); k = np.concatenate([[True], np.diff(t) > 0]); a, t = a[k], t[k]
    np.savez(fn, t=t, o=a[:, 1].astype(np.float64), h=a[:, 2].astype(np.float64), l=a[:, 3].astype(np.float64), c=a[:, 4].astype(np.float64), qv=a[:, 5].astype(np.float32))
    return c, len(t)
for c in (sys.argv[1:] or COINS):
    print(coin(c), flush=True)
