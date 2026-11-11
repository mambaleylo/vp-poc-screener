"""Funding arbitrage Gate <-> Binance, a first look (the user: "для нас есть смысл бот арбитражные сделать? Например для gate-binance"):
the same perpetual on both exchanges, long where the funding is lower, short where it is higher — the price cancels out, the funding
difference is the income. Data: Binance's settled funding (lab-store data/funding, data.binance.vision) and Gate's API (its last
180 days); per coin and UTC day each exchange's funding summed (their intervals differ: 8h / 4h / 1h). The rule decides on the day
before (no look-ahead): yesterday's |difference| above ENTER -> the position today on yesterday's side, kept while the side holds
and the difference stays above EXIT; 4 taker fills on entry + exit (2 legs x 2) at FEE each. -> per coin: days held, the income %
of the notional after fees; the best coins; the whole basket. usage: python3 fund_diff.py"""
import os, sys, json, time, urllib.request, concurrent.futures as cf, collections
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ST, "gate_funding"); os.makedirs(CACHE, exist_ok=True)
FEE = float(os.environ.get("FEE", "0.0005"))   # taker 0.05% a fill (Binance USDⓈ-M 0.05%, Gate perps ~0.05%)
NOW = int(time.time()); T0 = NOW - 179 * 86400


def gate(contract):
    fn = os.path.join(CACHE, contract + ".json")
    if os.path.exists(fn) and time.time() - os.path.getmtime(fn) < 86400:
        return json.load(open(fn))
    out, a = [], T0
    while a < NOW:
        b = min(NOW, a + 30 * 86400)
        url = f"https://api.gateio.ws/api/v4/futures/usdt/funding_rate?contract={contract}&from={a}&to={b}&limit=1000"
        for k in range(4):
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    rows = json.loads(r.read()); break
            except urllib.error.HTTPError as e:
                if e.code in (400, 404):
                    rows = None; break
                time.sleep(2 * (k + 1))
            except Exception:
                time.sleep(2 * (k + 1))
        else:
            rows = None
        if rows is None:
            return None
        out += [(int(x["t"]), float(x["r"])) for x in rows]
        a = b
    out = sorted(set(out)); json.dump(out, open(fn, "w")); return out


def binance(sym):
    fn = os.path.join(ST, "data", "funding", sym + ".csv")
    if not os.path.exists(fn):
        return None
    return [(int(a), float(b)) for a, b in (l.split(",")[:2] for l in open(fn).read().split())]


def daily(rows):
    d = collections.defaultdict(float)
    for t, r in rows:
        d[t // 86400] += r
    return d


def one(sym):
    bn = binance(sym)
    if not bn:
        return sym, None
    base = sym[:-4]
    g = None
    for c in (base + "_USDT", base.replace("1000", "", 1) + "_USDT" if base.startswith("1000") else None):
        if c and (g := gate(c)):
            break
    if not g:
        return sym, None
    db, dg = daily(bn), daily(g)
    days = sorted(set(db) & set(dg)); days = [d for d in days if d >= T0 // 86400]
    return sym, [(d, dg[d] - db[d]) for d in days]   # > 0: Gate's longs pay more -> short Gate, long Binance


def run(series, enter, exit_):
    inc, fees, held, trades = 0.0, 0.0, 0, 0
    side = 0
    for (d0, x0), (d1, x1) in zip(series, series[1:]):
        if d1 != d0 + 1:
            side = 0; continue
        want = (1 if x0 > 0 else -1) if abs(x0) >= enter else 0
        if side and (want != side and abs(x0) < exit_ or (x0 > 0) != (side > 0)):
            side = 0; fees += 2 * FEE   # out: 2 fills
        if not side and want:
            side = want; fees += 2 * FEE; trades += 1   # in: 2 fills
        if side:
            inc += side * x1; held += 1
    if side:
        fees += 2 * FEE
    return inc, fees, held, trades


if __name__ == "__main__":
    sp = json.load(open(os.path.join(HERE, "..", "winrate", "lv", "split.json")))
    syms = sorted(set(sp["bot"]) | set(sp["chk"]))
    with cf.ThreadPoolExecutor(8) as ex:
        S = {s: v for s, v in ex.map(one, syms) if v and len(v) > 60}
    last = max(d for v in S.values() for d, _ in v)
    print(f"монет с данными на обеих биржах: {len(S)} из {len(syms)}; дни {time.strftime('%Y-%m-%d', time.gmtime(T0))} .. {time.strftime('%Y-%m-%d', time.gmtime(last * 86400))}")
    allx = [abs(x) for v in S.values() for _, x in v]
    allx.sort(); q = lambda p: allx[int(p * (len(allx) - 1))] * 100
    print(f"разница фандинга за сутки, % от позиции: медиана {q(.5):.4f} · 90% {q(.9):.4f} · 99% {q(.99):.4f} · макс {allx[-1] * 100:.3f}")
    print(f"\nкомиссия {FEE * 100:.3f}% за исполнение, вход + выход = 4 исполнения = {4 * FEE * 100:.2f}% позиции")
    for enter, exit_ in ((0.0005, 0.0002), (0.001, 0.0003), (0.002, 0.0005), (0.004, 0.001)):
        res = {s: run(v, enter, exit_) for s, v in S.items()}
        tot = [(s, i - f, h, t) for s, (i, f, h, t) in res.items() if t]
        n_days = (last - T0 // 86400)
        gain = sorted(tot, key=lambda x: -x[1])
        pos = sum(1 for x in tot if x[1] > 0)
        print(f"\nвход при разнице ≥{enter * 100:.2f}%/сут, выход <{exit_ * 100:.2f}%: монет с позициями {len(tot)}, в плюсе {pos}; "
              f"сумма по всем {sum(x[1] for x in tot) * 100:+.1f}% позиции за {n_days} дн")
        for s, net, h, t in gain[:6]:
            print(f"   {s:14s} {net * 100:+6.1f}% за {h:3d} дн в позиции ({t} входов) → {net / max(1, h) * 365 * 100:+.0f}% годовых на время в позиции")
        print("   худшие:", ", ".join(f"{s} {net * 100:+.1f}%" for s, net, h, t in gain[-3:]))
    print("fund diff done")
