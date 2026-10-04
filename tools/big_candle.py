#!/usr/bin/env python3
"""Коррекция после длинной 4ч свечи — с условиями Neuro, временем суток и сеткой стопов/тейков. РЕАЛЬНЫЕ данные Gate.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python big_candle.py [число монет, по умолчанию 60] [--skip 0]

СОБЫТИЕ: 4ч свеча (UTC 00/04/08/12/16/20), тело которой >= 1.5 / 2 / 3 ATR(14, 4ч)
предыдущих свечей. Свечи вверх и вниз — отдельно.
СДЕЛКА: ПРОТИВ свечи (на коррекцию), вход — открытие первого часа после
закрытия 4ч свечи. Тейк 0.5/1/1.5/2/3 ATR, стоп 0.5/1/1.5/2 ATR (20 пар),
максимум 48ч, если в одном часе задеты оба — стоп. Комиссия 0.1% за круг.
Результат в R (1R = стоп).

УСЛОВИЯ на момент закрытия свечи: все, что считает Neuro (RSI, тренды 4ч/1д,
фандинг, BTC/ETH, объём, ...), плюс время свечи (ночь 00-04 UTC, утро 04-08,
... ) и день недели. Каждое значение — отдельная проверка.

ЧЕСТНОСТЬ:
 - каждая сделка сравнивается со случайным входом той же монеты, в ту же
   сторону, с тем же стопом/тейком в ATR (превышение = R сделки − R случайного);
 - t по дням; поиск на чётных монетах с поправкой BH 10% на число проверок,
   плюс в обеих половинах периода, сама сделка в плюсе;
 - подтверждение на нечётных монетах: превышение > 0, t >= 2, сделка в плюсе.
"""
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

DAYS = 365
SIZES = (1.5, 2.0, 3.0)
TPS = (0.5, 1.0, 1.5, 2.0, 3.0)
SLS = (0.5, 1.0, 1.5, 2.0)
EXITS = [(tp, sl) for tp in TPS for sl in SLS]
LEVELS = sorted(set(TPS) | set(SLS))
HOLD = 48
FEE = 0.001
COOLDOWN = 12 * 3600
BASE_SAMPLES = 120
FDR_Q = 0.10
CONFIRM_T = 2.0
MIN_EV = 100
OUT = []
LABELS = {}
BLOCK = {0: "ночь 00-04", 1: "утро 04-08", 2: "день 08-12", 3: "день 12-16", 4: "вечер 16-20", 5: "вечер 20-24"}


def say(s=""):
    print(s)
    OUT.append(s)


def atr4(c4, n=14):
    out, prev = [None] * len(c4), None
    for i in range(1, len(c4)):
        tr = max(c4[i]["high"] - c4[i]["low"], abs(c4[i]["high"] - c4[i - 1]["close"]), abs(c4[i]["low"] - c4[i - 1]["close"]))
        prev = tr if prev is None else (prev * (n - 1) + tr) / n
        out[i] = prev if i >= n else None
    return out


def to4h(h1):
    """4h bars from 1h (UTC-aligned), with the index of their last 1h bar"""
    out, cur = [], None
    for k, c in enumerate(h1):
        key = c["time"] // 14400 * 14400
        if cur is None or cur["time"] != key:
            if cur is not None and cur["n"] == 4:
                out.append(cur)
            cur = {"time": key, "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"], "n": 1, "last": k}
        else:
            cur["high"], cur["low"], cur["close"] = max(cur["high"], c["high"]), min(cur["low"], c["low"]), c["close"]
            cur["n"] += 1
            cur["last"] = k
    if cur is not None and cur["n"] == 4:
        out.append(cur)
    return out


