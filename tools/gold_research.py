#!/usr/bin/env python3
"""Золото: четыре классические схемы на РЕАЛЬНЫХ данных Gate (XAU_USDT / PAXG_USDT / XAUT_USDT).

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python gold_research.py
    python gold_research.py --stooq     # дневные схемы на истории спотового золота XAUUSD с stooq.com (десятки лет)

Ничего не торгует. Схемы заданы заранее, параметры не подбираются:
 1. ТРЕНД 12 МЕСЯЦЕВ (Moskowitz, Ooi, Pedersen 2012): каждые 30 дней лонг, если
    цена выше, чем 365 дней назад, иначе шорт. Дневные свечи.
 2. КАНАЛЫ ДОНЧИАНА («черепахи»): вход по закрытию выше 55-дневного максимума
    (шорт — ниже минимума), выход по 20-дневному каналу в обратную сторону,
    стоп 2 ATR(20). Дневные свечи.
 3. ПРОБОЙ АЗИАТСКОГО ДИАПАЗОНА: диапазон 00:00–06:59 UTC; с 07:00 до 15:59 первое
    закрытие часа выше/ниже диапазона — вход следующей свечой, стоп на другой
    стороне диапазона, выход в 20:00 UTC. Только будни. 1ч свечи (~400 дней).
 4. КАНАЛ КЕЛЬТНЕРА, возврат к среднему: EMA20 ± 2 ATR(20) на 1ч; касание
    границы — вход против движения, цель EMA, стоп 1 ATR от входа, максимум 24 ч.
Комиссии 0.1% за круг учтены. Схема проходит, если t >= 2.5 (поправка на 4
схемы) и плюс в обеих половинах периода. Для сравнения — «купить и держать».
"""
import importlib.util
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = next((p for p in (os.path.join(HERE, "vp_poc_screener.py"), os.path.join(HERE, "..", "vp_poc_screener.py"),
                         os.path.join(os.getcwd(), "vp_poc_screener.py")) if os.path.exists(p)), None)
if MAIN is None:
    sys.exit("не найден vp_poc_screener.py — положите этот скрипт в ту же папку")

SYMBOLS = ("XAU_USDT", "PAXG_USDT", "XAUT_USDT")
FEE = 0.001          # round trip, fraction of notional
PASS_T = 2.5
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def tstat(xs):
    n = len(xs)
    if n < 3:
        return None
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
    return mu / (sd / math.sqrt(n)) if sd > 0 else None


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


def money(rs, risk_pct, start=1000.0):
    """sequential trades, each risking risk_pct of the balance at the stop"""
    bal = peak = start
    dd = 0.0
    for r in rs:
        bal = max(bal * (1 + risk_pct / 100 * r), 0.0)
        peak = max(peak, bal)
        dd = max(dd, (1 - bal / peak) * 100 if peak else 100)
    return bal, dd


def report_trades(name, trades, span_days):
    """trades: list of (entry_time, R)"""
    say(f"\n=== {name} ===")
    if len(trades) < 10:
        say(f"  мало сделок ({len(trades)})")
        return False
    trades.sort()
    rs = [r for _, r in trades]
    half = len(rs) // 2
    t = tstat(rs)
    avg = sum(rs) / len(rs)
    h1, h2 = sum(rs[:half]) / half, sum(rs[half:]) / (len(rs) - half)
    wr = sum(1 for r in rs if r > 0) / len(rs) * 100
    say(f"  сделок {len(rs)} · WR {wr:.0f}% · {avg:+.3f}R/сделку · итого {sum(rs):+.1f}R · t={t if t is None else round(t, 2)}")
    say(f"  1-я половина {h1:+.3f}R · 2-я половина {h2:+.3f}R")
    years = {}
    for ts, r in trades:
        years.setdefault(time.gmtime(ts).tm_year, []).append(r)
    say("  по годам: " + " · ".join(f"{y}: {sum(v):+.1f}R/{len(v)}" for y, v in sorted(years.items())))
    yrs = max(span_days / 365, 0.1)
    for rp in (1, 2):
        b, dd = money(rs, rp)
        say(f"  $1000 при риске {rp}%: ${b:,.0f} ({((b / 1000) ** (1 / yrs) - 1) * 100:+.0f}%/год) · худшая просадка {dd:.0f}%")
    ok = (t or 0) >= PASS_T and h1 > 0 and h2 > 0
    say(f"  ВЕРДИКТ: {'ПРОШЛА' if ok else 'не прошла'} (нужно t >= {PASS_T} и плюс в обеих половинах)")
    return ok


