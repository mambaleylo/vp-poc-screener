"""Binance USDT-M daily metrics (5 min: open interest, its value, top traders' long/short by accounts and by position,
all accounts' long/short, taker buy/sell volume ratio) from the data.binance.vision S3 mirror, 2020-09 .. 2026-09,
reduced to 1h rows: the last OI / ratios of the hour and the mean taker ratio -> data/metrics/<SYM>.csv
(t = the hour's open, unix s; oi, oiv, top_acc, top_pos, ls_acc, taker)"""
import os, io, zipfile, urllib.request, datetime as dt, concurrent.futures as cf
B = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/daily/metrics"
OUT = "data/metrics"
os.makedirs(OUT, exist_ok=True)
d0, d1 = dt.date(2020, 9, 1), dt.date(2026, 9, 30)
days = [(d0 + dt.timedelta(k)).isoformat() for k in range((d1 - d0).days + 1)]
def get(sym, day):
    for _ in range(3):
        try:
            with urllib.request.urlopen(f"{B}/{sym}/{sym}-metrics-{day}.zip", timeout=60) as r:
                z = zipfile.ZipFile(io.BytesIO(r.read()))
            return z.read(z.namelist()[0]).decode().splitlines()
        except urllib.error.HTTPError as e:
            if e.code == 404: return []
        except Exception:
            pass
    return None
def f(x):
    try: return float(x)
    except ValueError: return float("nan")
def coin(sym):
    fn = f"{OUT}/{sym}.csv"
    if os.path.exists(fn): return sym, -1
    hrs, fails = {}, 0
    with cf.ThreadPoolExecutor(16) as ex:
        for lines in ex.map(lambda d: get(sym, d), days):
            if lines is None: fails += 1; continue
            for ln in lines:
                p = ln.split(",")
                if len(p) < 8 or not p[0][:1].isdigit(): continue
                t = int(dt.datetime.strptime(p[0][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp())
                h = hrs.setdefault(t // 3600 * 3600, {"tk": []})
                h["last"] = (t, [f(v) for v in p[2:7]]); h["tk"].append(f(p[7]))
    rows = []
    for t in sorted(hrs):
        h = hrs[t]; tk = [v for v in h["tk"] if v == v]
        rows.append(f"{t}," + ",".join(f"{v:.8g}" for v in h["last"][1]) + f",{(sum(tk) / len(tk)) if tk else float('nan'):.6g}")
    open(fn + ".tmp", "w").write("t,oi,oiv,top_acc,top_pos,ls_acc,taker\n" + "\n".join(rows)); os.replace(fn + ".tmp", fn)
    return sym, (len(rows), fails)
syms = sorted(f[:-4] for f in os.listdir("data/1h"))
if __name__ == "__main__":
    import multiprocessing as mp
    with mp.Pool(8) as p:
        for s, n in p.imap_unordered(coin, syms):
            print(s, n, flush=True)
print("done", len(os.listdir(OUT)), flush=True)
