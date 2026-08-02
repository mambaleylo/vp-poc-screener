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
v0.23.0 - added a settings button (⚙️) in the header: a modal with
         on/off switches for the big scan-mode toggles — Volume Profile
         scanner, Bounce, Breakout, RSI divergence, Telegram
         notifications — deliberately NOT the detailed indicator knobs
         (RR, buffers, thresholds), which stay env-var-only per request.
         These flags (VOLUME_PROFILE_ENABLED etc.) were already
         module-level globals read fresh at call time everywhere, so
         flipping them via the new /api/settings POST endpoint takes
         effect on the very next scan cycle / next alert — no restart.
         Verified none of them are used as function default-parameter
         values (which would've been evaluated once at import and stayed
         stale). Persisted to vp_poc_settings.json (own file, loaded at
         startup alongside the existing state/alert-config files) so a
         change made in the UI survives a restart. Added a new
         TELEGRAM_ENABLED flag, separate from whether a token exists —
         lets notifications be muted without losing the configured
         token. Tab visibility for the Сигналы/Watchlist/Тюнинг tabs is
         now reactive to volume_profile_enabled on every status poll,
         not just checked once at page load, so toggling it from the
         new settings panel shows/hides them live. Verified end-to-end:
         POST /api/settings mutates the actual module globals
         immediately, and a simulated restart (reload from disk)
         correctly restores a saved change.
v0.24.0 - split Telegram notifications by category in the settings
         panel, alongside the existing master on/off: separate switches
         for Volume Profile alerts (bounce/breakout signals + their
         WIN/LOSS closes) and RSI-divergence alerts, so either can be
         muted independently. send_telegram() now takes an optional
         category ("vp"/"div") checked against the new
         VP_TG_ALERTS_VP/VP_TG_ALERTS_DIV flags (both default on) in
         addition to the master TELEGRAM_ENABLED — all 4 call sites
         (both signal-open and both close alerts) tagged accordingly.
         Persisted alongside the other settings. Verified the category
         gating directly: a "vp"-tagged alert is suppressed when
         telegram_alerts_vp is off while a "div"-tagged one still goes
         through, and vice versa.
v0.25.0 - raised the universe cap and background-work throughput per
         user request (hardware has headroom): VP_MAX_SYMBOLS 150->250,
         VP_WORKERS 8->12 (parallel fetch/scan threads, so a bigger
         universe doesn't just make every cycle proportionally longer),
         VP_AUTO_TUNE_PER_CYCLE 1->3 (a 250-symbol universe's first full
         tuning pass now takes ~84 cycles instead of 250), and
         VP_DIV_STABILITY_PER_CYCLE 1->2 to match. Scan cadence itself
         (VP_SCAN_INTERVAL, 45s) is a pause added AFTER each cycle's work
         finishes, not a fixed period — so cycle time already scales
         naturally with universe size regardless; no change needed
         there. All four remain overridable via env var if the actual
         hardware/network turns out to need dialing back.
v0.26.0 - two user-requested changes to divergence TP/SL and timing:
         (1) TP is now a fixed % move from entry (VP_DIV_TP_PCT, default
         1.1%) instead of being derived from a pivot-based SL — SL is
         now sized backward from that fixed TP distance divided by
         DIV_RR, so the RR ratio (2.0) is preserved but SL is a
         mechanical fraction of TP, no longer the divergence's actual
         structural invalidation point beyond the pivot. Removed
         DIV_MAX_RISK_PCT entirely — it existed to catch a pivot-based
         SL sitting too far from entry, which can't happen anymore since
         risk is now always exactly tp_pct/rr of entry, a constant.
         Also removed the now-fully-unused DIV_BUFFER_PCT. (2) lowered
         VP_DIV_PIVOT_RIGHT 3->2 per overnight signal volume plus the
         tool's own shadow-stability read at right=2. VP_DIV_SHADOW_RIGHTS
         default updated to "1" (previously "2,3,4", all of which sat at
         or above the new right=2 and would have produced zero stability
         data going forward). Verified the new TP/SL calc directly (both
         directions land at exactly 1.1% TP and preserve RR=2.0) and a
         full endpoint regression.
v0.27.0 - user reported divergence signals feel "already played out" by
         the time they arrive. Rather than guess, added a direct
         measurement: pre_move_pct on every signal — the % of the
         anticipated move that already happened between the confirmed
         pivot (price_p2) and actual entry, signed so positive means
         price already moved favorably before the trade could open.
         Shown in the Дивергенции stats panel split by all/WIN/LOSS, so
         it's now possible to see concretely how much of the fixed
         1.1% TP is typically already gone by entry, rather than
         inferring it indirectly from the pivot-confirmation-delay
         diagnostics (which measure a related but different thing: how
         often a faster confirmation would agree, not how much of the
         actual TP distance is pre-consumed). Verified the signed
         formula against hand-computed cases for both directions
         (already-moved, no-move, and adverse-move scenarios).
v0.28.0 - split the "Очистить данные" button into two scoped ones:
         "Очистить объём" (/api/reset/volume — overrides, signals,
         watchlist, cooldowns) and "Очистить дивер" (/api/reset/divergence
         — div_signals, pivot-stability diagnostic, div cooldowns).
         Each leaves the other side untouched. The old combined
         /api/reset stays for backward compatibility but the header no
         longer calls it. Verified selectivity directly: resetting one
         side clears only its own data while the other side's populated
         test data survives untouched, in both directions.
v0.29.0 - added a third, fully independent signal source: the EMA
         7/14/28 crossover indicator, ported directly from a
         user-supplied Pine Script ("EMA 7,14,28 + Сигналы"). Own scan
         (VP_EMA_INTERVAL, default 1h), own history/stats/chart/tab
         ("Индикатор"), own Telegram category ("ema"), own settings
         toggle (labeled "Обещанный индикатор" per request) and reset
         button ("Очистить индикатор" / /api/reset/ema) — same
         "completely separate from everything else" treatment as
         divergence got in v0.14.
         compute_ema() matches Pine's ta.ema exactly: seeds with the
         first value (no SMA warm-up), then the standard
         alpha=2/(period+1) recursion — verified against a hand-computed
         first step. Three signal-type definitions mirror the script's
         own dropdown: price/EMA7 cross, EMA7/EMA14 cross, or
         "combined" (price crosses EMA7 while EMA7 already sits on the
         trade's side of EMA14) — plus the optional EMA28 trend filter,
         all only evaluated on the latest bar (no confirmation delay
         needed, since a crossover is knowable the instant a bar
         closes, unlike a swing pivot). The script only plots BUY/SELL
         labels with no TP/SL of its own, so added a fixed-%-TP-then-
         derive-SL calc (VP_EMA_TP_PCT, default 1.5%, RR 2.0) mirroring
         the divergence signals, purely so this fits the same win-rate/
         MFE/MAE tracking as everything else. Chart is overlay-only (no
         separate sub-panel, matching how the indicator actually draws
         on a real chart) — candles plus the three EMA lines in their
         original script colors, with entry/SL/TP level lines.
         Verified end-to-end: EMA seeding against a hand-computed
         value, a manufactured price/EMA7 crossover firing correctly
         through the full scan->record->outcome-tracking pipeline (WIN
         resolved correctly), the trend filter correctly blocking a
         counter-trend crossover, and a full endpoint regression across
         all three signal sources together.
v0.30.0 - two user-requested changes.
         (1) All three chart modals (Volume Profile, Divergence, EMA)
         zoomed in on the signal instead of showing the full ~200-bar
         fetch — added windowAroundTime(): finds the signal's own bar
         by timestamp and windows to a fixed size around it (20
         before/70 total for VP, 30/80 for divergence since pivots can
         sit further back, 15/60 for EMA), clamped at either array edge
         so it always returns a full-size window. Verified against
         signal-near-end, signal-in-middle, signal-near-start, and
         no-timestamp-match cases. Divergence and EMA windowing slice
         the parallel arrays (rsi/ema7/ema14/ema28) by the same indices
         so nothing desyncs.
         (2) EMA indicator now scans multiple timeframes at once —
         VP_EMA_INTERVALS (default "1h,1w") instead of a single
         VP_EMA_INTERVAL — since the script's own developer runs it on
         the weekly chart. Each signal is tagged with which interval it
         came from; cooldown and the open-signal check are now keyed by
         (symbol, interval) so the same symbol can have independent 1h
         and 1w signals simultaneously; update_ema_outcomes reads the
         interval back off each signal rather than a global default, so
         outcome tracking fetches the right timeframe's candles.
         compute_ema_stats() takes an optional interval filter;
         /api/ema/status now returns a stats_by_interval breakdown so
         1h vs weekly performance can be compared once enough data
         accumulates, per the "let's track both and see" ask rather
         than picking one upfront. Chart endpoint takes an interval
         query param, defaulting to the clicked signal's own interval.
         Verified end-to-end: same symbol firing independently on both
         intervals, correct per-interval stats breakdown, and chart
         fetch honoring interval=1w.
v0.30.1 - user feedback (with screenshot): the weekly EMA chart was
         still too zoomed out — 60 bars of a weekly candle spans well
         over a year, far more than needed to see the setup, squeezing
         the actual entry/SL/TP zone into a sliver at the edge. Added
         windowParamsForInterval(): picks the before/total bar counts
         based on the signal's own interval (1w: 6/20, 3d: 8/25, 1d:
         10/35, else: 15/60 as before) instead of one fixed size for
         every timeframe. Verified all four branches plus the
         undefined-interval fallback directly.
v0.31.0 - user feedback (with screenshot, weekly EMA chart): the real
         problem wasn't bar count, it was vertical stretch — a naive
         min/max-of-visible-candles autoscale let old bars at a very
         different price (e.g. 0.15-0.2 many weeks back vs a 0.053
         entry/SL/TP zone now) dominate the y-axis, squeezing the
         actual signal zone into an unreadable sliver at the very
         edge. Replaced the autoscale in all three chart types (Volume
         Profile, Divergence, EMA) with computeYRangeForZone(): if the
         entry/SL/TP zone would occupy less than 30% of the vertical
         range under naive autoscale, shrinks the range so the zone is
         centered and actually occupies 30% of the screen — bars whose
         highs/lows fall outside the new range simply clip off the
         top/bottom of the canvas (normal charting behavior, browsers
         clip out-of-bounds drawing for free). Falls back to the old
         padded-autoscale behavior when the zone already occupies a
         healthy fraction naturally, so normal-looking charts aren't
         needlessly cropped. Verified directly against the exact
         screenshot scenario (0.053 zone inside a 0.038-0.27 candle
         range) — zone now measures exactly 30% of the shown range,
         matching target — and confirmed a normal case (zone already
         ~10% of a tight natural range) is left alone rather than
         over-cropped.
v0.31.1 - user feedback (with screenshot): the v0.31.0 fix went too far
         the other way — compressing hard enough to hit a fixed 30% zone
         target could clip almost the entire visible window down to ~4
         candles when the lead-up trend was strong (a 5x price swing
         over a few weekly bars, e.g.). This is a genuine geometric
         conflict, not a simple bug: you can't have both a huge price
         swing AND a tiny zone each filling most of the screen at the
         same time. Reworked computeYRangeForZone() with a bounded
         compromise instead of an absolute target: it still compresses
         toward making the zone visible, but never shrinks the range
         below minKeepFrac (0.12) of the range needed to show bars from
         the window's start through ~8 bars past the signal — bars
         further out than that may still clip if extreme. Swept
         minKeepFrac from 0.35 down to 0.08 against the reported
         scenario (6 weekly bars in a 0.27->0.058 downtrend, entry
         0.0531) to find a balance: settled on 0.12, giving a 4.2% zone
         with 15/20 candles still visible, vs. the reported case's ~4
         candles and vs. 1.4%/16-visible at the more conservative 0.35.
         Verified this default against the original tiny-zone bug (now
         4% instead of <1%) and a normal, non-extreme case (unaffected,
         same ~36% as before) — both still behave sensibly.
v0.31.2 - fixed a real gap noticed while reading a user's stats
         screenshot: the Дивергенции and Индикатор (EMA) tabs were both
         still showing full-window (24h, contaminated by post-close
         drift) MFE/MAE as the primary numbers — the at-close snapshot
         fix from v0.19 only ever got wired into the Тюнинг (Volume
         Profile) panel's JS, even though compute_divergence_stats()
         and compute_ema_stats() had already been computing the
         *_at_close fields backend-side all along. Caught because a
         LOSS MAE of 2.683 shown for EMA is physically impossible for
         an at-close reading (a fixed-size stop means adverse excursion
         is exactly 1.0R the instant SL is touched) — that value could
         only come from continued post-close tracking. Both panels now
         lead with the at-close numbers and tuck the full-window ones
         into the same collapsed <details> the Тюнинг panel already
         uses, for consistency across all three signal sources.
v0.32.0 - URGENT FIX: compute_div_tp_sl() had no function signature —
         only its body existed, orphaned as dead/unreachable code after
         a str_replace edit ate the `def` line (the same category of
         bug caught and fixed twice before this session, for
         data_quality_check and compute_divergence_stats). This one
         slipped through because every regression check since v0.26.0
         only ever hit GET API endpoints (which read already-existing
         STATE data) — none of them actually CALLED
         scan_symbol_divergence(), so the NameError it threw every
         single scan cycle was silently caught by that function's own
         try/except and logged, never surfacing as a visible failure.
         Confirmed via the live GitHub copy at v0.31.2 (fetched before
         this fix) that the break has been live since v0.26.0 — meaning
         no new divergence signals have been created for however long
         devices have been running v0.26.0 or later. Fixed by restoring
         the missing signature; verified this time by directly calling
         scan_symbol, scan_symbol_divergence, and scan_symbol_ema (not
         just their API layers) end-to-end with no exceptions, and
         added this direct-call check as a standing practice going
         forward alongside the existing compile/import/JS checks.
         Also includes the early groundwork (untested-in-production,
         not yet wired into anything) for a new "Скальпинг" module per
         a separate ongoing request — config, an excursion-statistics
         engine, Gate.io's isolated-margin liquidation formula, a
         volatility-based universe ranker, and a maintenance-margin-rate
         fetch — all inert until wired up in a follow-up push.
v0.33.0 - wired the "Скальпинг" module all the way to a working
         dashboard. scan_symbol_scalp() runs the excursion engine
         across VP_SCALP_INTERVALS x LONG/SHORT for one symbol;
         recommend_scalp_config() picks, per interval/direction, the
         LARGEST target% that both clears VP_SCALP_MIN_HIT_RATE and
         has a liquidation buffer (at the leverage that target implies
         for the $7/$30 goal) exceeding the coin's own historical p90
         adverse move by VP_SCALP_SAFETY_MARGIN (1.5x) — then ranks
         across all interval/direction combos by hit_rate x
         trades_per_day. New scalp_loop() thread, own 6h cadence,
         fully separate from the main 45s scanner — rebuilds the
         volatility-ranked universe, fetches real per-contract MMR
         from Gate.io's risk_limit_tiers endpoint (falls back to a
         conservative default per-symbol, never crashes on an
         unexpected schema), then fans out the scan across the thread
         pool. New API routes (/api/scalp/status ranked list,
         /api/scalp/symbol/<symbol> full detail, /api/reset/scalp),
         settings toggle, and a fourth tab with a dense ranked table
         (score, hit-rate, leverage, liquidation buffer, MMR-verified
         flag) plus click-to-expand full per-symbol breakdown — this
         is explicitly a data tool for future review, not a live
         signal feed, so density won over polish.
         Verified end-to-end this time by directly calling all four
         scan_symbol_* functions (not just their API layers) with zero
         exceptions, plus a full manual replication of scalp_loop's
         cycle body (universe build -> MMR fetch -> per-symbol scan ->
         recommendation -> API read) against mocked data, confirming a
         sensible top-ranked result end to end.
v0.33.1 - SAFETY FIX, found by hand-checking the user's first real
         dashboard screenshot rather than trusting it: VELVET_USDT
         showed leverage 46.67x with a liquidation buffer of 5.467% —
         mathematically impossible at that leverage (the theoretical
         ceiling with zero MMR and zero fees is 100/46.67 = 2.14%; no
         non-negative MMR could ever produce a buffer above that,
         confirmed by sweeping MMR values and finding only an
         implausible ~-3.2% "MMR" reproduces 5.467%). Root cause: Gate's
         actual risk_limit_tiers response field names couldn't be
         verified against a live request during development (sandboxed,
         no network access to confirm) — for some contracts, a wrong
         field apparently parsed successfully into a plausible-looking
         but wrong number, which the earlier defensive code only guarded
         against exceptions/missing fields, not against successfully
         parsing garbage. Two independent fixes: (1)
         get_futures_risk_limit_tiers() now rejects any parsed value
         outside a sane MMR range (0.01%-5%, VP_SCALP_MMR_SANITY_MIN/MAX)
         before accepting it, falling back to the conservative default
         instead; (2) compute_scalp_liquidation_move_pct() now clamps
         its result to the hard mathematical ceiling of 100/leverage
         regardless of what mmr_pct it's given — a non-negative MMR can
         only ever shrink this buffer, never enlarge it, so this is a
         real invariant, not a heuristic, and protects against this
         entire bug class even from a source I haven't thought to
         distrust yet. Verified both fixes directly: the exact bad MMR
         value now correctly gets clamped/rejected, a normal MMR is
         unaffected, and even if a bad value somehow reached
         recommend_scalp_config() directly (bypassing the first fix
         entirely), the second fix alone still produces a safe result.
         Every "буфер" value shown before this fix should be treated as
         unverified until a fresh scan runs on the corrected code.
v0.34.0 - user caught another real gap: VELVET_USDT's recommendation
         called for 46.67x leverage, but Gate.io only allows 10x on
         that contract — the whole leverage-safety check validated
         liquidation risk but never checked whether the exchange would
         actually let the leverage be set at all. get_futures_risk_
         limit_tiers() now also extracts each contract's own max
         leverage (leverage_max, with a max_leverage fallback field
         name) from the same tiered response, sanity-bounded to
         [1,125] the same way MMR is. recommend_scalp_config() takes a
         new max_leverage param and now rejects any target whose
         required leverage exceeds it — a target the math likes but
         the exchange won't execute isn't a real recommendation.
         Defaults to a conservative 10x (VP_SCALP_DEFAULT_MAX_LEVERAGE)
         when a contract's real cap isn't confirmed, matching the exact
         value the user found for VELVET_USDT rather than assuming
         majors' 125x. Table and per-symbol detail both show a "~"
         marker on the leverage figure when unconfirmed, same pattern
         as the MMR marker.
         Also: caught and fixed a mistake made WHILE writing this fix —
         a str_replace matched only the tail of the old function and
         the new_str contained a full replacement function, which
         produced two overlapping `def get_futures_risk_limit_tiers():`
         blocks merged into one broken mess (not the usual "signature
         silently vanishes" version of this bug, but the same root
         cause: not re-viewing the exact match boundaries before
         trusting a large multi-line replacement). Caught immediately
         via the duplicate-def grep check before compiling, so it never
         reached even a local test run, let alone a push.
         Verified the fix directly: a synthetic VELVET-like scenario
         with a 10x cap correctly returns no recommendation, the same
         scenario with a 125x cap correctly recommends the smaller
         target that fits under it, and a full direct-call sweep of all
         four scan_symbol_* functions plus the endpoint regression both
         stayed clean.
v0.34.1 - the EMA indicator's current config has run at 22.4% win rate
         (19W/66L) at RR=2 — well below the ~33% breakeven, and on a
         large enough sample (85 closed) that it's not noise. User
         asked to consider trading it in reverse instead of just
         retuning the filter. Added VP_EMA_INVERT_SIGNALS: flips
         buy/sell in detect_ema_signal() after the trend filter is
         applied (inverts exactly what the current indicator+filter
         says, not the raw pre-filter crossover — matches "do the
         opposite of what it says" literally). Settings toggle
         ("↳ Реверс сигналов EMA"), and the Индикатор tab's header now
         shows a prominent "РЕВЕРС ВКЛЮЧЁН" marker when active, so
         historical stats read while toggling don't get misread as the
         wrong mode. Gave the user a reasoned starting estimate for
         reversed TP/SL (~0.6-0.75% target / ~0.4-0.5% stop, vs the
         original 1.5%/0.75%) based on reading LOSS MFE (median 0.29%
         — how far reversed-adverse typically ran on paths that would
         become reversed wins) against WIN MFE (median ~2.12% — how far
         reversed-adverse ran on paths that would become reversed
         losses) at-close, but was explicit that this is a directional
         estimate from aggregate stats, not a rigorous recomputation —
         the toggle exists so the same at-close MFE/MAE machinery can
         measure the reversed version directly going forward instead of
         trusting the estimate. Verified inversion flips LONG<->SHORT
         correctly, leaves the no-signal case as no-signal, and the
         full direct-call scan sweep plus endpoint regression stayed
         clean.
         (A night-vs-day excursion breakdown was added and then fully
         reverted per direct user feedback that it wasn't wanted —
         analyze_excursions/summarize_excursions and the per-symbol
         detail display are back to exactly their pre-breakdown form.)
v0.34.2 - retuned EMA_TP_PCT/EMA_RR for the reversed-signal hypothesis
         (0.015/2.0 -> 0.0075/1.5, i.e. TP 1.5%->0.75%, SL 0.75%->0.5%).
         Reasoning grounded in the original config's own at-close
         numbers: LOSS trades' favorable excursion (= the reversed
         side's adverse excursion) sat at median 0.29%/avg 0.375%
         before the original 0.75% stop was hit, so the new SL (0.5%)
         gives ~1.3-1.7x headroom above that without going so wide it
         wrecks RR. The new TP (0.75%) sits exactly at the original
         stop's level — a level every current LOSS trade crossed by
         definition, so a level the reversed side should reach often on
         those same historical paths. Verified the new defaults
         compute to exactly TP=0.75%/SL=0.5%/risk=0.5% in both
         directions, and the full scan-function/endpoint regression
         stayed clean.
v0.35.0 - user shared a live PROM_USDT divergence screenshot showing
         the bounce had already largely played out (price tagged above
         the eventual TP level in a candle well before entry, then
         pulled back to where the signal actually fired) — the same
         lateness problem this session already built pre_move_pct to
         measure, now seen concretely. Two changes: (1) reverted
         DIV_PIVOT_RIGHT 2->3 per direct request — flagged honestly
         that slower confirmation should, by the delay logic alone,
         make lateness worse rather than better, but reverted anyway;
         worth watching pre_move_pct to see the actual effect.
         DIV_SHADOW_RIGHTS default restored to "1,2" since shadow=2 is
         meaningful again now that right=3. (2) added
         VP_DIV_INVERT_SIGNALS mirroring the EMA one — detect_
         divergence() now flips "direction" (LONG<->SHORT) while
         leaving "kind" (bullish/bearish) untouched, since kind
         describes the RSI pattern found and direction is the separate
         trading decision now being inverted. Settings toggle
         ("↳ Реверс сигналов дивергенций"), and the Дивергенции tab
         header shows "РЕВЕРС ВКЛЮЧЁН" when active, same pattern as
         EMA's marker.
         Did NOT retune DIV_TP_PCT/DIV_RR for the reversed case the way
         EMA's were — EMA had 85 closed trades to derive percentiles
         from, divergence has 6. Explicitly left as a decision for the
         user rather than fabricating numbers off an n=6 sample.
         Verified the ternary-swap logic directly (kind stays constant,
         direction flips) and the full scan-function/endpoint
         regression, settings toggle, and DIV_PIVOT_RIGHT=3 all stayed
         clean.
v0.35.1 - user pushed back on leaving TP/SL untouched ("use what's
         there instead of waiting") — retuned DIV_TP_PCT/DIV_RR for the
         reversed hypothesis after all: 0.011/2.0 (SL 0.55%) ->
         0.0065/0.867 (SL~0.75%). Off the ORIGINAL direction's own
         at-close numbers (n=8: 3W/5L): LOSS trades' favorable
         excursion before the original stop sat at median 0.62%R/avg
         0.82%R — that's the reversed side's adverse excursion on
         paths that would become reversed wins, so SL~0.75% sits
         between median and avg. LOSS MAE at close (0.86%/1.05%,
         reflecting same-bar overshoot past the exact stop price)
         suggested price often continued past the stop's own level, so
         TP~0.65% sits above the bare 0.55% floor. Comment is explicit
         that this is a far weaker estimate than the EMA retune — n=8
         vs n=85 — an informed guess, not a validated figure. Verified
         the new defaults compute to exactly TP=0.65%/SL=0.75% in both
         directions, and the full scan-function/endpoint regression
         stayed clean.
v0.36.0 - UI restructure per user request: renamed "Сигналы" -> "Volume"
         and "Индикатор" -> "EMA" tab labels. More substantially,
         unified where each signal source's stats live — previously VP
         stats sat in their own standalone "Тюнинг" tab while
         Дивергенции and EMA each showed stats at the bottom of their
         own signals table, an inconsistent layout the user flagged
         directly. Removed the standalone tuning tab; tuningPanel now
         shows at the bottom of the Volume tab (same DOM position it
         already occupied, just re-tied to activeTab==='signals'
         instead of a separate tab click), matching the divStatsPanel/
         emaStatsPanel pattern exactly. Added a matching "Объём (Volume
         Profile) — статистика" header line to both the populated and
         empty states of that panel, since it's no longer implicitly
         labeled by living in its own tab. Verified the full
         scan-function/endpoint regression stayed clean and confirmed
         no leftover references to the old "tuning" tab anywhere in the
         JS.
v0.36.1 - URGENT FIX: the v0.36.0 claim of "no leftover tuning-tab
         references" was wrong — refreshStatus() still had
         ['signals','watch','tuning'].map(...) building the vpTabs
         array from data-tab selectors, and querySelector for the now-
         removed tuning tab returns null. Setting .style.display on
         that null threw, and since refreshStatus() wraps its whole
         body in try{}catch(e){} for unrelated resilience reasons, the
         throw happened before any of the header stats (winrate,
         bounce/breakout split, auto-tune progress) got rendered — the
         catch silently swallowed it. Every refresh cycle (every 15s)
         hit this, so the header stats the user was looking for had
         effectively stopped updating since the v0.36.0 push. Fixed by
         dropping 'tuning' from that array. Also, per user feedback
         that scrolling down for stats is tedious: reordered the DOM so
         each tab's stats panel (tuningPanel/divStatsPanel/
         emaStatsPanel) now sits ABOVE its signals table instead of
         below, for Volume, Дивергенции, and EMA alike — visible
         immediately without scrolling past a long signal list.
         Verified this time by actually re-deriving what broke instead
         of trusting the earlier grep, confirmed the only remaining
         'tuning' matches in the JS are legitimate references to the
         still-existing tuningPanel div (not the removed tab button),
         and re-ran the full scan-function/endpoint regression clean.
