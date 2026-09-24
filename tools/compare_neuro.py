#!/usr/bin/env python3
"""Сравнение старой и новой версии бэктеста Neuro на РЕАЛЬНЫХ данных Gate.

Запуск (из папки репозитория, в Termux):
    python compare_neuro.py <старый .py> <новый .py> [МОНЕТА ...]

Обе версии получают побайтово одинаковые данные: каждый ответ биржи
скачивается один раз и отдаётся обеим версиям из памяти, а время
"заморожено" на одном моменте, поэтому окна истории совпадают. Скрипт
ничего не торгует и не пишет в состояние сервера — только читает
публичные свечи/фандинг/OI и сравнивает результаты.
"""
import copy
import importlib.util
import json
import os
import sys
import time

# Порядок обхода set/dict со строками должен быть одинаковым в обоих прогонах.
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

import requests  # noqa: E402  (после re-exec)

DEFAULT_SYMBOLS = ["BTC_USDT", "SOL_USDT", "DOGE_USDT"]


def install_shared_data_layer(frozen_now):
    """Все GET-запросы кэшируются по (url, params): вторая версия получает
    ровно те же ответы, что и первая. time.time() заморожено."""
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
    return cache


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def canon(obj):
    return json.dumps(obj, sort_keys=True, default=str)


def first_diff(a, b, path="result"):
    """Краткое описание первого расхождения."""
    if type(a) is not type(b):
        return f"{path}: тип {type(a).__name__} vs {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                return f"{path}.{k}: есть только в {'новой' if k not in a else 'старой'}"
            if canon(a[k]) != canon(b[k]):
                return first_diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return f"{path}: длина {len(a)} vs {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            if canon(x) != canon(y):
                return first_diff(x, y, f"{path}[{i}]")
    elif a != b:
        return f"{path}: {a!r} vs {b!r}"
    return None


def main(old_path, new_path, symbols):
    frozen_now = float(int(time.time()) // 3600 * 3600)
    install_shared_data_layer(frozen_now)
    old = load(old_path, "vp_old")
    new = load(new_path, "vp_new")
    print(f"старая: v{getattr(old, 'APP_VERSION', '?')}   новая: v{getattr(new, 'APP_VERSION', '?')}")
    print(f"монеты: {', '.join(symbols)}   (на телефоне ~5-15 мин на монету)\n")
    all_ok = True
    for sym in symbols:
        t0 = time.perf_counter()
        r_old = old.neuro_backtest_symbol(sym)
        t_old = time.perf_counter() - t0
        t0 = time.perf_counter()
        r_new = new.neuro_backtest_symbol(sym)
        t_new = time.perf_counter() - t0
        n_pat, n_tr = len(r_old[0]), len(r_old[1])
        if not n_pat and not r_old[2]:
            print(f"{sym}: ⚠️ старая версия вернула пусто (ошибка сети/данных?) — сравнение не показательно")
            all_ok = False
            continue
        if canon(r_old) == canon(r_new):
            print(f"{sym}: ✅ СОВПАДАЕТ  ({n_pat} зависимостей, {n_tr} сделок)  "
                  f"время {t_old:.0f}с → {t_new:.0f}с")
        else:
            all_ok = False
            print(f"{sym}: ❌ РАСХОЖДЕНИЕ  время {t_old:.0f}с → {t_new:.0f}с")
            print(f"    старая: {n_pat} зависимостей, {n_tr} сделок; "
                  f"новая: {len(r_new[0])} зависимостей, {len(r_new[1])} сделок")
            print(f"    первое отличие: {first_diff(copy.deepcopy(list(r_old)), copy.deepcopy(list(r_new)))}")
    print("\nИТОГ:", "✅ всё совпадает" if all_ok else "❌ есть расхождения или ошибки — пришли этот вывод")
    return 0 if all_ok else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:] or DEFAULT_SYMBOLS))
