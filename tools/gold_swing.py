#!/usr/bin/env python3
"""Золото: схемы с сигналами раз в 1–3 дня — на 6 годах часовых свечей PAXG/USDT (Binance).

Запуск (в Termux):
    python gold_swing.py

Ничего не торгует, ключи не нужны. Схемы заданы заранее, параметры не подбираются:
 A. ОТКАТ ПО ТРЕНДУ (RSI-2, Коннорс), 4ч: цена выше EMA200 и RSI(2) < 10 — лонг;
    ниже EMA200 и RSI(2) > 90 — шорт. Выход: закрытие по другую сторону EMA5,
    максимум 12 свечей (2 дня), стоп 2 ATR(14).
 B. ПРОБОЙ КАНАЛА 20/10, 4ч: закрытие выше максимума 20 свечей — лонг (ниже
    минимума — шорт), выход по каналу 10 свечей в обратную сторону, стоп 2 ATR.
 C. ПРОБОЙ АЗИАТСКОГО ДИАПАЗОНА, 1ч: диапазон 00–06 UTC, с 07 до 15 UTC первое
    закрытие за ним — вход, стоп на другой стороне диапазона, выход в 20:00 UTC.

Главная проверка — против входов НАУГАД: для каждой сделки 20 раз берётся
случайная свеча, та же сторона, тот же стоп в ATR и то же время в сделке.
Так из результата убирается то, что золото просто росло. Схема проходит, если
превышение над случайными t >= 2.5 и есть в обеих половинах периода, а сама
схема в плюсе. Комиссия 0.1% за круг учтена.
"""
import math
import os
import random
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("нужен requests: pip install requests")

URL = "https://data-api.binance.vision/api/v3/klines"
FEE = 0.001
PASS_T = 2.5
RANDOM_DRAWS = 20
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def fetch_1h():
    out, start = [], 0
    while True:
        for attempt in range(4):
            try:
                ks = requests.get(URL, timeout=30, params={"symbol": "PAXGUSDT", "interval": "1h",
                                                           "startTime": start, "limit": 1000}).json()
                break
            except Exception as e:
                if attempt == 3:
                    sys.exit(f"Binance недоступен: {e}")
                time.sleep(2 ** attempt)
        if not isinstance(ks, list) or not ks:
            break
        out += [{"time": k[0] // 1000, "open": float(k[1]), "high": float(k[2]), "low": float(k[3]),
                 "close": float(k[4])} for k in ks]
        if len(out) % 10000 < 1000:
            print(f"  ...{len(out)} часовых свечей")
        if len(ks) < 1000:
            break
        start = ks[-1][0] + 1
    now = time.time()
    return [c for c in out if c["time"] + 3600 <= now]


def to_4h(h):
    out = {}
    for c in h:
        k = c["time"] // 14400 * 14400
        b = out.get(k)
        if b is None:
            out[k] = dict(c, time=k, n=1)
        else:
            b["high"] = max(b["high"], c["high"])
            b["low"] = min(b["low"], c["low"])
            b["close"] = c["close"]
            b["n"] += 1
    return [b for _, b in sorted(out.items()) if b["n"] == 4]


def atr(c, n):
    out, prev = [None] * len(c), None
    for i in range(1, len(c)):
        tr = max(c[i]["high"] - c[i]["low"], abs(c[i]["high"] - c[i - 1]["close"]), abs(c[i]["low"] - c[i - 1]["close"]))
        prev = tr if prev is None else (prev * (n - 1) + tr) / n
        out[i] = prev if i >= n else None
    return out


def ema(xs, n):
    out, k, v = [], 2 / (n + 1), None
    for x in xs:
        v = x if v is None else v + k * (x - v)
        out.append(v)
    return out


def rsi(xs, n):
    out, up, dn = [None] * len(xs), None, None
    for i in range(1, len(xs)):
        g, l_ = max(xs[i] - xs[i - 1], 0), max(xs[i - 1] - xs[i], 0)
        up = g if up is None else (up * (n - 1) + g) / n
        dn = l_ if dn is None else (dn * (n - 1) + l_) / n
        if i >= n:
            out[i] = 100.0 if dn == 0 else 100 - 100 / (1 + up / dn)
    return out


def tstat(xs):
    n = len(xs)
    if n < 3:
        return None
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
    return mu / (sd / math.sqrt(n)) if sd > 0 else None


