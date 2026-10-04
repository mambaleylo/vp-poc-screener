#!/usr/bin/env python3
"""Отбой от EMA после закола на дневках, неделях и месяцах. РЕАЛЬНЫЕ данные Gate.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python ema_bounce.py [число монет, по умолчанию 100] [--skip 0]
    python ema_bounce.py 100 --skip 100 --check "1н,20,S,касание,*,2,0.5; 1д,12,L,закол,по тренду,2,1"

EMA: 9, 12, 20, 21, 26, 34, 50, 55, 89, 100, 144, 200 (по закрытиям ТФ).
Таймфреймы: 1д, 1н (с понедельника), 1м — недели и месяцы собираются из дневок.

СОБЫТИЕ (лонг от поддержки; шорт от сопротивления — зеркально):
  прошлая свеча закрылась ВЫШЕ EMA, текущая
   - «закол»: фитилём ушла ниже EMA (не глубже 1 ATR) и закрылась выше EMA;
   - «касание»: минимум в пределах 0.1 ATR над EMA, без пробоя, закрытие выше.
  Наклон EMA: по тренду (EMA растёт для лонга) или против.
ВХОД: открытие следующей свечи ТФ. ВЫХОД: тейк 1/2/3 ATR, стоп 0.5/1/1.5 ATR
(ATR этого ТФ), максимум 10 дней / 8 недель / 6 месяцев. Что задето первым —
по 4ч свечам (для дневок) и по дневкам (для недель/месяцев); оба в одной
свече — стоп. Комиссия 0.1% за круг. Результат в R.

ЧЕСТНОСТЬ: сравнение со случайным входом той же монеты/ТФ/стороны с тем же
стопом и тейком; t по дням (разброс не ниже, чем у случайных входов); поиск на
чётных монетах с поправкой BH 10%, плюс в обеих половинах; подтверждение на
нечётных: превышение > 0, t >= 2, сделка в плюсе.
"""
import bisect
import importlib.util
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = next((p for p in (os.path.join(HERE, "vp_poc_screener.py"), os.path.join(HERE, "..", "vp_poc_screener.py"),
                         os.path.join(os.getcwd(), "vp_poc_screener.py")) if os.path.exists(p)), None)
if MAIN is None:
    sys.exit("не найден vp_poc_screener.py — положите этот скрипт в ту же папку")

EMAS = (9, 12, 20, 21, 26, 34, 50, 55, 89, 100, 144, 200)
TPS = (1.0, 2.0, 3.0)
SLS = (0.5, 1.0, 1.5)
EXITS = [(tp, sl) for tp in TPS for sl in SLS]
LEVELS = sorted(set(TPS) | set(SLS))
TFS = {"1д": 10 * 86400, "1н": 56 * 86400, "1м": 182 * 86400}   # max holding time
PIERCE_MAX, TOUCH_TOL = 1.0, 0.1
FEE = 0.001
BASE_SAMPLES = 100
FDR_Q = 0.10
CONFIRM_T = 2.0
MIN_EV = 60
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def ema(xs, n):
    out, k, v = [None] * len(xs), 2 / (n + 1), None
    for i, x in enumerate(xs):
        v = x if v is None else v + k * (x - v)
        out[i] = v if i >= n else None
    return out


def atr(c, n=14):
    out, prev = [None] * len(c), None
    for i in range(1, len(c)):
        tr = max(c[i]["high"] - c[i]["low"], abs(c[i]["high"] - c[i - 1]["close"]), abs(c[i]["low"] - c[i - 1]["close"]))
        prev = tr if prev is None else (prev * (n - 1) + tr) / n
        out[i] = prev if i >= min(n, 6) else None
    return out


def group(d1, keyf):
    """aggregate daily bars into periods (complete ones only: the last is dropped); bar = period start..end"""
    out, cur, ck = [], None, None
    for c in d1:
        k = keyf(c["time"])
        if k != ck:
            if cur is not None:
                out.append(cur)
            cur, ck = dict(c, end=c["time"] + 86400), k
        else:
            cur["high"], cur["low"], cur["close"] = max(cur["high"], c["high"]), min(cur["low"], c["low"]), c["close"]
            cur["end"] = c["time"] + 86400
    return out   # the period still in progress (cur) is not included


