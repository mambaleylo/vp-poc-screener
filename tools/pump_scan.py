#!/usr/bin/env python3
"""Предпамповое состояние: что происходит перед резким ростом и можно ли это поймать заранее. РЕАЛЬНЫЕ данные Gate.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python pump_scan.py [число монет, по умолчанию 100] [--skip 10] [--pump 15]

По умолчанию монеты с 11-й по 110-ю по объёму (топ-10 почти не пампятся), часовые
свечи ~400 дней (те же, что у setup_scan — берутся из кэша).

ПАМП: в следующие 24 часа максимум цены выше закрытия текущего часа на 15% (--pump).

Признаки (только прошлое, в момент закрытия часа):
  объём 6ч к обычному · объём 24ч к предыдущим 24ч · сжатие волатильности
  (ATR14/ATR100) · ход цены за 24ч и 72ч · расстояние до максимума недели ·
  ширина диапазона за 24ч · ход BTC за 24ч (общий рынок)

1. ПРОФИЛЬ: на какую пятую часть (квинтиль) каждого признака приходятся начала
   пампов. Если везде ~20% — признак ничего не говорит.
2. ПОИСК (чётные монеты): состояния = квинтиль одного признака или пара квинтилей
   двух признаков (~700 состояний). Для каждого: как часто памп и сделка —
   вход на следующем часе, тейк +15%, стоп −5%, выход через 24ч, комиссия 0.1%.
   Сигнал состояния на монете не чаще раза в 24ч. Сравнение со средней сделкой
   той же монеты в любой час. t по дням, поправка на число проверок (BH 10%),
   плюс в обеих половинах периода.
3. ПОДТВЕРЖДЕНИЕ (нечётные монеты): те же состояния с порогами квинтилей,
   посчитанными на поиске. Рабочее = превышение > 0, t >= 2, сделка в плюсе.
"""
import importlib.util
import math
import os
from collections import deque
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = next((p for p in (os.path.join(HERE, "vp_poc_screener.py"), os.path.join(HERE, "..", "vp_poc_screener.py"),
                         os.path.join(os.getcwd(), "vp_poc_screener.py")) if os.path.exists(p)), None)
if MAIN is None:
    sys.exit("не найден vp_poc_screener.py — положите этот скрипт в ту же папку")

DAYS = 400
H = 24            # look-ahead hours
STOP = 0.05
FEE = 0.001
COOLDOWN = 24
STEP = 2          # every 2nd hour is evaluated (speed); signals still 24h apart
FDR_Q = 0.10
CONFIRM_T = 2.0
MIN_SIG = 60
OUT = []
FEATS = [("vol6", "объём 6ч к обычному"), ("vol24", "объём 24ч к пред. 24ч"), ("squeeze", "ATR14/ATR100 (сжатие)"),
         ("ret24", "ход цены 24ч"), ("ret72", "ход цены 72ч"), ("dist_hi", "до максимума недели"),
         ("range24", "диапазон 24ч"), ("btc24", "ход BTC 24ч")]
FN = [f for f, _ in FEATS]


def say(s=""):
    print(s)
    OUT.append(s)


def atr(c, n):
    out, prev = [None] * len(c), None
    for i in range(1, len(c)):
        tr = max(c[i]["high"] - c[i]["low"], abs(c[i]["high"] - c[i - 1]["close"]), abs(c[i]["low"] - c[i - 1]["close"]))
        prev = tr if prev is None else (prev * (n - 1) + tr) / n
        out[i] = prev if i >= n else None
    return out


def series_rows(c, btc_ret, pump):
    """-> list of (time, features tuple, pumped bool, trade return) for every usable hour"""
    n = len(c)
    if n < 400:
        return []
    V = [b.get("volume") or 0.0 for b in c]
    cs = [0.0]
    for v in V:
        cs.append(cs[-1] + v)
    vsum = lambda a, b: cs[b] - cs[a]   # sum V[a:b]
    a14, a100 = atr(c, 14), atr(c, 100)
    # rolling 168-bar max of highs (monotonic deque) — a plain max() per bar is too slow on a phone
    hi168s, dq = [None] * n, deque()
    for i in range(n):
        while dq and c[dq[-1]]["high"] <= c[i]["high"]:
            dq.pop()
        dq.append(i)
        if dq[0] <= i - 168:
            dq.popleft()
        hi168s[i] = c[dq[0]]["high"]
    rows = []
    for i in range(200, n - H - 1, STEP):
        b = c[i]
        cl = b["close"]
        if cl <= 0 or not a14[i] or not a100[i]:
            continue
        base6 = vsum(i - 173, i - 5) / 28.0          # avg 6h volume over the prior week
        prev24 = vsum(i - 47, i - 23)
        if base6 <= 0 or prev24 <= 0:
            continue
        hi168 = hi168s[i]
        hi24 = max(x["high"] for x in c[i - 23:i + 1])
        lo24 = min(x["low"] for x in c[i - 23:i + 1])
        br = btc_ret.get(b["time"])
        f = (vsum(i - 5, i + 1) / base6, vsum(i - 23, i + 1) / prev24, a14[i] / a100[i],
             cl / c[i - 24]["close"] - 1, cl / c[i - 72]["close"] - 1, cl / hi168 - 1,
             (hi24 - lo24) / cl, br if br is not None else 0.0)
        # outcome
        e = c[i + 1]["open"]
        tp, sl = e * (1 + pump), e * (1 - STOP)
        pumped = max(x["high"] for x in c[i + 1:i + 1 + H]) >= cl * (1 + pump)
        px = c[i + H]["close"]
        for j in range(i + 1, i + 1 + H):
            x = c[j]
            if x["low"] <= sl:
                px = sl
                break
            if x["high"] >= tp:
                px = tp
                break
        rows.append((b["time"], f, pumped, px / e - 1 - FEE))
    return rows


