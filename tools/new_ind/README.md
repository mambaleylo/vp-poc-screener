# New indicator hunt (v0.99.678)

The user: "пробуем разные варианты индикаторов новых… пока не будет индикатор лучше чем любой из наших", then
"регулярные сделки, чтобы не редкие пачки, а хотя бы 10–15 сделок в месяц, но и по винрейту чтобы хорошо было".

Data: Binance 1h candles of 211 coins (127 = the bot's coins, 84 = the check coins never trained on), OI / long-short /
taker metrics, funding (the scratch `data/` of the earlier rounds; `common.py`, `mk.py`, `nx_h.py` from tools/zones_model
and tools/adaptation).

Judge (`lv_wf.py`): a yearly LightGBM (2 seeds) on the bot coins only, trained on everything closed 14 days before the
year; the threshold of a year = the q-quantile of the previous year's out-of-sample scores; one trade per coin & side,
at most 12 per side; growth at an equal 1-in-10 drawdown (45% bot / 50% check) by month-block bootstrap, as x per year.

| family | engine | best walk-forward (bot · check) |
|---|---|---|
| prev day/week/month high-low-mid, period opens, SMA / Bollinger 1d-1w | `lv_engine.py` (v1 families) | ~x3–4/yr · x2/yr |
| the EMA touches in the same harness (reference) | `lv_engine.py` (d/w EMAs) | ~x5.7/yr · x3.5/yr |
| OI flush / squeeze / pump, crowd z, taker z, funding, residual vs BTC, volume climax, smart-money divergence | `ev2_engine.py` | x1.1–1.9/yr |
| Supertrend, PSAR, Ichimoku, MACD, RSI divergence, Stoch, ADX, Heikin-Ashi, NR7, CCI, Bollinger re-entry, Keltner (4h, 1d) | `ev3_engine.py` | x1.3–2.1/yr |
| **SMC: unfilled FVG 4h/1d/1w, untouched swings 1d/1w, order blocks 4h/1d** | `lv_engine.py` (fam ≥ 33) | **x3.2/yr · x3.1/yr, +0.67R, WR 59%, ~10/month, every year in plus** |
| a calm-market-only model | `ev_grid.py` with a mask | +0.15R, WR 48% |

Regularity (`daily_top.py`, `smc_port2.py`): the good signals of every family come when the whole market moves; the best
signals of every day instead of a threshold: trades in 57–85% of the weeks but +0.1–0.25R, WR ~47%. EMA and P/R trade in
only ~20% of the weeks; SMC 37%; EMA + P/R + SMC at a quarter of EMA's risk: 22 trades a month, a trade in 55% of the
weeks, WR 70%, growth at the equal drawdown x54/yr vs x48/yr without SMC (bootstrap noise ± ~15%).

Deployed: 🧱 SMC (`smc_export.py`): the 2026 walk-forward model (trained before 2026), threshold = q 0.99 of the 2025
out-of-sample scores (the walk-forward rule; the final model's in-sample quantile would let ~5x fewer trades), stop
1 daily ATR, take 3R, 72 h. The bot's pure-Python levels / features == the engine (`t_smc_parity.py`, `t_smc_bot.py`:
120 events, all features equal; the bot re-makes the 2026 backtest trades to the R); UI `t_smc_ui.py`.