def outcomes(h1, k, side, atr):
    """R for every (tp, sl) in EXITS: enter at h1[k].open, levels in ATR; None if no full window"""
    if k + HOLD > len(h1) or atr <= 0:
        return None
    e = h1[k]["open"]
    if e <= 0 or atr < e * 0.001:   # flat market: ATR ~0 blows the fee in R up to -inf
        return None
    fav, adv = {}, {}
    fi = ai = 0
    nl = len(LEVELS)
    for j in range(HOLD):
        b = h1[k + j]
        up, dn = (b["high"] - e) / atr, (e - b["low"]) / atr
        f, a = (up, dn) if side > 0 else (dn, up)
        while fi < nl and f >= LEVELS[fi]:
            fav[LEVELS[fi]] = j
            fi += 1
        while ai < nl and a >= LEVELS[ai]:
            adv[LEVELS[ai]] = j
            ai += 1
    last = side * (h1[k + HOLD - 1]["close"] - e) / atr
    rs = []
    for tp, sl in EXITS:
        th, sh = fav.get(tp), adv.get(sl)
        if sh is not None and (th is None or sh <= th):
            r = -1.0
        elif th is not None:
            r = tp / sl
        else:
            r = last / sl
        rs.append(r - FEE * e / (sl * atr))
    return rs