def quintile_edges(all_rows):
    edges = []
    for k in range(len(FN)):
        xs = sorted(r[1][k] for r in all_rows[::7])
        edges.append([xs[int(len(xs) * q / 5)] for q in (1, 2, 3, 4)])
    return edges


def qof(v, e):
    return sum(1 for x in e if v >= x)


def cells_of(qs):
    out = [(k, q) for k, q in enumerate(qs)]
    for a in range(len(qs)):
        for b in range(a + 1, len(qs)):
            out.append((a, qs[a], b, qs[b]))
    return out


def cell_name(cell):
    lab = lambda k, q: f"{FEATS[k][1]} Q{q + 1}"
    return lab(cell[0], cell[1]) if len(cell) == 2 else f"{lab(cell[0], cell[1])} + {lab(cell[2], cell[3])}"


def evaluate(coin_rows, edges):
    """-> {cell: [(time, pumped, trade, excess)]} with a 24h cooldown per coin and cell"""
    res = {}
    for rows in coin_rows:
        if not rows:
            continue
        mean_tr = sum(r[3] for r in rows) / len(rows)
        last = {}
        for t, f, pumped, tr in rows:
            qs = [qof(f[k], edges[k]) for k in range(len(FN))]
            for cell in cells_of(qs):
                lt = last.get(cell)
                if lt is not None and t - lt < COOLDOWN * 3600:
                    continue
                last[cell] = t
                res.setdefault(cell, []).append((t, pumped, tr, tr - mean_tr))
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


def stats(rows, base_rate):
    rows = sorted(rows)
    n = len(rows)
    half = n // 2
    rate = sum(1 for r in rows if r[1]) / n
    return {"n": n, "rate": rate, "lift": rate / base_rate if base_rate else 0, "tr": sum(r[2] for r in rows) / n,
            "ex": sum(r[3] for r in rows) / n, "t": day_t(rows),
            "h1": sum(r[3] for r in rows[:half]) / max(half, 1), "h2": sum(r[3] for r in rows[half:]) / max(n - half, 1)}


def fmt(cell, s):
    td = "—" if s["t"] is None else f"{s['t']:+.2f}"
    return (f"  {cell_name(cell)}\n      сигналов {s['n']} · памп в {s['rate'] * 100:.1f}% (в {s['lift']:.1f} раза чаще обычного) · "
            f"сделка {s['tr'] * 100:+.2f}% · превыш. {s['ex'] * 100:+.2f}% · t={td} · половины "
            f"{s['h1'] * 100:+.2f}/{s['h2'] * 100:+.2f}%")


def load(m, syms, now, btc_ret, pump, label):
    out = []
    t0 = time.time()
    for k, s in enumerate(syms, 1):
        try:
            cs = m.get_candles_range(s, "1h", now - DAYS * 86400, now) or []
            cs = [b for b in cs if b["time"] + 3600 <= now]
            out.append(series_rows(cs, btc_ret, pump))
        except Exception as e:
            print(f"  {s}: {e}")
        if k % 10 == 0:
            print(f"  {label}: {k}/{len(syms)} ({time.time() - t0:.0f} с)")
    return out


