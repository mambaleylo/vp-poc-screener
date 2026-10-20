# 🌊 EMA cascade — how `vp_cas_model.json` was made

The user's idea: a close through the whole EMA cascade (EMA 5/10/14/20/28, 1h) — "сначала выше ема, потом затухание
роста и пробой" (pump → fade → break down) and "пробой снизу вверх и отбой обратно" (break up → fall back).

Uses the Binance 1h history and the Neuro feature store of `tools/zones_model` / `tools/neuro_model`
(`data/1h/*.csv`, `nxf/*.npz` from `nxf_build.py`, `common.py`, `mk.py`, `lgbpure.py`, `nx_h.py`). From that folder:

1. `python3 cas_ev.py` — every whole-cascade cross of 127 coins (966k events): context (48-bar range / ATR, bars of
   the opposite ribbon order before, bars since the opposite cross, excursion past the cascade, 24h move, cascade
   width, BTC 24h, ATR%) and the outcome grid: stop 1 / 1.5 / 2 ATR or the 24-bar swing ± 0.2 ATR, take 1 / 2 / 3R
   or the close back through the far EMA, 24 / 48 h; entry at the next bar's open, fee 0.1% + funding.
2. `python3 cas_an.py` — the raw edge: none. All shorts +0.03R (only the 2022 bear market), longs −0.03R; the
   user's two patterns alone are no better (pump-fade short −0.01R, break-and-reject short +0.03R).
3. `python3 cas_wf.py` — yearly walk-forward LightGBM per side on context + the 89 Neuro features; the threshold
   = a quantile of the previous year's scores; one trade per coin & side, at most 12 per side.
4. `python3 cas_sel.py` — the walk-forward scores saved once (folds 2022–2026); `python3 cas_h.py` — the
   harness: q 0.995 (the bot) and the looser check sets, equal pain (the risk at which the 1-in-10 drawdown is
   45% / 50%) and P/R for comparison. `SEED=7 python3 cas_sel2.py sw_t2_48` + `CAS_SEL=cas_sel_s7_15.npz` — another seed.
5. `python3 cas_pf.py` — what the model picks and the portfolio with P/R.
6. `python3 cas_years.py` — the yearly stats and the bot's backtest list (`vp_bt_trades.json` "cas");
   `python3 cas_export.py` — 3 models per side on everything, the threshold = top 0.5% of the last 12 months.
7. `t_cas_feat.py` (the bot's `cas_event` on 1000-bar windows = the research's features, 291/291) and
   `t_cas_e2e.py` (the bot's `cas_settle` on the same candles = the backtest trades, 80/80).

Chosen rule: stop at the 24-bar swing ± 0.2 ATR, take 2R, out after 48 h, top 0.5% per side:
2022 +0.34R, 2023 +0.25R, 2024 +0.83R, 2025–26 +0.39R a trade (~1.6/wk, WR 56%); another seed +0.40R with every
year positive. Looser check sets (top 1–2%) +0.13…+0.25R, every year ≥ 0. Shorts after a recent up-cross (the
user's "отбой") are the best kind (+0.74R, WR 66%). Alone it is weaker than P/R at an equal drawdown (2% risk →
x13 over 2023–26 vs P/R 8% → x363), but its months are nearly independent of P/R (+0.26): P/R 4% + cascade 1%
→ x95 vs P/R 4% alone → x26 at the same 1-in-10 drawdown (23%).