def week_key(t):
    return (t // 86400 + 3) // 7   # weeks start on Monday (1970-01-01 was a Thursday)


def month_key(t):
    g = time.gmtime(t)
    return g.tm_year * 12 + g.tm_mon


def outcomes(path, times, start_t, side, a, hold):
    """R per EXIT entering at the first path bar starting at/after start_t"""
    k = bisect.bisect_left(times, start_t)
    if k >= len(path) or a <= 0:
        return None
    end_t = path[k]["time"] + hold
    if path[-1]["time"] < end_t - 86400:
        return None   # not enough future
    e = path[k]["open"]
    if e <= 0 or a < e * 0.001:   # flat market: ATR ~0 blows the fee in R up to -inf
        return None
    fav, adv = {}, {}
    fi = ai = 0
    nl = len(LEVELS)
    j = k
    last = e
    while j < len(path) and path[j]["time"] < end_t:
        b = path[j]
        up, dn = (b["high"] - e) / a, (e - b["low"]) / a
        f, ad = (up, dn) if side > 0 else (dn, up)
        while fi < nl and f >= LEVELS[fi]:
            fav[LEVELS[fi]] = j
            fi += 1
        while ai < nl and ad >= LEVELS[ai]:
            adv[LEVELS[ai]] = j
            ai += 1
        last = b["close"]
        j += 1
    rs = []
    for tp, sl in EXITS:
        th, sh = fav.get(tp), adv.get(sl)
        if sh is not None and (th is None or sh <= th):
            r = -1.0
        elif th is not None:
            r = tp / sl
        else:
            r = side * (last - e) / a / sl
        rs.append(r - FEE * e / (sl * a))
    return rs


def coin_events(m, s, now, rng):
    d1 = [c for c in (m.get_candles_range(s, "1d", now - 3000 * 86400, now) or []) if c["time"] + 86400 <= now]
    if len(d1) < 120:
        return [], {}
    h4 = [c for c in (m.get_candles_range(s, "4h", now - 1650 * 86400, now) or []) if c["time"] + 14400 <= now]
    d1t, h4t = [c["time"] for c in d1], [c["time"] for c in h4]
    series = {"1д": [dict(c, end=c["time"] + 86400) for c in d1], "1н": group(d1, week_key), "1м": group(d1, month_key)}
    events, base = [], {}
    for tf, bars in series.items():
        if len(bars) < 15:
            continue
        hold = TFS[tf]
        path, ptimes = (h4, h4t) if tf == "1д" else (d1, d1t)
        cl = [b["close"] for b in bars]
        A = atr(bars)
        for L in EMAS:
            if len(bars) < L + 5:
                continue
            E = ema(cl, L)
            busy = {1: -1, -1: -1}   # one open trade per coin/TF/EMA/side, as in live trading (overlap inflated t)
            for i in range(L + 2, len(bars)):
                if E[i] is None or E[i - 1] is None or E[i - 5] is None or not A[i - 1]:
                    continue
                b, pc, a = bars[i], cl[i - 1], A[i - 1]
                for side in (1, -1):
                    if b["end"] < busy[side]:
                        continue
                    if side > 0:
                        if not (pc > E[i - 1] and b["close"] > E[i]):
                            continue
                        depth = (E[i] - b["low"]) / a      # > 0: pierced below
                    else:
                        if not (pc < E[i - 1] and b["close"] < E[i]):
                            continue
                        depth = (b["high"] - E[i]) / a
                    if 0 < depth <= PIERCE_MAX:
                        kind = "закол"
                    elif -TOUCH_TOL <= depth <= 0:
                        kind = "касание"
                    else:
                        continue
                    if tf == "1д" and (not h4 or b["end"] < h4[0]["time"]):
                        continue
                    rs = outcomes(path, ptimes, b["end"], side, a, hold)
                    if rs is None:
                        continue
                    busy[side] = b["end"] + hold
                    slope = "по тренду" if (E[i] - E[i - 5]) * side > 0 else "против тренда"
                    events.append((b["time"], tf, L, side, kind, slope, rs))
        # baseline for this TF: random bar closes, both sides
        ok = [i for i in range(15, len(bars)) if A[i - 1] and not (tf == "1д" and (not h4 or bars[i]["end"] < h4[0]["time"]))]
        for side in (1, -1):
            samples = []
            for _ in range(BASE_SAMPLES if ok else 0):
                i = rng.choice(ok)
                rs = outcomes(path, ptimes, bars[i]["end"], side, A[i - 1], hold)
                if rs:
                    samples.append(rs)
            if len(samples) >= 15:
                mu = [sum(x[q] for x in samples) / len(samples) for q in range(len(EXITS))]
                sd = [math.sqrt(sum((x[q] - mu[q]) ** 2 for x in samples) / (len(samples) - 1)) for q in range(len(EXITS))]
                base[(tf, side)] = (mu, sd)
    return events, base


def collect(coins):
    """key = (tf, ema, side, kind or '*', slope or '*', exit) -> [(time, R, excess, base sd)]"""
    res = {}
    for events, base in coins:
        for t, tf, L, side, kind, slope, rs in events:
            bl = base.get((tf, side))
            if not bl:
                continue
            mu, sd = bl
            for kd in (kind, "*"):
                for sp in (slope, "*"):
                    for xi, r in enumerate(rs):
                        res.setdefault((tf, L, side, kd, sp, xi), []).append((t, r, r - mu[xi], sd[xi]))
    return res


def day_t(rows):
    d = {}
    for r in rows:
        d.setdefault(r[0] // 86400, []).append(r[2])
    xs = [sum(v) / len(v) for v in d.values()]
    n = len(xs)
    if n < 10:
        return None
    mu = sum(xs) / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in xs) / (n - 1))
    floor = sum(r[3] for r in rows) / len(rows) * math.sqrt(n / len(rows))
    sd = max(sd, floor)
    return mu / (sd / math.sqrt(n)) if sd > 0 else None