def trade_r(c, i, side, stop_d, bars):
    """enter at open of bar i, stop stop_d away, exit at close of bar i+bars-1 (stop first)"""
    e = c[i]["open"]
    px = c[min(i + bars - 1, len(c) - 1)]["close"]
    for j in range(i, min(i + bars, len(c))):
        if (side > 0 and c[j]["low"] <= e - stop_d) or (side < 0 and c[j]["high"] >= e + stop_d):
            px = e - side * stop_d
            break
    return side * (px - e) / stop_d - FEE * e / stop_d


# every trade: (entry time, R, side, entry index, stop in ATR, bars held)

def rsi2_pullback(c):
    cl = [x["close"] for x in c]
    e200, e5, r2, a = ema(cl, 200), ema(cl, 5), rsi(cl, 2), atr(c, 14)
    out, i = [], 200
    while i < len(c) - 13:
        side = 1 if cl[i] > e200[i] and r2[i] is not None and r2[i] < 10 else \
            (-1 if cl[i] < e200[i] and r2[i] is not None and r2[i] > 90 else 0)
        if not side or not a[i]:
            i += 1
            continue
        k, e, sd = i + 1, c[i + 1]["open"], 2 * a[i]
        px, end = None, None
        for j in range(k, min(k + 12, len(c))):
            b = c[j]
            if (side > 0 and b["low"] <= e - sd) or (side < 0 and b["high"] >= e + sd):
                px, end = e - side * sd, j
                break
            if (side > 0 and b["close"] > e5[j]) or (side < 0 and b["close"] < e5[j]) or j == k + 11:
                px, end = b["close"], j
                break
        out.append((c[k]["time"], side * (px - e) / sd - FEE * e / sd, side, k, 2.0, end - k + 1))
        i = end + 1
    return out


def channel_breakout(c):
    a = atr(c, 14)
    out, i = [], 21
    while i < len(c) - 2:
        hi = max(x["high"] for x in c[i - 20:i])
        lo = min(x["low"] for x in c[i - 20:i])
        side = 1 if c[i]["close"] > hi else (-1 if c[i]["close"] < lo else 0)
        if not side or not a[i]:
            i += 1
            continue
        k, e, sd = i + 1, c[i + 1]["open"], 2 * a[i]
        px, end = c[-1]["close"], len(c) - 1
        for j in range(k, len(c)):
            b = c[j]
            if (side > 0 and b["low"] <= e - sd) or (side < 0 and b["high"] >= e + sd):
                px, end = e - side * sd, j
                break
            lo10 = min(x["low"] for x in c[j - 10:j])
            hi10 = max(x["high"] for x in c[j - 10:j])
            if (side > 0 and b["close"] < lo10) or (side < 0 and b["close"] > hi10):
                px, end = b["close"], j
                break
        out.append((c[k]["time"], side * (px - e) / sd - FEE * e / sd, side, k, 2.0, end - k + 1))
        i = end + 1
    return out


