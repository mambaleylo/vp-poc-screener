#!/usr/bin/env python3
"""Trend: проверка модуля на РЕАЛЬНЫХ дневных свечах Gate — оставить или удалить.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python trend_research.py [число монет, по умолчанию 60]
    python trend_research.py 60 --holdout     # второй запуск: открыть последний год для вариантов
    python trend_research.py 60 --money       # сколько с $100: по годам и месяцам, с лотами Gate и фандингом

Ничего не торгует и не пишет в состояние сервера. Свечи берутся через кэш
программы, повторный запуск быстрый. Отчёт печатается и сохраняется в
trend_report.txt (его удобно скопировать целиком).

Как читать:
1. «ОСНОВНОЙ ВАРИАНТ» — ровно те правила, что в программе. Они взяты из
   исследования и на этих данных не подбирались, поэтому вся история для него —
   честная проверка. По ней и решается «оставить / удалить».
2. «ВАРИАНТЫ» — калибровка. Показана только история ДО последнего года.
   Последний год спрятан: если выбрать лучший вариант, глядя на всё сразу,
   проверки не останется. После выбора запустите с --holdout ОДИН раз.
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

HOLDOUT_DAYS = 365
BASE = {"name": "основной", "lookbacks": (5, 10, 20, 30, 60, 90, 150, 250, 360), "votes": 5, "min_stop": 1.0}
VARIANTS = [
    {"name": "голосов 3 из 9", "votes": 3},
    {"name": "голосов 4 из 9", "votes": 4},
    {"name": "голосов 6 из 9", "votes": 6},
    {"name": "голосов 7 из 9", "votes": 7},
    {"name": "быстрые 5..60, 3 из 5", "lookbacks": (5, 10, 20, 30, 60), "votes": 3},
    {"name": "медленные 20..360, 4 из 7", "lookbacks": (20, 30, 60, 90, 150, 250, 360), "votes": 4},
    {"name": "мин. стоп 3%", "min_stop": 3.0},
    {"name": "только топ-10 монет", "top": 10},
    {"name": "только топ-30 монет", "top": 30},
    {"name": "BTC выше SMA100 (оценка)", "btc_sma": 100},
    {"name": "BTC выше SMA200 (оценка)", "btc_sma": 200},
]

PF_VARIANTS = ("голосов 3 из 9", "быстрые 5..60, 3 из 5")
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def tstat(rs):
    n = len(rs)
    if n < 2:
        return None
    mu = sum(rs) / n
    sd = math.sqrt(sum((r - mu) ** 2 for r in rs) / (n - 1))
    return mu / (sd / math.sqrt(n)) if sd > 0 else None


def stats(trades):
    rs = [t["pnl_r_net"] for t in trades]
    n = len(rs)
    if not n:
        return {"n": 0}
    eq = peak = dd = 0.0
    for t in sorted(trades, key=lambda x: x["exit_time"]):
        eq += t["pnl_r_net"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    t = tstat(rs)
    return {"n": n, "wr": round(sum(1 for r in rs if r > 0) / n * 100, 1), "avg": sum(rs) / n, "sum": sum(rs),
            "t": t, "dd": dd, "best": max(rs), "hold": sum(x["hold_days"] for x in trades) / n}


def line(s):
    if not s.get("n"):
        return "нет сделок"
    return (f"n={s['n']:4d} · WR {s['wr']:4.1f}% · {s['avg']:+.3f}R/сд · итого {s['sum']:+7.1f}R · "
            f"t={s['t']:.2f} · просадка {s['dd']:.1f}R" if s["t"] is not None else f"n={s['n']} · итого {s['sum']:+.1f}R")


def run(m, data, v, btc_ok):
    m.TREND_LOOKBACKS = tuple(v.get("lookbacks", BASE["lookbacks"]))
    m.TREND_ENTRY_VOTES = v.get("votes", BASE["votes"])
    m.TREND_MIN_STOP_PCT = v.get("min_stop", BASE["min_stop"])
    syms = [s for s, _ in data][: v.get("top", len(data))]
    out = {}
    for s, candles in data:
        if s not in syms:
            continue
        trades, _ = m.trend_simulate(candles)
        if v.get("btc_sma"):
            ok = btc_ok[v["btc_sma"]]
            trades = [t for t in trades if ok.get(t["time"], False)]
        out[s] = trades
    return out


def portfolio(trades, risk_pct):
    """All coins on ONE balance, as the auto-trader would run them: each
    entry risks risk_pct of the balance at that moment, the result lands at
    the exit. Returns (final x, worst drawdown %, most positions at once)."""
    ev = []
    for t in trades:
        ev.append((t["entry_time"], 1, t))
        ev.append((t["exit_time"], 0, t))
    ev.sort(key=lambda e: (e[0], e[1]))
    bal = peak = 1.0
    dd = 0.0
    risk, open_n, max_open = {}, 0, 0
    for _, kind, t in ev:
        if kind == 1:
            risk[id(t)] = bal * risk_pct / 100
            open_n += 1
            max_open = max(max_open, open_n)
        else:
            bal = max(bal + risk.pop(id(t), 0.0) * t["pnl_r_net"], 0.0)
            open_n -= 1
            peak = max(peak, bal)
            dd = max(dd, (1 - bal / peak) * 100 if peak > 0 else 100)
    return bal, dd, max_open


def pf_line(trades):
    out = []
    for rp in (0.5, 1, 2):
        b, dd, mo = portfolio(trades, rp)
        out.append(f"риск {rp:g}%: x{b:.2f}, просадка {dd:.0f}%")
    return " · ".join(out) + f" · позиций одновременно до {mo}"


def pick_best(per, score, top, start, step_days=7, min_n=5):
    """Walk-forward, as the program would trade ONE coin: every step_days the
    coins are ranked by score() of their trades CLOSED before that moment
    (nothing from the future), and until the next re-pick only the top
    coin(s) may open trades. A coin with a score <= 0 is never picked."""
    out, m_ = [], start
    now = time.time()
    while m_ < now:
        sc = []
        for s, ts in per.items():
            past = [t for t in ts if t["exit_time"] < m_]
            if len(past) >= min_n:
                v = score(past, m_)
                if v is not None and v > 0:
                    sc.append((v, s))
        chosen = {s for _, s in sorted(sc, reverse=True)[:top]}
        end = m_ + step_days * 86400
        for s in chosen:
            out += [t for t in per[s] if m_ <= t["entry_time"] < end]
        m_ = end
    return sorted(out, key=lambda t: t["entry_time"])


SCORES = (
    ("сумма R за всё время", lambda past, m_: sum(t["pnl_r_net"] for t in past)),
    ("сумма R за последний год", lambda past, m_: sum(t["pnl_r_net"] for t in past if t["exit_time"] >= m_ - 365 * 86400) or None),
    ("t за всё время", lambda past, m_: tstat([t["pnl_r_net"] for t in past])),
)


FUNDING_PER_DAY = 0.0003   # longs pay ~0.01% every 8h on average — not in the R backtest, charged here


def money_sim(trades, specs, risk_pct, start=100.0, fee=0.0005):
    """$ simulation of ONE account trading every coin, sized like the live
    auto-trader: loss at the stop = risk_pct of the balance (fees included),
    whole contracts only (same rule as live: round up to the minimum lot only
    if it is <= 1.5x the wanted size, else skip), leverage ~ the safe one for
    the stop, margin of all open positions <= the balance, funding charged.
    Returns (final, month-end balances {(y, m): bal}, max drawdown %, skipped)."""
    ev = []
    for t in trades:
        ev.append((t["entry_time"], 1, t))
        ev.append((t["exit_time"], 0, t))
    ev.sort(key=lambda e: (e[0], e[1]))
    bal, peak, dd, used, skipped = start, start, 0.0, 0.0, 0
    pos, months = {}, {}
    for ts, kind, t in ev:
        ym = time.gmtime(ts)[:2]
        months[ym] = bal
        if kind == 1:
            sp = specs.get(t["symbol"])
            e, sl = t["entry"], t["sl"]
            stop = (e - sl) / e
            if not sp or stop <= 0 or bal <= 0:
                skipped += 1
                continue
            want = bal * risk_pct / 100 / (stop + 2 * fee)
            lot = sp["mult"] * e * sp["min"]
            if want < lot:
                if lot > want * 1.5:
                    skipped += 1
                    continue
                notional = lot
            else:
                notional = math.floor(want / lot) * lot
            lev = max(1, min(sp["lev"], int(0.8 / stop)))
            margin = notional / lev
            if used + margin > bal * 0.98:
                skipped += 1
                continue
            used += margin
            pos[id(t)] = (notional, margin)
        else:
            if id(t) not in pos:
                continue
            notional, margin = pos.pop(id(t))
            used -= margin
            move = (t["exit_price"] - t["entry"]) / t["entry"]
            pnl = notional * move - notional * fee * (2 + move) - notional * FUNDING_PER_DAY * t["hold_days"]
            bal = max(bal + max(pnl, -margin), 0.0)
            peak = max(peak, bal)
            dd = max(dd, (1 - bal / peak) * 100 if peak > 0 else 100)
        months[ym] = bal
    # every calendar month, carrying the balance through months with no exits
    full, y, mo, last = {}, *time.gmtime(ev[0][0])[:2], start
    end = time.gmtime()[:2]
    while (y, mo) <= end:
        last = months.get((y, mo), last)
        full[(y, mo)] = last
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    return bal, full, dd, skipped


def money_block(m, per):
    say("\n=== СКОЛЬКО С $100 (все монеты, размер как у автоторговли, целые контракты, маржа, комиссии, фандинг) ===")
    specs = {}
    for s in per:
        try:
            sp = m.get_contract_spec(s)
            specs[s] = {"mult": sp["quanto_multiplier"], "min": sp["order_size_min"] or 1,
                        "lev": int(sp.get("leverage_max") or 20)}
        except Exception as e:
            print(f"  спецификация {s}: {e}")
    trades = [dict(t, symbol=s) for s, ts in per.items() for t in ts]
    first = min(t["entry_time"] for t in trades)
    for rp in (0.5, 1, 2, 3, 5):
        fin, months, dd, skipped = money_sim(trades, specs, rp)
        keys = sorted(months)
        years = (time.time() - first) / (365 * 86400)
        yr = (fin / 100) ** (1 / years) - 1 if fin > 0 else -1
        rets, prev = [], 100.0
        for k in keys:
            rets.append(months[k] / prev - 1 if prev > 0 else 0)
            prev = months[k]
        by_year = {}
        for k in keys:
            by_year[k[0]] = months[k]
        yline, prev = [], 100.0
        for y in sorted(by_year):
            yline.append(f"{y}: {(by_year[y] / prev - 1) * 100:+.0f}%")
            prev = by_year[y]
        srt = sorted(rets)
        neg = sum(1 for r in rets if r < 0)
        say(f"  риск {rp:g}%: $100 → ${fin:,.0f} за {years:.1f} г. · в среднем {yr * 100:+.0f}%/год "
            f"({((1 + yr) ** (1 / 12) - 1) * 100:+.1f}%/мес) · худшая просадка {dd:.0f}%")
        say(f"      по годам: {' · '.join(yline)}")
        if srt:
            say(f"      месяцы: в минусе {neg} из {len(rets)} · медиана {srt[len(srt) // 2] * 100:+.1f}% · "
                f"худший {srt[0] * 100:+.0f}% · лучший {srt[-1] * 100:+.0f}% · пропущено сделок {skipped} из {len(trades)}")
    say("  пропущено = минимальный лот Gate больше нужного размера или не хватило маржи (на $100 это часто)")


def btc_filter(btc, n):
    closes, ok = [c["close"] for c in btc], {}
    for i, c in enumerate(btc):
        if i >= n:
            ok[c["time"]] = closes[i] > sum(closes[i - n + 1:i + 1]) / n
    return ok


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_holdout = "--holdout" in sys.argv
    spec = importlib.util.spec_from_file_location("vp", MAIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if not hasattr(m, "trend_simulate"):
        sys.exit("vp_poc_screener.py старый — скачайте версию 0.99.425 или новее")
    n = int(args[0]) if args else 60
    m.TREND_UNIVERSE_N = n
    syms = m.trend_build_universe()
    if not syms:
        sys.exit("не удалось получить список монет с Gate (нет сети?)")
    t0, data = time.time(), []
    say(f"монет: {len(syms)} · история до {m.TREND_HISTORY_DAYS} дн. · дневные свечи · комиссии учтены")
    for i, s in enumerate(syms, 1):
        try:
            cs = m.trend_daily_candles(s)
            if len(cs) >= 60:
                data.append((s, cs))
        except Exception as e:
            print(f"  {s}: {e}")
        if i % 10 == 0:
            print(f"  ...скачано {i}/{len(syms)} ({time.time() - t0:.0f} с)")
    btc = dict(data).get("BTC_USDT") or m.trend_daily_candles("BTC_USDT")
    btc_ok = {k: btc_filter(btc, k) for k in (100, 200)}
    first = min(c[0]["time"] for _, c in data)
    cut = time.time() - HOLDOUT_DAYS * 86400
    say(f"данные с {time.strftime('%Y-%m-%d', time.gmtime(first))} · монет с историей ≥ 60 дн.: {len(data)}")

    # 1. the rules the program trades: the whole history is a clean test
    per = run(m, data, BASE, btc_ok)
    allt = sorted((t for ts in per.values() for t in ts), key=lambda t: t["entry_time"])
    s_all = stats(allt)
    half = len(allt) // 2
    h1, h2 = stats(allt[:half]), stats(allt[half:])
    say("\n=== ОСНОВНОЙ ВАРИАНТ (правила из программы, не подбирались) ===")
    say(f"  все:         {line(s_all)}")
    if s_all.get("n"):
        say(f"               лучшая {s_all['best']:+.1f}R · в сделке ~{s_all['hold']:.0f} дн.")
    say(f"  1-я половина {line(h1)}")
    say(f"  2-я половина {line(h2)}")
    say(f"  последний год {line(stats([t for t in allt if t['entry_time'] >= cut]))}")
    say("  по годам (вход):")
    years = {}
    for t in allt:
        years.setdefault(time.gmtime(t["entry_time"]).tm_year, []).append(t)
    for y in sorted(years):
        st = stats(years[y])
        say(f"    {y}: n={st['n']:3d} · WR {st['wr']:4.1f}% · итого {st['sum']:+7.1f}R")
    coin = sorted(((s, sum(t["pnl_r_net"] for t in ts), len(ts)) for s, ts in per.items() if ts), key=lambda x: -x[1])
    pos = sum(1 for _, r, _ in coin if r > 0)
    say(f"  монет в плюсе: {pos} из {len(coin)}")
    say("  лучшие: " + ", ".join(f"{s[:-5]} {r:+.0f}R/{k}" for s, r, k in coin[:6]))
    say("  худшие: " + ", ".join(f"{s[:-5]} {r:+.0f}R/{k}" for s, r, k in coin[-6:]))
    # the module's own verdict rule
    passed = (s_all.get("n", 0) >= m.TREND_MIN_TRADES and (s_all.get("t") or 0) >= m.TREND_PASS_T
              and h1.get("n") and h1["avg"] > 0 and h2.get("n") and h2["avg"] > 0)
    say(f"\n  ВЕРДИКТ ПРОГРАММЫ: {'ПРОШЁЛ — оставляем' if passed else 'НЕ прошёл'} "
        f"(нужно n ≥ {m.TREND_MIN_TRADES}, t ≥ {m.TREND_PASS_T}, плюс в обеих половинах)")
    say("  монеты двигаются вместе, t немного завышен — смотрите и на годы, и на число монет в плюсе")

    if "--money" in sys.argv:
        money_block(m, per)
        say(f"\nвремя: {time.time() - t0:.0f} с")
        with open(os.path.join(os.getcwd(), "trend_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        return

    # 1b. trading ONE coin: the best by its own backtest, re-picked weekly
    start = first + 365 * 86400
    base_after = [t for t in allt if t["entry_time"] >= start]
    say(f"\n=== ОДНА МОНЕТА — ЛУЧШАЯ ПО БЭКТЕСТУ (выбор раз в неделю только по прошлому, с {time.strftime('%Y-%m-%d', time.gmtime(start))}) ===")
    say(f"  для сравнения, все монеты:  {line(stats(base_after))}")
    for name, fn in SCORES:
        for top in ((1, 3) if name == SCORES[0][0] else (1,)):
            ts = pick_best(per, fn, top, start)
            say(f"  топ-{top}, {name}:")
            say(f"      {line(stats(ts))}")
            if top == 1:
                yrs = {}
                for t in ts:
                    yrs.setdefault(time.gmtime(t["entry_time"]).tm_year, []).append(t["pnl_r_net"])
                say("      по годам: " + " · ".join(f"{y}: {sum(v):+.1f}R/{len(v)}" for y, v in sorted(yrs.items())))
                say("      один счёт: " + " · ".join(
                    f"риск {rp:g}%: x{portfolio(ts, rp)[0]:.2f}, просадка {portfolio(ts, rp)[1]:.0f}%" for rp in (2, 5, 10, 30)))
    say("  если «лучшая монета» не лучше «все монеты» на сделку — выбор по бэктесту не помогает, это удача прошлого")

    # 2. calibration: variants on everything BEFORE the last year
    say(f"\n=== ВАРИАНТЫ: калибровка (только до {time.strftime('%Y-%m-%d', time.gmtime(cut))}) ===")
    rows = []
    for v in [BASE] + VARIANTS:
        pv = run(m, data, v, btc_ok)
        ts = [t for x in pv.values() for t in x]
        cal = stats([t for t in ts if t["entry_time"] < cut])
        hold = stats([t for t in ts if t["entry_time"] >= cut])
        rows.append((v["name"], cal, hold))
    for name, cal, hold in rows:
        say(f"  {name:28s} {line(cal)}")
        if show_holdout:
            say(f"  {'   └ последний год':28s} {line(hold)}")
    say("\n=== ОДИН СЧЁТ НА ВСЕ МОНЕТЫ (как автоторговля: риск % от баланса на сделку) ===")
    say(f"  основной, вся история: {pf_line(allt)}")
    for name in PF_VARIANTS:
        v = next(x for x in VARIANTS if x["name"] == name)
        ts = [t for x in run(m, data, v, btc_ok).values() for t in x]
        if not show_holdout:
            ts = [t for t in ts if t["entry_time"] < cut]
        say(f"  {name}, {'вся история' if show_holdout else 'до последнего года'}: {pf_line(ts)}")
    say("  (без учёта маржи: при многих позициях сразу часть сделок не хватило бы денег открыть)")
    if not show_holdout:
        say("  последний год скрыт. Выберите вариант по этой таблице, потом ОДИН раз: --holdout")
    say(f"\nвремя: {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "trend_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: trend_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