def stats(rows):
    rows = sorted(rows)
    n, half = len(rows), len(rows) // 2
    return {"n": n, "r": sum(r[1] for r in rows) / n, "ex": sum(r[2] for r in rows) / n, "t": day_t(rows),
            "wr": sum(1 for r in rows if r[1] > 0) / n * 100,
            "h1": sum(r[2] for r in rows[:half]) / max(half, 1), "h2": sum(r[2] for r in rows[half:]) / max(n - half, 1)}


def kname(key):
    tf, L, side, kind, slope, xi = key
    tp, sl = EXITS[xi]
    parts = [f"{tf} EMA{L}", "лонг от поддержки" if side > 0 else "шорт от сопротивления"]
    if kind != "*":
        parts.append(kind)
    if slope != "*":
        parts.append(slope)
    return " · ".join(parts) + f" · тейк {tp:g} / стоп {sl:g} ATR"


def fmt(key, s):
    td = "—" if s["t"] is None else f"{s['t']:+.2f}"
    return (f"  {kname(key)}\n      сделок {s['n']} · WR {s['wr']:.0f}% · {s['r']:+.3f}R · превыш. {s['ex']:+.3f}R · "
            f"t={td} · половины {s['h1']:+.3f}/{s['h2']:+.3f}")


def load(m, syms, now, rng, label):
    out, t0 = [], time.time()
    for k, s in enumerate(syms, 1):
        try:
            out.append(coin_events(m, s, now, rng))
        except Exception as e:
            print(f"  {s}: {e}")
        if k % 5 == 0 or k == len(syms):
            print(f"  {label}: {k}/{len(syms)} ({time.time() - t0:.0f} с)")
    return out