def tsmom(d):
    """monthly long/short by the sign of the 365-day return; returns monthly % returns"""
    rets = []
    times = [c["time"] for c in d]
    i = next((k for k, c in enumerate(d) if c["time"] >= d[0]["time"] + 365 * 86400), None)
    while i is not None and i < len(d) - 1:
        j_back = max(0, next((k for k in range(i, -1, -1) if times[k] <= times[i] - 365 * 86400), 0))
        side = 1 if d[i]["close"] > d[j_back]["close"] else -1
        k_end = next((k for k in range(i + 1, len(d)) if times[k] >= times[i] + 30 * 86400), None)
        if k_end is None:
            break
        r = side * (d[k_end]["close"] / d[i]["close"] - 1) - FEE
        rets.append((times[i], r, d[k_end]["close"] / d[i]["close"] - 1))
        i = k_end
    return rets


def donchian(d):
    a = atr(d, 20)
    out, pos = [], None
    for i in range(56, len(d) - 1):
        c = d[i]
        if pos is None:
            hi55 = max(x["high"] for x in d[i - 55:i])
            lo55 = min(x["low"] for x in d[i - 55:i])
            side = 1 if c["close"] > hi55 else (-1 if c["close"] < lo55 else 0)
            if side and a[i]:
                e = d[i + 1]["open"]
                pos = {"side": side, "e": e, "stop": e - side * 2 * a[i], "risk": 2 * a[i], "t": d[i + 1]["time"]}
            continue
        s = pos["side"]
        if (s > 0 and c["low"] <= pos["stop"]) or (s < 0 and c["high"] >= pos["stop"]):
            px = pos["stop"]
        else:
            lo20 = min(x["low"] for x in d[i - 20:i])
            hi20 = max(x["high"] for x in d[i - 20:i])
            if not ((s > 0 and c["close"] < lo20) or (s < 0 and c["close"] > hi20)):
                continue
            px = d[i + 1]["open"]
        out.append((pos["t"], s * (px - pos["e"]) / pos["risk"] - FEE * pos["e"] / pos["risk"]))
        pos = None
    return out


def asia_breakout(h):
    out = []
    by_day = {}
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
        if rh <= rl:
            continue
        for hr in range(7, 16):
            c = h[hrs[hr]]
            side = 1 if c["close"] > rh else (-1 if c["close"] < rl else 0)
            if not side:
                continue
            e = h[hrs[hr + 1]]["open"]
            stop = rl if side > 0 else rh
            risk = abs(e - stop)
            if risk <= 0:
                break
            px = h[hrs[20]]["close"]
            for x in range(hr + 1, 21):
                b = h[hrs[x]]
                if (side > 0 and b["low"] <= stop) or (side < 0 and b["high"] >= stop):
                    px = stop
                    break
            out.append((h[hrs[hr + 1]]["time"], side * (px - e) / risk - FEE * e / risk))
            break
    return out


def keltner_mr(h):
    closes = [c["close"] for c in h]
    m = ema(closes, 20)
    a = atr(h, 20)
    out, busy = [], -1
    for i in range(21, len(h) - 25):
        if i <= busy or not a[i]:
            continue
        up, dn = m[i] + 2 * a[i], m[i] - 2 * a[i]
        side = -1 if h[i]["high"] >= up else (1 if h[i]["low"] <= dn else 0)
        if not side:
            continue
        e = h[i + 1]["open"]
        stop = e - side * a[i]
        px, j_end = h[i + 24]["close"], i + 24
        for j in range(i + 1, i + 25):
            b = h[j]
            if (side > 0 and b["low"] <= stop) or (side < 0 and b["high"] >= stop):
                px, j_end = stop, j
                break
            if (side > 0 and b["high"] >= m[j]) or (side < 0 and b["low"] <= m[j]):
                px, j_end = m[j], j
                break
        out.append((h[i + 1]["time"], side * (px - e) / a[i] - FEE * e / a[i]))
        busy = j_end
    return out


STOOQ_URL = "https://stooq.com/q/d/l/?s=xauusd&i=d"


def stooq_daily(m):
    """Long daily spot-gold history (XAUUSD) from stooq.com — Gate's own gold
    contracts are too young for the daily systems; XAU_USDT tracks spot gold."""
    try:
        r = m.requests.get(STOOQ_URL, timeout=30)
        rows = r.text.strip().splitlines()
    except Exception as e:
        say(f"stooq: {e}")
        return []
    out = []
    for line in rows[1:]:
        p = line.split(",")
        if len(p) < 5:
            continue
        try:
            t = int(time.mktime(time.strptime(p[0], "%Y-%m-%d"))) - time.timezone
            o, h, l, c = (float(x) for x in p[1:5])
        except ValueError:
            continue
        out.append({"time": t, "open": o, "high": h, "low": l, "close": c, "volume": 0})
    out.sort(key=lambda x: x["time"])
    return out


