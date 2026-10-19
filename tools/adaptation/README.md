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
