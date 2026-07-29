#!/usr/bin/env python3
"""
VP-POC Screener
================
Signal screener based on the "Bar Magnified Volume Profile / Fixed Range"
concept (ChartPrime, TradingView): builds a fixed-range volume profile over
a lookback window, finds the highest-volume nodes (POC + HVN zones), and
raises LONG/SHORT signals when price wicks into one of those zones and
closes back out (a rejection / bounce off a high-volume support or
resistance area).

Runs as a local HTTP server (Flask) served through a mobile browser —
no exchange keys required, this build is signal/alert only (no
auto-trading). Data source: Gate.io USDT-M futures public REST API.

CHANGELOG
---------
v0.1.0 - initial release: contract universe fetch, fixed-range volume
         profile computation (bar-level proportional overlap, mirrors
         the Pine Script "quadratic" bin-attribution logic), HVN/POC
         zone extraction, bounce-signal detection, watchlist +
         signals API, canvas-based chart UI, optional Telegram alerts.
v0.1.1 - fix: universe builder was reading volume fields off
         /futures/usdt/contracts, which doesn't carry volume data at
         all (always 0 -> everything filtered out -> "0 пар"). Switched
         to /futures/usdt/tickers, which actually has volume_24h_quote/
         _settle/_base.
v0.1.2 - added explicit TP/SL per signal (stop beyond the far edge of
         the HVN zone, target at RR multiples of that risk, RR
         configurable via VP_RR) and outcome tracking: each scan cycle
         checks open signals' candles for TP/SL hits (or a timeout),
         closes them WIN/LOSS/TIMEOUT, and exposes rolling win-rate
         stats in /api/status and the UI header.
v0.2.0 - chart modal now draws entry/SL/TP lines for a clicked signal
         and highlights the POC zone (bold line + label, like the
         reference ChartPrime indicator); added a per-symbol parameter
         optimizer (walk-forward backtest over a small grid of
         lookback/HVN-count/RR) triggered on demand via an
         "Оптимизировать" button — picks the historically best-winrate
         combo for that symbol and uses it for that symbol's live
         signals going forward (/api/optimize/<symbol>).
v0.2.1 - added a data-quality gate: symbols whose candle feed itself
         looks illiquid/stale (too many zero-volume bars, too many
         flat high==low bars, or near-zero average range vs price —
         the "dashes that don't move" look on thin contracts) are
         excluded from the watchlist/signals even if they cleared the
         24h-volume filter. Excluded count shown in the header.
v0.3.0 - added MFE/MAE tracking (max favorable/adverse excursion, in R
         multiples of risk) per signal, kept updating for VP_MFE_TRACK_SEC
         after detection regardless of whether/when TP or SL fired —
         the raw data needed to later judge whether TP/SL should sit
         further out or tighter in. New "Тюнинг" tab aggregates
         avg/median/p25/p75 of MFE and MAE across WIN/LOSS/OPEN signals;
         new /api/tuning endpoint exposes the same numbers.
v0.3.1 - fix: update_signal_outcomes was checking the trigger candle
         itself (time >= sig["time"]) against SL/TP. That candle's own
         wick is what produced the signal (it's what touched the HVN
         zone) — checking it against SL/TP could close a trade
         instantly, on the very bar it was detected, before the trade
         had any chance to actually play out. Now only candles that
         close strictly AFTER the trigger bar (time > sig["time"])
         count toward TP/SL/MFE/MAE. This was corrupting the win-rate
         stats; in-memory stats reset on restart so this takes effect
         cleanly.
v0.4.0 - zone quality overhaul: extract_hvn_zones now drops merged
         zones taller than VP_MAX_ZONE_HEIGHT_FRAC of the whole profile
         range (no more wide/diffuse "zones"); added eligible_zones(),
         which restricts signal generation to zones whose volume is at
         least VP_ZONE_STRENGTH_MIN_RATIO of the POC's volume — weak
         zones still render on the chart (dim/dotted) but won't fire
         signals on their own. Added a second signal type, detect_breakout
         (price bases inside/around a zone for a few bars then clears an
         edge decisively) alongside the existing bounce/rejection
         detector — both run every scan, tagged via a new "reason" field
         (bounce/breakout) shown in the signals table and Telegram
         alerts. The per-symbol optimizer (backtest_params) now uses the
         exact same eligible-zone + bounce-or-breakout logic as live
         scanning, so tuned parameters stay consistent with what
         actually trades. Chart now visually distinguishes POC (bold
         green) / eligible zones (dashed amber) / weak context-only
         zones (faint dotted grey).
v0.4.1 - two fixes from live examples: (1) added a whole-profile
         "peakedness" gate in extract_hvn_zones — if the busiest bin
         isn't at least VP_MIN_PEAK_RATIO times the average bin, volume
         is just spread flat across the range and there's no real POC;
         such symbols now return zero zones instead of pretending the
         busiest bin means something. (2) the SL buffer (fraction of
         zone height beyond the edge) was a fixed global constant the
         optimizer never touched, so a symbol whose price routinely
         pokes slightly past a node before reversing would get stopped
         out even with "optimized" params. buffer_pct is now a 4th grid
         dimension (15% / 35%) in the per-symbol optimizer, so a wider
         stop can be selected per-symbol when it improves win rate.
v0.5.0 - defaults updated from the first real MFE/MAE dataset (159
         signals, 46% winrate): WIN median MFE was ~2.8R against a
         1.5R TP (leaving profit on the table), and LOSS median MFE
         was ~1.7R (a chunk of stopped-out trades kept moving the
         "right" way afterward — SL was clipped too close by noise).
         Raised default RR 1.5 -> 2.0 and default ZONE_BUFFER_PCT
         0.15 -> 0.30. Also widened the per-symbol optimizer grid to
         match (RR now tests 1.5/2.0/2.5, buffer now tests
         0.20/0.35/0.50) so "Оптимизировать" explores the same wider
         range instead of being capped below the new defaults.
v0.6.0 - added background auto-tuning: previously per-symbol
         optimization only ran when someone tapped "Оптимизировать" in
         the chart modal — every other symbol traded on global
         defaults forever. Each scan cycle now also (re-)tunes up to
         VP_AUTO_TUNE_PER_CYCLE (default 1) symbols, prioritizing ones
         with no override yet, then whichever override is oldest once
         VP_AUTO_TUNE_REFRESH_SEC (default 48h) has passed — so the
         whole universe gets tuned, and re-tuned, over time without any
         manual action. Kept deliberately slow (one symbol's 81-combo
         backtest costs real CPU) so it doesn't blow out the scan
         cadence on a phone; toggle via VP_AUTO_TUNE=0 to disable. The
         manual button still works for forcing an immediate re-tune.
         Header now shows tuning progress (N/universe already tuned).
v0.6.1 - extended data_quality_check with three "sawtooth chop" checks:
         direction-flip ratio (bar-to-bar close direction reversing
         almost every bar), average wick ratio (candles that are mostly
         wick, little real body — indecision noise), and gap ratio
         (open jumping away from the prior close too often). A symbol
         can have plenty of volume and pass every earlier check yet
         still whip back and forth with no continuity — such symbols
         are now excluded the same way illiquid ones are.
v0.6.2 - the direction-flip/wick-ratio checks from v0.6.1 didn't catch
         the actual reported example (XIAOMI_USDT) — real chop often
         runs a few bars the same way before reversing, not a strict
         every-other-bar flip, so the flip ratio stayed under threshold.
         Added a Kaufman-style efficiency ratio check: net price
         displacement over the window divided by the total path length
         traveled. A symbol that swings hard but ends up near where it
         started (lots of movement, ~0 net progress) now gets excluded
         directly, regardless of the flip-ratio/wick-ratio numbers.
         Loosened those two thresholds slightly (0.68->0.60,
         0.72->0.65) since the efficiency-ratio check now carries more
         of the load.
v0.6.3 - added a bounce-vs-breakout win-rate breakdown (compute_signal_stats
         now returns by_reason, shown in the header) — needed to tell
         whether an aggregate winrate drop is coming from one signal
         type dragging the other down, rather than guessing from the
         combined number alone.
v0.6.4 - loosened MIN_EFFICIENCY_RATIO 0.15 -> 0.08: the stricter value
         was excluding 98/150 universe symbols in practice — normal
         crypto ranging/consolidation has low net displacement too, and
         isn't the same thing as sawtooth chop. 0.08 should only catch
         the more extreme cases while leaving the sample size usable.
v0.7.0 - persist state to disk (vp_poc_state.json next to the script):
         SYMBOL_OVERRIDES (auto-tuned + manually-optimized per-symbol
         params) and the signal history (win-rate, MFE/MAE stats) now
         survive a restart instead of resetting every time the script
         is relaunched to pick up an update. Saved at the end of every
         scan cycle and right after a manual "Оптимизировать". Loaded
         once at startup, before the scan thread begins. Best-effort —
         any read/write failure just logs and the app keeps running on
         in-memory state alone.
v0.8.0 - added two signal filters, both applied identically in live
         scanning and the backtest optimizer for consistency:
         (1) trend filter — compute_trend() reads net price change over
         VP_TREND_LOOKBACK bars (default 50); in a clear UP/DOWN move
         (beyond VP_TREND_THRESHOLD_PCT, default 2%) only signals going
         with that direction are taken (a LONG bounce off support in a
         hard downtrend is fighting the move). Neutral regime: no
         filtering. (2) volume confirmation — the trigger bar's volume
         must be >= VP_VOL_CONFIRM_RATIO (default 1.15x) the average of
         the preceding VP_VOL_CONFIRM_LOOKBACK bars (default 20); a
         touch/breakout on below-average volume is more likely noise.
         Both toggleable independently (VP_TREND_FILTER=0 /
         VP_VOLUME_CONFIRM=0). Verified against synthetic up/down/flat
         trends and low/high-volume trigger bars before shipping.
v0.8.1 - observability for the v0.8.0 filters and for version-over-version
         comparisons in general: (1) each signal is now tagged with the
         APP_VERSION active when it was detected, and compute_signal_stats
         returns a current_version winrate split alongside the aggregate —
         old signals still in the rolling history no longer dilute the
         read on "did this version's change actually help". (2) added
         filtered_by_trend / filtered_by_volume counters (reset each scan
         cycle) so it's visible how often each filter is actually
         rejecting a candidate signal, not just that it exists. Both
         shown in a new header line.
v0.8.2 - fix: two signals for the same symbol at the same instant, with
         near-identical but slightly different SL/TP (seen live on
         DOGE_USDT). Root cause: build_universe() didn't dedupe symbol
         names — if the tickers endpoint returned an entry twice, the
         ThreadPoolExecutor scanned that symbol twice concurrently, and
         each call independently fetched candles, built its own zone
         object, and raced the cooldown check-before-set (both threads
         read the old timestamp before either wrote the new one).
         Deduped build_universe() (keeps the higher-volume reading per
         name) and made the cooldown check-and-set atomic under a lock
         as defense in depth, in case two threads ever land on the exact
         same key concurrently again. Verified both with synthetic
         duplicate-ticker input and a 20-thread concurrent-claim test.
v0.9.0 - added a "Очистить данные" button in the header: wipes
         SYMBOL_OVERRIDES, signal history, watchlist, cooldowns, error
         log, and the auto-tune rotation cursor, both in memory and in
         the persisted state file (/api/reset, POST). Requires a native
         confirm() dialog before it fires — no accidental taps. Useful
         after a change to signal-generation logic, when old and new
         signals mixed together would muddy the win-rate read.
v0.9.1 - added VP_BOUNCE_ENABLED / VP_BREAKOUT_ENABLED toggles: the
         bounce-vs-breakout winrate split (v0.6.3/v0.8.1) surfaced a big
         gap in real data (bounce 20% vs breakout 38%), so being able to
         disable either type independently and compare the aggregate is
         now possible without a code change.
v0.9.2 - fix: the same symbol could fire near-duplicate signals a few
         minutes apart (seen live on CBRS_USDT — three SHORT bounce
         signals in ~10 minutes, all at essentially the same level).
         Root cause: cooldown was keyed on the HVN zone's exact mid
         price, but the zone is rebuilt from scratch every scan from a
         rolling lookback window — its edges wobble slightly scan to
         scan even with no real change in the level, so the "same" zone
         kept producing a technically-different key and skipping the
         cooldown check entirely. Replaced with a much simpler rule:
         don't fire a new signal for a symbol that already has an
         unresolved (OPEN) one, regardless of which zone produced it.
         Cooldown is now just per-symbol, applied after that symbol's
         open signal closes.
v0.10.0 - "bar magnification": the original ChartPrime indicator builds
         its profile from lower-timeframe sub-bars (request.security_lower_tf,
         ~16x finer), distributing each sub-bar's own volume instead of
         approximating a whole parent-timeframe bar's volume as spread
         evenly across its own high-low range. We'd been doing the
         latter (an approximation) for performance reasons. Implemented
         the former: get_candles_range() pages through Gate.io's
         candlesticks endpoint (from/to, chunked under its ~2000-point
         cap) to pull real sub-bar data at a finer interval
         (pick_magnify_interval() picks the coarsest interval that's
         still >= VP_MAGNIFY_RATIO, default 16x, finer than the main
         one — 10s for a 5m main interval), and compute_profile_magnified()
         distributes THEIR volume into the bins instead. Wired into live
         scanning and /api/profile (chart view); the backtest optimizer
         still uses the same-timeframe approximation deliberately — an
         extra paginated fetch per walk-forward iteration across 81 grid
         combos would be prohibitively slow. Falls back to the old
         approximation automatically if the magnified fetch fails.
         Toggle via VP_MAGNIFY=0. Verified: pick_magnify_interval picks
         sensible finer intervals across several main intervals, and
         compute_profile_magnified(window, window) exactly reproduces
         compute_profile(window) when fed the same data (refactor
         sanity check) — plus a mocked-network test confirming
         get_candles_range correctly paginates a 3000-candle window into
         2 chunks under the per-request cap.
v0.10.1 - changed default VP_INTERVAL from 5m to 15m — confirmed by the
         user that the author's own demo screenshots used 15m candles.
         Lookback stays 100 bars, so the profile window is now ~25h
         instead of ~8.3h. MAGNIFY_INTERVAL auto-recalculates from the
         new default (still 10s, now a 90x sub-bar ratio instead of 30x).
v0.10.2 - fix pick_magnify_interval(): it picked the coarsest interval
         that was AT LEAST the target ratio, so 15m (now the default)
         picked 10s sub-bars — a 90x ratio, 6x more requests than
         needed for no real accuracy gain over the intended ~16x.
         Switched to closest-in-log-ratio selection: 15m now correctly
         picks 1m sub-bars (15x, right on target). 5m/1h/etc. picks are
         unaffected or improved (see the ladder verified across every
         interval: 1m->10s 6x, 5m->10s 30x, 15m->1m 15x, 30m->1m 30x,
         1h->5m 12x, 4h->15m 16x, 8h->30m 16x, 1d->1h 24x).
v0.10.3 - added exit-candle diagnostics: a closed signal now records
         exit_time and the exact OHLC of the candle that triggered
         WIN/LOSS, shown as a tooltip (and inline time) next to the
         status in the signals table. Direct response to a user report
         that a LOSS looked wrong on our chart canvas at that zoom level
         — this makes it possible to verify a specific result against
         the exchange's own chart at the exact timestamp instead of
         eyeballing a compressed price range.
v0.10.4 - reverted default VP_INTERVAL back to 5m per request. Added an
         explicit MAGNIFY_OVERRIDES table so 5m always magnifies to 1m
         (5x) rather than what the general closest-ratio algorithm picks
         (10s, 30x) — the author's own formula floors to a coarser step
         when tf<16 rather than going to a very fine sub-interval, and
         1m is the practical equivalent here given our interval ladder
         doesn't have anything between 10s and 1m.
v0.10.5 - reverted default VP_INTERVAL back to 15m per follow-up
         request (the 5m revert in v0.10.4 was a misread — 15m is what
         should stay as default, confirmed matching the author's demo
         screenshots). MAGNIFY_OVERRIDES for 5m stays in place, harmless
         since it only applies if VP_INTERVAL is explicitly set to 5m.
v0.11.0 - bounce and breakout now get fully independent settings, not
         just independent stats. Real data showed bounce and breakout
         can have meaningfully different win rates for the same symbol
         (item #3 from the earlier improvement list); sharing one RR/
         buffer/lookback/HVN across both meant tuning one could only
         ever be a compromise. Changes:
         - New global defaults VP_RR_BOUNCE / VP_RR_BREAKOUT and
           VP_BUFFER_PCT_BOUNCE / VP_BUFFER_PCT_BREAKOUT (each falls
           back to the shared VP_RR / VP_ZONE_BUFFER_PCT if unset, so
           nothing changes unless configured).
         - SYMBOL_OVERRIDES is now {"bounce": {...}, "breakout": {...}}
           per symbol instead of one flat dict — optimize_symbol() runs
           two separate 81-combo grid searches (via a new
           allowed_reasons param threaded through detect_any_signal and
           backtest_params, not a global toggle, so it's safe against
           concurrent live scanning) and can land on entirely different
           lookback/HVN/RR/buffer for bounce vs breakout on the same
           symbol.
         - scan_symbol() builds a profile per reason (reusing it when
           both happen to share the same lookback, to avoid doubling
           the magnified sub-candle fetch when nothing's actually been
           tuned apart) and detects/prices each signal type against its
           own zones and its own RR/buffer.
         - /api/profile/<symbol> takes a ?reason=bounce|breakout param;
           the chart modal now requests the profile scoped to whichever
           reason the clicked signal actually was. The "Оптимизировать"
           button shows both results side by side.
         - auto_tune_cycle's staleness check updated for the new nested
           structure (oldest optimized_at across whichever reasons have
           a result).
         Verified: allowed_reasons correctly restricts backtest_params
         to one signal type, optimize_symbol produces and stores
         separate bounce/breakout results end-to-end (mocked candles).
v0.12.0 - added an open-interest filter, applied to breakout signals
         only (bounce is a rejection off a level; breakout is a move
         away from it, which is what OI direction actually speaks to).
         get_contract_stats() pulls OI history via GET
         /futures/usdt/contract_stats; compute_oi_trend() reads net
         change over VP_OI_LOOKBACK bars (default 24 x VP_OI_INTERVAL,
         default 1h — so a 24h window) and calls it UP/DOWN beyond
         VP_OI_THRESHOLD_PCT (default 5%). Rising OI only allows LONG
         breakouts, falling OI only allows SHORT — new positions opening
         should back a breakout in that direction; unwinding shouldn't.
         Only fetched when a breakout candidate already exists (not
         blanket per-symbol-per-scan), and degrades to NEUTRAL
         (unfiltered) on any fetch error rather than blocking signals on
         a network hiccup. Toggle via VP_OI_FILTER=0. New
         filtered_by_oi counter alongside the trend/volume ones in the
         header. Not applied inside the backtest optimizer (same
         reasoning as bar magnification — historical OI alignment per
         walk-forward iteration would be expensive for a button click).
         Verified against synthetic rising/falling/flat OI series and a
         forced fetch-error case.
v0.13.0 - replaced HVN zone construction entirely: extract_hvn_zones()
         used to rank bins and merge a fixed top-N by rank, which could
         cut a wide plateau short mid-shoulder or merge unrelated bins.
         Now each zone grows outward from a local volume peak while
         neighboring bins stay >= VP_SHOULDER_THRESHOLD_PCT (default
         50%) of that peak's own volume — stopping exactly where the
         bars visibly get shorter, matching what a person looking at
         the profile would trace by eye. Removed the separate
         VP_MAX_ZONE_HEIGHT_FRAC cap entirely: it existed to reject
         "too tall" merged zones under the old method, but directly
         fought the new one — a genuinely wide volume plateau should
         produce a genuinely wide zone; the shoulder threshold is what
         keeps it honest now, not an arbitrary height ceiling. Verified
         against a Gaussian-hump-on-baseline synthetic profile (realistic
         shape): the POC zone came out correctly wide, spanning the true
         shoulder-to-shoulder width; a sharp narrow spike still stays
         narrow; pure random-walk data (no genuine concentration)
         correctly still returns zero zones (the flat-profile gate is
         unaffected); 81-combo grid search performance unchanged (~5s).
v0.14.0 - new feature, fully separate from the volume-profile screener
         above: RSI divergence detection on its own timeframe (1h by
         default, VP_DIV_INTERVAL), own scan pass, own signal history,
         own stats, own chart, own "Дивергенции" tab. compute_rsi() is a
         standard Wilder RSI; find_pivots() confirms a swing high/low
         `right` bars after it happens; detect_divergence() compares
         RSI's value at the two most recent PRICE pivots (not
         independently-found RSI pivots — the standard approach): price
         higher-high + RSI lower-high = bearish -> SHORT; price
         lower-low + RSI higher-low = bullish -> LONG. Only fires if the
         second pivot is within VP_DIV_FRESHNESS_BARS (default 8) of the
         latest candle. SL sits beyond the more extreme of the two
         pivot prices (VP_DIV_BUFFER_PCT buffer), TP at VP_DIV_RR (own
         RR, default 2.0) multiples of that risk. Same MFE/MAE tracking,
         WIN/LOSS/TIMEOUT resolution, and disk persistence as the main
         screener, but in a completely separate deque/cooldown/state so
         the two never mix. New endpoints: /api/divergence/status,
         /api/divergence/signals, /api/divergence/chart/<symbol>. The
         chart modal renders two stacked panels — candles with a
         trendline connecting the two price pivots (plus entry/SL/TP
         lines), and RSI below with a trendline connecting RSI's value
         at those same two bars — matching what a person tracing
         divergences by eye on a chart would draw.
         Caught and fixed two self-inflicted bugs while building this:
         an edit that silently deleted the `data_quality_check` function
         signature (body got orphaned as dead code inside the previous
         function — compiled fine, failed at runtime), and a second edit
         that deleted the `refreshAll` JS function signature the same
         way. Added a standing check for both risks going forward:
         `python3 -m py_compile` + a full module import (catches
         function-signature deletions py_compile alone misses, since
         orphaned code is still syntactically valid) for the Python
         side, and extracting the embedded frontend script block and
         running `node --check` on it for the JS side, after every edit
         that touches either. Verified end-to-end with synthetic engineered
         bearish/bullish divergences (correct direction, entry/SL/TP,
         and — importantly — that the chart endpoint's candle timestamps
         actually contain the signal's stored pivot timestamps, since
         the frontend trendline draw depends on finding them), a Flask
         test-client pass across all new and existing endpoints, and a
         duplicate-top-level-function-definition scan across the whole
         file.
v0.15.0 - added VP_VOLUME_PROFILE_ENABLED (default 1): set to 0 to run
         divergence-only, skipping the whole volume-profile scan
         (zones, bounce/breakout signals, watchlist, auto-tuning)
         while the RSI divergence scan keeps running normally. The
         universe is still built once and shared by whichever mode(s)
         are on. UI hides the Sигналы/Watchlist/Тюнинг tabs and jumps
         to Дивергенции automatically when volume-profile mode is off
         (checked once via a new volume_profile_enabled field in
         /api/status, not on every poll, so it doesn't fight a
         manually-selected tab). Telegram alerts with a hardcoded
         token from another project: not done yet, waiting on the
         actual bot token/chat_id (or the sending code) from the user —
         nothing to reuse without it.
v0.16.0 - Telegram: reads mambaleylo/EMA-screener's already-populated
         ~/.smc_alert_cfg.json (same file, same tg_token/tg_chat keys)
         as a fallback when VP_TG_TOKEN/VP_TG_CHAT aren't set — the
         token already configured there just gets picked up, nothing
         to paste in again. Also replaced the fire-and-own-thread
         sender with the queued, rate-limited one already proven in
         that project's Pump_Radar.py: Telegram Bot API caps at ~1
         msg/sec/chat, so bursts (several signals the same scan cycle)
         used to silently drop some sends (429s). One background
         worker now drains a queue sequentially with a ~1.1s pause
         between sends, with 3 retries (5s apart) on network errors,
         no retry on non-network errors. Verified: config-file
         precedence (env wins over file, missing file doesn't crash),
         queued messages arrive in order, and a flaky
         connection recovers on retry — all via a mocked requests.post,
         plus a full endpoint regression sweep.
v0.16.1 - divergence chart is now self-labeling: each pivot point on
         both panels shows its type (HIGH for bearish, LOW for bullish
         — derived from the signal's own kind) and numeric value, plus
         a prominent kind/direction banner drawn directly on the
         canvas. Prompted by a user screenshot where it wasn't possible
         to tell, from pixels alone, whether the two connected points
         were pivot highs or lows — which made it impossible to verify
         the trendline against our own bearish/bullish logic without
         also seeing the (separately scrollable) header text. Traced
         the coordinate math by hand to confirm the price-up/RSI-down
         pattern in that screenshot is consistent with our bearish
         detection (HH price + LH RSI) if the points are highs, which
         they most likely were — the labels make this self-evident
         going forward instead of requiring a manual trace.
v0.17.0 - fix: a real bug this time, confirmed by a user screenshot
         showing the RSI trendline cutting straight through visibly
         taller peaks between its two connected points. Root cause:
         detect_divergence compared RSI's value at the EXACT same bar
         as the price pivot, but RSI and price don't necessarily peak
         on the same bar — reading RSI only at price's pivot bar can
         land on a mediocre point while RSI's real local extreme sits a
         few bars away. Added _rsi_extreme_near(): for each price pivot,
         search VP_DIV_RSI_SEARCH_WINDOW bars (default 10) each side for
         RSI's own local max/min, and use THAT — both value and bar —
         instead of the same-bar reading. New rsi_time_p1/rsi_time_p2
         fields on the signal record so the chart's RSI trendline
         connects to RSI's own extreme bars, which can now differ from
         the price pivot bars (price panel and RSI panel trendlines no
         longer share the same x-positions when the two series peak on
         different bars — this is correct, not a bug). Also fixed the
         chart modals' background: was semi-transparent (rgba alpha
         .92) at z-index 20, letting the page header/button bleed
         through visibly behind the modal on at least one mobile
         browser (reported via screenshot) — now solid opaque #05070c
         at z-index 999. Verified _rsi_extreme_near against three cases
         (peak before the pivot bar, trough after it, and a peak outside
         the search window correctly ignored) and a full
         detect->store->chart-endpoint pipeline confirming rsi_time_p1/
         p2 differ from time_p1/p2 when they should and are findable in
         the chart's own candle timestamps.
v0.18.0 - user feedback: v0.12-13 together cut live signal volume too
         much, enough that they'd rolled back to v0.11 and lost the
         dedup/Telegram/divergence fixes shipped since. Rather than
         re-deleting the v0.13 zone method, made it selectable:
         VP_ZONE_METHOD=shoulder (default, v0.13's behavior) or
         VP_ZONE_METHOD=topn (restores v0.11's exact zone construction
         — top-N bins merged by rank, with the original
         VP_MAX_ZONE_HEIGHT_FRAC cap). Tested both against the same
         Gaussian-hump profile: shoulder produced a 2.5-wide zone,
         topn a 0.6-wide one (25% vs 6% of the price range) — a
         materially narrower zone is easier to wick into and close back
         out of, which is exactly the touch-and-reject condition both
         bounce and breakout need to fire, so the width difference
         plausibly explains the drop in signal frequency directly. Also
         raised the default OI filter threshold 5% -> 8%
         (VP_OI_THRESHOLD_PCT) since 5% over a 24h window was likely
         triggering (and filtering breakouts) too readily — can still
         be disabled entirely with VP_OI_FILTER=0. zone_method now
         shown in /api/status config for visibility into which mode is
         active.
v0.19.0 - fixed a real measurement problem affecting every TP/SL
         conclusion drawn from the tuning stats so far: MFE/MAE keep
         updating for VP_MFE_TRACK_SEC (24h) after a signal closes, by
         design, to see how much headroom existed — but that also means
         a closed trade's mfe_r/mae_r pick up whatever the market did
         AFTER it already resolved, which isn't the trade's own run and
         shouldn't be read as "how far did it get before winning/
         losing". close_signal()/close_div_signal() now snapshot
         mfe_r_at_close/mae_r_at_close the instant a trade resolves,
         before the post-close window keeps growing the originals. The
         Тюнинг panel now leads with the at-close numbers (labeled
         "на момент закрытия сделки") and tucks the original full-window
         ones into a collapsed <details> for the separate "how much
         general headroom exists" question. Also caught and fixed a
         second self-inflicted bug while writing this: a template
         literal referencing MFE_TRACK_HOURS, a JS variable that was
         never declared (node --check doesn't catch undefined-variable
         references, only syntax errors — it validates parseability, not
         runtime correctness). Fixed by exposing mfe_track_hours from
         /api/tuning instead. Added a static analysis pass — grep every
         ${ALL_CAPS} template variable in the extracted script block
         against declared const/let/function names — to catch this
         category of bug going forward; found none remaining.
v0.20.0 - added pivot-confirmation-delay diagnostics for RSI divergence
         (user asked: track this so we can later decide how much
         VP_DIV_PIVOT_RIGHT can safely be reduced) — and, in the
         process, caught and discarded a genuinely broken first attempt
         before shipping it. The first version checked whether an
         already-known-correct pivot would ALSO pass a smaller
         confirmation window — mathematically this is guaranteed to
         always be true (a point that's the extreme over a larger window
         is trivially also the extreme over any smaller sub-window of
         it), confirmed empirically at 898/898 True across 200 random
         trials, i.e. it measured nothing. Replaced with
         simulate_pivot_stability(): walks the series bar-by-bar as if
         running live, and at each point checks whether the SHADOW
         (smaller-right) method's current pick is a bar that the
         RIGOROUS (full-right) method — computed with full hindsight —
         also confirms as genuine, excluding the unconfirmable tail so
         "not judged yet" isn't miscounted as "wrong". Verified this
         version produces a non-trivial, monotonic result on synthetic
         data (71% agreement at right=1, 80% at right=2, 83% at right=3,
         95% at right=4, 100% at right=right — the last one a sanity
         check, not a coincidence). Wired into the scan loop as
         div_stability_cycle(), rotating one symbol per cycle like
         auto_tune_cycle, accumulating agree/disagree counts per
         VP_DIV_SHADOW_RIGHTS value (default 2,3,4) in
         STATE["div_pivot_stability"], exposed via /api/divergence/status
         and rendered in the Дивергенции tab. Cleared by "Очистить
         данные" along with everything else. Point 2 of the same
         request (track where/how far price goes after a signal, for
         TP/SL tuning) was already covered by the existing MFE/MAE
         tracking shared with the volume-profile signals (and just
         improved further by v0.19's at-close fix) — nothing new needed
         there, confirmed working for divergence signals via the same
         end-to-end test.
v0.20.1 - MFE/MAE at-close values (v0.19) were only visible in the
         aggregate Тюнинг stats, not per-signal — the signals tables
         still showed the still-growing 24h-window value for every row,
         which doesn't directly answer "how far did THIS trade get
         before it resolved". Added fmtMfeMae(): for a closed trade,
         shows the at-close value with the current (possibly since
         grown) value alongside it — e.g. "2.10 (→3.46)" — falling back
         to just the current value for open trades or older signals
         recorded before this field existed. Applied to both the main
         signals table and the divergence signals table. Verified
         against open/closed/legacy/missing-field cases directly.
v0.21.0 - extended the pivot-stability diagnostic with the other half
         of the question: not just "would a smaller right window agree
         with the rigorous one", but "how much price move gets given up
         waiting for the extra confirmation bars, on the cases where
         they do agree". simulate_pivot_stability() now also takes
         closes and, for every agreeing case, compares the close price
         at shadow-confirmation time vs at full-confirmation time —
         signed so positive always means "the earlier entry would have
         been better" (higher price for a bearish/high pivot, lower for
         a bullish/low one). Accumulated as a running avg (gain_sum/
         gain_count, not a growing list, to keep memory bounded) per
         VP_DIV_SHADOW_RIGHTS value, shown in the Дивергенции tab
         alongside the agreement rate. Verified on synthetic data: gain
         shrinks monotonically as shadow_right approaches the real one
         (less waiting -> less to give up), consistent with the
         agreement-rate trend from v0.20.
v0.22.0 - Диверы приведены в соответствие со стандартной практикой
         торговли дивергенциями (проверено по опорным материалам, в
         т.ч. по логике самого известного открытого скрипта дивергенций
         на TradingView, LonesomeTheBlue "Divergence for Many
         Indicators"): (1) VP_DIV_FRESHNESS_BARS теперь по умолчанию
         равен VP_DIV_PIVOT_RIGHT — сигнал живёт ровно в момент
         подтверждения пивота, а не ещё несколько баров после (было
         freshness=8 при right=3, из-за чего сигнал мог появиться на
         5 баров позже самого пивота на графике). (2) detect_divergence
         больше не ищет "свой" локальный экстремум RSI в окне вокруг
         ценового пивота (_rsi_extreme_near/VP_DIV_RSI_SEARCH_WINDOW из
         v0.17.0) — теперь RSI читается строго на тех же барах, что и
         ценовые пивоты, как это делают референсные индикаторы
         дивергенций. Из-за поиска в окне верхняя (цена) и нижняя (RSI)
         трендлинии на графике могли идти по разным x-координатам —
         теперь они всегда синхронны. (3) добавлена стандартная
         проверка "cut-through": если между двумя пивотами RSI хотя бы
         раз пробивает линию, соединяющую rsi[p1] и rsi[p2] (пик выше
         неё при медвежьей дивергенции / впадина ниже при бычьей),
         сигнал отбраковывается как недостоверный — это правильный
         способ обработать случай "линия режет более высокий пик",
         вместо того чтобы переносить точку в сторону от реального бара
         пивота.
"""

