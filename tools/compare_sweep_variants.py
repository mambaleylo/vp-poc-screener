#!/usr/bin/env python3
"""Sweep: какие изменения стратегии реально помогают — на РЕАЛЬНЫХ данных Gate.

Запуск (в Termux): положите файл рядом с vp_poc_screener.py и
    python compare_sweep_variants.py [МОНЕТА ...]

Без списка монет берутся 30 самых ликвидных фьючерсов Gate. Ничего не торгует
и не пишет в состояние сервера. Таймфрейм и глубина истории — как в
vp_poc_screener.py (LSW_INTERVAL / LSW_BACKTEST_DAYS, сейчас 4h / 730 дней), одна позиция на монету.

Для каждого варианта:
  - RR подбирается на первых 70% истории монеты (обучение), с комиссиями;
  - монета «отобрана», если на обучении ≥10 сделок и плюс после комиссий;
  - ТЕСТ = последние 30% отобранных монет вместе — честная цифра
    (на нём ничего не подбиралось). Смотрите на R/сделку и z теста.

Варианты (RR подбирается по монете на обучении; «@N» — RR = N у всех монет):
  base      — как сейчас: вход на закрытии свечи-свипа, стоп за фитилём +0.15%
  sl_atr    — стоп дальше: за фитилём + 0.5 ATR (меньше выбивает шумом)
  retest    — вход лимиткой на ретесте уровня в течение 3 свечей (лучше цена,
              тот же стоп — выше RR; часть сигналов не исполнится)
  tol_atr   — «равные» пики в пределах 0.25 ATR вместо фиксированных 0.12%
              (больше уровней и сделок на волатильных монетах)
  touches3  — только уровни с ≥3 касаниями
  sl_atr+retest — оба изменения вместе
"""
import importlib.util
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# vp_poc_screener.py next to this script, one folder up (repo layout), or in the current folder
MAIN = next((p for p in (os.path.join(HERE, "vp_poc_screener.py"), os.path.join(HERE, "..", "vp_poc_screener.py"),
                         os.path.join(os.getcwd(), "vp_poc_screener.py")) if os.path.exists(p)), None)
if MAIN is None:
    sys.exit("не найден vp_poc_screener.py — положите этот скрипт в ту же папку, где он лежит")

DAYS = None   # v0.99.397 — taken from vp_poc_screener.py (LSW_BACKTEST_DAYS), like the timeframe
TRAIN_FRAC = 0.7
MIN_TRAIN = 10
RETEST_BARS = 3
SL_ATR_EXTRA = 0.5
TOL_ATR = 0.25


