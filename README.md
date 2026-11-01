# lab-store — данные лабы (не бот)

Ветка только для данных исследований: свечи, признаки, оценки моделей, пулы сделок. Бот её не скачивает
(обновляется файлом vp_poc_screener.py из main). Код лабы — в main, tools/winrate.

- data/1h/<SYM>.csv.gz — 1h-свечи Binance USDT-M (t, o, h, l, c, объём $), 2021-01 … 2026-09, зеркало data.binance.vision (dl_all.py)
- universe.json, brackets.json — монеты (объём 2026, история) и плечи Binance (выгрузка бота 31.10.2026)
- replay/ — прогоны кода бота ⚡ по 2026 (rp.py, rp8.py)
- data/funding/<SYM>.csv — фандинг Binance (t, ставка), 2020 … 2026-09, data.binance.vision (tools/prv_audit/dl_fund2.py)
- wf/rbs_<1|2|4>.npz, rbs_<tf>_X.npz — события 🚀 короткого пробоя и их признаки (tools/winrate/rb_short.py, rbs_feat.py)
- wf/dlm_miss_*.json, prv_lab*.npz / .json, money_*.json, rbs_ml*.json, bear_screen.json, lv_new_*.json — результаты расчётов

Не хранится (пересобирается за минуты, см. .gitignore):
- prv_ev/ — события P/R (касания канала) с признаками и исходами: `python3 tools/prv_audit/prv_ev2.py` (после dl_fund2.py)
- wf/prv_lab_ev.npz, wf/prv_lab2_ev.npz — кэши prv_lab.py / prv_lab2.py (сами пересоздаются)
- feat_v175/ — признаки ⚡ с выходами 1.75 / 1.2 (tools/winrate/dlm_relabel.py)
