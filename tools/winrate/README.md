# Win-rate hunt (v0.99.679)

The user: "главная цель только винрейт и количество сделок, пусть это будет хоть минутный тайм фрейм, главное входить
в сделку вовремя, не важно rr какой, главное положительный".

`s15_engine.py` — 15m bars of the 127 coins (Binance, 2020–26): deep limits 2 / 3 x ATR from the close (alive 4 bars),
Bollinger(20, 2.5) and day-VWAP ± 2σ limits, EMA20 pullbacks in a trend, 24 h sweeps with a reclaim; exits with small
takes (0.2–1 ATR) and wide stops (1–2 ATR), fees: a limit entry / take 0.02%, a stop / time exit 0.05%.
`s15_wf.py` — the yearly walk-forward model (every 3rd coin never trained on), WR / R / trades a month / weeks with a
trade. `s15_real.py` — the selected trades re-simulated on Binance 1m bars (`dl1m.py`, 40 coins, 2024-10 .. 2026-09):
the exact stop / take order, fills only through the limit, all fees taker, stop slippage. `s15_money.py` — the growth
at an equal 1-in-10 drawdown. `s5_engine.py` — the same on 5m bars built from the 1m klines.

| family (best exit) | top % | train coins | check coins |
|---|---|---|---|
| **deep2, take 0.5 / stop 2 ATR / 16 bars** | 2% | 178/mo, WR 84%, +0.045R, every year + | 96/mo, WR 84%, +0.034R |
| deep2, take 0.2 / stop 2 | any | WR 89%, −0.02R | |
| deep2, take 0.3 / stop 1.5 | any | WR 84%, ~0R | |
| EMA20 pullback | 1% | WR 81%, +0.02R (2025–26 ~0) | |
| Bollinger / VWAP | 1–2% | WR 80%, ~0R | |
| deep3 / 24 h sweep | 1% | WR 83%, +0.016R | |
| deep2 on 5m | any | WR 81–83%, −0.01 … −0.035R | |

deep2 on 1m bars (2024-10+, 40 coins): WR 87–88%, +0.07–0.08R (fill on touch); a fill only 0.05% through the limit
(87% of the orders): WR 85%, +0.05R; + all fees taker: +0.013 … +0.023R; + 0.05% stop slippage: +0.045R.
Money: x2.97/yr (train coins, risk 1.25%), x1.38/yr (check, 1%) at an equal 1-in-10 drawdown — small per trade.

Deployed: ⚡ Лимитки 15м (`dlm_export.py`: the 2026 walk-forward model, the threshold from its 2025 out-of-sample
scores; the bot's pure-Python features equal the engine's; `t_dlm_bot.py`: the bot re-makes the backtest trades and
the real path on a fake exchange: a GTC limit, the stop trigger + a reduce-only take limit, the time exit).