def asia_breakout(h, a):
    out, by_day = [], {}
    for k, c in enumerate(h):
        by_day.setdefault(c["time"] // 86400, []).append(k)
    for day, idxs in sorted(by_day.items()):
        if time.gmtime(day * 86400).tm_wday >= 5:
            continue
        hrs = {time.gmtime(h[k]["time"]).tm_hour: k for k in idxs}
        if not all(x in hrs for x in range(0, 21)):
            continue
        rh = max(h[hrs[x]]["high"] for x in range(0, 7))
        rl = min(h[hrs[x]]["low"] for x in range(0, 7))
        for hr in range(7, 16):
            c = h[hrs[hr]]
            side = 1 if c["close"] > rh else (-1 if c["close"] < rl else 0)
            if not side:
                continue
            k = hrs[hr + 1]
            e = h[k]["open"]
            sd = abs(e - (rl if side > 0 else rh))
            if sd > 0 and a[k - 1]:
                bars = hrs[20] - k + 1
                out.append((h[k]["time"], trade_r(h, k, side, sd, bars), side, k, sd / a[k - 1], bars))
            break
    return out


def judge(name, trades, c, span_days):
    say(f"\n=== {name} ===")
    if len(trades) < 30:
        say(f"  мало сделок ({len(trades)})")
        return False
    a = atr(c, 14)
    rng = random.Random(7)
    ok_idx = [i for i in range(15, len(c) - 60) if a[i - 1]]
    excess, base_all = [], []
    for t, r, side, k, stop_atr, bars in trades:
        bs = []
        for _ in range(RANDOM_DRAWS):
            i = rng.choice(ok_idx)
            bs.append(trade_r(c, i, side, stop_atr * a[i - 1], bars))
        b = sum(bs) / len(bs)
        base_all.append(b)
        excess.append(r - b)
    rs = [x[1] for x in trades]
    n, half = len(rs), len(rs) // 2
    avg, base = sum(rs) / n, sum(base_all) / n
    t_ex = tstat(excess)
    ex1, ex2 = sum(excess[:half]) / half, sum(excess[half:]) / (n - half)
    longs = [x[1] for x in trades if x[2] > 0]
    shorts = [x[1] for x in trades if x[2] < 0]
    per_week = n / (span_days / 7)
    say(f"  сделок {n} (≈{per_week:.1f} в неделю, раз в {7 / per_week:.1f} дн.) · WR {sum(1 for r in rs if r > 0) / n * 100:.0f}% · "
        f"{avg:+.3f}R/сделку · итого {sum(rs):+.0f}R")
    say(f"  лонги {len(longs)}: {sum(longs) / max(len(longs), 1):+.3f}R · шорты {len(shorts)}: "
        f"{sum(shorts) / max(len(shorts), 1):+.3f}R")
    say(f"  входы наугад (та же сторона/стоп/время): {base:+.3f}R/сделку → превышение {avg - base:+.3f}R · "
        f"t={t_ex if t_ex is None else round(t_ex, 2)}")
    say(f"  превышение по половинам: {ex1:+.3f}R / {ex2:+.3f}R")
    years = {}
    for x in trades:
        years.setdefault(time.gmtime(x[0]).tm_year, []).append(x[1])
    say("  по годам: " + " · ".join(f"{y}: {sum(v):+.1f}R/{len(v)}" for y, v in sorted(years.items())))
    for rp in (1, 2):
        bal = peak = 1000.0
        dd = 0.0
        for r in rs:
            bal = max(bal * (1 + rp / 100 * r), 0.0)
            peak = max(peak, bal)
            dd = max(dd, (1 - bal / peak) * 100 if peak else 100)
        say(f"  $1000 при риске {rp}%: ${bal:,.0f} ({((bal / 1000) ** (365 / span_days) - 1) * 100:+.0f}%/год) · "
            f"худшая просадка {dd:.0f}%")
    ok = (t_ex or 0) >= PASS_T and ex1 > 0 and ex2 > 0 and avg > 0
    say(f"  ВЕРДИКТ: {'ПРОШЛА' if ok else 'не прошла'} (нужно: превышение над случайными t >= {PASS_T} "
        f"и в обеих половинах, сама схема в плюсе)")
    return ok


def main():
    t0 = time.time()
    print("качаю часовые PAXG/USDT с Binance...")
    h = fetch_1h()
    if len(h) < 5000:
        sys.exit(f"мало данных ({len(h)} свечей)")
    c4 = to_4h(h)
    span = (h[-1]["time"] - h[0]["time"]) / 86400
    say(f"PAXG/USDT: {len(h)} часовых ({len(c4)} 4ч) с {time.strftime('%Y-%m-%d', time.gmtime(h[0]['time']))}, "
        f"{span / 365:.1f} г.")
    bh = h[-1]["close"] / h[0]["close"] - 1
    say(f"купить и держать: {bh * 100:+.0f}% ({((1 + bh) ** (365 / span) - 1) * 100:+.0f}%/год)")
    passed = []
    if judge("A. ОТКАТ ПО ТРЕНДУ RSI-2, 4ч", rsi2_pullback(c4), c4, span):
        passed.append("A")
    if judge("B. ПРОБОЙ КАНАЛА 20/10, 4ч", channel_breakout(c4), c4, span):
        passed.append("B")
    if judge("C. ПРОБОЙ АЗИАТСКОГО ДИАПАЗОНА, 1ч", asia_breakout(h, atr(h, 14)), h, span):
        passed.append("C")
    say(f"\nИТОГ: прошли — {', '.join(passed) if passed else 'ни одна'} · время {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "gold_swing_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: gold_swing_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
