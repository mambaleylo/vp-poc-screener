#!/usr/bin/env python3
"""MSNR: старый расчёт против честного (v0.99.400) на РЕАЛЬНЫХ данных Gate.

Запуск (в Termux, из папки где лежат оба файла):
    python compare_msnr_honest.py <старый .py> <новый .py> [МОНЕТА ...]

Без списка монет берутся 25 монет из вселенной MSNR (широкая выборка — не
те, что отобрал старый расчёт). В конце — вердикт, как в программе.

Обе версии получают одинаковые данные (каждый ответ биржи скачивается один
раз, время "заморожено"). Ничего не торгует и не пишет в состояние сервера.

Что печатается по каждой монете:
  СТАРЫЙ  — то, что показывала таблица (все 40 дней, параметры подобраны
            на них же, без комиссий в R), и что эти же старые сделки дали
            на последних 30% истории (тот же период, что у нового «теста»),
            с комиссиями и проскальзыванием.
  НОВЫЙ   — вся история (с комиссиями) и ТЕСТ: последние 30%, параметры
            подбирались без них. Честная цифра — «ТЕСТ».
"""
import importlib.util
import sys
import time

import requests

DEFAULT_SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT"]


def install_shared_data_layer(frozen_now):
    real_get = requests.get
    cache = {}

    def cached_get(url, params=None, **kw):
        key = (url, tuple(sorted((params or {}).items())))
        if key not in cache:
            for attempt in range(4):
                try:
                    cache[key] = real_get(url, params=params, **kw)
                    break
                except requests.RequestException:
                    if attempt == 3:
                        raise
                    time.sleep(2 * (attempt + 1))
        return cache[key]

    requests.get = cached_get
    time.time = lambda: frozen_now


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def net_r(t, cost_frac):
    """WIN/LOSS в R с издержками, из цен сделки (одинаково для обеих версий)."""
    e, sl, tp = t["entry"], t["sl"], t["tp"]
    risk = abs(e - sl)
    if risk <= 0:
        return None
    cost = e * cost_frac
    if t["result"] == "WIN":
        return (abs(tp - e) - cost) / (risk + cost)
    return -1.0


def stats(ts, cost_frac):
    rs = [net_r(t, cost_frac) for t in ts if t.get("result") in ("WIN", "LOSS")]
    rs = [r for r in rs if r is not None]
    if not rs:
        return "нет сделок"
    w = sum(1 for r in rs if r > -1.0)
    return f"WR {100 * w / len(rs):.1f}% · {sum(rs) / len(rs):+.3f}R · n={len(rs)}"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    old_path, new_path = sys.argv[1], sys.argv[2]
    symbols = sys.argv[3:]
    install_shared_data_layer(int(time.time()))
    old = load(old_path, "vp_old")
    new = load(new_path, "vp_new")
    for m in (old, new):
        m.CALC_WORKERS = 0            # в этом процессе, без рабочих процессов
    if not symbols:
        # a broad sample of the MSNR universe, NOT the coins the old rule
        # picked (those were chosen on the same history — a biased sample)
        try:
            symbols = list(new.msnr_build_backtest_universe())[:25]
        except Exception as e:
            print("не удалось получить список монет:", e)
    symbols = symbols or DEFAULT_SYMBOLS
    cost = new.msnr_trade_cost_frac()
    print(f"монеты: {', '.join(symbols)}   (издержки на сделку {cost * 100:.2f}% цены)\n")
    tot = {"old_test": [], "new_test": []}
    new_ovs, new_res = {}, {}
    for sym in symbols:
        t0 = time.perf_counter()
        ob, ot, _ = old.msnr_optimize_symbol(sym)
        t1 = time.perf_counter()
        nb, nt, _ = new.msnr_optimize_symbol(sym)
        t2 = time.perf_counter()
        if ob.get("error") or nb.get("error"):
            print(f"=== {sym}: {ob.get('error') or nb.get('error')}\n")
            continue
        new_ovs[sym], new_res[sym] = nb, nt
        split = nb["oos_split_time"]
        old_test = [t for t in ot if t["time"] >= split]
        new_test = [t for t in nt if t["time"] >= split]
        tot["old_test"] += old_test
        tot["new_test"] += new_test
        print(f"=== {sym}   (старый {t1 - t0:.0f} с, новый {t2 - t1:.0f} с)")
        print(f"  СТАРЫЙ таблица:   WR {ob.get('winrate')}% · {ob.get('expectancy_r')}R · n={ob.get('trades')} · "
              f"$15→{ob.get('compound_final_balance')} · в топ: {'нет' if ob.get('stress_test_failed') else 'да'}")
        print(f"  СТАРЫЙ за период теста (с издержками): {stats(old_test, cost)}")
        print(f"  НОВЫЙ  вся история (с издержками): WR {nb.get('winrate')}% · {nb.get('expectancy_r')}R · "
              f"n={nb.get('trades')} · $15→{nb.get('compound_final_balance')}")
        print(f"  НОВЫЙ  обучение: n={nb.get('train_n')} · WR {nb.get('train_winrate')}% · {nb.get('train_expectancy_r')}R/сделку"
              f" · {'отобрана' if nb.get('picked') else 'не отобрана'}")
        print(f"  НОВЫЙ  ТЕСТ: {stats(new_test, cost)}   ← честная цифра\n")
    print("=== ВСЕ МОНЕТЫ ВМЕСТЕ, период теста, с издержками")
    print(f"  старый: {stats(tot['old_test'], cost)}")
    print(f"  новый:  {stats(tot['new_test'], cost)}")
    if hasattr(new, "msnr_pooled_verdict"):
        v = new.msnr_pooled_verdict(new_ovs, new_res)
        print(f"\n=== ВЕРДИКТ (как в программе): отобрано {v['picked']} монет, их тест: n={v['test_n']} · "
              f"{v['test_exp_r']}R/сделку · итого {v['test_sum_r']}R · z={v['test_z']}")
        print("  → " + ("торговать можно: тест подтвердил" if v["passed"]
                        else f"торговать нельзя: нужно n ≥ {v['min_test']} и z ≥ {v['z_needed']} с плюсом"))


if __name__ == "__main__":
    main()
