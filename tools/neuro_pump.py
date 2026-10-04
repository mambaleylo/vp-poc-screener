#!/usr/bin/env python3
"""Предпамповое состояние по ВСЕМ условиям Neuro (~55 штук и их пары). РЕАЛЬНЫЕ данные Gate.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python neuro_pump.py [число монет, по умолчанию 60] [--skip 10] [--pump 15]

Условия — те же, что Neuro считает на каждой часовой свече (neuro_compute_conditions):
RSI, Stoch, MACD, Боллинджер, ADX, Ишимоку, CCI, OBV, Supertrend, EMA, тренды 4ч/1д,
фандинг, OI, согласие с BTC/ETH, сессия, день недели, объём, волатильность,
сжатие, дивергенция RSI, сила к BTC и т.д. (история OI на Gate короткая — эти
условия есть только для последних недель).

ПАМП: в следующие 24ч максимум выше закрытия на 15% (--pump). Сделка: вход на
следующем часе, тейк +15%, стоп −5%, выход через 24ч, комиссия 0.1%.

1. ПРОФИЛЬ: какие значения условий встречаются перед пампом чаще, чем вообще
   (во сколько раз).
2. ПОИСК (чётные монеты по объёму): каждое значение условия и пары значений
   (пары — среди 15 лучших условий). Сигнал на монете не чаще раза в 24ч.
   Сравнение со средней сделкой той же монеты в любой час (так «волатильные
   монеты чаще пампятся» не засчитывается). t по дням, BH 10%, плюс в обеих
   половинах, сама сделка в плюсе.
3. ПОДТВЕРЖДЕНИЕ (нечётные монеты): превышение > 0, t >= 2, сделка в плюсе.
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

DAYS = 365
H = 24
STOP = 0.05
FEE = 0.001
COOLDOWN = 24 * 3600
STEP = 2
FDR_Q = 0.10
CONFIRM_T = 2.0
MIN_SIG = 60
TOP_KEYS = 15
OUT = []
LABELS = {}


def say(s=""):
    print(s)
    OUT.append(s)


def cname(cell):
    parts = [cell[i:i + 2] for i in range(0, len(cell), 2)]
    return " + ".join(f"{LABELS.get(k, k)} = {v}" for k, v in parts)


def coin_rows(m, s, btc, eth, warm, start, now, pump):
    h1 = [c for c in (m.get_candles_range(s, "1h", warm, now) or []) if c["time"] + 3600 <= now]
    if len(h1) < 24 * 120:
        return []
    h4 = m.get_candles_range(s, "4h", warm - 30 * 86400, now) or []
    d1 = m.get_candles_range(s, "1d", warm - 120 * 86400, now) or []
    try:
        fr = m.neuro_fetch_funding_rate(s, warm, now)
    except Exception:
        fr = []
    try:
        m.neuro_set_index_context(s, warm, now)
    except Exception:
        pass
    try:
        oi = m.get_contract_stats(s, interval="1h", limit=999)
    except Exception:
        oi = []
    conds = m.neuro_compute_conditions(h1, h4, fr, None if s == "BTC_USDT" else btc, d1, oi,
                                       None if s == "ETH_USDT" else eth)
    rows = []
    for i in range(1, len(h1) - H - 1, STEP):
        b = h1[i]
        if b["time"] < start or not conds[i]:
            continue
        cl, e = b["close"], h1[i + 1]["open"]
        if cl <= 0 or e <= 0:
            continue
        pumped = max(x["high"] for x in h1[i + 1:i + 1 + H]) >= cl * (1 + pump)
        tp, sl = e * (1 + pump), e * (1 - STOP)
        px = h1[i + H]["close"]
        for j in range(i + 1, i + 1 + H):
            x = h1[j]
            if x["low"] <= sl:
                px = sl
                break
            if x["high"] >= tp:
                px = tp
                break
        items = tuple(sorted((k, str(v)) for k, v in conds[i].items() if v is not None))
        rows.append((b["time"], items, pumped, px / e - 1 - FEE))
    return rows


def evaluate(coins, pair_keys):
    """-> {cell: [(time, pumped, trade, excess)]}, cell = (k, v) or (k1, v1, k2, v2); 24h cooldown per coin"""
    res = {}
    for rows in coins:
        if not rows:
            continue
        mean_tr = sum(r[3] for r in rows) / len(rows)
        last = {}
        for t, items, pumped, tr in rows:
            rec = (t, pumped, tr, tr - mean_tr)
            cells = list(items)
            if pair_keys:
                sel = [kv for kv in items if kv[0] in pair_keys]
                for a in range(len(sel)):
                    for b in range(a + 1, len(sel)):
                        cells.append(sel[a] + sel[b])
            for cell in cells:
                lt = last.get(cell)
                if lt is not None and t - lt < COOLDOWN:
                    continue
                last[cell] = t
                res.setdefault(cell, []).append(rec)
    return res


def day_t(rows):
    d = {}
    for r in rows:
        d.setdefault(r[0] // 86400, []).append(r[3])
    xs = [sum(v) / len(v) for v in d.values()]
    n = len(xs)
    if n < 10:
        return None
    mu = sum(xs) / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in xs) / (n - 1))
    return mu / (sd / math.sqrt(n)) if sd > 0 else None


def stats(rows, base):
    rows = sorted(rows)
    n, half = len(rows), len(rows) // 2
    rate = sum(1 for r in rows if r[1]) / n
    return {"n": n, "rate": rate, "lift": rate / base if base else 0, "tr": sum(r[2] for r in rows) / n,
            "ex": sum(r[3] for r in rows) / n, "t": day_t(rows),
            "h1": sum(r[3] for r in rows[:half]) / max(half, 1), "h2": sum(r[3] for r in rows[half:]) / max(n - half, 1)}


def fmt(cell, s):
    td = "—" if s["t"] is None else f"{s['t']:+.2f}"
    return (f"  {cname(cell)}\n      сигналов {s['n']} · памп в {s['rate'] * 100:.1f}% (x{s['lift']:.1f} к обычному) · "
            f"сделка {s['tr'] * 100:+.2f}% · превыш. {s['ex'] * 100:+.2f}% · t={td} · половины "
            f"{s['h1'] * 100:+.2f}/{s['h2'] * 100:+.2f}%")


def load(m, syms, btc, eth, warm, start, now, pump, label):
    out, t0 = [], time.time()
    for k, s in enumerate(syms, 1):
        try:
            out.append(coin_rows(m, s, btc, eth, warm, start, now, pump))
        except Exception as e:
            print(f"  {s}: {e}")
        print(f"  {label}: {k}/{len(syms)} ({time.time() - t0:.0f} с)")
    return out


def main():
    global LABELS
    args = [a for i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith("--") and sys.argv[i - 1] not in ("--skip", "--pump")]
    skip = int(sys.argv[sys.argv.index("--skip") + 1]) if "--skip" in sys.argv else 10
    pump = float(sys.argv[sys.argv.index("--pump") + 1]) / 100 if "--pump" in sys.argv else 0.15
    n_coins = int(args[0]) if args else 60
    spec = importlib.util.spec_from_file_location("vp", MAIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    LABELS = getattr(m, "NEURO_COND_LABELS", {})
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
    syms = [s for s, _ in sorted(vols.items(), key=lambda kv: -kv[1])
            if s not in ("BTC_USDT", "ETH_USDT")][skip:skip + n_coins]
    disc, conf = syms[0::2], syms[1::2]
    now = int(time.time())
    start = now - DAYS * 86400
    warm = start - 60 * 86400
    t0 = time.time()
    btc = m.get_candles_range("BTC_USDT", "1h", warm, now) or []
    eth = m.get_candles_range("ETH_USDT", "1h", warm, now) or []
    say(f"монеты с {skip + 1}-й по {skip + len(syms)}-ю: поиск {len(disc)}, подтверждение {len(conf)} · {DAYS} дн. · "
        f"памп = +{pump * 100:g}% за {H}ч · сделка: тейк +{pump * 100:g}%, стоп −{STOP * 100:g}%, выход через {H}ч")

    A = load(m, disc, btc, eth, warm, start, now, pump, "поиск")
    allA = [r for rows in A for r in rows]
    if not allA:
        sys.exit("нет данных")
    base = sum(1 for r in allA if r[2]) / len(allA)
    say(f"\nчасов: {len(allA)} · памп после случайного часа: {base * 100:.2f}% · средняя сделка: "
        f"{sum(r[3] for r in allA) / len(allA) * 100:+.2f}%")

    # 1. profile: how much more often a value is seen right before a pump
    tot, pre = {}, {}
    n_p = 0
    for r in allA:
        for kv in r[1]:
            tot[kv] = tot.get(kv, 0) + 1
        if r[2]:
            n_p += 1
            for kv in r[1]:
                pre[kv] = pre.get(kv, 0) + 1
    prof = []
    for kv, c in tot.items():
        if c >= 500 and n_p:
            share_all, share_pre = c / len(allA), pre.get(kv, 0) / n_p
            prof.append((share_pre / share_all if share_all else 0, kv, share_pre, share_all))
    prof.sort(reverse=True)
    say(f"\n=== 1. ПРОФИЛЬ: что чаще бывает перед пампом ({n_p} часов перед пампом) ===")
    say("  (без проверки значимости: часы одного пампа идут подряд, так что x1.3-1.5 бывает и случайно — решает часть 2)")
    for lift, kv, sp, sa in prof[:15]:
        say(f"  {LABELS.get(kv[0], kv[0])} = {kv[1]}: перед пампом {sp * 100:.0f}% часов, обычно {sa * 100:.0f}% (x{lift:.1f})")
    say("  реже всего перед пампом:")
    for lift, kv, sp, sa in prof[-5:]:
        say(f"  {LABELS.get(kv[0], kv[0])} = {kv[1]}: перед пампом {sp * 100:.0f}%, обычно {sa * 100:.0f}% (x{lift:.1f})")

    # 2. search: single values first, then pairs among the best keys
    single = evaluate(A, None)
    tests = []
    for cell, rows in single.items():
        if len(rows) >= MIN_SIG:
            tests.append((cell, stats(rows, base)))
    best_key = {}
    for cell, s in tests:
        best_key[cell[0]] = max(best_key.get(cell[0], -99), s["t"] or -99)
    pair_keys = set(k for k, _ in sorted(best_key.items(), key=lambda kv: -kv[1])[:TOP_KEYS])
    paired = evaluate(A, pair_keys)
    for cell, rows in paired.items():
        if len(cell) == 4 and len(rows) >= MIN_SIG:
            tests.append((cell, stats(rows, base)))
    scored = [(c, s, 0.5 * math.erfc(s["t"] / math.sqrt(2)) if s["t"] is not None else 1.0) for c, s in tests]
    scored.sort(key=lambda z: z[2])
    mt = len(scored)
    cut = 0
    for r_, (_, _, p) in enumerate(scored, 1):
        if p <= FDR_Q * r_ / mt:
            cut = r_
    chosen = [(c, s) for c, s, p in scored[:cut] if s["ex"] > 0 and s["tr"] > 0 and s["h1"] > 0 and s["h2"] > 0]
    say(f"\n=== 2. ПОИСК: {mt} состояний (значения {len(single)} + пары среди {len(pair_keys)} условий), лучшие 12 по t ===")
    for c, s, p in sorted(scored, key=lambda z: -(z[1]["t"] or -99))[:12]:
        say(fmt(c, s))
    say(f"\nпрошли отбор (BH {int(FDR_Q * 100)}% на {mt} проверок, сделка в плюсе, обе половины): {len(chosen)}")
    if not chosen:
        say("ИТОГ: по условиям Neuro предпамповое состояние не ловится сильнее случайности")
    else:
        for c, s in chosen[:15]:
            say(fmt(c, s))
        say(f"\n=== 3. ПОДТВЕРЖДЕНИЕ на других {len(conf)} монетах ===")
        B = load(m, conf, btc, eth, warm, start, now, pump, "подтверждение")
        allB = [r for rows in B for r in rows]
        base_b = sum(1 for r in allB if r[2]) / max(len(allB), 1)
        EB = evaluate(B, pair_keys)
        good = []
        for c, _ in chosen[:40]:
            rows = EB.get(c) or []
            if len(rows) < 30:
                say(f"  {cname(c)}: мало сигналов ({len(rows)})")
                continue
            s = stats(rows, base_b)
            ok = s["ex"] > 0 and (s["t"] or 0) >= CONFIRM_T and s["tr"] > 0
            say(fmt(c, s) + ("  ✓ ПОДТВЕРДИЛОСЬ" if ok else ""))
            if ok:
                good.append(c)
        say(f"\nИТОГ: {'рабочие — ' + '; '.join(cname(c) for c in good) if good else 'на других монетах не подтвердилось ни одно'}")
    say(f"время: {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "neuro_pump_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: neuro_pump_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
