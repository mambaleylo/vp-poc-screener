# Adaptation study — how long to learn, how often to retrain, when to pause

The user: the market changes, the models learn on years of history — find the training window and the retrain
schedule for every indicator and catch a regime change as early as possible. Run from the research folder of
`tools/neuro_model` / `tools/prv_audit` / `tools/ema_model` / `tools/zones_model` (their datasets).

1. `python3 ad_wf.py <nx|prv|emx|zm> [schemes]` — the same out-of-sample months 2023-01 .. 2026-09 for every scheme:
   the window (6 / 12 / 24 / 36 months / all history), the retrain step (1 / 3 / 12 months), recency weights
   (half-life 6 / 12 / 24 months). Each retrain: train on [t0 - W - gap, t0 - gap), the threshold = the deployed
   quantile of the new model's scores over the 12 months before, the module's own replay (one trade per coin &
   side, at most 12 per side). `SEED=2 / 3` repeats a scheme with other random seeds (the seed noise is large).
2. `python3 ad_rbx.py` — the 📈 range breakout's trades for the gates; `python3 ad_gate.py <mod> <scheme>` — a pause
   while the last N closed virtual trades / the last D days are negative (per side too, or an EMA of R).
3. Result (avg R per trade, 2023 .. 2026-09):
   - P/R: all history yearly (the old model) +0.21R (3 seeds: +0.10 / +0.33 / +0.20); the last 24 months, every
     quarter +0.50R (+0.52 / +0.60 / +0.37), every year positive in every seed; with 3 models per retrain
     (`prv_export3.py`): 2023 +0.35R, 2024 +0.84R, 2025–26 +0.70R, ~2 trades a week -> deployed (P/R model ver 2).
   - Neuro: all yearly +0.23R (2 seeds), 24 months quarterly +0.15R, recency half-life 12 m +0.26R with half the
     trades — within the seed noise, unchanged.
   - EMA: all yearly +0.30R, all quarterly +0.33R, 36 months +0.34R; 12 / 6 months +0.15 / +0.10R — unchanged.
   - Strong zones: all yearly +0.18R, 36 months +0.19R, 12–24 months +0.07R — unchanged.
   - Short windows (6–12 months) are worse everywhere: they learn the last months' noise.
   - The pause gates cut the range breakout (12h +522R -> +20..+126R) and P/R; for EMA a 14-day gate halves the
     drawdown (73 -> 36R) but lowers the total (611 -> 527R) — no gate deployed.
4. The bot (v0.99.636) checks the repo once a day: a model of the same version with a later `trained_to` replaces
   the local one (`t_refresh.py`: 8/8), so a retrained model reaches the phone without a bot update.
5. P/R stop and take (v0.99.639; the user: P/R often hits the stop and then the take, or nearly reaches the take and
   turns to the stop). `pr_lab2.py <out> s30_t45 ...` writes more exit labels aligned with `prv_ev` (`s30_t45` = stop
   3.0 ATR, take 4.5 ATR). 392 walk-forward trades of the deployed scheme, simulated on 15m bars, R of each variant's
   own stop (the same $ risk): now (1.5 ATR / 3R) +0.66R, Σ+257, WR 48%, drawdown 24R; the same model with a stop of
   2.0 ATR Σ+218, WR 56%, dd 23; 3.0 ATR (take where it was = 1.5R) Σ+176, WR 66%, dd 15. A model retrained for
   1.0 ATR: Σ+299 but dd 43; for 2.0 / 2.5 / 3.0 ATR: Σ+195 / +130 / +153 — worse than the same model with a wider
   stop. Breakeven at +1 / +1.5 / +2R, half off at +1.5R, a closer take: all lower. A re-entry when the price comes
   back to the entry within n bars after the stop looked good on the 392 trades (+0.36R a re-entry) but is negative
   on the top 5% (3087 trades, -0.03..-0.15R) and with a 1.0 ATR stop -> not used. Deployed: the same model, stop
   3.0 ATR, take 4.5 ATR (`prv_export3.py`, model ver 3, `label_rule` = what the model learns).
6. P/R stop clusters (v0.99.641; the user: the good stats are spoiled by clusters of stops, all swept by one big wick).
   75 of 110 stops of the 392 trades were wicks (the stop bar closed back inside); the worst clusters (10–14 stops in a
   row) were 10–12 trades opened at once against a market-wide move. Checked on the 392 trades and on the top 5%
   (3087 trades, a check set): a pause after a stop until a plus, one / two / three open trades at a time — worse at an
   equal drawdown. Kept: (a) the stop by the CLOSE of the trade's bar at 3 ATR with a hard stop 6 ATR on the exchange
   (`pr_lab_cs.py`; R per the hard stop): the drawdown halves on both sets at about the same R; (b) the BTC filter: no
   long after BTC -4% over 24 h, no short after +4% (feature `b_r24`) — +0.45 -> +0.65R a trade on the 392 trades but
   only slightly better on the top 5% (the threshold was picked on the 392, so its gain is optimistic). Together at
   5% risk of the hard stop: x46 over 2023–26 with a 1-in-10 drawdown of 42% (now: 2% -> x18, 56%). Model ver 4;
   `t_prx_cs.py` 14/14 (the stop by close, the hard stop, the market close of a real position, the BTC filter).
7. More P/R filters (v0.99.642) on the saved walk-forward scores (`pr_sel.py` once, then `pr_hyp.py` / `pr_hyp2.py` /
   `pr_hyp3.py <99|95>` in seconds; the replay keeps a slot until the trade's real exit). At an equal 1-in-10 drawdown
   (45%): the 24 h BTC filter x47, the 1 h one alone x43, both x103 (the top 5%: x2.2 / x2.6 / x2.6) -> both deployed
   (`b_r1` > -1% in the trade's direction; model ver 5). Not kept: BTC 4 h (the two sets disagree), one / two entries
   per side an hour (disagree), at most 4–6 open per side, the day trend (EMA200), ADX < 30, the coin's own 24 h move,
   the market breadth (the share of coins with the same event) — fewer trades, less growth at the same drawdown.
