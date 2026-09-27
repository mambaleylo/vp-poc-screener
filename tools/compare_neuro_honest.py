#!/usr/bin/env python3
"""Neuro: старый расчёт против честного (v0.99.389) на РЕАЛЬНЫХ данных Gate.

Запуск (в Termux, из папки где лежат оба файла):
    python compare_neuro_honest.py <старый .py> <новый .py> [МОНЕТА ...]

Без списка монет берутся текущие монеты Neuro из vp_neuro_state.json (если
файл лежит рядом), иначе BTC/ETH/SOL/XRP/DOGE.

Обе версии получают одинаковые данные (каждый ответ биржи скачивается один
раз, время "заморожено"). Ничего не торгует и не пишет в состояние сервера.

Что печатается по каждой монете:
  СТАРЫЙ  — то, что показывала карточка (вся история, без комиссий),
            и что эти же старые сделки дали на последних 20% истории
            (тот же период, что у нового «теста»), с комиссиями.
  НОВЫЙ   — обучение / проверка / ТЕСТ (последние 20%, поиск их не видел,
            с комиссиями) + сколько зависимостей прошло проверку.
Честная цифра — «ТЕСТ». На телефоне 1-3 минуты на монету на версию.
"""
import importlib.util
import json
import os
import sys
import time

if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

import requests  # noqa: E402

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


def fee_r(t, fee_pct=0.0005):
    e, sl = t.get("entry"), t.get("sl")
    d = abs((e or 0) - (sl or 0))
    return 2 * fee_pct * e / d if e and d > 0 else 0.0


def stats(ts, net=True):
    cl = [t for t in ts if t.get("result") in ("WIN", "LOSS", "LOSS_EARLY") and t.get("pnl_r") is not None]
    if not cl:
        return "нет сделок"
    w = sum(1 for t in cl if t["result"] == "WIN")
    r = sum(t["pnl_r"] - (fee_r(t) if net else 0) for t in cl) / len(cl)
    return f"WR {100 * w / len(cl):.1f}% · {r:+.3f}R · n={len(cl)}"


def fmt(x):
    if not x or not x.get("n"):
        return "нет сделок"
    return f"WR {x['winrate']}% · {x['avg_pnl_r']:+.3f}R · n={x['n']}"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    old_path, new_path = sys.argv[1], sys.argv[2]
    symbols = sys.argv[3:]
    if not symbols:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(new_path)), "vp_neuro_state.json")) as f:
                symbols = (json.load(f).get("neuro_display_symbols") or [])[:6]
        except Exception:
            symbols = []
    symbols = symbols or DEFAULT_SYMBOLS
    install_shared_data_layer(int(time.time()))
    old = load(old_path, "vp_old")
    new = load(new_path, "vp_new")
    for m in (old, new):
        m.CALC_WORKERS = 0            # в этом процессе, без рабочих процессов
        m.save_neuro_state = lambda *a, **k: None
    print(f"монеты: {', '.join(symbols)}\n")
    tot = {"old_claim": [], "old_last20": [], "new_hold": []}
    for sym in symbols:
        t0 = time.time()
        oc, ot, osum = old.neuro_backtest_symbol(sym)
        t1 = time.time()
        nc, nt, nsum = new.neuro_backtest_symbol(sym)
        t2 = time.time()
        sp = nsum.get("split") or {}
        ve = sp.get("valid_end")
        print(f"=== {sym}   (старый {t1 - t0:.0f} с, новый {t2 - t1:.0f} с)")
        print(f"  СТАРЫЙ карточка:  WR {osum.get('winrate')}% · {osum.get('avg_pnl_r')}R · n={osum.get('n')} · "
              f"$15→{osum.get('compound_final_balance')} · зависимостей {len(oc)}")
        if ve:
            print(f"  СТАРЫЙ за период теста (с комиссиями): {stats([t for t in ot if t['time'] > ve])}")
            tot["old_last20"] += [t for t in ot if t["time"] > ve]
        print(f"  НОВЫЙ  обучение:  {fmt(sp.get('mine'))}")
        print(f"  НОВЫЙ  проверка:  {fmt(sp.get('valid'))}")
        print(f"  НОВЫЙ  ТЕСТ:      {fmt(sp.get('holdout'))}   ← честная цифра ({sp.get('holdout_days')} дн.)")
        print(f"  НОВЫЙ  зависимостей {len(nc)} из {sp.get('fdr_tested')} · $15→{nsum.get('compound_final_balance')} · "
              f"в топ: {'да' if new.neuro_eligible(nsum) else 'нет'}\n")
        tot["new_hold"] += [t for t in nt if ve and t["time"] > ve]
    print("=== ВСЕ МОНЕТЫ ВМЕСТЕ, период теста, с комиссиями")
    print(f"  старый: {stats(tot['old_last20'])}")
    print(f"  новый:  {stats(tot['new_hold'])}")


if __name__ == "__main__":
    main()
