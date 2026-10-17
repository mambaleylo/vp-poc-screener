# Peak Reversal — the audit and `vp_prv_model.json`

Uses `tools/zones_model` data (Binance 1h of 127 coins, `dl.py 1h`, funding `tools/neuro_model/dl_fund.py`) and
`tools/neuro_model/nx_feat.py`. From this folder:

1. `python3 prv_build.py` + `python3 prv_tab.py` — the rule grid without a model: 1h / 4h × EMA14 / 20 / 30, SMA20 ×
   band 1.5 / 2 / 2.5 / 3 ATR × entry (wick touch = the old bot, close beyond, close back inside) × stop 1 / 1.5 / 2
   ATR / beyond the bar × take 1–4R / to the basis × hold 24 / 48 bars (4 608 rules): all lose in every year
   2021–2026 (−0.03…−0.18R); the old bot's per-coin search (best rule of the past 12 months → next month) too.
2. `python3 prv_coinsel.py` — coin auto-selection by the past: no help.
3. `python3 prv_ev.py` — every EMA20 channel event (1h, 4h) with 13 band features + the 89 Neuro features;
   `python3 prv_wf.py` — 13 rule filters (ADX, trend, squeeze, RSI, BTC, volume…): all lose;
   `python3 prv_wf.py model` — the model per side, walk-forward.
4. `python3 prv_export.py` — the chosen rule (stop 1.5 ATR, take 3R, 48 bars, top 1% per side), 3 models per fold:
   2022 +0.23R (4.3/wk), 2023 +0.19R, 2024 +0.35R, 2025–26 +0.13R (2.4/wk, dd 28R); exported for the bot.
5. `t_prx_e2e.py` — the bot's events / features / scores (72/72) and trade record (60/60) = the research's.
