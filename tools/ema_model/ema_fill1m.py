"""📐 the check the ⚡ limits taught ("касание = исполнение"): the lab fills an EMA trade AT its limit (the touch hour went 0.1%
past it), but the bot's real EMA trade is a MARKET order sent when it sees the touch (Gate's last price or Binance's 1-min
wick, polled every 10 s). On Binance's 1-min candles of each trade's touch hour: the first minute that reached the limit, the
price at that minute's close (the market entry ~seconds..a minute late) and at the next minute's open; the cost in R of
the planned risk (+ = worse than the limit); how many would be skipped (the bot's guard: > 1R worse -> no real trade).
usage: python3 ema_fill1m.py LIST.json   (the money format of ema_var.py; the 1m days cached in /home/user/ema1m)"""
import os, sys, io, json, time, zipfile, datetime as dt, urllib.request, urllib.error, numpy as np, concurrent.futures as cf
BD = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision/data/futures/um/daily/klines"
CACHE = "/home/user/ema1m"; os.makedirs(CACHE, exist_ok=True)
def day1m(sym, ds):
    fn = f"{CACHE}/{sym}-{ds}.npy"
    if os.path.exists(fn): return np.load(fn)
    url = f"{BD}/{sym}/1m/{sym}-1m-{ds}.zip"
    for k in range(6):
        try:
            with urllib.request.urlopen(url, timeout=60) as r: raw = r.read()
            z = zipfile.ZipFile(io.BytesIO(raw)); rows = []
            for line in z.read(z.namelist()[0]).decode().splitlines():
                p = line.split(",")
                if p[0].isdigit(): rows.append((int(p[0]) // 1000, float(p[1]), float(p[2]), float(p[3]), float(p[4])))
            a = np.array(rows); np.save(fn, a); return a
        except urllib.error.HTTPError as e:
            if e.code == 404: a = np.zeros((0, 5)); np.save(fn, a); return a
        except Exception:
            pass
        time.sleep(2 ** k)
    raise RuntimeError(url)
def one(x):
    t0 = int(x["t0"]); ds = dt.datetime.fromtimestamp(t0, dt.timezone.utc).strftime("%Y-%m-%d"); a = day1m(x["sym"], ds)
    if not len(a): return None
    s, e, risk = x["side"], x["e"], x["e"] * x["st"]
    w = np.flatnonzero((a[:, 0] >= t0) & (a[:, 0] < t0 + 3600))
    hit = [i for i in w if (a[i, 3] <= e if s > 0 else a[i, 2] >= e)]
    if not hit: return ("miss", x)
    i = hit[0]; cl = a[i, 4]; nx = a[i + 1, 1] if i + 1 < len(a) else cl
    return ("ok", s * (cl - e) / risk, s * (nx - e) / risk, x["r"])
if __name__ == "__main__":
    L = json.load(open(sys.argv[1])); L = [x for x in L if x["t0"] >= 1640995200]
    with cf.ThreadPoolExecutor(8) as ex: res = list(ex.map(one, L))
    ok = [r for r in res if r and r[0] == "ok"]; miss = sum(1 for r in res if r and r[0] == "miss"); none = sum(1 for r in res if r is None)
    c = np.array([r[1] for r in ok]); n_ = np.array([r[2] for r in ok]); R = np.array([r[3] for r in ok])
    print(f"сделок {len(L)}: минутки найдены {len(ok)}, касания в минутках нет {miss}, нет файла {none}")
    for nm, v in (("закрытие минуты касания", c), ("открытие следующей минуты", n_)):
        late = v > 1.0
        print(f"{nm}: в среднем {v.mean():+.3f}R (медиана {np.median(v):+.3f}), хуже лимитки у {(v > 0).mean() * 100:.0f}%, "
              f"> 1R хуже (бот пропустит) {late.sum()}; R бэктеста {R.mean():+.3f} -> с рыночным входом ≈ {np.where(late, 0, R - v).mean():+.3f}"
              f" (пропущенные = 0)")
    print("fill1m done")
