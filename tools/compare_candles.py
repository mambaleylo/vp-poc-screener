#!/usr/bin/env python3
"""Проверка кэша свечей на РЕАЛЬНЫХ данных Gate: старая загрузка (без
кэша) против новой (с кэшем) должны отдавать побайтово одинаковые свечи.

Запуск (в Termux, из папки со скачанными файлами):
    python compare_candles.py <старый .py> <новый .py> [МОНЕТА ...]

Как проверяется:
  1. "Прогрев": новая версия с часами, отведёнными на 6 часов назад,
     скачивает историю и складывает её во ВРЕМЕННЫЙ кэш (отдельная папка,
     рабочий кэш сервера не трогается).
  2. Сравнение: часы на 1 час назад. Для каждой монеты, таймфрейма и окна
     истории (с ровными и "неровными" границами) старая версия качает всё
     с биржи, новая берёт из кэша и докачивает только новые 6 часов.
     Каждая пара результатов сравнивается целиком.
Ничего не торгует и не меняет состояние сервера.
"""
import importlib.util
import json
import os
import shutil
import sys
import time

TMP_CACHE = os.path.expanduser("~/vp_candle_cache_verify_tmp")
os.environ["VP_CANDLE_CACHE_DIR"] = TMP_CACHE

import requests  # noqa: E402

DEFAULT_SYMBOLS = ["BTC_USDT", "SOL_USDT", "DOGE_USDT"]
INTERVALS = ["15m", "1h", "4h", "1d"]
WINDOWS_DAYS = [40, 102, 400, 1500]

_real_time = time.time
_frozen = [None]
time.time = lambda: _frozen[0] if _frozen[0] is not None else _real_time()

_req_count = [0]
_real_get = requests.get


def _counting_get(*a, **kw):
    _req_count[0] += 1
    return _real_get(*a, **kw)


requests.get = _counting_get


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(old_path, new_path, symbols):
    shutil.rmtree(TMP_CACHE, ignore_errors=True)
    old = load(old_path, "vp_old")
    new = load(new_path, "vp_new")
    print(f"старая: v{getattr(old, 'APP_VERSION', '?')}   новая: v{getattr(new, 'APP_VERSION', '?')}")
    hour = int(_real_time()) // 3600 * 3600
    t_warm, t_cmp = hour - 6 * 3600, hour - 3600

    has_cache = hasattr(new, "_cc_from_semantics")
    if has_cache:
        print("1/2 прогрев кэша...")
        _frozen[0] = float(t_warm)
        for sym in symbols:
            for iv in INTERVALS:
                for days in WINDOWS_DAYS:
                    new.get_candles_range(sym, iv, t_warm - days * 86400 + 17, t_warm)
        print(f"    правило биржи для неровного from: {new._cc_from_semantics}")
    else:
        print("КОНТРОЛЬ: во второй версии нет кэша — сравниваются два обычных скачивания "
              "(покажет, насколько биржа сама отвечает по-разному на одинаковые запросы)")

    print("2/2 сравнение...")
    _frozen[0] = float(t_cmp)
    total = bad = forming = 0
    req_old = req_new = 0
    for sym in symbols:
        sym_bad = 0
        for iv in INTERVALS:
            sec = new.INTERVAL_SECONDS[iv]
            for days in WINDOWS_DAYS:
                for start_jitter, end_jitter in ((0, 0), (17, 0), (sec // 2, 1), (0, sec)):
                    start = t_cmp - days * 86400 + start_jitter
                    end = t_cmp - end_jitter
                    r0 = _req_count[0]
                    a = old.get_candles_range(sym, iv, start, end)
                    r1 = _req_count[0]
                    b = new.get_candles_range(sym, iv, start, end)
                    r2 = _req_count[0]
                    req_old += r1 - r0
                    req_new += r2 - r1
                    total += 1
                    if json.dumps(a) != json.dumps(b):
                        da = {c["time"]: c for c in a}
                        db = {c["time"]: c for c in b}
                        diff_t = sorted(t for t in set(da) | set(db) if da.get(t) != db.get(t))
                        # A candle still FORMING in real time changes between the old
                        # and the new download (seconds apart) — both versions always
                        # fetch it live, so a difference there says nothing about the
                        # cache. Only differences in really-closed candles count.
                        real_now = _real_time()
                        closed_diff = [t for t in diff_t if t + sec <= real_now]
                        if not closed_diff:
                            forming += 1
                            continue
                        bad += 1
                        sym_bad += 1
                        ta, tb = set(da), set(db)
                        print(f"  ❌ {sym} {iv} {days}д (+{start_jitter}/-{end_jitter}): "
                              f"старая {len(a)} свечей, новая {len(b)}; "
                              f"только в старой {sorted(ta - tb)[:3]}, только в новой {sorted(tb - ta)[:3]}, "
                              f"разные значения {[t for t in closed_diff if t in ta and t in tb][:3]}")
        print(f"  {sym}: {'✅ совпадает' if not sym_bad else f'❌ расхождений: {sym_bad}'}")
    shutil.rmtree(TMP_CACHE, ignore_errors=True)
    saved = (1 - req_new / req_old) * 100 if req_old else 0
    print(f"\nсравнений: {total}, запросов к бирже: старая {req_old}, новая {req_new} (−{saved:.0f}%)")
    if forming:
        print(f"(ещё {forming} сравнений отличались только ещё не закрытой свечой — она меняется в реальном "
              f"времени между двумя скачиваниями и всегда качается с биржи; на кэш не влияет)")
    print("ИТОГ:", "✅ всё совпадает" if not bad else f"❌ расхождений: {bad} — пришли этот вывод")
    return 0 if not bad else 1


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    args = sys.argv[3:]
    tf = [a.split("=", 1)[1] for a in args if a.startswith("--tf=")]
    if tf:
        INTERVALS[:] = tf[0].split(",")
    syms = [a for a in args if not a.startswith("--")]
    sys.exit(main(sys.argv[1], sys.argv[2], syms or DEFAULT_SYMBOLS))
