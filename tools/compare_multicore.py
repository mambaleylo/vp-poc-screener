#!/usr/bin/env python3
"""Сверка расчёта на нескольких ядрах (MSNR, Sweep, S/R, P/R, Neuro): старая версия
(один процесс) против новой (отдельные процессы) на РЕАЛЬНЫХ данных Gate.

Запуск (в Termux, из папки где лежат оба файла):
    python compare_multicore.py <старый .py> <новый .py> [МОНЕТА ...]

Обе версии получают одинаковые данные (каждый ответ биржи скачивается один
раз, время "заморожено"). Сначала данные скачиваются (прогрев), потом обе
версии считают на уже скачанных данных — так честно видно ускорение.
Ничего не торгует и не пишет в состояние сервера. Neuro — самый долгий
(на телефоне несколько минут на монету), поэтому по умолчанию для него
берутся первые 3 монеты.
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


def run(fn, symbols, threads):
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max(1, threads)) as ex:
        res = list(ex.map(fn, symbols))
    return dict(zip(symbols, res)), time.perf_counter() - t0


def check(title, old_fn, new_fn, symbols, old_threads, new_threads):
    print(f"\n=== {title} ({len(symbols)} монет) ===")
    run(old_fn, symbols, old_threads)                  # прогрев: скачать данные
    r_old, t_old = run(old_fn, symbols, old_threads)
    r_new, t_new = run(new_fn, symbols, new_threads)
    print(f"старая {t_old:.0f} с → новая {t_new:.0f} с  (ускорение x{t_old / max(t_new, 0.1):.1f})")
    ok = True
    for s in symbols:
        same = canon(r_old[s]) == canon(r_new[s])
        ok &= same
        print(f"  {s}: {'✅ совпадает' if same else '❌ РАСХОЖДЕНИЕ'}")
    return ok


def main(old_path, new_path, symbols):
    install_shared_data_layer(float(int(time.time()) // 3600 * 3600))
    old = load(old_path, "vp_old")
    new = load(new_path, "vp_new")
    for m in (old, new):
        if hasattr(m, "CANDLE_CACHE_ENABLED"):
            m.CANDLE_CACHE_ENABLED = False
    new.CALC_WORKERS = max(new.CALC_WORKERS, new.CALC_WORKERS_BOOST)   # как при первом прогоне
    print(f"старая: v{getattr(old, 'APP_VERSION', '?')}   новая: v{getattr(new, 'APP_VERSION', '?')} "
          f"(процессов: {new.CALC_WORKERS})")
    ok = check("MSNR", lambda s: list(old.msnr_optimize_symbol(s)), lambda s: list(new.msnr_optimize_symbol(s)), symbols, 8, 8)
    ok &= check("Sweep", lambda s: list(old.lsw_backtest_symbol(s)), lambda s: list(new.lsw_backtest_symbol(s)), symbols, 8, 8)
    ok &= check("S/R", old.snr_optimize_symbol, new.snr_optimize_symbol, symbols, 8, 8)
    ok &= check("P/R", old.prv_optimize_symbol, new.prv_optimize_symbol, symbols, 8, 8)
    nsyms = symbols[:3]
    btc_o = old.get_candles_range("BTC_USDT", old.NEURO_TF, int(time.time()) - old.NEURO_HISTORY_DAYS * 86400, int(time.time()))
    eth_o = old.get_candles_range("ETH_USDT", old.NEURO_TF, int(time.time()) - old.NEURO_HISTORY_DAYS * 86400, int(time.time()))
    ok &= check("Neuro", lambda s: list(old.neuro_backtest_symbol(s, btc_o, eth_o)),
                lambda s: list(new.neuro_backtest_symbol(s, btc_o, eth_o)), nsyms, 1, new.CALC_WORKERS)
    print("\nИТОГ:", "✅ всё совпадает" if ok else "❌ есть расхождения — пришли этот вывод")
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:] or DEFAULT_SYMBOLS))