import os
import json
import time
import math
import threading
import traceback
import queue
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, jsonify, request, Response

APP_VERSION = "0.22.0"

# ----------------------------------------------------------------------------
# Config (env-overridable, no secrets required for base functionality)
# ----------------------------------------------------------------------------
GATE_BASE = "https://api.gateio.ws/api/v4"

SEGS = int(os.environ.get("VP_SEGS", 100))                # grid levels in profile
LOOKBACK = int(os.environ.get("VP_LOOKBACK", 100))        # candles used to build profile
INTERVAL = os.environ.get("VP_INTERVAL", "15m")           # candle timeframe — matches the author's confirmed 15m demo screenshots

# --- volume profile "bar magnification": instead of approximating a bar's
# volume as spread evenly across its own high-low range, pull actual
# sub-bar data at a finer interval and distribute THEIR volume — same idea
# as the original ChartPrime script's request.security_lower_tf, just
# implemented via REST pagination. Prioritizes accuracy over request
# count: this adds a second (often multi-request, paginated) fetch per
# symbol per scan.
INTERVAL_SECONDS = {
    "10s": 10, "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "4h": 14400, "8h": 28800, "1d": 86400,
}
MAGNIFY_ENABLED = os.environ.get("VP_MAGNIFY", "1") == "1"
MAGNIFY_TARGET_RATIO = float(os.environ.get("VP_MAGNIFY_RATIO", 16))  # aim for at least this many sub-bars per parent bar, like the original's "~16x lower timeframe"


# Explicit overrides for main intervals where the general algorithm's
# pick doesn't match what's actually wanted: the original script's own
# formula (round(tf/16), floored to a minimum step when tf<16) doesn't
# land cleanly on our available interval ladder either. For a 5m main
# interval specifically, 1m sub-bars (5x) is the intended magnify
# interval — 10s (30x) is unnecessarily heavy for the accuracy gained.
MAGNIFY_OVERRIDES = {
    "5m": "1m",
}


def pick_magnify_interval(main_interval, target_ratio=MAGNIFY_TARGET_RATIO):
    """Pick whichever available finer interval gives a sub-bar ratio
    closest to target_ratio — comparing in log space so being 2x off at
    a ratio of 15 counts the same as being 2x off at a ratio of 150.
    Matters in practice: for a 15m main interval, 1m sub-bars give a 15x
    ratio (right on target) while 10s would overshoot to 90x — the
    floor-based version used to pick 10s here since it was "at least"
    the target, burning 6x more requests for no real accuracy gain."""
    if main_interval in MAGNIFY_OVERRIDES:
        return MAGNIFY_OVERRIDES[main_interval]
    main_sec = INTERVAL_SECONDS.get(main_interval)
    if not main_sec:
        return main_interval
    finer = [(name, sec) for name, sec in INTERVAL_SECONDS.items() if sec < main_sec]
    if not finer:
        return main_interval

    def log_distance(item):
        _, sec = item
        return abs(math.log(main_sec / sec) - math.log(target_ratio))

    finer.sort(key=log_distance)
    return finer[0][0]


MAGNIFY_INTERVAL = pick_magnify_interval(INTERVAL)
HVN_TOP_N = int(os.environ.get("VP_HVN_TOP_N", 6))        # top bins considered "high volume"
MIN_VOL_USD = float(os.environ.get("VP_MIN_VOL_USD", 500000))  # min 24h quote volume filter
MAX_SYMBOLS = int(os.environ.get("VP_MAX_SYMBOLS", 150))  # universe cap
# master switch for the whole volume-profile screener (zones, bounce/breakout
# signals, watchlist, auto-tuning) — turn off to run divergence-only
VOLUME_PROFILE_ENABLED = os.environ.get("VP_VOLUME_PROFILE_ENABLED", "1") == "1"
SCAN_INTERVAL_SEC = int(os.environ.get("VP_SCAN_INTERVAL", 45))
COOLDOWN_SEC = int(os.environ.get("VP_COOLDOWN", 900))    # per-symbol re-alert cooldown, applied after a signal on that symbol closes
WORKERS = int(os.environ.get("VP_WORKERS", 8))
SIGNAL_HISTORY = 200
RR = float(os.environ.get("VP_RR", 2.0))                  # take-profit distance as a multiple of risk — raised from 1.5: collected MFE stats showed WIN median MFE ~2.8R, i.e. TP was cutting winners short
ZONE_BUFFER_PCT = float(os.environ.get("VP_ZONE_BUFFER_PCT", 0.30))  # stop sits this far beyond the zone edge (fraction of zone height) — raised from 0.15: LOSS median MFE was ~1.7R, meaning a chunk of stopped-out trades kept moving in the original direction afterward — noise was clipping the stop too close
# bounce and breakout are different setups (rejection vs. continuation) —
# give each its own RR/buffer defaults rather than forcing them to share
# one setting. Falls back to the shared RR/ZONE_BUFFER_PCT above if not
# explicitly set, so nothing changes unless these are configured.
RR_BOUNCE = float(os.environ.get("VP_RR_BOUNCE", RR))
RR_BREAKOUT = float(os.environ.get("VP_RR_BREAKOUT", RR))
BUFFER_PCT_BOUNCE = float(os.environ.get("VP_BUFFER_PCT_BOUNCE", ZONE_BUFFER_PCT))
BUFFER_PCT_BREAKOUT = float(os.environ.get("VP_BUFFER_PCT_BREAKOUT", ZONE_BUFFER_PCT))
SIGNAL_TIMEOUT_SEC = int(os.environ.get("VP_SIGNAL_TIMEOUT", 6 * 3600))  # close as TIMEOUT if neither TP/SL hit
MFE_TRACK_SEC = int(os.environ.get("VP_MFE_TRACK_SEC", 24 * 3600))  # keep measuring max favorable/adverse excursion this long after detection, past TP/SL/timeout

# ----------------------------------------------------------------------------
# RSI divergence: a completely separate signal source from the volume
# profile screener above — own timeframe, own scan, own history/stats,
# own chart. Bearish (regular) divergence: price makes a higher high while
# RSI makes a lower high at the same two pivots -> SHORT. Bullish: price
# lower low, RSI higher low -> LONG.
# ----------------------------------------------------------------------------
DIVERGENCE_ENABLED = os.environ.get("VP_DIVERGENCE_ENABLED", "1") == "1"
DIV_INTERVAL = os.environ.get("VP_DIV_INTERVAL", "1h")
DIV_FETCH_LIMIT = int(os.environ.get("VP_DIV_FETCH_LIMIT", 200))  # candles pulled per symbol per scan
DIV_RSI_PERIOD = int(os.environ.get("VP_DIV_RSI_PERIOD", 14))
DIV_PIVOT_LEFT = int(os.environ.get("VP_DIV_PIVOT_LEFT", 5))
DIV_PIVOT_RIGHT = int(os.environ.get("VP_DIV_PIVOT_RIGHT", 3))  # was 5 — the tool's own shadow-stability stats (right=3: 88.3% agreement, entry ~0.15% better) show right=5 was confirming later than it needed to, often after the move had already played out
# Стандартная практика торговли дивергенциями: сигнал считается живым
# ровно в момент подтверждения пивота (right баров после самого пивота),
# а не ещё сколько-то баров сверху. По умолчанию равен DIV_PIVOT_RIGHT —
# это минимально возможное значение (раньше пивот физически не может
# быть подтверждён), поэтому сигнал срабатывает один раз, точно на баре
# подтверждения, и не "протухает" через дополнительные 5 баров, как было
# при freshness=8 vs right=3.
DIV_FRESHNESS_BARS = int(os.environ.get("VP_DIV_FRESHNESS_BARS", DIV_PIVOT_RIGHT))
DIV_MAX_RISK_PCT = float(os.environ.get("VP_DIV_MAX_RISK_PCT", 0.03))  # skip a divergence signal if the pivot-based invalidation point sits more than this fraction of entry price away — a distant pivot means an oversized SL and (at DIV_RR) an even more oversized TP, not a genuinely tradeable setup
# Diagnostic only, doesn't affect live detection: for each fired signal,
# check whether a SMALLER right-confirmation window would have picked the
# exact same pivot bar using only the data that would actually have been
# available at that earlier point in time (not the full future dataset —
# that comparison is meaningless, since a pivot confirmed with the full
# window trivially also satisfies any smaller one in hindsight). This is
# what actually tells us the risk of reducing VP_DIV_PIVOT_RIGHT: how
# often would going faster have picked a different, wrong point instead.
DIV_SHADOW_RIGHTS = [int(x) for x in os.environ.get("VP_DIV_SHADOW_RIGHTS", "2,3,4").split(",") if x.strip()]
DIV_RR = float(os.environ.get("VP_DIV_RR", 2.0))
DIV_BUFFER_PCT = float(os.environ.get("VP_DIV_BUFFER_PCT", 0.005))  # SL sits this far beyond the pivot extreme (fraction of price)
DIV_COOLDOWN_SEC = int(os.environ.get("VP_DIV_COOLDOWN", 3600))
DIV_SIGNAL_HISTORY = 200

