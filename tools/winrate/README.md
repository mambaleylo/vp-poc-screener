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

## ⚡ v2 — the honest 4h wick limits (v0.99.687)

The 15m numbers above were inflated by a future-fill selection bias (an order every bar, kept only where the earlier
ones had not filled). Re-done honestly (`s15u_engine.py`: every order on its own; `bot_since` = the crowding feature as
the bot sees it) deep2 15m is ~0R a trade.

Honest engines on other bars (`s20h4_engine.py` 4h; `s23_engine.py` 4h / 6h / 8h / 12h with wick limits 0.5–1.5 ATR),
the yearly walk-forward (`s20h4_wf.py`, `s23_wf.py`), the 83 extra coins (`extra_run.py`, `extra_eval.py`), 1m Binance
bars (`tf_real.py`), the exits (`h4exit.py`, `h4exit2.py`, `h4part.py`), money with up to N positions (`pool*.py`),
daily features (`s24_feat.py`, `s24_wf.py`) and seed ensembles (`s25_ens.py`):

| 125 unseen coins, top 1%, take 1 / stop 2 ATR / 32 bars | WR | R a trade | last 12 months |
|---|---|---|---|
| 30m / 1h / 2h streams (best) | 70–75% | +0.06 … +0.07 | ~0 … +0.05 |
| 4h wick 1 ATR, one model | 78% | +0.164 | +0.134 |
| 4h, 10-seed ensemble + 5 daily features | 80% | +0.204 | +0.224 |
| **4h, both ensembles averaged (deployed, 20 models)** | **82%** | **+0.235** | **+0.243** |
| the same on 1m bars (fill 0.05% through) | 86% | +0.31 | |

Money (20 positions at 3%, cautious −0.025R a trade, from $100, 2024–26 starts): 6 months median $335, 12 months
median $1 146 (worst 10% $406). Deployed by `dlm4_export2.py`; the bot's features: `t_dlm_parity.py`.

## Lab round after v0.99.688 (nothing deployed)

- **Crash protection** (`crash.py`, `crash2.py`): at most 2–5 new orders a side per 4h bar cuts the usual drawdown 53% ->
  16–21% but halves the money; at an equal worst drawdown the deployed rule makes more. A pause of a side after k stops
  in 24 h: no effect (the stops come at once — 24–25 May 2025, 19 stops, −19R).
- **The "stop-hunt then take" pattern** (`stopcheck.py`, `reentry.py`): 43% of the stops reach the take later inside
  the 32 bars, 57% do not. A stop on the 4h close with a hard stop further: WR up to 88% but 2–4x less money (the
  position is sized by the hard stop); a re-entry after the stop: ~0R.
- **A second 4h stream** (`s24_featall.py`, `s26_mix.py`, `pool4h.py`, `dlm4_export3.py`): a limit 1.5 ATR from the close,
  the same recipe — alone WR 80%, +0.21R on unseen coins, on 1m bars WR 84%, +0.26R. But the pool with the wick stream
  is NOT better when simulated as a bot must trade it (both orders stand, the first to fill is the trade): the median
  year $1 534 at 4% vs $1 878 for the wick stream alone. The research's pool kept, at a bar where both kinds were
  signalled, the one that later filled — a look-ahead. To pick between the streams honestly the engines would have to
  keep the unfilled orders too (their features and scores).
- **A look-ahead in the money sims** found and fixed: sorting one bar's trades by their exit time (`rows.sort()` on
  (time, exit time, …)) gave the quick ones the free slots — +10% for one stream, +80% for a pool. The honest order:
  the signal's time, then its score (`deposits2.py`; `best_money*.py`, `s25_money*.py` were already in that order).
- Monthly top-ups (`deposits2.py`, the deployed ⚡ at 4%, a year, cautious): $100 alone -> median $1 878; + $50 a month
  ($650 in) -> $4 258 (the worst 10% $2 270); $700 at once -> $13 146.

## v0.99.689 — ⚡ 4h wick + 2h close-2ATR (deployed)

- **The 2h stream revived** (`s24_featall.py`, `s26_mix.py` on `s21h2`): a limit 2 ATR from the 2h close, the same
  recipe (20 models, daily features, q 0.99). Pooled with the 4h wick stream as the bot trades them (`pool2h.py`,
  `pool2h_chk.py`: every order stands, the first of a coin & side to fill is the trade): on unseen coins WR ~79%,
  +0.18R; 20 positions at 4%, a year from $100, cautious: the median $5 163 (wick alone $1 878), the worst 10%
  $1 799, harsh $3 107; better from every 2024–25 start; the worst drawdown 65–68%. 1h streams: ~0.
- Deployed by `dlm4_export4.py` (model ver 3 with "streams", the backtest list); the bot's features for both
  streams: `t_dlm_parity.py`, the bot re-makes backtest trades of both: `t_dlm_bot.py`.
- **Re-entry on the reclaim of the stop** (`reclaim.py`, the user's idea): a stop order at the old stop's price
  after a ⚡ stop, the old take, a short stop — not better than ~0R after fees.
- **Elliott wave 5 + RSI divergence, the entry on the Fibo bounce, target 0.702** (`ew5.py`, `ew5_rep.py`, the
  user's post): causal zigzag pivots; on 1m bars negative, on 15m ~0, on 4h n=211 — too few to trust (likely fit).

## v0.99.690 — ⚡ the take 2 ATR unless the price dips 0.4 ATR first (deployed)

- **The user's idea** (`tkext.py`, `tkext_ctl.py`, `tkext_1m.py`, `tkext3.py`): the take 1 ATR becomes 2 ATR for the
  trades that reach +1 ATR without going 0.4 ATR against first. The pool: +0.24R (was +0.18R), WR 70%; a year from
  $100 at 4%, cautious: the median $18 247 (was $5 163), the worst 10% $3 633; better from every 2024–25 start. On 1m
  bars +0.26R vs +0.20R. Always 2 ATR: less money than 1 ATR; the stop moved after the touch: much worse.
  Deployed by `dlm4_export5.py` (the same models, the new exits and numbers).
- **A third stream** (`pool3s.py`, `pool4.py`): 2h wick 1 ATR helps the old take (median $8 100) but not the new one;
  1h close 2 ATR28: the drawdown 89–94% from 2024 starts. **A BTC panic filter** (`btcf.py`): the cancelled orders
  were profitable — no gain. **Risk by the drawdown / positions** (`ddrisk.py`): the drawdown comes in a day or two,
  cutting the risk after it only loses money; more than 15 positions changes nothing (the margin binds).
