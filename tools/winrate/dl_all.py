"""every Binance USDT-M perpetual's 1h candles (the S3 mirror of data.binance.vision, monthly files 2021-01 .. 2026-09) ->
data/1h/<SYM>.csv: t,o,h,l,c,quote volume (the research format); syms.json — every symbol with its months"""
import re, io, os, json, time, zipfile, urllib.request, concurrent.futures as cf
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
def ls(prefix):
    out, marker = [], ""
    while True:
        for k in range(5):
            try:
                x = urllib.request.urlopen(f"{S3}?prefix={prefix}&delimiter=/" + (f"&marker={marker}" if marker else ""), timeout=60).read().decode(); break
            except Exception:
                time.sleep(2 * (k + 1)); x = ""
        out += re.findall(r"<Prefix>([^<]+)</Prefix>", x)[1:] + re.findall(r"<Key>([^<]+)</Key>", x)
        m = re.search(r"<NextMarker>([^<]+)</NextMarker>", x)
        if "<IsTruncated>true</IsTruncated>" in x:
            marker = m.group(1) if m else (out[-1] if out else "")
        else:
            return out
syms = sorted({p.rstrip("/").split("/")[-1] for p in ls("data/futures/um/monthly/klines/")})
syms = [s for s in syms if s.endswith("USDT")]
print("symbols", len(syms), flush=True)
def months(sym):
    ks = ls(f"data/futures/um/monthly/klines/{sym}/1h/")
    return sym, sorted(m for m in re.findall(rf"{sym}-1h-(\d{{4}}-\d{{2}})\.zip$", "\n".join(ks), re.M) if "2021-01" <= m <= "2026-09")
with cf.ThreadPoolExecutor(16) as ex:
    info = dict(ex.map(months, syms))
json.dump(info, open("syms.json", "w"))
print("with months", sum(1 for v in info.values() if v), flush=True)
def get(url):
    for k in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            return [(int(p[0]) // 1000, p[1], p[2], p[3], p[4], p[7]) for p in (l.split(",") for l in z.read(z.namelist()[0]).decode().splitlines() if l[:1].isdigit())]
        except Exception:
            time.sleep(2 * (k + 1))
    return None
def one(sym):
    fn = f"data/1h/{sym}.csv"
    if os.path.exists(fn) or not info.get(sym):
        return sym, 0
    rows = []
    for m in info[sym]:
        r = get(f"{S3}/data/futures/um/monthly/klines/{sym}/1h/{sym}-1h-{m}.zip")
        if r: rows += r
    rows.sort(key=lambda x: x[0]); seen = set(); out = []
    for r in rows:
        if r[0] not in seen: seen.add(r[0]); out.append(r)
    with open(fn + ".tmp", "w") as f:
        f.write("\n".join(",".join(map(str, r)) for r in out))
    os.replace(fn + ".tmp", fn)
    return sym, len(out)
n = 0
with cf.ThreadPoolExecutor(16) as ex:
    for sym, k in ex.map(one, list(info)):
        n += 1
        if n % 50 == 0: print(n, "of", len(info), flush=True)
print("DONE", len(os.listdir("data/1h")), flush=True)