# --- zone quality filters: only narrow, genuinely dominant nodes should
# fire signals. A merge of many adjacent top-N bins can produce a tall,
# diffuse "zone" that isn't really a precise level — and a zone that's
# technically in the top-N but far weaker than the POC isn't the kind of
# node price actually respects.
MIN_PEAK_RATIO = float(os.environ.get("VP_MIN_PEAK_RATIO", 2.5))  # the busiest bin must be at least this many times the average bin — otherwise volume is just spread flat across the whole range and there's no real POC to trade
SHOULDER_THRESHOLD_PCT = float(os.environ.get("VP_SHOULDER_THRESHOLD_PCT", 0.5))  # a zone grows outward from its local peak bin while neighboring bins stay >= this fraction of that peak's volume — stops right where the bars visibly get shorter
# v0.13's shoulder-growth method replaced v0.11's top-N-bin-merge method.
# User feedback: v0.12-13 together cut signal volume too much. Kept both
# methods selectable rather than re-deleting the newer one — "topn"
# restores the pre-v0.13 zone construction (with its original height cap)
# exactly, in case the shoulder method is the one over-filtering.
ZONE_METHOD = os.environ.get("VP_ZONE_METHOD", "shoulder")  # "shoulder" or "topn"
LEGACY_MAX_ZONE_HEIGHT_FRAC = float(os.environ.get("VP_MAX_ZONE_HEIGHT_FRAC", 0.10))  # only used when VP_ZONE_METHOD=topn
ZONE_STRENGTH_MIN_RATIO = float(os.environ.get("VP_ZONE_STRENGTH_MIN_RATIO", 0.55))  # zone volume must be >= this fraction of the POC's volume to be eligible for signals
BREAKOUT_MIN_BARS_INSIDE = int(os.environ.get("VP_BREAKOUT_MIN_BARS", 3))  # bars that must have been basing inside/around the zone right before a breakout signal
BOUNCE_ENABLED = os.environ.get("VP_BOUNCE_ENABLED", "1") == "1"
BREAKOUT_ENABLED = os.environ.get("VP_BREAKOUT_ENABLED", "1") == "1"

# --- trend filter: in a clear up/down move, only take signals in that
# direction (a LONG bounce off support in a hard downtrend is fighting the
# move — the level is more likely to just break).
TREND_FILTER_ENABLED = os.environ.get("VP_TREND_FILTER", "1") == "1"
TREND_LOOKBACK = int(os.environ.get("VP_TREND_LOOKBACK", 50))
TREND_THRESHOLD_PCT = float(os.environ.get("VP_TREND_THRESHOLD_PCT", 0.02))  # net move over TREND_LOOKBACK bars beyond which it counts as trending, not neutral

# --- volume confirmation: the trigger bar should have above-average
# volume — a level touch/breakout on thin, below-average volume is more
# likely noise than a real move.
VOLUME_CONFIRM_ENABLED = os.environ.get("VP_VOLUME_CONFIRM", "1") == "1"
VOL_CONFIRM_LOOKBACK = int(os.environ.get("VP_VOL_CONFIRM_LOOKBACK", 20))
VOL_CONFIRM_RATIO = float(os.environ.get("VP_VOL_CONFIRM_RATIO", 1.15))  # trigger bar volume must be >= this multiple of the average of the preceding VOL_CONFIRM_LOOKBACK bars

# --- open interest filter: applied to breakout signals only (bounce is a
# rejection off a level, breakout is a move away from it — OI direction
# is a "is real money backing this move" check that fits breakout, not
# bounce). Rising OI = new positions opening, more likely to back a
# breakout in that direction; falling OI = positions unwinding, weaker
# conviction the move continues. Only fetched when a breakout candidate
# actually exists (not blanket per-symbol-per-scan) to limit the extra
# network cost.
OI_FILTER_ENABLED = os.environ.get("VP_OI_FILTER", "1") == "1"
OI_INTERVAL = os.environ.get("VP_OI_INTERVAL", "1h")
OI_LOOKBACK = int(os.environ.get("VP_OI_LOOKBACK", 24))
OI_THRESHOLD_PCT = float(os.environ.get("VP_OI_THRESHOLD_PCT", 0.08))  # raised from 0.05 — was triggering (and filtering) too readily per user feedback that v0.12-13 cut signal volume too much

# --- data quality filter: skip symbols that look illiquid/stale on the
# candle feed itself (near-zero volume bars, flat high==low bars, or an
# almost flat price range) even if they cleared the 24h volume filter.
MAX_ZERO_VOL_RATIO = float(os.environ.get("VP_MAX_ZERO_VOL_RATIO", 0.15))
MAX_FLAT_RATIO = float(os.environ.get("VP_MAX_FLAT_RATIO", 0.15))
MIN_AVG_RANGE_PCT = float(os.environ.get("VP_MIN_AVG_RANGE_PCT", 0.0004))
# "sawtooth" chop: candles whipping direction back and forth almost every
# bar, mostly-wick candles (little real body vs total range), or frequent
# open/close gaps between bars — technically has volume, but the profile
# and any zone off it is unreliable because price isn't behaving
# continuously, it's just jumping around.
MAX_DIRECTION_FLIP_RATIO = float(os.environ.get("VP_MAX_DIRECTION_FLIP_RATIO", 0.60))
MAX_AVG_WICK_RATIO = float(os.environ.get("VP_MAX_AVG_WICK_RATIO", 0.65))
GAP_THRESHOLD_PCT = float(os.environ.get("VP_GAP_THRESHOLD_PCT", 0.004))
MAX_GAP_RATIO = float(os.environ.get("VP_MAX_GAP_RATIO", 0.12))
# Kaufman-style efficiency ratio: net displacement over the window divided
# by the total path length traveled. A real sawtooth can have a flip ratio
# near the ~50% random baseline (a few bars in a row each way, not a
# strict alternation) and still be pure chop — this catches that case
# directly: lots of total movement, almost no net progress.
MIN_EFFICIENCY_RATIO = float(os.environ.get("VP_MIN_EFFICIENCY_RATIO", 0.08))  # 0.15 excluded 98/150 symbols in practice — normal crypto ranging/consolidation isn't the same thing as sawtooth chop, loosened to only catch the extreme cases

TELEGRAM_BOT_TOKEN = os.environ.get("VP_TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("VP_TG_CHAT", "")
# Same config file path used by the EMA-screener/Pump_Radar project — if
# Telegram was already set up there, this picks up the same token/chat_id
# automatically, no re-entry needed. Env vars above still win if set.
ALERT_CFG_PATH = os.path.expanduser("~/.smc_alert_cfg.json")


def _load_alert_cfg():
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    try:
        with open(ALERT_CFG_PATH, "r") as f:
            cfg = json.load(f)
        TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN or cfg.get("tg_token", "") or ""
        TELEGRAM_CHAT_ID = TELEGRAM_CHAT_ID or cfg.get("tg_chat", "") or ""
    except FileNotFoundError:
        pass
    except Exception as e:
        log_error(f"reading {ALERT_CFG_PATH}: {e}")

HTTP_TIMEOUT = 10

# ----------------------------------------------------------------------------
# State
# ----------------------------------------------------------------------------
app = Flask(__name__)

state_lock = threading.Lock()
STATE = {
    "watchlist": {},          # symbol -> {price, top, bottom, dist_pct, zones, updated}
    "signals": deque(maxlen=SIGNAL_HISTORY),
    "universe_size": 0,
    "excluded_low_quality": 0,
    "filtered_by_trend": 0,
    "filtered_by_volume": 0,
    "filtered_by_oi": 0,
    "last_scan_started": None,
    "last_scan_finished": None,
    "last_scan_duration": None,
    "errors": deque(maxlen=30),
    # RSI divergence — kept fully separate from the volume-profile
    # screener above (own history, own stats, own "page").
    "div_signals": deque(maxlen=DIV_SIGNAL_HISTORY),
    "div_last_scan_finished": None,
    "div_last_scan_duration": None,
    # rotating diagnostic: how often would a smaller DIV_PIVOT_RIGHT have
    # agreed with the rigorous one, accumulated one symbol per cycle
    "div_pivot_stability": {str(r): {"agree": 0, "disagree": 0, "gain_sum": 0.0, "gain_count": 0} for r in DIV_SHADOW_RIGHTS},
}
_cooldowns = {}  # (symbol, zone_key) -> last_alert_ts
_cooldowns_lock = threading.Lock()
_div_cooldowns = {}  # symbol -> last_alert_ts
_div_cooldowns_lock = threading.Lock()


def has_open_signal(symbol):
    """True if this symbol already has an unresolved (OPEN) signal —
    simplest fix for the "repeat signal on the same level every scan"
    problem: don't stack a second signal on a symbol that already has one
    running, regardless of which exact zone/direction produced it."""
    with state_lock:
        return any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in STATE["signals"])


# ----------------------------------------------------------------------------
# RSI divergence: RSI calc, swing-pivot detection, divergence match
# ----------------------------------------------------------------------------
def compute_rsi(closes, period=DIV_RSI_PERIOD):
    n = len(closes)
    rsi = [None] * n
    if n < period + 1:
        return rsi
    gains = [0.0] * n
    losses = [0.0] * n
    for i in range(1, n):
        change = closes[i] - closes[i - 1]
        gains[i] = max(change, 0.0)
        losses[i] = max(-change, 0.0)
    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period
    rsi[period] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rsi[i] = 100 - 100 / (1 + avg_gain / avg_loss)
    return rsi


def find_pivots(values, left=DIV_PIVOT_LEFT, right=DIV_PIVOT_RIGHT, kind="high"):
    """A bar is a pivot high/low if it's the max/min of the window
    `left` bars before it through `right` bars after it — a pivot only
    gets confirmed `right` bars after it actually happened."""
    n = len(values)
    pivots = []
    for i in range(left, n - right):
        if values[i] is None:
            continue
        window = values[i - left:i + right + 1]
        if any(v is None for v in window):
            continue
        if kind == "high" and values[i] == max(window):
            pivots.append(i)
        elif kind == "low" and values[i] == min(window):
            pivots.append(i)
    return pivots


def simulate_pivot_stability(values, closes, left, real_right, shadow_right, kind, stride=1):
    """Walk bar-by-bar as if running live: at each point T, compute what
    the SHADOW (smaller right) method would currently call its most
    recent pivot, using only data up to T. Check whether that specific
    bar is ALSO a pivot per the RIGOROUS (full right) method computed
    with full hindsight over the whole series — that's genuine ground
    truth, unlike checking a single already-known-correct bar (which is
    guaranteed to always agree, a mistake caught before shipping this).
    Only counts cases where the rigorous method has had a full chance to
    judge that bar (excludes the unconfirmable tail), so a "disagree"
    here means a real false start, not just "not confirmed yet".

    On every AGREEING case (same real pivot either way — an apples-to-
    apples comparison), also records the % price move given up while
    waiting the extra (real_right - shadow_right) bars for full
    confirmation: close price at shadow-confirmation time vs close price
    at full-confirmation time, signed so positive always means "the
    earlier entry would have been better" (for a high/bearish pivot a
    higher price is better; for a low/bullish pivot a lower price is
    better, so that side is flipped)."""
    n = len(values)
    real_pivots = set(find_pivots(values, left, real_right, kind))
    agree = disagree = 0
    pct_gains = []
    for T in range(left + shadow_right, n, stride):
        shadow_pivots = find_pivots(values[:T + 1], left, shadow_right, kind)
        if not shadow_pivots:
            continue
        latest = shadow_pivots[-1]
        if latest + real_right >= n:
            continue  # rigorous method hasn't had a full chance to judge this bar yet
        if latest in real_pivots:
            agree += 1
            shadow_t, real_t = latest + shadow_right, latest + real_right
            p_shadow, p_real = closes[shadow_t], closes[real_t]
            if p_real:
                pct = (p_shadow - p_real) / p_real * 100
                if kind == "low":
                    pct = -pct
                pct_gains.append(pct)
        else:
            disagree += 1
    return agree, disagree, pct_gains


def _rsi_cut_through(rsi, p1, p2, r1, r2, mode):
    """Стандартная проверка валидности дивергенции (аналог опции
    "Check Cut-Through" в референсном индикаторе дивергенций
    LonesomeTheBlue): между двумя пивотами RSI не должен пробивать
    прямую линию, соединяющую r1->r2 — иначе на самом деле RSI не
    делал чистый lower-high/higher-low относительно ценовых пивотов,
    а полученная "дивергенция" ненадёжна. Отбраковка такого сигнала —
    правильный способ обработать случай "линия режет более высокий
    пик между точками", а не перенос точки в сторону от реального
    бара ценового пивота (как было в v0.17.0 через _rsi_extreme_near)."""
    if p2 <= p1:
        return False
    span = p2 - p1
    for i in range(p1 + 1, p2):
        v = rsi[i]
        if v is None:
            continue
        interp = r1 + (r2 - r1) * (i - p1) / span
        if mode == "high" and v > interp:
            return True
        if mode == "low" and v < interp:
            return True
    return False


def detect_divergence(candles, rsi, left=DIV_PIVOT_LEFT, right=DIV_PIVOT_RIGHT,
                       freshness=DIV_FRESHNESS_BARS):
    """Ценовые пивоты берутся из find_pivots(). RSI читается СТРОГО на
    тех же барах, что и ценовые пивоты — это стандартный подход
    (так пары цена/осциллятор сравнивают референсные индикаторы
    дивергенций), а не отдельно найденный локальный экстремум RSI в
    окне (как было в v0.17.0) — это как раз и рассинхронизировало
    x-координаты верхней и нижней трендлиний на графике. Кандидат
    отбраковывается, если RSI между пивотами пробивает линию,
    соединяющую его значения на этих пивотах (_rsi_cut_through) —
    правильная обработка "более высокого пика между точками" вместо
    переноса точки. Сигнал засчитывается, только если второй пивот
    отстоит от последнего бара не больше чем на `freshness` баров
    (по умолчанию freshness == right, т.е. сигнал живой ровно в
    момент подтверждения пивота, а не ещё долго после)."""
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    n = len(candles)

    pivot_highs = find_pivots(highs, left, right, "high")
    if len(pivot_highs) >= 2:
        p1, p2 = pivot_highs[-2], pivot_highs[-1]
        r1, r2 = rsi[p1], rsi[p2]
        if (r1 is not None and r2 is not None and highs[p2] > highs[p1] and r2 < r1
                and n - 1 - p2 <= freshness
                and not _rsi_cut_through(rsi, p1, p2, r1, r2, "high")):
            return {
                "direction": "SHORT", "kind": "bearish",
                "p1": p1, "p2": p2,
                "price_p1": highs[p1], "price_p2": highs[p2],
                "rsi_p1": r1, "rsi_p2": r2,
                "time_p1": candles[p1]["time"], "time_p2": candles[p2]["time"],
                "rsi_time_p1": candles[p1]["time"], "rsi_time_p2": candles[p2]["time"],
            }

    pivot_lows = find_pivots(lows, left, right, "low")
    if len(pivot_lows) >= 2:
        p1, p2 = pivot_lows[-2], pivot_lows[-1]
        r1, r2 = rsi[p1], rsi[p2]
        if (r1 is not None and r2 is not None and lows[p2] < lows[p1] and r2 > r1
                and n - 1 - p2 <= freshness
                and not _rsi_cut_through(rsi, p1, p2, r1, r2, "low")):
            return {
                "direction": "LONG", "kind": "bullish",
                "p1": p1, "p2": p2,
                "price_p1": lows[p1], "price_p2": lows[p2],
                "rsi_p1": r1, "rsi_p2": r2,
                "time_p1": candles[p1]["time"], "time_p2": candles[p2]["time"],
                "rsi_time_p1": candles[p1]["time"], "rsi_time_p2": candles[p2]["time"],
            }
    return None


def compute_div_tp_sl(direction, entry, sig, rr=DIV_RR, buffer_pct=DIV_BUFFER_PCT):
    """SL sits beyond whichever pivot price is more extreme (the level
    that, if broken, invalidates the divergence read)."""
    if direction == "SHORT":
        extreme = max(sig["price_p1"], sig["price_p2"])
        sl = extreme * (1 + buffer_pct)
        risk = sl - entry
        tp = entry - risk * rr
    else:
        extreme = min(sig["price_p1"], sig["price_p2"])
        sl = extreme * (1 - buffer_pct)
        risk = entry - sl
        tp = entry + risk * rr
    return sl, tp, risk


def has_open_divergence_signal(symbol):
    with state_lock:
        return any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in STATE["div_signals"])


def scan_symbol_divergence(symbol):
    if not DIVERGENCE_ENABLED:
        return
    try:
        candles = get_candles(symbol, interval=DIV_INTERVAL, limit=DIV_FETCH_LIMIT)
        min_needed = DIV_RSI_PERIOD + DIV_PIVOT_LEFT + DIV_PIVOT_RIGHT + 20
        if len(candles) < min_needed:
            return
        ok, _reason = data_quality_check(candles[-min(len(candles), 100):])
        if not ok:
            return
        closes = [c["close"] for c in candles]
        rsi = compute_rsi(closes, period=DIV_RSI_PERIOD)
        sig = detect_divergence(candles, rsi, left=DIV_PIVOT_LEFT, right=DIV_PIVOT_RIGHT, freshness=DIV_FRESHNESS_BARS)
        if not sig:
            return
        if has_open_divergence_signal(symbol):
            return

        now = time.time()
        with _div_cooldowns_lock:
            last_ts = _div_cooldowns.get(symbol, 0)
            allowed = now - last_ts >= DIV_COOLDOWN_SEC
            if allowed:
                _div_cooldowns[symbol] = now
        if not allowed:
            return

        entry = candles[-1]["close"]
        sl, tp, risk = compute_div_tp_sl(sig["direction"], entry, sig)
        if entry and risk / entry > DIV_MAX_RISK_PCT:
            return  # pivot too far from current price — SL/TP would be oversized, not a real setup
        record = {
            "symbol": symbol,
            "direction": sig["direction"],
            "kind": sig["kind"],  # bearish / bullish
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "risk": risk,
            "price_p1": sig["price_p1"], "price_p2": sig["price_p2"],
            "rsi_p1": sig["rsi_p1"], "rsi_p2": sig["rsi_p2"],
            "time_p1": sig["time_p1"], "time_p2": sig["time_p2"],
            "rsi_time_p1": sig["rsi_time_p1"], "rsi_time_p2": sig["rsi_time_p2"],
            "time": candles[-1]["time"],
            "detected_at": now,
            "status": "OPEN",
            "result": None,
            "closed_at": None,
            "exit_price": None,
            "exit_time": None,
            "exit_candle": None,
            "app_version": APP_VERSION,
            "mfe_r": 0.0,
            "mae_r": 0.0,
            "mfe_price": None,
            "mae_price": None,
            "mfe_tracking_until": now + MFE_TRACK_SEC,
        }
        with state_lock:
            STATE["div_signals"].appendleft(record)
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        send_telegram(
            f"{arrow} {symbol} (RSI {sig['kind']} divergence)\n"
            f"entry: {entry:.6g}\n"
            f"SL: {sl:.6g}  TP: {tp:.6g}  (RR {DIV_RR:g})"
        )
    except Exception as e:
        log_error(f"div {symbol}: {e}")