def check_mode(m, syms, skip, spec_txt):
    """Pre-chosen variants only, e.g. "1н,20,S,касание,*,2,0.5; 1д,12,L,закол,по тренду,2,1"
    (ТФ, EMA, L/S, закол|касание|*, по тренду|против тренда|*, тейк, стоп) — each is
    one hypothesis on coins the search never saw: no multiple-testing correction."""
    keys = []
    for part in spec_txt.split(";"):
        f = [x.strip() for x in part.split(",")]
        if len(f) != 7:
            continue
        tf, L, sd, kind, slope, tp, sl = f
        xi = EXITS.index((float(tp), float(sl)))
        keys.append((tf, int(L), 1 if sd.upper().startswith("L") else -1, kind, slope, xi))
    if not keys:
        sys.exit("не разобрал варианты: ТФ,EMA,L/S,вид,тренд,тейк,стоп через ;")
    now = int(time.time())
    t0 = time.time()
    say(f"ПРОВЕРКА {len(keys)} вариантов на монетах с {skip + 1}-й по {skip + len(syms)}-ю")
    R = collect(load(m, syms, now, random.Random(9), "проверка"))
    good = []
    for k in keys:
        rows = R.get(k) or []
        if len(rows) < 20:
            say(f"  {kname(k)}: мало сделок ({len(rows)})")
            continue
        s = stats(rows)
        ok = s["ex"] > 0 and (s["t"] or 0) >= CONFIRM_T and s["r"] > 0 and s["h1"] > 0 and s["h2"] > 0
        say(fmt(k, s) + ("  ✓ ПОДТВЕРДИЛОСЬ" if ok else ""))
        if ok:
            good.append(k)
    say(f"\nИТОГ: подтвердились {len(good)} из {len(keys)} (нужно: сделка в плюсе, превышение > 0, t >= {CONFIRM_T}, "
        f"плюс в обеих половинах) · время {time.time() - t0:.0f} с")
    with open(os.path.join(os.getcwd(), "ema_bounce_check.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")


def main():
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--skip"]
    skip = int(sys.argv[sys.argv.index("--skip") + 1]) if "--skip" in sys.argv else 0
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
    syms = [s for s, _ in sorted(vols.items(), key=lambda kv: -kv[1])][skip:skip + n_coins]
    disc, conf = syms[0::2], syms[1::2]
    if "--check" in sys.argv:
        return check_mode(m, syms, skip, sys.argv[sys.argv.index("--check") + 1])
    now = int(time.time())
    rng = random.Random(9)
    t0 = time.time()
    say(f"монеты с {skip + 1}-й по {skip + len(syms)}-ю: поиск {len(disc)}, подтверждение {len(conf)} · ТФ 1д/1н/1м · "
        f"EMA {EMAS} · закол <= {PIERCE_MAX:g} ATR, касание <= {TOUCH_TOL:g} ATR · тейк {TPS} / стоп {SLS} ATR")
    A = collect(load(m, disc, now, rng, "поиск"))

    say("\n=== ЛУЧШИЙ ВАРИАНТ ДЛЯ КАЖДОГО ТФ (закол, без фильтра тренда) — для ориентира ===")
    for tf in TFS:
        best = None
        for key, rows in A.items():
            if key[0] == tf and key[3] == "закол" and key[4] == "*" and len(rows) >= MIN_EV:
                s = stats(rows)
                if best is None or (s["t"] or -99) > (best[1]["t"] or -99):
                    best = (key, s)
        say(fmt(*best) if best else f"  {tf}: мало событий")

    tests = []
    for key, rows in A.items():
        if len(rows) >= MIN_EV:
            s = stats(rows)
            p = 0.5 * math.erfc(s["t"] / math.sqrt(2)) if s["t"] is not None else 1.0
            tests.append((key, s, p))
    tests.sort(key=lambda z: z[2])
    mt = len(tests)
    cut = 0
    for r_, (_, _, p) in enumerate(tests, 1):
        if p <= FDR_Q * r_ / mt:
            cut = r_
    chosen = [(k, s) for k, s, p in tests[:cut] if s["ex"] > 0 and s["r"] > 0 and s["h1"] > 0 and s["h2"] > 0]
    say(f"\n=== ПОИСК: {mt} проверок, лучшие 15 по t ===")
    for k, s, p in sorted(tests, key=lambda z: -(z[1]["t"] or -99))[:15]:
        say(fmt(k, s))
    say(f"\nпрошли отбор (BH {int(FDR_Q * 100)}% на {mt} проверок, сделка в плюсе, обе половины): {len(chosen)}")
    if not chosen:
        say("ИТОГ: отбой от EMA после закола не отличается от случайного входа сильнее, чем бывает случайно")
    else:
        chosen.sort(key=lambda z: -(z[1]["t"] or 0))
        for k, s in chosen[:20]:
            say(fmt(k, s))
        say(f"\n=== ПОДТВЕРЖДЕНИЕ на других {len(conf)} монетах ===")
        B = collect(load(m, conf, now, rng, "подтверждение"))
        good = []
        for k, _ in chosen[:40]:
            rows = B.get(k) or []
            if len(rows) < 30:
                say(f"  {kname(k)}: мало сделок ({len(rows)})")
                continue
            s = stats(rows)
            ok = s["ex"] > 0 and (s["t"] or 0) >= CONFIRM_T and s["r"] > 0
            say(fmt(k, s) + ("  ✓ ПОДТВЕРДИЛОСЬ" if ok else ""))
            if ok:
                good.append(k)
        say(f"\nИТОГ: {'рабочие — ' + '; '.join(kname(k) for k in good) if good else 'на других монетах не подтвердилось ни одно'}")
    say(f"время: {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "ema_bounce_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: ema_bounce_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