def main():
    spec = importlib.util.spec_from_file_location("vp", MAIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    now = int(time.time())
    best = {}
    if "--stooq" in sys.argv:
        sd_ = stooq_daily(m)
        if len(sd_) > 500:
            say(f"stooq XAUUSD 1d: {len(sd_)} свечей с {time.strftime('%Y-%m-%d', time.gmtime(sd_[0]['time']))}")
            best["1d"] = ("XAUUSD (stooq)", sd_)
        else:
            say(f"stooq: не удалось получить историю ({len(sd_)} строк) — дневные схемы по данным Gate")
    for tf, days in (("1d", 3000), ("1h", 420)):
        for s in SYMBOLS:
            try:
                cs = m.get_candles_range(s, tf, now - days * 86400, now) or []
            except Exception as e:
                print(f"  {s} {tf}: {e}")
                cs = []
            sec = m.INTERVAL_SECONDS.get(tf, 3600)
            cs = [c for c in cs if c["time"] + sec <= now]
            if cs:
                say(f"{s} {tf}: {len(cs)} свечей с {time.strftime('%Y-%m-%d', time.gmtime(cs[0]['time']))}")
            if cs and len(cs) > len(best.get(tf, ("", []))[1]) and not (tf == "1d" and "stooq" in best.get("1d", ("",))[0]):
                best[tf] = (s, cs)
    if "1d" not in best:
        sys.exit("нет данных по золоту")
    sd, d = best["1d"]
    span_d = (d[-1]["time"] - d[0]["time"]) / 86400
    say(f"\nдневные: {sd} ({span_d:.0f} дн.) · часовые: {best.get('1h', ('—', []))[0]}")
    bh = d[-1]["close"] / d[0]["close"] - 1
    say(f"купить и держать: {bh * 100:+.0f}% за {span_d / 365:.1f} г. ({((1 + bh) ** (365 / span_d) - 1) * 100:+.0f}%/год)")

    passed = []
    # 1. TSMOM: monthly returns, not R
    rets = tsmom(d)
    say("\n=== 1. ТРЕНД 12 МЕСЯЦЕВ (лонг/шорт раз в 30 дней, плечо 1) ===")
    if len(rets) >= 10:
        rs = [r for _, r, _ in rets]
        half = len(rs) // 2
        t = tstat(rs)
        bal = peak = 1.0
        dd = 0.0
        for r in rs:
            bal *= 1 + r
            peak = max(peak, bal)
            dd = max(dd, 1 - bal / peak)
        yrs = len(rs) * 30 / 365
        say(f"  месяцев {len(rs)} · в плюсе {sum(1 for r in rs if r > 0)} · в среднем {sum(rs) / len(rs) * 100:+.2f}%/мес · "
            f"t={t if t is None else round(t, 2)}")
        say(f"  итог x{bal:.2f} ({(bal ** (1 / yrs) - 1) * 100:+.0f}%/год) · худшая просадка {dd * 100:.0f}% · "
            f"половины {sum(rs[:half]) / half * 100:+.2f}% / {sum(rs[half:]) / (len(rs) - half) * 100:+.2f}% в мес.")
        hold = 1.0
        for _, _, raw in rets:
            hold *= 1 + raw
        say(f"  за тот же период «купить и держать»: x{hold:.2f}")
        ok = (t or 0) >= PASS_T and sum(rs[:half]) > 0 and sum(rs[half:]) > 0
        say(f"  ВЕРДИКТ: {'ПРОШЛА' if ok else 'не прошла'} (нужно t >= {PASS_T} и плюс в обеих половинах)")
        if ok:
            passed.append("тренд 12 мес.")
    else:
        say("  мало истории")
    if report_trades("2. КАНАЛЫ ДОНЧИАНА 55/20, стоп 2 ATR (дневные)", donchian(d), span_d):
        passed.append("Дончиан")
    if "1h" in best:
        sh, h = best["1h"]
        span_h = (h[-1]["time"] - h[0]["time"]) / 86400
        if report_trades(f"3. ПРОБОЙ АЗИАТСКОГО ДИАПАЗОНА ({sh}, 1ч)", asia_breakout(h), span_h):
            passed.append("азиатский диапазон")
        if report_trades(f"4. КАНАЛ КЕЛЬТНЕРА, возврат к среднему ({sh}, 1ч)", keltner_mr(h), span_h):
            passed.append("Кельтнер")
    say(f"\nИТОГ: прошли проверку — {', '.join(passed) if passed else 'ни одна'}")
    try:
        with open(os.path.join(os.getcwd(), "gold_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: gold_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