def main():
    args = [a for i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith("--") and sys.argv[i - 1] not in ("--skip", "--pump")]
    skip = int(sys.argv[sys.argv.index("--skip") + 1]) if "--skip" in sys.argv else 10
    pump = float(sys.argv[sys.argv.index("--pump") + 1]) / 100 if "--pump" in sys.argv else 0.15
    n_coins = int(args[0]) if args else 100
    spec = importlib.util.spec_from_file_location("vp", MAIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
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
    syms = [s for s, _ in sorted(vols.items(), key=lambda kv: -kv[1]) if s != "BTC_USDT"][skip:skip + n_coins]
    disc, conf = syms[0::2], syms[1::2]
    now = int(time.time())
    t0 = time.time()
    btc = m.get_candles_range("BTC_USDT", "1h", now - DAYS * 86400, now) or []
    btc_ret = {btc[i]["time"]: btc[i]["close"] / btc[i - 24]["close"] - 1 for i in range(24, len(btc))}
    say(f"монеты с {skip + 1}-й по {skip + len(syms)}-ю: поиск {len(disc)}, подтверждение {len(conf)} · "
        f"памп = +{pump * 100:g}% за {H}ч · сделка: тейк +{pump * 100:g}%, стоп −{STOP * 100:g}%, выход через {H}ч")

    A = load(m, disc, now, btc_ret, pump, "поиск")
    allA = [r for rows in A for r in rows]
    if not allA:
        sys.exit("нет данных")
    base = sum(1 for r in allA if r[2]) / len(allA)
    base_tr = sum(r[3] for r in allA) / len(allA)
    say(f"\nчасов: {len(allA)} · памп после случайного часа: {base * 100:.2f}% · средняя сделка в случайный час: "
        f"{base_tr * 100:+.2f}%")
    edges = quintile_edges(allA)

    # 1. profile: every hour followed by a pump (not just the "first" one — the
    # first qualifying hour is biased to a local low, a fake "drop before pump")
    starts = [r for r in allA if r[2]]
    say(f"\n=== 1. ПРОФИЛЬ ПЕРЕД ПАМПОМ ({len(starts)} часов перед пампом) — доля по квинтилям, без связи было бы 20/20/20/20/20 ===")
    for k, (f, title) in enumerate(FEATS):
        cnt = [0] * 5
        for r in starts:
            cnt[qof(r[1][k], edges[k])] += 1
        tot = max(sum(cnt), 1)
        sh = " / ".join(f"{c * 100 / tot:.0f}" for c in cnt)
        med = sorted(r[1][k] for r in starts)[len(starts) // 2] if starts else 0
        med_all = sorted(r[1][k] for r in allA[::7])[len(allA[::7]) // 2]
        say(f"  {title:<24} Q1..Q5: {sh}%   (медиана перед пампом {med:+.3g}, обычно {med_all:+.3g})")

    # 2. search
    EA = evaluate(A, edges)
    tests = []
    for cell, rows in EA.items():
        if len(rows) >= MIN_SIG:
            s = stats(rows, base)
            p = 0.5 * math.erfc(s["t"] / math.sqrt(2)) if s["t"] is not None else 1.0
            tests.append((cell, s, p))
    tests.sort(key=lambda z: z[2])
    mt = len(tests)
    cut = 0
    for r_, (_, _, p) in enumerate(tests, 1):
        if p <= FDR_Q * r_ / mt:
            cut = r_
    chosen = [(c, s) for c, s, p in tests[:cut] if s["ex"] > 0 and s["tr"] > 0 and s["h1"] > 0 and s["h2"] > 0]
    say(f"\n=== 2. ПОИСК: {mt} состояний, лучшие 12 по t ===")
    for c, s, p in sorted(tests, key=lambda z: -(z[1]["t"] or -99))[:12]:
        say(fmt(c, s))
    say(f"\nпрошли отбор (BH {int(FDR_Q * 100)}% на {mt} проверок, сделка в плюсе, обе половины): {len(chosen)}")
    if not chosen:
        say("ИТОГ: предпамповое состояние по этим признакам не ловится сильнее случайности")
    else:
        for c, s in chosen[:15]:
            say(fmt(c, s))
        say(f"\n=== 3. ПОДТВЕРЖДЕНИЕ на других {len(conf)} монетах ===")
        B = load(m, conf, now, btc_ret, pump, "подтверждение")
        allB = [r for rows in B for r in rows]
        base_b = sum(1 for r in allB if r[2]) / max(len(allB), 1)
        EB = evaluate(B, edges)
        good = []
        for c, _ in chosen:
            rows = EB.get(c) or []
            if len(rows) < 30:
                say(f"  {cell_name(c)}: мало сигналов ({len(rows)})")
                continue
            s = stats(rows, base_b)
            ok = s["ex"] > 0 and (s["t"] or 0) >= CONFIRM_T and s["tr"] > 0
            say(fmt(c, s) + ("  ✓ ПОДТВЕРДИЛОСЬ" if ok else ""))
            if ok:
                good.append(c)
        say(f"\nИТОГ: {'рабочие — ' + '; '.join(cell_name(c) for c in good) if good else 'на других монетах не подтвердилось ни одно'}")
    say(f"время: {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "pump_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: pump_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