def coin_events(m, s, btc, eth, warm, start, now, rng):
    """-> (events, baseline) ; event = (time, size_bucket, dir, cond items, [R per exit])"""
    h1 = [c for c in (m.get_candles_range(s, "1h", warm, now) or []) if c["time"] + 3600 <= now]
    if len(h1) < 24 * 120:
        return [], None
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
    c4 = to4h(h1)
    a4 = atr4(c4)
    events, last_t = [], None
    for q in range(15, len(c4)):
        b, atr = c4[q], a4[q - 1]
        if b["time"] < start or not atr:
            continue
        body = b["close"] - b["open"]
        size = abs(body) / atr
        if size < SIZES[0]:
            continue
        k = b["last"] + 1
        if last_t is not None and b["time"] - last_t < COOLDOWN:
            continue
        rs = outcomes(h1, k, -1 if body > 0 else 1, atr)
        if rs is None:
            continue
        last_t = b["time"]
        bucket = max(x for x in SIZES if size >= x)
        cd = conds[b["last"]] or {}
        items = [(kk, str(v)) for kk, v in cd.items() if v is not None]
        items.append(("candle_time", BLOCK[(b["time"] % 86400) // 14400]))
        items.append(("candle_dow", str(time.gmtime(b["time"]).tm_wday)))
        events.append((b["time"], bucket, "up" if body > 0 else "down", tuple(items), rs))
    # baseline: random 4h closes on this coin, same side, same exits (ATR-scaled)
    ok = [q for q in range(15, len(c4)) if a4[q - 1] and c4[q]["time"] >= start and c4[q]["last"] + 1 + HOLD <= len(h1)]
    base = {}
    if ok:
        for side in (1, -1):
            samples = []
            for _ in range(BASE_SAMPLES):
                q = rng.choice(ok)
                rs = outcomes(h1, c4[q]["last"] + 1, side, a4[q - 1])
                if rs:
                    samples.append(rs)
            if len(samples) < 20:
                base[side] = None
                continue
            mu = [sum(x[i] for x in samples) / len(samples) for i in range(len(EXITS))]
            sd = [math.sqrt(sum((x[i] - mu[i]) ** 2 for x in samples) / (len(samples) - 1)) for i in range(len(EXITS))]
            base[side] = (mu, sd)
    return events, base


def collect(events_by_coin):
    """-> {(size, dir, cond or None, exit_index): [(time, R, excess)]}; size bucket counts as '>= size'"""
    res = {}
    for events, base in events_by_coin:
        if not base:
            continue
        for t, bucket, d, items, rs in events:
            side = -1 if d == "up" else 1
            bl = base.get(side)
            if not bl:
                continue
            bmu, bsd = bl
            conds = [None] + list(items)
            for size in SIZES:
                if bucket < size:
                    continue
                for cd in conds:
                    for xi, r in enumerate(rs):
                        res.setdefault((size, d, cd, xi), []).append((t, r, r - bmu[xi], bsd[xi]))
    return res


def day_t(rows):
    """t by days; the spread is never taken below that of random entries with
    the same exit (a skewed 0.5/2 ATR bracket on few trades has rare -1R
    losses that may simply not have happened yet — that made t look huge)"""
    d = {}
    for r in rows:
        d.setdefault(r[0] // 86400, []).append(r[2])
    xs = [sum(v) / len(v) for v in d.values()]
    n = len(xs)
    if n < 10:
        return None
    mu = sum(xs) / n
    sd = math.sqrt(sum((v - mu) ** 2 for v in xs) / (n - 1))
    floor = sum(r[3] for r in rows) / len(rows) * math.sqrt(n / len(rows))   # random-entry spread of a day mean
    sd = max(sd, floor)
    return mu / (sd / math.sqrt(n)) if sd > 0 else None


def stats(rows):
    rows = sorted(rows)
    n, half = len(rows), len(rows) // 2
    return {"n": n, "r": sum(r[1] for r in rows) / n, "ex": sum(r[2] for r in rows) / n, "t": day_t(rows),
            "wr": sum(1 for r in rows if r[1] > 0) / n * 100,
            "h1": sum(r[2] for r in rows[:half]) / max(half, 1), "h2": sum(r[2] for r in rows[half:]) / max(n - half, 1)}


def kname(key):
    size, d, cd, xi = key
    tp, sl = EXITS[xi]
    what = f"свеча {'ВВЕРХ → шорт' if d == 'up' else 'ВНИЗ → лонг'} ≥{size:g} ATR"
    if cd:
        k, v = cd
        lab = {"candle_time": "время свечи", "candle_dow": "день недели"}.get(k, LABELS.get(k, k))
        what += f" + {lab} = {v}"
    return f"{what} · тейк {tp:g} / стоп {sl:g} ATR"


def fmt(key, s):
    td = "—" if s["t"] is None else f"{s['t']:+.2f}"
    return (f"  {kname(key)}\n      сделок {s['n']} · WR {s['wr']:.0f}% · {s['r']:+.3f}R · превыш. {s['ex']:+.3f}R · "
            f"t={td} · половины {s['h1']:+.3f}/{s['h2']:+.3f}")


def load(m, syms, btc, eth, warm, start, now, rng, label):
    out, t0 = [], time.time()
    for k, s in enumerate(syms, 1):
        try:
            out.append(coin_events(m, s, btc, eth, warm, start, now, rng))
        except Exception as e:
            print(f"  {s}: {e}")
        print(f"  {label}: {k}/{len(syms)} ({time.time() - t0:.0f} с)")
    return out


def main():
    global LABELS
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--skip"]
    skip = int(sys.argv[sys.argv.index("--skip") + 1]) if "--skip" in sys.argv else 0
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
    syms = [s for s, _ in sorted(vols.items(), key=lambda kv: -kv[1])][skip:skip + n_coins]
    disc, conf = syms[0::2], syms[1::2]
    now = int(time.time())
    start = now - DAYS * 86400
    warm = start - 60 * 86400
    rng = random.Random(5)
    t0 = time.time()
    btc = m.get_candles_range("BTC_USDT", "1h", warm, now) or []
    eth = m.get_candles_range("ETH_USDT", "1h", warm, now) or []
    say(f"монеты с {skip + 1}-й по {skip + len(syms)}-ю: поиск {len(disc)}, подтверждение {len(conf)} · {DAYS} дн. · "
        f"длинная 4ч свеча >= {SIZES} ATR · сделка против неё · тейк {TPS} / стоп {SLS} ATR, до {HOLD}ч")
    A = collect(load(m, disc, btc, eth, warm, start, now, rng, "поиск"))

    say("\n=== БЕЗ УСЛОВИЙ: средний R коррекции (лучший тейк/стоп для каждого размера) ===")
    for size in SIZES:
        for d in ("up", "down"):
            best = None
            for xi in range(len(EXITS)):
                rows = A.get((size, d, None, xi)) or []
                if len(rows) >= MIN_EV:
                    s = stats(rows)
                    if best is None or s["ex"] > best[1]["ex"]:
                        best = ((size, d, None, xi), s)
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
        say("ИТОГ: коррекция после длинной 4ч свечи не отличается от случайного входа сильнее, чем бывает случайно")
    else:
        chosen.sort(key=lambda z: -(z[1]["t"] or 0))
        for k, s in chosen[:20]:
            say(fmt(k, s))
        say(f"\n=== ПОДТВЕРЖДЕНИЕ на других {len(conf)} монетах ===")
        B = collect(load(m, conf, btc, eth, warm, start, now, rng, "подтверждение"))
        good = []
        for k, _ in chosen[:40]:
            rows = B.get(k) or []
            if len(rows) < 25:
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
        with open(os.path.join(os.getcwd(), "big_candle_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: big_candle_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
