import csv, math, numpy as np, calendar, time
def load(fn):
    out = []
    for r in csv.DictReader(open(fn)):
        p = r.get("PriceUSD") or r.get("ReferenceRateUSD")
        if p: out.append((calendar.timegm(time.strptime(r["time"], "%Y-%m-%d")), float(p)))
    return np.array(out)
B = load("dl/btc.csv"); E = load("dl/eth.csv")
def yr(t): return time.gmtime(t).tm_year
def stats(A, name):
    t, p = A[:, 0], A[:, 1]; lr = np.diff(np.log(p)); ty = np.array([yr(x) for x in t[1:]])
    print(f"== {name}: годовая волатильность (дневная, в год) и итог года")
    for Y in range(2014 if name == "BTC" else 2016, 2027):
        m = ty == Y
        if m.sum() < 60: continue
        py = p[1:][m]; p0 = p[:-1][m][0]
        # the average daily range proxy: mean |daily return|
        print(f"  {Y}: волатильность {lr[m].std() * math.sqrt(365) * 100:4.0f}%  средний дневной ход {np.abs(lr[m]).mean() * 100:.2f}%  итог года {(py[-1] / p0 - 1) * 100:+5.0f}%  дней {m.sum()}")
stats(B, "BTC"); stats(E, "ETH")
t, p = B[:, 0], B[:, 1]; lr = np.diff(np.log(p))
print("== BTC: 30-дневная волатильность по месяцам с 2025")
for Y, M in [(y, m) for y in (2025, 2026) for m in range(1, 13)]:
    a, b = calendar.timegm((Y, M, 1, 0, 0, 0)), calendar.timegm((Y + (M == 12), M % 12 + 1, 1, 0, 0, 0))
    m = (t[1:] >= a) & (t[1:] < b)
    if m.sum() > 10: print(f"  {Y}-{M:02d}: {lr[m].std() * math.sqrt(365) * 100:4.0f}%  цена на конец {p[1:][m][-1]:>8,.0f}")
# the cycles: peak -> bottom -> the next ATH, from the price
def at(d): return calendar.timegm(time.strptime(d, "%Y-%m-%d"))
for pk, nm in (("2013-11-30", "2013"), ("2017-12-17", "2017"), ("2021-11-10", "2021"), ("2025-10-06", "2025")):
    i0 = np.searchsorted(t, at(pk) - 20 * 86400); i1 = np.searchsorted(t, at(pk) + 20 * 86400)
    ip = i0 + int(np.argmax(p[i0:i1])); hi = p[ip]
    seg = slice(ip, min(len(p), ip + 600)); ib = ip + int(np.argmin(p[seg])); lo = p[ib]
    ath = np.flatnonzero((t > t[ib]) & (p > hi)); ia = ath[0] if len(ath) else None
    print(f"цикл {nm}: пик {time.strftime('%Y-%m-%d', time.gmtime(t[ip]))} ${hi:,.0f} -> дно {time.strftime('%Y-%m-%d', time.gmtime(t[ib]))} ${lo:,.0f} ({(lo / hi - 1) * 100:.0f}%, {int((t[ib] - t[ip]) // 86400)} дн.)"
          + (f" -> новый максимум {time.strftime('%Y-%m-%d', time.gmtime(t[ia]))} (через {int((t[ia] - t[ib]) // 86400)} дн. после дна)" if ia is not None else " -> (данные до мая 2026)"))
    # the volatility in the 12 months after the bottom vs the 12 months before it
    a = (t[1:] > t[ib]) & (t[1:] <= t[ib] + 365 * 86400); b = (t[1:] > t[ib] - 365 * 86400) & (t[1:] <= t[ib])
    print(f"     волатильность: год до дна {lr[b].std() * math.sqrt(365) * 100:.0f}%, год после дна {lr[a].std() * math.sqrt(365) * 100:.0f}%")
