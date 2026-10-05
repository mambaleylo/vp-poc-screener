#!/usr/bin/env python3
"""Пробой наклонных (трендовых) линий на 1ч / 4ч / 1д. РЕАЛЬНЫЕ данные Gate.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python trendline_scan.py [число монет, по умолчанию 80] [--skip 0]

НАКЛОНКА СОПРОТИВЛЕНИЯ: линия через два подтверждённых свинг-максимума (свинг =
максимум среди k свечей слева и справа, k = 3 или 5), второй ниже первого, между
ними не меньше 10 свечей и ни один максимум не выше линии. Линия известна только
после подтверждения второго свинга (никакого заглядывания вперёд).
ПРОБОЙ: первое закрытие выше линии (не позже 200 свечей после второго свинга) → ЛОНГ.
Наклонка поддержки (через свинг-минимумы, второй выше) — зеркально, пробой вниз → ШОРТ.
Варианты: k = 3 / 5 · касаний линии 2 / 3+ (свинги в пределах 0.25 ATR от линии) ·
объём на пробое > 1.5 среднего за 20 свечей или без условия.
ВЫХОД: вход на открытии следующей свечи, тейк 1/2/3 ATR, стоп 0.5/1/1.5 ATR, до 30
свечей. Что задето первым — по часовикам (для 1ч и 4ч) и по 4ч (для 1д); оба в одной
свече — стоп. Комиссия 0.1% за круг. Результат в R.

ЧЕСТНОСТЬ: одна сделка на монету/ТФ/вариант/сторону за раз; сравнение со случайным
входом той же монеты/ТФ/стороны с тем же стопом и тейком; t по дням (разброс не
ниже, чем у случайных входов); поиск на чётных монетах с поправкой BH 10%, плюс
в обеих половинах; подтверждение на нечётных: превышение > 0, t >= 2, сделка в плюсе.
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

TFS = {"1ч": (3600, 400), "4ч": (14400, 400), "1д": (86400, 1600)}   # (bar sec, days of history)
KS = (3, 5)
TPS = (1.0, 2.0, 3.0)
SLS = (0.5, 1.0, 1.5)
EXITS = [(tp, sl) for tp in TPS for sl in SLS]
LEVELS = sorted(set(TPS) | set(SLS))
HOLD_BARS = 30
MIN_GAP, MAX_AGE, TOUCH_TOL, MAX_ANCHORS = 10, 200, 0.25, 6
FEE = 0.001
BASE_SAMPLES = 100
FDR_Q = 0.10
CONFIRM_T = 2.0
MIN_EV = 60
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def atr(c, n=14):
    out, prev = [None] * len(c), None
    for i in range(1, len(c)):
        tr = max(c[i]["high"] - c[i]["low"], abs(c[i]["high"] - c[i - 1]["close"]), abs(c[i]["low"] - c[i - 1]["close"]))
        prev = tr if prev is None else (prev * (n - 1) + tr) / n
        out[i] = prev if i >= n else None
    return out


def pivots(vals, k, is_high):
    out = []
    for p in range(k, len(vals) - k):
        w = vals[p - k:p + k + 1]
        if vals[p] == (max(w) if is_high else min(w)):
            out.append(p)
    return out


def breakouts(c, A, k):
    """-> list of (bar index of the breakout close, side, touches). side +1 = resistance line broken up."""
    H = [b["high"] for b in c]
    L = [b["low"] for b in c]
    C = [b["close"] for b in c]
    found = {}
    for side, vals, is_high in ((1, H, True), (-1, L, False)):
        piv = pivots(vals, k, is_high)
        for bi, pb in enumerate(piv):
            known = pb + k   # the second swing is confirmed only here
            for pa in piv[max(0, bi - MAX_ANCHORS):bi][::-1]:
                if pb - pa < MIN_GAP:
                    continue
                if (is_high and vals[pa] <= vals[pb]) or (not is_high and vals[pa] >= vals[pb]):
                    continue
                slope = (vals[pb] - vals[pa]) / (pb - pa)
                line = lambda t: vals[pa] + slope * (t - pa)
                # nothing between the anchors may stick through the line
                if is_high and any(H[t] > line(t) + 1e-12 for t in range(pa + 1, pb)):
                    continue
                if not is_high and any(L[t] < line(t) - 1e-12 for t in range(pa + 1, pb)):
                    continue
                # first close through the line after the anchors
                brk = None
                for t in range(pb + 1, min(len(c), pb + MAX_AGE)):
                    if (is_high and C[t] > line(t)) or (not is_high and C[t] < line(t)):
                        brk = t
                        break
                if brk is None or brk < known or not A[brk]:
                    continue
                touches = sum(1 for p in piv if pa <= p < brk and abs(vals[p] - line(p)) <= TOUCH_TOL * A[brk])
                key = (brk, side)
                found[key] = max(found.get(key, 0), touches)
                break   # the longest valid line for this second swing
    return sorted((b, s, t) for (b, s), t in found.items())


def outcomes(path, times, start_t, side, a, hold):
    k = bisect.bisect_left(times, start_t)
    if k >= len(path):
        return None
    e = path[k]["open"]
    if e <= 0 or a < e * 0.001:
        return None
    end_t = path[k]["time"] + hold
    step = times[1] - times[0] if len(times) > 1 else 0
    if path[-1]["time"] + step < end_t:
        return None   # not enough future for the whole holding window
    fav, adv = {}, {}
    fi = ai = 0
    nl = len(LEVELS)
    j, last = k, e
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
    data = {}
    for tf, (sec, days) in TFS.items():
        api_tf = {"1ч": "1h", "4ч": "4h", "1д": "1d"}[tf]
        data[tf] = [b for b in (m.get_candles_range(s, api_tf, now - days * 86400, now) or []) if b["time"] + sec <= now]
    events, base = [], {}
    for tf, (sec, _) in TFS.items():
        c = data[tf]
        if len(c) < 150:
            continue
        path = data["1ч"] if tf in ("1ч", "4ч") else data["4ч"]
        if len(path) < 50:
            continue
        ptimes = [b["time"] for b in path]
        hold = HOLD_BARS * sec
        A = atr(c)
        V = [b.get("volume") or 0.0 for b in c]
        for k in KS:
            busy = {}
            for brk, side, touches in breakouts(c, A, k):
                b = c[brk]
                start_t = b["time"] + sec
                if start_t < ptimes[0]:
                    continue
                avgv = sum(V[max(0, brk - 20):brk]) / max(1, min(20, brk))
                volok = avgv > 0 and V[brk] > 1.5 * avgv
                tags = [("2+", True), ("3+", touches >= 3)]
                rs = None
                for tname, ok in tags:
                    if not ok:
                        continue
                    for vname, vok in (("*", True), ("объём", volok)):
                        if not vok:
                            continue
                        var = (tf, k, tname, vname, side)
                        if start_t < busy.get(var, 0):
                            continue
                        if rs is None:
                            rs = outcomes(path, ptimes, start_t, side, A[brk], hold)
                            if rs is None:
                                break
                        busy[var] = start_t + hold
                        events.append((b["time"], var, rs))
        ok = [i for i in range(15, len(c)) if A[i] and c[i]["time"] + sec >= ptimes[0]]
        for side in (1, -1):
            samples = []
            for _ in range(BASE_SAMPLES if ok else 0):
                i = rng.choice(ok)
                rs = outcomes(path, ptimes, c[i]["time"] + sec, side, A[i], hold)
                if rs:
                    samples.append(rs)
            if len(samples) >= 15:
                mu = [sum(x[q] for x in samples) / len(samples) for q in range(len(EXITS))]
                sd = [math.sqrt(sum((x[q] - mu[q]) ** 2 for x in samples) / (len(samples) - 1)) for q in range(len(EXITS))]
                base[(tf, side)] = (mu, sd)
    return events, base


def collect(coins):
    res = {}
    for events, base in coins:
        for t, var, rs in events:
            bl = base.get((var[0], var[4]))
            if not bl:
                continue
            mu, sd = bl
            for xi, r in enumerate(rs):
                res.setdefault(var + (xi,), []).append((t, r, r - mu[xi], sd[xi]))
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
    tf, k, touches, vol, side, xi = key
    tp, sl = EXITS[xi]
    what = "пробой наклонки сопротивления → лонг" if side > 0 else "пробой наклонки поддержки → шорт"
    return (f"{tf} · {what} · свинг {k} · касаний {touches}" + (" · с объёмом" if vol != "*" else "")
            + f" · тейк {tp:g} / стоп {sl:g} ATR")


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
    """'4ч,3,3+,объём,L,2,1; 1д,5,2+,*,S,3,1.5' (ТФ, свинг, касаний, объём|*, L/S, тейк, стоп)"""
    keys = []
    for part in spec_txt.split(";"):
        f = [x.strip() for x in part.split(",")]
        if len(f) != 7:
            continue
        tf, k, tch, vol, sd, tp, sl = f
        keys.append((tf, int(k), tch, vol, 1 if sd.upper().startswith("L") else -1, EXITS.index((float(tp), float(sl)))))
    if not keys:
        sys.exit("не разобрал варианты: ТФ,свинг,касаний,объём|*,L/S,тейк,стоп через ;")
    now, t0 = int(time.time()), time.time()
    say(f"ПРОВЕРКА {len(keys)} вариантов на монетах с {skip + 1}-й по {skip + len(syms)}-ю")
    R = collect(load(m, syms, now, random.Random(4), "проверка"))
    good = []
    for key in keys:
        rows = R.get(key) or []
        if len(rows) < 20:
            say(f"  {kname(key)}: мало сделок ({len(rows)})")
            continue
        s = stats(rows)
        ok = s["ex"] > 0 and (s["t"] or 0) >= CONFIRM_T and s["r"] > 0 and s["h1"] > 0 and s["h2"] > 0
        say(fmt(key, s) + ("  ✓ ПОДТВЕРДИЛОСЬ" if ok else ""))
        if ok:
            good.append(key)
    say(f"\nИТОГ: подтвердились {len(good)} из {len(keys)} · время {time.time() - t0:.0f} с")
    with open(os.path.join(os.getcwd(), "trendline_check.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT) + "\n")


def main():
    args = [a for i, a in enumerate(sys.argv[1:], 1)
            if not a.startswith("--") and sys.argv[i - 1] not in ("--skip", "--check")]
    skip = int(sys.argv[sys.argv.index("--skip") + 1]) if "--skip" in sys.argv else 0
    n_coins = int(args[0]) if args else 80
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
    if "--check" in sys.argv:
        return check_mode(m, syms, skip, sys.argv[sys.argv.index("--check") + 1])
    disc, conf = syms[0::2], syms[1::2]
    now, t0 = int(time.time()), time.time()
    rng = random.Random(4)
    say(f"монеты с {skip + 1}-й по {skip + len(syms)}-ю: поиск {len(disc)}, подтверждение {len(conf)} · ТФ 1ч/4ч/1д · "
        f"свинг {KS} · касаний 2+/3+ · тейк {TPS} / стоп {SLS} ATR · до {HOLD_BARS} свечей")
    A = collect(load(m, disc, now, rng, "поиск"))
    say("\n=== ЛУЧШЕЕ ДЛЯ КАЖДОГО ТФ И СТОРОНЫ (свинг 3, касаний 2+, без объёма) — для ориентира ===")
    for tf in TFS:
        for side in (1, -1):
            best = None
            for xi in range(len(EXITS)):
                rows = A.get((tf, 3, "2+", "*", side, xi)) or []
                if len(rows) >= MIN_EV:
                    s = stats(rows)
                    if best is None or s["ex"] > best[1]["ex"]:
                        best = ((tf, 3, "2+", "*", side, xi), s)
            if best:
                say(fmt(*best))
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
        say("ИТОГ: пробой наклонок не отличается от случайного входа сильнее, чем бывает случайно")
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
        with open(os.path.join(os.getcwd(), "trendline_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: trendline_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