v0.37.0 - two tuning changes from fresh Volume stats (breakout had
         degraded to 34.5% win rate, barely above the 33.3% breakeven
         at RR=2, down from 41.7% a few versions back):
         (1) OI_THRESHOLD_PCT reverted 0.08 -> 0.05, undoing the earlier
         raise — testing whether the looser OI filter correlates with
         breakout's decline.
         (2) PARAM_GRID_BUFFER: re-added 0.15 (now [0.15,0.20,0.35,0.50]),
         which had been dropped earlier in this session when LOSS
         median MFE was ~1.7R (tight buffers were getting stopped out
         before eventually reversing "the right way"). Bounce's LOSS
         MFE has since fallen to ~0.48R and WIN MAE sits at ~0.18R
         (winners barely dip toward the stop at all) — the data that
         justified excluding the tight buffer no longer holds, so
         letting the auto-tuner test it again rather than assuming.
         Verified backtest_params runs cleanly with buffer=0.15 directly,
         and the full scan-function/endpoint regression stayed clean.
v0.37.1 - the EMA reverse-signal hypothesis (v0.34.1) is now CONFIRMED
         live: n=86 closed, 54.7% win rate vs. RR=1.5's 40% breakeven,
         +0.37R/trade — a real edge, not a guess anymore. Round 2
         retune off that live data's own at-close numbers: WIN MFE sat
         at median 2.065R/avg 3.842R (well above the old RR=1.5),
         meaning the TP was cutting winners short, so EMA_TP_PCT moved
         0.0075->0.01 (0.75%->1.0%, roughly the median, capturing most
         of the current win population fully rather than clipping it).
         WIN MAE sat at median 0/avg 0.214R/p75 0.356R — winners barely
         dipped toward the stop — so EMA_RR moved 1.5->2.5, giving
         SL=0.4% (comfortable buffer above p75, down from 0.5%). Also
         flagged in the config comment that LOSS MAE ran noticeably
         above the nominal 1R (median 1.697R/avg 2.89R) on the 1h
         timeframe with this tight a stop — not a bug, just volatile
         candles against a narrow stop, worth keeping in mind for real
         position sizing. Verified the new defaults compute to exactly
         TP=1.0%/SL=0.4% in both directions, and the full scan-function/
         endpoint regression stayed clean.
v0.38.0 - two scalp-module changes from user feedback (with a live
         screenshot showing ~96/189 symbols with no safe config and
         most rows missing confirmed leverage/MMR):
         (1) FIX: get_futures_risk_limit_tiers() made a single
         unpaginated request. Gate's own docs say the endpoint defaults
         to the top 100 markets when no `contract` filter is passed —
         confirmed as the root cause, matching the observed pattern
         (roughly half the universe never had a chance to get real
         data). Now paginates with limit/offset until a page comes back
         empty, capped at 30 pages as a safety net. Verified against
         250 mocked symbols across multiple pages (all covered
         correctly), and that a network failure mid-pagination keeps
         already-fetched pages rather than discarding everything.
         (2) NEW: live signal generation on top of the stats-only
         engine — scan_symbol_scalp_signal() enters at the most
         recently closed candle's close (same candles[-1] convention
         EMA/divergence already use) on whichever interval/direction/
         target% recommend_scalp_config() currently recommends for that
         symbol, no stop per the original spec: outcome is WIN (target
         touched) or TIMEOUT, never LOSS. Per-(symbol,interval)
         cooldown keyed to the candle's own timestamp prevents refiring
         on the same still-open candle. Wired into the existing fast
         45s scan_loop (using the already-computed, slow-refresh
         recommendations — no expensive recompute on the fast path) and
         update_scalp_signal_outcomes() alongside it. New
         /api/scalp/signals route, compute_scalp_signal_stats() for a
         win-rate summary now included in /api/scalp/status, reset
         endpoint clears signals too, and a live-signals table now sits
         above the recommendations table in the Скальпинг tab.
         Verified directly: signal creation, same-candle dedup via
         cooldown, WIN detection (forced target touch), TIMEOUT
         detection (backdated timeout), and the full scan-function/
         endpoint regression — all clean.
v0.39.0 - hourly Telegram digest across all four modes. New
         hourly_stats_loop() thread, own independent 1h cadence
         (VP_HOURLY_STATS_INTERVAL_SEC), separate from every other loop.
         build_hourly_stats_report() pulls compute_signal_stats() /
         compute_divergence_stats() / compute_ema_stats() /
         compute_scalp_signal_stats() and formats a compact HTML summary
         — winrate, W/L, open count per mode, Volume's bounce/breakout
         split, and a [РЕВЕРС] tag on Дивергенции/EMA when their invert
         toggles are active, so the digest doesn't read misleadingly
         after a reverse-mode switch. New "hourly" Telegram category
         (gated the same way vp/div/ema already are), its own toggle in
         settings ("↳ Часовая статистика"), plus VP_HOURLY_STATS_ENABLED
         as an env-only master switch alongside the Telegram gate.
         Verified the report builds correctly on both empty state and
         populated state (including the [РЕВЕРС] tags rendering
         correctly), confirmed the "hourly" category gate actually
         blocks/allows queuing via the real _telegram_send_queue (an
         earlier version of this same test checked the wrong queue
         variable name and would have passed either way — caught before
         trusting it), and the full scan-function/endpoint regression
         stayed clean.
v0.39.1 - removed the weekly (1w) timeframe from EMA scanning per user
         request — EMA_INTERVALS now defaults to just EMA_INTERVAL
         ("1h") instead of "1h,1w". Weekly signals were always going to
         be rare by nature (one bar a week) and never accumulated
         meaningful data to compare against 1h. Existing 1w signals
         already in history are untouched and still track their
         outcome correctly (update_ema_outcomes reads each signal's own
         stored interval, independent of the scan list), so nothing
         needs resetting — only new 1w signal creation stops. Verified
         EMA_INTERVALS resolves to ['1h'], the full scan-function sweep
         stayed clean, and /api/ema/status reports the single interval
         correctly.
v0.40.0 - UI restructure per user feedback (with screenshot): the
         persistent header showed detailed Volume-specific stats
         (winrate breakdown, bounce/breakout split, auto-tune progress,
         rejected-this-scan counts) even while a completely different
         tab like EMA was open — confusing, and inconsistent with every
         other mode which keeps its stats inside its own tab. New
         /api/overview endpoint returns a compact winrate/W-L/open
         summary for all four modes in one call (avoids hitting four
         separate endpoints on every 15s poll regardless of which tab
         is active). Header now shows just the general v/scan-time line
         plus one compact multi-mode line — "Volume 41.4% (63W/89L)
         откр.20 · Див[Р] 33.3%... · EMA[Р] 54.7%... · Скальп 60%..." —
         with a [Р] marker when a mode's reverse toggle is on. All the
         detailed Volume-specific content that used to live in the
         header moved into the Volume tab itself (refreshTuning now
         also fetches /api/status and prepends that detail above the
         existing MFE/MAE stats), matching the layout every other tab
         already uses. Also removed the Watchlist tab entirely per
         direct request — tab button, table markup, refreshWatch(), and
         all references cleaned up (the underlying /api/watchlist route
         is left as-is, just unused by the UI now).
         Verified: JS syntax and undefined-variable sweep clean, no
         leftover watch/watchTable/refreshWatch references anywhere
         live in the code (only the historical changelog mention
         remains), /api/overview returns correctly shaped data, and the
         full scan-function/endpoint regression stayed clean.
v0.40.1 - color-coded the new overview header line, reusing the app's
         existing classes rather than inventing new ones: winrate green
         (.win) at >=50%, red (.loss) below, grey (.dim) with no data
         yet; W count always green, L count always red; open count in
         the same amber (.status-open) used for OPEN rows elsewhere;
         Скальп's TIMEOUT count uses .status-timeout to match. Verified
         JS syntax/undefined-var sweep and the full scan-function/
         endpoint regression stayed clean.
v0.41.0 - new "Сессия" module: London-session-open liquidity-sweep
         manipulation (user's screenshot: price consolidates, the
         session open sweeps one side of that range grabbing stops,
         then closes back inside — trade the reversal to the opposite
         side). Core detect_session_manipulation() is shared by live
         scanning and historical backtesting. Session open is 10:00
         Europe/Kyiv, DST-aware via zoneinfo (07:00 UTC in summer,
         08:00 in winter) rather than a hardcoded UTC hour. The
         consolidation range is the PRIOR (Asian) session — from
         00:00 UTC to the session open, ~7-8h depending on DST, not a
         fixed lookback window (corrected mid-session per user
         feedback). SL sits just beyond the sweep's own extreme
         (+0.1% buffer), TP is the opposite side of the range — a
         measured-move target, so RR floats per-day rather than being
         fixed like the other three modules, which matches the
         pattern's actual logic.
         Two real bugs caught and fixed while reconciling work written
         across separate sessions: (1) a full STATE-key and config
         duplication (session_backtest vs session_backtest_results/
         summary, session_last_build_* vs session_last_backtest_*,
         SESSION_REFRESH_SEC vs SESSION_BACKTEST_REFRESH_SEC) — merged
         to one consistent schema; (2) the daily wait-loop recomputed
         next_open_ts mid-sleep, which after crossing the target would
         see "today's open is in the past" and jump straight to
         tomorrow — skipping the entire day's window. Fixed by sleeping
         in bounded chunks toward one fixed target instead of
         recomputing it, and confirmed with a fake-clock test that the
         old logic really did skip a day while the new one lands
         exactly on target.
         Two loops: session_loop (batch-backtests the whole liquidity-
         ranked universe once a day) and session_live_loop (sleeps
         until precisely the next session open, then scans the
         backtest-ranked universe for 30 min looking for a live
         signal). Outcome tracking wired into the existing fast
         scan_loop. Four new API routes, settings toggles (module +
         its own Telegram alert category), reset button, and a
         "Сессия" tab with backtest-ranking table + live-signals table,
         matching every other module's layout.
         Also caught via direct testing (not just reading the code):
         session_enabled and telegram_alerts_session were wired into
         SETTINGS_KEYS and get_settings() but never into
         apply_settings() — the toggles existed in the UI but silently
         did nothing. Found by actually posting a settings change and
         checking the echoed value came back wrong, not by inspection.
         Fixed, then re-verified every single one of the 16 settings
         keys round-trips correctly, not just the two that broke.
         Verified end-to-end: DST-transition test on the real 2026
         EU changeover date, detection against a direct reproduction
         of the screenshot's pattern (SHORT case) plus its LONG
         mirror, all edge cases (no sweep, both-sides-swept ambiguity,
         too-flat range), the wait-loop fix against the exact bug
         scenario, and the full scan-function/endpoint regression.
v0.41.1 - user's first live backtest finished in 21.1s for "0/100"
         symbols — far too fast for real paginated 60-day-history
         fetches, meaning every symbol was failing near-instantly
         before any network call. Prime suspect: Termux/Android Python
         builds often ship without the system IANA tzdata database
         zoneinfo relies on by default (unlike a normal Linux distro),
         so every ZoneInfo(SESSION_TZ_NAME) call would raise
         identically — impossible to confirm directly in this sandbox
         (which does have system tzdata), but reproduced the exact
         failure mode with a mocked ZoneInfoNotFoundError and confirmed
         it explains both symptoms (instant "failure", 0 successes).
         Added get_session_tz(): caches the ZoneInfo object, and on
         first failure logs ONE clear diagnostic naming the likely
         cause and the fix (pip install tzdata --break-system-packages)
         instead of the same opaque error 100 times, once per symbol,
         burying the actual cause. Verified: 5 repeated failing calls
         now log exactly 1 error (not 5), the working-timezone case is
         completely unaffected (empty error log, all functions still
         return normally), and the full scan-function/endpoint
         regression stayed clean.
v0.41.2 - tzdata fix worked (no more timezone errors), but every
         session backtest then 400'd on the FIRST candlestick fetch —
         get_candles_range() had never been exercised at 60-day scale
         before (its original use was short bar-magnification ranges),
         and Gate's own SDK docs disagree with each other on the real
         per-request point cap (1000 in some, 2000 in others); the
         actual server rejected a chunk sized for ~1900 points. Rather
         than guess a single new hardcoded number that might also be
         wrong, made get_candles_range() self-adjusting: starts at a
         conservative 900 points, and if the server 400s a chunk,
         halves the size and retries — remembering the smaller size for
         every later chunk in the same call instead of re-discovering
         it from scratch each time (checked this specifically: without
         memoization, a 60-day pull would re-fail at 900 on every
         single chunk; with it, only the first 1-2 chunks pay the
         discovery cost). Verified against a simulated server with an
         arbitrary 400-point limit: correctly discovers and settles on
         225 points after two halvings, and a full 8-chunk range needed
         only 2 failed calls total, not 16. Full scan-function/endpoint
         regression stayed clean.
v0.42.0 - tzdata still wouldn't install on the user's Termux — pip
         itself was broken (python3.14t executable linked against a
         missing libpython3.14t.so), an environment problem unrelated
         to this app and not fixable from here. User offered Moscow
         10:00 as an acceptable substitute for Kyiv. Took that further:
         Moscow has used a fixed UTC+3 with no DST since 2014, so
         "10:00 Moscow" is always exactly 07:00 UTC — no timezone
         database needed at all. Replaced the whole zoneinfo/ZoneInfo-
         based session_open_utc_ts() with plain datetime arithmetic
         (SESSION_UTC_OFFSET_HOURS, default 3), removed the now-dead
         get_session_tz() cache/diagnostic and the zoneinfo import
         entirely — this class of problem can't recur since there's no
         external tz database dependency left in the module at all.
         Traded away true Kyiv-local DST-awareness (drifts 1h from Kyiv
         during the EU winter half of the year) for something that
         works unconditionally, per direct user request rather than
         continuing to fight a broken pip/python install neither of us
         can see. SESSION_TZ_NAME config and the API's tz_name field
         renamed to SESSION_UTC_OFFSET_HOURS/utc_offset_hours
         throughout (config, API, UI). Verified session_open_utc_ts()
         resolves to exactly 07:00 UTC across all four tested dates
         (summer, winter, and both 2026 DST transition dates — now
         correctly IDENTICAL across all of them, which is the whole
         point), and the full scan-function/endpoint regression
         stayed clean.
v0.42.1 - the chunk-halving fix from v0.41.2 didn't actually solve the
         backtest 400s — user's log showed it still failing even after
         self-halving all the way down to a 28-point request. That
         ruled out "chunk too big" as the cause. Root cause, confirmed
         via a public ccxt issue: Gate silently started enforcing
         "Candlestick too long ago. Maximum 10000 points recently are
         allowed" around Feb 2026 — a hard floor on how far `from` can
         be from NOW, totally independent of how small the requested
         span is, so no amount of chunk-size reduction could ever have
         fixed it. For 5m candles that's ~34.7 days; SESSION_BACKTEST_
         DAYS defaulted to 60, comfortably over the wall. Two fixes:
         (1) SESSION_BACKTEST_DAYS 60->30, safely inside the limit; (2)
         get_candles_range() now proactively clamps its start_ts up
         front to the earliest allowed point (9800 candles back, a
         margin under the confirmed 10000) instead of ever attempting
         the doomed request — no wasted 400s at all now, vs. before
         where every single symbol burned 5-6 failing requests each
         cycle before giving up. Kept the v0.41.2 chunk-halving as a
         secondary safety net (a genuine over-sized-chunk rejection may
         still be real; Gate's own docs disagree with each other on
         that separate number too), but it's no longer load-bearing for
         this specific failure. Verified directly: a simulated 60-day
         request against a mocked API confirms the first chunk's `from`
         now lands at ~34 days back, not 60.
v0.42.2 - user confirmed they're actually in Moscow, so v0.42.0's
         fixed-UTC+3-no-DST design is exactly right for them, not just
         an acceptable substitute — no code change needed there.
         Cleaned up a docstring that was left stale by that same
         change: detect_session_manipulation() still said the
         consolidation range "varies 7-8h depending on DST", which was
         true under the old Kyiv+zoneinfo version but hasn't been since
         v0.42.0 removed DST entirely. Verified directly: the range is
         now exactly 7.0h on all four previously-varying test dates
         (summer, winter, both 2026 DST transition dates), confirming
         the fix's own behavior matches the corrected docstring.
v0.43.0 - chart visualization for Сессия, matching the click-to-view
         pattern every other mode already has. New /api/session/chart/
         <symbol>?session_open=<ts> route: re-runs detect_session_
         manipulation() on freshly fetched candles for that specific
         day rather than looking anything up from stored records —
         works identically for a past backtest day or a live signal,
         since both are just (symbol, session_open) and detection is
         fully deterministic from candle data alone. New sessionModal
         (mirrors the div/ema modal pattern exactly: own canvas, own
         header, own close button) with drawSessionChart() — candles,
         a shaded band for the consolidation range (range_high/low), a
         dashed vertical line marking the session open, and entry/SL/TP
         level lines, reusing the existing windowAroundTime/
         computeYRangeForZone/drawLevelLine helpers rather than
         reinventing them. Both places a user would want to click now
         open the chart: live-signal rows directly, and each day in a
         symbol's backtest-history detail view (previously plain text,
         now clickable spans). Had to fix the click-wiring for the
         Сессия tab's two different row types (live signals vs.
         backtest-ranking rows) which both carry data-symbol — split
         into wireSessionRowClicks() disambiguating on the presence of
         data-session-open, and fixed a real gap where the early-return
         path (no backtest results yet) never wired the live-signals
         rows' clicks at all.
         Verified: the chart endpoint returns correctly shaped data
         end-to-end, JS syntax/undefined-var/duplicate-id sweeps all
         clean, and the full scan-function/endpoint regression
         (including the new chart route) stayed clean.
v0.44.0 - user hit computeYRangeForZone's scaling being uninformative
         again (screenshot: a divergence chart with a huge dead-empty
         upper section, entry/TP/SL squeezed low, hard to read) and
         asked to drop the "smart" scaling entirely — for Сессия
         charts specifically at first (plain candles, no tricks), then
         extended to all the older chart types too after this latest
         example. Given the zone-bias logic had already been tuned
         through several rounds this session (30% target -> capped
         compression -> etc.) and was still producing bad results
         sometimes, simplifying beats iterating further: added
         computeYRangeSimple() — natural min/max of the visible candles
         plus the trade levels, with plain 5% padding, no compression,
         no "near-bars" logic. Replaced all four computeYRangeForZone()
         call sites (VP, divergence, EMA, session) with it, then
         deleted computeYRangeForZone() entirely since nothing called
         it anymore. Session's chart also dropped its windowAroundTime
         crop and now shows every candle in the API response directly
         (the fetch range itself is already reasonably bounded) rather
         than a narrowed window, matching the "just show many candles"
         request literally.
         Verified: JS syntax/undefined-var sweep clean, confirmed via
         grep that computeYRangeForZone has zero remaining references
         anywhere (not even the definition), and the full scan-function/
         endpoint regression (all four chart-backing scan functions +
         the session chart route) stayed clean.
v0.44.1 - two fixes from user feedback (screenshots): (1) Сессия's
         per-symbol day-by-day detail (sessionDetail) rendered BELOW
         the full backtest-ranking table, so clicking any row required
         scrolling past potentially 100+ rows to see what was clicked —
         moved it above the ranking table instead, same "don't make me
         scroll for what I just clicked" fix applied to other tabs'
         stats earlier this session. (2) Volume's winrate got WORSE
         after the v0.37.0 experiments, not better (45.3% -> 33.3%) —
         reverted both OI_THRESHOLD_PCT (0.05 -> back to 0.08) and
         PARAM_GRID_BUFFER (dropped the re-added 0.15, back to
         [0.20,0.35,0.50]) per direct request rather than continuing to
         chase it. Existing per-symbol tuned overrides that had already
         settled on buffer=0.15 during the ~week those changes were
         live would otherwise keep using it until their next scheduled
         48h re-tune — pointed the user at the existing "Очистить
         объём" button (already clears SYMBOL_OVERRIDES) instead of
         writing new reset logic, since that mechanism already exists
         and forces an immediate re-tune against the reverted grid.
         Verified: full scan-function/endpoint regression stayed clean,
         and confirmed the reverted config values load correctly.
v0.44.2 - divergence reverse mode is working (55.6% win rate) but user
         wanted a better RR. Round 2 retune off the reversed direction's
         own live at-close data (n=8, 5W/3L — still a tiny sample,
         weaker basis than EMA's analogous round-2 retune which had
         n=86, flagged explicitly): WIN MFE sat at median 1.348R/avg
         1.935R (R=0.75% at the old config), well above the old
         0.65% TP, meaning it was cutting winners short — DIV_TP_PCT
         moved 0.0065->0.01 (0.65%->1.0%). WIN MAE sat at median 0/avg
         0.264R — winners barely dipped toward the stop — so DIV_RR
         moved 0.867->2.0, giving SL=0.5% (down from 0.75%), with
         headroom above the p75 WIN MAE reference point. Verified the
         new defaults compute to exactly TP=1.0%/SL=0.5% in both
         directions, and the full scan-function/endpoint regression
         stayed clean.
v0.45.0 - Сессия's manipulation detection redesigned per user feedback
         (screenshot showing a live signal whose entry sat near the
         session open, not the obvious sweep candle they circled). The
         original design allowed the sweep and the close-back-inside
         confirmation to be arbitrarily far apart within the whole
         30-min window; a first attempt tightened this to requiring
         both on the SAME candle, but the user went back to the
         original reference screenshot and clarified the real pattern
         is a short 2-3 candle thrust (sweep, brief drift, then
         reversal), not strictly one bar. New VP_SESSION_MAX_THRUST_BARS
         (default 3): for each candle whose own close lands back inside
         the range, looks back at just that trailing cluster (up to 3
         bars including itself) for a sweep, rather than the entire
         window. Confirmed via direct testing that a "sweep now, clean
         drift for several bars, confirm much later" scenario is
         actually architecturally impossible to construct — a candle
         whose close stays outside the range necessarily has its own
         high/low outside too (high>=close, low<=close), so it's always
         itself a fresh nearby sweep; the cluster naturally uses
         whichever sweep is most recent rather than a stale one,
         which is the sensible behavior. Verified: single-candle
         sweep+reject still works (the 1-bar case is a special case of
         the cluster logic), a 3-bar thrust with the sweep 2 bars
         before confirmation correctly picks up the right sweep_extreme,
         no-sweep/both-sides-ambiguous/LONG-mirror/flat-range all still
         behave correctly, and the full scan-function/endpoint
         regression stayed clean. Old backtest/signal history under the
         previous detection logic is no longer comparable — worth a
         "Очистить сессию" before trusting fresh numbers.
v0.45.1 - two fixes from a live example (BANK_USDT LONG, screenshot):
         (1) SESSION_SL_BUFFER_PCT 0.1%->0.5% — the chart showed a
         shallow bounce confirming the pattern (closing back inside the
         range) before the REAL low was actually reached a bit later —
         a double-dip, where the first reversal attempt fails and stops
         get run again before the genuine move. The old 0.1% buffer sat
         right at the shallow bounce's own extreme, so the deeper
         second dip stopped the trade out just before it turned into a
         winner (visibly ran most of the way to TP afterward). Didn't
         redesign the confirmation window itself — that would need more
         live data to get right — just gave the stop more room to
         survive exactly this kind of continuation.
         (2) SESSION_UNIVERSE_SIZE 100->50, per direct request to focus
         on the most liquid coins specifically — already sorted by 24h
         volume descending, this just cuts deeper into that ranking
         rather than reaching into the less-liquid tail.
         Verified: new config values load correctly (buffer=0.005,
         universe size=50 confirmed against a mocked 150-symbol
         ticker list), and the full scan-function/endpoint regression
         stayed clean.
v0.45.2 - settings modal redesigned per direct request — was one
         continuous flat list of 15 toggle rows with no visual
         separation, hard to scan. New .settingsGroup card style: each
         module (Volume Profile, Дивергенции, EMA, Скальпинг, Сессия,
         Telegram) is its own bordered, rounded card with an uppercase
         section title, matching toggles grouped inside it instead of
         one undifferentiated column. All 15 checkbox IDs kept
         identical (setVolumeProfile, setBounce, ... setTelegramHourly)
         so no JS wiring changed, just the surrounding markup/CSS.
         Verified: all 15 IDs still present exactly once (no
         duplicates from the restructure), JS syntax clean, and a full
         settings round-trip (posting all 16 SETTINGS_KEYS as true and
         reading them back) confirmed every key still applies
         correctly through the reorganized markup.
