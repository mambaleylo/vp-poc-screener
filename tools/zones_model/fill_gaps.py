"""Binance's monthly kline archives are sometimes cut short (2022-02 and 2022-03 lack their last 2-3 days on ~30 coins,
ICPUSDT 2022-09 has only its last 4 days) while the daily archives of those days exist. This fills every missing day inside a
coin's history (between its first and its last bar) from the daily archive; a day absent there too stays missing (printed).
fill(rows, sym, tf) -> rows (used by dl.py after the monthly files); as a script it fixes the files already downloaded:
usage: python3 fill_gaps.py DIR [tf]   (DIR of SYM.csv or SYM.csv.gz rows "t,o,h,l,c,v"; t in seconds)"""
import os, sys, io, gzip, time, zipfile, urllib.request, urllib.error, concurrent.futures as cf
BD = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/daily/klines"
STEP = {"1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400}
def get1(url):
    for k in range(6):   # a network error -> retried; 404 = no such file
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                raw = r.read()
            z = zipfile.ZipFile(io.BytesIO(raw)); out = []
            for line in z.read(z.namelist()[0]).decode().splitlines():
                p = line.split(",")
                if p[0].isdigit():
                    out.append((int(p[0]) // 1000, float(p[1]), float(p[2]), float(p[3]), float(p[4]), float(p[7])))
            return out
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
        except Exception:
            pass
        time.sleep(2 ** k)
    raise RuntimeError(f"не скачалось: {url}")
def missing_days(ts, tf="1h"):
    """the UTC days strictly inside the history with fewer bars than a full day"""
    if not ts: return []
    per = 86400 // STEP[tf]; cnt = {}
    for t in ts: cnt[t // 86400] = cnt.get(t // 86400, 0) + 1
    a, b = min(cnt), max(cnt)
    return [d for d in range(a + 1, b) if cnt.get(d, 0) < per]
def fill(rows, sym, tf="1h"):
    """rows: (t, o, h, l, c, v) sorted or not -> sorted rows with the missing days added from the daily archive"""
    import datetime as dt
    days = missing_days([r[0] for r in rows], tf)
    if not days: return sorted(rows), 0, []
    have = {r[0] for r in rows}; add = []; absent = []
    def one(d):
        ds = dt.datetime.fromtimestamp(d * 86400, dt.timezone.utc).strftime("%Y-%m-%d")
        return ds, get1(f"{BD}/{sym}/{tf}/{sym}-{tf}-{ds}.zip")
    with cf.ThreadPoolExecutor(8) as ex:
        for ds, got in ex.map(one, days):
            if got is None: absent.append(ds); continue
            add += [r for r in got if r[0] not in have]
    return sorted(list(rows) + add), len(add), absent
def _read(fn):
    op = gzip.open if fn.endswith(".gz") else open
    with op(fn, "rt") as f:
        return [tuple([int(p[0])] + [float(x) for x in p[1:6]]) for p in (l.strip().split(",") for l in f) if p[0].isdigit()]
def _write(fn, rows):
    op = gzip.open if fn.endswith(".gz") else open
    with op(fn + ".tmp", "wt") as f:   # whole or nothing
        f.write("\n".join(",".join(map(str, r)) for r in rows))
    os.replace(fn + ".tmp", fn)
if __name__ == "__main__":
    D = sys.argv[1]; TF = sys.argv[2] if len(sys.argv) > 2 else "1h"
    fns = sorted(f for f in os.listdir(D) if f.endswith(".csv") or f.endswith(".csv.gz"))
    tot = nf = 0
    for f in fns:
        fn = f"{D}/{f}"; sym = f.split(".")[0]; rows = _read(fn)
        if not missing_days([r[0] for r in rows], TF): continue
        new, n, absent = fill(rows, sym, TF)
        if n:
            _write(fn, new); tot += n; nf += 1
        print(f"{sym}: +{n} баров" + (f", нет и в дневных: {', '.join(absent[:6])}{' …' if len(absent) > 6 else ''} ({len(absent)} дн)" if absent else ""), flush=True)
    print(f"fill done: {nf} монет, +{tot} баров", flush=True)
