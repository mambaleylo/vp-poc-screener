#!/usr/bin/env python3
"""MSNR v2: тот же честный отбор, что делает программа, — на РЕАЛЬНЫХ данных Gate.

Запуск (в Termux, файл рядом с vp_poc_screener.py):
    python msnr_research.py [число монет, по умолчанию 60]

Берёт самые ликвидные монеты (как программа), 90 дней 15m + 1h/4h, прогоняет
все варианты стратегии, выбирает лучший по обучающей части (первые 70%
истории всех монет вместе) и проверяет на тестовой (последние 30%). Ничего не
торгует и не пишет в состояние сервера. 1-3 минуты на телефоне.
"""
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = next((p for p in (os.path.join(HERE, "vp_poc_screener.py"), os.path.join(HERE, "..", "vp_poc_screener.py"),
                         os.path.join(os.getcwd(), "vp_poc_screener.py")) if os.path.exists(p)), None)
if MAIN is None:
    sys.exit("не найден vp_poc_screener.py — положите этот скрипт в ту же папку")


def main():
    spec = importlib.util.spec_from_file_location("vp", MAIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    if not hasattr(m, "msnr2_select"):
        sys.exit("vp_poc_screener.py старый — скачайте версию 0.99.401 или новее")
    n = int(sys.argv[1]) if len(sys.argv) > 1 else m.MSNR2_UNIVERSE_N
    syms = m.msnr_build_backtest_universe()[:n]
    print(f"монет: {len(syms)} · {m.MSNR2_DAYS} дн. 15m · вариантов: {len(m.MSNR2_VARIANTS)}\n")
    per, now, t0 = {}, time.time(), time.time()
    for i, s in enumerate(syms, 1):
        try:
            r = m.msnr2_symbol_all_variants(*m.msnr2_fetch(s, now))
            if r:
                per[s] = r
        except Exception as e:
            print(f"  {s}: {e}")
        if i % 10 == 0:
            print(f"  ...{i}/{len(syms)} ({time.time() - t0:.0f} с)")
    v = m.msnr2_select(per)

    def part(p):
        return (f"n={p['n']:4d} · WR {p['wr']}% · {p['avg_r']:+.3f}R/сделку · итого {p['sum_r']:+.1f}R · z={p['z']}"
                if p["n"] else "нет сделок")
    print("\nлучшие варианты по обучению:")
    for r in v["variants"][:8]:
        print(f"  {r['label']}\n     обучение {part(r['train'])}\n     тест     {part(r['test'])}")
    c = v["chosen"] or v["best_train"]
    print(f"\n=== ВЕРДИКТ: {'ТОРГОВАТЬ МОЖНО' if v['passed'] else 'торговать нельзя'}")
    if c:
        print(f"  вариант: {c['label']}")
        print(f"  обучение: {part(c['train'])}   (нужно z ≥ {v['z_needed']})")
        print(f"  ТЕСТ:     {part(c['test'])}   (нужно n ≥ {v['min_test']}, z ≥ {v['z_test_needed']}, плюс)")
        coins = m.msnr2_coin_table(per, c["key"])
        picked = sorted((s for s, x in coins.items() if x["picked"]), key=lambda s: -coins[s]["train"]["sum_r"])
        print(f"\n  монеты с плюсом на своём обучении: {len(picked)}"
              + (f" — торговались бы: {', '.join(x.replace('_USDT', '') for x in picked[:m.MSNR2_TOP_N])}" if v["passed"] else ""))


if __name__ == "__main__":
    main()