v0.46.0 - two scalp module changes from direct feedback: (1) live
         signals now only fire for the top SCALP_SIGNAL_TOP_N (default
         1) symbols by score each cycle, not every qualifying one —
         selection happens in the fast scan_loop, sorting the
         recommendation snapshot by score before submitting to
         scan_symbol_scalp_signal. (2) Added a real SL — user asked
         directly whether "no stop" was an actual requirement or just
         something Claude assumed; it was the latter, carried over
         from the original stats-only module's methodology (which only
         measured target-hit probability, no stop-survival concept at
         all). Rather than invent an arbitrary stop, used data the
         module was already computing: SL sits at p90_adverse_pct
         (the 90th-percentile adverse excursion the stats engine
         already measures) plus a 20% buffer (SCALP_SL_BUFFER_MULT) —
         a hard floor at the exact p90 would still stop out ~10% of
         otherwise-fine trades on normal noise. update_scalp_signal_
         outcomes() now checks SL before TP within the same candle
         (same conservative convention as the session module), with a
         LOSS result added alongside WIN/TIMEOUT; compute_scalp_signal_
         stats() and every place it feeds (header overview, hourly
         Telegram digest, the Скальпинг tab's own panel) updated to
         show losses and use the same wins/(wins+losses) winrate
         convention every other module already uses (timeouts excluded
         from the denominator). Backward compatible: old signals
         without sl_price just skip the SL check, same as before.
         Verified: SL computes to the expected p90*1.2 value, forcing
         a price move to the SL level correctly produces a LOSS result
         and updates the stats correctly, the top-N selection picks
         the right highest-scored symbol, JS syntax is clean, and the
         full scan-function/endpoint regression stayed clean.
v0.46.1 - SCALP_SIGNALS_ENABLED had no settings UI at all — it was
         wired into scan_loop and the outputs it feeds, but never added
         to SETTINGS_KEYS/get_settings/apply_settings or given a
         checkbox, so there was no way to toggle live scalp signals
         off separately from the underlying stats module. Added
         scalp_signals_enabled throughout (settings dict, mutation
         logic — remembered this time, unlike the session_enabled miss
         a few versions back — checkbox registration) and a new "↳
         Живые сигналы" row under Скальпинг in the settings UI. Also
         fixed the Скальпинг group's now-stale "без сигналов"
         description, left over from before signal generation existed.
         Verified: the new toggle actually changes SCALP_SIGNALS_ENABLED
         (not just echoes back the posted value), a full round-trip of
         all 17 settings keys still applies correctly, and the full
         scan-function/endpoint regression stayed clean.
v0.46.2 - user didn't see BTC/ETH in the Сессия ranked list despite
         asking for the most liquid coins. Prime suspect: they ARE in
         the liquidity-selected universe (BTC/ETH are almost certainly
         top-2 by volume) but likely just never showed a qualifying
         manipulation — majors tend to have lower % volatility than
         alts, and SESSION_MIN_RANGE_PCT (0.3%) would filter out an
         overnight range that never gets that wide, giving them n=0
         across the whole backtest, which api_session_status silently
         dropped from the ranked list with no distinction from "not
         selected as liquid enough" at all. Rather than guess further,
         made this directly checkable: /api/session/status now returns
         zero_manipulation_count, not_yet_processed_count, and a
         watch_symbols block explicitly reporting BTC_USDT/ETH_USDT's
         exact status (ranked / zero_manipulations_found /
         not_yet_processed / not_in_universe) with their n. Surfaced
         directly in the Сессия tab header instead of requiring a
         manual API call. Verified with mocked state covering all four
         statuses at once (BTC/ETH zero-manipulation, one ranked
         symbol, one not-yet-processed) — counts and per-symbol status
         all came back correct — plus the full scan-function/endpoint
         regression stayed clean.
v0.47.0 - user shared a batch of live screenshots across every module
         and asked for analysis + recommendations. Two follow-throughs
         from that review, both confirmed with the user first:
         (1) EMA reverse round 3 retune off n=70 closed live data:
         at-close WIN MAE sat at median 0/p75 0.269R — winners barely
         dipped toward the stop — while the full-window WIN MFE sat at
         median 7.725R/p25 4.471R, several times past the round-2 TP
         (2.5R) actually captured. Anchored the new TP to the full
         window's p25 (not the median/avg, to avoid overfitting to
         outliers) then rounded down to a more measured step:
         EMA_TP_PCT 1.0%->1.5%, EMA_RR 2.5->5.0 (SL 0.4%->0.3%).
         Breakeven win rate needed drops to ~16.7%, wide margin below
         the 50% observed even allowing for a real decline post-retune.
         (2) Volume's bounce reason (30.8%, below the 33.3% breakeven
         at RR=2) vs breakout (50%) — bounce/breakout already get
         independently auto-tuned RR/buffer per symbol from the same
         grid, so the likely issue isn't a global default to tweak, and
         guessing new numbers without reason-specific MFE/MAE data would
         just be another blind guess, not a real retune. Instead added
         the missing visibility: compute_tuning_stats() takes an
         optional reason filter, /api/tuning now returns a by_reason
         breakdown (bounce/breakout) alongside the combined numbers, and
         the Volume tab's stats panel shows both side by side. No
         parameter change yet — needs this data to actually accumulate
         before a bounce-specific retune would be anything but a guess.
         Verified: new EMA TP/SL compute to the exact expected 1.5%/0.3%
         in both directions, the reason-filtered tuning stats correctly
         separate bounce/breakout in a direct test, fmtStat handles the
         undefined case gracefully for symbols with no reason-specific
         data yet, and the full scan-function/endpoint regression
         stayed clean.
