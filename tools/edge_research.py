#!/usr/bin/env python3
"""Две идеи на РЕАЛЬНЫХ данных Gate: экстремальный фандинг и пары монет.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python edge_research.py [число монет, по умолчанию 40]

Ничего не торгует и не пишет в состояние сервера. Свечи 4ч за 2 года и история
фандинга; первый запуск 5-10 минут, повторный быстрее (свечи в кэше).
Отчёт печатается и сохраняется в edge_report.txt.

Правила заданы ЗАРАНЕЕ и не подбираются — вся история для них честная проверка.

1. ФАНДИНГ. Сигнал в момент начисления фандинга монеты:
   - шорт: ставка выше 95-го перцентиля её собственных ставок за прошлые 90 дней
     И выше 0.03% (втрое выше обычной 0.01%) — перегретые лонги;
   - лонг: ставка ниже 5-го перцентиля за 90 дней И ниже -0.01% — перегретые шорты.
   Вход по открытию следующей 4ч свечи, выход через 24ч / 72ч / 7 дней.
   Считается: движение цены + фандинг, полученный/уплаченный за время сделки,
   минус комиссии 0.1% за круг. Сравнение: та же сделка в любой момент (без сигнала).
2. ПАРЫ. Для самых ликвидных монет: пара торгуется, если корреляция их 4ч
   доходностей за прошлые 90 дней >= 0.7. Спред = ln(A) - ln(B), z = отклонение
   от среднего за 30 дней в стандартных отклонениях. |z| >= 2 -> шорт дорогой,
   лонг дешёвой (равные суммы); выход, когда z пересёк 0, или |z| >= 4 (стоп),
   или через 10 дней. Комиссии: 4 x 0.05%.

Проходит, если в среднем на сделку плюс после всех издержек, t по ДНЯМ >= 2
(сделки одного дня усредняются: монеты движутся вместе, иначе t завышен)
и плюс в обеих половинах периода.
"""
import bisect
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

DAYS = 730
BAR = 4 * 3600
FEE = 0.0005              # taker, one side
HOLDS_H = (24, 72, 168)
F_LOOKBACK = 90 * 86400
F_MIN_PAST = 60
F_SHORT_ABS, F_LONG_ABS = 0.0003, -0.0001
P_TOP = 15
P_CORR_BARS = 90 * 6
P_Z_BARS = 30 * 6
P_CORR_MIN, P_Z_IN, P_Z_STOP, P_MAX_BARS = 0.7, 2.0, 4.0, 10 * 6

OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def tstat(xs):
    n = len(xs)
    if n < 2:
        return None
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
    return mu / (sd / math.sqrt(n)) if sd > 0 else None