def close_div_signal(sig, result, exit_price, exit_candle=None):
    with state_lock:
        sig["status"] = "CLOSED"
        sig["result"] = result
        sig["exit_price"] = exit_price
        sig["closed_at"] = time.time()
        sig["mfe_r_at_close"] = sig["mfe_r"]
        sig["mae_r_at_close"] = sig["mae_r"]
        if exit_candle:
            sig["exit_time"] = exit_candle["time"]
            sig["exit_candle"] = {
                "open": exit_candle["open"], "high": exit_candle["high"],
                "low": exit_candle["low"], "close": exit_candle["close"],
            }
    if result in ("WIN", "LOSS"):
        arrow = "\u2705" if result == "WIN" else "\u274c"
        send_telegram(f"{arrow} {sig['symbol']} divergence {sig['direction']} closed: {result} @ {exit_price:.6g}")


def update_divergence_outcomes():
    now = time.time()
    with state_lock:
        active = [
            s for s in STATE["div_signals"]
            if s.get("status") == "OPEN" or now < s.get("mfe_tracking_until", 0)
        ]
    for sig in active:
        try:
            candles = get_candles(sig["symbol"], interval=DIV_INTERVAL, limit=300)
            relevant = [c for c in candles if c["time"] > sig["time"]]
            direction = sig["direction"]
            entry = sig["entry"]
            risk = sig.get("risk") or abs(entry - sig["sl"]) or 1e-9

            for c in relevant:
                if direction == "LONG":
                    fav, adv = c["high"] - entry, entry - c["low"]
                else:
                    fav, adv = entry - c["low"], c["high"] - entry
                fav_r, adv_r = fav / risk, adv / risk
                if fav_r > sig["mfe_r"] or adv_r > sig["mae_r"]:
                    with state_lock:
                        if fav_r > sig["mfe_r"]:
                            sig["mfe_r"] = round(fav_r, 3)
                            sig["mfe_price"] = c["high"] if direction == "LONG" else c["low"]
                        if adv_r > sig["mae_r"]:
                            sig["mae_r"] = round(adv_r, 3)
                            sig["mae_price"] = c["low"] if direction == "LONG" else c["high"]

                if sig["status"] == "OPEN":
                    if direction == "LONG":
                        if c["low"] <= sig["sl"]:
                            close_div_signal(sig, "LOSS", sig["sl"], exit_candle=c)
                        elif c["high"] >= sig["tp"]:
                            close_div_signal(sig, "WIN", sig["tp"], exit_candle=c)
                    else:
                        if c["high"] >= sig["sl"]:
                            close_div_signal(sig, "LOSS", sig["sl"], exit_candle=c)
                        elif c["low"] <= sig["tp"]:
                            close_div_signal(sig, "WIN", sig["tp"], exit_candle=c)

            if sig["status"] == "OPEN" and now - sig["detected_at"] > SIGNAL_TIMEOUT_SEC:
                last_price = candles[-1]["close"] if candles else entry
                close_div_signal(sig, "TIMEOUT", last_price)
        except Exception as e:
            log_error(f"update_divergence_outcomes {sig.get('symbol')}: {e}")


