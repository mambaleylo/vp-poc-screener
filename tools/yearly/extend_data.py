"""The yearly fallback's data (GitHub Actions: the lab-store branch ends at its last upload): the months after it up to END appended
from data.binance.vision — the 1h candles (monthly klines -> <LABSTORE>/data/1h/<SYM>.csv.gz: t, o, h, l, c, quote volume), the
hourly metrics (daily files -> data/metrics/<SYM>.csv, dl_metrics.py's hour rows), the funding (tools/prv_audit/dl_fund2.py,
FUND_END). The coins: the lab's 210 (lv/split.json bot + chk) + BTC, ETH. A coin's month not on the archive (not listed then /
delisted) is skipped. usage: END=2026-12 python3 extend_data.py [coins…]"""
import os, sys, io, gzip, json, time, zipfile, calendar, subprocess, datetime as dt, urllib.request, urllib.error, concurrent.futures as cf
HERE = os.path.dirname(os.path.abspath(__file__)); WR = os.path.join(HERE, "..", "winrate")
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); END = os.environ["END"]
B = "https://data.binance.vision/data/futures/um"
ey, em = map(int, END.split("-")); END_T = calendar.timegm((ey + (em == 12), em % 12 + 1, 1, 0, 0, 0))   # the first second after END


def fetch(url):
    for k in range(4):
        try:
            with urllib.request.urlopen(url, timeout=90) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            return z.read(z.namelist()[0]).decode().splitlines()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
        except Exception:
            time.sleep(2 * (k + 1))
    return None


def months_after(t):
    g = time.gmtime(t); y, m = g.tm_year, g.tm_mon; out = []
    while True:
        y, m = (y, m + 1) if m < 12 else (y + 1, 1)
        if (y, m) > (ey, em):
            return out
        out.append(f"{y}-{m:02d}")


def candles(sym):
    fn = f"{ST}/data/1h/{sym}.csv.gz"
    if not os.path.exists(fn):
        return sym, "нет файла"
    with gzip.open(fn, "rt") as f:
        old = f.read().splitlines()
    last = int(old[-1].split(",")[0]) if old else 0
    add, miss = [], 0
    for mo in months_after(last):
        rows = fetch(f"{B}/monthly/klines/{sym}/1h/{sym}-1h-{mo}.zip")
        if rows is None:
            miss += 1; continue
        for ln in rows:
            p = ln.split(",")
            if not p[0].isdigit():
                continue
            t = int(p[0]) // 1000
            if last < t < END_T:
                add.append(f"{t},{p[1]},{p[2]},{p[3]},{p[4]},{p[7]}")
    # a day missing in a monthly file (the archive has such: 28.10.2026 in BTCUSDT's) -> that day's daily file
    have = {int(x.split(",", 1)[0]) for x in add}
    if have:
        lo, hi = max(last + 3600, min(have) - min(have) % 86400), max(have)
        gap_days = sorted({t // 86400 for t in range(lo, hi, 3600) if t not in have})
        for dd in gap_days:
            day = time.strftime("%Y-%m-%d", time.gmtime(dd * 86400))
            rows = fetch(f"{B}/daily/klines/{sym}/1h/{sym}-1h-{day}.zip") or []
            for ln in rows:
                p = ln.split(",")
                if p[0].isdigit():
                    t = int(p[0]) // 1000
                    if last < t < END_T and t not in have:
                        add.append(f"{t},{p[1]},{p[2]},{p[3]},{p[4]},{p[7]}"); have.add(t)
    if add:
        add.sort(key=lambda s: int(s.split(",", 1)[0]))
        with gzip.open(fn + ".tmp", "wt") as f:
            f.write("\n".join(old + add) + "\n")
        os.replace(fn + ".tmp", fn)
    holes = 0
    if add:
        tt = sorted(int(x.split(",", 1)[0]) for x in add); holes = sum(1 for a_, b_ in zip(tt, tt[1:]) if b_ - a_ != 3600)
    return sym, (len(add), miss, holes)


def metrics(sym):
    fn = f"{ST}/data/metrics/{sym}.csv"
    if not os.path.exists(fn):
        return sym, "нет файла"
    old = open(fn).read().splitlines()
    last = int(old[-1].split(",")[0]) if len(old) > 1 else 0
    d0 = dt.date.fromtimestamp(last + 86400 - (last % 86400)) if last else dt.date(2020, 9, 1)
    d1 = dt.date.fromtimestamp(END_T - 1)
    days = [(d0 + dt.timedelta(k)).isoformat() for k in range((d1 - d0).days + 1)]
    hrs, fails = {}, 0
    f_ = lambda x: (float(x) if x not in ("", "nan") else float("nan")) if True else 0
    with cf.ThreadPoolExecutor(8) as ex:
        for lines in ex.map(lambda d: fetch(f"{B}/daily/metrics/{sym}/{sym}-metrics-{d}.zip"), days):
            if lines is None:
                fails += 1; continue
            for ln in lines:
                p = ln.split(",")
                if len(p) < 8 or not p[0][:1].isdigit():
                    continue
                t = int(dt.datetime.strptime(p[0][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp())
                if t <= last or t >= END_T:
                    continue
                try:
                    v = [float(x) for x in p[2:7]]; tk = float(p[7])
                except ValueError:
                    continue
                h = hrs.setdefault(t // 3600 * 3600, {"tk": []}); h["last"] = (t, v); h["tk"].append(tk)
    rows = []
    for t in sorted(hrs):
        if t <= last:
            continue
        h = hrs[t]; tk = [v for v in h["tk"] if v == v]
        rows.append(f"{t}," + ",".join(f"{v:.8g}" for v in h["last"][1]) + f",{(sum(tk) / len(tk)) if tk else float('nan'):.6g}")
    if rows:
        open(fn + ".tmp", "w").write("\n".join(old + rows) + "\n"); os.replace(fn + ".tmp", fn)
    return sym, (len(rows), fails)


if __name__ == "__main__":
    sp = json.load(open(os.path.join(WR, "lv", "split.json")))
    syms = sys.argv[1:] or sorted(set(sp["bot"]) | set(sp["chk"]) | {"BTCUSDT", "ETHUSDT"})
    t0 = time.time()
    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(candles, syms))
    print("свечи 1ч:", sum(r[1][0] for r in res if isinstance(r[1], tuple)), "строк;", [r for r in res if not isinstance(r[1], tuple) or r[1][1]][:10],
          "| пропуски архива (нет ни месячного, ни дневного файла):", sum(1 for r in res if isinstance(r[1], tuple) and r[1][2]), "монет", f"{time.time() - t0:.0f}s", flush=True)
    with cf.ThreadPoolExecutor(4) as ex:
        res = list(ex.map(metrics, syms))
    print("метрики:", sum(r[1][0] for r in res if isinstance(r[1], tuple)), "строк;", [r for r in res if not isinstance(r[1], tuple) or r[1][1]][:10], f"{time.time() - t0:.0f}s", flush=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "..", "prv_audit", "dl_fund2.py")] + syms, env=dict(os.environ, FUND_END=END, LABSTORE=ST),
                       capture_output=True, text=True)
    print("фандинг:", (r.stdout.strip().splitlines() or ["?"])[-1], f"{time.time() - t0:.0f}s", flush=True)
    print("extend done", flush=True)