"""

import os
import json
import time
import math
import threading
import traceback
import queue
import datetime
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, jsonify, request, Response

APP_VERSION = "0.47.0"

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
MAX_SYMBOLS = int(os.environ.get("VP_MAX_SYMBOLS", 250))  # universe cap — was 150, raised per user request (hardware headroom available)
# master switch for the whole volume-profile screener (zones, bounce/breakout
# signals, watchlist, auto-tuning) — turn off to run divergence-only
VOLUME_PROFILE_ENABLED = os.environ.get("VP_VOLUME_PROFILE_ENABLED", "1") == "1"
SCAN_INTERVAL_SEC = int(os.environ.get("VP_SCAN_INTERVAL", 45))
COOLDOWN_SEC = int(os.environ.get("VP_COOLDOWN", 900))    # per-symbol re-alert cooldown, applied after a signal on that symbol closes
WORKERS = int(os.environ.get("VP_WORKERS", 12))  # was 8, raised alongside MAX_SYMBOLS
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
DIV_PIVOT_RIGHT = int(os.environ.get("VP_DIV_PIVOT_RIGHT", 3))  # reverted from 2 -> 3 after a live example showed the divergence firing well after the bounce had already largely played out (screenshot: entry sat below a candle that had already tagged above TP). Note: going slower should, if anything, make lateness worse, not better, by the pivot-confirmation-delay logic alone — reverted per direct request anyway, worth watching pre_move_pct data to see if it actually helps
# Стандартная практика торговли дивергенциями: сигнал считается живым
# ровно в момент подтверждения пивота (right баров после самого пивота),
# а не ещё сколько-то баров сверху. По умолчанию равен DIV_PIVOT_RIGHT —
# это минимально возможное значение (раньше пивот физически не может
# быть подтверждён), поэтому сигнал срабатывает один раз, точно на баре
# подтверждения, и не "протухает" через дополнительные 5 баров, как было
# при freshness=8 vs right=3.
DIV_FRESHNESS_BARS = int(os.environ.get("VP_DIV_FRESHNESS_BARS", DIV_PIVOT_RIGHT))
# Diagnostic only, doesn't affect live detection: for each fired signal,
# check whether a SMALLER right-confirmation window would have picked the
# exact same pivot bar using only the data that would actually have been
# available at that earlier point in time (not the full future dataset —
# that comparison is meaningless, since a pivot confirmed with the full
# window trivially also satisfies any smaller one in hindsight). This is
# what actually tells us the risk of reducing VP_DIV_PIVOT_RIGHT: how
# often would going faster have picked a different, wrong point instead.
DIV_SHADOW_RIGHTS = [int(x) for x in os.environ.get("VP_DIV_SHADOW_RIGHTS", "1,2").split(",") if x.strip()]  # only values below DIV_PIVOT_RIGHT are meaningful for the stability diagnostic
DIV_RR = float(os.environ.get("VP_DIV_RR", 2.0))  # round 2 retune — see DIV_TP_PCT comment. Was 0.867 for round 1 (pre-data guess).
DIV_TP_PCT = float(os.environ.get("VP_DIV_TP_PCT", 0.01))  # TP is a fixed % move from entry — SL is then sized backward from this via DIV_RR, rather than TP being derived from a pivot-based SL.
# Round 1 (0.011/RR2.0 -> 0.0065/RR0.867) was a pre-data guess for the
# reversed hypothesis, off the ORIGINAL direction's own stats.
# Round 2, off the REVERSED direction's own live at-close data (n=8,
# 5W/3L — still a tiny sample, weaker basis than EMA's round-2 retune
# which had n=86): WIN MFE sat at median 1.348R/avg 1.935R (R=0.75%
# then) — well above the old target, meaning TP was cutting winners
# short — so TP moved up to ~1.0%. WIN MAE sat at median 0/avg 0.264R
# — winners barely dipped toward the stop at all — so SL tightened to
# ~0.5% (RR=2.0), giving headroom above the p75 WIN MAE (0.337R at the
# old R, ~0.253%) without going razor-thin on an 8-trade sample.
# CAVEAT: even more than round 1, this is a low-confidence tune —
# treat as a starting guess to test forward, not a validated figure.
DIV_INVERT_SIGNALS = os.environ.get("VP_DIV_INVERT_SIGNALS", "0") == "1"  # a live example showed the divergence-implied bounce often already largely played out by the time the signal actually fires — worth testing whether trading the OPPOSITE direction (effectively fading the already-completed move) does better than trading the original signal late
DIV_COOLDOWN_SEC = int(os.environ.get("VP_DIV_COOLDOWN", 3600))
DIV_SIGNAL_HISTORY = 200

# ----------------------------------------------------------------------------
# EMA 7/14/28 signal indicator — ported from a user-supplied Pine Script
# ("EMA 7,14,28 + Сигналы"). A third, fully separate signal source: own
# scan, own history/stats, own chart, own Telegram category. Three
# possible crossover definitions (price/EMA7, EMA7/EMA14, or both
# combined), optionally filtered by trend (price vs EMA28) — exactly
# mirroring the Pine Script's own input options.
# ----------------------------------------------------------------------------
EMA_ENABLED = os.environ.get("VP_EMA_ENABLED", "1") == "1"
EMA_INTERVAL = os.environ.get("VP_EMA_INTERVAL", "1h")  # kept for backward-compat single-interval env overrides
# the script's own developer runs it on the weekly chart — scanning both
# alongside the existing 1h lets stats be compared later rather than
# guessing which is better upfront
EMA_INTERVALS = [x.strip() for x in os.environ.get("VP_EMA_INTERVALS", EMA_INTERVAL).split(",") if x.strip()]  # was f"{EMA_INTERVAL},1w" — weekly removed per user request (accumulated almost no signals, wasn't worth the ongoing comparison)
EMA_FETCH_LIMIT = int(os.environ.get("VP_EMA_FETCH_LIMIT", 200))
EMA_LEN_7 = int(os.environ.get("VP_EMA_LEN_7", 7))
EMA_LEN_14 = int(os.environ.get("VP_EMA_LEN_14", 14))
EMA_LEN_28 = int(os.environ.get("VP_EMA_LEN_28", 28))
# "price_ema7" = Pine's "Пересечение цены и EMA7"; "ema7_ema14" = "Пересечение
# EMA7 и EMA14"; "combined" = "Комбинированный" (price crosses EMA7 AND EMA7
# is already on the trade's side of EMA14)
EMA_SIGNAL_TYPE = os.environ.get("VP_EMA_SIGNAL_TYPE", "combined")
EMA_TREND_FILTER = os.environ.get("VP_EMA_TREND_FILTER", "1") == "1"  # only BUY above EMA28 / SELL below it, same as the script's "Фильтровать по тренду"
EMA_INVERT_SIGNALS = os.environ.get("VP_EMA_INVERT_SIGNALS", "0") == "1"  # user hypothesis: this indicator's config has been systematically wrong more often than right (22.4% win rate at RR=2) — worth testing whether trading the OPPOSITE of what it says works, with its own (smaller, asymmetric) TP/SL rather than reusing the original's
EMA_COOLDOWN_SEC = int(os.environ.get("VP_EMA_COOLDOWN", 3600))
EMA_SIGNAL_HISTORY = 200
# the Pine Script only plots BUY/SELL labels, no TP/SL of its own — added
# a fixed-% TP (mirroring the divergence signals) purely so this fits the
# same win-rate/MFE/MAE tracking as everything else in the app.
# Round 1 retune (0.015/2.0 -> 0.0075/1.5) was for the reverse-signal
# hypothesis before it had any of its own data. That hypothesis has since
# been CONFIRMED live: n=86 closed at 54.7% win rate vs. RR=1.5's 40%
# breakeven, +0.37R/trade — a real, validated edge, not a guess.
# Round 2 retune, off THAT reversed data's own at-close stats: WIN MFE
# sat at median 2.065R/avg 3.842R (R=0.5% then) — well above the old
# RR=1.5, meaning the TP was cutting winners short — so TP moved up to
# ~1.0% (roughly the median, capturing most of the current win
# population fully). WIN MAE sat at median 0/avg 0.214R/p75 0.356R —
# winners barely dipped toward the stop at all — so SL tightened to
# ~0.4% (comfortable buffer above p75, well below the old 0.5%).
# RR=2.5. If reverting to the non-inverted signal, these should
# probably go back to something re-derived for that direction instead —
# neither retune round was validated for it.
EMA_TP_PCT = float(os.environ.get("VP_EMA_TP_PCT", 0.015))  # round 3 — see comment above/below
EMA_RR = float(os.environ.get("VP_EMA_RR", 5.0))  # round 3
# Round 3 retune, off n=70 closed live reversed-signal data (screenshot):
# at-close WIN MAE sat at median 0/p75 0.269R (R=0.4% under round 2) —
# winners essentially never dipped toward the stop — while the FULL 24h
# window's WIN MFE sat at median 7.725R/p25 4.471R, several times past
# the round-2 TP (2.5R) that was actually captured. Anchored the new TP
# to the full window's p25 (4.471R * 0.4% ≈ 1.8%) rather than the
# median/avg (7.725R/10.843R) to avoid overfitting to outlier moves,
# then rounded down slightly to 1.5% as a more measured step given
# widening TP typically also lowers the realized win rate somewhat —
# unknown by how much until live data comes in at the new levels. SL
# tightened 0.4%->0.3%, still well above the at-close p75 MAE reference
# point. New RR=5.0 vs round 2's 2.5 — breakeven win rate needed drops
# to ~16.7%, a wide margin below the round-2 50% actually observed, even
# allowing for a real winrate decline post-retune.

# ----------------------------------------------------------------------------
# Scalp volatility statistics ("Скальпинг" tab) — a pure exploratory/stats
# tool, no signals, no auto-trading yet. For a universe of the most
# volatile "sawtooth" coins, walks every historical candle as a
# hypothetical entry and measures how long it takes (and how much
# adverse move happens first) to reach various % targets, separately for
# LONG and SHORT, across a few timeframes. This is deliberately NOT a
# signal generator — see /areas note for the full design rationale.
# ----------------------------------------------------------------------------
SCALP_ENABLED = os.environ.get("VP_SCALP_ENABLED", "1") == "1"
SCALP_UNIVERSE_SIZE = int(os.environ.get("VP_SCALP_UNIVERSE_SIZE", 200))
SCALP_RANK_INTERVAL = os.environ.get("VP_SCALP_RANK_INTERVAL", "15m")  # timeframe used to rank symbols by volatility
SCALP_RANK_LOOKBACK = int(os.environ.get("VP_SCALP_RANK_LOOKBACK", 200))  # candles used for the ranking metric
SCALP_INTERVALS = [x.strip() for x in os.environ.get("VP_SCALP_INTERVALS", "5m,15m,1h").split(",") if x.strip()]
SCALP_TARGET_PCTS = [float(x) for x in os.environ.get("VP_SCALP_TARGET_PCTS", "0.3,0.5,1.0,1.5,2.0,3.0").split(",") if x.strip()]
SCALP_MAX_WAIT_SEC = int(os.environ.get("VP_SCALP_MAX_WAIT_SEC", 24 * 3600))  # give up tracking a hypothetical entry after this long
SCALP_FETCH_LIMIT = int(os.environ.get("VP_SCALP_FETCH_LIMIT", 500))
SCALP_TAKER_FEE_PCT = float(os.environ.get("VP_SCALP_TAKER_FEE_PCT", 0.0005))  # 0.05% per side, Gate.io VIP0 default
SCALP_DEFAULT_MMR_PCT = float(os.environ.get("VP_SCALP_DEFAULT_MMR_PCT", 0.006))  # conservative fallback when a contract's own maintenance rate isn't available
SCALP_MMR_SANITY_MIN = float(os.environ.get("VP_SCALP_MMR_SANITY_MIN", 0.0001))  # 0.01% — a fetched "MMR" outside [MIN,MAX] is almost certainly the wrong field, not a real maintenance rate
SCALP_MMR_SANITY_MAX = float(os.environ.get("VP_SCALP_MMR_SANITY_MAX", 0.05))  # 5%
SCALP_LEVERAGE_SANITY_MIN = float(os.environ.get("VP_SCALP_LEVERAGE_SANITY_MIN", 1))
SCALP_LEVERAGE_SANITY_MAX = float(os.environ.get("VP_SCALP_LEVERAGE_SANITY_MAX", 125))  # Gate.io's own advertised ceiling for its most liquid pairs
SCALP_DEFAULT_MAX_LEVERAGE = float(os.environ.get("VP_SCALP_DEFAULT_MAX_LEVERAGE", 10))  # conservative fallback when a contract's own max leverage isn't confirmed — matches what the user found on a real altcoin (VELVET_USDT: 10x), not the 125x majors get
SCALP_REFRESH_SEC = int(os.environ.get("VP_SCALP_REFRESH_SEC", 6 * 3600))  # how often the whole universe gets rebuilt/rescanned — this is a slow, batch stats job, not a live scanner
SCALP_ACCOUNT_USD = float(os.environ.get("VP_SCALP_ACCOUNT_USD", 30.0))
SCALP_TARGET_PROFIT_USD = float(os.environ.get("VP_SCALP_TARGET_PROFIT_USD", 7.0))
# Live signal generation, on top of the stats-only engine above. Enters
# at the most recently closed candle's close (same "candles[-1]" close
# convention the EMA/divergence scanners already use) on whichever
# interval/direction/target% recommend_scalp_config currently picks for
# that symbol — no stop, per the original spec ("без стопа пока что"):
# outcomes are WIN (target touched) or TIMEOUT (never touched within
# the window), there is no LOSS state for this module.
SCALP_SIGNALS_ENABLED = os.environ.get("VP_SCALP_SIGNALS_ENABLED", "1") == "1"
SCALP_SIGNAL_HISTORY = 200
SCALP_SIGNAL_COOLDOWN_SEC = int(os.environ.get("VP_SCALP_SIGNAL_COOLDOWN_SEC", 3600))  # per (symbol, interval) — avoid re-firing every 45s scan tick for the same still-fresh candle
SCALP_SIGNAL_TIMEOUT_MULT = float(os.environ.get("VP_SCALP_SIGNAL_TIMEOUT_MULT", 4.0))  # timeout = this many times the recommendation's own median time-to-hit
SCALP_SL_BUFFER_MULT = float(os.environ.get("VP_SCALP_SL_BUFFER_MULT", 0.2))  # SL = p90_adverse_pct * (1 + this) — some margin beyond the p90 itself, since a hard floor at the exact p90 would still stop out ~10% of otherwise-fine trades on normal noise
SCALP_SIGNAL_TOP_N = int(os.environ.get("VP_SCALP_SIGNAL_TOP_N", 1))  # only fire a live signal for the top-N ranked symbols by score each cycle, not every qualifying one
SCALP_SAFETY_MARGIN = float(os.environ.get("VP_SCALP_SAFETY_MARGIN", 1.5))  # liquidation buffer must exceed the coin's own historical p90 adverse move by this factor before a target/leverage combo is flagged "safe"
SCALP_MIN_HIT_RATE = float(os.environ.get("VP_SCALP_MIN_HIT_RATE", 60.0))  # a target below this hit-rate isn't worth recommending even if technically "safe"

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
OI_THRESHOLD_PCT = float(os.environ.get("VP_OI_THRESHOLD_PCT", 0.08))  # reverted back from 0.05 — the 0.05 experiment (v0.37.0) was meant to test whether it explained breakout's earlier decline, but overall Volume winrate got WORSE after the change (45.3% -> 33.3%), not better, so reverting per direct user request rather than continuing to chase it

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
TELEGRAM_ENABLED = os.environ.get("VP_TG_ENABLED", "1") == "1"  # separate from whether a token exists — lets notifications be muted without losing the token
# per-category toggles, checked in addition to the master TELEGRAM_ENABLED
# above — lets someone mute just one signal source without losing alerts
# from the other.
TELEGRAM_ALERTS_VP = os.environ.get("VP_TG_ALERTS_VP", "1") == "1"
TELEGRAM_ALERTS_DIV = os.environ.get("VP_TG_ALERTS_DIV", "1") == "1"
TELEGRAM_ALERTS_EMA = os.environ.get("VP_TG_ALERTS_EMA", "1") == "1"
TELEGRAM_ALERTS_HOURLY = os.environ.get("VP_TG_ALERTS_HOURLY", "1") == "1"
TELEGRAM_ALERTS_SESSION = os.environ.get("VP_TG_ALERTS_SESSION", "1") == "1"
HOURLY_STATS_ENABLED = os.environ.get("VP_HOURLY_STATS_ENABLED", "1") == "1"
HOURLY_STATS_INTERVAL_SEC = int(os.environ.get("VP_HOURLY_STATS_INTERVAL_SEC", 3600))

# ----------------------------------------------------------------------------
# Session-open manipulation ("Сессия" tab) — London-session liquidity sweep:
# price consolidates into a range, the session open sweeps one side of that
# range (grabbing stops / trapping breakout traders), then closes back
# inside the range — trade the reversal, targeting the opposite side. Same
# detection function is used for live scanning and historical backtesting.
# ----------------------------------------------------------------------------
SESSION_ENABLED = os.environ.get("VP_SESSION_ENABLED", "1") == "1"
SESSION_UTC_OFFSET_HOURS = float(os.environ.get("VP_SESSION_UTC_OFFSET_HOURS", 3))  # Moscow, fixed since 2014 (no DST) — deliberately not Europe/Kyiv+zoneinfo, see session_open_utc_ts() docstring for why
SESSION_OPEN_HOUR_LOCAL = int(os.environ.get("VP_SESSION_OPEN_HOUR_LOCAL", 10))  # 10:00 at SESSION_UTC_OFFSET_HOURS ahead of UTC
SESSION_RANGE_TF = os.environ.get("VP_SESSION_RANGE_TF", "5m")
SESSION_RANGE_START_UTC_HOUR = int(os.environ.get("VP_SESSION_RANGE_START_UTC_HOUR", 0))  # consolidation range spans [this UTC hour, session open) — i.e. the prior (Asian) session, not a fixed lookback window
SESSION_MANIPULATION_WINDOW_MIN = int(os.environ.get("VP_SESSION_MANIPULATION_WINDOW_MIN", 30))  # how long after open to watch for the sweep+reversal
SESSION_SL_BUFFER_PCT = float(os.environ.get("VP_SESSION_SL_BUFFER_PCT", 0.005))  # was 0.1% — a live example showed price continuing well past that tight a buffer (a shallow bounce confirmed the pattern before the real, deeper low was actually reached) before reversing hard toward TP; 0.5% gives room for that kind of double-dip without redesigning the confirmation window itself
SESSION_MIN_RANGE_PCT = float(os.environ.get("VP_SESSION_MIN_RANGE_PCT", 0.003))  # 0.3% — skip symbols whose 4h range is too tiny to be a meaningful consolidation
SESSION_MAX_THRUST_BARS = int(os.environ.get("VP_SESSION_MAX_THRUST_BARS", 3))  # the sweep and the close-back-inside confirmation can be up to this many bars apart — a short thrust, not strictly the same candle, per the reference chart (2-3 candle burst, not a single bar)
SESSION_BACKTEST_DAYS = int(os.environ.get("VP_SESSION_BACKTEST_DAYS", 30))  # was 60 — Gate enforces a hard "from" floor of ~10000 candles back from now (added without notice ~Feb 2026); for 5m candles that's ~34.7 days, so 30 leaves margin
SESSION_UNIVERSE_SIZE = int(os.environ.get("VP_SESSION_UNIVERSE_SIZE", 50))  # reduced from 100 — user wants the most liquid coins specifically, not a broad tail; already sorted by 24h volume descending, this just cuts deeper into that ranking
SESSION_MIN_SAMPLE = int(os.environ.get("VP_SESSION_MIN_SAMPLE", 8))  # don't rank a symbol's backtest as meaningful with fewer closed sessions than this
SESSION_SIGNAL_HISTORY = 200
SESSION_REFRESH_SEC = int(os.environ.get("VP_SESSION_REFRESH_SEC", 24 * 3600))  # batch backtest job — once a day is plenty, one new day of data per cycle anyway

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

# --- basic runtime settings: scan modes + notifications, exposed through
# the header's settings button. Deliberately NOT the detailed indicator
# knobs (RR, buffer, thresholds, etc.) — those stay env-var-only. Backed
# by a small JSON file so a change made in the UI survives a restart.
SETTINGS_FILE = os.environ.get(
    "VP_SETTINGS_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "vp_poc_settings.json"),
)
SETTINGS_KEYS = ("volume_profile_enabled", "divergence_enabled", "div_invert_signals", "bounce_enabled", "breakout_enabled",
                  "ema_enabled", "ema_invert_signals", "scalp_enabled", "scalp_signals_enabled", "session_enabled", "hourly_stats_enabled", "telegram_enabled",
                  "telegram_alerts_vp", "telegram_alerts_div", "telegram_alerts_ema", "telegram_alerts_hourly", "telegram_alerts_session")


def get_settings():
    return {
        "volume_profile_enabled": VOLUME_PROFILE_ENABLED,
        "divergence_enabled": DIVERGENCE_ENABLED,
        "div_invert_signals": DIV_INVERT_SIGNALS,
        "bounce_enabled": BOUNCE_ENABLED,
        "breakout_enabled": BREAKOUT_ENABLED,
        "ema_enabled": EMA_ENABLED,
        "ema_invert_signals": EMA_INVERT_SIGNALS,
        "scalp_enabled": SCALP_ENABLED,
        "scalp_signals_enabled": SCALP_SIGNALS_ENABLED,
        "session_enabled": SESSION_ENABLED,
        "hourly_stats_enabled": HOURLY_STATS_ENABLED,
        "telegram_enabled": TELEGRAM_ENABLED,
        "telegram_alerts_vp": TELEGRAM_ALERTS_VP,
        "telegram_alerts_div": TELEGRAM_ALERTS_DIV,
        "telegram_alerts_ema": TELEGRAM_ALERTS_EMA,
        "telegram_alerts_hourly": TELEGRAM_ALERTS_HOURLY,
        "telegram_alerts_session": TELEGRAM_ALERTS_SESSION,
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
    }



def apply_settings(updates):
    """Mutates the module-level flags directly — every place that checks
    them (scan_loop, scan_symbol, send_telegram, ...) reads the name at
    call time, not at import time, so this takes effect on the very next
    scan cycle / next alert, no restart needed."""
    global VOLUME_PROFILE_ENABLED, DIVERGENCE_ENABLED, DIV_INVERT_SIGNALS, BOUNCE_ENABLED, BREAKOUT_ENABLED, EMA_ENABLED, EMA_INVERT_SIGNALS, SCALP_ENABLED, SCALP_SIGNALS_ENABLED, SESSION_ENABLED, HOURLY_STATS_ENABLED
    global TELEGRAM_ENABLED, TELEGRAM_ALERTS_VP, TELEGRAM_ALERTS_DIV, TELEGRAM_ALERTS_EMA, TELEGRAM_ALERTS_HOURLY, TELEGRAM_ALERTS_SESSION
    if "volume_profile_enabled" in updates:
        VOLUME_PROFILE_ENABLED = bool(updates["volume_profile_enabled"])
    if "divergence_enabled" in updates:
        DIVERGENCE_ENABLED = bool(updates["divergence_enabled"])
    if "div_invert_signals" in updates:
        DIV_INVERT_SIGNALS = bool(updates["div_invert_signals"])
    if "bounce_enabled" in updates:
        BOUNCE_ENABLED = bool(updates["bounce_enabled"])
    if "breakout_enabled" in updates:
        BREAKOUT_ENABLED = bool(updates["breakout_enabled"])
    if "ema_enabled" in updates:
        EMA_ENABLED = bool(updates["ema_enabled"])
    if "ema_invert_signals" in updates:
        EMA_INVERT_SIGNALS = bool(updates["ema_invert_signals"])
    if "scalp_enabled" in updates:
        SCALP_ENABLED = bool(updates["scalp_enabled"])
    if "scalp_signals_enabled" in updates:
        SCALP_SIGNALS_ENABLED = bool(updates["scalp_signals_enabled"])
    if "session_enabled" in updates:
        SESSION_ENABLED = bool(updates["session_enabled"])
    if "hourly_stats_enabled" in updates:
        HOURLY_STATS_ENABLED = bool(updates["hourly_stats_enabled"])
    if "telegram_enabled" in updates:
        TELEGRAM_ENABLED = bool(updates["telegram_enabled"])
    if "telegram_alerts_vp" in updates:
        TELEGRAM_ALERTS_VP = bool(updates["telegram_alerts_vp"])
    if "telegram_alerts_div" in updates:
        TELEGRAM_ALERTS_DIV = bool(updates["telegram_alerts_div"])
    if "telegram_alerts_ema" in updates:
        TELEGRAM_ALERTS_EMA = bool(updates["telegram_alerts_ema"])
    if "telegram_alerts_session" in updates:
        TELEGRAM_ALERTS_SESSION = bool(updates["telegram_alerts_session"])
    if "telegram_alerts_hourly" in updates:
        TELEGRAM_ALERTS_HOURLY = bool(updates["telegram_alerts_hourly"])


def save_settings():
    try:
        tmp_path = SETTINGS_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(get_settings(), f)
        os.replace(tmp_path, SETTINGS_FILE)
    except Exception as e:
        log_error(f"save_settings: {e}")


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return
    try:
        with open(SETTINGS_FILE) as f:
            saved = json.load(f)
        apply_settings({k: v for k, v in saved.items() if k in SETTINGS_KEYS})
    except Exception as e:
        log_error(f"load_settings: {e}")


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
    # EMA 7/14/28 signal indicator — same "own page" treatment as divergence
    "ema_signals": deque(maxlen=EMA_SIGNAL_HISTORY),
    "ema_last_scan_finished": None,
    "ema_last_scan_duration": None,
    # Скальпинг — pure stats, not a signal source: universe + per-symbol
    # excursion data + the computed recommendation for each, refreshed on
    # its own slow SCALP_REFRESH_SEC cadence, separate from the main loop.
    "scalp_universe": [],
    "scalp_universe_scores": {},
    "scalp_mmr_map": {},
    "scalp_max_leverage_map": {},
    "scalp_data": {},          # symbol -> {interval -> {direction -> target-summary}}
    "scalp_recommendations": {},  # symbol -> best config (or None)
    "scalp_last_build_started": None,
    "scalp_last_build_finished": None,
    "scalp_last_build_duration": None,
    "scalp_symbols_done": 0,
    "scalp_signals": deque(maxlen=SCALP_SIGNAL_HISTORY),
    # Session-open manipulation — backtest results/summary per symbol,
    # plus live signals fired during each day's manipulation window.
    "session_universe": [],
    "session_backtest_results": {},
    "session_backtest_summary": {},
    "session_last_backtest_started": None,
    "session_last_backtest_finished": None,
    "session_last_backtest_duration": None,
    "session_symbols_done": 0,
    "session_signals": deque(maxlen=SESSION_SIGNAL_HISTORY),
    "session_next_open_ts": None,
}
_cooldowns = {}  # (symbol, zone_key) -> last_alert_ts
_cooldowns_lock = threading.Lock()
_div_cooldowns = {}  # symbol -> last_alert_ts
_div_cooldowns_lock = threading.Lock()
_ema_cooldowns = {}  # symbol -> last_alert_ts
_ema_cooldowns_lock = threading.Lock()
_scalp_signal_cooldowns = {}  # (symbol, interval) -> last_signal_ts
_scalp_signal_cooldowns_lock = threading.Lock()
_session_signal_cooldowns = {}  # (symbol, session_open_ts) -> True, once fired
_session_signal_cooldowns_lock = threading.Lock()
_session_signal_cooldowns = {}  # symbol -> last session_open_ts signaled
_session_signal_cooldowns_lock = threading.Lock()


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
                "direction": "LONG" if DIV_INVERT_SIGNALS else "SHORT", "kind": "bearish",
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
                "direction": "SHORT" if DIV_INVERT_SIGNALS else "LONG", "kind": "bullish",
                "p1": p1, "p2": p2,
                "price_p1": lows[p1], "price_p2": lows[p2],
                "rsi_p1": r1, "rsi_p2": r2,
                "time_p1": candles[p1]["time"], "time_p2": candles[p2]["time"],
                "rsi_time_p1": candles[p1]["time"], "rsi_time_p2": candles[p2]["time"],
            }
    return None


# ----------------------------------------------------------------------------
# EMA 7/14/28 signal indicator — ported from a user-supplied Pine Script.
# ----------------------------------------------------------------------------
def compute_ema(values, period):
    """Matches Pine Script's ta.ema exactly: seeds with the first value
    (no SMA warm-up), then applies alpha=2/(period+1) recursively."""
    n = len(values)
    ema = [None] * n
    if n == 0:
        return ema
    alpha = 2 / (period + 1)
    ema[0] = values[0]
    for i in range(1, n):
        ema[i] = alpha * values[i] + (1 - alpha) * ema[i - 1]
    return ema


def _crossover(a, b, i):
    """a crosses above b at bar i (Pine's ta.crossover)."""
    return a[i - 1] <= b[i - 1] and a[i] > b[i]


def _crossunder(a, b, i):
    """a crosses below b at bar i (Pine's ta.crossunder)."""
    return a[i - 1] >= b[i - 1] and a[i] < b[i]


def detect_ema_signal(closes, len7=EMA_LEN_7, len14=EMA_LEN_14, len28=EMA_LEN_28,
                       signal_type=EMA_SIGNAL_TYPE, trend_filter=EMA_TREND_FILTER):
    """Same three signal definitions as the Pine Script's "Тип сигнала"
    input: price/EMA7 cross, EMA7/EMA14 cross, or "combined" (price
    crosses EMA7 while EMA7 is already positioned on the trade's side of
    EMA14) — plus the optional EMA28 trend filter. Only looks at the
    latest bar, mirroring how the indicator plots live on a chart."""
    n = len(closes)
    if signal_type == "disabled" or n < max(len7, len14, len28) + 2:
        return None
    ema7 = compute_ema(closes, len7)
    ema14 = compute_ema(closes, len14)
    ema28 = compute_ema(closes, len28)
    i = n - 1

    cross_buy = _crossover(closes, ema7, i)
    cross_sell = _crossunder(closes, ema7, i)

    if signal_type == "price_ema7":
        buy, sell = cross_buy, cross_sell
    elif signal_type == "ema7_ema14":
        buy, sell = _crossover(ema7, ema14, i), _crossunder(ema7, ema14, i)
    elif signal_type == "combined":
        buy = cross_buy and ema7[i] > ema14[i]
        sell = cross_sell and ema7[i] < ema14[i]
    else:
        buy, sell = False, False

    if trend_filter:
        buy = buy and closes[i] > ema28[i]
        sell = sell and closes[i] < ema28[i]

    if EMA_INVERT_SIGNALS:
        buy, sell = sell, buy  # trade the opposite of whatever the indicator (including its trend filter) says

    if buy:
        return {"direction": "LONG", "ema7": ema7[i], "ema14": ema14[i], "ema28": ema28[i]}
    if sell:
        return {"direction": "SHORT", "ema7": ema7[i], "ema14": ema14[i], "ema28": ema28[i]}
    return None


def session_open_utc_ts(ref_ts):
    """Given any UTC epoch timestamp, returns the UTC epoch timestamp of
    that SAME calendar day's session open (SESSION_OPEN_HOUR_LOCAL,
    SESSION_UTC_OFFSET_HOURS ahead of UTC). Pure arithmetic, no zoneinfo/
    tzdata dependency at all — this was originally DST-aware via
    Europe/Kyiv + zoneinfo, but Termux/Android environments proved
    unreliable for getting a working tzdata install (pip itself was
    broken on the user's device, unrelated to this app). Switched the
    reference to Moscow, which has used a fixed UTC+3 with no DST since
    2014 — "10:00 Moscow" is always exactly 07:00 UTC, so this can be
    plain arithmetic and never depend on a timezone database again. The
    tradeoff: this drifts by 1h from true Kyiv-local time during the EU
    winter half of the year (Kyiv is UTC+2 then) — accepted per direct
    user request rather than fighting the broken tzdata install
    further."""
    dt_utc = datetime.datetime.fromtimestamp(ref_ts, tz=datetime.timezone.utc)
    local_shifted = dt_utc + datetime.timedelta(hours=SESSION_UTC_OFFSET_HOURS)
    open_shifted = local_shifted.replace(hour=SESSION_OPEN_HOUR_LOCAL, minute=0, second=0, microsecond=0)
    open_utc = open_shifted - datetime.timedelta(hours=SESSION_UTC_OFFSET_HOURS)
    return open_utc.timestamp()


def detect_session_manipulation(candles, session_open_ts):
    """Core pattern detector, shared by live scanning and historical
    backtesting. candles must be 5m (or whatever SESSION_RANGE_TF is)
    and cover at least [that UTC day's SESSION_RANGE_START_UTC_HOUR,
    session_open_ts + SESSION_MANIPULATION_WINDOW_MIN]. Returns a dict
    with direction/entry/range/sl/tp, or None if no confirmed
    manipulation happened around this particular session open.
    The consolidation range is the PRIOR (Asian) session, not a fixed
    lookback window — spans from SESSION_RANGE_START_UTC_HOUR (UTC,
    default midnight) up to the session open itself. Since v0.42.0's
    fixed-Moscow-offset session_open_utc_ts(), the open is always
    exactly 07:00 UTC, so this range is now always exactly 7h — it
    used to vary 7-8h under the earlier DST-aware Kyiv version, no
    longer applicable."""
    open_dt = datetime.datetime.fromtimestamp(session_open_ts, tz=datetime.timezone.utc)
    range_start_dt = open_dt.replace(hour=SESSION_RANGE_START_UTC_HOUR, minute=0, second=0, microsecond=0)
    range_start = range_start_dt.timestamp()
    range_duration_sec = session_open_ts - range_start
    range_candles = [c for c in candles if range_start <= c["time"] < session_open_ts]
    expected_bars = range_duration_sec / INTERVAL_SECONDS.get(SESSION_RANGE_TF, 300)
    if expected_bars <= 0 or len(range_candles) < expected_bars * 0.6:  # tolerate some gaps, but not a mostly-missing range
        return None
    range_high = max(c["high"] for c in range_candles)
    range_low = min(c["low"] for c in range_candles)
    if range_low <= 0:
        return None
    range_pct = (range_high - range_low) / range_low
    if range_pct < SESSION_MIN_RANGE_PCT:
        return None  # too flat to be a meaningful consolidation

    window_end = session_open_ts + SESSION_MANIPULATION_WINDOW_MIN * 60
    window_candles = [c for c in candles if session_open_ts <= c["time"] < window_end]

    for i, c in enumerate(window_candles):
        closed_back_inside = range_low <= c["close"] <= range_high
        if not closed_back_inside:
            continue  # this candle didn't reject back into the range on its own close — not a confirmation point, keep looking
        cluster = window_candles[max(0, i - (SESSION_MAX_THRUST_BARS - 1)):i + 1]
        cluster_highs_above = [cc["high"] for cc in cluster if cc["high"] > range_high]
        cluster_lows_below = [cc["low"] for cc in cluster if cc["low"] < range_low]
        if cluster_highs_above and cluster_lows_below:
            continue  # both sides swept within this short cluster — too chaotic to call cleanly, keep looking
        if cluster_highs_above:
            entry = c["close"]
            sweep_extreme = max(cluster_highs_above)
            sl = sweep_extreme * (1 + SESSION_SL_BUFFER_PCT)
            tp = range_low
            return {"direction": "SHORT", "entry": entry, "sl": sl, "tp": tp,
                    "range_high": range_high, "range_low": range_low,
                    "sweep_extreme": sweep_extreme, "confirm_time": c["time"]}
        if cluster_lows_below:
            entry = c["close"]
            sweep_extreme = min(cluster_lows_below)
            sl = sweep_extreme * (1 - SESSION_SL_BUFFER_PCT)
            tp = range_high
            return {"direction": "LONG", "entry": entry, "sl": sl, "tp": tp,
                    "range_high": range_high, "range_low": range_low,
                    "sweep_extreme": sweep_extreme, "confirm_time": c["time"]}
    return None


def track_session_outcome(candles, sig, max_wait_sec=24 * 3600):
    """Walks forward from the signal's confirm_time looking for TP or SL
    touch. If a single candle's range covers both (can't tell from OHLC
    alone which came first), SL is checked first — the conservative
    assumption, consistent with how a real position would behave if
    price is volatile enough to touch both in one bar."""
    future = [c for c in candles if c["time"] >= sig["confirm_time"]]
    for c in future:
        if c["time"] - sig["confirm_time"] > max_wait_sec:
            return "TIMEOUT", None
        if sig["direction"] == "SHORT":
            if c["high"] >= sig["sl"]:
                return "LOSS", c["time"]
            if c["low"] <= sig["tp"]:
                return "WIN", c["time"]
        else:
            if c["low"] <= sig["sl"]:
                return "LOSS", c["time"]
            if c["high"] >= sig["tp"]:
                return "WIN", c["time"]
    return "TIMEOUT", None


def backtest_session_symbol(symbol, days=SESSION_BACKTEST_DAYS):
    """Walks the last `days` calendar days for one symbol, running
    detect_session_manipulation() at each day's own DST-correct session
    open, and tracking the outcome of any signal found. Returns a list
    of per-day results — the aggregate stats (win rate etc.) are
    computed separately so this stays a single-purpose data collector,
    same split as the scalp module's analyze_excursions/summarize."""
    now = time.time()
    fetch_start = now - days * 86400 - 25 * 3600  # generous buffer: covers a full day before the first session's range starts
    candles = get_candles_range(symbol, SESSION_RANGE_TF, fetch_start, now)
    if len(candles) < 50:
        return []

    results = []
    cur = session_open_utc_ts(fetch_start) + 86400  # first full day inside the fetched window
    cutoff = now - SESSION_MANIPULATION_WINDOW_MIN * 60  # need the full manipulation window to have elapsed
    seen_days = 0
    while cur < cutoff and seen_days < days:
        sig = detect_session_manipulation(candles, cur)
        if sig:
            result, exit_time = track_session_outcome(candles, sig)
            results.append({
                "session_open": cur, "direction": sig["direction"],
                "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
                "range_high": sig["range_high"], "range_low": sig["range_low"],
                "result": result, "exit_time": exit_time,
            })
        # re-derive from the calendar date rather than a flat +86400 stride —
        # a fixed-seconds increment would drift by 1h for every day past a
        # DST transition, since the local 10:00 offset from UTC changes but
        # a raw +86400 doesn't know that
        cur = session_open_utc_ts(cur + 86400)
        seen_days += 1
    return results


def summarize_session_backtest(results):
    total = len(results)
    if not total:
        return {"n": 0, "win_rate": None, "wins": 0, "losses": 0, "timeouts": 0}
    wins = sum(1 for r in results if r["result"] == "WIN")
    losses = sum(1 for r in results if r["result"] == "LOSS")
    timeouts = sum(1 for r in results if r["result"] == "TIMEOUT")
    closed = wins + losses
    win_rate = round(wins / closed * 100, 1) if closed else None
    return {"n": total, "win_rate": win_rate, "wins": wins, "losses": losses, "timeouts": timeouts}


def build_session_universe():
    """Liquid-symbol pool, same source as build_scalp_universe (tickers'
    24h volume), capped to SESSION_UNIVERSE_SIZE since backtesting
    SESSION_BACKTEST_DAYS of 5m history per symbol (paginated fetch) is
    the expensive part here — no separate volatility ranking pass, the
    backtest results themselves are the ranking."""
    tickers = get_tickers()
    seen_vol = {}
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
        if name not in seen_vol or vol > seen_vol[name]:
            seen_vol[name] = vol
    ranked = sorted(seen_vol.items(), key=lambda x: -x[1])
    return [s[0] for s in ranked[:SESSION_UNIVERSE_SIZE]]


def scan_symbol_session_live(symbol, session_open_ts):
    """Live counterpart to backtest_session_symbol — only called for
    TODAY's session_open_ts, and only while we're inside the
    manipulation window (checked by the caller). Fires at most once per
    (symbol, session_open_ts): a confirmed manipulation doesn't change
    once found, so re-scanning the same session after a signal exists
    would just rediscover it."""
    if not SESSION_ENABLED:
        return
    with _session_signal_cooldowns_lock:
        if _session_signal_cooldowns.get(symbol) == session_open_ts:
            return
    try:
        range_start_dt = datetime.datetime.fromtimestamp(session_open_ts, tz=datetime.timezone.utc).replace(
            hour=SESSION_RANGE_START_UTC_HOUR, minute=0, second=0, microsecond=0)
        candles = get_candles_range(symbol, SESSION_RANGE_TF, range_start_dt.timestamp(), time.time())
        sig = detect_session_manipulation(candles, session_open_ts)
        if not sig:
            return
        with _session_signal_cooldowns_lock:
            if _session_signal_cooldowns.get(symbol) == session_open_ts:
                return  # another thread found it first this same cycle
            _session_signal_cooldowns[symbol] = session_open_ts
        record = {
            "symbol": symbol, "direction": sig["direction"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
            "range_high": sig["range_high"], "range_low": sig["range_low"],
            "session_open": session_open_ts, "confirm_time": sig["confirm_time"],
            "detected_at": time.time(), "status": "OPEN", "result": None,
            "exit_price": None, "exit_time": None, "app_version": APP_VERSION,
        }
        with state_lock:
            STATE["session_signals"].appendleft(record)
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        send_telegram(
            f"{arrow} {symbol} (открытие сессии — манипуляция)\n"
            f"entry: {sig['entry']:.6g}\n"
            f"SL: {sig['sl']:.6g}  TP: {sig['tp']:.6g}",
            category="session",
        )
    except Exception as e:
        log_error(f"session_live {symbol}: {e}")


def update_session_signal_outcomes():
    now = time.time()
    with state_lock:
        open_signals = [s for s in STATE["session_signals"] if s["status"] == "OPEN"]
    for sig in open_signals:
        try:
            candles = get_candles(sig["symbol"], interval=SESSION_RANGE_TF, limit=300)
            future = [c for c in candles if c["time"] >= sig["confirm_time"]]
            result = None
            exit_price = None
            exit_time = None
            for c in future:
                if sig["direction"] == "SHORT":
                    if c["high"] >= sig["sl"]:
                        result, exit_price, exit_time = "LOSS", sig["sl"], c["time"]
                        break
                    if c["low"] <= sig["tp"]:
                        result, exit_price, exit_time = "WIN", sig["tp"], c["time"]
                        break
                else:
                    if c["low"] <= sig["sl"]:
                        result, exit_price, exit_time = "LOSS", sig["sl"], c["time"]
                        break
                    if c["high"] >= sig["tp"]:
                        result, exit_price, exit_time = "WIN", sig["tp"], c["time"]
                        break
            timed_out = (now - sig["detected_at"]) > 24 * 3600
            with state_lock:
                if result:
                    sig["status"] = "CLOSED"
                    sig["result"] = result
                    sig["exit_price"] = exit_price
                    sig["exit_time"] = exit_time
                elif timed_out:
                    sig["status"] = "CLOSED"
                    sig["result"] = "TIMEOUT"
                    sig["exit_price"] = candles[-1]["close"] if candles else None
                    sig["exit_time"] = candles[-1]["time"] if candles else None
        except Exception as e:
            log_error(f"session_outcome {sig['symbol']}: {e}")


def compute_session_signal_stats():
    with state_lock:
        signals = list(STATE["session_signals"])
    closed = [s for s in signals if s["status"] == "CLOSED" and s["result"] in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = sum(1 for s in closed if s["result"] == "LOSS")
    timeouts = sum(1 for s in signals if s.get("result") == "TIMEOUT")
    open_n = sum(1 for s in signals if s["status"] == "OPEN")
    total_closed = len(closed)
    winrate = round(wins / total_closed * 100, 1) if total_closed else None
    return {"total": len(signals), "wins": wins, "losses": losses, "timeouts": timeouts,
            "open": open_n, "winrate": winrate}


def compute_ema_tp_sl(direction, entry, rr=EMA_RR, tp_pct=EMA_TP_PCT):
    """Same fixed-%-TP-then-derive-SL approach as the divergence signals
    — the source Pine Script only plots BUY/SELL labels, no TP/SL."""
    if direction == "SHORT":
        tp = entry * (1 - tp_pct)
        risk = (entry - tp) / rr
        sl = entry + risk
    else:
        tp = entry * (1 + tp_pct)
        risk = (tp - entry) / rr
        sl = entry - risk
    return sl, tp, risk


# ----------------------------------------------------------------------------
# Scalp volatility statistics — see SCALP_ENABLED comment above for the
# design summary. This is a stats/exploration tool, not a signal source:
# no records get created, no Telegram alerts, nothing "fires". It answers
# "if I'd entered at any point in this coin's history, how often and how
# fast would volatility alone have carried price X% in my favor, and how
# rough would the ride there typically have been" — separately per
# direction and timeframe, which is exactly the raw material needed to
# size a safe leverage and judge whether $7-off-$30 five times a day is
# realistic for a given coin.
# ----------------------------------------------------------------------------
def analyze_excursions(candles, direction, target_pcts, max_bars_ahead, stride=3):
    """Samples every `stride`-th candle as a hypothetical entry (its own
    open as entry price), walks forward up to max_bars_ahead bars, and
    for each target % records how many bars until that favorable move
    was first reached, plus — importantly — the worst adverse move seen
    before that point (not just "did it hit", but "how rough was the
    ride there", which is what a leverage/liquidation safety check
    needs)."""
    n = len(candles)
    results = {pct: {"hit_bars": [], "not_hit": 0} for pct in target_pcts}
    adverse_before_hit = {pct: [] for pct in target_pcts}

    for i in range(0, max(0, n - 1), stride):
        entry = candles[i]["open"]
        if not entry or entry <= 0:
            continue
        end = min(n, i + 1 + max_bars_ahead)
        max_fav = 0.0
        max_adv = 0.0
        hit_this_target = {pct: None for pct in target_pcts}
        remaining = set(target_pcts)
        for j in range(i + 1, end):
            c = candles[j]
            if direction == "LONG":
                fav = (c["high"] - entry) / entry * 100
                adv = (entry - c["low"]) / entry * 100
            else:
                fav = (entry - c["low"]) / entry * 100
                adv = (c["high"] - entry) / entry * 100
            if fav > max_fav:
                max_fav = fav
            if adv > max_adv:
                max_adv = adv
            newly_hit = [pct for pct in remaining if max_fav >= pct]
            for pct in newly_hit:
                hit_this_target[pct] = j - i
                adverse_before_hit[pct].append(max_adv)
                remaining.discard(pct)
            if not remaining:
                break
        for pct in target_pcts:
            if hit_this_target[pct] is not None:
                results[pct]["hit_bars"].append(hit_this_target[pct])
            else:
                results[pct]["not_hit"] += 1
    return results, adverse_before_hit


def _percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    idx = min(int(len(sorted_vals) * p), len(sorted_vals) - 1)
    return sorted_vals[idx]


def summarize_excursions(results, adverse_before_hit, target_pcts):
    out = {}
    for pct in target_pcts:
        hb = sorted(results[pct]["hit_bars"])
        nh = results[pct]["not_hit"]
        total = len(hb) + nh
        hit_rate = round(len(hb) / total * 100, 1) if total else None
        adv = sorted(adverse_before_hit[pct])
        out[str(pct)] = {
            "hit_rate": hit_rate, "n": total,
            "median_bars_to_hit": _percentile(hb, 0.5),
            "p75_adverse_pct": round(_percentile(adv, 0.75), 3) if adv else None,
            "p90_adverse_pct": round(_percentile(adv, 0.90), 3) if adv else None,
        }
    return out


def compute_scalp_liquidation_move_pct(direction, leverage, mmr_pct, taker_fee_pct=SCALP_TAKER_FEE_PCT):
    """% adverse move from entry to isolated-margin liquidation, per
    Gate.io's own formula (Est. Liq. Price = (Entry ± Margin/Amount) /
    [1 ± (MMR + TakerFee)], with Margin/Amount = Entry/leverage for a
    fully-margined isolated position). Returns a positive percentage —
    how far price can move against the position before liquidation.
    A non-negative MMR+fee can only ever SHRINK this buffer relative to
    the naive 1/leverage figure, never enlarge it — that's a hard
    mathematical ceiling, clamped here regardless of what mmr_pct turns
    out to be. This caught a real bug once: a bad MMR value from an
    unverified field parse produced a buffer far above that ceiling,
    which silently passed the safety check upstream. Clamping here
    means any future bad MMR source degrades to "overly conservative",
    never to "unsafely optimistic"."""
    if leverage <= 0:
        return None
    if direction == "LONG":
        liq_price = (1 - 1 / leverage) / (1 - (mmr_pct + taker_fee_pct))
    else:
        liq_price = (1 + 1 / leverage) / (1 + (mmr_pct + taker_fee_pct))
    buffer_pct = abs(1 - liq_price) * 100
    return min(buffer_pct, 100 / leverage)


def compute_scalp_leverage_for_target(target_pct, account_usd=SCALP_ACCOUNT_USD, target_profit_usd=SCALP_TARGET_PROFIT_USD):
    """Leverage needed so that a target_pct favorable move on the full
    account balance yields target_profit_usd (before fees)."""
    if target_pct <= 0:
        return None
    required_notional = target_profit_usd / (target_pct / 100)
    return required_notional / account_usd


def compute_div_tp_sl(direction, entry, rr=DIV_RR, tp_pct=DIV_TP_PCT):
    """TP is a fixed % move from entry (tp_pct) rather than derived from
    the pivot-based invalidation point. SL is then sized backward from
    that TP distance divided by rr, so the RR ratio is preserved — but
    note this means SL no longer corresponds to where the divergence
    pattern itself is actually invalidated (beyond the pivot extreme);
    it's now a purely mechanical fraction of the TP distance. Deliberate
    tradeoff, requested in place of the structural (pivot-based) stop."""
    if direction == "SHORT":
        tp = entry * (1 - tp_pct)
        tp_dist = entry - tp
        risk = tp_dist / rr
        sl = entry + risk
    else:
        tp = entry * (1 + tp_pct)
        tp_dist = tp - entry
        risk = tp_dist / rr
        sl = entry - risk
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
        sl, tp, risk = compute_div_tp_sl(sig["direction"], entry)
        # how much of the anticipated move already happened between the
        # pivot forming and the signal actually firing (confirmation +
        # freshness delay) — positive means price already moved in the
        # favorable direction before we could enter, i.e. "already played
        # out" by the time the alert arrives.
        p2 = sig["price_p2"]
        if sig["direction"] == "SHORT":
            pre_move_pct = (p2 - entry) / p2 * 100 if p2 else 0.0
        else:
            pre_move_pct = (entry - p2) / p2 * 100 if p2 else 0.0
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
            "pre_move_pct": round(pre_move_pct, 4),
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
            f"SL: {sl:.6g}  TP: {tp:.6g}  (RR {DIV_RR:g})",
            category="div",
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
        send_telegram(f"{arrow} {sig['symbol']} divergence {sig['direction']} closed: {result} @ {exit_price:.6g}", category="div")


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


def has_open_ema_signal(symbol, interval):
    with state_lock:
        return any(s["symbol"] == symbol and s.get("interval") == interval and s.get("status") == "OPEN" for s in STATE["ema_signals"])


def scan_symbol_ema(symbol, interval=EMA_INTERVAL):
    if not EMA_ENABLED:
        return
    try:
        candles = get_candles(symbol, interval=interval, limit=EMA_FETCH_LIMIT)
        min_needed = max(EMA_LEN_7, EMA_LEN_14, EMA_LEN_28) + 20
        if len(candles) < min_needed:
            return
        ok, _reason = data_quality_check(candles[-min(len(candles), 100):])
        if not ok:
            return
        closes = [c["close"] for c in candles]
        sig = detect_ema_signal(closes, EMA_LEN_7, EMA_LEN_14, EMA_LEN_28, EMA_SIGNAL_TYPE, EMA_TREND_FILTER)
        if not sig:
            return
        if has_open_ema_signal(symbol, interval):
            return

        now = time.time()
        cooldown_key = (symbol, interval)
        with _ema_cooldowns_lock:
            last_ts = _ema_cooldowns.get(cooldown_key, 0)
            allowed = now - last_ts >= EMA_COOLDOWN_SEC
            if allowed:
                _ema_cooldowns[cooldown_key] = now
        if not allowed:
            return

        entry = candles[-1]["close"]
        sl, tp, risk = compute_ema_tp_sl(sig["direction"], entry)
        record = {
            "symbol": symbol,
            "interval": interval,
            "direction": sig["direction"],
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "risk": risk,
            "ema7": sig["ema7"], "ema14": sig["ema14"], "ema28": sig["ema28"],
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
            STATE["ema_signals"].appendleft(record)
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        send_telegram(
            f"{arrow} {symbol} (EMA {EMA_SIGNAL_TYPE}, {interval})\n"
            f"entry: {entry:.6g}\n"
            f"SL: {sl:.6g}  TP: {tp:.6g}  (RR {EMA_RR:g})",
            category="ema",
        )
    except Exception as e:
        log_error(f"ema {symbol}: {e}")


def close_ema_signal(sig, result, exit_price, exit_candle=None):
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
        send_telegram(f"{arrow} {sig['symbol']} EMA {sig['direction']} closed: {result} @ {exit_price:.6g}", category="ema")


def update_ema_outcomes():
    now = time.time()
    with state_lock:
        active = [
            s for s in STATE["ema_signals"]
            if s.get("status") == "OPEN" or now < s.get("mfe_tracking_until", 0)
        ]
    for sig in active:
        try:
            candles = get_candles(sig["symbol"], interval=sig.get("interval", EMA_INTERVAL), limit=300)
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
                            close_ema_signal(sig, "LOSS", sig["sl"], exit_candle=c)
                        elif c["high"] >= sig["tp"]:
                            close_ema_signal(sig, "WIN", sig["tp"], exit_candle=c)
                    else:
                        if c["high"] >= sig["sl"]:
                            close_ema_signal(sig, "LOSS", sig["sl"], exit_candle=c)
                        elif c["low"] <= sig["tp"]:
                            close_ema_signal(sig, "WIN", sig["tp"], exit_candle=c)

            if sig["status"] == "OPEN" and now - sig["detected_at"] > SIGNAL_TIMEOUT_SEC:
                last_price = candles[-1]["close"] if candles else entry
                close_ema_signal(sig, "TIMEOUT", last_price)
        except Exception as e:
            log_error(f"update_ema_outcomes {sig.get('symbol')}: {e}")


def compute_ema_stats(interval=None):
    with state_lock:
        signals = list(STATE["ema_signals"])
    if interval is not None:
        signals = [s for s in signals if s.get("interval") == interval]
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
    win_set_all = [s for s in signals if s.get("result") == "WIN"]
    loss_set_all = [s for s in signals if s.get("result") == "LOSS"]

    return {
        "open": open_count, "wins": wins, "losses": losses,
        "timeouts": timeouts, "winrate": winrate, "closed_total": total,
        "mfe_r_all": agg("mfe_r", dataset), "mae_r_all": agg("mae_r", dataset),
        "mfe_r_wins": agg("mfe_r", win_set), "mae_r_wins": agg("mae_r", win_set),
        "mfe_r_losses": agg("mfe_r", loss_set), "mae_r_losses": agg("mae_r", loss_set),
        "mfe_r_open": agg("mfe_r", open_set), "mae_r_open": agg("mae_r", open_set),
        "mfe_r_wins_at_close": agg("mfe_r_at_close", win_set), "mae_r_wins_at_close": agg("mae_r_at_close", win_set),
        "mfe_r_losses_at_close": agg("mfe_r_at_close", loss_set), "mae_r_losses_at_close": agg("mae_r_at_close", loss_set),
        "pre_move_pct_all": agg("pre_move_pct", signals),
        "pre_move_pct_wins": agg("pre_move_pct", win_set_all),
        "pre_move_pct_losses": agg("pre_move_pct", loss_set_all),
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
    main scan uses, paginating since the API caps each response and
    rejects combining `limit` with `from`/`to`. Used to build the volume
    profile from actual sub-bar data instead of approximating each
    parent bar's volume as spread evenly across its own high-low range
    — the same "bar magnification" idea as the original indicator, just
    implemented via REST polling instead of Pine's
    request.security_lower_tf. Also used by the session-manipulation
    module's multi-week backtests, a much larger range than this was
    originally exercised at.
    CONFIRMED (not just suspected): Gate enforces a hard floor on how
    far back `from` can be — "Candlestick too long ago. Maximum 10000
    points recently are allowed" — added server-side without notice
    around Feb 2026. This is a floor on the START of the request
    relative to NOW, completely independent of how small the requested
    span is — a real-world test confirmed even a 28-point chunk still
    400s if its `from` is past that floor. (An earlier version of this
    docstring guessed the problem was purely a too-large per-request
    point cap and added the retry-with-smaller-chunk logic below for
    that; that logic doesn't help THIS failure mode at all, but is kept
    as a secondary safety net for genuine over-sized-chunk rejections,
    which may also be real — Gate's own SDK docs disagree with each
    other on that number, 1000 in some places and 2000 in others.)
    Clamps `start_ts` forward to the earliest allowed point up front so
    this doesn't even attempt the doomed request."""
    interval_sec = INTERVAL_SECONDS.get(interval, 60)
    earliest_allowed = time.time() - 9800 * interval_sec  # margin under the confirmed ~10000-candle floor
    chunk_points = 900  # conservative starting point — under both documented figures; shrinks (and stays shrunk) the first time the server rejects it
    seen = {}
    cur = max(int(start_ts), int(earliest_allowed))
    end_ts = int(end_ts)
    while cur < end_ts:
        while True:
            chunk_span = interval_sec * chunk_points
            chunk_end = min(cur + chunk_span, end_ts)
            try:
                r = requests.get(
                    f"{GATE_BASE}/futures/usdt/candlesticks",
                    params={"contract": symbol, "interval": interval, "from": cur, "to": chunk_end},
                    timeout=HTTP_TIMEOUT,
                )
                r.raise_for_status()
                break
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 400 and chunk_points > 50:
                    chunk_points = chunk_points // 2  # server rejected this size — shrink, and keep it shrunk for later chunks too
                    continue
                raise
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


def get_futures_risk_limit_tiers():
    """Public, no-auth endpoint that exposes each contract's own tiered
    maintenance margin rate AND max leverage — used instead of assuming
    one fixed MMR/leverage cap for every coin (altcoins often carry a
    higher MMR and a MUCH lower max leverage than BTC/ETH's lowest
    tier — confirmed by the user: a coin the math said needed 23-47x
    for, the exchange itself only allows 10x on). Field names are
    parsed defensively: if the exchange's exact schema doesn't match
    what's expected here, this returns empty maps and every symbol just
    falls back to the conservative defaults. Parsing successfully to a
    float isn't proof it's the right field, though — a wrong field name
    could still produce a plausible-looking number (this exact bug
    shipped once for MMR: a value that only made sense as roughly -3.2%
    MMR passed through unnoticed). Anything outside a realistic range
    gets discarded, same as if it were missing, for both fields.
    Paginated: without a `contract` filter, Gate's own docs say this
    endpoint defaults to only the top 100 markets — a single
    unpaginated call silently covered a small fraction of the universe
    (confirmed live: ~96/189 symbols had no safe config, almost all
    missing exactly the leverage/MMR data this fetches). Pages through
    with limit/offset until a page comes back empty."""
    all_rows = []
    limit = 100
    offset = 0
    try:
        for _ in range(30):  # safety cap — 30*100 = 3000 markets, far more than any real universe
            r = requests.get(f"{GATE_BASE}/futures/usdt/risk_limit_tiers",
                              params={"limit": limit, "offset": offset}, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            page = r.json()
            if not page:
                break
            all_rows.extend(page)
            offset += limit
    except Exception as e:
        log_error(f"get_futures_risk_limit_tiers: {e}")
        if not all_rows:
            return {}, {}
    data = all_rows
    mmr_out = {}
    lev_out = {}
    for row in data:
        try:
            name = row.get("contract") or row.get("name")
            if not name:
                continue
            mmr = row.get("maintenance_rate")
            if mmr is None:
                mmr = row.get("maintain_rate")
            if mmr is not None:
                mmr = float(mmr)
                if SCALP_MMR_SANITY_MIN <= mmr <= SCALP_MMR_SANITY_MAX:
                    if name not in mmr_out or mmr < mmr_out[name]:
                        mmr_out[name] = mmr
            max_lev = row.get("leverage_max")
            if max_lev is None:
                max_lev = row.get("max_leverage")
            if max_lev is not None:
                max_lev = float(max_lev)
                if SCALP_LEVERAGE_SANITY_MIN <= max_lev <= SCALP_LEVERAGE_SANITY_MAX:
                    # keep the HIGHEST max-leverage seen (the lowest-risk /
                    # smallest-size tier allows the most leverage)
                    if name not in lev_out or max_lev > lev_out[name]:
                        lev_out[name] = max_lev
        except (TypeError, ValueError, AttributeError):
            continue
    return mmr_out, lev_out


def build_scalp_universe():
    """Ranks candidate symbols by average full-range volatility per
    candle — (high-low)/close — on SCALP_RANK_INTERVAL, over the last
    SCALP_RANK_LOOKBACK bars. Starts from the same liquid-symbol pool as
    the main screener (via tickers' 24h volume) so we're not ranking
    illiquid/unlisted-in-practice contracts, then fetches candles for
    each candidate in parallel to compute the actual metric."""
    tickers = get_tickers()
    candidates = []
    seen_vol = {}
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
        if name not in seen_vol or vol > seen_vol[name]:
            seen_vol[name] = vol
    candidates = list(seen_vol.keys())

    def rank_one(symbol):
        try:
            candles = get_candles(symbol, interval=SCALP_RANK_INTERVAL, limit=SCALP_RANK_LOOKBACK)
            if len(candles) < 20:
                return None
            moves = [(c["high"] - c["low"]) / c["close"] * 100 for c in candles if c.get("close")]
            if not moves:
                return None
            return symbol, sum(moves) / len(moves)
        except Exception:
            return None

    scored = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for res in ex.map(rank_one, candidates):
            if res:
                scored.append(res)
    scored.sort(key=lambda x: -x[1])
    return [s[0] for s in scored[:SCALP_UNIVERSE_SIZE]], {s[0]: round(s[1], 4) for s in scored[:SCALP_UNIVERSE_SIZE]}


def scan_symbol_scalp(symbol):
    """Runs the excursion-statistics engine for one symbol across every
    configured timeframe and both directions. Pure data collection —
    returns a dict, doesn't touch STATE or fire anything."""
    out = {}
    for interval in SCALP_INTERVALS:
        try:
            candles = get_candles(symbol, interval=interval, limit=SCALP_FETCH_LIMIT)
            if len(candles) < 30:
                continue
            interval_sec = INTERVAL_SECONDS.get(interval, 300)
            max_bars_ahead = max(5, min(SCALP_MAX_WAIT_SEC // interval_sec, 48))
            interval_out = {}
            for direction in ("LONG", "SHORT"):
                res, adv = analyze_excursions(candles, direction, SCALP_TARGET_PCTS, max_bars_ahead)
                interval_out[direction] = summarize_excursions(res, adv, SCALP_TARGET_PCTS)
            out[interval] = interval_out
        except Exception as e:
            log_error(f"scalp {symbol} {interval}: {e}")
    return out


def recommend_scalp_config(symbol_data, mmr_pct, max_leverage=SCALP_DEFAULT_MAX_LEVERAGE):
    """Given one symbol's full interval/direction/target data, picks the
    single best (interval, direction, target%) combination: the LARGEST
    target that still clears SCALP_MIN_HIT_RATE, needs no more leverage
    than the exchange actually allows for this contract (max_leverage —
    confirmed by the user that this varies a lot by coin, e.g. 10x on
    VELVET_USDT vs 125x on majors; a target the math likes but the
    exchange won't let you execute isn't a real recommendation), and
    where the liquidation buffer at that leverage exceeds the coin's own
    historical p90 adverse move by SCALP_SAFETY_MARGIN. Returns None if
    nothing on this symbol clears all three bars at any
    interval/direction/target — that's a legitimate, informative result
    (this coin isn't a safe, executable candidate for the stated goal),
    not an error."""
    best = None
    for interval, dirs in symbol_data.items():
        interval_sec = INTERVAL_SECONDS.get(interval, 300)
        for direction, summary in dirs.items():
            for pct_str in sorted(summary.keys(), key=lambda x: -float(x)):
                s = summary[pct_str]
                if s["hit_rate"] is None or s["hit_rate"] < SCALP_MIN_HIT_RATE:
                    continue
                if s["p90_adverse_pct"] is None or s["median_bars_to_hit"] is None:
                    continue
                pct = float(pct_str)
                leverage = compute_scalp_leverage_for_target(pct)
                if not leverage or leverage <= 0:
                    continue
                if leverage > max_leverage:
                    continue  # exchange won't allow this leverage on this contract, however good the stats are
                liq_buffer = compute_scalp_liquidation_move_pct(direction, leverage, mmr_pct)
                if liq_buffer is None or liq_buffer < s["p90_adverse_pct"] * SCALP_SAFETY_MARGIN:
                    continue
                time_to_hit_hours = s["median_bars_to_hit"] * interval_sec / 3600
                if time_to_hit_hours <= 0:
                    continue
                trades_per_day_est = round(24 / time_to_hit_hours, 2)
                score = round((s["hit_rate"] / 100) * trades_per_day_est, 4)
                candidate = {
                    "interval": interval, "direction": direction, "target_pct": pct,
                    "hit_rate": s["hit_rate"], "n": s["n"],
                    "median_bars_to_hit": s["median_bars_to_hit"],
                    "time_to_hit_hours": round(time_to_hit_hours, 2),
                    "trades_per_day_est": trades_per_day_est,
                    "leverage": round(leverage, 2),
                    "max_leverage": max_leverage,
                    "liq_buffer_pct": round(liq_buffer, 3),
                    "p90_adverse_pct": s["p90_adverse_pct"],
                    "score": score,
                }
                if best is None or candidate["score"] > best["score"]:
                    best = candidate
                break  # this interval/direction's largest qualifying target — no need to check smaller ones too
    return best


def scan_symbol_scalp_signal(symbol, rec):
    """Fires a live scalp signal for one symbol, given its current
    recommend_scalp_config() output. Entry is the most recently closed
    candle's close on the recommended interval — the same "enter right
    at the new candle" convention EMA/divergence already use for
    candles[-1]. SL sits just beyond the p90 adverse excursion already
    measured by the underlying stats engine (analyze_excursions) — a
    data-driven stop rather than an arbitrary guess, added after
    confirming with the user that "no stop" was never an actual
    requirement, just something carried over from the original
    stats-only module (which only measured target-hit probability, with
    no stop-survival concept at all)."""
    if not SCALP_SIGNALS_ENABLED or not rec:
        return
    interval = rec["interval"]
    try:
        candles = get_candles(symbol, interval=interval, limit=5)
        if len(candles) < 2:
            return
        last = candles[-1]
        entry_time = last["time"]

        cooldown_key = (symbol, interval)
        with _scalp_signal_cooldowns_lock:
            last_ts = _scalp_signal_cooldowns.get(cooldown_key)
            if last_ts == entry_time:
                return  # already signaled off this exact candle
            _scalp_signal_cooldowns[cooldown_key] = entry_time

        with state_lock:
            if any(s["symbol"] == symbol and s["interval"] == interval and s["status"] == "OPEN"
                   for s in STATE["scalp_signals"]):
                return  # one open scalp signal per (symbol, interval) at a time

        entry = last["close"]
        direction = rec["direction"]
        target_pct = rec["target_pct"]
        adverse_pct = rec.get("p90_adverse_pct") or (target_pct * SCALP_SAFETY_MARGIN)  # fallback if somehow missing
        sl_pct = adverse_pct * (1 + SCALP_SL_BUFFER_MULT)
        if direction == "LONG":
            target_price = entry * (1 + target_pct / 100)
            sl_price = entry * (1 - sl_pct / 100)
        else:
            target_price = entry * (1 - target_pct / 100)
            sl_price = entry * (1 + sl_pct / 100)
        interval_sec = INTERVAL_SECONDS.get(interval, 300)
        timeout_sec = max(rec["time_to_hit_hours"] * 3600 * SCALP_SIGNAL_TIMEOUT_MULT, interval_sec * 4)

        record = {
            "symbol": symbol, "interval": interval, "direction": direction,
            "entry": entry, "target_price": target_price, "target_pct": target_pct,
            "sl_price": sl_price, "sl_pct": round(sl_pct, 3),
            "leverage": rec["leverage"], "max_leverage": rec.get("max_leverage"),
            "hit_rate_hist": rec["hit_rate"], "score": rec["score"],
            "time": entry_time, "detected_at": time.time(),
            "timeout_at": time.time() + timeout_sec,
            "status": "OPEN", "result": None,
            "exit_price": None, "exit_time": None,
            "app_version": APP_VERSION,
        }
        with state_lock:
            STATE["scalp_signals"].appendleft(record)
    except Exception as e:
        log_error(f"scalp_signal {symbol}: {e}")


def compute_scalp_signal_stats():
    with state_lock:
        signals = list(STATE["scalp_signals"])
    closed = [s for s in signals if s["status"] == "CLOSED" and s["result"] in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = sum(1 for s in closed if s["result"] == "LOSS")
    timeouts = sum(1 for s in signals if s.get("status") == "CLOSED" and s.get("result") == "TIMEOUT")
    open_n = sum(1 for s in signals if s["status"] == "OPEN")
    total_closed = len(closed)
    win_rate = round(wins / total_closed * 100, 1) if total_closed else None
    return {"total": len(signals), "wins": wins, "losses": losses, "timeouts": timeouts, "open": open_n, "win_rate": win_rate}


def update_scalp_signal_outcomes():
    now = time.time()
    with state_lock:
        open_signals = [s for s in STATE["scalp_signals"] if s["status"] == "OPEN"]
    for sig in open_signals:
        try:
            candles = get_candles(sig["symbol"], interval=sig["interval"], limit=200)
            future = [c for c in candles if c["time"] >= sig["time"]]
            result = None
            exit_price = None
            exit_time = None
            sl_price = sig.get("sl_price")  # older signals created before SL existed won't have this — falls back to WIN/TIMEOUT only, same as before
            for c in future:
                if sl_price is not None:
                    if sig["direction"] == "LONG" and c["low"] <= sl_price:
                        result = "LOSS"
                        exit_price = sl_price
                        exit_time = c["time"]
                        break
                    if sig["direction"] == "SHORT" and c["high"] >= sl_price:
                        result = "LOSS"
                        exit_price = sl_price
                        exit_time = c["time"]
                        break
                if sig["direction"] == "LONG" and c["high"] >= sig["target_price"]:
                    result = "WIN"
                    exit_price = sig["target_price"]
                    exit_time = c["time"]
                    break
                if sig["direction"] == "SHORT" and c["low"] <= sig["target_price"]:
                    result = "WIN"
                    exit_price = sig["target_price"]
                    exit_time = c["time"]
                    break
            with state_lock:
                if result:
                    sig["status"] = "CLOSED"
                    sig["result"] = result
                    sig["exit_price"] = exit_price
                    sig["exit_time"] = exit_time
                elif now >= sig["timeout_at"]:
                    sig["status"] = "CLOSED"
                    sig["result"] = "TIMEOUT"
                    sig["exit_price"] = candles[-1]["close"] if candles else None
                    sig["exit_time"] = candles[-1]["time"] if candles else None
        except Exception as e:
            log_error(f"scalp_outcome {sig['symbol']}: {e}")


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
AUTO_TUNE_PER_CYCLE = int(os.environ.get("VP_AUTO_TUNE_PER_CYCLE", 3))  # was 1, raised so a bigger universe still finishes its first full tuning pass in reasonable time — each tune costs several seconds of CPU on top of the regular scan
AUTO_TUNE_REFRESH_SEC = int(os.environ.get("VP_AUTO_TUNE_REFRESH_SEC", 48 * 3600))  # re-tune a symbol once its override is this old — price behavior drifts
PARAM_GRID_LOOKBACK = [60, 100, 150]
PARAM_GRID_HVN = [3, 6, 9]
PARAM_GRID_RR = [1.5, 2.0, 2.5]              # data showed WIN median MFE ~2.8R, so the old 1.0 floor rarely won and was dropped in favor of testing further out
PARAM_GRID_BUFFER = [0.20, 0.35, 0.50]  # reverted — 0.15 was re-added in v0.37.0 to test whether tight buffers now perform better, but overall Volume winrate got WORSE after that change (45.3% -> 33.3%), not better, so reverting per direct user request

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
                "ema_signals": list(STATE["ema_signals"]),
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
        ema_signals = data.get("ema_signals", [])
        with state_lock:
            STATE["signals"] = deque(signals, maxlen=SIGNAL_HISTORY)
            STATE["div_signals"] = deque(div_signals, maxlen=DIV_SIGNAL_HISTORY)
            STATE["ema_signals"] = deque(ema_signals, maxlen=EMA_SIGNAL_HISTORY)
        print(f"Loaded persisted state: {len(SYMBOL_OVERRIDES)} overrides, {len(signals)} signals, {len(div_signals)} divergence signals, {len(ema_signals)} EMA signals")
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
DIV_STABILITY_PER_CYCLE = int(os.environ.get("VP_DIV_STABILITY_PER_CYCLE", 2))  # was 1, raised alongside MAX_SYMBOLS


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


def send_telegram(text, category=None):
    if not TELEGRAM_ENABLED or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    if category == "vp" and not TELEGRAM_ALERTS_VP:
        return
    if category == "div" and not TELEGRAM_ALERTS_DIV:
        return
    if category == "ema" and not TELEGRAM_ALERTS_EMA:
        return
    if category == "hourly" and not TELEGRAM_ALERTS_HOURLY:
        return
    if category == "session" and not TELEGRAM_ALERTS_SESSION:
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
                    f"HVN zone: {sig['zone']['bottom']:.6g} - {sig['zone']['top']:.6g}",
                    category="vp",
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
        send_telegram(f"{arrow} {sig['symbol']} {sig['direction']} closed: {result} @ {exit_price:.6g}", category="vp")


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


def compute_tuning_stats(reason=None):
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
    before this distinction existed won't have "_at_close" values.

    reason=None aggregates bounce+breakout together (previous behavior);
    reason="bounce"/"breakout" filters to just that reason — bounce and
    breakout get independently auto-tuned RR/buffer per symbol already,
    but that tuning had no visibility into MFE/MAE split by reason, only
    combined-Volume numbers, which isn't enough to tell whether a
    reason's own TP/SL sizing is the actual issue."""
    with state_lock:
        signals = list(STATE["signals"])
    dataset = [s for s in signals if s.get("mfe_price") is not None]
    if reason is not None:
        dataset = [s for s in dataset if s.get("reason") == reason]
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
                if EMA_ENABLED:
                    futs += [ex.submit(scan_symbol_ema, s, interval) for s in universe for interval in EMA_INTERVALS]
                if SCALP_SIGNALS_ENABLED:
                    with state_lock:
                        scalp_recs_snapshot = dict(STATE["scalp_recommendations"])
                    top_recs = sorted(
                        [(sym, rec) for sym, rec in scalp_recs_snapshot.items() if rec],
                        key=lambda x: -x[1]["score"]
                    )[:SCALP_SIGNAL_TOP_N]
                    futs += [ex.submit(scan_symbol_scalp_signal, sym, rec) for sym, rec in top_recs]
                if SESSION_ENABLED:
                    now_ts = time.time()
                    todays_open = session_open_utc_ts(now_ts)
                    if todays_open <= now_ts < todays_open + SESSION_MANIPULATION_WINDOW_MIN * 60:
                        futs += [ex.submit(scan_symbol_session_live, s, todays_open) for s in universe]
                for _ in as_completed(futs):
                    pass
            if VOLUME_PROFILE_ENABLED:
                update_signal_outcomes()
                auto_tune_cycle(universe)
            if DIVERGENCE_ENABLED:
                update_divergence_outcomes()
                div_stability_cycle(universe)
            if EMA_ENABLED:
                update_ema_outcomes()
            if SCALP_SIGNALS_ENABLED:
                update_scalp_signal_outcomes()
            if SESSION_ENABLED:
                update_session_signal_outcomes()
            save_state()
            t1 = time.time()
            with state_lock:
                STATE["last_scan_finished"] = t1
                STATE["last_scan_duration"] = round(t1 - t0, 1)
                STATE["div_last_scan_finished"] = t1
                STATE["div_last_scan_duration"] = round(t1 - t0, 1)
                STATE["ema_last_scan_finished"] = t1
                STATE["ema_last_scan_duration"] = round(t1 - t0, 1)
        except Exception as e:
            log_error(f"scan_loop: {e}\n{traceback.format_exc()}")
        time.sleep(max(5, SCAN_INTERVAL_SEC))


def build_hourly_stats_report():
    vp_s = compute_signal_stats()
    div_s = compute_divergence_stats()
    ema_s = compute_ema_stats()
    scalp_s = compute_scalp_signal_stats()

    def wr(x):
        return f"{x}%" if x is not None else "-"

    br = vp_s.get("by_reason", {}) or {}
    bounce = br.get("bounce", {}) or {}
    breakout = br.get("breakout", {}) or {}
    vp_line = (f"<b>Volume</b>: {wr(vp_s['winrate'])} ({vp_s['wins']}W/{vp_s['losses']}L) · "
               f"открытых {vp_s['open']} · bounce {wr(bounce.get('winrate'))}/breakout {wr(breakout.get('winrate'))}")

    div_tag = " [РЕВЕРС]" if DIV_INVERT_SIGNALS else ""
    div_line = f"<b>Дивергенции</b>{div_tag}: {wr(div_s['winrate'])} ({div_s['wins']}W/{div_s['losses']}L) · открытых {div_s['open']}"

    ema_tag = " [РЕВЕРС]" if EMA_INVERT_SIGNALS else ""
    ema_line = f"<b>EMA</b>{ema_tag}: {wr(ema_s['winrate'])} ({ema_s['wins']}W/{ema_s['losses']}L) · открытых {ema_s['open']}"

    scalp_line = (f"<b>Скальпинг</b>: {wr(scalp_s['win_rate'])} ({scalp_s['wins']}W/{scalp_s['losses']}L/{scalp_s['timeouts']}TIMEOUT) · "
                  f"открытых {scalp_s['open']}") if SCALP_SIGNALS_ENABLED else None

    lines = [f"📊 Часовая статистика (v{APP_VERSION})", vp_line, div_line, ema_line]
    if scalp_line:
        lines.append(scalp_line)
    return "\n".join(lines)


def hourly_stats_loop():
    """Own hourly cadence, independent of every other loop in the app —
    sends a compact win-rate summary across all modes to Telegram."""
    while True:
        try:
            if HOURLY_STATS_ENABLED:
                send_telegram(build_hourly_stats_report(), category="hourly")
        except Exception as e:
            log_error(f"hourly_stats_loop: {e}")
        time.sleep(max(60, HOURLY_STATS_INTERVAL_SEC))


def scalp_loop():
    """Own slow cadence (SCALP_REFRESH_SEC, default 6h) — this is a batch
    stats job, not a live scanner, so it runs on a separate thread from
    the main 45s scan_loop entirely."""
    while True:
        try:
            if not SCALP_ENABLED:
                time.sleep(60)
                continue
            t0 = time.time()
            with state_lock:
                STATE["scalp_last_build_started"] = t0
                STATE["scalp_symbols_done"] = 0

            universe, scores = build_scalp_universe()
            mmr_map, max_leverage_map = get_futures_risk_limit_tiers()
            with state_lock:
                STATE["scalp_universe"] = universe
                STATE["scalp_universe_scores"] = scores
                STATE["scalp_mmr_map"] = mmr_map
                STATE["scalp_max_leverage_map"] = max_leverage_map
                # purge symbols that dropped out of this cycle's universe,
                # rather than letting stale entries linger indefinitely
                STATE["scalp_data"] = {}
                STATE["scalp_recommendations"] = {}

            def process_one(symbol):
                try:
                    data = scan_symbol_scalp(symbol)
                    mmr = mmr_map.get(symbol, SCALP_DEFAULT_MMR_PCT)
                    max_lev = max_leverage_map.get(symbol, SCALP_DEFAULT_MAX_LEVERAGE)
                    rec = recommend_scalp_config(data, mmr, max_lev)
                    with state_lock:
                        STATE["scalp_data"][symbol] = data
                        STATE["scalp_recommendations"][symbol] = rec
                        STATE["scalp_symbols_done"] += 1
                except Exception as e:
                    log_error(f"scalp process_one {symbol}: {e}")

            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futs = [ex.submit(process_one, s) for s in universe]
                for _ in as_completed(futs):
                    pass

            t1 = time.time()
            with state_lock:
                STATE["scalp_last_build_finished"] = t1
                STATE["scalp_last_build_duration"] = round(t1 - t0, 1)
        except Exception as e:
            log_error(f"scalp_loop: {e}")
        time.sleep(max(60, SCALP_REFRESH_SEC))


def session_loop():
    """Own daily-ish cadence — batch-backtests the whole universe for the
    session-open manipulation pattern, one day of history at a time in
    steady state. Separate thread from both the fast scan_loop and the
    slower scalp_loop."""
    while True:
        try:
            if not SESSION_ENABLED:
                time.sleep(60)
                continue
            t0 = time.time()
            with state_lock:
                STATE["session_last_backtest_started"] = t0
                STATE["session_symbols_done"] = 0

            universe = build_session_universe()
            with state_lock:
                STATE["session_universe"] = universe
                # purge symbols that dropped out of this cycle's universe
                STATE["session_backtest_results"] = {}
                STATE["session_backtest_summary"] = {}

            def process_one(symbol):
                try:
                    results = backtest_session_symbol(symbol)
                    summary = summarize_session_backtest(results)
                    with state_lock:
                        STATE["session_backtest_results"][symbol] = results
                        STATE["session_backtest_summary"][symbol] = summary
                        STATE["session_symbols_done"] += 1
                except Exception as e:
                    log_error(f"session process_one {symbol}: {e}")

            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futs = [ex.submit(process_one, s) for s in universe]
                for _ in as_completed(futs):
                    pass

            t1 = time.time()
            with state_lock:
                STATE["session_last_backtest_finished"] = t1
                STATE["session_last_backtest_duration"] = round(t1 - t0, 1)
        except Exception as e:
            log_error(f"session_loop: {e}")
        time.sleep(max(60, SESSION_REFRESH_SEC))


def session_live_loop():
    """Handles the daily live-signal window: sleeps until shortly before
    the next session open, then polls the backtested universe (ranked by
    win rate) during the SESSION_MANIPULATION_WINDOW_MIN window looking
    for a live manipulation. Separate from session_loop's slow backtest
    refresh entirely — this one wakes up precisely once a day."""
    while True:
        try:
            if not SESSION_ENABLED:
                time.sleep(60)
                continue
            now = time.time()
            next_open = session_open_utc_ts(now)
            if next_open <= now:
                next_open = session_open_utc_ts(now + 86400)
            with state_lock:
                STATE["session_next_open_ts"] = next_open

            # sleep in bounded chunks toward this SAME fixed target — do
            # NOT recompute next_open mid-wait, or sleeping past it would
            # make the recompute see "today's open is in the past" and
            # jump straight to tomorrow, skipping today's window entirely
            while True:
                remaining = next_open - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 1800))

            with state_lock:
                summaries = dict(STATE["session_backtest_summary"])
                universe = list(STATE["session_universe"]) or list(summaries.keys())
            candidates = [s for s in universe
                          if summaries.get(s, {}).get("n", 0) >= SESSION_MIN_SAMPLE
                          and (summaries.get(s, {}).get("win_rate") or 0) >= 50]
            window_end = next_open + SESSION_MANIPULATION_WINDOW_MIN * 60
            while time.time() < window_end:
                with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                    futs = [ex.submit(scan_symbol_session_live, s, next_open) for s in candidates]
                    for _ in as_completed(futs):
                        pass
                time.sleep(60)
        except Exception as e:
            log_error(f"session_live_loop: {e}")
            time.sleep(60)


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------
@app.route("/api/overview")
def api_overview():
    """Compact win-rate summary across all four modes, for the persistent
    header — one call instead of hitting four separate endpoints on
    every poll regardless of which tab is open."""
    vp = compute_signal_stats()
    div = compute_divergence_stats()
    ema = compute_ema_stats()
    scalp = compute_scalp_signal_stats()
    session = compute_session_signal_stats()
    return jsonify({
        "volume": {"winrate": vp["winrate"], "wins": vp["wins"], "losses": vp["losses"], "open": vp["open"],
                    "enabled": VOLUME_PROFILE_ENABLED},
        "divergence": {"winrate": div["winrate"], "wins": div["wins"], "losses": div["losses"], "open": div["open"],
                        "enabled": DIVERGENCE_ENABLED, "invert": DIV_INVERT_SIGNALS},
        "ema": {"winrate": ema["winrate"], "wins": ema["wins"], "losses": ema["losses"], "open": ema["open"],
                 "enabled": EMA_ENABLED, "invert": EMA_INVERT_SIGNALS},
        "scalp": {"winrate": scalp["win_rate"], "wins": scalp["wins"], "losses": scalp["losses"], "timeouts": scalp["timeouts"], "open": scalp["open"],
                   "enabled": SCALP_SIGNALS_ENABLED},
        "session": {"winrate": session["winrate"], "wins": session["wins"], "losses": session["losses"], "open": session["open"],
                     "enabled": SESSION_ENABLED},
    })


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
    result["by_reason"] = {
        "bounce": compute_tuning_stats(reason="bounce"),
        "breakout": compute_tuning_stats(reason="breakout"),
    }
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
                "rr": DIV_RR, "tp_pct": DIV_TP_PCT, "rsi_period": DIV_RSI_PERIOD,
                "pivot_left": DIV_PIVOT_LEFT, "pivot_right": DIV_PIVOT_RIGHT, "invert_signals": DIV_INVERT_SIGNALS,
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


@app.route("/api/ema/status")
def api_ema_status():
    stats = compute_ema_stats()
    by_interval = {interval: compute_ema_stats(interval) for interval in EMA_INTERVALS}
    with state_lock:
        return jsonify({
            "version": APP_VERSION,
            "enabled": EMA_ENABLED,
            "interval": EMA_INTERVAL,
            "intervals": EMA_INTERVALS,
            "last_scan_finished": STATE["ema_last_scan_finished"],
            "last_scan_duration": STATE["ema_last_scan_duration"],
            "stats": stats,
            "stats_by_interval": by_interval,
            "config": {
                "rr": EMA_RR, "tp_pct": EMA_TP_PCT,
                "len7": EMA_LEN_7, "len14": EMA_LEN_14, "len28": EMA_LEN_28,
                "signal_type": EMA_SIGNAL_TYPE, "trend_filter": EMA_TREND_FILTER, "invert_signals": EMA_INVERT_SIGNALS,
                "cooldown": EMA_COOLDOWN_SEC,
            },
        })


@app.route("/api/ema/signals")
def api_ema_signals():
    with state_lock:
        return jsonify(list(STATE["ema_signals"]))


@app.route("/api/ema/chart/<symbol>")
def api_ema_chart(symbol):
    try:
        interval = request.args.get("interval", EMA_INTERVAL)
        candles = get_candles(symbol, interval=interval, limit=EMA_FETCH_LIMIT)
        closes = [c["close"] for c in candles]
        ema7 = compute_ema(closes, EMA_LEN_7)
        ema14 = compute_ema(closes, EMA_LEN_14)
        ema28 = compute_ema(closes, EMA_LEN_28)
        return jsonify({"symbol": symbol, "interval": interval, "candles": candles,
                         "ema7": ema7, "ema14": ema14, "ema28": ema28})
    except Exception as e:
        log_error(f"api_ema_chart {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/scalp/status")
def api_scalp_status():
    with state_lock:
        universe = list(STATE["scalp_universe"])
        scores = dict(STATE["scalp_universe_scores"])
        mmr_map = dict(STATE["scalp_mmr_map"])
        max_lev_map = dict(STATE["scalp_max_leverage_map"])
        recs = dict(STATE["scalp_recommendations"])
        last_build_finished = STATE["scalp_last_build_finished"]
        last_build_duration = STATE["scalp_last_build_duration"]
        symbols_done = STATE["scalp_symbols_done"]
    ranked = []
    for symbol, rec in recs.items():
        if not rec:
            continue
        row = dict(rec)
        row["symbol"] = symbol
        row["volatility_score"] = scores.get(symbol)
        row["mmr_pct"] = mmr_map.get(symbol, SCALP_DEFAULT_MMR_PCT)
        row["mmr_verified"] = symbol in mmr_map
        row["leverage_verified"] = symbol in max_lev_map
        ranked.append(row)
    ranked.sort(key=lambda r: -r["score"])
    no_safe_config = sum(1 for r in recs.values() if r is None)
    return jsonify({
        "enabled": SCALP_ENABLED,
        "universe_size": len(universe),
        "symbols_done": symbols_done,
        "last_build_finished": last_build_finished,
        "last_build_duration": last_build_duration,
        "no_safe_config_count": no_safe_config,
        "config": {
            "account_usd": SCALP_ACCOUNT_USD, "target_profit_usd": SCALP_TARGET_PROFIT_USD,
            "intervals": SCALP_INTERVALS, "target_pcts": SCALP_TARGET_PCTS,
            "safety_margin": SCALP_SAFETY_MARGIN, "min_hit_rate": SCALP_MIN_HIT_RATE,
            "taker_fee_pct": SCALP_TAKER_FEE_PCT, "default_mmr_pct": SCALP_DEFAULT_MMR_PCT,
            "default_max_leverage": SCALP_DEFAULT_MAX_LEVERAGE,
            "signal_top_n": SCALP_SIGNAL_TOP_N,
        },
        "top": ranked,
        "signals_stats": compute_scalp_signal_stats(),
    })


@app.route("/api/scalp/signals")
def api_scalp_signals():
    with state_lock:
        return jsonify(list(STATE["scalp_signals"]))


@app.route("/api/scalp/symbol/<symbol>")
def api_scalp_symbol(symbol):
    with state_lock:
        data = STATE["scalp_data"].get(symbol)
        rec = STATE["scalp_recommendations"].get(symbol)
        score = STATE["scalp_universe_scores"].get(symbol)
        mmr_map = dict(STATE["scalp_mmr_map"])
        max_lev_map = dict(STATE["scalp_max_leverage_map"])
    if data is None:
        return jsonify({"error": "no data for this symbol yet"}), 404
    return jsonify({
        "symbol": symbol, "volatility_score": score,
        "mmr_pct": mmr_map.get(symbol, SCALP_DEFAULT_MMR_PCT),
        "mmr_verified": symbol in mmr_map,
        "max_leverage": max_lev_map.get(symbol, SCALP_DEFAULT_MAX_LEVERAGE),
        "leverage_verified": symbol in max_lev_map,
        "recommendation": rec, "data": data,
    })


@app.route("/api/reset/scalp", methods=["POST"])
def api_reset_scalp():
    try:
        with state_lock:
            STATE["scalp_universe"] = []
            STATE["scalp_universe_scores"] = {}
            STATE["scalp_mmr_map"] = {}
            STATE["scalp_max_leverage_map"] = {}
            STATE["scalp_data"] = {}
            STATE["scalp_recommendations"] = {}
            STATE["scalp_last_build_started"] = None
            STATE["scalp_last_build_finished"] = None
            STATE["scalp_last_build_duration"] = None
            STATE["scalp_symbols_done"] = 0
            STATE["scalp_signals"].clear()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_scalp: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/session/status")
def api_session_status():
    with state_lock:
        universe = list(STATE["session_universe"])
        summaries = dict(STATE["session_backtest_summary"])
        last_backtest_finished = STATE["session_last_backtest_finished"]
        last_backtest_duration = STATE["session_last_backtest_duration"]
        symbols_done = STATE["session_symbols_done"]
        next_open_ts = STATE["session_next_open_ts"]
    ranked = []
    zero_manipulation_count = 0
    not_yet_processed_count = 0
    for symbol in universe:
        s = summaries.get(symbol)
        if s is None:
            not_yet_processed_count += 1
            continue
        if not s.get("n"):
            zero_manipulation_count += 1  # in the universe (passed the liquidity filter), backtested, just never showed a qualifying manipulation — NOT excluded for being illiquid
            continue
        row = dict(s)
        row["symbol"] = symbol
        row["meets_min_sample"] = s["n"] >= SESSION_MIN_SAMPLE
        ranked.append(row)
    ranked.sort(key=lambda r: (-1 if r["meets_min_sample"] else 0, r["win_rate"] or 0, r["n"]), reverse=True)
    watch_symbols = {}
    for sym in ("BTC_USDT", "ETH_USDT"):
        in_universe = sym in universe
        s = summaries.get(sym)
        watch_symbols[sym] = {
            "in_universe": in_universe,
            "n": s.get("n") if s else None,
            "status": ("not_in_universe" if not in_universe else
                       "not_yet_processed" if s is None else
                       "zero_manipulations_found" if not s.get("n") else "ranked"),
        }
    return jsonify({
        "enabled": SESSION_ENABLED,
        "universe_size": len(universe),
        "symbols_done": symbols_done,
        "zero_manipulation_count": zero_manipulation_count,
        "not_yet_processed_count": not_yet_processed_count,
        "watch_symbols": watch_symbols,
        "last_backtest_finished": last_backtest_finished,
        "last_backtest_duration": last_backtest_duration,
        "next_open_ts": next_open_ts,
        "signals_stats": compute_session_signal_stats(),
        "config": {
            "utc_offset_hours": SESSION_UTC_OFFSET_HOURS, "open_hour_local": SESSION_OPEN_HOUR_LOCAL,
            "range_tf": SESSION_RANGE_TF, "range_start_utc_hour": SESSION_RANGE_START_UTC_HOUR,
            "manipulation_window_min": SESSION_MANIPULATION_WINDOW_MIN,
            "min_sample": SESSION_MIN_SAMPLE, "backtest_days": SESSION_BACKTEST_DAYS,
        },
        "top": ranked,
    })


@app.route("/api/session/signals")
def api_session_signals():
    with state_lock:
        return jsonify(list(STATE["session_signals"]))


@app.route("/api/session/symbol/<symbol>")
def api_session_symbol(symbol):
    with state_lock:
        results = STATE["session_backtest_results"].get(symbol)
        summary = STATE["session_backtest_summary"].get(symbol)
    if results is None:
        return jsonify({"error": "no data for this symbol yet"}), 404
    return jsonify({"symbol": symbol, "summary": summary, "results": results})


@app.route("/api/session/chart/<symbol>")
def api_session_chart(symbol):
    """Re-derives the manipulation for one specific session open by
    re-running detect_session_manipulation() on freshly fetched candles
    — works identically for a past backtest day or a live signal, since
    both are just (symbol, session_open) and the detection is fully
    deterministic from the candle data alone, no need to look anything
    up from stored records."""
    try:
        session_open = float(request.args.get("session_open"))
        range_start_dt = datetime.datetime.fromtimestamp(session_open, tz=datetime.timezone.utc).replace(
            hour=SESSION_RANGE_START_UTC_HOUR, minute=0, second=0, microsecond=0)
        fetch_start = range_start_dt.timestamp() - 2 * 3600
        fetch_end = session_open + SESSION_MANIPULATION_WINDOW_MIN * 60 + 8 * 3600
        candles = get_candles_range(symbol, SESSION_RANGE_TF, fetch_start, fetch_end)
        sig = detect_session_manipulation(candles, session_open)
        result = None
        exit_time = None
        exit_price = None
        if sig:
            result, exit_time = track_session_outcome(candles, sig)
            if result == "WIN":
                exit_price = sig["tp"]
            elif result == "LOSS":
                exit_price = sig["sl"]
        return jsonify({
            "symbol": symbol, "candles": candles, "session_open": session_open,
            "signal": sig, "result": result, "exit_time": exit_time, "exit_price": exit_price,
        })
    except Exception as e:
        log_error(f"api_session_chart {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset/session", methods=["POST"])
def api_reset_session():
    try:
        with state_lock:
            STATE["session_universe"] = []
            STATE["session_backtest_results"] = {}
            STATE["session_backtest_summary"] = {}
            STATE["session_last_backtest_started"] = None
            STATE["session_last_backtest_finished"] = None
            STATE["session_last_backtest_duration"] = None
            STATE["session_symbols_done"] = 0
            STATE["session_signals"].clear()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_session: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/reset/ema", methods=["POST"])
def api_reset_ema():
    try:
        with state_lock:
            STATE["ema_signals"].clear()
        with _ema_cooldowns_lock:
            _ema_cooldowns.clear()
        save_state()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_ema: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(get_settings())


@app.route("/api/settings", methods=["POST"])
def api_post_settings():
    try:
        body = request.get_json(force=True, silent=True) or {}
        updates = {k: v for k, v in body.items() if k in SETTINGS_KEYS}
        apply_settings(updates)
        save_settings()
        return jsonify({"ok": True, "settings": get_settings()})
    except Exception as e:
        log_error(f"api_post_settings: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/reset/volume", methods=["POST"])
def api_reset_volume():
    """Wipe only the volume-profile side: per-symbol tuning overrides,
    signal history (win-rate/MFE/MAE stats), cooldowns, and the
    watchlist. Leaves divergence data untouched."""
    try:
        with state_lock:
            SYMBOL_OVERRIDES.clear()
            STATE["signals"].clear()
            STATE["watchlist"].clear()
            STATE["excluded_low_quality"] = 0
            STATE["filtered_by_trend"] = 0
            STATE["filtered_by_volume"] = 0
            STATE["filtered_by_oi"] = 0
            STATE["errors"].clear()
        with _cooldowns_lock:
            _cooldowns.clear()
        global _auto_tune_cursor
        _auto_tune_cursor = 0
        save_state()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_volume: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/reset/divergence", methods=["POST"])
def api_reset_divergence():
    """Wipe only the divergence side: signal history, cooldowns, and the
    pivot-stability diagnostic. Leaves volume-profile data untouched."""
    try:
        with state_lock:
            STATE["div_signals"].clear()
            STATE["div_pivot_stability"] = {str(r): {"agree": 0, "disagree": 0, "gain_sum": 0.0, "gain_count": 0} for r in DIV_SHADOW_RIGHTS}
        with _div_cooldowns_lock:
            _div_cooldowns.clear()
        save_state()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_divergence: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Wipe everything — both volume-profile and divergence state. Kept
    for backward compatibility; the header now has two separate buttons
    that call the scoped endpoints above instead."""
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
  #resetVolumeBtn, #resetDivBtn, #resetEmaBtn, #resetScalpBtn, #resetSessionBtn { background:#3a1e22; border:none; color:#ff9b9b; padding:6px 12px; border-radius:8px; font-size:12px; white-space:nowrap; }
  #settingsBtn { background:#1e2a3f; border:none; color:#9cc4ff; padding:6px 12px; border-radius:8px; font-size:12px; white-space:nowrap; }
  #settingsModal { position:fixed; inset:0; background:#05070c; display:none; z-index:999; }
  #settingsModal.open { display:flex; flex-direction:column; }
  #settingsModalHeader { padding:12px; display:flex; justify-content:space-between; align-items:center; }
  #settingsModalHeader h2 { font-size:15px; margin:0; }
  #settingsCloseBtn { background:#1e2a3f; border:none; color:#fff; padding:6px 12px; border-radius:8px; font-size:13px; }
  #settingsBody { padding:4px 16px 16px; overflow-y:auto; }
  .settingsGroup { margin-top:18px; border:1px solid #1c2433; border-radius:12px; overflow:hidden; }
  .settingsGroup:first-child { margin-top:4px; }
  .settingsGroupTitle { padding:10px 14px; font-size:11px; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:#6b7688; background:#0d1220; border-bottom:1px solid #1c2433; }
  .settingsGroup .settingRow { padding:14px; }
  .settingsGroup .settingRow:last-child { border-bottom:none; }
  .settingRow { display:flex; justify-content:space-between; align-items:center; padding:14px 0; border-bottom:1px solid #1c2433; }
  .settingRow .label { font-size:14px; }
  .settingRow .sub { font-size:11px; color:#8b98ab; margin-top:2px; }
  .switch { position:relative; display:inline-block; width:44px; height:24px; flex-shrink:0; }
  .switch input { opacity:0; width:0; height:0; }
  .switchSlider { position:absolute; cursor:pointer; inset:0; background:#3a4356; border-radius:24px; transition:.15s; }
  .switchSlider:before { position:absolute; content:""; height:18px; width:18px; left:3px; bottom:3px; background:#fff; border-radius:50%; transition:.15s; }
  input:checked + .switchSlider { background:#3ddc97; }
  input:checked + .switchSlider:before { transform:translateX(20px); }
  input:disabled + .switchSlider { opacity:.4; }
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
  #emaModal { position:fixed; inset:0; background:#05070c; display:none; z-index:999; }
  #emaModal.open { display:flex; flex-direction:column; }
  #emaModalHeader { padding:12px; display:flex; justify-content:space-between; align-items:flex-start; }
  #emaModalHeader h2 { font-size:15px; margin:0; }
  #emaCloseBtn { background:#1e2a3f; border:none; color:#fff; padding:6px 12px; border-radius:8px; font-size:13px; }
  #emaChartWrap { flex:1; overflow:hidden; padding:0 8px 8px; }
  #sessionModal { position:fixed; inset:0; background:#05070c; display:none; z-index:999; }
  #sessionModal.open { display:flex; flex-direction:column; }
  #sessionModalHeader { padding:12px; display:flex; justify-content:space-between; align-items:flex-start; }
  #sessionModalHeader h2 { font-size:15px; margin:0; }
  #sessionCloseBtn { background:#1e2a3f; border:none; color:#fff; padding:6px 12px; border-radius:8px; font-size:13px; }
  #sessionChartWrap { flex:1; overflow:hidden; padding:0 8px 8px; }
  .dim { color:#8b98ab; }
  .empty { padding:30px 14px; text-align:center; color:#6b7688; font-size:13px; }
</style>
</head>
<body>
<header>
  <div id="headerTop">
    <h1>VP-POC Screener</h1>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <button id="settingsBtn">⚙️ Настройки</button>
      <button id="resetVolumeBtn">Очистить объём</button>
      <button id="resetDivBtn">Очистить дивер</button>
      <button id="resetEmaBtn">Очистить индикатор</button>
      <button id="resetScalpBtn">Очистить скальпинг</button>
      <button id="resetSessionBtn">Очистить сессию</button>
    </div>
  </div>
  <div id="status">загрузка...</div>
  <div id="overview" class="dim" style="margin-top:2px;font-size:12px;"></div>
</header>
<div class="tabs">
  <div class="tab active" data-tab="signals">Volume</div>
  <div class="tab" data-tab="divergence">Дивергенции</div>
  <div class="tab" data-tab="ema">EMA</div>
  <div class="tab" data-tab="scalp">Скальпинг</div>
  <div class="tab" data-tab="session">Сессия</div>
</div>
<div class="panel">
  <div id="tuningPanel" style="display:none;padding:10px 4px;font-size:13px;"></div>
  <table id="signalsTable" style="display:table">
    <thead><tr><th>Symbol</th><th>Dir</th><th>Reason</th><th>Entry</th><th>SL</th><th>TP</th><th>MFE(R)</th><th>MAE(R)</th><th>Status</th><th>Time</th></tr></thead>
    <tbody></tbody>
  </table>
  <div id="divStatsPanel" style="display:none;padding:10px 4px;font-size:13px;"></div>
  <table id="divTable" style="display:none">
    <thead><tr><th>Symbol</th><th>Dir</th><th>Kind</th><th>Entry</th><th>SL</th><th>TP</th><th>MFE(R)</th><th>MAE(R)</th><th>Status</th><th>Time</th></tr></thead>
    <tbody></tbody>
  </table>
  <div id="emaStatsPanel" style="display:none;padding:10px 4px;font-size:13px;"></div>
  <table id="emaTable" style="display:none">
    <thead><tr><th>Symbol</th><th>Dir</th><th>TF</th><th>Entry</th><th>SL</th><th>TP</th><th>MFE(R)</th><th>MAE(R)</th><th>Status</th><th>Time</th></tr></thead>
    <tbody></tbody>
  </table>
  <div id="scalpPanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
  <div id="sessionPanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
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

<div id="emaModal">
  <div id="emaModalHeader">
    <div>
      <h2 id="emaModalTitle">-</h2>
      <div id="emaModalParams" class="dim" style="font-size:11px;margin-top:2px;"></div>
    </div>
    <button id="emaCloseBtn">Закрыть</button>
  </div>
  <div id="emaChartWrap"><canvas id="emaChartCanvas"></canvas></div>
</div>

<div id="sessionModal">
  <div id="sessionModalHeader">
    <div>
      <h2 id="sessionModalTitle">-</h2>
      <div id="sessionModalParams" class="dim" style="font-size:11px;margin-top:2px;"></div>
    </div>
    <button id="sessionCloseBtn">Закрыть</button>
  </div>
  <div id="sessionChartWrap"><canvas id="sessionChartCanvas"></canvas></div>
</div>

<div id="settingsModal">
  <div id="settingsModalHeader">
    <h2>Настройки</h2>
    <button id="settingsCloseBtn">Закрыть</button>
  </div>
  <div id="settingsBody">
    <div class="settingsGroup">
      <div class="settingsGroupTitle">Volume Profile</div>
      <div class="settingRow">
        <div>
          <div class="label">Volume Profile сканер</div>
          <div class="sub">зоны, bounce/breakout сигналы, watchlist, автотюнинг</div>
        </div>
        <label class="switch"><input type="checkbox" id="setVolumeProfile"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Bounce сигналы</div>
          <div class="sub">отбой от уровня</div>
        </div>
        <label class="switch"><input type="checkbox" id="setBounce"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Breakout сигналы</div>
          <div class="sub">пробой после консолидации</div>
        </div>
        <label class="switch"><input type="checkbox" id="setBreakout"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="settingsGroup">
      <div class="settingsGroupTitle">Дивергенции</div>
      <div class="settingRow">
        <div>
          <div class="label">RSI-дивергенции</div>
          <div class="sub">отдельный скан на часовом ТФ</div>
        </div>
        <label class="switch"><input type="checkbox" id="setDivergence"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Реверс сигналов</div>
          <div class="sub">торговать в обратную сторону от того, что говорит дивергенция</div>
        </div>
        <label class="switch"><input type="checkbox" id="setDivInvert"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="settingsGroup">
      <div class="settingsGroupTitle">EMA</div>
      <div class="settingRow">
        <div>
          <div class="label">EMA 7/14/28</div>
          <div class="sub">пересечения, свой скан, вкладка "EMA"</div>
        </div>
        <label class="switch"><input type="checkbox" id="setEma"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Реверс сигналов</div>
          <div class="sub">торговать в обратную сторону от того, что говорит индикатор</div>
        </div>
        <label class="switch"><input type="checkbox" id="setEmaInvert"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="settingsGroup">
      <div class="settingsGroupTitle">Скальпинг</div>
      <div class="settingRow">
        <div>
          <div class="label">Скальпинг</div>
          <div class="sub">фоновый сбор статистики волатильности, раз в несколько часов</div>
        </div>
        <label class="switch"><input type="checkbox" id="setScalp"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Живые сигналы</div>
          <div class="sub">топ монет по score, вход на закрытии свечи, TP/SL из статистики</div>
        </div>
        <label class="switch"><input type="checkbox" id="setScalpSignals"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="settingsGroup">
      <div class="settingsGroupTitle">Сессия</div>
      <div class="settingRow">
        <div>
          <div class="label">Манипуляция на открытии</div>
          <div class="sub">бэктест раз в сутки + живой скан в окне открытия Лондона</div>
        </div>
        <label class="switch"><input type="checkbox" id="setSession"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="settingsGroup">
      <div class="settingsGroupTitle">Telegram</div>
      <div class="settingRow">
        <div>
          <div class="label">Уведомления в Telegram</div>
          <div class="sub" id="setTelegramSub">проверка...</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegram"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Алерты Volume Profile</div>
          <div class="sub">bounce/breakout сигналы и их закрытие</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegramVp"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Алерты дивергенций</div>
          <div class="sub">сигналы RSI-дивергенций и их закрытие</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegramDiv"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Алерты EMA</div>
          <div class="sub">EMA-сигналы и их закрытие</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegramEma"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Алерты сессии</div>
          <div class="sub">живые сигналы манипуляции на открытии</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegramSession"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Часовая статистика</div>
          <div class="sub">сводка винрейта по всем режимам, раз в час</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegramHourly"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="dim" style="font-size:12px;margin-top:16px;">Изменения применяются сразу, без перезапуска, и сохраняются на диск. Здесь только общие переключатели — детальные параметры (RR, буферы, пороги фильтров) настраиваются через переменные окружения при запуске.</div>
  </div>
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
    document.getElementById('tuningPanel').style.display = activeTab === 'signals' ? 'block' : 'none';
    document.getElementById('divTable').style.display = activeTab === 'divergence' ? 'table' : 'none';
    document.getElementById('divStatsPanel').style.display = activeTab === 'divergence' ? 'block' : 'none';
    document.getElementById('emaTable').style.display = activeTab === 'ema' ? 'table' : 'none';
    document.getElementById('emaStatsPanel').style.display = activeTab === 'ema' ? 'block' : 'none';
    document.getElementById('scalpPanel').style.display = activeTab === 'scalp' ? 'block' : 'none';
    document.getElementById('sessionPanel').style.display = activeTab === 'session' ? 'block' : 'none';
    if (activeTab === 'signals') refreshTuning();
    if (activeTab === 'divergence') refreshDivergence();
    if (activeTab === 'ema') refreshEma();
    if (activeTab === 'scalp') refreshScalp();
    if (activeTab === 'session') refreshSession();
  };
});

async function refreshStatus() {
  try {
    const s = await (await fetch('/api/status')).json();
    const vpTabs = ['signals'].map(t => document.querySelector(`.tab[data-tab="${t}"]`));
    vpTabs.forEach(el => { el.style.display = s.volume_profile_enabled === false ? 'none' : ''; });
    if (!vpModeChecked) {
      vpModeChecked = true;
      if (s.volume_profile_enabled === false) {
        document.querySelector('.tab[data-tab="divergence"]').click();
      }
    }
    const el = document.getElementById('status');
    const scanTxt = s.last_scan_finished ? `скан ${s.last_scan_duration}s, ${s.universe_size} пар (искл. ${s.excluded_low_quality||0} неликвид)` : 'сканирование...';
    el.textContent = `v${s.version} · ${scanTxt}`;
  } catch(e) {}
}

async function refreshOverview() {
  try {
    const o = await (await fetch('/api/overview')).json();
    const wrClass = (m) => (m.winrate === null || m.winrate === undefined) ? 'dim' : (m.winrate >= 50 ? 'win' : 'loss');
    const wr = (m) => `<span class="${wrClass(m)}">${m.winrate !== null && m.winrate !== undefined ? m.winrate+'%' : '-'}</span>`;
    const wl = (w, l) => `<span class="win">${w}W</span>/<span class="loss">${l}L</span>`;
    const openTxt = (n) => `<span class="status-open">откр.${n}</span>`;
    const parts = [];
    if (o.volume.enabled) parts.push(`<b>Volume</b> ${wr(o.volume)} (${wl(o.volume.wins, o.volume.losses)}) ${openTxt(o.volume.open)}`);
    if (o.divergence.enabled) parts.push(`<b>Див</b>${o.divergence.invert?'[Р]':''} ${wr(o.divergence)} (${wl(o.divergence.wins, o.divergence.losses)}) ${openTxt(o.divergence.open)}`);
    if (o.ema.enabled) parts.push(`<b>EMA</b>${o.ema.invert?'[Р]':''} ${wr(o.ema)} (${wl(o.ema.wins, o.ema.losses)}) ${openTxt(o.ema.open)}`);
    if (o.scalp.enabled) {
      const scalpWrClass = (o.scalp.winrate === null || o.scalp.winrate === undefined) ? 'dim' : (o.scalp.winrate >= 50 ? 'win' : 'loss');
      const scalpWr = `<span class="${scalpWrClass}">${o.scalp.winrate !== null && o.scalp.winrate !== undefined ? o.scalp.winrate+'%' : '-'}</span>`;
      parts.push(`<b>Скальп</b> ${scalpWr} (<span class="win">${o.scalp.wins}W</span>/<span class="loss">${o.scalp.losses}L</span>/<span class="status-timeout">${o.scalp.timeouts}T</span>) ${openTxt(o.scalp.open)}`);
    }
    if (o.session.enabled) parts.push(`<b>Сессия</b> ${wr(o.session)} (${wl(o.session.wins, o.session.losses)}) ${openTxt(o.session.open)}`);
    document.getElementById('overview').innerHTML = parts.join(' &nbsp;·&nbsp; ');
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
  const [t, s] = await Promise.all([
    (await fetch('/api/tuning')).json(),
    (await fetch('/api/status')).json(),
  ]);
  const el = document.getElementById('tuningPanel');
  const st = s.stats || {};
  const wr = st.winrate !== null && st.winrate !== undefined ? `${st.winrate}%` : '-';
  const at = s.auto_tune || {};
  const atTxt = at.enabled
    ? `автотюнинг: ${at.tuned_symbols}/${s.universe_size} монет уже подобрано (обновление каждые ${at.refresh_hours}ч, +${at.per_cycle}/скан)`
    : 'автотюнинг выключен';
  const br = st.by_reason || {};
  const bounceTxt = br.bounce && br.bounce.total ? `bounce ${br.bounce.winrate}% (${br.bounce.total})` : 'bounce -';
  const breakoutTxt = br.breakout && br.breakout.total ? `breakout ${br.breakout.winrate}% (${br.breakout.total})` : 'breakout -';
  const cv = st.current_version || {};
  const cvTxt = cv.total ? `с v${s.version}: ${cv.winrate}% (${cv.wins}W/${cv.losses}L)` : `с v${s.version}: пока нет закрытых`;
  const detailHtml = `
    <div class="dim" style="margin-bottom:10px;">
      <b>Volume</b> · Винрейт: ${wr} (${st.wins||0}W / ${st.losses||0}L, timeout ${st.timeouts||0}) · ${bounceTxt} · ${breakoutTxt} · открытых: ${st.open||0} · RR ${s.config ? s.config.rr : ''}<br>
      ${atTxt}<br>
      За этот скан отклонено — тренд: ${s.filtered_by_trend||0}, объём: ${s.filtered_by_volume||0}, OI: ${s.filtered_by_oi||0} · ${cvTxt}
    </div>`;
  if (!t.count) {
    el.innerHTML = detailHtml + '<div class="dim" style="padding-top:10px;border-top:1px solid #1c2433;"><b>Объём (Volume Profile) — статистика</b><br>Пока недостаточно данных — подожди пару циклов скана.</div>';
    return;
  }
  el.innerHTML = detailHtml + `
    <div class="dim" style="margin-bottom:10px;padding-top:10px;border-top:1px solid #1c2433;">
      <b>Объём (Volume Profile) — статистика</b> · Всего сигналов с накопленными данными: ${t.count} ·
      WIN: ${t.wins_n} · LOSS: ${t.losses_n} · OPEN: ${t.open_n}
    </div>
    <div style="margin-bottom:10px;"><b>MFE/MAE (R) на момент закрытия сделки</b> — сколько реально было хода в плюс/минус, пока сделка была ещё жива (это и есть ответ на "можно ли было раздвинуть TP/SL"):<br>
      <span class="win">WIN MFE: ${fmtStat(t.mfe_r_wins_at_close)}</span><br>
      <span class="win">WIN MAE: ${fmtStat(t.mae_r_wins_at_close)}</span><br>
      <span class="loss">LOSS MFE: ${fmtStat(t.mfe_r_losses_at_close)}</span><br>
      <span class="loss">LOSS MAE: ${fmtStat(t.mae_r_losses_at_close)}</span>
    </div>
    <div style="margin-bottom:10px;"><b>То же самое, отдельно по bounce и breakout</b> (на закрытии):<br>
      <span class="dim">bounce — </span><span class="win">WIN MFE: ${fmtStat(t.by_reason?.bounce?.mfe_r_wins_at_close)}</span> ·
      <span class="win">MAE: ${fmtStat(t.by_reason?.bounce?.mae_r_wins_at_close)}</span> ·
      <span class="loss">LOSS MFE: ${fmtStat(t.by_reason?.bounce?.mfe_r_losses_at_close)}</span> ·
      <span class="loss">MAE: ${fmtStat(t.by_reason?.bounce?.mae_r_losses_at_close)}</span><br>
      <span class="dim">breakout — </span><span class="win">WIN MFE: ${fmtStat(t.by_reason?.breakout?.mfe_r_wins_at_close)}</span> ·
      <span class="win">MAE: ${fmtStat(t.by_reason?.breakout?.mae_r_wins_at_close)}</span> ·
      <span class="loss">LOSS MFE: ${fmtStat(t.by_reason?.breakout?.mfe_r_losses_at_close)}</span> ·
      <span class="loss">MAE: ${fmtStat(t.by_reason?.breakout?.mae_r_losses_at_close)}</span>
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
    <div style="margin-bottom:8px;"><b>MFE/MAE (R) на момент закрытия сделки</b> — сколько реально было хода в плюс/минус, пока сделка была ещё жива:<br>
      <span class="win">WIN MFE: ${fmtStat(s.mfe_r_wins_at_close)}</span><br>
      <span class="win">WIN MAE: ${fmtStat(s.mae_r_wins_at_close)}</span><br>
      <span class="loss">LOSS MFE: ${fmtStat(s.mfe_r_losses_at_close)}</span><br>
      <span class="loss">LOSS MAE: ${fmtStat(s.mae_r_losses_at_close)}</span>
    </div>
    <details style="margin-top:6px;">
      <summary class="dim" style="cursor:pointer;font-size:12px;">Полное окно (24ч после сигнала, включая то, что было уже после закрытия — для оценки общего запаса, не для оценки конкретной сделки)</summary>
      <div style="margin-top:8px;"><b>MFE (R):</b><br>
        <span class="dim">все: ${fmtStat(s.mfe_r_all)}</span><br>
        <span class="win">WIN: ${fmtStat(s.mfe_r_wins)}</span><br>
        <span class="loss">LOSS: ${fmtStat(s.mfe_r_losses)}</span><br>
        <span class="status-open">OPEN: ${fmtStat(s.mfe_r_open)}</span>
      </div>
      <div style="margin-top:6px;"><b>MAE (R):</b><br>
        <span class="dim">все: ${fmtStat(s.mae_r_all)}</span><br>
        <span class="win">WIN: ${fmtStat(s.mae_r_wins)}</span><br>
        <span class="loss">LOSS: ${fmtStat(s.mae_r_losses)}</span><br>
        <span class="status-open">OPEN: ${fmtStat(s.mae_r_open)}</span>
      </div>
    </details>` : '<div class="dim">Пока недостаточно закрытых сигналов для MFE/MAE.</div>';
  const pm = s.pre_move_pct_all;
  const preMoveBlock = pm ? `
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid #1c2433;">
      <b>Сколько % хода уже съедено к моменту входа</b> (от пивота до входа, с учётом задержки подтверждения):<br>
      <span class="dim">все: ${fmtStat(s.pre_move_pct_all)}</span><br>
      <span class="win">WIN: ${fmtStat(s.pre_move_pct_wins)}</span><br>
      <span class="loss">LOSS: ${fmtStat(s.pre_move_pct_losses)}</span><br>
      <span class="dim" style="font-size:12px;">Положительное — цена уже пошла в нужную сторону до входа (TP ${cfg.tp_pct ? (cfg.tp_pct*100).toFixed(2) : '?'}% — сравни, сколько из него уже "съедено"). Отрицательное — цена ещё не начала двигаться или уже развернулась против.</span>
    </div>` : '';
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
      RSI-дивергенции${cfg.invert_signals ? ' <span style="color:#ffcc55;font-weight:bold;">· РЕВЕРС ВКЛЮЧЁН</span>' : ''} · ТФ ${status.interval} · скан ${status.last_scan_duration!==null && status.last_scan_duration!==undefined ? status.last_scan_duration+'s' : '...'} ·
      Винрейт: ${wr} (${s.wins||0}W / ${s.losses||0}L, timeout ${s.timeouts||0}) · открытых: ${s.open||0} · RR ${cfg.rr}
    </div>
    ${mfeBlock}
    ${preMoveBlock}
    ${psBlock}`;
}

async function refreshEma() {
  const status = await (await fetch('/api/ema/status')).json();
  const rows = await (await fetch('/api/ema/signals')).json();

  const tbody = document.querySelector('#emaTable tbody');
  tbody.innerHTML = '';
  document.getElementById('emptyMsg').style.display = (activeTab==='ema' && rows.length===0) ? 'block' : 'none';
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
      <td class="dim">${r.interval || '-'}</td>
      <td>${fmt(r.entry)}</td>
      <td class="dim">${fmt(r.sl)}</td>
      <td class="dim">${fmt(r.tp)}</td>
      <td class="dim" title="на закрытии → полное окно 24ч">${fmtMfeMae(r, 'mfe_r')}</td>
      <td class="dim" title="на закрытии → полное окно 24ч">${fmtMfeMae(r, 'mae_r')}</td>
      <td>${statusHtml}</td>
      <td class="dim">${fmtTime(r.time)}</td>`;
    tr.onclick = () => openEmaChart(r);
    tbody.appendChild(tr);
  }

  const s = status.stats || {};
  const wr = s.winrate !== null && s.winrate !== undefined ? `${s.winrate}%` : '-';
  const panel = document.getElementById('emaStatsPanel');
  const cfg = status.config || {};
  const mfeBlock = s.dataset_count ? `
    <div style="margin-bottom:8px;"><b>MFE/MAE (R) на момент закрытия сделки</b> — сколько реально было хода в плюс/минус, пока сделка была ещё жива:<br>
      <span class="win">WIN MFE: ${fmtStat(s.mfe_r_wins_at_close)}</span><br>
      <span class="win">WIN MAE: ${fmtStat(s.mae_r_wins_at_close)}</span><br>
      <span class="loss">LOSS MFE: ${fmtStat(s.mfe_r_losses_at_close)}</span><br>
      <span class="loss">LOSS MAE: ${fmtStat(s.mae_r_losses_at_close)}</span>
    </div>
    <details style="margin-top:6px;">
      <summary class="dim" style="cursor:pointer;font-size:12px;">Полное окно (24ч после сигнала, включая то, что было уже после закрытия — для оценки общего запаса, не для оценки конкретной сделки)</summary>
      <div style="margin-top:8px;"><b>MFE (R):</b><br>
        <span class="dim">все: ${fmtStat(s.mfe_r_all)}</span><br>
        <span class="win">WIN: ${fmtStat(s.mfe_r_wins)}</span><br>
        <span class="loss">LOSS: ${fmtStat(s.mfe_r_losses)}</span><br>
        <span class="status-open">OPEN: ${fmtStat(s.mfe_r_open)}</span>
      </div>
      <div style="margin-top:6px;"><b>MAE (R):</b><br>
        <span class="dim">все: ${fmtStat(s.mae_r_all)}</span><br>
        <span class="win">WIN: ${fmtStat(s.mae_r_wins)}</span><br>
        <span class="loss">LOSS: ${fmtStat(s.mae_r_losses)}</span><br>
        <span class="status-open">OPEN: ${fmtStat(s.mae_r_open)}</span>
      </div>
    </details>` : '<div class="dim">Пока недостаточно закрытых сигналов для MFE/MAE.</div>';
  const byInterval = status.stats_by_interval || {};
  const intervalRows = (status.intervals || []).map(iv => {
    const st = byInterval[iv] || {};
    const ivWr = st.winrate !== null && st.winrate !== undefined ? `${st.winrate}%` : '-';
    return `${iv}: <b>${ivWr}</b> (${st.wins||0}W/${st.losses||0}L, timeout ${st.timeouts||0}) · открытых: ${st.open||0}`;
  }).join('<br>');
  panel.innerHTML = `
    <div class="dim" style="margin-bottom:10px;">
      EMA ${cfg.len7}/${cfg.len14}/${cfg.len28} (${cfg.signal_type}${cfg.trend_filter ? ', с фильтром тренда' : ''})${cfg.invert_signals ? ' <span style="color:#ffcc55;font-weight:bold;">· РЕВЕРС ВКЛЮЧЁН</span>' : ''} · сканируются ТФ: ${(status.intervals||[]).join(', ')} ·
      скан ${status.last_scan_duration!==null && status.last_scan_duration!==undefined ? status.last_scan_duration+'s' : '...'} ·
      Винрейт (всё вместе): ${wr} (${s.wins||0}W / ${s.losses||0}L, timeout ${s.timeouts||0}) · открытых: ${s.open||0} · RR ${cfg.rr}
    </div>
    <div style="margin-bottom:10px;padding-top:6px;border-top:1px solid #1c2433;">
      <b>По таймфреймам (для сравнения):</b><br>
      <span style="font-size:13px;">${intervalRows}</span>
    </div>
    ${mfeBlock}`;
}

let scalpExpanded = null;

function fmtScalpRow(r, rank) {
  const dirClass = r.direction === 'LONG' ? 'long' : 'short';
  const mmrTag = r.mmr_verified ? '' : '<span title="MMR не подтверждён с Gate.io, используется консервативный дефолт" style="color:#e0a030;">~</span>';
  const levTag = r.leverage_verified ? '' : '<span title="Макс. плечо биржи для этой монеты не подтверждено с Gate.io — используется консервативный дефолт (10x). Реальный лимит биржи может отличаться, проверь вручную перед входом." style="color:#e0a030;">~</span>';
  return `<tr data-symbol="${r.symbol}" style="cursor:pointer;">
    <td class="dim">${rank}</td>
    <td>${r.symbol}</td>
    <td class="dim">${r.volatility_score !== null && r.volatility_score !== undefined ? r.volatility_score.toFixed(2)+'%' : '-'}</td>
    <td class="${dirClass}">${r.direction}</td>
    <td class="dim">${r.interval}</td>
    <td>${r.target_pct}%</td>
    <td>${r.hit_rate}% <span class="dim">(n=${r.n})</span></td>
    <td class="dim">${r.median_bars_to_hit}б / ${r.time_to_hit_hours}ч</td>
    <td>${r.trades_per_day_est}</td>
    <td>${r.leverage}x${levTag}</td>
    <td class="dim">${r.liq_buffer_pct}%${mmrTag}</td>
    <td class="dim">${r.p90_adverse_pct}%</td>
    <td><b>${r.score}</b></td>
  </tr>`;
}

async function refreshScalp() {
  const status = await (await fetch('/api/scalp/status')).json();
  const signals = await (await fetch('/api/scalp/signals')).json();
  const panel = document.getElementById('scalpPanel');
  const cfg = status.config || {};
  const ss = status.signals_stats || {};
  const buildTxt = status.last_build_finished
    ? `последнее построение: ${fmtTime(status.last_build_finished)} (${status.last_build_duration}s) · монет обработано: ${status.symbols_done}/${status.universe_size}`
    : `первое построение ещё не завершилось (${status.symbols_done}/${status.universe_size || '?'})`;
  const ssWr = ss.win_rate !== null && ss.win_rate !== undefined ? `${ss.win_rate}%` : '-';
  const headerHtml = `
    <div class="dim" style="margin-bottom:8px;">
      Цель: $${cfg.target_profit_usd} со счёта $${cfg.account_usd} · ТФ: ${(cfg.intervals||[]).join(', ')} ·
      мин. hit-rate ${cfg.min_hit_rate}% · запас безопасности x${cfg.safety_margin} · комиссия ${(cfg.taker_fee_pct*100).toFixed(3)}%/сторону<br>
      ${buildTxt} · без безопасной конфигурации: ${status.no_safe_config_count}<br>
      <b>Живые сигналы</b> (вход на закрытии свечи, топ-${cfg.signal_top_n || 1} по score): ${ssWr} (${ss.wins||0}W/${ss.losses||0}L/${ss.timeouts||0}TIMEOUT) · открытых: ${ss.open||0} · всего: ${ss.total||0}<br>
      <span style="font-size:11px;">~ рядом с буфером = MMR не подтверждён с Gate.io, используется консервативный дефолт ${(cfg.default_mmr_pct*100).toFixed(2)}%<br>
      ~ рядом с плечом = макс. плечо биржи для монеты не подтверждено, используется дефолт ${cfg.default_max_leverage}x — проверь реальный лимит на бирже перед входом</span>
    </div>`;
  const signalsRows = signals.map(s => {
    const dirClass = s.direction === 'LONG' ? 'long' : 'short';
    let statusHtml;
    if (s.status === 'OPEN') statusHtml = '<span class="status-open">OPEN</span>';
    else if (s.result === 'WIN') statusHtml = `<span class="win">WIN @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else if (s.result === 'LOSS') statusHtml = `<span class="loss">LOSS @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else statusHtml = '<span class="status-timeout">TIMEOUT</span>';
    return `<tr>
      <td>${s.symbol}</td><td class="${dirClass}">${s.direction}</td><td class="dim">${s.interval}</td>
      <td>${fmt(s.entry)}</td><td class="dim">${fmt(s.target_price)} (${s.target_pct}%)</td>
      <td class="dim">${s.sl_price !== undefined ? fmt(s.sl_price)+' ('+s.sl_pct+'%)' : '-'}</td>
      <td class="dim">${s.leverage}x</td><td>${statusHtml}</td><td class="dim">${fmtTime(s.time)}</td>
    </tr>`;
  }).join('');
  const signalsTableHtml = signals.length ? `
    <div style="overflow-x:auto;margin-bottom:14px;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>Dir</th><th>TF</th><th>Entry</th><th>Target</th><th>SL</th><th>Плечо</th><th>Status</th><th>Time</th></tr></thead>
      <tbody>${signalsRows}</tbody>
    </table>
    </div>` : '<div class="dim" style="margin-bottom:14px;">Живых сигналов пока нет.</div>';
  if (!status.top || status.top.length === 0) {
    panel.innerHTML = headerHtml + signalsTableHtml + '<div class="dim">Пока нет рекомендаций — либо ещё считается, либо ни одна монета не прошла проверку безопасности при текущих настройках.</div>';
    return;
  }
  const rows = status.top.map((r, i) => fmtScalpRow(r, i + 1)).join('');
  panel.innerHTML = headerHtml + signalsTableHtml + `
    <div class="dim" style="margin-bottom:6px;"><b>Рекомендации по монетам</b> (для справки, откуда берутся сигналы):</div>
    <div style="overflow-x:auto;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr>
        <th>#</th><th>Symbol</th><th>Vola</th><th>Dir</th><th>TF</th><th>Target</th>
        <th>Hit-rate</th><th>До цели</th><th>Trades/д</th><th>Плечо</th><th>Буфер</th><th>p90 adv</th><th>Score</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    </div>
    <div id="scalpDetail" style="margin-top:12px;"></div>`;
  document.querySelectorAll('#scalpPanel tbody tr[data-symbol]').forEach(tr => {
    tr.onclick = () => openScalpDetail(tr.dataset.symbol);
  });
}

async function openScalpDetail(symbol) {
  const detail = document.getElementById('scalpDetail');
  if (scalpExpanded === symbol) {
    detail.innerHTML = '';
    scalpExpanded = null;
    return;
  }
  scalpExpanded = symbol;
  detail.innerHTML = '<div class="dim">загрузка...</div>';
  try {
    const j = await (await fetch(`/api/scalp/symbol/${symbol}`)).json();
    if (j.error) { detail.innerHTML = `<div class="dim">${j.error}</div>`; return; }
    let html = `<div style="border-top:1px solid #1c2433;padding-top:8px;"><b>${symbol}</b> — полная разбивка по ТФ/направлению/цели` +
      `${j.mmr_verified ? '' : ' <span style="color:#e0a030;">(MMR не подтверждён, дефолт)</span>'}:</div>`;
    for (const interval in j.data) {
      for (const direction in j.data[interval]) {
        const dirClass = direction === 'LONG' ? 'long' : 'short';
        html += `<div style="margin-top:6px;"><b>${interval} · <span class="${dirClass}">${direction}</span></b><br>`;
        const targets = j.data[interval][direction];
        const parts = [];
        for (const pct in targets) {
          const t = targets[pct];
          parts.push(`${pct}%: ${t.hit_rate}% (n=${t.n}, ${t.median_bars_to_hit}б, p90adv ${t.p90_adverse_pct}%)`);
        }
        html += `<span style="font-size:11px;">${parts.join(' · ')}</span></div>`;
      }
    }
    detail.innerHTML = html;
  } catch (e) {
    detail.innerHTML = `<div class="dim">ошибка загрузки: ${e}</div>`;
  }
}

let sessionExpanded = null;

function fmtSessionRow(r, rank) {
  const wrClass = (r.win_rate === null || r.win_rate === undefined) ? 'dim' : (r.win_rate >= 50 ? 'win' : 'loss');
  const sampleTag = r.meets_min_sample ? '' : '<span title="Меньше минимальной выборки — ненадёжно" style="color:#e0a030;">~</span>';
  return `<tr data-symbol="${r.symbol}" style="cursor:pointer;">
    <td class="dim">${rank}</td>
    <td>${r.symbol}</td>
    <td class="${wrClass}">${r.win_rate !== null && r.win_rate !== undefined ? r.win_rate+'%' : '-'}${sampleTag}</td>
    <td class="dim">n=${r.n}</td>
    <td class="win">${r.wins}W</td>
    <td class="loss">${r.losses}L</td>
    <td class="status-timeout">${r.timeouts}T</td>
  </tr>`;
}

async function refreshSession() {
  const status = await (await fetch('/api/session/status')).json();
  const signals = await (await fetch('/api/session/signals')).json();
  const panel = document.getElementById('sessionPanel');
  const cfg = status.config || {};
  const ss = status.signals_stats || {};
  const buildTxt = status.last_backtest_finished
    ? `последний бэктест: ${fmtTime(status.last_backtest_finished)} (${status.last_backtest_duration}s) · монет обработано: ${status.symbols_done}/${status.universe_size}`
    : `первый бэктест ещё не завершился (${status.symbols_done}/${status.universe_size || '?'})`;
  const nextOpenTxt = status.next_open_ts ? `следующее открытие сессии: ${fmtTime(status.next_open_ts)}` : '';
  const ssWr = ss.winrate !== null && ss.winrate !== undefined ? `${ss.winrate}%` : '-';
  const watchTxt = Object.entries(status.watch_symbols || {}).map(([sym, w]) => {
    const label = {ranked: 'в рейтинге', zero_manipulations_found: 'манипуляций не найдено', not_yet_processed: 'ещё считается', not_in_universe: 'не в вселенной'}[w.status] || w.status;
    return `${sym}: ${label}${w.n !== null && w.n !== undefined ? ' (n='+w.n+')' : ''}`;
  }).join(' · ');
  const headerHtml = `
    <div class="dim" style="margin-bottom:8px;">
      Открытие сессии: ${cfg.open_hour_local}:00 (UTC+${cfg.utc_offset_hours}, фикс.) · диапазон проторговки: с ${cfg.range_start_utc_hour}:00 UTC до открытия, ТФ ${cfg.range_tf} ·
      окно манипуляции: первые ${cfg.manipulation_window_min} мин после открытия · мин. выборка для ранжирования: ${cfg.min_sample}<br>
      ${buildTxt} · ${nextOpenTxt}<br>
      Монет в рейтинге: ${(status.top||[]).length} · манипуляций не найдено: ${status.zero_manipulation_count||0} · ещё не обработано: ${status.not_yet_processed_count||0}<br>
      ${watchTxt}<br>
      <b>Живые сигналы</b>: ${ssWr} (${ss.wins||0}W/${ss.losses||0}L, timeout ${ss.timeouts||0}) · открытых: ${ss.open||0} · всего: ${ss.total||0}<br>
      <span style="font-size:11px;">~ рядом с винрейтом = меньше минимальной выборки (${cfg.min_sample}) — цифра пока ненадёжна<br>
      "манипуляций не найдено" = монета прошла отбор по ликвидности и была проверена, просто ни разу не дала подходящий паттерн — не исключена как неликвидная</span>
    </div>`;
  const signalsRows = signals.map(s => {
    const dirClass = s.direction === 'LONG' ? 'long' : 'short';
    let statusHtml;
    if (s.status === 'OPEN') statusHtml = '<span class="status-open">OPEN</span>';
    else if (s.result === 'WIN') statusHtml = `<span class="win">WIN @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else if (s.result === 'LOSS') statusHtml = `<span class="loss">LOSS @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else statusHtml = '<span class="status-timeout">TIMEOUT</span>';
    return `<tr data-symbol="${s.symbol}" data-session-open="${s.session_open}" style="cursor:pointer;">
      <td>${s.symbol}</td><td class="${dirClass}">${s.direction}</td>
      <td>${fmt(s.entry)}</td><td class="dim">${fmt(s.sl)}</td><td class="dim">${fmt(s.tp)}</td>
      <td>${statusHtml}</td><td class="dim">${fmtTime(s.session_open)}</td>
    </tr>`;
  }).join('');
  const signalsTableHtml = signals.length ? `
    <div style="overflow-x:auto;margin-bottom:14px;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>Status</th><th>Открытие</th></tr></thead>
      <tbody>${signalsRows}</tbody>
    </table>
    </div>` : '<div class="dim" style="margin-bottom:14px;">Живых сигналов пока нет.</div>';
  if (!status.top || status.top.length === 0) {
    panel.innerHTML = headerHtml + signalsTableHtml + '<div class="dim">Пока нет результатов бэктеста — либо ещё считается, либо ни у одной монеты не нашлось манипуляций.</div>';
    wireSessionRowClicks();
    return;
  }
  const rows = status.top.map((r, i) => fmtSessionRow(r, i + 1)).join('');
  panel.innerHTML = headerHtml + signalsTableHtml + `
    <div id="sessionDetail" style="margin-bottom:12px;"></div>
    <div class="dim" style="margin-bottom:6px;"><b>Бэктест по монетам</b> (сортировка: сначала прошедшие мин. выборку, потом по винрейту):</div>
    <div style="overflow-x:auto;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>#</th><th>Symbol</th><th>Win-rate</th><th>n</th><th>W</th><th>L</th><th>T</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    </div>`;
  wireSessionRowClicks();
}

function wireSessionRowClicks() {
  document.querySelectorAll('#sessionPanel tbody tr[data-session-open]').forEach(tr => {
    tr.onclick = () => openSessionChart(tr.dataset.symbol, tr.dataset.sessionOpen);
  });
  document.querySelectorAll('#sessionPanel tbody tr[data-symbol]:not([data-session-open])').forEach(tr => {
    tr.onclick = () => openSessionDetail(tr.dataset.symbol);
  });
}

async function openSessionDetail(symbol) {
  const detail = document.getElementById('sessionDetail');
  if (sessionExpanded === symbol) {
    detail.innerHTML = '';
    sessionExpanded = null;
    return;
  }
  sessionExpanded = symbol;
  detail.innerHTML = '<div class="dim">загрузка...</div>';
  try {
    const j = await (await fetch(`/api/session/symbol/${symbol}`)).json();
    if (j.error) { detail.innerHTML = `<div class="dim">${j.error}</div>`; return; }
    const rows = (j.results || []).map(r => {
      const dirClass = r.direction === 'LONG' ? 'long' : 'short';
      const resClass = r.result === 'WIN' ? 'win' : (r.result === 'LOSS' ? 'loss' : 'status-timeout');
      return `<span class="sessionDayLink" data-symbol="${symbol}" data-session-open="${r.session_open}" style="cursor:pointer;text-decoration:underline dotted;">${fmtTime(r.session_open)}: <span class="${dirClass}">${r.direction}</span> <span class="${resClass}">${r.result}</span></span>`;
    }).join(' · ');
    detail.innerHTML = `<div style="border-top:1px solid #1c2433;padding-top:8px;"><b>${symbol}</b> — история по дням (клик открывает график):<br>
      <span style="font-size:11px;">${rows || 'нет данных'}</span></div>`;
    detail.querySelectorAll('.sessionDayLink').forEach(el => {
      el.onclick = () => openSessionChart(el.dataset.symbol, el.dataset.sessionOpen);
    });
  } catch (e) {
    detail.innerHTML = `<div class="dim">ошибка загрузки: ${e}</div>`;
  }
}

async function refreshAll() {
  await refreshStatus();
  await refreshOverview();
  await refreshSignals();
  if (activeTab === 'signals') await refreshTuning();
  if (activeTab === 'divergence') await refreshDivergence();
  if (activeTab === 'ema') await refreshEma();
  if (activeTab === 'scalp') await refreshScalp();
  if (activeTab === 'session') await refreshSession();
}
refreshAll();
setInterval(refreshAll, 15000);

function wireResetButton(btnId, endpoint, confirmMsg, idleLabel) {
  const btn = document.getElementById(btnId);
  btn.onclick = async () => {
    const sure = confirm(confirmMsg);
    if (!sure) return;
    btn.disabled = true;
    btn.textContent = 'Удаляю...';
    try {
      const res = await (await fetch(endpoint, {method: 'POST'})).json();
      if (res.ok) {
        await refreshAll();
      } else {
        alert('Не удалось очистить: ' + (res.error || 'неизвестная ошибка'));
      }
    } catch (e) {
      alert('Не удалось очистить: ' + e);
    }
    btn.disabled = false;
    btn.textContent = idleLabel;
  };
}
wireResetButton('resetVolumeBtn', '/api/reset/volume',
  'Удалить статистику и подобранные параметры Volume Profile (Сигналы/Watchlist/Тюнинг)? Дивергенции не тронет. Это необратимо.',
  'Очистить объём');
wireResetButton('resetDivBtn', '/api/reset/divergence',
  'Удалить статистику RSI-дивергенций? Volume Profile не тронет. Это необратимо.',
  'Очистить дивер');
wireResetButton('resetEmaBtn', '/api/reset/ema',
  'Удалить статистику EMA-индикатора? Остальное не тронет. Это необратимо.',
  'Очистить индикатор');
wireResetButton('resetScalpBtn', '/api/reset/scalp',
  'Удалить накопленную статистику скальпинга (вселенная, данные по монетам, рекомендации)? Остальное не тронет. Это необратимо.',
  'Очистить скальпинг');
wireResetButton('resetSessionBtn', '/api/reset/session',
  'Удалить накопленный бэктест и сигналы по манипуляции на открытии сессии? Остальное не тронет. Это необратимо.',
  'Очистить сессию');

// ---------------- Settings modal ----------------
const settingsModal = document.getElementById('settingsModal');
const setInputs = {
  volume_profile_enabled: document.getElementById('setVolumeProfile'),
  bounce_enabled: document.getElementById('setBounce'),
  breakout_enabled: document.getElementById('setBreakout'),
  divergence_enabled: document.getElementById('setDivergence'),
  div_invert_signals: document.getElementById('setDivInvert'),
  ema_enabled: document.getElementById('setEma'),
  ema_invert_signals: document.getElementById('setEmaInvert'),
  scalp_enabled: document.getElementById('setScalp'),
  scalp_signals_enabled: document.getElementById('setScalpSignals'),
  session_enabled: document.getElementById('setSession'),
  telegram_enabled: document.getElementById('setTelegram'),
  telegram_alerts_vp: document.getElementById('setTelegramVp'),
  telegram_alerts_div: document.getElementById('setTelegramDiv'),
  telegram_alerts_ema: document.getElementById('setTelegramEma'),
  telegram_alerts_hourly: document.getElementById('setTelegramHourly'),
  telegram_alerts_session: document.getElementById('setTelegramSession'),
};

function applySettingsToInputs(s) {
  for (const key in setInputs) {
    if (s[key] !== undefined) setInputs[key].checked = s[key];
  }
  document.getElementById('setTelegramSub').textContent = s.telegram_configured
    ? 'токен найден'
    : 'токен не найден — уведомления не уйдут, даже если включено';
}

async function loadSettings() {
  try {
    const s = await (await fetch('/api/settings')).json();
    applySettingsToInputs(s);
  } catch (e) {}
}

document.getElementById('settingsBtn').onclick = async () => {
  settingsModal.classList.add('open');
  await loadSettings();
};
document.getElementById('settingsCloseBtn').onclick = () => settingsModal.classList.remove('open');

for (const key in setInputs) {
  setInputs[key].onchange = async (e) => {
    const input = e.target;
    input.disabled = true;
    try {
      const res = await (await fetch('/api/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({[key]: input.checked}),
      })).json();
      if (res.ok) {
        applySettingsToInputs(res.settings);
      } else {
        alert('Не удалось сохранить настройку');
        await loadSettings();
      }
    } catch (err) {
      alert('Не удалось сохранить настройку: ' + err);
      await loadSettings();
    }
    input.disabled = false;
  };
}

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

  const allCandles = data.candles || [];
  if (!allCandles.length) return;
  const { start: winStart, end: winEnd } = windowAroundTime(allCandles, signalRow && signalRow.time, 20, 70);
  const candles = allCandles.slice(winStart, winEnd);

  const profileW = W * 0.22;
  const chartW = W - profileW - 50;
  const padTop = 10, padBottom = 24;
  const chartH = H - padTop - padBottom;

  const hasTrade = signalRow && signalRow.entry !== undefined && signalRow.sl !== undefined;
  const { hi, lo } = computeYRangeSimple(candles, hasTrade ? signalRow.entry : undefined,
    hasTrade ? signalRow.sl : undefined, hasTrade ? signalRow.tp : undefined);
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

  const allCandles = data.candles || [];
  const allRsi = data.rsi || [];
  if (!allCandles.length) return;
  // wider before-margin than other charts: pivots can sit up to left+right+rsi_window
  // bars before the signal's own bar, not just a handful
  const { start: winStart, end: winEnd } = windowAroundTime(allCandles, row && row.time, 30, 80);
  const candles = allCandles.slice(winStart, winEnd);
  const rsi = allRsi.slice(winStart, winEnd);
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
  const { hi, lo } = computeYRangeSimple(candles, row && row.entry, row && row.sl, row && row.tp);
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

// ---------------- EMA chart modal ----------------
const emaModal = document.getElementById('emaModal');
document.getElementById('emaCloseBtn').onclick = () => emaModal.classList.remove('open');
let currentEmaRow = null;
let currentEmaData = null;

async function openEmaChart(row) {
  currentEmaRow = row;
  document.getElementById('emaModalTitle').textContent = row.symbol;
  document.getElementById('emaModalParams').textContent = 'загрузка...';
  emaModal.classList.add('open');
  try {
    const data = await (await fetch(`/api/ema/chart/${row.symbol}?interval=${encodeURIComponent(row.interval || '')}`)).json();
    currentEmaData = data;
    document.getElementById('emaModalParams').textContent =
      `EMA 7/14/28 · ${row.interval || ''} · ${row.direction} · entry ${fmt(row.entry)} · SL ${fmt(row.sl)} · TP ${fmt(row.tp)}`;
    drawEmaChart(data, row);
  } catch (e) {
    console.error(e);
  }
}

function windowAroundTime(candles, targetTime, beforeBars, totalBars) {
  let idx = candles.length - 1;
  if (targetTime !== undefined) {
    const found = candles.findIndex(c => c.time === targetTime);
    if (found >= 0) idx = found;
  }
  let start = Math.max(0, idx - beforeBars);
  let end = Math.min(candles.length, start + totalBars);
  if (end - start < totalBars) start = Math.max(0, end - totalBars);
  return { start, end };
}

function windowParamsForInterval(interval) {
  // a weekly bar covers ~52x more time than an hourly one — the same bar
  // COUNT would span over a year, way more than needed to see the setup
  if (interval === '1w') return { before: 6, total: 20 };
  if (interval === '3d') return { before: 8, total: 25 };
  if (interval === '1d') return { before: 10, total: 35 };
  return { before: 15, total: 60 };
}

function computeYRangeSimple(candles, entry, sl, tp) {
  // deliberately no zone-compression logic — after repeated back-and-forth
  // tuning that was still sometimes uninformative (entry point invisible
  // or most candles clipped depending on the case), simple natural
  // min/max of what's actually shown is more reliably readable.
  let hi = Math.max(...candles.map(c => c.high));
  let lo = Math.min(...candles.map(c => c.low));
  if (entry !== undefined && sl !== undefined && tp !== undefined) {
    hi = Math.max(hi, entry, sl, tp);
    lo = Math.min(lo, entry, sl, tp);
  }
  const range = (hi - lo) || (hi * 0.02) || 1;
  const pad = range * 0.05;
  return { hi: hi + pad, lo: lo - pad };
}

function drawEmaChart(data, row) {
  const canvas = document.getElementById('emaChartCanvas');
  const wrap = document.getElementById('emaChartWrap');
  const dpr = window.devicePixelRatio || 1;
  const W = wrap.clientWidth, H = wrap.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const allCandles = data.candles || [];
  if (!allCandles.length) return;
  const { before: emaBefore, total: emaTotal } = windowParamsForInterval(row && row.interval);
  const { start: winStart, end: winEnd } = windowAroundTime(allCandles, row && row.time, emaBefore, emaTotal);
  const candles = allCandles.slice(winStart, winEnd);
  const ema7Full = data.ema7 || [], ema14Full = data.ema14 || [], ema28Full = data.ema28 || [];
  const ema7 = ema7Full.slice(winStart, winEnd);
  const ema14 = ema14Full.slice(winStart, winEnd);
  const ema28 = ema28Full.slice(winStart, winEnd);
  const padRight = 54;
  const chartW = W - padRight;
  const n = candles.length;
  const slot = chartW / n;
  const bodyW = Math.max(1, slot * 0.6);
  const xAt = (i) => i * slot + slot / 2;

  const { hi, lo } = computeYRangeSimple(candles, row && row.entry, row && row.sl, row && row.tp);
  const range = hi - lo || 1;
  const yP = (price) => (hi - price) / range * H;

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

  const drawEmaLine = (values, color) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    let started = false;
    values.forEach((v, i) => {
      if (v === null || v === undefined) return;
      const cx = xAt(i), cy = yP(v);
      if (!started) { ctx.moveTo(cx, cy); started = true; } else { ctx.lineTo(cx, cy); }
    });
    ctx.stroke();
  };
  drawEmaLine(ema7, '#2962FF');
  drawEmaLine(ema14, '#FF6D00');
  drawEmaLine(ema28, '#E53935');

  ctx.fillStyle = 'rgba(5,7,12,0.75)';
  ctx.fillRect(4, 4, 150, 40);
  ctx.font = 'bold 10px sans-serif';
  ctx.fillStyle = '#2962FF'; ctx.fillText('EMA 7', 8, 16);
  ctx.fillStyle = '#FF6D00'; ctx.fillText('EMA 14', 8, 28);
  ctx.fillStyle = '#E53935'; ctx.fillText('EMA 28', 8, 40);

  if (row) {
    drawLevelLine(ctx, yP(row.entry), chartW, '#5aa8ff', 'ENTRY ' + fmtNum(row.entry));
    drawLevelLine(ctx, yP(row.sl), chartW, '#ff6b6b', 'SL ' + fmtNum(row.sl));
    drawLevelLine(ctx, yP(row.tp), chartW, '#3ddc97', 'TP ' + fmtNum(row.tp));
  }
}

// ---------------- Session chart modal ----------------
const sessionModal = document.getElementById('sessionModal');
document.getElementById('sessionCloseBtn').onclick = () => sessionModal.classList.remove('open');
let currentSessionData = null;

async function openSessionChart(symbol, sessionOpen) {
  document.getElementById('sessionModalTitle').textContent = symbol;
  document.getElementById('sessionModalParams').textContent = 'загрузка...';
  sessionModal.classList.add('open');
  try {
    const data = await (await fetch(`/api/session/chart/${symbol}?session_open=${sessionOpen}`)).json();
    if (data.error) { document.getElementById('sessionModalParams').textContent = data.error; return; }
    currentSessionData = data;
    const sig = data.signal;
    if (!sig) {
      document.getElementById('sessionModalParams').textContent = `${fmtTime(sessionOpen)} · манипуляции в этот день не было`;
    } else {
      const resTxt = data.result ? ` · ${data.result}${data.exit_price ? ' @ '+fmtNum(data.exit_price) : ''}` : '';
      document.getElementById('sessionModalParams').textContent =
        `${fmtTime(sessionOpen)} · ${sig.direction} · entry ${fmtNum(sig.entry)} · SL ${fmtNum(sig.sl)} · TP ${fmtNum(sig.tp)}${resTxt}`;
    }
    drawSessionChart(data);
  } catch (e) {
    console.error(e);
  }
}

function drawSessionChart(data) {
  const canvas = document.getElementById('sessionChartCanvas');
  const wrap = document.getElementById('sessionChartWrap');
  const dpr = window.devicePixelRatio || 1;
  const W = wrap.clientWidth, H = wrap.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const candles = data.candles || [];
  if (!candles.length) return;
  const sig = data.signal;

  const padRight = 54;
  const chartW = W - padRight;
  const n = candles.length;
  const slot = chartW / n;
  const bodyW = Math.max(1, slot * 0.6);
  const xAt = (i) => i * slot + slot / 2;

  const entry = sig ? sig.entry : undefined;
  const sl = sig ? sig.sl : undefined;
  const tp = sig ? sig.tp : undefined;
  const { hi, lo } = computeYRangeSimple(candles, entry, sl, tp);
  const range = hi - lo || 1;
  const yP = (price) => (hi - price) / range * H;

  if (sig) {
    ctx.fillStyle = 'rgba(80,160,255,0.08)';
    const topY = yP(sig.range_high), botY = yP(sig.range_low);
    ctx.fillRect(0, Math.min(topY, botY), chartW, Math.abs(botY - topY));
  }

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

  const openIdx = candles.findIndex(c => c.time === data.session_open);
  if (openIdx >= 0) {
    const ox = xAt(openIdx);
    ctx.strokeStyle = 'rgba(255,255,255,0.35)';
    ctx.setLineDash([4, 3]);
    ctx.beginPath(); ctx.moveTo(ox, 0); ctx.lineTo(ox, H); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 10px sans-serif';
    ctx.fillText('OPEN', ox + 3, 12);
  }

  if (sig) {
    drawLevelLine(ctx, yP(sig.range_high), chartW, '#5aa8ff', 'RANGE HIGH ' + fmtNum(sig.range_high));
    drawLevelLine(ctx, yP(sig.range_low), chartW, '#5aa8ff', 'RANGE LOW ' + fmtNum(sig.range_low));
    drawLevelLine(ctx, yP(sig.entry), chartW, '#e8b93d', 'ENTRY ' + fmtNum(sig.entry));
    drawLevelLine(ctx, yP(sig.sl), chartW, '#ff6b6b', 'SL ' + fmtNum(sig.sl));
    drawLevelLine(ctx, yP(sig.tp), chartW, '#3ddc97', 'TP ' + fmtNum(sig.tp));
  }
}

window.addEventListener('resize', () => {
  if (modal.classList.contains('open') && currentData) {
    drawChart(currentData, currentRow);
  }
  if (divModal.classList.contains('open') && currentDivData) {
    drawDivergenceChart(currentDivData, currentDivRow);
  }
  if (emaModal.classList.contains('open') && currentEmaData) {
    drawEmaChart(currentEmaData, currentEmaRow);
  }
  if (sessionModal.classList.contains('open') && currentSessionData) {
    drawSessionChart(currentSessionData);
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
    load_settings()
    _load_alert_cfg()
    threading.Thread(target=_telegram_sender_worker, daemon=True).start()
    t = threading.Thread(target=scan_loop, daemon=True)
    t.start()
    threading.Thread(target=scalp_loop, daemon=True).start()
    threading.Thread(target=hourly_stats_loop, daemon=True).start()
    threading.Thread(target=session_loop, daemon=True).start()
    threading.Thread(target=session_live_loop, daemon=True).start()
    port = int(os.environ.get("VP_PORT", 8080))
    tg_status = "настроен" if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) else "не настроен"
    print(f"VP-POC Screener v{APP_VERSION} — http://127.0.0.1:{port} — Telegram: {tg_status}")
    app.run(host="0.0.0.0", port=port, threaded=True)
