# Neuro v3 — how `vp_neuro_model.json` was made

Uses the Binance 1h history of `tools/zones_model` (`dl.py 1h`, 127 coins, 2020–2026) and the funding rates
(`python3 dl_fund.py`, the same S3 mirror). From this folder:

1. `python3 nx_build.py` — every 2nd closed 1h bar of every coin: 89 features (`nx_feat.nx_series` = the bot's
   `nx_series`, the same code) and the long / short outcome of 24 rules: stop 1 / 1.5 / 2.5 ATR(1h, Wilder 14),
   take 1 / 1.5 / 2 / 3 R, out after 12 / 48 h; entry at the next bar's open, stop first, fee 0.1% + funding.
2. `FINAL=1 python3 nx_wf.py 1.0_2.0_12 1.5_2.0_48 …` — walk-forward per rule: LightGBM per side trained on the
   years before, judged on 2022 / 2023 / 2024 (2025–26 shown, never used to choose); the threshold = a quantile
   of the scores on the last training year; one trade per coin & side, at most 12 per side.
3. `python3 nx_coinsel.py nx_trades_<rule>.json <q>` — coin auto-selection by past results (no help here: too
   few trades per coin; the model already uses what the coin and the market are).
4. `RULE=1.0_2.0_12 Q=0.997 EXPORT=1 python3 nx_final.py` — the yearly check at 3 thresholds and the export:
   3 models per side trained on everything, as pure-Python trees.
5. `t_nx_e2e.py` — the bot's features / scores on live-sized windows and its trade record = the research's.

Chosen rule (best over 2022–24): stop 1 ATR, take 2R, out after 12 h, top 0.3% per side:
2022 +0.55R (3/wk), 2023 +0.49R (1.4/wk), 2024 +0.28R (9/wk), 2025–26 (unseen) +0.10R (4.5/wk), dd up to 60R.
