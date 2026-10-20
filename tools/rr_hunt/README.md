# High-RR hunt — the archived indicators re-tested, and 📈 range breakout

Binance 1h history of 127 coins 2020–2026 (`tools/zones_model/dl.py 1h`), funding (`tools/neuro_model/dl_fund.py`).

1. `python3 ev_engine.py` — the project's old indicators as events on 1h / 4h / 1d: Donchian 20 / 55 (Trend),
   squeeze, sweep (Sweep / LSW), retest of a broken level (Mirror), EMA pullback, range breakout, AMD, MR4
   extremes, big candle; each with stops 1 / 1.5 / 3 ATR × fixed takes 3 / 5 / 8 / 12 / 20R, chandelier 3 / 5 / 8
   ATR and Donchian 10 / 20 / 50 exits. `ev_tab.py` — raw table; `ev_wf.py` — a model per side (noisy on trend
   trades); `ev_regime.py`, `ev_gates.py` — market / trend gates without a model.
2. `python3 rb_daily.py` + `rb_tab.py` / `rb_cap.py` / `rb_order.py` — the daily range breakout in depth (range
   10–40 days, compression 2–6 × ATR100, gates, stops, takes / trailing exits, the cap on positions, random and
   ranked order among same-day signals).
3. The rule (picked on 2021–23): 20-day range < 2.5 × ATR100, daily close out of it in the direction of the coin's
   EMA200, stop 1.5 ATR, out at the daily close beyond the 20-day low / high, at most 6 per side, the strongest
   breakout first: 2021 +3.58R, 2022 +0.85R, 2023 +1.03R, 2024 +0.94R, 2025–26 +0.93R (~1/wk, WR ~30%,
   drawdown ≤ 24R, up to 22 stops in a row). `rb_final.py` writes the stats the bot shows.
4. `t_rbx_e2e.py` — the bot's signal (98/98, 320/320 random days) and trade record (97/97) = the research's.
5. `TFH=4|8|12|24 python3 rb_tf.py` — the range breakout on 4h / 8h / 12h / 1d with stops 1 / 1.5 / 2 ATR × takes
   2–8R, Donchian 10 / 20 / 50, chandelier, breakeven at +1R and half at +2R exits (+ the 89 Neuro features of the
   signal hour). `rbtf_tab.py` — the grid with the cap; `rbtf_nx.py` — Neuro score / feature filters (did not
   raise the win rate). 4h / 8h are not stable; 12h (30 bars, < 4 × ATR100) holds: +0.73R a trade, ~2.4/wk.
   Half at +2R: day +0.83R WR 44%, 12h +0.34R WR 37%. `rbx2_stats.py` writes the stats the bot shows.
6. `t_rbx_e2e2.py` — the bot's day and 12h signals (79/79, 241/241, 480 random bars) and trade records with the
   trend exit and with half at +2R (148/148, 444/444) = the research's.

v0.99.646 — the win-rate / RR study for 📈 (same method as P/R and EMA). `rb_h.py`: the bot's breakouts (day N 20 /
2.5, 12h N 30 / 4.0, own EMA200) and a check set (the other range lengths / widths, K < 4); each idea judged at an
equal 1-in-10 drawdown on both. `rb_diag.py` / `rb_hyp.py`: the filters (BTC 24h / vs EMA50, volume, breakout
strength, ATR ratio, longs / shorts, day / 12h) are noise or disagree between the sets; fixed takes 2–8R, a chandelier,
dc10 / dc50 and breakeven are worse. `rb_sim.py` (re-simulated exits, 99.9–100% = the label): the stop 2 ATR beats 1.5
on both sets (x29 vs x20, check x6.3 vs x4.0; WR 32% vs 28%, a losing run of 28 vs 31), with half at +2R WR 41% and a
run of 17 at about the same growth; the stop by close, 2.5 and 3 ATR disagree between the sets. Deployed: the stop 2 ATR
(`rb_export.py` recomputes RBX_RESEARCH / RBX_RESEARCH_MONTHS and the backtest list); `t_rbx_e2e2.py` uses the bot's stop.

v0.99.647 — round 2 (`rb_sim2.py`, `rb_sim3.py`): a retest entry (a limit at the broken edge, 3 / 6 bars), the exit
channel 15 / 30, closing a trade that has not been +1R in 5 / 10 / 20 bars, the EMA200 slope, one signal per coin
across the two charts, half at +2R — worse or disagreeing between the two sets. Kept: the exit channel shortens to 15
bars once the trade has been +4R (x32 vs x29, check x8.4 vs x6.2; +5 / +6 / +8R give the same, -> 10 bars is worse).
`rb_export2.py` recomputes the stats and the list; `t_rbx_e2e2.py` checks the tightened exit too (0 differences).
