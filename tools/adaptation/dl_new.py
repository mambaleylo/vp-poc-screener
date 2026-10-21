"""the extra coins for P/R: Binance USDT-M volume >= 150M $ in 2026-08 (more_coins.json) and 1h history from 2025-06 or
earlier (drops the TradFi perps and the very new coins) -> data/1h/<SYM>.csv + data/funding/<SYM>.csv, new_coins.txt"""
import re, io, os, json, zipfile, urllib.request, concurrent.futures as cf
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
new = [s for s, v in json.load(open("more_coins.json")) if v >= 150e6]
import time
def first(sym):
    for k in range(5):
        try:
            x = urllib.request.urlopen(f"{S3}?prefix=data/futures/um/monthly/klines/{sym}/1h/&delimiter=/", timeout=60).read().decode(); break
        except Exception:
            time.sleep(2 * (k + 1)); x = ""
    ms = sorted(re.findall(rf"{sym}-1h-(\d{{4}}-\d{{2}})\.zip<", x))
    return sym, (ms[0] if ms else None), ms
with cf.ThreadPoolExecutor(6) as ex:
    info = list(ex.map(first, new))
pick = [(s, f, ms) for s, f, ms in info if f and f <= "2025-06"]
print("volume >= 150M:", len(new), "with history from <= 2025-06:", len(pick), flush=True)
def get(url, cols, tries=3):
  for k in range(tries):
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        return [cols(l.split(",")) for l in z.read(z.namelist()[0]).decode().splitlines() if l[:1].isdigit()]
    except urllib.error.HTTPError:
        return []
    except Exception:
        time.sleep(2 * (k + 1))
  return []
def coin(x):
    sym, f, ms = x
    fn = f"data/1h/{sym}.csv"
    if not os.path.exists(fn):
        rows = []
        for mo in ms:
            rows += get(f"{S3}/data/futures/um/monthly/klines/{sym}/1h/{sym}-1h-{mo}.zip",
                        lambda p: (int(p[0]) // 1000, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[7])))
        rows.sort(); open(fn, "w").write("\n".join(",".join(map(str, r)) for r in rows))
    fd = f"data/funding/{sym}.csv"
    if not os.path.exists(fd):
        rows = []
        for mo in ms:
            rows += get(f"{S3}/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{mo}.zip", lambda p: (int(p[0]) // 1000, float(p[-1])))
        rows.sort(); open(fd, "w").write("\n".join(f"{t},{v}" for t, v in rows))
    return sym
with cf.ThreadPoolExecutor(8) as ex:
    done = list(ex.map(coin, pick))
open("new_coins.txt", "w").write("\n".join(done))
print("downloaded", len(done), done[:20], flush=True)
