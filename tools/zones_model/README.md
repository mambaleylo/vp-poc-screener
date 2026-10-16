# «Сильные зоны» — how the model in `vp_zones_model.json` was made

Run from this folder (needs numpy, pandas, lightgbm, pyarrow; ~30 GB disk, 16 GB RAM, a few hours on 4 cores).

1. `python3 dl.py 1h` — Binance USDT-M 1h klines of 127 coins, 2020–2026 (data.binance.vision via its S3 mirror).
2. `python3 build.py` — every 48 h per coin: the bot's own zone candidates (`oc_candidates_mtf`) and its 23 features.
3. `python3 build2.py` / `build3.py` / `build4.py` / `build5.py` — the 29 new features (`zfeat.py`, the same code as
   `zm_snap_feats` / `zm_cand_feats` in the bot) and every trade rule replayed (`fastsim.py` = the bot's
   `zone_ladder_sim`, checked by `t_fastsim.py`; confirmation entries in `confsim.py`).
4. `python3 mkdf.py && python3 addlab4.py && python3 volrank.py` — one table (~1 million candidates).
5. `labcmp.py <labels>` — walk-forward (train on the years before, judge on 2022 / 2023 / 2024) per trade rule;
   `freq.py` — trades per week vs R per trade by threshold; `caps.py` — the portfolio with a cap per side.
6. `LAB=G_1.0_R3.0 Q=0.95 SEEDS=3 EXPORT=1 python3 final.py` — the yearly check incl. the unseen 2025–26 and
   the final model (3 LightGBM models, pure-Python trees for the phone, `lgbpure.py`).
7. `t_equiv.py` (the bot's features = the table) and `t_bot_e2e.py` (the bot's scan and ladder on history =
   the research's score and R) must pass after any change.

Chosen: stop = 1 daily ATR beyond the zone's far edge, take = 3R from the average entry, the top 5% of the scores,
at most 12 active zones per side. Walk-forward per trade: 2022 +0.36R (2.8/wk), 2023 +0.18R (7.8/wk),
2024 +0.20R (5.1/wk), 2025–26 (never seen while choosing) +0.17R (6.4/wk); drawdowns up to 52R → small risk.

v0.99.622 — the take sweep (the user: "полноценная проверка разных тейков"): `zt_wf.py` judges every stop 0.75 / 1 /
1.5 / 2 daily ATR × take 1.5 / 2 / 3 / 4 / 6 R label in the same capped walk-forward. Stop 0.75 / take 4R beat the
deployed 1 / 3R in every year; with 3 models per fold (`LAB=G_0.75_R4.0 python3 zm_expect2.py`): 2022 +0.46R,
2023 +0.27R, 2024 +0.22R, 2025–26 +0.17R (+383R in all vs +279R). `zm_export2.py` exports it with the monthly
expectation; `t_bot_e2e2.py` checks the bot's ladder (23/23).
