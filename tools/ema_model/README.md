# «EMA — касания» — how `vp_ema_model.json` was made

Uses the Binance 1h history of `tools/zones_model` (`dl.py 1h`, 127 coins, 2020–2026). From this folder:

1. `python3 er_build.py` — every first touch of EMA n in a candle's period (4h: 20/50/100/200; 1d, 1w, 1M:
   7/14/21/28/50/100/200), the limit at the EMA from the period's open, both sides; 39 features known at the
   touch hour's start (`features()` = the bot's `emx_features`); labels for 48 stop / take / hold rules.
2. `python3 er_df.py && python3 er_lab2.py && python3 er_pen.py` — one table (1.16 million touches), 64 more
   short rules, how far past the EMA each touch hour went (a limit touched exactly may not fill).
3. `python3 er_wf.py <labels>` — walk-forward (train on the years before, judge 2022 / 2023 / 2024),
   one trade per coin & side, at most 12 per side; `er_final.py` adds the fill filter and 2025–26.
4. `python3 er_export.py` — the chosen rule (stop 0.5 daily ATR past the EMA, take 2R, out after 24 h, top 3%)
   trained on everything, 3 LightGBM models as pure-Python trees.
5. `t_emx_e2e.py` — the bot's levels / scores / trade record on the history = the research's (must pass).

Walk-forward per trade (fills ≥ 0.1% past the EMA only): 2022 +0.19R (5/wk), 2023 +0.33R (15/wk),
2024 +0.34R (14/wk), 2025–26 (never seen while choosing) +0.15R (9/wk); drawdowns up to 52R → small risk.

v0.99.621 — far takes (the user: "полноценная проверка разных тейков"): `er_lab3.py` adds stop 0.5 / 0.75 / 1 daily
ATR × take 4 / 5 / 6 / 8 R × hold 1 / 3 / 7 days; `er_final.py <labels>` judged them. Stop 0.75, take 4R, out after
72 h, top 3%: 2022 +0.22R (2.3/wk), 2023 +0.48R, 2024 +0.70R, 2025–26 +0.39R (6.8/wk, +239R, dd 38R) vs the old
rule's +0.15R (+127R, dd 52R). Take 8R / 7 days was unstable (2024 negative). The coin auto-selection is not used
with this rule: too few trades per coin to judge (it would keep ~1 trade a week). `EXPORT=1 python3 er_export2.py`
exports it; `t_emx_e2e2.py` checks the bot (47/48 levels, 74/75 trades — the one open at the data's end).