def load():
    spec = importlib.util.spec_from_file_location("vp", MAIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.CALC_WORKERS = 0
    return m


def variant_signals(m, candles, atr, variant, rr):
    tol = m.LSW_EQUAL_TOLERANCE_PCT
    if "tol_atr" in variant:
        rel = sorted(a / c["close"] for a, c in zip(atr, candles) if a and c["close"])
        if rel:
            tol = TOL_ATR * rel[len(rel) // 2] * 100
    sigs = m.lsw_detect_signals(candles, rr=rr, equal_tolerance_pct=tol)
    out = []
    buf = m.LSW_SL_BUFFER_PCT / 100.0
    for s in sigs:
        if "touches3" in variant and s["level_touches"] < 3:
            continue
        s = dict(s)
        i = s["entry_idx"]
        extreme = s["sl"] / (1 + buf) if s["direction"] == "SHORT" else s["sl"] / (1 - buf)
        if "sl_atr" in variant and atr[i]:
            s["sl"] = extreme + SL_ATR_EXTRA * atr[i] if s["direction"] == "SHORT" else extreme - SL_ATR_EXTRA * atr[i]
        if "retest" in variant:
            lvl = s["level_price"]
            fill = None
            for k in range(i + 1, min(len(candles), i + 1 + RETEST_BARS)):
                c = candles[k]
                if s["direction"] == "SHORT" and c["high"] >= lvl:
                    fill = k
                    break
                if s["direction"] == "LONG" and c["low"] <= lvl:
                    fill = k
                    break
            if fill is None:
                continue
            s["entry"], s["entry_idx"], s["entry_time"] = lvl, fill, candles[fill]["time"]
            # the fill bar itself may already hit the stop: checked from the next bar by lsw_track_outcome,
            # so be conservative and count a same-bar stop touch as a loss
            c = candles[fill]
            if (s["direction"] == "SHORT" and c["high"] >= s["sl"]) or (s["direction"] == "LONG" and c["low"] <= s["sl"]):
                s["_same_bar_loss"] = True
        risk = abs(s["entry"] - s["sl"])
        if risk <= 0:
            continue
        s["tp"] = s["entry"] - risk * rr if s["direction"] == "SHORT" else s["entry"] + risk * rr
        s["rr"] = rr
        out.append(s)
    return out


def run_trades(m, candles, sigs):
    wait = m.LSW_MAX_WAIT_BARS * m.INTERVAL_SECONDS.get(m.LSW_INTERVAL, 3600)
    trades, busy = [], float("-inf")
    for s in sigs:
        if s["entry_time"] < busy:
            continue
        if s.get("_same_bar_loss"):
            res, ex = "LOSS", s["entry_time"]
        else:
            res, ex = m.lsw_track_outcome(candles, s)
        busy = ex if ex else s["entry_time"] + wait
        if res in ("WIN", "LOSS"):
            r = (s["rr"] if res == "WIN" else -1.0) - m.trade_fee_r(s["entry"], s["sl"])
            trades.append((s["entry_time"], res, r))
        else:
            # a real timeout (not "data ended"): closed at that bar's close, so
            # big RRs aren't flattered by dropping the trades that never got there
            k = s["entry_idx"] + m.LSW_MAX_WAIT_BARS
            if k < len(candles):
                risk = abs(s["entry"] - s["sl"])
                move = candles[k]["close"] - s["entry"] if s["direction"] == "LONG" else s["entry"] - candles[k]["close"]
                trades.append((s["entry_time"], "TIMEOUT", move / risk - m.trade_fee_r(s["entry"], s["sl"])))
    return trades


def coin_variant(m, candles, atr, variant):
    split_t = candles[int(len(candles) * TRAIN_FRAC) - 1]["time"]
    best = None
    # "name@4" = RR fixed at 4 for every coin (nothing chosen per coin)
    variant, _, fixed = variant.partition("@")
    for rr in ([float(fixed)] if fixed else m.LSW_RR_CANDIDATES):
        tr = [t for t in run_trades(m, candles, variant_signals(m, candles, atr, variant, rr)) if t[0] <= split_t]
        if len(tr) >= MIN_TRAIN:
            e = sum(t[2] for t in tr) / len(tr)
            if best is None or e > best[1]:
                best = (rr, e)
    if best is None:
        return None
    all_t = run_trades(m, candles, variant_signals(m, candles, atr, variant, best[0]))
    tr = [t for t in all_t if t[0] <= split_t]
    te = [t for t in all_t if t[0] > split_t]
    return {"rr": best[0], "train": tr, "test": te}


def stats(ts):
    if not ts:
        return "нет сделок"
    rs = [t[2] for t in ts]
    n = len(rs)
    mean = sum(rs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in rs) / (n - 1)) if n > 1 else 0
    z = mean / (sd / math.sqrt(n)) if sd else 0
    wr = 100 * sum(1 for t in ts if t[1] == "WIN") / n
    return f"n={n:4d} · WR {wr:4.1f}% · {mean:+.3f}R/сделку · итого {sum(rs):+.1f}R · z={z:+.2f}"


def main():
    m = load()
    symbols = sys.argv[1:]
    if not symbols:
        try:
            symbols = m.lsw_build_universe()[:30]
        except Exception as e:
            print("не удалось получить список монет:", e)
            sys.exit(1)
    # 4h run (v0.99.397): retest / tol_atr / touches3 were clearly worse or had no trades — dropped.
    # "@N" rows: RR fixed at N for all coins — shows which RR the strategy itself supports.
    variants = ["base", "sl_atr", "sl_atr+retest",
                "base@2", "base@3", "base@4", "base@5",
                "sl_atr@3", "sl_atr@4", "sl_atr@5"]
    now = time.time()
    data = {}
    tf, days = m.LSW_INTERVAL, DAYS or m.LSW_BACKTEST_DAYS
    print(f"загрузка {len(symbols)} монет, {tf}, {days} дней...")
    for sym in symbols:
        try:
            c = m.get_candles_range(sym, tf, now - days * 86400, now)
            if len(c) > 300:
                data[sym] = (c, m.neuro_atr_series(c, 14))
        except Exception as e:
            print(f"  {sym}: {e}")
    print(f"монет с данными: {len(data)}\n")
    for v in variants:
        picked, train_all, test_all, all_test = 0, [], [], []
        for sym, (c, atr) in data.items():
            r = coin_variant(m, c, atr, v)
            if not r:
                continue
            all_test += r["test"]
            e = sum(t[2] for t in r["train"]) / len(r["train"])
            if e > 0:
                picked += 1
                train_all += r["train"]
                test_all += r["test"]
        print(f"=== {v}" + (f"   (RR {v.split('@')[1]} у всех монет)" if "@" in v else "   (RR подбирается по монете)"))
        print(f"  отобрано по обучению: {picked} из {len(data)}")
        print(f"  обучение (отобранные): {stats(train_all)}")
        print(f"  ТЕСТ (отобранные):     {stats(test_all)}   ← честная цифра")
        print(f"  тест всех монет:       {stats(all_test)}\n")
    print("Хороший вариант: ТЕСТ (или тест всех монет для строк с @RR) в плюсе с z ≥ 2. Пришлите вывод — включу лучший.")


if __name__ == "__main__":
    main()
