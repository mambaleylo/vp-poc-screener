# lab-store — данные лабы (не бот)

Ветка только для данных исследований: свечи, признаки, оценки моделей, пулы сделок. Бот её не скачивает
(обновляется файлом vp_poc_screener.py из main). Код лабы — в main, tools/winrate.

- data/1h/<SYM>.csv.gz — 1h-свечи Binance USDT-M (t, o, h, l, c, объём $), 2021-01 … 2026-09, зеркало data.binance.vision (dl_all.py)
- universe.json, brackets.json — монеты (объём 2026, история) и плечи Binance (выгрузка бота 31.10.2026)
- replay/ — прогоны кода бота ⚡ по 2026 (rp.py, rp8.py)
