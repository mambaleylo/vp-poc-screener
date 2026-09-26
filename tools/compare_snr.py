#!/usr/bin/env python3
"""Сравнение бэктеста S/R: старая версия (один процесс) и новая (расчёт в
отдельных процессах на нескольких ядрах) — на РЕАЛЬНЫХ данных Gate.

Запуск (в Termux, из папки где лежат оба файла):
    python compare_snr.py <старый .py> <новый .py> [МОНЕТА ...]

Обе версии получают одинаковые данные: каждый ответ биржи скачивается один
раз и отдаётся обеим из памяти, время "заморожено". Монеты считаются
параллельно (8 потоков), как в самом приложении, чтобы было видно ускорение.
Ничего не торгует и не пишет в состояние сервера.
"""
import importlib.util
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

import requests  # noqa: E402

DEFAULT_SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT", "ADA_USDT"]


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


def canon(x):
    return json.dumps(x, sort_keys=True, default=str)


def run_all(mod, symbols):
    t0 = time.perf_counter()
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(mod.snr_optimize_symbol, symbols))
    return dict(zip(symbols, res)), time.perf_counter() - t0


def main(old_path, new_path, symbols):
    install_shared_data_layer(float(int(time.time()) // 3600 * 3600))
    old = load(old_path, "vp_old")
    new = load(new_path, "vp_new")
    for m in (old, new):   # the disk candle cache must not mix the two runs
        if hasattr(m, "CANDLE_CACHE_ENABLED"):
            m.CANDLE_CACHE_ENABLED = False
    print(f"старая: v{getattr(old, 'APP_VERSION', '?')}   новая: v{getattr(new, 'APP_VERSION', '?')} "
          f"(процессов для расчёта: {getattr(new, 'CALC_WORKERS', '?')})")
    print(f"монеты: {', '.join(symbols)}\n1) прогрев: скачиваю данные (старая версия)...")
    r_old, t_old = run_all(old, symbols)
    print(f"   старая: {t_old:.0f} с (включая скачивание)")
    r_old2, t_old2 = run_all(old, symbols)
    print(f"2) старая ещё раз (данные уже в памяти): {t_old2:.0f} с")
    r_new, t_new = run_all(new, symbols)
    print(f"3) новая (данные в памяти): {t_new:.0f} с  -> ускорение x{t_old2 / max(t_new, 0.1):.1f}\n")
    ok = True
    for s in symbols:
        a, b = canon(r_old2[s]), canon(r_new[s])
        if r_old2[s] is None and r_new[s] is None:
            print(f"{s}: ✅ совпадает (монета не прошла проверку в обеих)")
        elif a == b:
            print(f"{s}: ✅ СОВПАДАЕТ (прошла: {r_new[s].get('timeframe')}, test WR {r_new[s].get('test_wr')}%)")
        else:
            ok = False
            print(f"{s}: ❌ РАСХОЖДЕНИЕ")
    if canon(r_old) != canon(r_old2):
        print("\n⚠️ старая версия дала разный результат в двух прогонах — данные менялись во время теста, повтори")
    print("\nИТОГ:", "✅ всё совпадает" if ok else "❌ есть расхождения — пришли этот вывод")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:] or DEFAULT_SYMBOLS))
