# New data — open interest, long/short ratios, taker flow (v0.99.667)

The user: "новые данные: открытый интерес, ликвидации, фандинг по истории". Binance's own archive (the
data.binance.vision S3 mirror) keeps the USDT-M "metrics" files: every 5 min the open interest and its value, the top
traders' long/short ratio by accounts and by position, all accounts' long/short ratio and the taker buy/sell volume
ratio, from 2020-09 for the 127 coins of the research. (Liquidations are not in the archive; funding was already in
the Neuro features.) Run from the research folder (`tools/zones_model` data):

1. `python3 dl_metrics.py` — ~280k daily files -> `data/metrics/<SYM>.csv`, one row per hour (the last 5-min values,
   the mean taker ratio).
2. `mfeat.py` — 13 features per coin and closed hour: the OI change over 1 / 4 / 24 / 72 h, OI vs its 30-day mean,
   the three long/short ratios, the all-accounts ratio's 24 h change (`ls_d24`), the taker ratio over 1 / 4 / 24 h, the
   top traders vs the crowd. The directional ones are read × the trade's side.
3. `python3 mtest.py prv|emx|rbx|cas|nx` — every feature as a filter (drop the top or the bottom third, the thresholds
   from the bot's set before 2023) on each module's deployed rule, the bot's and the check set; `mparse.py` lists what is
   better on both (avg R and equal-pain growth). `mrobust.py <mod> <feat> top|bottom` — the cut 20–50%, 2 bootstrap
   seeds, 2023+ alone.

Result: passed on both sets and was robust — 📈 breakout `ls_d24` (drop the trades into which the crowd moved > 9.6%
over 24 h: the bot's set +0.62R vs +0.55R, x75 vs x31; the check +0.45R vs +0.32R, x39 vs x11; every cut 20–50% and
2023+ alone better) and 📐 EMA `ls_d24` (no long when the crowd's ratio did not rise over 24 h: +1.00R vs +0.86R,
x185k–250k vs x46k–51k; the check +0.56R vs +0.45R, x1.2k–1.3k vs x210; cuts 25–50% and 2023+ better, 20% neutral on
the bot's set). Not kept: the EMA taker flow (a degenerate threshold from the gaps), EMA OI vs its mean (mixed),
P/R filters (within the noise); nothing for 🌊 cascade and 🧠 Neuro. Exports: `rb_part4.py` (the breakout list and
yearly stats), `ema_export8.py` (EMA model ver 9, "ls_min_d24"). The bot reads Binance's
`futures/data/globalLongShortAccountRatio` (5 min, the last 24 h) — `binance_ls_d24`; no answer = no filter.
`t_ls_d24.py`: the bot's helper on a feed built from the archive = the research's feature (300/300).