def summary(trades):
    """trades: (entry_time, pnl fraction). Day-clustered t: one number per day."""
    if not trades:
        return {"n": 0}
    xs = [p for _, p in trades]
    days = {}
    for t, p in trades:
        days.setdefault(int(t // 86400), []).append(p)
    dmeans = [sum(v) / len(v) for v in days.values()]
    srt = sorted(trades)
    half = len(srt) // 2
    h = lambda part: sum(p for _, p in part) / len(part) if part else 0.0
    return {"n": len(xs), "days": len(days), "avg": sum(xs) / len(xs), "wr": sum(1 for x in xs if x > 0) / len(xs) * 100,
            "t_day": tstat(dmeans), "h1": h(srt[:half]), "h2": h(srt[half:])}


def fmt(s):
    if not s.get("n"):
        return "нет сделок"
    td = f"{s['t_day']:.2f}" if s["t_day"] is not None else "—"
    ok = s["avg"] > 0 and (s["t_day"] or 0) >= 2 and s["h1"] > 0 and s["h2"] > 0
    return (f"n={s['n']:5d} ({s['days']} дн.) · {s['avg'] * 100:+.2f}%/сд · WR {s['wr']:.0f}% · t(дни)={td} · "
            f"половины {s['h1'] * 100:+.2f}% / {s['h2'] * 100:+.2f}%{'  ✓' if ok else ''}")


def funding_history(m, sym, start, end):
    out, to = {}, end
    for _ in range(40):
        rows = m.neuro_fetch_funding_rate(sym, max(start, to - 300 * 86400), to)
        new = [r for r in rows if r["time"] not in out]
        if not new:
            break
        for r in new:
            out[r["time"]] = r["rate"]
        earliest = min(r["time"] for r in new)
        if earliest <= start:
            break
        to = earliest - 1
    return sorted(out.items())


def funding_study(data, fund):
    """Returns {(side, hold_h): [(t, pnl)]} and the no-signal baseline."""
    res, base = {}, {}
    for sym, cs in data.items():
        fr = fund.get(sym) or []
        if len(fr) < F_MIN_PAST or len(cs) < 50:
            continue
        times = [c["time"] for c in cs]
        idx = {t: i for i, t in enumerate(times)}

        def bar_at(ts):   # first 4h bar starting at or after ts
            b = (int(ts) // BAR) * BAR
            if b < ts:
                b += BAR
            for k in range(3):
                if b + k * BAR in idx:
                    return idx[b + k * BAR]
            return None

        ftimes = [t for t, _ in fr]
        pref = [0.0]
        for _, r in fr:
            pref.append(pref[-1] + r)

        def fsum(a, b):   # funding rates paid at times in (a, b]
            return pref[bisect.bisect_right(ftimes, b)] - pref[bisect.bisect_right(ftimes, a)]

        # thresholds from the coin's own PAST 90 days, recomputed once a day
        thr, day_cache = [], {}
        for j, (ft, rate) in enumerate(fr):
            d = int(ft // 86400)
            if d not in day_cache:
                lo_j = bisect.bisect_left(ftimes, d * 86400 - F_LOOKBACK)
                hi_j = bisect.bisect_left(ftimes, d * 86400)
                past = sorted(r for _, r in fr[lo_j:hi_j])
                day_cache[d] = ((past[int(len(past) * 0.95)], past[int(len(past) * 0.05)])
                                if len(past) >= F_MIN_PAST else None)
            thr.append(day_cache[d])

        for hold_h in HOLDS_H:
            nb = hold_h * 3600 // BAR
            busy_until = {"short": 0, "long": 0}
            for j, (ft, rate) in enumerate(fr):
                if thr[j] is None:
                    continue
                i = bar_at(ft)
                if i is None or i + nb >= len(cs):
                    continue
                e, x = cs[i]["open"], cs[i + nb]["open"]
                if e <= 0:
                    continue
                ret = x / e - 1
                fs = fsum(cs[i]["time"], cs[i + nb]["time"])
                cost = 2 * FEE
                # baseline: the same trade at every funding time, no signal
                base.setdefault(("short", hold_h), []).append((ft, -ret + fs - cost))
                base.setdefault(("long", hold_h), []).append((ft, ret - fs - cost))
                hi, lo = thr[j]
                if rate > hi and rate > F_SHORT_ABS and ft >= busy_until["short"]:
                    res.setdefault(("short", hold_h), []).append((ft, -ret + fs - cost))
                    busy_until["short"] = cs[i + nb]["time"]
                if rate < lo and rate < F_LONG_ABS and ft >= busy_until["long"]:
                    res.setdefault(("long", hold_h), []).append((ft, ret - fs - cost))
                    busy_until["long"] = cs[i + nb]["time"]
    return res, base


def pairs_study(data, syms):
    trades = []
    closes = {s: {c["time"]: c for c in data[s]} for s in syms if s in data}
    names = list(closes)
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            A, B = closes[names[a]], closes[names[b]]
            ts = sorted(set(A) & set(B))
            if len(ts) < P_CORR_BARS + 10:
                continue
            la = [math.log(A[t]["close"]) for t in ts]
            lb = [math.log(B[t]["close"]) for t in ts]
            s = [x - y for x, y in zip(la, lb)]
            ra = [0.0] + [la[k] - la[k - 1] for k in range(1, len(ts))]
            rb = [0.0] + [lb[k] - lb[k - 1] for k in range(1, len(ts))]
            pos = None
            n_w = P_Z_BARS
            sw = sum(s[P_CORR_BARS - n_w + 1:P_CORR_BARS + 1]) - s[P_CORR_BARS]
            sw2 = sum(v * v for v in s[P_CORR_BARS - n_w + 1:P_CORR_BARS + 1]) - s[P_CORR_BARS] ** 2
            for k in range(P_CORR_BARS, len(ts) - 1):
                sw += s[k]
                sw2 += s[k] * s[k]
                if k - n_w >= 0 and k > P_CORR_BARS:
                    sw -= s[k - n_w]
                    sw2 -= s[k - n_w] ** 2
                mu = sw / n_w
                var = (sw2 - n_w * mu * mu) / (n_w - 1)
                if var <= 0:
                    continue
                sd = math.sqrt(var)
                z = (s[k] - mu) / sd
                if pos is not None:
                    side, k0 = pos
                    done = (side > 0 and z <= 0) or (side < 0 and z >= 0) or abs(z) >= P_Z_STOP or k - k0 >= P_MAX_BARS
                    if done:
                        o0a, o0b = A[ts[k0 + 1]]["open"], B[ts[k0 + 1]]["open"]
                        o1a, o1b = A[ts[k + 1]]["open"], B[ts[k + 1]]["open"]
                        # side>0: A rich -> short A, long B (per 1 unit of notional on each leg)
                        pnl = side * ((o1b / o0b - 1) - (o1a / o0a - 1)) - 4 * FEE
                        trades.append((ts[k0 + 1], pnl, f"{names[a][:-5]}/{names[b][:-5]}"))
                        pos = None
                    continue
                if abs(z) >= P_Z_IN and abs(z) < P_Z_STOP:
                    xa, xb = ra[k - P_CORR_BARS + 1:k + 1], rb[k - P_CORR_BARS + 1:k + 1]
                    ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
                    cov = sum((p - ma) * (q - mb) for p, q in zip(xa, xb))
                    va = sum((p - ma) ** 2 for p in xa)
                    vb = sum((q - mb) ** 2 for q in xb)
                    if va > 0 and vb > 0 and cov / math.sqrt(va * vb) >= P_CORR_MIN:
                        pos = (1 if z > 0 else -1, k)
    return trades


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    spec = importlib.util.spec_from_file_location("vp", MAIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    n = int(args[0]) if args else 40
    try:
        tickers = m.get_tickers()
    except Exception as e:
        sys.exit(f"не удалось получить список монет с Gate: {e}")
    vols = {}
    for t in tickers:
        name = t.get("contract", "")
        if not name.endswith("_USDT") or name[:-5] in m.SNR_EXCLUDED_STABLES:
            continue
        try:
            vols[name] = float(t.get("volume_24h_quote") or t.get("volume_24h_settle") or 0)
        except (TypeError, ValueError):
            pass
    syms = [s for s, _ in sorted(vols.items(), key=lambda kv: -kv[1])[:n]]
    now = time.time()
    start = now - DAYS * 86400
    t0 = time.time()
    data, fund = {}, {}
    say(f"монет: {len(syms)} · свечи 4ч за {DAYS} дн. · комиссия {FEE * 100:.2f}% за сторону")
    for i, s in enumerate(syms, 1):
        try:
            cs = [c for c in (m.get_candles_range(s, "4h", start, now) or []) if c["time"] + BAR <= now]
            if len(cs) >= 200:
                data[s] = cs
            fund[s] = funding_history(m, s, start, now)
        except Exception as e:
            print(f"  {s}: {e}")
        if i % 5 == 0:
            print(f"  ...скачано {i}/{len(syms)} ({time.time() - t0:.0f} с)")
    fdays = [(f[-1][0] - f[0][0]) / 86400 for f in fund.values() if len(f) > 1]
    say(f"свечи есть у {len(data)} монет · история фандинга: в среднем {sum(fdays) / max(1, len(fdays)):.0f} дн.")

    say("\n=== 1. ЭКСТРЕМАЛЬНЫЙ ФАНДИНГ (цена + фандинг - комиссии, на сумму позиции) ===")
    res, base = funding_study(data, fund)
    for side, title in (("short", "ШОРТ после очень высокого фандинга"), ("long", "ЛОНГ после сильно отрицательного")):
        say(f"  {title}:")
        for h in HOLDS_H:
            lbl = f"{h // 24} дн." if h >= 24 else f"{h} ч"
            say(f"    держать {lbl:6s} сигнал: {fmt(summary(res.get((side, h), [])))}")
            say(f"    {'':13s} без сигнала: {fmt(summary(base.get((side, h), [])))}")
    say("  сигнал имеет смысл, только если он заметно лучше строки «без сигнала» и отмечен ✓")

    say(f"\n=== 2. ПАРЫ МОНЕТ (топ-{P_TOP} по объёму, корреляция >= {P_CORR_MIN}, вход |z| >= {P_Z_IN}) ===")
    ptr = pairs_study(data, syms[:P_TOP])
    s2 = summary([(t, p) for t, p, _ in ptr])
    say(f"  все пары: {fmt(s2)}  (% на сумму одной ноги)")
    by = {}
    for _, p, name in ptr:
        by.setdefault(name, []).append(p)
    top = sorted(by.items(), key=lambda kv: -sum(kv[1]))
    if top:
        say("  лучшие пары:  " + ", ".join(f"{k} {sum(v) * 100:+.0f}%/{len(v)}" for k, v in top[:5]))
        say("  худшие пары:  " + ", ".join(f"{k} {sum(v) * 100:+.0f}%/{len(v)}" for k, v in top[-5:]))
    say("  (фандинг двух ног в парах не учтён: он частично взаимно гасится)")

    say(f"\nвремя: {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "edge_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: edge_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
