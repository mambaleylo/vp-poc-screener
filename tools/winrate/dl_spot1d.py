"""daily SPOT candles of the 127 research coins from Binance's archive (data.binance.vision) since 2017 — the long history
for the weekly studies (the futures start in 2019-2020): <OUT>/<SYM>.csv (t, o, h, l, c, quote volume); the spot name
(1000PEPE -> PEPE …); a month without its monthly archive by the days; a network error retried, a 404 = no file.
The timestamps: ms, from 2025 microseconds (both read). usage: dl_spot1d.py OUT [END=2026-10]"""
import os, sys, io, time, zipfile, calendar, urllib.request, urllib.error, concurrent.futures as cf
B = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/spot"
OUT = sys.argv[1]; END = sys.argv[2] if len(sys.argv) > 2 else "2026-10"; os.makedirs(OUT, exist_ok=True)
COINS = [l.strip()[:-4] for l in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "coins127.txt")) if l.strip()]
months = [f"{y}-{m:02d}" for y in range(2017, 2027) for m in range(1, 13) if "2017-07" <= f"{y}-{m:02d}" <= END]
def get1(url):
    for k in range(6):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read())); rows = []
                for line in z.read(z.namelist()[0]).decode().splitlines():
                    p = line.split(",")
                    if not p[0].isdigit(): continue
                    t = int(p[0]); t = t // 1000000 if t > 10 ** 14 else t // 1000
                    rows.append((t, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[7])))
                return rows
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
        except Exception:
            pass
        time.sleep(2 ** k)
    raise RuntimeError(f"не скачалось: {url}")
def get(sym, mo):
    r = get1(f"{B}/monthly/klines/{sym}/1d/{sym}-1d-{mo}.zip")
    if r is None and mo >= "2026-01":
        y, m = map(int, mo.split("-"))
        ds = [get1(f"{B}/daily/klines/{sym}/1d/{sym}-1d-{mo}-{d:02d}.zip") for d in range(1, calendar.monthrange(y, m)[1] + 1)]
        r = [x for d in ds if d for x in d] or None
    return r
def coin(c):
    sym = (c[4:] if c.startswith("1000") else c) + "USDT"
    fn = f"{OUT}/{sym}.csv"
    if os.path.exists(fn): return sym, -1
    rows = []
    with cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(lambda mo: get(sym, mo), months):
            if r: rows += r
    rows = sorted(set(rows))
    if rows:
        with open(fn + ".tmp", "w") as f: f.write("\n".join(",".join(map(str, r)) for r in rows))
        os.replace(fn + ".tmp", fn)
    return sym, len(rows)
with cf.ThreadPoolExecutor(4) as ex:
    for s, n in ex.map(coin, COINS): print(s, n, flush=True)
print("spot dl done", flush=True)
