"""more coins for P/R: every Binance USDT-M symbol (the S3 listing), its quote volume in 2026-08 (monthly 1d klines),
the ones not in the research's 127 ranked -> more_coins.json [(sym, usdt volume)]"""
import re, io, os, json, zipfile, urllib.request, concurrent.futures as cf
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
syms, marker = [], ""
while True:
    x = urllib.request.urlopen(f"{S3}?prefix=data/futures/um/monthly/klines/&delimiter=/&marker={marker}", timeout=60).read().decode()
    syms += re.findall(r"<Prefix>data/futures/um/monthly/klines/([A-Z0-9]+)/</Prefix>", x)
    m = re.search(r"<NextMarker>(.*?)</NextMarker>", x)
    if not m or "<IsTruncated>true" not in x: break
    marker = m.group(1)
syms = sorted({s for s in syms if s.endswith("USDT")})
have = {f[:-4] for f in os.listdir("data/1h")}
print("USDT symbols", len(syms), "have", len(have & set(syms)), flush=True)
def vol(sym):
    try:
        with urllib.request.urlopen(f"{S3}/data/futures/um/monthly/klines/{sym}/1d/{sym}-1d-2026-08.zip", timeout=60) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        rows = [l.split(",") for l in z.read(z.namelist()[0]).decode().splitlines() if l[:1].isdigit()]
        return sym, sum(float(x[7]) for x in rows)
    except Exception:
        return sym, 0.0
with cf.ThreadPoolExecutor(24) as ex:
    v = dict(ex.map(vol, syms))
rank = sorted(((s, x) for s, x in v.items() if x > 0), key=lambda t: -t[1])
old = [i for i, (s, _) in enumerate(rank) if s in have]
print("the 127 sit at ranks", min(old), "..", max(old), "of", len(rank))
new = [(s, round(x)) for s, x in rank if s not in have]
json.dump(new, open("more_coins.json", "w"))
print("new coins with volume", len(new)); print(new[:15]); print("100th:", new[99] if len(new) > 99 else None, " 200th:", new[199] if len(new) > 199 else None)
med_old = sorted(v[s] for s in have if s in v)[len(have) // 2]; print("median 2026-08 volume of the 127:", round(med_old))
