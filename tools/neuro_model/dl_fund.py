import os, io, zipfile, urllib.request, concurrent.futures as cf
B = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/monthly/fundingRate"
OUT = "data/funding"
os.makedirs(OUT, exist_ok=True)
months = [f"{y}-{m:02d}" for y in range(2020, 2027) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-09"]
def get(sym, mo):
    try:
        with urllib.request.urlopen(f"{B}/{sym}/{sym}-fundingRate-{mo}.zip", timeout=60) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        out = []
        for line in z.read(z.namelist()[0]).decode().splitlines():
            p = line.split(",")
            if p[0].isdigit():
                out.append((int(p[0]) // 1000, float(p[-1])))
        return out
    except Exception:
        return []
def coin(sym):
    fn = f"{OUT}/{sym}.csv"
    if os.path.exists(fn):
        return sym, -1
    rows = []
    with cf.ThreadPoolExecutor(8) as ex:
        for r in ex.map(lambda mo: get(sym, mo), months):
            rows += r
    rows.sort()
    open(fn, "w").write("\n".join(f"{t},{v}" for t, v in rows))
    return sym, len(rows)
syms = sorted(f[:-4] for f in os.listdir("data/1h"))
with cf.ThreadPoolExecutor(4) as ex:
    for s, n in ex.map(coin, syms):
        pass
print("done", len(os.listdir(OUT)))
