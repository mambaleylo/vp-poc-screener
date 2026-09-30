#!/usr/bin/env python3
"""S/R: куда в среднем идёт цена после отбоя и после пробоя зоны — на РЕАЛЬНЫХ данных Gate.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python snr_diag.py [число монет, по умолчанию 40]

Ничего не торгует. Зоны и события — те же, что у модуля S/R (snr_build_zones).
Для каждого события: вход по открытию следующей свечи, движение цены в сторону
сделки через 1, 3, 6, 12, 24, 42 свечи — в % и в ATR, с поправкой на общий
дрейф рынка (то же направление у случайных свечей). Плюс средний максимальный
ход в плюс (MFE) и в минус (MAE) за 42 свечи.

Как читать: если движение в сторону сделки около нуля на всех горизонтах — у
входа нет направления, и никакой стоп/тейк это не исправит (они меняют только
форму результата, не среднее). Если движение есть, но на каком-то отрезке —
значит, надо менять выход, а не вход. t считается по дням.
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

HORIZONS = (1, 3, 6, 12, 24, 42)
TFS = ("4h", "1d")
PIVOTS = (10, 20)
MIN_STRENGTH = 2
OUT = []


def say(s=""):
    print(s)
    OUT.append(s)


def events(m, candles, atr, pivot, mode):
    """(bar index, direction) of the S/R module's own events."""
    out = []
    for z in m.snr_build_zones(candles, atr, pivot):
        if mode == "breakout":
            if z["break_idx"] is not None and 1 + len(z["retest_idxs"]) >= MIN_STRENGTH:
                out.append((z["break_idx"], 1 if z["type"] == "resistance" else -1))
            continue
        s = 1
        for r in z["retest_idxs"]:
            s += 1
            if z["break_idx"] is not None and r >= z["break_idx"]:
                continue
            if s >= MIN_STRENGTH:
                out.append((r, 1 if z["type"] == "support" else -1))
    return sorted(out)


def day_t(pairs):
    """pairs: (day, value) -> t of the mean over per-day averages"""
    d = {}
    for day, v in pairs:
        d.setdefault(day, []).append(v)
    xs = [sum(v) / len(v) for v in d.values()]
    n = len(xs)
    if n < 3:
        return None
    mu = sum(xs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (n - 1))
    return mu / (sd / math.sqrt(n)) if sd > 0 else None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n_coins = int(args[0]) if args else 40
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
    syms = [s for s, _ in sorted(vols.items(), key=lambda kv: -kv[1])[:n_coins]]
    now = int(time.time())
    t0 = time.time()
    say(f"монет: {len(syms)} · ТФ {', '.join(TFS)} · пивот {PIVOTS} · сила >= {MIN_STRENGTH} · горизонты {HORIZONS} свечей")
    data = {}
    for i, s in enumerate(syms, 1):
        for tf in TFS:
            try:
                cs = m.get_candles_range(s, tf, now - m.snr_history_days_for_tf(tf) * 86400, now) or []
                sec = m.INTERVAL_SECONDS.get(tf, 3600)
                cs = [c for c in cs if c["time"] + sec <= now]
                if len(cs) >= 200:
                    data[(s, tf)] = cs
            except Exception as e:
                print(f"  {s} {tf}: {e}")
        if i % 10 == 0:
            print(f"  ...{i}/{len(syms)} ({time.time() - t0:.0f} с)")

    for tf in TFS:
        # market drift per horizon (mean % move of every bar, entry at next open)
        drift = {h: [] for h in HORIZONS}
        for (s, t_), cs in data.items():
            if t_ != tf:
                continue
            for i in range(len(cs) - max(HORIZONS) - 1):
                e = cs[i + 1]["open"]
                for h in HORIZONS:
                    drift[h].append((cs[i + h]["close"] / e - 1) * 100)
        mdrift = {h: (sum(v) / len(v) if v else 0.0) for h, v in drift.items()}
        for mode, title in (("bounce", "ОТБОЙ"), ("breakout", "ПРОБОЙ")):
            rows = {h: [] for h in HORIZONS}     # (day, signed % adjusted, signed ATR)
            mfe, mae, nev, longs = [], [], 0, 0
            for (s, t_), cs in data.items():
                if t_ != tf:
                    continue
                atr = m.neuro_atr_series(cs, 14)
                seen = set()
                for pv in PIVOTS:
                    for idx, d in events(m, cs, atr, pv, mode):
                        if idx in seen or idx + max(HORIZONS) + 1 >= len(cs) or not atr[idx]:
                            continue
                        seen.add(idx)
                        nev += 1
                        longs += d > 0
                        e = cs[idx + 1]["open"]
                        day = cs[idx]["time"] // 86400
                        for h in HORIZONS:
                            mv = (cs[idx + h]["close"] / e - 1) * 100
                            rows[h].append((day, d * mv - d * mdrift[h], d * (cs[idx + h]["close"] - e) / atr[idx]))
                        path = cs[idx + 1:idx + 1 + max(HORIZONS)]
                        hi = max(c["high"] for c in path)
                        lo = min(c["low"] for c in path)
                        fav, adv = ((hi / e - 1), (1 - lo / e)) if d > 0 else ((1 - lo / e), (hi / e - 1))
                        mfe.append(fav * 100)
                        mae.append(adv * 100)
            say(f"\n=== {tf} · {title}: {nev} событий (лонгов {longs}) ===")
            if not nev:
                continue
            say("  свечей после входа | в сторону сделки, % (за вычетом дрейфа рынка) | в ATR | t по дням")
            for h in HORIZONS:
                r = rows[h]
                avg = sum(x[1] for x in r) / len(r)
                avg_atr = sum(x[2] for x in r) / len(r)
                t = day_t([(x[0], x[1]) for x in r])
                say(f"    {h:3d}: {avg:+.2f}% · {avg_atr:+.2f} ATR · t={t if t is None else round(t, 1)}")
            say(f"  за {max(HORIZONS)} свечей в среднем: ход в плюс {sum(mfe) / len(mfe):.1f}% · ход в минус {sum(mae) / len(mae):.1f}%")
    say("\nкомиссия за круг ~0.1%: движение в сторону сделки меньше неё — входу нечего предложить;")
    say("если оно растёт с горизонтом — держать дольше; если есть только на коротком — выходить раньше")
    say(f"\nвремя: {time.time() - t0:.0f} с")
    try:
        with open(os.path.join(os.getcwd(), "snr_diag_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(OUT) + "\n")
        print("отчёт сохранён: snr_diag_report.txt")
    except Exception as e:
        print(f"отчёт не сохранён: {e}")


if __name__ == "__main__":
    main()
