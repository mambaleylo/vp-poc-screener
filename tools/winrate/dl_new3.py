"""⚡ on more coins: Binance USDT-M with volume >= 50M $ in 2026-08 (more_coins.json), not in data/1h, 1h history from
<= 2025-09 -> data/1h/<SYM>.csv (2025-04 .. 2026-09 only), new_coins3.txt"""
import re, io, os, json, time, zipfile, urllib.request, concurrent.futures as cf
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
have = {f[:-4] for f in os.listdir("data/1h")}
new = [s for s, v in json.load(open("more_coins.json")) if v >= 50e6 and s not in have]
def first(sym):
    for k in range(5):
        try:
            x = urllib.request.urlopen(f"{S3}?prefix=data/futures/um/monthly/klines/{sym}/1h/&delimiter=/", timeout=60).read().decode(); break
        except Exception:
            time.sleep(2 * (k + 1)); x = ""
    ms = sorted(re.findall(rf"{sym}-1h-(\d{{4}}-\d{{2}})\.zip<", x))
    return sym, ms
with cf.ThreadPoolExecutor(8) as ex:
    info = list(ex.map(first, new))
pick = [(s, [m for m in ms if "2025-04" <= m <= "2026-09"]) for s, ms in info if ms and ms[0] <= "2025-09" and ms[-1] >= "2026-09"]
print("candidates", len(new), "with history 2025-09 .. 2026-09:", len(pick), flush=True)
def get(url, tries=4):
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            return [(int(p[0]) // 1000, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[7]))
                    for p in (l.split(",") for l in z.read(z.namelist()[0]).decode().splitlines() if l[:1].isdigit())]
        except urllib.error.HTTPError:
            return []
        except Exception:
            time.sleep(2 * (k + 1))
    return []
def coin(x):
    sym, ms = x; fn = f"data/1h/{sym}.csv"
    rows = []
    for mo in ms: rows += get(f"{S3}/data/futures/um/monthly/klines/{sym}/1h/{sym}-1h-{mo}.zip")
    rows.sort(); open(fn, "w").write("\n".join(",".join(map(str, r)) for r in rows))
    return sym
with cf.ThreadPoolExecutor(8) as ex:
    done = list(ex.map(coin, pick))
open("new_coins3.txt", "w").write("\n".join(done))
print("downloaded", len(done), done[:30], flush=True)