def compute_divergence_stats():
    with state_lock:
        signals = list(STATE["div_signals"])
    closed = [s for s in signals if s.get("status") == "CLOSED" and s.get("result") in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = sum(1 for s in closed if s["result"] == "LOSS")
    total = wins + losses
    timeouts = sum(1 for s in signals if s.get("result") == "TIMEOUT")
    open_count = sum(1 for s in signals if s.get("status") == "OPEN")
    winrate = round(wins / total * 100, 1) if total else None

    dataset = [s for s in signals if s.get("mfe_price") is not None]

    def agg(key, subset):
        vals = [s[key] for s in subset if s.get(key) is not None]
        if not vals:
            return None
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        return {
            "avg": round(sum(vals) / n, 3),
            "median": round(vals_sorted[n // 2], 3),
            "p25": round(vals_sorted[int(n * 0.25)], 3),
            "p75": round(vals_sorted[min(int(n * 0.75), n - 1)], 3),
            "n": n,
        }

    win_set = [s for s in dataset if s.get("result") == "WIN"]
    loss_set = [s for s in dataset if s.get("result") == "LOSS"]
    open_set = [s for s in dataset if s.get("status") == "OPEN"]

    return {
        "open": open_count, "wins": wins, "losses": losses,
        "timeouts": timeouts, "winrate": winrate, "closed_total": total,
        "mfe_r_all": agg("mfe_r", dataset), "mae_r_all": agg("mae_r", dataset),
        "mfe_r_wins": agg("mfe_r", win_set), "mae_r_wins": agg("mae_r", win_set),
        "mfe_r_losses": agg("mfe_r", loss_set), "mae_r_losses": agg("mae_r", loss_set),
        "mfe_r_open": agg("mfe_r", open_set), "mae_r_open": agg("mae_r", open_set),
        "mfe_r_wins_at_close": agg("mfe_r_at_close", win_set), "mae_r_wins_at_close": agg("mae_r_at_close", win_set),
        "mfe_r_losses_at_close": agg("mfe_r_at_close", loss_set), "mae_r_losses_at_close": agg("mae_r_at_close", loss_set),
        "dataset_count": len(dataset),
    }


def data_quality_check(candles):
    """Reject symbols whose candle feed itself looks illiquid/stale or
    unreliable: too many zero-volume bars, too many flat (high==low) bars,
    an average range too small relative to price (the "sideways dashes"
    look on thin/rarely-traded contracts), or a "sawtooth" pattern — price
    whipping direction almost every bar, mostly-wick candles, or frequent
    open/close gaps between bars, all of which make any zone built off the
    profile unreliable even though the raw volume numbers look fine.
    Returns (ok, reason)."""
    n = len(candles)
    if n < 20:
        return False, "too few candles"
    zero_vol = sum(1 for c in candles if c["volume"] <= 0)
    flat = sum(1 for c in candles if c["high"] <= c["low"])
    ranges = [(c["high"] - c["low"]) / c["close"] for c in candles if c["close"] > 0]
    avg_range_pct = sum(ranges) / len(ranges) if ranges else 0.0

    if zero_vol / n > MAX_ZERO_VOL_RATIO:
        return False, f"zero-volume bars {zero_vol}/{n}"
    if flat / n > MAX_FLAT_RATIO:
        return False, f"flat bars {flat}/{n}"
    if avg_range_pct < MIN_AVG_RANGE_PCT:
        return False, f"avg range {avg_range_pct:.5f} < {MIN_AVG_RANGE_PCT}"

    # direction flip ratio: how often bar-to-bar candle direction reverses
    directions = [1 if c["close"] > c["open"] else (-1 if c["close"] < c["open"] else 0) for c in candles]
    compared = flips = 0
    for i in range(1, n):
        if directions[i] != 0 and directions[i - 1] != 0:
            compared += 1
            if directions[i] != directions[i - 1]:
                flips += 1
    flip_ratio = flips / compared if compared else 0.0
    if flip_ratio > MAX_DIRECTION_FLIP_RATIO:
        return False, f"sawtooth direction flips {flip_ratio:.2f}"

    # wick ratio: how much of each bar's range is wick rather than body
    wick_ratios = []
    for c in candles:
        rng = c["high"] - c["low"]
        if rng > 0:
            wick_ratios.append((rng - abs(c["close"] - c["open"])) / rng)
    avg_wick_ratio = sum(wick_ratios) / len(wick_ratios) if wick_ratios else 0.0
    if avg_wick_ratio > MAX_AVG_WICK_RATIO:
        return False, f"mostly-wick candles {avg_wick_ratio:.2f}"

    # gap ratio: bars whose open jumps away from the prior close
    gaps = 0
    for i in range(1, n):
        prev_close = candles[i - 1]["close"]
        if prev_close > 0 and abs(candles[i]["open"] - prev_close) / prev_close > GAP_THRESHOLD_PCT:
            gaps += 1
    gap_ratio = gaps / (n - 1) if n > 1 else 0.0
    if gap_ratio > MAX_GAP_RATIO:
        return False, f"gappy bars {gap_ratio:.2f}"

    # efficiency ratio: net displacement vs total path length. Low value =
    # price traveled a lot but ended up nowhere — classic sawtooth, even
    # when no single metric above crosses its own threshold.
    net_move = abs(candles[-1]["close"] - candles[0]["close"])
    path_length = sum(abs(candles[i]["close"] - candles[i - 1]["close"]) for i in range(1, n))
    efficiency = net_move / path_length if path_length > 0 else 1.0
    if efficiency < MIN_EFFICIENCY_RATIO:
        return False, f"low efficiency ratio {efficiency:.3f} (chop, little net progress)"

    return True, None


def log_error(msg):
    print("[ERR]", msg)
    with state_lock:
        STATE["errors"].append({"t": time.time(), "msg": str(msg)[:500]})


# ----------------------------------------------------------------------------
# Gate.io REST helpers (public endpoints, no auth needed)
# ----------------------------------------------------------------------------
def get_contracts():
    r = requests.get(f"{GATE_BASE}/futures/usdt/contracts", timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _parse_candles(raw):
    out = []
    for c in raw:
        out.append({
            "time": int(c.get("t", 0)),
            "open": float(c.get("o", 0)),
            "high": float(c.get("h", 0)),
            "low": float(c.get("l", 0)),
            "close": float(c.get("c", 0)),
            "volume": abs(float(c.get("v", 0))),
        })
    out.sort(key=lambda x: x["time"])
    return out


def get_candles(symbol, interval=INTERVAL, limit=LOOKBACK + 5):
    r = requests.get(
        f"{GATE_BASE}/futures/usdt/candlesticks",
        params={"contract": symbol, "interval": interval, "limit": limit},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    # Gate.io returns oldest->newest already; fields: t,v,c,h,l,o,sum (varies by version)
    return _parse_candles(r.json())


def get_contract_stats(symbol, interval=OI_INTERVAL, limit=OI_LOOKBACK + 2):
    """Open interest history via GET /futures/usdt/contract_stats."""
    r = requests.get(
        f"{GATE_BASE}/futures/usdt/contract_stats",
        params={"contract": symbol, "interval": interval, "limit": limit},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for c in r.json():
        try:
            out.append({"time": int(c.get("time", 0)), "open_interest": float(c.get("open_interest", 0))})
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["time"])
    return out


def get_candles_range(symbol, interval, start_ts, end_ts):
    """Fetch every candle in [start_ts, end_ts] at a finer interval than the
    main scan uses, paginating since the API caps each response (~2000
    points) and rejects combining `limit` with `from`/`to`. Used to build
    the volume profile from actual sub-bar data instead of approximating
    each parent bar's volume as spread evenly across its own high-low
    range — the same "bar magnification" idea as the original indicator,
    just implemented via REST polling instead of Pine's request.security_lower_tf."""
    interval_sec = INTERVAL_SECONDS.get(interval, 60)
    chunk_span = interval_sec * 1900  # a little under the ~2000-point cap, for safety
    seen = {}
    cur = int(start_ts)
    end_ts = int(end_ts)
    while cur < end_ts:
        chunk_end = min(cur + chunk_span, end_ts)
        r = requests.get(
            f"{GATE_BASE}/futures/usdt/candlesticks",
            params={"contract": symbol, "interval": interval, "from": cur, "to": chunk_end},
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        for c in _parse_candles(r.json()):
            seen[c["time"]] = c
        cur = chunk_end
    return sorted(seen.values(), key=lambda x: x["time"])


def get_tickers():
    r = requests.get(f"{GATE_BASE}/futures/usdt/tickers", timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def build_universe():
    # Volume fields (volume_24h_quote/_settle/_base) live on the /tickers
    # endpoint, not /contracts — /contracts has no volume data at all.
    tickers = get_tickers()
    best_vol = {}
    for t in tickers:
        name = t.get("contract", "")
        if not name.endswith("_USDT"):
            continue
        vol = t.get("volume_24h_quote") or t.get("volume_24h_settle") or t.get("volume_24h") or 0
        try:
            vol = float(vol)
        except (TypeError, ValueError):
            vol = 0.0
        if vol < MIN_VOL_USD:
            continue
        # dedupe: if a name shows up more than once (seen in practice —
        # caused two concurrent scan_symbol() calls for the same symbol,
        # which raced on the cooldown check and produced duplicate
        # signals), keep the higher-volume reading.
        if name not in best_vol or vol > best_vol[name]:
            best_vol[name] = vol
    scored = sorted(best_vol.items(), key=lambda x: -x[1])
    return [s[0] for s in scored[:MAX_SYMBOLS]]


# ----------------------------------------------------------------------------
# Volume profile (fixed range, bar-level proportional overlap)
# Mirrors the Pine Script logic: split [lowest_low, highest_high] into SEGS
# bins, then for every candle in the lookback window distribute its volume
# across the bins it overlaps, weighted by the fraction of the candle's
# high-low range inside each bin.
# ----------------------------------------------------------------------------
def _distribute_volume(source_candles, borders, hh, inc, segs):
    bin_vols = [0.0] * segs
    for c in source_candles:
        ch, cl, cv = c["high"], c["low"], c["volume"]
        if cv <= 0:
            continue
        diff = ch - cl
        if diff <= 0:
            idx = min(max(int((hh - ch) / inc), 0), segs - 1)
            bin_vols[idx] += cv
            continue
        for b in range(segs):
            t_border = borders[b]
            b_border = borders[b + 1]
            if cl <= t_border and ch >= b_border:
                top_reg = min(ch, t_border)
                bot_reg = max(cl, b_border)
                overlap = top_reg - bot_reg
                if overlap > 0:
                    bin_vols[b] += cv * (overlap / diff)
    return bin_vols


def compute_profile(candles, segs=SEGS, lookback=LOOKBACK):
    window = candles[-lookback:]
    if len(window) < 10:
        return None
    hh = max(c["high"] for c in window)
    ll = min(c["low"] for c in window)
    if hh <= ll:
        return None
    inc = (hh - ll) / segs
    # borders[0] = hh (top), borders[segs] = ll (bottom), descending
    borders = [hh - inc * i for i in range(segs + 1)]
    bin_vols = _distribute_volume(window, borders, hh, inc, segs)
    return {"borders": borders, "bin_vols": bin_vols, "hh": hh, "ll": ll, "inc": inc}


def compute_profile_magnified(main_window, sub_candles, segs=SEGS):
    """Same fixed-range profile as compute_profile, but the volume
    distribution comes from real finer-interval sub-bars instead of
    approximating each parent bar's volume as spread evenly across its own
    high-low range — mirrors the original indicator's lower-timeframe
    bar-magnification approach. The price range (hh/ll/borders) still
    comes from the parent-timeframe window, only the volume attribution
    granularity changes."""
    if len(main_window) < 10 or not sub_candles:
        return None
    hh = max(c["high"] for c in main_window)
    ll = min(c["low"] for c in main_window)
    if hh <= ll:
        return None
    inc = (hh - ll) / segs
    borders = [hh - inc * i for i in range(segs + 1)]
    bin_vols = _distribute_volume(sub_candles, borders, hh, inc, segs)
    return {"borders": borders, "bin_vols": bin_vols, "hh": hh, "ll": ll, "inc": inc}


def build_profile_for_symbol(symbol, candles, lookback, segs=SEGS, interval=INTERVAL):
    """Preferred entry point for building a symbol's profile: uses real
    sub-bar data when magnification is enabled, falling back to the
    same-timeframe approximation if the magnified fetch fails for any
    reason (thin sub-interval history, a transient API error, etc.) so a
    network hiccup on the extra request doesn't take the symbol out of
    the scan entirely."""
    window = candles[-lookback:]
    if len(window) < 10:
        return None
    if MAGNIFY_ENABLED:
        try:
            magnify_interval = MAGNIFY_INTERVAL if interval == INTERVAL else pick_magnify_interval(interval)
            start_ts = window[0]["time"]
            end_ts = window[-1]["time"] + INTERVAL_SECONDS.get(interval, 300)
            sub_candles = get_candles_range(symbol, magnify_interval, start_ts, end_ts)
            profile = compute_profile_magnified(window, sub_candles, segs=segs)
            if profile:
                return profile
        except Exception as e:
            log_error(f"magnified profile {symbol}: {e}")
    return compute_profile(candles, segs=segs, lookback=lookback)


def _extract_hvn_zones_shoulder(profile, top_n, min_peak_ratio, shoulder_pct):
    """Grow each zone outward from a local volume peak while neighboring
    bins stay >= shoulder_pct of that peak's volume, stopping right where
    the bars visibly get shorter — rather than merging together a fixed
    top-N bins by rank, which could cut a zone short mid-shoulder or
    merge two genuinely separate peaks into one. A zone can legitimately
    come out wide if the underlying volume plateau is wide — the shoulder
    threshold is what keeps it honest, not a separate height cap."""
    borders = profile["borders"]
    bin_vols = profile["bin_vols"]
    segs = len(bin_vols)

    avg_vol = sum(bin_vols) / segs if segs else 0
    max_vol = max(bin_vols) if bin_vols else 0
    if min_peak_ratio and avg_vol > 0 and max_vol < avg_vol * min_peak_ratio:
        return []

    ranked = sorted(range(segs), key=lambda i: -bin_vols[i])
    used = set()
    zones = []
    for idx in ranked:
        if len(zones) >= top_n:
            break
        if idx in used or bin_vols[idx] <= 0:
            continue
        peak_vol = bin_vols[idx]
        threshold = peak_vol * shoulder_pct
        lo = hi = idx
        while lo - 1 >= 0 and (lo - 1) not in used and bin_vols[lo - 1] >= threshold:
            lo -= 1
        while hi + 1 < segs and (hi + 1) not in used and bin_vols[hi + 1] >= threshold:
            hi += 1
        for k in range(lo, hi + 1):
            used.add(k)
        top = borders[lo]
        bottom = borders[hi + 1]
        vol = sum(bin_vols[lo:hi + 1])
        zones.append({"top": top, "bottom": bottom, "mid": (top + bottom) / 2, "volume": vol})

    zones.sort(key=lambda z: -z["volume"])
    return zones


def _extract_hvn_zones_topn(profile, top_n, min_peak_ratio, max_height_frac):
    """Pre-v0.13 method: take the top_n highest-volume bins and merge
    adjacent ones into contiguous zones, dropping any merged zone taller
    than max_height_frac of the whole profile range. Restored as an
    option after user feedback that v0.12-13 together cut signal volume
    too much — lets that be isolated/reverted independently of the
    other fixes shipped since."""
    borders = profile["borders"]
    bin_vols = profile["bin_vols"]
    segs = len(bin_vols)
    total_range = max(profile["hh"] - profile["ll"], 1e-12)

    avg_vol = sum(bin_vols) / segs if segs else 0
    max_vol = max(bin_vols) if bin_vols else 0
    if min_peak_ratio and avg_vol > 0 and max_vol < avg_vol * min_peak_ratio:
        return []

    ranked = sorted(range(segs), key=lambda i: -bin_vols[i])[:top_n]
    ranked_set = set(ranked)
    zones = []
    used = set()
    for idx in sorted(ranked_set):
        if idx in used:
            continue
        lo = hi = idx
        while (lo - 1) in ranked_set and (lo - 1) not in used:
            lo -= 1
        while (hi + 1) in ranked_set and (hi + 1) not in used:
            hi += 1
        for k in range(lo, hi + 1):
            used.add(k)
        top = borders[lo]
        bottom = borders[hi + 1]
        height = top - bottom
        if max_height_frac and height / total_range > max_height_frac:
            continue
        vol = sum(bin_vols[lo:hi + 1])
        zones.append({"top": top, "bottom": bottom, "mid": (top + bottom) / 2, "volume": vol})

    zones.sort(key=lambda z: -z["volume"])
    return zones


def extract_hvn_zones(profile, top_n=HVN_TOP_N, min_peak_ratio=MIN_PEAK_RATIO,
                       shoulder_pct=SHOULDER_THRESHOLD_PCT, method=None):
    """If the whole profile is flat (no bin meaningfully busier than
    average), there's no real POC to trade at all — both methods return
    no zones rather than pretending the busiest bin means something."""
    method = method or ZONE_METHOD
    if method == "topn":
        return _extract_hvn_zones_topn(profile, top_n, min_peak_ratio, LEGACY_MAX_ZONE_HEIGHT_FRAC)
    return _extract_hvn_zones_shoulder(profile, top_n, min_peak_ratio, shoulder_pct)


def eligible_zones(zones, min_ratio=ZONE_STRENGTH_MIN_RATIO):
    """Restrict to zones strong enough, relative to the POC, to actually
    trade off of. Weaker zones still show on the chart but won't fire
    signals on their own."""
    if not zones:
        return []
    top_vol = zones[0]["volume"]
    if top_vol <= 0:
        return zones
    return [z for z in zones if z["volume"] >= top_vol * min_ratio]


def poc_zone(zones):
    return zones[0] if zones else None


# ----------------------------------------------------------------------------
# Signal detection
# ----------------------------------------------------------------------------
def detect_signal(candles, zones):
    """Bounce/rejection: a wick pokes into the zone and the bar closes back
    outside it, in the same direction the prior close was already on."""
    if len(candles) < 3 or not zones:
        return None
    prev, last = candles[-2], candles[-1]
    for zone in zones:
        top, bottom = zone["top"], zone["bottom"]
        touched = last["low"] <= top and last["high"] >= bottom
        if not touched:
            continue
        if prev["close"] > top and last["close"] > top:
            return {"direction": "LONG", "zone": zone, "price": last["close"], "time": last["time"], "reason": "bounce"}
        if prev["close"] < bottom and last["close"] < bottom:
            return {"direction": "SHORT", "zone": zone, "price": last["close"], "time": last["time"], "reason": "bounce"}
    return None


def detect_breakout(candles, zones, min_bars_inside=BREAKOUT_MIN_BARS_INSIDE):
    """Breakout: price was basing in/around the zone for several bars, then
    this bar clears an edge decisively — the "launch off the node" pattern,
    as opposed to a single-wick rejection."""
    if len(candles) < min_bars_inside + 2 or not zones:
        return None
    last = candles[-1]
    window = candles[-(min_bars_inside + 1):-1]
    for zone in zones:
        top, bottom = zone["top"], zone["bottom"]
        height = max(top - bottom, 1e-12)
        inside_count = sum(1 for c in window if c["low"] <= top and c["high"] >= bottom)
        if inside_count < max(2, min_bars_inside - 1):
            continue
        buf = height * 0.1
        if last["close"] > top + buf and last["low"] <= top + buf:
            return {"direction": "LONG", "zone": zone, "price": last["close"], "time": last["time"], "reason": "breakout"}
        if last["close"] < bottom - buf and last["high"] >= bottom - buf:
            return {"direction": "SHORT", "zone": zone, "price": last["close"], "time": last["time"], "reason": "breakout"}
    return None


def detect_any_signal(candles, zones, allowed_reasons=None):
    """Try a bounce first, then a breakout — either qualifies as a signal.
    Either type can be disabled independently (VP_BOUNCE_ENABLED /
    VP_BREAKOUT_ENABLED) for A/B-style comparisons if one type turns out
    to be underperforming the other. allowed_reasons, if given, overrides
    those globals for this call only — used to backtest bounce and
    breakout separately without any shared mutable state (thread-safe
    against concurrent live scanning)."""
    if allowed_reasons is None:
        allow_bounce, allow_breakout = BOUNCE_ENABLED, BREAKOUT_ENABLED
    else:
        allow_bounce, allow_breakout = "bounce" in allowed_reasons, "breakout" in allowed_reasons
    if allow_bounce:
        sig = detect_signal(candles, zones)
        if sig:
            return sig
    if allow_breakout:
        return detect_breakout(candles, zones)
    return None


# ----------------------------------------------------------------------------
# Signal filters: trend direction + volume confirmation
# ----------------------------------------------------------------------------
def compute_trend(candles, lookback=TREND_LOOKBACK, threshold_pct=TREND_THRESHOLD_PCT):
    """Net price change over the last `lookback` bars. Returns 'UP', 'DOWN',
    or 'NEUTRAL' — a coarse regime read, not a precise trend indicator."""
    if len(candles) < lookback + 1:
        return "NEUTRAL"
    window = candles[-lookback:]
    start, end = window[0]["close"], window[-1]["close"]
    if start <= 0:
        return "NEUTRAL"
    change = (end - start) / start
    if change > threshold_pct:
        return "UP"
    if change < -threshold_pct:
        return "DOWN"
    return "NEUTRAL"


def trend_allows(direction, trend):
    """In a clear trend, only take signals that go with it."""
    if not TREND_FILTER_ENABLED or trend == "NEUTRAL":
        return True
    return (trend == "UP" and direction == "LONG") or (trend == "DOWN" and direction == "SHORT")


def compute_oi_trend(symbol, lookback=OI_LOOKBACK, threshold_pct=OI_THRESHOLD_PCT, interval=OI_INTERVAL):
    """Net open-interest change over the lookback window. Returns 'UP'
    (OI growing — new positions opening), 'DOWN' (OI shrinking —
    positions unwinding), or 'NEUTRAL'. Any fetch/data problem degrades
    to NEUTRAL (never blocks a signal outright on a network hiccup)."""
    try:
        stats = get_contract_stats(symbol, interval=interval, limit=lookback + 2)
    except Exception as e:
        log_error(f"oi fetch {symbol}: {e}")
        return "NEUTRAL"
    if len(stats) < lookback:
        return "NEUTRAL"
    window = stats[-lookback:]
    start_oi, end_oi = window[0]["open_interest"], window[-1]["open_interest"]
    if start_oi <= 0:
        return "NEUTRAL"
    change = (end_oi - start_oi) / start_oi
    if change > threshold_pct:
        return "UP"
    if change < -threshold_pct:
        return "DOWN"
    return "NEUTRAL"


def oi_allows(direction, oi_trend):
    """Rising OI backs a breakout in the same direction as the move
    (new money); falling OI (unwinding) doesn't back a fresh breakout in
    either direction as strongly — only the matching direction passes."""
    if not OI_FILTER_ENABLED or oi_trend == "NEUTRAL":
        return True
    return (oi_trend == "UP" and direction == "LONG") or (oi_trend == "DOWN" and direction == "SHORT")


def volume_confirms(candles, min_ratio=VOL_CONFIRM_RATIO, lookback=VOL_CONFIRM_LOOKBACK):
    """The trigger bar (the last candle) should have above-average volume
    versus the bars right before it — a touch/breakout on thin volume is
    more likely noise than a real move."""
    if not VOLUME_CONFIRM_ENABLED:
        return True
    if len(candles) < lookback + 1:
        return True  # not enough history to judge, don't block on it
    trigger = candles[-1]
    prior = candles[-(lookback + 1):-1]
    avg_vol = sum(c["volume"] for c in prior) / len(prior) if prior else 0
    if avg_vol <= 0:
        return True
    return trigger["volume"] >= avg_vol * min_ratio


def signal_passes_filters(candles, sig):
    """Apply trend + volume filters to a candidate signal. candles is the
    full series ending at the trigger bar (candles[-1] == trigger)."""
    if sig is None:
        return False
    trend = compute_trend(candles)
    if not trend_allows(sig["direction"], trend):
        return False
    if not volume_confirms(candles):
        return False
    return True


def nearest_zone_distance(price, zones):
    best = None
    best_dist = None
    for z in zones:
        if price > z["top"]:
            d = (price - z["top"]) / price
        elif price < z["bottom"]:
            d = (z["bottom"] - price) / price
        else:
            d = 0.0
        if best_dist is None or d < best_dist:
            best_dist = d
            best = z
    return best, best_dist


def compute_tp_sl(direction, entry, zone, rr=None, buffer_pct=None):
    """Stop sits just beyond the far edge of the HVN zone (the level that,
    if broken, invalidates the bounce). Take-profit is RR multiples of that
    risk distance."""
    rr = RR if rr is None else rr
    buffer_pct = ZONE_BUFFER_PCT if buffer_pct is None else buffer_pct
    zone_height = max(zone["top"] - zone["bottom"], entry * 0.0005)
    buffer = max(zone_height * buffer_pct, entry * 0.0005)
    if direction == "LONG":
        sl = zone["bottom"] - buffer
        risk = entry - sl
        tp = entry + risk * rr
    else:
        sl = zone["top"] + buffer
        risk = sl - entry
        tp = entry - risk * rr
    return sl, tp, risk


# ----------------------------------------------------------------------------
# Per-symbol parameter optimizer: walk-forward backtest over a small grid
# (lookback / HVN top-n / RR) to find the combo with the best historical
# win rate for THIS symbol, then use that combo for its live signals.
# Triggered on demand (UI "Оптимизировать" button) rather than for the
# whole universe every cycle — a phone CPU can't grid-search 150 symbols
# on a schedule, but one symbol on tap is fine.
# ----------------------------------------------------------------------------
BT_SEGS = int(os.environ.get("VP_BT_SEGS", 40))
BT_HISTORY = int(os.environ.get("VP_BT_HISTORY", 500))
BT_STRIDE = int(os.environ.get("VP_BT_STRIDE", 2))
MIN_BACKTEST_TRADES = int(os.environ.get("VP_BT_MIN_TRADES", 6))
AUTO_TUNE_ENABLED = os.environ.get("VP_AUTO_TUNE", "1") == "1"
AUTO_TUNE_PER_CYCLE = int(os.environ.get("VP_AUTO_TUNE_PER_CYCLE", 1))  # how many symbols get (re-)tuned per scan cycle — kept low, each tune costs several seconds of CPU on top of the regular scan
AUTO_TUNE_REFRESH_SEC = int(os.environ.get("VP_AUTO_TUNE_REFRESH_SEC", 48 * 3600))  # re-tune a symbol once its override is this old — price behavior drifts
PARAM_GRID_LOOKBACK = [60, 100, 150]
PARAM_GRID_HVN = [3, 6, 9]
PARAM_GRID_RR = [1.5, 2.0, 2.5]              # data showed WIN median MFE ~2.8R, so the old 1.0 floor rarely won and was dropped in favor of testing further out
PARAM_GRID_BUFFER = [0.20, 0.35, 0.50]       # data showed LOSS median MFE ~1.7R (stopped out, then kept going the "right" way) — dropped the too-tight 0.15 floor, testing wider

SYMBOL_OVERRIDES = {}  # symbol -> {lookback, hvn_top_n, rr, buffer_pct, winrate, trades, optimized_at}

# Persist tuning + signal history to disk so a restart (e.g. to pick up a
# new version) doesn't throw away days of accumulated auto-tuning and
# win-rate stats. Best-effort: any failure here just logs and continues,
# the app runs fine on in-memory state alone if the file can't be written.
STATE_FILE = os.environ.get(
    "VP_STATE_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "vp_poc_state.json"),
)


def save_state():
    try:
        with state_lock:
            data = {
                "overrides": SYMBOL_OVERRIDES,
                "signals": list(STATE["signals"]),
                "div_signals": list(STATE["div_signals"]),
                "saved_at": time.time(),
            }
        tmp_path = STATE_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, STATE_FILE)
    except Exception as e:
        log_error(f"save_state: {e}")


def load_state():
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        SYMBOL_OVERRIDES.update(data.get("overrides", {}))
        signals = data.get("signals", [])
        div_signals = data.get("div_signals", [])
        with state_lock:
            STATE["signals"] = deque(signals, maxlen=SIGNAL_HISTORY)
            STATE["div_signals"] = deque(div_signals, maxlen=DIV_SIGNAL_HISTORY)
        print(f"Loaded persisted state: {len(SYMBOL_OVERRIDES)} overrides, {len(signals)} signals, {len(div_signals)} divergence signals")
    except Exception as e:
        log_error(f"load_state: {e}")


def backtest_params(candles, lookback, hvn_top_n, rr, buffer_pct=ZONE_BUFFER_PCT, segs=BT_SEGS, stride=BT_STRIDE, allowed_reasons=None):
    """Walk forward through history one trade at a time (no overlapping
    positions), using only data strictly before each candidate bar to build
    the profile — no lookahead. allowed_reasons restricts which signal
    type(s) count, for tuning bounce and breakout independently."""
    n = len(candles)
    start = lookback + 2
    if n <= start + 10:
        return {"trades": 0, "wins": 0, "losses": 0, "winrate": None}
    open_trade = None
    wins = losses = 0
    i = start
    while i < n:
        c = candles[i]
        if open_trade:
            if open_trade["direction"] == "LONG":
                if c["low"] <= open_trade["sl"]:
                    losses += 1
                    open_trade = None
                elif c["high"] >= open_trade["tp"]:
                    wins += 1
                    open_trade = None
            else:
                if c["high"] >= open_trade["sl"]:
                    losses += 1
                    open_trade = None
                elif c["low"] <= open_trade["tp"]:
                    wins += 1
                    open_trade = None
            i += 1
            continue

        window = candles[i - lookback:i]
        profile = compute_profile(window, segs=segs, lookback=lookback)
        if profile:
            zones = extract_hvn_zones(profile, top_n=hvn_top_n)
            strong_zones = eligible_zones(zones)
            trigger_series = window + [c]
            sig = detect_any_signal(trigger_series, strong_zones, allowed_reasons=allowed_reasons)
            if sig and signal_passes_filters(trigger_series, sig):
                direction = sig["direction"]
                entry = sig["price"]
                sl, tp, _ = compute_tp_sl(direction, entry, sig["zone"], rr=rr, buffer_pct=buffer_pct)
                open_trade = {"direction": direction, "sl": sl, "tp": tp}
        i += stride if not open_trade else 1

    total = wins + losses
    winrate = round(wins / total * 100, 1) if total else None
    return {"trades": total, "wins": wins, "losses": losses, "winrate": winrate}


def _optimize_for_reason(candles, reason):
    """Grid search restricted to a single signal type. Returns the best
    combo (or a best-effort one, with a note, if nothing clears the
    min-trades bar) — same selection logic as before, just scoped to one
    reason at a time."""
    best = None
    tried = []
    for lb in PARAM_GRID_LOOKBACK:
        for hvn in PARAM_GRID_HVN:
            for rr in PARAM_GRID_RR:
                for buf in PARAM_GRID_BUFFER:
                    res = backtest_params(candles, lb, hvn, rr, buffer_pct=buf, allowed_reasons={reason})
                    tried.append({**res, "lookback": lb, "hvn_top_n": hvn, "rr": rr, "buffer_pct": buf})
                    if res["trades"] < MIN_BACKTEST_TRADES or res["winrate"] is None:
                        continue
                    if best is None or res["winrate"] > best["winrate"] or \
                            (res["winrate"] == best["winrate"] and res["trades"] > best["trades"]):
                        best = {**res, "lookback": lb, "hvn_top_n": hvn, "rr": rr, "buffer_pct": buf}

    if best is None:
        tried.sort(key=lambda t: -t["trades"])
        best = tried[0] if tried else None
        if best:
            best["note"] = f"insufficient {reason} trades for a confident pick (<{MIN_BACKTEST_TRADES}); showing best-effort combo"
    return best


def optimize_symbol(symbol):
    """Tunes bounce and breakout completely independently — separate grid
    searches, separate best lookback/HVN/RR/buffer per type — since
    real data showed one can meaningfully underperform the other for the
    same symbol. Stores {"bounce": {...}, "breakout": {...}} instead of
    one shared set of params."""
    candles = get_candles(symbol, interval=INTERVAL, limit=BT_HISTORY)
    if len(candles) < 150:
        return {"error": "not enough history"}

    now = time.time()
    result = {}
    for reason in ("bounce", "breakout"):
        best = _optimize_for_reason(candles, reason)
        if best:
            best["optimized_at"] = now
            best["candles_used"] = len(candles)
        result[reason] = best

    with state_lock:
        SYMBOL_OVERRIDES[symbol] = result
    return result


_auto_tune_cursor = 0  # rotating pointer into the universe list, persists across cycles


def auto_tune_cycle(universe):
    """Background version of the "Оптимизировать" button: each scan cycle,
    (re-)tune a small number of symbols — new ones first, then whichever
    override is oldest — so that over time every symbol in the universe
    gets tuned, and stays tuned, without anyone having to tap a button.
    Deliberately slow (AUTO_TUNE_PER_CYCLE per cycle): a full 81-combo
    backtest costs real CPU, and doing it for 150 symbols at once would
    make a phone miss its scan cadence."""
    global _auto_tune_cursor
    if not AUTO_TUNE_ENABLED or not universe or AUTO_TUNE_PER_CYCLE <= 0:
        return
    now = time.time()

    def needs_tuning(sym):
        ov = SYMBOL_OVERRIDES.get(sym)
        if not ov:
            return True
        # oldest optimized_at across whichever reasons have a result at all
        timestamps = [r.get("optimized_at", 0) for r in ov.values() if r]
        if not timestamps:
            return True
        return (now - min(timestamps)) > AUTO_TUNE_REFRESH_SEC

    n = len(universe)
    candidates = []
    for i in range(n):
        sym = universe[(_auto_tune_cursor + i) % n]
        if needs_tuning(sym):
            candidates.append(sym)
        if len(candidates) >= AUTO_TUNE_PER_CYCLE:
            break
    _auto_tune_cursor = (_auto_tune_cursor + max(1, len(candidates))) % n

    for sym in candidates:
        try:
            optimize_symbol(sym)
        except Exception as e:
            log_error(f"auto_tune {sym}: {e}")


_div_stability_cursor = 0
DIV_STABILITY_PER_CYCLE = int(os.environ.get("VP_DIV_STABILITY_PER_CYCLE", 1))


def div_stability_cycle(universe):
    """Rotates through the universe (like auto_tune_cycle), one symbol per
    cycle, accumulating pivot-stability diagnostics — real data on how
    much VP_DIV_PIVOT_RIGHT could safely be reduced. Doesn't affect live
    detection at all, purely observational."""
    global _div_stability_cursor
    if not DIVERGENCE_ENABLED or not universe or DIV_STABILITY_PER_CYCLE <= 0 or not DIV_SHADOW_RIGHTS:
        return
    n = len(universe)
    picks = [universe[(_div_stability_cursor + i) % n] for i in range(min(DIV_STABILITY_PER_CYCLE, n))]
    _div_stability_cursor = (_div_stability_cursor + len(picks)) % n

    for symbol in picks:
        try:
            candles = get_candles(symbol, interval=DIV_INTERVAL, limit=DIV_FETCH_LIMIT)
            if len(candles) < DIV_RSI_PERIOD + DIV_PIVOT_LEFT + max(DIV_SHADOW_RIGHTS) + DIV_PIVOT_RIGHT + 10:
                continue
            highs = [c["high"] for c in candles]
            lows = [c["low"] for c in candles]
            closes = [c["close"] for c in candles]
            for shadow_r in DIV_SHADOW_RIGHTS:
                if shadow_r >= DIV_PIVOT_RIGHT:
                    continue
                a1, d1, g1 = simulate_pivot_stability(highs, closes, DIV_PIVOT_LEFT, DIV_PIVOT_RIGHT, shadow_r, "high")
                a2, d2, g2 = simulate_pivot_stability(lows, closes, DIV_PIVOT_LEFT, DIV_PIVOT_RIGHT, shadow_r, "low")
                gains = g1 + g2
                with state_lock:
                    bucket = STATE["div_pivot_stability"].setdefault(
                        str(shadow_r), {"agree": 0, "disagree": 0, "gain_sum": 0.0, "gain_count": 0})
                    bucket["agree"] += a1 + a2
                    bucket["disagree"] += d1 + d2
                    bucket["gain_sum"] += sum(gains)
                    bucket["gain_count"] += len(gains)
        except Exception as e:
            log_error(f"div_stability {symbol}: {e}")


# ----------------------------------------------------------------------------
# Telegram
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# Telegram — queued sender, mirrors the fix already proven in the
# EMA-screener/Pump_Radar project: Telegram Bot API has a real limit of
# ~1 message/sec per chat. Firing each alert in its own thread caused
# silent drops (429s) during bursts (e.g. several signals the same scan
# cycle). One background worker drains a queue sequentially with a pause
# between sends instead.
# ----------------------------------------------------------------------------
_telegram_send_queue = queue.Queue()


def _telegram_sender_worker():
    while True:
        task = _telegram_send_queue.get()
        try:
            task()
        except Exception as e:
            log_error(f"telegram queue: {e}")
        time.sleep(1.1)  # a little above Telegram's ~1 msg/sec/chat limit


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    def _do_send():
        for attempt in range(1, 4):
            try:
                r = requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
                    timeout=8,
                )
                if r.ok:
                    return
                log_error(f"telegram HTTP {r.status_code} (attempt {attempt}/3)")
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                log_error(f"telegram network (attempt {attempt}/3): {e}")
            except Exception as e:
                log_error(f"telegram send: {e} — not retrying (non-network error)")
                return
            if attempt < 3:
                time.sleep(5)

    _telegram_send_queue.put(_do_send)


# ----------------------------------------------------------------------------
# Per-symbol scan
# ----------------------------------------------------------------------------
def _try_signal(symbol, candles, candidate):
    """Apply trend/volume filters to a candidate signal, tracking which
    filter rejected it (if any) for the header's per-cycle counters."""
    if candidate is None:
        return None
    trend = compute_trend(candles)
    if not trend_allows(candidate["direction"], trend):
        with state_lock:
            STATE["filtered_by_trend"] += 1
        return None
    if not volume_confirms(candles):
        with state_lock:
            STATE["filtered_by_volume"] += 1
        return None
    return candidate


def scan_symbol(symbol):
    try:
        ov = SYMBOL_OVERRIDES.get(symbol, {}) or {}
        bounce_ov = ov.get("bounce") or {}
        breakout_ov = ov.get("breakout") or {}

        bounce_lookback = bounce_ov.get("lookback", LOOKBACK)
        bounce_hvn = bounce_ov.get("hvn_top_n", HVN_TOP_N)
        bounce_rr = bounce_ov.get("rr", RR_BOUNCE)
        bounce_buffer = bounce_ov.get("buffer_pct", BUFFER_PCT_BOUNCE)

        breakout_lookback = breakout_ov.get("lookback", LOOKBACK)
        breakout_hvn = breakout_ov.get("hvn_top_n", HVN_TOP_N)
        breakout_rr = breakout_ov.get("rr", RR_BREAKOUT)
        breakout_buffer = breakout_ov.get("buffer_pct", BUFFER_PCT_BREAKOUT)

        max_lookback = max(bounce_lookback, breakout_lookback)
        candles = get_candles(symbol, limit=max_lookback + 5)
        if len(candles) < 20:
            return

        ok, dq_reason = data_quality_check(candles[-max_lookback:])
        if not ok:
            with state_lock:
                STATE["watchlist"].pop(symbol, None)
                STATE["excluded_low_quality"] += 1
            return

        # Bounce and breakout can have independently-tuned lookback/HVN —
        # only rebuild the (network-costly, magnified) profile twice if
        # they actually differ; otherwise reuse the same one.
        profile_bounce = build_profile_for_symbol(symbol, candles, bounce_lookback, segs=SEGS) if BOUNCE_ENABLED else None
        if BREAKOUT_ENABLED and breakout_lookback == bounce_lookback and profile_bounce is not None:
            profile_breakout = profile_bounce
        elif BREAKOUT_ENABLED:
            profile_breakout = build_profile_for_symbol(symbol, candles, breakout_lookback, segs=SEGS)
        else:
            profile_breakout = None

        if not profile_bounce and not profile_breakout:
            return

        zones_bounce = extract_hvn_zones(profile_bounce, top_n=bounce_hvn) if profile_bounce else []
        zones_breakout = extract_hvn_zones(profile_breakout, top_n=breakout_hvn) if profile_breakout else []

        # Whichever set is available drives the watchlist/POC display —
        # informational only, doesn't affect signal generation.
        display_zones = zones_bounce or zones_breakout
        if not display_zones:
            return
        price = candles[-1]["close"]
        nz, dist = nearest_zone_distance(price, display_zones)
        poc = poc_zone(display_zones)

        with state_lock:
            STATE["watchlist"][symbol] = {
                "symbol": symbol,
                "price": price,
                "poc_top": poc["top"] if poc else None,
                "poc_bottom": poc["bottom"] if poc else None,
                "nearest_top": nz["top"] if nz else None,
                "nearest_bottom": nz["bottom"] if nz else None,
                "dist_pct": round(dist * 100, 3) if dist is not None else None,
                "updated": time.time(),
            }

        # Only narrow, POC-strength zones fire signals (weak/wide zones
        # still show on the chart, they just don't trade). Bounce is
        # tried first (matches the previous priority order), each against
        # its own zone set and its own tuned params.
        sig = None
        if BOUNCE_ENABLED and zones_bounce:
            sig = _try_signal(symbol, candles, detect_signal(candles, eligible_zones(zones_bounce)))
        if sig is None and BREAKOUT_ENABLED and zones_breakout:
            candidate = _try_signal(symbol, candles, detect_breakout(candles, eligible_zones(zones_breakout)))
            if candidate:
                oi_trend = compute_oi_trend(symbol)
                if oi_allows(candidate["direction"], oi_trend):
                    sig = candidate
                else:
                    with state_lock:
                        STATE["filtered_by_oi"] += 1

        if sig and has_open_signal(symbol):
            sig = None  # already have an unresolved signal on this symbol — don't stack another
        if sig:
            key = symbol
            now = time.time()
            with _cooldowns_lock:
                last_ts = _cooldowns.get(key, 0)
                allowed = now - last_ts >= COOLDOWN_SEC
                if allowed:
                    _cooldowns[key] = now
            if allowed:
                rr = bounce_rr if sig["reason"] == "bounce" else breakout_rr
                buffer_pct = bounce_buffer if sig["reason"] == "bounce" else breakout_buffer
                sl, tp, risk = compute_tp_sl(sig["direction"], sig["price"], sig["zone"], rr=rr, buffer_pct=buffer_pct)
                record = {
                    "symbol": symbol,
                    "direction": sig["direction"],
                    "reason": sig["reason"],
                    "price": sig["price"],
                    "entry": sig["price"],
                    "sl": sl,
                    "tp": tp,
                    "risk": risk,
                    "zone_top": sig["zone"]["top"],
                    "zone_bottom": sig["zone"]["bottom"],
                    "time": sig["time"],
                    "detected_at": now,
                    "status": "OPEN",
                    "result": None,
                    "closed_at": None,
                    "exit_price": None,
                    # app version at detection time — lets us later split
                    # stats "before/after this change" instead of lumping
                    # signals generated under different signal-generation
                    # logic into one aggregate.
                    "app_version": APP_VERSION,
                    # max favorable/adverse excursion, in R (risk) multiples —
                    # keeps updating for VP_MFE_TRACK_SEC after detection
                    # regardless of when/whether TP or SL is hit, so we can
                    # later see how much room there actually was to move
                    # TP/SL by.
                    "mfe_r": 0.0,
                    "mae_r": 0.0,
                    "mfe_price": None,
                    "mae_price": None,
                    "mfe_tracking_until": now + MFE_TRACK_SEC,
                }
                with state_lock:
                    STATE["signals"].appendleft(record)
                arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
                send_telegram(
                    f"{arrow} {symbol} ({sig['reason']})\n"
                    f"entry: {sig['price']:.6g}\n"
                    f"SL: {sl:.6g}  TP: {tp:.6g}  (RR {rr:g})\n"
                    f"HVN zone: {sig['zone']['bottom']:.6g} - {sig['zone']['top']:.6g}"
                )
    except Exception as e:
        log_error(f"{symbol}: {e}")


def close_signal(sig, result, exit_price, exit_candle=None):
    with state_lock:
        sig["status"] = "CLOSED"
        sig["result"] = result
        sig["exit_price"] = exit_price
        sig["closed_at"] = time.time()
        # mfe_r/mae_r keep growing for VP_MFE_TRACK_SEC after this (by
        # design, to see how much room there was to move TP/SL by) — but
        # that means they stop answering "how far did this trade actually
        # get before it resolved" the moment more candles arrive. Freeze
        # a snapshot right now, before that continues.
        sig["mfe_r_at_close"] = sig["mfe_r"]
        sig["mae_r_at_close"] = sig["mae_r"]
        if exit_candle:
            # exact candle that triggered the close, for direct
            # cross-checking against the exchange's own chart if a result
            # ever looks wrong on our canvas rendering
            sig["exit_time"] = exit_candle["time"]
            sig["exit_candle"] = {
                "open": exit_candle["open"], "high": exit_candle["high"],
                "low": exit_candle["low"], "close": exit_candle["close"],
            }
    if result in ("WIN", "LOSS"):
        arrow = "\u2705" if result == "WIN" else "\u274c"
        send_telegram(f"{arrow} {sig['symbol']} {sig['direction']} closed: {result} @ {exit_price:.6g}")


def update_signal_outcomes():
    now = time.time()
    with state_lock:
        active = [
            s for s in STATE["signals"]
            if s.get("status") == "OPEN" or now < s.get("mfe_tracking_until", 0)
        ]
    for sig in active:
        try:
            candles = get_candles(sig["symbol"], interval=INTERVAL, limit=300)
            # Strictly AFTER the trigger candle: that candle's own wick is
            # what produced the signal (its high/low drove the zone touch),
            # so checking it against SL/TP would count the very move that
            # created the signal as if it happened post-entry — closing
            # trades instantly and corrupting the win-rate stats.
            relevant = [c for c in candles if c["time"] > sig["time"]]
            direction = sig["direction"]
            entry = sig["entry"]
            risk = sig.get("risk") or abs(entry - sig["sl"]) or 1e-9

            for c in relevant:
                # --- MFE/MAE tracking (runs regardless of open/closed) ---
                if direction == "LONG":
                    fav, adv = c["high"] - entry, entry - c["low"]
                else:
                    fav, adv = entry - c["low"], c["high"] - entry
                fav_r, adv_r = fav / risk, adv / risk
                if fav_r > sig["mfe_r"] or adv_r > sig["mae_r"]:
                    with state_lock:
                        if fav_r > sig["mfe_r"]:
                            sig["mfe_r"] = round(fav_r, 3)
                            sig["mfe_price"] = c["high"] if direction == "LONG" else c["low"]
                        if adv_r > sig["mae_r"]:
                            sig["mae_r"] = round(adv_r, 3)
                            sig["mae_price"] = c["low"] if direction == "LONG" else c["high"]

                # --- TP/SL resolution (only while still open) ---
                if sig["status"] == "OPEN":
                    if direction == "LONG":
                        if c["low"] <= sig["sl"]:
                            close_signal(sig, "LOSS", sig["sl"], exit_candle=c)
                        elif c["high"] >= sig["tp"]:
                            close_signal(sig, "WIN", sig["tp"], exit_candle=c)
                    else:
                        if c["high"] >= sig["sl"]:
                            close_signal(sig, "LOSS", sig["sl"], exit_candle=c)
                        elif c["low"] <= sig["tp"]:
                            close_signal(sig, "WIN", sig["tp"], exit_candle=c)

            if sig["status"] == "OPEN" and now - sig["detected_at"] > SIGNAL_TIMEOUT_SEC:
                last_price = candles[-1]["close"] if candles else entry
                close_signal(sig, "TIMEOUT", last_price)
        except Exception as e:
            log_error(f"update_signal_outcomes {sig.get('symbol')}: {e}")


def compute_signal_stats():
    with state_lock:
        signals = list(STATE["signals"])
    closed = [s for s in signals if s.get("status") == "CLOSED" and s.get("result") in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = sum(1 for s in closed if s["result"] == "LOSS")
    total = wins + losses
    timeouts = sum(1 for s in signals if s.get("result") == "TIMEOUT")
    open_count = sum(1 for s in signals if s.get("status") == "OPEN")
    winrate = round(wins / total * 100, 1) if total else None

    by_reason = {}
    for reason in ("bounce", "breakout"):
        rc = [s for s in closed if s.get("reason") == reason]
        rw = sum(1 for s in rc if s["result"] == "WIN")
        rl = sum(1 for s in rc if s["result"] == "LOSS")
        rt = rw + rl
        by_reason[reason] = {"wins": rw, "losses": rl, "total": rt, "winrate": round(rw / rt * 100, 1) if rt else None}

    # signals detected under the currently-running version's signal logic —
    # lets a version bump that changes detection/filters be evaluated on
    # its own, instead of being diluted by older signals still in the
    # rolling history.
    cur = [s for s in closed if s.get("app_version") == APP_VERSION]
    cur_w = sum(1 for s in cur if s["result"] == "WIN")
    cur_l = sum(1 for s in cur if s["result"] == "LOSS")
    cur_t = cur_w + cur_l
    current_version = {
        "wins": cur_w, "losses": cur_l, "total": cur_t,
        "winrate": round(cur_w / cur_t * 100, 1) if cur_t else None,
    }

    return {
        "open": open_count, "wins": wins, "losses": losses,
        "timeouts": timeouts, "winrate": winrate, "closed_total": total,
        "by_reason": by_reason, "current_version": current_version,
    }


def _pct(vals, p):
    if not vals:
        return None
    vals = sorted(vals)
    idx = min(int(len(vals) * p), len(vals) - 1)
    return round(vals[idx], 3)


def compute_tuning_stats():
    """Aggregate MFE/MAE (in R multiples) across signals that have been
    tracked at least one cycle — the raw material for deciding whether
    TP/SL could sit further out or tighter in.

    Two versions of each number: the "_at_close" ones freeze the moment
    a trade actually resolved (WIN/LOSS/TIMEOUT) — "how far did this
    trade get before it was decided". The plain ones (mfe_r_all etc.)
    keep growing for VP_MFE_TRACK_SEC after that, by design, to see how
    much further room there was — but that means they also pick up
    whatever the market did AFTER the trade was already closed, which
    isn't really about that trade's own run. Use "_at_close" to judge
    "was this specific trade's TP/SL well-placed"; use the plain ones to
    judge "how much headroom exists in general". Older signals recorded
    before this distinction existed won't have "_at_close" values."""
    with state_lock:
        signals = list(STATE["signals"])
    dataset = [s for s in signals if s.get("mfe_price") is not None]
    if not dataset:
        return {"count": 0}

    def agg(key, subset):
        vals = [s[key] for s in subset if s.get(key) is not None]
        if not vals:
            return None
        return {
            "avg": round(sum(vals) / len(vals), 3),
            "median": _pct(vals, 0.5),
            "p25": _pct(vals, 0.25),
            "p75": _pct(vals, 0.75),
            "n": len(vals),
        }

    wins = [s for s in dataset if s.get("result") == "WIN"]
    losses = [s for s in dataset if s.get("result") == "LOSS"]
    still_open = [s for s in dataset if s.get("status") == "OPEN"]

    return {
        "count": len(dataset),
        "mfe_r_all": agg("mfe_r", dataset),
        "mae_r_all": agg("mae_r", dataset),
        "mfe_r_wins": agg("mfe_r", wins),
        "mae_r_wins": agg("mae_r", wins),
        "mfe_r_losses": agg("mfe_r", losses),
        "mae_r_losses": agg("mae_r", losses),
        "mfe_r_open": agg("mfe_r", still_open),
        "mae_r_open": agg("mae_r", still_open),
        "mfe_r_wins_at_close": agg("mfe_r_at_close", wins),
        "mae_r_wins_at_close": agg("mae_r_at_close", wins),
        "mfe_r_losses_at_close": agg("mfe_r_at_close", losses),
        "mae_r_losses_at_close": agg("mae_r_at_close", losses),
        "wins_n": len(wins), "losses_n": len(losses), "open_n": len(still_open),
    }


def scan_loop():
    while True:
        try:
            t0 = time.time()
            with state_lock:
                STATE["last_scan_started"] = t0
            universe = build_universe()
            with state_lock:
                STATE["universe_size"] = len(universe)
                STATE["excluded_low_quality"] = 0
                STATE["filtered_by_trend"] = 0
                STATE["filtered_by_volume"] = 0
                STATE["filtered_by_oi"] = 0
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futs = []
                if VOLUME_PROFILE_ENABLED:
                    futs += [ex.submit(scan_symbol, s) for s in universe]
                if DIVERGENCE_ENABLED:
                    futs += [ex.submit(scan_symbol_divergence, s) for s in universe]
                for _ in as_completed(futs):
                    pass
            if VOLUME_PROFILE_ENABLED:
                update_signal_outcomes()
                auto_tune_cycle(universe)
            if DIVERGENCE_ENABLED:
                update_divergence_outcomes()
                div_stability_cycle(universe)
            save_state()
            t1 = time.time()
            with state_lock:
                STATE["last_scan_finished"] = t1
                STATE["last_scan_duration"] = round(t1 - t0, 1)
                STATE["div_last_scan_finished"] = t1
                STATE["div_last_scan_duration"] = round(t1 - t0, 1)
        except Exception as e:
            log_error(f"scan_loop: {e}\n{traceback.format_exc()}")
        time.sleep(max(5, SCAN_INTERVAL_SEC))


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------
@app.route("/api/status")
def api_status():
    stats = compute_signal_stats()
    with state_lock:
        tuned_count = len(SYMBOL_OVERRIDES)
        return jsonify({
            "version": APP_VERSION,
            "volume_profile_enabled": VOLUME_PROFILE_ENABLED,
            "universe_size": STATE["universe_size"],
            "excluded_low_quality": STATE["excluded_low_quality"],
            "filtered_by_trend": STATE["filtered_by_trend"],
            "filtered_by_volume": STATE["filtered_by_volume"],
            "filtered_by_oi": STATE["filtered_by_oi"],
            "last_scan_started": STATE["last_scan_started"],
            "last_scan_finished": STATE["last_scan_finished"],
            "last_scan_duration": STATE["last_scan_duration"],
            "errors": list(STATE["errors"])[-10:],
            "stats": stats,
            "auto_tune": {
                "enabled": AUTO_TUNE_ENABLED,
                "per_cycle": AUTO_TUNE_PER_CYCLE,
                "tuned_symbols": tuned_count,
                "refresh_hours": round(AUTO_TUNE_REFRESH_SEC / 3600, 1),
            },
            "config": {
                "segs": SEGS, "lookback": LOOKBACK, "interval": INTERVAL,
                "hvn_top_n": HVN_TOP_N, "min_vol_usd": MIN_VOL_USD,
                "max_symbols": MAX_SYMBOLS, "scan_interval": SCAN_INTERVAL_SEC,
                "cooldown": COOLDOWN_SEC, "rr": RR,
                "max_zero_vol_ratio": MAX_ZERO_VOL_RATIO, "max_flat_ratio": MAX_FLAT_RATIO,
                "min_avg_range_pct": MIN_AVG_RANGE_PCT,
                "max_direction_flip_ratio": MAX_DIRECTION_FLIP_RATIO,
                "max_avg_wick_ratio": MAX_AVG_WICK_RATIO,
                "gap_threshold_pct": GAP_THRESHOLD_PCT, "max_gap_ratio": MAX_GAP_RATIO,
                "min_efficiency_ratio": MIN_EFFICIENCY_RATIO,
                "shoulder_threshold_pct": SHOULDER_THRESHOLD_PCT, "min_peak_ratio": MIN_PEAK_RATIO,
                "zone_method": ZONE_METHOD,
                "trend_filter_enabled": TREND_FILTER_ENABLED, "trend_lookback": TREND_LOOKBACK,
                "trend_threshold_pct": TREND_THRESHOLD_PCT,
                "volume_confirm_enabled": VOLUME_CONFIRM_ENABLED, "vol_confirm_ratio": VOL_CONFIRM_RATIO,
                "bounce_enabled": BOUNCE_ENABLED, "breakout_enabled": BREAKOUT_ENABLED,
                "oi_filter_enabled": OI_FILTER_ENABLED, "oi_interval": OI_INTERVAL,
                "oi_lookback": OI_LOOKBACK, "oi_threshold_pct": OI_THRESHOLD_PCT,
                "magnify_enabled": MAGNIFY_ENABLED, "magnify_interval": MAGNIFY_INTERVAL,
                "magnify_target_ratio": MAGNIFY_TARGET_RATIO,
            },
        })


@app.route("/api/watchlist")
def api_watchlist():
    with state_lock:
        rows = list(STATE["watchlist"].values())
    rows.sort(key=lambda r: (r["dist_pct"] if r["dist_pct"] is not None else 1e9))
    return jsonify(rows)


@app.route("/api/signals")
def api_signals():
    with state_lock:
        return jsonify(list(STATE["signals"]))


@app.route("/api/tuning")
def api_tuning():
    result = compute_tuning_stats()
    result["mfe_track_hours"] = round(MFE_TRACK_SEC / 3600, 1)
    return jsonify(result)


@app.route("/api/profile/<symbol>")
def api_profile(symbol):
    all_ov = SYMBOL_OVERRIDES.get(symbol, {}) or {}
    reason = request.args.get("reason", "bounce")
    if reason not in ("bounce", "breakout"):
        reason = "bounce"
    ov = all_ov.get(reason) or {}
    default_rr = RR_BOUNCE if reason == "bounce" else RR_BREAKOUT
    default_buffer = BUFFER_PCT_BOUNCE if reason == "bounce" else BUFFER_PCT_BREAKOUT

    interval = request.args.get("interval", INTERVAL)
    lookback = int(request.args.get("lookback", ov.get("lookback", LOOKBACK)))
    hvn_top_n = int(request.args.get("hvn_top_n", ov.get("hvn_top_n", HVN_TOP_N)))
    try:
        candles = get_candles(symbol, interval=interval, limit=lookback + 5)
        profile = build_profile_for_symbol(symbol, candles, lookback, segs=SEGS, interval=interval)
        if not profile:
            return jsonify({"error": "not enough data"}), 400
        zones = extract_hvn_zones(profile, top_n=hvn_top_n)
        strong_mids = {z["mid"] for z in eligible_zones(zones)}
        for z in zones:
            z["eligible"] = z["mid"] in strong_mids
        return jsonify({
            "symbol": symbol,
            "reason": reason,
            "candles": candles[-lookback:],
            "borders": profile["borders"],
            "bin_vols": profile["bin_vols"],
            "zones": zones,
            "params": {"lookback": lookback, "hvn_top_n": hvn_top_n, "rr": ov.get("rr", default_rr), "buffer_pct": ov.get("buffer_pct", default_buffer)},
            "override": ov if ov else None,
            "all_overrides": all_ov if all_ov else None,
        })
    except Exception as e:
        log_error(f"api_profile {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/optimize/<symbol>", methods=["POST"])
def api_optimize(symbol):
    try:
        result = optimize_symbol(symbol)
        if result is None:
            return jsonify({"error": "optimization failed"}), 500
        save_state()
        return jsonify(result)
    except Exception as e:
        log_error(f"api_optimize {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/overrides")
def api_overrides():
    return jsonify(SYMBOL_OVERRIDES)


@app.route("/api/divergence/status")
def api_divergence_status():
    stats = compute_divergence_stats()
    with state_lock:
        stability_raw = {k: dict(v) for k, v in STATE["div_pivot_stability"].items()}
        return jsonify({
            "version": APP_VERSION,
            "enabled": DIVERGENCE_ENABLED,
            "interval": DIV_INTERVAL,
            "last_scan_finished": STATE["div_last_scan_finished"],
            "last_scan_duration": STATE["div_last_scan_duration"],
            "stats": stats,
            "pivot_stability": {
                k: {
                    "agree": v["agree"], "disagree": v["disagree"],
                    "rate": round(v["agree"] / (v["agree"] + v["disagree"]) * 100, 1) if (v["agree"] + v["disagree"]) else None,
                    "avg_pct_gain": round(v.get("gain_sum", 0) / v["gain_count"], 3) if v.get("gain_count") else None,
                }
                for k, v in stability_raw.items()
            },
            "config": {
                "rr": DIV_RR, "buffer_pct": DIV_BUFFER_PCT, "rsi_period": DIV_RSI_PERIOD,
                "pivot_left": DIV_PIVOT_LEFT, "pivot_right": DIV_PIVOT_RIGHT,
                "freshness_bars": DIV_FRESHNESS_BARS, "cooldown": DIV_COOLDOWN_SEC,
            },
        })


@app.route("/api/divergence/signals")
def api_divergence_signals():
    with state_lock:
        return jsonify(list(STATE["div_signals"]))


@app.route("/api/divergence/chart/<symbol>")
def api_divergence_chart(symbol):
    try:
        candles = get_candles(symbol, interval=DIV_INTERVAL, limit=DIV_FETCH_LIMIT)
        closes = [c["close"] for c in candles]
        rsi = compute_rsi(closes, period=DIV_RSI_PERIOD)
        return jsonify({"symbol": symbol, "interval": DIV_INTERVAL, "candles": candles, "rsi": rsi})
    except Exception as e:
        log_error(f"api_divergence_chart {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Wipe all accumulated state: per-symbol tuning overrides, signal
    history (win-rate/MFE/MAE stats), cooldowns, and the watchlist —
    both in memory and in the persisted state file. Used by the header's
    "Очистить данные" button, which confirms before calling this."""
    try:
        with state_lock:
            SYMBOL_OVERRIDES.clear()
            STATE["signals"].clear()
            STATE["div_signals"].clear()
            STATE["watchlist"].clear()
            STATE["excluded_low_quality"] = 0
            STATE["filtered_by_trend"] = 0
            STATE["filtered_by_volume"] = 0
            STATE["filtered_by_oi"] = 0
            STATE["errors"].clear()
            STATE["div_pivot_stability"] = {str(r): {"agree": 0, "disagree": 0, "gain_sum": 0.0, "gain_count": 0} for r in DIV_SHADOW_RIGHTS}
        with _cooldowns_lock:
            _cooldowns.clear()
        with _div_cooldowns_lock:
            _div_cooldowns.clear()
        global _auto_tune_cursor
        _auto_tune_cursor = 0
        save_state()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ----------------------------------------------------------------------------
# Frontend (single page, canvas rendering, no external CDN dependency)
# ----------------------------------------------------------------------------
INDEX_HTML = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VP-POC Screener</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; background:#0b0e14; color:#d7dee8; font-family: -apple-system, Roboto, Segoe UI, sans-serif; }
  header { padding:10px 14px; background:#121826; position:sticky; top:0; z-index:5; border-bottom:1px solid #1f2937; }
  #headerTop { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
  #resetBtn { background:#3a1e22; border:none; color:#ff9b9b; padding:6px 12px; border-radius:8px; font-size:12px; white-space:nowrap; }
  header h1 { font-size:16px; margin:0 0 4px; }
  #status { font-size:11px; color:#8b98ab; }
  .tabs { display:flex; gap:6px; padding:8px 10px 0; }
  .tab { padding:7px 12px; border-radius:8px 8px 0 0; background:#161d2b; font-size:13px; cursor:pointer; color:#9aa7ba; }
  .tab.active { background:#1e2a3f; color:#fff; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { padding:8px 10px; text-align:right; border-bottom:1px solid #1c2433; white-space:nowrap; }
  th:first-child, td:first-child { text-align:left; }
  th { color:#8b98ab; font-weight:500; font-size:11px; text-transform:uppercase; }
  tr:active { background:#182036; }
  .long { color:#3ddc97; font-weight:600; }
  .short { color:#ff6b6b; font-weight:600; }
  .win { color:#3ddc97; font-weight:600; }
  .loss { color:#ff6b6b; font-weight:600; }
  .status-open { color:#e8b93d; font-weight:600; }
  .status-timeout { color:#8b98ab; }
  .panel { padding:0 4px 20px; }
  #modal { position:fixed; inset:0; background:#05070c; display:none; z-index:999; }
  #modal.open { display:flex; flex-direction:column; }
  #modalHeader { padding:12px; display:flex; justify-content:space-between; align-items:flex-start; }
  #modalHeader h2 { font-size:15px; margin:0; }
  #closeBtn, #optimizeBtn { background:#1e2a3f; border:none; color:#fff; padding:6px 12px; border-radius:8px; font-size:13px; }
  #optimizeBtn { background:#2a4030; color:#7fe0ab; }
  #optimizeBtn:disabled { opacity:.5; }
  #chartWrap { flex:1; overflow:hidden; padding:0 8px 8px; }
  canvas { width:100%; height:100%; display:block; background:#0d1017; border-radius:8px; }
  #divModal { position:fixed; inset:0; background:#05070c; display:none; z-index:999; }
  #divModal.open { display:flex; flex-direction:column; }
  #divModalHeader { padding:12px; display:flex; justify-content:space-between; align-items:flex-start; }
  #divModalHeader h2 { font-size:15px; margin:0; }
  #divCloseBtn { background:#1e2a3f; border:none; color:#fff; padding:6px 12px; border-radius:8px; font-size:13px; }
  #divChartWrap { flex:1; overflow:hidden; padding:0 8px 8px; }
  .dim { color:#8b98ab; }
  .empty { padding:30px 14px; text-align:center; color:#6b7688; font-size:13px; }
</style>
</head>
<body>
<header>
  <div id="headerTop">
    <h1>VP-POC Screener</h1>
    <button id="resetBtn">Очистить данные</button>
  </div>
  <div id="status">загрузка...</div>
  <div id="stats" class="dim" style="margin-top:2px;font-size:11px;"></div>
  <div id="filterStats" class="dim" style="margin-top:2px;font-size:11px;"></div>
</header>
<div class="tabs">
  <div class="tab active" data-tab="signals">Сигналы</div>
  <div class="tab" data-tab="watch">Watchlist</div>
  <div class="tab" data-tab="tuning">Тюнинг</div>
  <div class="tab" data-tab="divergence">Дивергенции</div>
</div>
<div class="panel">
  <table id="signalsTable" style="display:table">
    <thead><tr><th>Symbol</th><th>Dir</th><th>Reason</th><th>Entry</th><th>SL</th><th>TP</th><th>MFE(R)</th><th>MAE(R)</th><th>Status</th><th>Time</th></tr></thead>
    <tbody></tbody>
  </table>
  <table id="watchTable" style="display:none">
    <thead><tr><th>Symbol</th><th>Price</th><th>Nearest zone</th><th>Dist %</th></tr></thead>
    <tbody></tbody>
  </table>
  <div id="tuningPanel" style="display:none;padding:10px 4px;font-size:13px;"></div>
  <table id="divTable" style="display:none">
    <thead><tr><th>Symbol</th><th>Dir</th><th>Kind</th><th>Entry</th><th>SL</th><th>TP</th><th>MFE(R)</th><th>MAE(R)</th><th>Status</th><th>Time</th></tr></thead>
    <tbody></tbody>
  </table>
  <div id="divStatsPanel" style="display:none;padding:10px 4px;font-size:13px;"></div>
  <div class="empty" id="emptyMsg" style="display:none">Пока нет данных</div>
</div>

<div id="modal">
  <div id="modalHeader">
    <div>
      <h2 id="modalTitle">-</h2>
      <div id="modalParams" class="dim" style="font-size:11px;margin-top:2px;"></div>
    </div>
    <div style="display:flex;gap:8px;">
      <button id="optimizeBtn">Оптимизировать</button>
      <button id="closeBtn">Закрыть</button>
    </div>
  </div>
  <div id="chartWrap"><canvas id="chartCanvas"></canvas></div>
</div>

<div id="divModal">
  <div id="divModalHeader">
    <div>
      <h2 id="divModalTitle">-</h2>
      <div id="divModalParams" class="dim" style="font-size:11px;margin-top:2px;"></div>
    </div>
    <button id="divCloseBtn">Закрыть</button>
  </div>
  <div id="divChartWrap"><canvas id="divChartCanvas"></canvas></div>
</div>

<script>
const fmt = (n, d=6) => n === null || n === undefined ? '-' : Number(n).toPrecision(d).replace(/\\.?0+$/,'').replace(/\\.$/, '');
const fmtTime = (t) => t ? new Date(t*1000).toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'}) : '-';

let activeTab = 'signals';
let vpModeChecked = false;
document.querySelectorAll('.tab').forEach(el => {
  el.onclick = () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    activeTab = el.dataset.tab;
    document.getElementById('signalsTable').style.display = activeTab === 'signals' ? 'table' : 'none';
    document.getElementById('watchTable').style.display = activeTab === 'watch' ? 'table' : 'none';
    document.getElementById('tuningPanel').style.display = activeTab === 'tuning' ? 'block' : 'none';
    document.getElementById('divTable').style.display = activeTab === 'divergence' ? 'table' : 'none';
    document.getElementById('divStatsPanel').style.display = activeTab === 'divergence' ? 'block' : 'none';
    if (activeTab === 'tuning') refreshTuning();
    if (activeTab === 'divergence') refreshDivergence();
  };
});

async function refreshStatus() {
  try {
    const s = await (await fetch('/api/status')).json();
    if (!vpModeChecked) {
      vpModeChecked = true;
      if (s.volume_profile_enabled === false) {
        document.querySelector('.tab[data-tab="signals"]').style.display = 'none';
        document.querySelector('.tab[data-tab="watch"]').style.display = 'none';
        document.querySelector('.tab[data-tab="tuning"]').style.display = 'none';
        document.querySelector('.tab[data-tab="divergence"]').click();
      }
    }
    const el = document.getElementById('status');
    const scanTxt = s.last_scan_finished ? `скан ${s.last_scan_duration}s, ${s.universe_size} пар (искл. ${s.excluded_low_quality||0} неликвид)` : 'сканирование...';
    el.textContent = `v${s.version} · ${scanTxt}`;
    const st = s.stats || {};
    const wr = st.winrate !== null && st.winrate !== undefined ? `${st.winrate}%` : '-';
    const at = s.auto_tune || {};
    const atTxt = at.enabled
      ? `автотюнинг: ${at.tuned_symbols}/${s.universe_size} монет уже подобрано (обновление каждые ${at.refresh_hours}ч, +${at.per_cycle}/скан)`
      : 'автотюнинг выключен';
    const br = st.by_reason || {};
    const bounceTxt = br.bounce && br.bounce.total ? `bounce ${br.bounce.winrate}% (${br.bounce.total})` : 'bounce -';
    const breakoutTxt = br.breakout && br.breakout.total ? `breakout ${br.breakout.winrate}% (${br.breakout.total})` : 'breakout -';
    document.getElementById('stats').textContent =
      `Винрейт: ${wr} (${st.wins||0}W / ${st.losses||0}L, timeout ${st.timeouts||0}) · ${bounceTxt} · ${breakoutTxt} · открытых: ${st.open||0} · RR ${s.config ? s.config.rr : ''} · ${atTxt}`;
    const cv = st.current_version || {};
    const cvTxt = cv.total ? `с v${s.version}: ${cv.winrate}% (${cv.wins}W/${cv.losses}L)` : `с v${s.version}: пока нет закрытых`;
    document.getElementById('filterStats').textContent =
      `За этот скан отклонено — тренд: ${s.filtered_by_trend||0}, объём: ${s.filtered_by_volume||0}, OI: ${s.filtered_by_oi||0} · ${cvTxt}`;
  } catch(e) {}
}

async function refreshSignals() {
  const rows = await (await fetch('/api/signals')).json();
  const tbody = document.querySelector('#signalsTable tbody');
  tbody.innerHTML = '';
  document.getElementById('emptyMsg').style.display = (activeTab==='signals' && rows.length===0) ? 'block' : 'none';
  for (const r of rows) {
    const tr = document.createElement('tr');
    let statusHtml;
    const exitTitle = r.exit_time
      ? `title="свеча закрытия: ${fmtTime(r.exit_time)} · O ${fmt(r.exit_candle?.open)} H ${fmt(r.exit_candle?.high)} L ${fmt(r.exit_candle?.low)} C ${fmt(r.exit_candle?.close)}"`
      : '';
    if (r.status === 'OPEN') {
      statusHtml = `<span class="status-open">OPEN</span>`;
    } else if (r.result === 'WIN') {
      statusHtml = `<span class="win" ${exitTitle}>WIN @ ${fmt(r.exit_price)}${r.exit_time ? ' ('+fmtTime(r.exit_time)+')' : ''}</span>`;
    } else if (r.result === 'LOSS') {
      statusHtml = `<span class="loss" ${exitTitle}>LOSS @ ${fmt(r.exit_price)}${r.exit_time ? ' ('+fmtTime(r.exit_time)+')' : ''}</span>`;
    } else {
      statusHtml = `<span class="status-timeout">TIMEOUT</span>`;
    }
    tr.innerHTML = `<td>${r.symbol}</td>
      <td class="${r.direction==='LONG'?'long':'short'}">${r.direction}</td>
      <td class="dim">${r.reason || '-'}</td>
      <td>${fmt(r.entry)}</td>
      <td class="dim">${fmt(r.sl)}</td>
      <td class="dim">${fmt(r.tp)}</td>
      <td class="dim" title="на закрытии → полное окно 24ч">${fmtMfeMae(r, 'mfe_r')}</td>
      <td class="dim" title="на закрытии → полное окно 24ч">${fmtMfeMae(r, 'mae_r')}</td>
      <td>${statusHtml}</td>
      <td class="dim">${fmtTime(r.time)}</td>`;
    tr.onclick = () => openChart(r);
    tbody.appendChild(tr);
  }
}

async function refreshWatch() {
  const rows = await (await fetch('/api/watchlist')).json();
  const tbody = document.querySelector('#watchTable tbody');
  tbody.innerHTML = '';
  document.getElementById('emptyMsg').style.display = (activeTab==='watch' && rows.length===0) ? 'block' : 'none';
  for (const r of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${r.symbol}</td>
      <td>${fmt(r.price)}</td>
      <td class="dim">${fmt(r.nearest_bottom,5)}-${fmt(r.nearest_top,5)}</td>
      <td>${r.dist_pct !== null ? r.dist_pct.toFixed(2)+'%' : '-'}</td>`;
    tr.onclick = () => openChart(r);
    tbody.appendChild(tr);
  }
}

function fmtMfeMae(r, key) {
  const closeKey = key + '_at_close';
  const cur = r[key];
  if (cur === undefined) return '-';
  if (r.status === 'CLOSED' && r[closeKey] !== undefined && r[closeKey] !== null) {
    const atClose = r[closeKey].toFixed(2);
    const full = cur.toFixed(2);
    return atClose === full ? atClose : `${atClose} (→${full})`;
  }
  return cur.toFixed(2);
}

function fmtStat(s) {
  if (!s) return '-';
  return `avg ${s.avg} · median ${s.median} · p25 ${s.p25} · p75 ${s.p75}${s.n!==undefined ? ' (n='+s.n+')' : ''}`;
}

async function refreshTuning() {
  const t = await (await fetch('/api/tuning')).json();
  const el = document.getElementById('tuningPanel');
  if (!t.count) {
    el.innerHTML = '<div class="dim">Пока недостаточно данных — подожди пару циклов скана.</div>';
    return;
  }
  el.innerHTML = `
    <div class="dim" style="margin-bottom:10px;">
      Всего сигналов с накопленными данными: ${t.count} ·
      WIN: ${t.wins_n} · LOSS: ${t.losses_n} · OPEN: ${t.open_n}
    </div>
    <div style="margin-bottom:10px;"><b>MFE/MAE (R) на момент закрытия сделки</b> — сколько реально было хода в плюс/минус, пока сделка была ещё жива (это и есть ответ на "можно ли было раздвинуть TP/SL"):<br>
      <span class="win">WIN MFE: ${fmtStat(t.mfe_r_wins_at_close)}</span><br>
      <span class="win">WIN MAE: ${fmtStat(t.mae_r_wins_at_close)}</span><br>
      <span class="loss">LOSS MFE: ${fmtStat(t.mfe_r_losses_at_close)}</span><br>
      <span class="loss">LOSS MAE: ${fmtStat(t.mae_r_losses_at_close)}</span>
    </div>
    <div class="dim" style="margin-bottom:10px;font-size:12px;">
      Если WIN MFE (на закрытии) заметно больше текущего RR — тейк резал прибыль рано,
      можно двигать дальше. Если LOSS MFE (на закрытии) заметно больше 0 — часть лоссов
      была в плюсе перед тем как развернуться и выбить стоп, тейк можно ставить ближе.
      Если WIN MAE близко к 1.0 — почти дошло до стопа перед тем как выиграть, стоп
      можно чуть шире. Если LOSS MAE сильно меньше 1.0 — стоп стоит теснее, чем
      реально нужно было.
    </div>
    <details style="margin-top:6px;">
      <summary class="dim" style="cursor:pointer;font-size:12px;">Полное окно (${t.mfe_track_hours}ч после сигнала, включая то, что было уже после закрытия — для оценки общего запаса, не для оценки конкретной сделки)</summary>
      <div style="margin-top:8px;"><b>MFE (R):</b><br>
        <span class="dim">все: ${fmtStat(t.mfe_r_all)}</span><br>
        <span class="win">WIN: ${fmtStat(t.mfe_r_wins)}</span><br>
        <span class="loss">LOSS: ${fmtStat(t.mfe_r_losses)}</span><br>
        <span class="status-open">OPEN: ${fmtStat(t.mfe_r_open)}</span>
      </div>
      <div style="margin-top:6px;"><b>MAE (R):</b><br>
        <span class="dim">все: ${fmtStat(t.mae_r_all)}</span><br>
        <span class="win">WIN: ${fmtStat(t.mae_r_wins)}</span><br>
        <span class="loss">LOSS: ${fmtStat(t.mae_r_losses)}</span><br>
        <span class="status-open">OPEN: ${fmtStat(t.mae_r_open)}</span>
      </div>
    </details>`;
}

async function refreshDivergence() {
  const status = await (await fetch('/api/divergence/status')).json();
  const rows = await (await fetch('/api/divergence/signals')).json();

  const tbody = document.querySelector('#divTable tbody');
  tbody.innerHTML = '';
  document.getElementById('emptyMsg').style.display = (activeTab==='divergence' && rows.length===0) ? 'block' : 'none';
  for (const r of rows) {
    const tr = document.createElement('tr');
    let statusHtml;
    const exitTitle = r.exit_time
      ? `title="свеча закрытия: ${fmtTime(r.exit_time)} · O ${fmt(r.exit_candle?.open)} H ${fmt(r.exit_candle?.high)} L ${fmt(r.exit_candle?.low)} C ${fmt(r.exit_candle?.close)}"`
      : '';
    if (r.status === 'OPEN') {
      statusHtml = `<span class="status-open">OPEN</span>`;
    } else if (r.result === 'WIN') {
      statusHtml = `<span class="win" ${exitTitle}>WIN @ ${fmt(r.exit_price)}${r.exit_time ? ' ('+fmtTime(r.exit_time)+')' : ''}</span>`;
    } else if (r.result === 'LOSS') {
      statusHtml = `<span class="loss" ${exitTitle}>LOSS @ ${fmt(r.exit_price)}${r.exit_time ? ' ('+fmtTime(r.exit_time)+')' : ''}</span>`;
    } else {
      statusHtml = `<span class="status-timeout">TIMEOUT</span>`;
    }
    tr.innerHTML = `<td>${r.symbol}</td>
      <td class="${r.direction==='LONG'?'long':'short'}">${r.direction}</td>
      <td class="dim">${r.kind || '-'}</td>
      <td>${fmt(r.entry)}</td>
      <td class="dim">${fmt(r.sl)}</td>
      <td class="dim">${fmt(r.tp)}</td>
      <td class="dim" title="на закрытии → полное окно 24ч">${fmtMfeMae(r, 'mfe_r')}</td>
      <td class="dim" title="на закрытии → полное окно 24ч">${fmtMfeMae(r, 'mae_r')}</td>
      <td>${statusHtml}</td>
      <td class="dim">${fmtTime(r.time)}</td>`;
    tr.onclick = () => openDivergenceChart(r);
    tbody.appendChild(tr);
  }

  const s = status.stats || {};
  const wr = s.winrate !== null && s.winrate !== undefined ? `${s.winrate}%` : '-';
  const panel = document.getElementById('divStatsPanel');
  const cfg = status.config || {};
  const mfeBlock = s.dataset_count ? `
    <div style="margin-bottom:8px;"><b>MFE (R) — насколько цена уходила в плюс:</b><br>
      <span class="dim">все: ${fmtStat(s.mfe_r_all)}</span><br>
      <span class="win">WIN: ${fmtStat(s.mfe_r_wins)}</span><br>
      <span class="loss">LOSS: ${fmtStat(s.mfe_r_losses)}</span><br>
      <span class="status-open">OPEN: ${fmtStat(s.mfe_r_open)}</span>
    </div>
    <div><b>MAE (R) — насколько цена уходила в минус:</b><br>
      <span class="dim">все: ${fmtStat(s.mae_r_all)}</span><br>
      <span class="win">WIN: ${fmtStat(s.mae_r_wins)}</span><br>
      <span class="loss">LOSS: ${fmtStat(s.mae_r_losses)}</span><br>
      <span class="status-open">OPEN: ${fmtStat(s.mae_r_open)}</span>
    </div>` : '<div class="dim">Пока недостаточно закрытых сигналов для MFE/MAE.</div>';
  const ps = status.pivot_stability || {};
  const psRows = Object.keys(ps).sort((a,b)=>Number(a)-Number(b)).map(r => {
    const v = ps[r];
    const total = v.agree + v.disagree;
    const gainTxt = v.avg_pct_gain !== null && v.avg_pct_gain !== undefined ? ` · вход раньше в среднем на ${v.avg_pct_gain > 0 ? '+' : ''}${v.avg_pct_gain}% лучше` : '';
    return total
      ? `right=${r}: <b>${v.rate}%</b> согласия (${v.agree}/${total})${gainTxt}`
      : `right=${r}: пока нет данных`;
  }).join('<br>');
  const psBlock = psRows ? `
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid #1c2433;">
      <b>Насколько можно уменьшить задержку подтверждения пивота (right=${cfg.pivot_right} сейчас):</b><br>
      <span class="dim" style="font-size:12px;">процент случаев, когда укороченное окно указало бы на ту же точку, что и строгая (текущая) проверка — не ретроспективно на уже известном ответе, а по факту вживую</span><br>
      <span style="font-size:13px;">${psRows}</span>
    </div>` : '';
  panel.innerHTML = `
    <div class="dim" style="margin-bottom:10px;">
      RSI-дивергенции · ТФ ${status.interval} · скан ${status.last_scan_duration!==null && status.last_scan_duration!==undefined ? status.last_scan_duration+'s' : '...'} ·
      Винрейт: ${wr} (${s.wins||0}W / ${s.losses||0}L, timeout ${s.timeouts||0}) · открытых: ${s.open||0} · RR ${cfg.rr}
    </div>
    ${mfeBlock}
    ${psBlock}`;
}

async function refreshAll() {
  await refreshStatus();
  await refreshSignals();
  await refreshWatch();
  if (activeTab === 'tuning') await refreshTuning();
  if (activeTab === 'divergence') await refreshDivergence();
}
refreshAll();
setInterval(refreshAll, 15000);

document.getElementById('resetBtn').onclick = async () => {
  const sure = confirm('Удалить всю накопленную статистику и подобранные параметры по монетам? Это необратимо.');
  if (!sure) return;
  const btn = document.getElementById('resetBtn');
  btn.disabled = true;
  btn.textContent = 'Удаляю...';
  try {
    const res = await (await fetch('/api/reset', {method: 'POST'})).json();
    if (res.ok) {
      await refreshAll();
    } else {
      alert('Не удалось очистить: ' + (res.error || 'неизвестная ошибка'));
    }
  } catch (e) {
    alert('Не удалось очистить: ' + e);
  }
  btn.disabled = false;
  btn.textContent = 'Очистить данные';
};

// ---------------- Chart modal ----------------
const modal = document.getElementById('modal');
document.getElementById('closeBtn').onclick = () => modal.classList.remove('open');
let currentRow = null;
let currentData = null;

async function openChart(row) {
  currentRow = row;
  document.getElementById('modalTitle').textContent = row.symbol;
  document.getElementById('modalParams').textContent = 'загрузка...';
  modal.classList.add('open');
  try {
    const reason = row.reason || 'bounce';
    const data = await (await fetch(`/api/profile/${row.symbol}?reason=${reason}`)).json();
    currentData = data;
    renderParams(data);
    drawChart(data, row);
  } catch (e) {
    console.error(e);
  }
}

function renderParams(data) {
  const p = data.params || {};
  const ov = data.override;
  const base = `[${data.reason}] lookback ${p.lookback} · HVN ${p.hvn_top_n} · RR ${p.rr} · буфер SL ${(p.buffer_pct*100).toFixed(0)}%`;
  const tag = ov ? ` · оптимизировано (${ov.winrate}%, ${ov.trades} сделок)` : ' · параметры по умолчанию';
  document.getElementById('modalParams').textContent = base + tag;
}

function fmtOptimizeResult(r, label) {
  if (!r) return `${label}: нет данных`;
  const note = r.note ? ` (${r.note})` : '';
  return `${label}: lookback ${r.lookback} · HVN ${r.hvn_top_n} · RR ${r.rr} · буфер ${(r.buffer_pct*100).toFixed(0)}% · винрейт ${r.winrate}% (${r.trades})${note}`;
}

document.getElementById('optimizeBtn').onclick = async () => {
  if (!currentRow) return;
  const btn = document.getElementById('optimizeBtn');
  btn.disabled = true;
  btn.textContent = 'Считаю...';
  try {
    const res = await (await fetch(`/api/optimize/${currentRow.symbol}`, {method:'POST'})).json();
    if (res.error) {
      document.getElementById('modalParams').textContent = 'Ошибка: ' + res.error;
    } else {
      document.getElementById('modalParams').textContent =
        fmtOptimizeResult(res.bounce, 'bounce') + '  |  ' + fmtOptimizeResult(res.breakout, 'breakout');
      const reason = currentRow.reason || 'bounce';
      const data = await (await fetch(`/api/profile/${currentRow.symbol}?reason=${reason}`)).json();
      currentData = data;
      drawChart(data, currentRow);
    }
  } catch (e) {
    document.getElementById('modalParams').textContent = 'Ошибка оптимизации';
  }
  btn.disabled = false;
  btn.textContent = 'Оптимизировать';
};

function drawChart(data, signalRow) {
  const canvas = document.getElementById('chartCanvas');
  const wrap = document.getElementById('chartWrap');
  const dpr = window.devicePixelRatio || 1;
  const W = wrap.clientWidth, H = wrap.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const candles = data.candles || [];
  if (!candles.length) return;

  const profileW = W * 0.22;
  const chartW = W - profileW - 50;
  const padTop = 10, padBottom = 24;
  const chartH = H - padTop - padBottom;

  const hasTrade = signalRow && signalRow.entry !== undefined && signalRow.sl !== undefined;
  let hi = Math.max(...candles.map(c => c.high));
  let lo = Math.min(...candles.map(c => c.low));
  if (hasTrade) {
    hi = Math.max(hi, signalRow.tp, signalRow.sl, signalRow.entry);
    lo = Math.min(lo, signalRow.tp, signalRow.sl, signalRow.entry);
  }
  const pad = (hi - lo) * 0.04 || hi * 0.01;
  hi += pad; lo -= pad;
  const range = hi - lo || 1;
  const y = (price) => padTop + (hi - price) / range * chartH;

  const n = candles.length;
  const slot = chartW / n;
  const bodyW = Math.max(1, slot * 0.6);

  const zones = data.zones || [];
  const pocZone = zones.length ? zones[0] : null;

  // HVN zones (background bands)
  for (const z of zones) {
    const isPoc = pocZone && z.mid === pocZone.mid;
    if (isPoc) {
      ctx.fillStyle = 'rgba(80,220,160,0.14)';
    } else if (z.eligible) {
      ctx.fillStyle = 'rgba(80,160,255,0.10)';
    } else {
      ctx.fillStyle = 'rgba(120,120,130,0.05)';
    }
    ctx.fillRect(0, y(z.top), chartW, Math.max(1, y(z.bottom) - y(z.top)));
  }

  // candles
  candles.forEach((c, i) => {
    const cx = i * slot + slot / 2;
    const up = c.close >= c.open;
    ctx.strokeStyle = ctx.fillStyle = up ? '#3ddc97' : '#ff6b6b';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, y(c.high));
    ctx.lineTo(cx, y(c.low));
    ctx.stroke();
    const top = y(Math.max(c.open, c.close));
    const h = Math.max(1, Math.abs(y(c.open) - y(c.close)));
    ctx.fillRect(cx - bodyW / 2, top, bodyW, h);
  });

  // price axis labels
  ctx.fillStyle = '#6b7688';
  ctx.font = '10px sans-serif';
  for (let i = 0; i <= 4; i++) {
    const p = hi - (range * i / 4);
    const yy = y(p);
    ctx.fillText(fmtNum(p), chartW + 4, yy + 3);
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(chartW, yy); ctx.stroke();
  }

  // volume profile bars
  const borders = data.borders || [];
  const binVols = data.bin_vols || [];
  const maxVol = Math.max(...binVols, 1);
  const px = chartW + 50;
  for (let b = 0; b < binVols.length; b++) {
    const top = borders[b], bottom = borders[b + 1];
    if (top < lo || bottom > hi) continue;
    const yTop = y(top), yBot = y(bottom);
    const w = (binVols[b] / maxVol) * profileW;
    const t = binVols[b] / maxVol;
    const r = Math.round(60 + t * 40), g = Math.round(90 + t * 140), bl = Math.round(200 - t * 120);
    ctx.fillStyle = `rgb(${r},${g},${bl})`;
    ctx.fillRect(px, yTop, w, Math.max(1, yBot - yTop));
  }

  // zone edges — POC gets a bold highlighted line all the way across,
  // eligible (tradeable) zones get a visible dashed line, weak/non-eligible
  // zones get a faint dotted line so it's clear they're context-only
  for (const z of zones) {
    const isPoc = pocZone && z.mid === pocZone.mid;
    if (isPoc) {
      ctx.setLineDash([]);
      ctx.lineWidth = 2;
      ctx.strokeStyle = 'rgba(90,230,160,0.9)';
    } else if (z.eligible) {
      ctx.setLineDash([4, 3]);
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(255,200,80,0.6)';
    } else {
      ctx.setLineDash([1, 4]);
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(150,150,160,0.3)';
    }
    ctx.beginPath(); ctx.moveTo(0, y(z.mid)); ctx.lineTo(px + profileW, y(z.mid)); ctx.stroke();
    if (isPoc) {
      ctx.fillStyle = 'rgba(90,230,160,0.9)';
      ctx.font = '10px sans-serif';
      ctx.fillText('POC', 4, y(z.mid) - 4);
    }
  }
  ctx.setLineDash([]);

  // entry / SL / TP lines for an actual signal
  if (hasTrade) {
    drawLevelLine(ctx, y(signalRow.entry), chartW, '#5aa8ff', 'ENTRY ' + fmtNum(signalRow.entry));
    drawLevelLine(ctx, y(signalRow.sl), chartW, '#ff6b6b', 'SL ' + fmtNum(signalRow.sl));
    drawLevelLine(ctx, y(signalRow.tp), chartW, '#3ddc97', 'TP ' + fmtNum(signalRow.tp));
  }
}

function drawLevelLine(ctx, yy, chartW, color, label) {
  ctx.setLineDash([2, 4]);
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = color;
  ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(chartW, yy); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = color;
  ctx.font = 'bold 10px sans-serif';
  ctx.fillText(label, 4, yy - 4);
}

function fmtNum(n) {
  return Number(n).toPrecision(6).replace(/\\.?0+$/,'').replace(/\\.$/, '');
}

// ---------------- Divergence chart modal ----------------
const divModal = document.getElementById('divModal');
document.getElementById('divCloseBtn').onclick = () => divModal.classList.remove('open');
let currentDivRow = null;
let currentDivData = null;

async function openDivergenceChart(row) {
  currentDivRow = row;
  document.getElementById('divModalTitle').textContent = row.symbol;
  document.getElementById('divModalParams').textContent = 'загрузка...';
  divModal.classList.add('open');
  try {
    const data = await (await fetch(`/api/divergence/chart/${row.symbol}`)).json();
    currentDivData = data;
    document.getElementById('divModalParams').textContent =
      `RSI дивергенция (${row.kind}) · ${row.direction} · entry ${fmt(row.entry)} · SL ${fmt(row.sl)} · TP ${fmt(row.tp)}`;
    drawDivergenceChart(data, row);
  } catch (e) {
    console.error(e);
  }
}

function drawDivergenceChart(data, row) {
  const canvas = document.getElementById('divChartCanvas');
  const wrap = document.getElementById('divChartWrap');
  const dpr = window.devicePixelRatio || 1;
  const W = wrap.clientWidth, H = wrap.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const candles = data.candles || [];
  const rsi = data.rsi || [];
  if (!candles.length) return;

  const priceH = H * 0.62;
  const rsiTop = priceH + 14;
  const rsiH = H - rsiTop - 4;
  const padRight = 54;
  const chartW = W - padRight;

  const n = candles.length;
  const slot = chartW / n;
  const bodyW = Math.max(1, slot * 0.6);
  const xAt = (i) => i * slot + slot / 2;
  const findIdx = (t) => candles.findIndex(c => c.time === t);

  // ---- price panel ----
  let hi = Math.max(...candles.map(c => c.high));
  let lo = Math.min(...candles.map(c => c.low));
  if (row) { hi = Math.max(hi, row.tp, row.sl, row.entry); lo = Math.min(lo, row.tp, row.sl, row.entry); }
  const pad = (hi - lo) * 0.05 || hi * 0.01;
  hi += pad; lo -= pad;
  const range = hi - lo || 1;
  const yP = (price) => (hi - price) / range * priceH;

  candles.forEach((c, i) => {
    const cx = xAt(i);
    const up = c.close >= c.open;
    ctx.strokeStyle = ctx.fillStyle = up ? '#3ddc97' : '#ff6b6b';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, yP(c.high));
    ctx.lineTo(cx, yP(c.low));
    ctx.stroke();
    const top = yP(Math.max(c.open, c.close));
    const h = Math.max(1, Math.abs(yP(c.open) - yP(c.close)));
    ctx.fillRect(cx - bodyW / 2, top, bodyW, h);
  });

  ctx.fillStyle = '#6b7688';
  ctx.font = '10px sans-serif';
  for (let i = 0; i <= 3; i++) {
    const p = hi - (range * i / 3);
    const yy = yP(p);
    ctx.fillText(fmtNum(p), chartW + 4, yy + 3);
    ctx.strokeStyle = 'rgba(255,255,255,0.05)';
    ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(chartW, yy); ctx.stroke();
  }

  // price pivot trendline — connects the two swing points the divergence was read from
  let pi1 = -1, pi2 = -1;
  const pivotType = row && row.kind === 'bearish' ? 'HIGH' : 'LOW';
  if (row && row.time_p1 !== undefined && row.time_p2 !== undefined) {
    pi1 = findIdx(row.time_p1);
    pi2 = findIdx(row.time_p2);
    if (pi1 >= 0 && pi2 >= 0) {
      const x1 = xAt(pi1), x2 = xAt(pi2), y1 = yP(row.price_p1), y2 = yP(row.price_p2);
      ctx.strokeStyle = '#ffcc55';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      ctx.fillStyle = '#ffcc55';
      [[x1, y1], [x2, y2]].forEach(([x, y]) => { ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill(); });
      ctx.font = 'bold 9px sans-serif';
      ctx.fillText(`P1 ${pivotType} ${fmtNum(row.price_p1)}`, x1 + 5, y1 - 6);
      ctx.fillText(`P2 ${pivotType} ${fmtNum(row.price_p2)}`, x2 + 5, y2 - 6);
    }
  }

  // prominent banner — what our own code decided, directly on the image so
  // it never depends on the (scrollable/croppable) header text above the canvas
  if (row) {
    const bannerColor = row.direction === 'SHORT' ? '#ff6b6b' : '#3ddc97';
    ctx.fillStyle = 'rgba(5,7,12,0.75)';
    ctx.fillRect(4, 4, 210, 18);
    ctx.fillStyle = bannerColor;
    ctx.font = 'bold 11px sans-serif';
    ctx.fillText(`${(row.kind||'').toUpperCase()} DIVERGENCE -> ${row.direction}`, 8, 17);
  }

  if (row) {
    drawLevelLine(ctx, yP(row.entry), chartW, '#5aa8ff', 'ENTRY ' + fmtNum(row.entry));
    drawLevelLine(ctx, yP(row.sl), chartW, '#ff6b6b', 'SL ' + fmtNum(row.sl));
    drawLevelLine(ctx, yP(row.tp), chartW, '#3ddc97', 'TP ' + fmtNum(row.tp));
  }

  // ---- RSI panel ----
  ctx.fillStyle = '#8b98ab';
  ctx.font = '10px sans-serif';
  ctx.fillText('RSI', 4, rsiTop + 10);

  const yR = (v) => rsiTop + (100 - v) / 100 * rsiH;
  ctx.setLineDash([3, 3]);
  [30, 50, 70].forEach(v => {
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.beginPath(); ctx.moveTo(0, yR(v)); ctx.lineTo(chartW, yR(v)); ctx.stroke();
    ctx.fillStyle = '#555f70'; ctx.font = '9px sans-serif';
    ctx.fillText(String(v), chartW + 4, yR(v) + 3);
  });
  ctx.setLineDash([]);

  ctx.strokeStyle = '#c58cff';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  let started = false;
  rsi.forEach((v, i) => {
    if (v === null || v === undefined) return;
    const cx = xAt(i), cy = yR(v);
    if (!started) { ctx.moveTo(cx, cy); started = true; } else { ctx.lineTo(cx, cy); }
  });
  ctx.stroke();

  // RSI pivot trendline — RSI's OWN local extreme near each price pivot,
  // not necessarily the same bar as the price pivot (rsi_time_p1/p2),
  // falling back to the price pivot's own bar for older stored signals
  // that predate this field.
  if (row && row.rsi_p1 !== undefined && row.rsi_p2 !== undefined) {
    const ri1 = row.rsi_time_p1 !== undefined ? findIdx(row.rsi_time_p1) : pi1;
    const ri2 = row.rsi_time_p2 !== undefined ? findIdx(row.rsi_time_p2) : pi2;
    if (ri1 >= 0 && ri2 >= 0) {
      const x1 = xAt(ri1), x2 = xAt(ri2), y1 = yR(row.rsi_p1), y2 = yR(row.rsi_p2);
      ctx.strokeStyle = '#ffcc55';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      ctx.fillStyle = '#ffcc55';
      [[x1, y1], [x2, y2]].forEach(([x, y]) => { ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill(); });
      ctx.font = 'bold 9px sans-serif';
      ctx.fillText(`RSI ${row.rsi_p1.toFixed(1)}`, x1 + 5, y1 - 6);
      ctx.fillText(`RSI ${row.rsi_p2.toFixed(1)}`, x2 + 5, y2 - 6);
    }
  }
}

window.addEventListener('resize', () => {
  if (modal.classList.contains('open') && currentData) {
    drawChart(currentData, currentRow);
  }
  if (divModal.classList.contains('open') && currentDivData) {
    drawDivergenceChart(currentDivData, currentDivRow);
  }
});
</script>
</body>
</html>"""


@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")


# ----------------------------------------------------------------------------
# Entrypoint
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    load_state()
    _load_alert_cfg()
    threading.Thread(target=_telegram_sender_worker, daemon=True).start()
    t = threading.Thread(target=scan_loop, daemon=True)
    t.start()
    port = int(os.environ.get("VP_PORT", 8080))
    tg_status = "настроен" if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) else "не настроен"
    print(f"VP-POC Screener v{APP_VERSION} — http://127.0.0.1:{port} — Telegram: {tg_status}")
    app.run(host="0.0.0.0", port=port, threaded=True)
