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
v0.47.1 - real bug: a live session signal (BULLA_USDT, LOSS in the
         table) but opening its chart said no manipulation happened
         and showed nothing. scan_symbol_session_live() fetched candles
         up to time.time() and evaluated ALL of them including the
         most recent — which, mid-window, is very likely still
         FORMING (its OHLC keeps changing until the candle actually
         closes). A transient wick+close-back-inside during formation
         could satisfy detect_session_manipulation() and fire a signal,
         but by the time /api/session/chart re-derives from now-
         finalized candle data, that same candle's real final values no
         longer show the pattern — exactly the mismatch reported. Fixed
         by excluding any candle whose close time hasn't been reached
         yet (c["time"] + interval_sec > now) before running detection
         — only fully-closed candles get evaluated live, matching what
         backtesting already does implicitly (every candle in a past
         day is guaranteed closed). Verified directly: a candle still
         within its own formation window no longer creates a signal
         (0 signals, was firing before the fix), while the identical
         candle re-checked after its close time has passed still
         creates the correct signal — the fix only excludes genuinely
         incomplete data, not real detections. Full scan-function/
         endpoint regression stayed clean.
v0.48.0 - Auto-trading on Gate.io futures, off the signals every module
         already generates. Real money, so built and verified this in
         layers rather than all at once, referencing hard-learned
         lessons from the mambaleylo/EMA-screener project (per-symbol
         leverage_max/quanto_multiplier instead of a flat assumption,
         POSITION_NOT_FOUND not treated as an error, bounded-limit-style
         stop orders to cap slippage).
         Gate APIv4 HMAC-SHA512 request signing (gate_signed_request) —
         verified the empty-payload SHA512 hash against Gate's own
         documented value, and independently recomputed a full request
         signature by hand to confirm gate_signed_request's output
         matches. Credentials (API key/secret) live in their own file
         (vp_poc_credentials.json, chmod 600), entered via the UI,
         deliberately kept separate from the general settings file so a
         secret never ends up in a GET /api/settings response — only a
         "configured: true/false" boolean is ever returned.
         compute_position_size() converts the configured sizing
         (% of futures wallet balance, or a flat $ margin — mode
         switchable, only one active at a time) into a contract count
         using each symbol's own quanto_multiplier/order_size_min,
         instead of the EMA-screener's flat "force minimum 1 contract"
         approach: if hitting the minimum lot would need more than 1.5x
         the intended notional, the trade is skipped rather than
         silently oversized. Order flow: set_leverage -> market order
         (tif=ioc, the only tif Gate allows at price=0) -> two
         price-triggered close orders for TP/SL (rule=1/2 verified
         correct and mirrored for LONG vs SHORT). execute_autotrade()
         is the single entry point every signal source calls through,
         always writes exactly one log entry (OPENED/SKIPPED/DRY_RUN/
         ERROR) regardless of outcome, and makes ZERO network calls in
         dry-run — verified directly, since that's the single most
         important safety property here.
         Per direct request: opt-in per mode with Volume split into
         bounce/breakout specifically (6 independent toggles total),
         leverage configurable per mode EXCEPT scalp, which uses its
         own signal's already-computed leverage field instead of a
         settings fallback. AUTOTRADE_DRY_RUN defaults to on (verified:
         a fresh install has dry-run true and every mode-enabled flag
         false) — no real order fires until both the person turns dry-
         run off AND enables a specific mode.
         Wired into all 6 signal-creation sites (bounce, breakout,
         divergence, EMA, scalp, session) — verified end-to-end with a
         mixed live-scan run: session/scalp/EMA signals all correctly
         reached execute_autotrade and logged DRY_RUN entries with the
         right values (scalp's leverage pulled from its own signal,
         confirmed at 12.5x not the fallback).
         Settings UI: new "Автоторговля" group — API key/secret input
         (password-masked, save/clear buttons, status line that never
         echoes the secret back), dry-run switch, size mode+value,
         and the 6 per-mode toggles with their leverage inputs.
         Verified: full settings round-trip across all new keys
         (checkbox AND value-type together), out-of-range leverage/
         invalid size-mode rejected rather than silently accepted, all
         new element IDs unique, JS syntax clean, and the full
         scan-function/endpoint regression stayed clean throughout.
         NOT yet done: a dedicated autotrade log viewer in the UI (the
         log itself is being written correctly, just not surfaced
         anywhere to look at yet) and a prominent live-money warning
         banner when dry-run is off — next up.
v0.48.1 - the two pieces left over from v0.48.0: new "Автоторговля" tab
         with a live/dry-run status line, per-mode enabled state, and
         the full trade attempt log (OPENED/DRY_RUN/SKIPPED/ERROR, with
         detail text) via two new routes (/api/autotrade/log,
         /api/autotrade/status). A red "⚠️ РЕАЛЬНЫЕ ОРДЕРА ВКЛЮЧЕНЫ"
         banner shows inside that tab whenever dry-run is off, plus a
         compact always-visible version in the persistent header
         (independent of which tab is open) so live-money mode can't
         go unnoticed while looking at something else.
         Caught and fixed a real bug in my own edit before pushing: an
         earlier str_replace's old_str matched the exact text of the
         "async function refreshAll() {" declaration line and the
         replacement didn't preserve it, silently deleting that
         function's own opening line — its body was still there but
         no longer inside any function, which node --check correctly
         flagged as "await is only valid in async functions". Restored
         the declaration, reran the JS syntax check clean, and
         confirmed via grep that both refreshAll and refreshAutotrade
         now have exactly one declaration each (would have caught a
         duplicate too, not just the deletion). Full scan-function/
         endpoint regression stayed clean, and the two new endpoints
         verified directly with mock log entries covering all four
         status types.
v0.49.0 - Balance simulator, separate from the real/dry-run auto-trader:
         always runs for every firing signal across all six sources
         regardless of each mode's own autotrade-enabled toggle, using
         the same sizing/leverage config, to answer "what would my
         balance look like if this had been running the whole time"
         continuously rather than only once a mode is turned on.
         sim_execute_trade() opens a paper position sized off the
         running simulated balance (AUTOTRADE_SIM_START_BALANCE,
         default $30) and keeps a direct reference to the originating
         signal record; sweep_sim_trades() (wired into the main scan
         loop) settles it once that record's own outcome-tracking sets
         status=CLOSED, computing PnL from the REAL exit price the
         signal actually closed at rather than an assumed R-multiple,
         with entry+exit taker fees applied both ways. Verified the
         PnL/fee math by hand against a known case (margin $10, 10x
         leverage, +2% move -> net $1.95 after $0.05 fees each side)
         and confirmed it matches exactly, plus a LOSS case and the
         zero-balance guard (stops opening new paper trades once
         busted).
         Persistence: sim_balance and SETTLED trades survive a restart;
         still-PENDING trades are deliberately excluded on save, since
         their live signal reference can't survive a restart anyway
         (scalp/session signals aren't persisted either) — verified via
         a full save/reload cycle that only the settled trade survives
         and the balance is exact.
         New "Симулятор" tab (balance, PnL $ and %, win rate, full trade
         history with per-trade PnL and running balance) plus three API
         routes (/api/simulator/status, /trades, /reset — the trades
         route strips the internal _signal_ref before returning,
         verified it never leaks). Learned from the exact mistake in
         v0.48.1 (an insertion that silently ate the refreshAll()
         declaration line): inserted refreshSimulator() as a fully
         isolated block this time and immediately ran node --check plus
         a grep for exactly-one-declaration on both functions before
         doing anything else — confirmed clean on the first try.
         Full scan-function/endpoint regression stayed clean throughout.
v0.49.1 - corrected the simulator's design per direct feedback: it
         should mirror the real/dry-run auto-trader's actual trades,
         not run independently for every signal regardless of which
         modes are enabled. All six sim_execute_trade() calls moved
         inside their existing `if AUTOTRADE_ENABLED_X:` block, right
         alongside the execute_autotrade() call they used to sit next
         to unconditionally — same gate, same leverage, same signal.
         Updated the now-inaccurate "always runs regardless of toggles"
         comment (config docstring and the UI's own description text)
         to describe the corrected behavior instead of the old one.
         Verified directly: with a mode's autotrade toggle off, neither
         the autotrade log nor the simulator gets an entry; with it on,
         both fire together for the same signal.
v0.50.0 - added MFE/MAE-at-close tracking for scalp signals, the piece
         that made the earlier EMA/divergence RR retunes possible but
         scalp never had — user asked directly whether there was enough
         data to retune scalp's RR and the honest answer was no, so
         built the missing visibility first rather than guess.
         update_scalp_signal_outcomes() now tracks the best-favorable
         and worst-adverse price reached while a signal is open
         (mfe_price/mae_price), freezing them as R-multiples
         (mfe_r_at_close/mae_r_at_close, R = that signal's own sl_pct —
         scalp's SL varies per symbol/cycle unlike EMA/divergence's
         fixed global RR, so the R unit has to be per-signal too) at
         the exact moment the trade resolves — same "at close" semantics
         as Volume/EMA/divergence's existing panels. New
         compute_scalp_tuning_stats() aggregates this WIN/LOSS split
         (avg/median/p25/p75), exposed via /api/scalp/status's new
         tuning_stats field and a new MFE/MAE panel in the Скальпинг
         tab, styled the same as the Volume tuning panel it's modeled
         on. Verified with direct WIN and LOSS scenarios: MFE/MAE
         signs and magnitudes came out exactly as expected (a LOSS
         case's MAE landed at essentially -1.0R, precisely the SL
         definition; a WIN case's MFE exceeded the target's own R,
         confirming it captured the overshoot correctly). No retune
         yet — this is the prerequisite data, not the retune itself;
         next actual RR change should be grounded in this once enough
         closed scalp trades accumulate.
v0.50.1 - EMA's round-3 retune (TP=1.5%/SL=0.3%/RR=5.0) dropped the win
         rate to 35.5% (11W/20L) — still profitable on paper (breakeven
         ~16.7% at that RR) but the user wanted the round-2 stop back.
         First attempt reverted TP too (back to round 2's 1.0%); user
         corrected that they only wanted the stop touched, not the
         take. Fixed: TP stayed at round 3's 1.5%, and EMA_RR moved to
         3.75 (not round 2's 2.5) specifically so the DERIVED SL lands
         back at round 2's 0.4% while TP stays put — SL is computed as
         TP/RR here, so getting SL=0.4% with TP=1.5% needs RR=3.75, not
         RR=2.5 (which would have given a barely-different TP=1.5% but
         SL=0.6%, not what was actually asked for). Verified directly:
         TP computes to exactly 1.5% and SL to exactly 0.4% in both
         directions, and the full scan-function/endpoint regression
         stayed clean.
v0.51.0 - entry marker dot on all four chart types (VP, divergence,
         EMA, session) — the horizontal ENTRY line showed the price but
         gave no way to tell WHICH candle was actually the entry.
         findCandleIndex() locates the candle closest to the signal's
         own entry timestamp (row.time for VP/divergence/EMA,
         sig.confirm_time for session — the confirming candle IS the
         entry candle there), drawEntryMarker() draws a small filled
         circle with a dark outline at that candle's (x, entry-price)
         position, reusing the same slot-width math each chart already
         computes for candle x-positions rather than recomputing it.
         Added both helpers once, next to drawLevelLine, and wired one
         call into each of the four chart functions right after their
         existing ENTRY/SL/TP lines. Verified: JS syntax clean, both
         new functions declared exactly once, and the full
         scan-function/endpoint regression stayed clean.
v0.51.1 - CRITICAL: user's live log showed two real EMA positions
         (ZBT_USDT SHORT, TAG_USDT LONG) opened with real money but
         with NO stop-loss/take-profit protection — both TP and SL
         price_orders calls failed with 400. Two root causes, both
         fixed:
         (1) gate_signed_request() only surfaced requests'
         generic "400 Client Error: Bad Request" text, discarding
         Gate's actual JSON error body (label/message) — meaning the
         real cause was invisible in the log, forcing a guess instead
         of a diagnosis. Now captures and includes the real response
         body in the raised error.
         (2) The likely actual cause: Gate's close-position order
         schema genuinely differs by account position mode. Single
         mode closes via size=0/close=true (what place_tp_sl_orders
         already sent); two-side (hedge/dual) mode instead requires
         auto_size ("close_long"/"close_short") + reduce_only=true, and
         doesn't use `close` at all — a request built for one mode gets
         rejected under the other. Added get_dual_mode() (cached,
         reads in_dual_mode from GET /futures/usdt/accounts) and
         branched place_tp_sl_orders()'s initial-order payload
         accordingly. If mode detection itself fails, falls back to
         single-mode (the more common default) with a logged warning
         rather than blocking the close order entirely.
         Verified directly: single-mode payload unchanged (close:true,
         no auto_size), dual-mode payload correctly uses auto_size
         (close_long for LONG, close_short for SHORT) + reduce_only
         with no close field, and the detection-failure path falls
         back gracefully without raising. Full scan-function/endpoint
         regression stayed clean.
         Told the user directly to manually verify/protect the two
         live unprotected positions on the exchange before relying on
         this fix — a code fix doesn't retroactively add stops to
         positions that already exist without them.
v0.51.2 - user reported open EMA signals, autotrade log, and simulator
         data disappearing on restart. EMA signal persistence itself
         checked out fine in isolation (verified with a direct
         save/reload round-trip of an OPEN signal) — but scalp_signals,
         session_signals, and autotrade_log were never in save_state()/
         load_state()'s whitelist at all, a real gap that predates this
         session's work (only signals/div_signals/ema_signals/overrides
         were ever covered, then sim_balance/settled sim_trades got
         added later without extending the other two). Added all three
         missing categories to both functions. Verified directly: an
         OPEN record in each of the four previously-gapped categories
         (ema/scalp/session signals, autotrade log) survives a full
         save-then-reload cycle with its status and fields intact.
         Full scan-function/endpoint regression stayed clean.
         Still NOT persisted, by design (documented when the simulator
         shipped): PENDING sim trades, since their live reference to a
         signal record can't survive a restart anyway — only SETTLED
         ones carry over.
v0.51.3 - CRITICAL: user's Gate.io API credentials weren't surviving a
         restart at all — four EMA autotrade attempts all failed with
         "Gate.io API credentials not configured" right after a
         restart, despite having entered and saved them before. Root
         cause: load_credentials() existed (reads CREDENTIALS_FILE,
         sets GATE_API_KEY/GATE_API_SECRET) and save_credentials()
         correctly wrote the file (chmod 600, verified working back
         when the credentials feature shipped) — but load_credentials()
         was never actually CALLED in __main__ at startup. save_state()/
         load_settings() were both wired in; this one call was simply
         missing, meaning every restart silently reset both credential
         globals to empty strings regardless of what was saved to disk.
         Added the missing load_credentials() call alongside the
         existing load_state()/load_settings() calls. Verified directly
         with a save -> simulated restart (fresh module load, matching
         what a real process restart does) -> load_credentials() cycle:
         both GATE_API_KEY and GATE_API_SECRET come back exactly as
         saved, and GET /api/credentials correctly reports configured=
         true afterward. Full scan-function/endpoint regression stayed
         clean.
v0.51.4 - v0.51.1's error-body-capture fix immediately paid off: user's
         next TP/SL failure showed the REAL cause instead of a generic
         400 — Gate rejected both trigger prices with
         AUTO_INVALID_PARAM_TRIGGER_PRICE: "price is not an integer
         multiple of a price unit". Root cause: computed TP/SL prices
         were sent with whatever floating-point precision the math
         happened to produce, never rounded to the contract's actual
         tick size — Gate requires every order/trigger price to be an
         exact multiple of it. Added order_price_round to
         get_contract_spec() (the tick size field, confirmed from
         Gate's own docs) and round_to_tick() (snaps to the nearest
         exact multiple, falls back to the raw price unchanged if the
         tick size is missing rather than guessing). execute_autotrade()
         now rounds both TP and SL to the contract's tick size right
         before calling place_tp_sl_orders(), and logs the rounded
         values on the record for visibility. Verified end-to-end with
         a simulated Gate that rejects non-tick-aligned prices exactly
         like the real error: the same TP/SL values that would have
         been rejected unrounded now place successfully after rounding
         (0.0468912345 -> 0.0469 at a 0.0001 tick). Full scan-function/
         endpoint regression stayed clean.
v0.52.0 - added position/order reconciliation, per direct request:
         catch unprotected positions and clean up orphaned trigger
         orders, checked at the moment a new real trade opens rather
         than on a separate timer (avoids adding another periodic
         API-polling loop, and avoids spamming — piggybacks on however
         often trades actually happen).
         reconcile_positions_and_orders() fetches live positions
         (GET /futures/usdt/positions) and live open trigger orders
         (GET /futures/usdt/price_orders?status=open) ONCE and reuses
         that single fetch for both checks:
         (1) a position with no attached trigger order at all — exactly
         the OPENED_TP_SL_FAILED scenario from two fixes ago — gets a
         Telegram alert, deduped via a small in-memory set so the same
         still-unprotected contract doesn't re-alert on every
         subsequent trade; the set self-clears once that contract is
         protected again, so a genuinely new recurrence still alerts.
         (2) a trigger order whose position has ALREADY closed — Gate
         has no native OCO, so when TP fires and closes a position, the
         paired SL order (or vice versa) just sits there as a live
         trigger with nothing left to close, and would fire against
         whatever NEW position later opens on that same contract if
         left alone — gets cancelled outright via DELETE
         /futures/usdt/price_orders/{id}.
         Wired into execute_autotrade() right before a REAL trade opens
         (after the dry-run check, so this never touches dry-run or
         costs it any network calls — reverified that property still
         holds, zero calls in dry-run). Verified the full scenario
         directly: an unprotected position alerts once and stays
         silent on repeat calls while still unprotected, an orphaned
         trigger gets cancelled, protecting the position clears it from
         the alerted set, and a later genuine recurrence alerts again.
         Full scan-function/endpoint regression stayed clean.
v0.52.1 - user's live log showed two more real failures: LEVERAGE_
         EXCEEDED ("limit [1, 10]") on ZEST_USDT and Q_USDT — both
         capped at 10x on Gate, while the EMA mode was configured for
         15x. get_contract_spec() already fetched leverage_max for
         exactly this reason but nothing actually used it to constrain
         the requested leverage before calling set_leverage() — it was
         sent as configured, unconditionally, regardless of what the
         specific contract allows.
         Fixed by clamping leverage to the contract's leverage_max
         BEFORE compute_position_size() runs (not after) — sizing has
         to use the leverage that will actually be applied, or the
         resulting margin/notional relationship would be wrong once
         Gate enforces the real cap. When a clamp happens, the
         originally-requested value is kept in the log under
         extra.leverage_requested and record["leverage"] reflects what
         was actually used, so it's visible after the fact without
         being a scary top-level field. Verified directly: a contract
         capped at 10x correctly opens at 10x (with 15 logged as the
         requested value) instead of erroring, a contract with plenty
         of headroom (50x max, 15x requested) is completely unaffected,
         and dry-run still makes zero network calls. Full scan-function/
         endpoint regression stayed clean.
v0.52.2 - first scalp SL retune, off the MFE/MAE tracking added in
         v0.50.0 (n=8: 7W/1L — a genuinely small sample, flagged as
         such before touching anything). WIN MAE stayed well clear of
         the stop (p75 -0.127R, nowhere near -1.0) while the single
         LOSS's MAE landed at -1.103R, roughly where the stop already
         sits. Given the small n and — critically — only one loss ever
         (not enough to know the true distribution of adverse moves,
         unlike the win side which had 7 data points), tightened
         SCALP_SL_BUFFER_MULT modestly: 0.2 -> 0.05, not all the way to
         0 or as far as the win-side data alone might suggest. For a
         real example from the live data (RATS_USDT), this moves the
         SL from ~7.516% to ~6.577% — a real but measured step.
         Verified the resulting SL% computes correctly for that exact
         case, and the full scan-function/endpoint regression stayed
         clean.
v0.52.3 - user reported overnight scalp trades looked like they had no
         SL/TP at all — lucky the price moved the right way. Checked
         the actual gating logic first (sim_execute_trade calls are
         still correctly nested inside each mode's `if AUTOTRADE_
         ENABLED_X:` block, confirmed by direct inspection — the
         v0.49.1 toggle-mirroring fix is intact, not a regression).
         The real gap: the Симулятор tab never showed the per-mode
         enabled toggles at all (so there was no way to see AT A
         GLANCE whether scalp was even supposed to be trading), and
         the trade table had no SL/TP columns — entry/sl/tp were
         already stored on every sim trade record and returned by
         /api/simulator/trades, just never rendered, so a trade with a
         real stop and target LOOKED like it had neither.
         Added both: a "Режимы: ..." status line (reusing /api/
         autotrade/status's existing enabled field, same style as the
         Автоторговля tab) and Entry/SL/TP columns to the trade table.
         Learned from the exact mistake in v0.48.1 (an insertion that
         silently ate a function declaration): checked refreshSimulator
         and refreshAll both still have exactly one declaration each
         via grep before moving on, and ran node --check immediately.
         Verified directly that sl/tp fields are present and correctly
         populated in a real /api/simulator/trades response. Full
         scan-function/endpoint regression stayed clean.
v0.52.4 - user's live autotrade log showed a repeating pattern:
         INSUFFICIENT_AVAILABLE errors for Breakout, "margin 10.03...
         while available 1.09695" — same ~$10 fixed margin attempted
         over and over as available balance kept shrinking (25 open
         positions already consuming margin). Root cause: fixed-$
         sizing mode had NO relationship to actual account balance at
         all — unlike percent mode, which naturally scales with
         wallet_balance, fixed mode just used the configured $ value
         directly and let Gate reject it after the fact, every single
         time, with no way to know in advance.
         compute_position_size() now checks margin against actual
         wallet_balance regardless of sizing mode, skipping cleanly
         (SKIPPED, not a wasted API round-trip that fails) when the
         computed margin exceeds what's actually free. This required
         also fetching wallet_balance in the real (non-dry-run) path
         for BOTH modes, not just percent — previously fixed mode never
         fetched it at all since the sizing math didn't need it.
         Verified directly: the exact reported scenario ($10 margin,
         $1.10 available) now skips with zero order-placement API calls
         instead of hitting the exchange and failing; a normal
         sufficient-balance case still opens correctly in both fixed
         and percent mode; dry-run with fixed mode and no credentials
         still makes zero network calls. Full scan-function/endpoint
         regression stayed clean.
v0.53.0 - Volume winrate analysis (31.9%, below the RR=2 breakeven of
         33.3%) turned up a clear pattern comparing at-close vs full-
         window (24h) stats: LOSS full-window MFE averaged 2.737R —
         past the TP itself — vs only 0.343-0.461R at the moment the
         tight stop actually closed the trade. A large share of
         "losses" appear to reverse in the intended direction anyway;
         the stop just doesn't survive the noise long enough. WIN full-
         window MFE similarly ran to 5.425R (median 3.94R) vs the
         ~2R the current TP captures.
         Unlike EMA/divergence's single global TP%/RR, Volume's TP/SL
         come from a per-symbol auto-tuned grid (PARAM_GRID_BUFFER,
         PARAM_GRID_RR), so there's no one fixed value to change —
         widened the grids instead (buffer 0.20/0.35/0.50 -> +0.65,
         RR 1.5/2.0/2.5 -> +3.0) so the per-symbol auto-tuner can
         select the wider options where they backtest better, rather
         than forcing everyone to the same new value. Recommended the
         user clear Volume's accumulated per-symbol overrides so the
         new grid gets explored promptly instead of waiting for the
         normal 48h-per-symbol refresh cycle to reach everyone.
         Verified: new grid values load correctly, and the full
         scan-function/endpoint regression stayed clean (a test-harness
         call to backtest_params with an incomplete arg list raised as
         expected — a test mistake, not an application bug, confirmed
         by every other check passing).
v0.53.1 - proactive bug audit of the auto-trade path (per direct
         request), reviewing execute_autotrade/compute_position_size/
         reconcile_positions_and_orders end to end rather than waiting
         for the next live failure. Found and fixed two real issues:
         (1) get_dual_mode()'s cache mutated a shared dict with no
         lock at all, unlike get_contract_spec()'s identical caching
         pattern which does use one — under concurrent scan threads,
         multiple could see a stale cache simultaneously and each fire
         a redundant GET /accounts call. Added the missing lock;
         verified with 10 concurrent threads hitting it at once that
         exactly one real fetch happens, all ten get the same
         (correct) cached result.
         (2) compute_position_size()'s balance-sufficiency check (added
         last version) compared margin against the exact available
         figure with zero headroom — a margin sitting right at the
         boundary could still get rejected by Gate's own fee/margin-
         rate buffer on the real order. Added a 2% safety margin.
         Verified: 99%-of-balance margin now correctly skips, 97%
         still passes through unaffected.
         Reviewed but left alone: order `size` gets sent as a float
         (e.g. "495.0" — visible in the user's own logs) rather than a
         clean int; real evidence (OPENED, not ERROR, in that same log)
         shows Gate accepts it fine, so changed nothing rather than
         risk touching working real-money code without a concrete
         failure to fix. Also noted as a latent (not yet hit) limit:
         get_open_positions()/get_open_price_orders() don't paginate,
         so an account with more open positions/orders than Gate's
         default page size would have some silently missed by
         reconcile — well beyond the ~25 positions currently in use,
         not touched this round.
         Full scan-function/endpoint regression and the dry-run
         zero-network-call property both stayed clean throughout.
v0.53.2 - network-loss resilience audit, per direct request (this runs
         on mobile Termux, so flaky/dropped connectivity is a real
         scenario, not an edge case). Checked systematically:
         scan_loop's whole iteration is wrapped in try/except with a
         minimum-5s sleep before retrying — a network failure logs and
         backs off rather than hot-looping or crashing the thread.
         Every requests.get/post/request call in the file (confirmed
         by grep, including multi-line calls a naive search missed at
         first) has an explicit timeout — no call can hang forever on
         a half-dead connection. _telegram_sender_worker catches per-
         task exceptions individually so one failed send never kills
         the worker thread, and send_telegram's own retry loop (3
         attempts with backoff) is already in place. STATE["errors"]
         is bounded (maxlen=30) so a long outage can't grow it
         unbounded. The browser-side fetch() calls talk to 127.0.0.1
         only (the local Flask server, not an external host) — losing
         the device's actual internet connection doesn't affect those
         at all, and setInterval(refreshAll, 15000) doesn't depend on
         the previous tick succeeding, so the UI polling loop is
         inherently self-recovering regardless.
         Found and fixed one real gap: the Telegram send queue was
         unbounded, and used a blocking put() — during a long enough
         outage with signals still firing, it could in theory grow
         without limit, and if it ever did fill, put() would block
         WHATEVER thread called send_telegram (e.g. a scan worker),
         which is worse than dropping a message. Bounded it to 200 and
         switched to put_nowait() with a caught queue.Full that logs
         and drops rather than blocks. Verified directly: filling the
         queue to capacity and calling send_telegram again returns
         near-instantly (not blocked) and logs the drop; a normal send
         below capacity still queues exactly as before. Full scan-
         function/endpoint regression stayed clean.
v0.54.0 - removed the scalp timeout entirely, per direct request:
         KOMA_USDT kept expiring into TIMEOUT (4 of 5 recent signals)
         at the old 4x-median-time cutoff (~79 min) without ever
         reaching its target or stop — a low-volatility grinder that
         just needs longer to resolve either way. User wanted a real
         WIN/LOSS outcome no matter how long it takes rather than an
         ambiguous TIMEOUT.
         timeout_sec is now 10**12 seconds (~31,700 years) instead of
         rec["time_to_hit_hours"] * SCALP_SIGNAL_TIMEOUT_MULT — a very
         large FINITE number rather than float('inf'), specifically
         because inf serializes as the non-standard JSON token
         'Infinity'; scalp_signals get persisted to disk via
         save_state() (since v0.51.2), and a plain huge number is safe
         there without relying on Python's json module happening to
         accept a non-standard token forever. The existing "now >=
         timeout_at" check in update_scalp_signal_outcomes() needed no
         change — it simply can never become true now, no second code
         path added.
         Verified directly: a signal survives ~41 hours of flat price
         action (far past the old ~79min cutoff) still OPEN, then
         correctly resolves to WIN once price actually reaches the
         target; the huge timeout_at value round-trips through JSON
         serialization correctly with no 'Infinity' token anywhere.
         Full scan-function/endpoint regression stayed clean.

v0.55.0 - new "flat zone" filter for the Сессия consolidation range, per
         user's annotated chart screenshot: the range immediately
         before the session open should be a genuine sideways
         consolidation, not just the tail end of a directional move
         that happens to satisfy SESSION_MIN_RANGE_PCT. The old check
         only rejected ranges that were too SMALL — it said nothing
         about whether the range was still trending in one direction.
         Added SESSION_MAX_TREND_RATIO (default 0.5): computes the
         range's net directional drift (abs(last close - first open))
         as a fraction of the range's total height (range_high -
         range_low). A clean sideways chop has a small net drift
         relative to its swing (price goes back and forth without
         going anywhere); a directional move has net drift close to
         the full range height (most of the swing was in one
         direction). Reject (return None) if trend_ratio exceeds the
         threshold. Applied in detect_session_manipulation() right
         after the existing range_pct/SESSION_MIN_RANGE_PCT check, so
         a session is now skipped if the pre-open range is either too
         small OR too directional. Threshold picked as a reasonable
         starting point, not yet backtested against history — flagged
         to retune once there's live/backtest data showing how it
         performs.

v0.56.0 - fixed a real autotrade bug reported by user (screenshots of
         autotrade_log): scalp signals on RATS_USDT were opening a
         position (OPENED_TP_SL_FAILED) with BOTH the TP and SL
         price_orders rejected by Gate as code 1009,
         AUTO_INVALID_PARAM_TRIGGER_PRICE. Root cause: place_tp_sl_
         orders() sent trigger.price as str(price) — Python's str()/
         repr() switches small floats to scientific notation (e.g.
         str(0.0000034) == '3.4e-06'), which Gate's API doesn't accept
         for trigger.price. Only showed up on cheap/meme contracts
         (RATS_USDT's price sits well below 1e-4); ordinary-priced
         symbols never hit this. New format_price_str(price, tick_size)
         always renders a plain fixed-point decimal string, with
         decimals derived from the contract's own tick_size (via
         Decimal, not float log10, to avoid a rounding-hair-off decimal
         count) — falls back to 10 decimals if tick_size is missing.
         place_tp_sl_orders() now takes a `tick` param and uses this
         for both trigger prices instead of str(); execute_autotrade()
         passes through the tick it already fetches for round_to_tick().
         Also noticed while making this change: v0.55.0's flat-zone
         session filter shipped without bumping APP_VERSION (stayed at
         0.54.0) — corrected here, no functional relation to this fix.

v0.57.0 - per direct user request, off the bounce/breakout stats screenshot
         (bounce 1W/5L ~16.7% vs breakout 5W/4L ~56%):
         (1) BOUNCE_ENABLED now defaults to "0" (was "1") — bounce
         signals disabled by default. Module code kept intact (toggle
         only, not ripped out) so it can be re-enabled for comparison
         later.
         (2) VOL_CONFIRM_RATIO default raised 1.15x -> 1.4x — the
         existing volume-confirmation filter (already active on both
         bounce and breakout via _try_signal/volume_confirms) was too
         weak to reliably separate a real breakout's volume spike from
         ordinary noise.
         (3) New breakeven stop-move for breakout signals only, via
         BREAKOUT_BREAKEVEN_TRIGGER_R (default 0.8R) and
         BREAKOUT_BREAKEVEN_BUFFER_PCT (default 0.1%). Motivated by the
         same screenshot: breakout LOSS MFE showed p75=1.224R, meaning
         a quarter of losses had traveled over 1R in favor before
         reversing to hit the original stop — pure wasted edge. Once an
         OPEN breakout signal with a real (non-dry-run) SL order on
         Gate reaches fav_r >= BREAKOUT_BREAKEVEN_TRIGGER_R,
         move_stop_to_breakeven() cancels that SL order and places a
         new one at entry (+/- the small buffer) — implemented via a
         new shared place_close_trigger_order() helper (place_tp_sl_
         orders() refactored to use it too, no behavior change there).
         Only ever attempted once per signal (breakeven_moved flag),
         success or failure, to avoid hammering the API every cycle on
         a persistent error. A close against a successfully-moved
         breakeven stop is labeled result="BREAKEVEN" rather than
         "LOSS" (tracked via a separate breakeven_active flag, true
         only on confirmed success) — mirrors how "TIMEOUT" already
         sits outside the WIN/LOSS stats buckets, so this doesn't
         require touching win/loss aggregation elsewhere. sim_execute_
         trade's paper-trading PnL needed no change: it already prices
         off the real exit_price, not an assumed result label, so a
         breakeven exit naturally nets to ~0 PnL (minus fees) on its
         own.
         Not yet backtested — this changes LIVE order management, not
         just signal-generation math, so it can only really be
         validated by watching real trade outcomes going forward.

v0.58.0 - new signal-staleness filter for the Volume module (bounce/
         breakout), per direct user observation (screenshot): a signal
         showed 14:00 as its candle time while the scan that surfaced
         it ran at 14:08 — an 8-minute-old candle by the time it was
         even seen, on top of however long the actual order placement
         then took. A full universe scan takes several minutes (429s
         observed for 182 symbols), so a symbol near the end of the
         scan queue can pick up a signal whose candle closed well
         before the scan actually reached it. Entry/SL/TP are computed
         off that candle's close, but the real market order fills at
         whatever price exists NOW — too much elapsed time means price
         has likely already moved past where the signal detected it,
         so the trade would enter late into an already-spent move
         instead of near its start.
         New SIGNAL_MAX_STALENESS_SEC (default 300s / 5 min): right
         after a candidate signal passes the existing trend/volume/OI
         filters, if time.time() - sig["time"] exceeds this, the signal
         is dropped (same pattern as the other filters — a new
         filtered_by_staleness counter, reset alongside filtered_by_
         trend/volume/oi in all three existing reset sites, exposed in
         the same API response and the same "отклонено" line in the
         UI). Applies to both bounce and breakout paths (bounce is
         disabled by default anyway per v0.57.0, but the check sits
         before that branch either way, so it's ready if bounce ever
         gets re-enabled for comparison).
         5 min is a starting default at ~1/3 of the 15m candle
         interval — not yet tuned against how much it costs in missed
         entries vs. how much bad-entry risk it actually removes;
         adjustable via VP_SIGNAL_MAX_STALENESS_SEC without a code
         change if it turns out too tight or too loose.

v0.58.1 - SIGNAL_MAX_STALENESS_SEC tightened 300s -> 60s, per direct
         user request (5 min still felt too loose). Worth flagging:
         at 60s, a symbol only fires a signal if the scan happens to
         reach it within a minute of its candle closing — with a full
         182-symbol scan cycle taking ~429s observed, that's a fairly
         narrow window relative to the whole cycle, meaning a real
         chunk of otherwise-valid signals may now get rejected purely
         on scan-queue timing (which symbol happens to be scanned
         when) rather than on the signal itself being stale. Left as
         requested since the user was explicit about wanting it
         tighter, not asking for an analysis — but this is the
         tradeoff worth watching via the new filtered_by_staleness
         counter (v0.58.0) going forward: if it's rejecting most
         breakout candidates rather than an occasional stale one, that
         signals the scan cycle itself is too slow for a 60s window
         and either the interval, worker count, or universe size may
         need attention rather than this threshold alone.

v0.59.0 - major scan-cycle speedup, per direct user question ("why so
         slow, isn't it just loading one new candle?"). It wasn't one
         candle: every update_*_outcomes() function (signal/divergence/
         ema/scalp/session) was calling get_candles() inside a plain
         `for sig in active:` loop — one blocking network request per
         active signal, fully sequential, fetching 200-300 candles
         each time. With MFE tracking running 24h past close on top of
         whatever's still OPEN across five modules, that list adds up
         fast, and this ran with ZERO concurrency, unlike the main
         per-symbol scan (which already uses a WORKERS-sized thread
         pool). This was very likely the single biggest chunk of the
         reported ~429s cycle time — bigger than the main scan itself.
         New fetch_candles_concurrent(fetch_specs, workers=WORKERS):
         takes a list of (symbol, interval, limit) specs, fetches all
         of them in a thread pool, returns results in the same order
         (a failed fetch yields None at that position, logged, rather
         than raising and losing the whole batch). All five update_*_
         outcomes() functions now build their fetch_specs list, call
         this once up front, then zip(active, all_candles) into the
         same per-signal processing loop they already had — no change
         to the actual outcome/MFE/breakeven logic itself, purely
         collapsing N sequential requests into ceil(N/WORKERS)
         concurrent batches.
         Each function creates and closes its own ThreadPoolExecutor
         via this helper; no conflict with the main scan's pool since
         that `with ThreadPoolExecutor(...) as ex:` block has already
         exited (its results collected via as_completed) by the time
         these run, per scan_loop()'s existing sequencing.

v0.60.0 - deduped candle fetches across Divergence and EMA, per direct
         user request after v0.59.0 got the cycle down to 268s and they
         asked to keep going. Both modules default to the same interval
         (DIV_INTERVAL == EMA_INTERVAL == "1h"), so every symbol was
         being fetched twice for identical candles. scan_loop() now
         builds a shared_interval_limits dict (interval -> the largest
         limit any enabled module needs at that interval) before the
         main scan pool starts, fetches every (symbol, interval) pair
         in that set ONCE via the existing fetch_candles_concurrent(),
         and hands the result to scan_symbol_divergence()/scan_symbol_
         ema() — both now take an optional `candles` param and only
         fetch their own if it's missing (backward compatible; no other
         caller passes it, so nothing else changes behavior).
         Volume (scan_symbol()) deliberately stays out of this dedup:
         its interval (15m default) differs from Divergence/EMA's, and
         its per-symbol lookback can vary via SYMBOL_OVERRIDES (auto-
         tune) — a shared fixed-limit cache wouldn't reliably cover a
         tuned symbol. scan_symbol() takes an optional `candles` too,
         but only accepts a passed-in list if it's already long enough
         for that specific symbol's tuned lookback; otherwise it falls
         back to its own fetch — a length check, not a behavior change,
         so a tuned symbol never silently gets truncated history.
         Full lazy/incremental candle loading (fetching only the newest
         bar instead of the whole lookback window every cycle) was
         discussed and deliberately NOT done here — user flagged it
         as the next lever but wanted it separate, correctly expecting
         it's more invasive (needs a persistent per-symbol candle store,
         gap handling, in-progress-candle handling) and more likely to
         introduce subtle bugs than this dedup was.

v0.61.0 - fixed the scalp recommendation score to be EV-based, per direct
         user question about why KOMA_USDT outranked AKE_USDT despite
         AKE's clearly better hit-rate (85% vs 75.4%). Root cause:
         score was hit_rate * trades_per_day_est — literally just an
         estimate of wins/day, completely blind to how big a loss
         costs. KOMA fires more often (57.6 trades/day vs AKE's 48),
         which was enough to out-score AKE on pure frequency despite
         AKE's better hit-rate.
         New: sl_pct_est = p90_adverse_pct * (1 + SCALP_SL_BUFFER_MULT)
         — mirrors the REAL stop scan_symbol_scalp_signal() actually
         places, not liq_buffer_pct (a separate, unrelated liquidation-
         distance safety check that was never the right basis for this
         and wasn't used in the old score either — worth naming since
         an earlier draft of this same fix used liq_buffer_pct by
         mistake before catching it against the real SL logic).
         ev_per_trade_pct = hit_frac*target_pct - (1-hit_frac)*sl_pct_est
         score = ev_per_trade_pct * trades_per_day_est — now an actual
         (rough) expected-return-per-day estimate, not just a win-count
         proxy. Both sl_pct_est and ev_per_trade_pct are now stored on
         the candidate dict alongside the existing fields (liq_buffer_
         pct/p90_adverse_pct untouched, still there for their original
         leverage/liquidation-safety purpose).
         Recalculated against the screenshot: KOMA's EV/trade ≈ 0.82%
         (score ≈47.3) vs AKE's ≈1.86% (score ≈89.3) — AKE now clearly
         outranks KOMA, matching what the raw hit-rate gap actually
         implies.
         Note: score can now legitimately come out negative for a
         symbol whose only qualifying combo has bad EV (wide stop,
         marginal hit-rate) — no code elsewhere assumed score >= 0
         (checked: only used for -score sorting and storage), so this
         doesn't break anything, and correctly demotes those symbols
         to the bottom of the ranking instead of hiding the problem.

v0.62.0 - EMA diagnostics-only logging, per direct user request to
         understand the module's low win rate (30%, 6W/14L) before
         touching any filter or the fixed-%-based SL. Existing filters:
         EMA_TREND_FILTER (only trade with EMA28) and signal_type=
         "combined" (the strictest of the three signal definitions)
         were already active — what was missing was any per-signal
         context to tell WHY a given signal won or lost.
         Four new fields attached at signal-detection time, none of
         which affect whether a signal fires or its TP/SL — purely
         informational:
         - atr_pct: ATR(14) as % of price (new _true_range_series() +
           _atr_series() — proper Wilder smoothing, not compute_ema()
           reused with a different period). Tests the hypothesis that
           losses cluster on high-volatility bars where the fixed 0.4%
           SL is simply too tight for that coin's actual noise.
         - ema_slope_pct: EMA28's slope over the last
           EMA_DIAG_SLOPE_LOOKBACK (5) bars, SIGNED so positive always
           means "moving with this trade's direction" regardless of
           LONG/SHORT — lets win/loss aggregation compare both
           directions on one scale. Tests whether losses happen more in
           a flat/undecided EMA28 vs a clearly trending one.
         - ema_gap_pct: (EMA7-EMA14)/price at signal time — how
           decisive vs marginal the cross was.
         - recent_crossover_count: EMA7/EMA14 crossovers in the last
           EMA_DIAG_CHOP_LOOKBACK (20) bars — a whipsaw/chop proxy;
           classic failure mode for crossover systems is a ranging
           market chopping out one signal after another.
         All four also added to compute_ema_stats()'s win/loss
         breakdown (same agg() pattern as the existing mfe_r/mae_r
         stats), so /api/ema/status now shows win vs loss avg/median/
         p25/p75 for each — actual evidence to decide between an
         ATR-based stop and/or an anti-chop filter next, instead of
         guessing (matches how the two earlier SL/RR retunes for this
         module were done blind, per EMA_RR's own comment history).
         detect_ema_signal() gained an optional `candles` param (for
         ATR); its only caller (scan_symbol_ema) already had candles in
         hand, so no extra fetch needed. Backward compatible — omitting
         candles just leaves atr_pct None.

v0.62.1 - SIGNAL_MAX_STALENESS_SEC raised 60s -> 180s (3 min), per
         direct user request — 60s turned out too tight (flagged as a
         risk back in v0.58.1's own changelog note). 5min -> 60s ->
         180s across three rounds now; still adjustable via
         VP_SIGNAL_MAX_STALENESS_SEC without a code change.

v0.63.0 - scalp gets its own position-size config, per direct user
         request ("as everywhere else, by analogy"). Previously every
         mode (bounce/breakout/divergence/ema/session/scalp) shared ONE
         global AUTOTRADE_SIZE_MODE/AUTOTRADE_SIZE_VALUE — unlike
         leverage, which already has a separate per-mode constant for
         every mode except scalp (scalp computes its own leverage per
         signal, so it never needed AUTOTRADE_LEVERAGE_SCALP). Size had
         no equivalent split for scalp until now.
         New SCALP_SIZE_MODE / SCALP_SIZE_VALUE (env VP_SCALP_SIZE_MODE
         / VP_SCALP_SIZE_VALUE), defaulting to whatever AUTOTRADE_SIZE_
         MODE/VALUE resolve to at import time — an existing setup's
         scalp sizing doesn't silently change until the user actually
         customizes it via settings.
         execute_autotrade() and sim_execute_trade() both gained
         optional size_mode/size_value params, defaulting to the shared
         AUTOTRADE_SIZE_MODE/VALUE when omitted (every other mode's
         call site is unchanged, still passes nothing here) — only
         scalp's call site passes SCALP_SIZE_MODE/VALUE explicitly, for
         both the real order and its paper-trading counterpart, so the
         simulator's scalp stats stay honest against what real scalp
         trades would actually size.
         Wired through get_settings()/apply_settings()/SETTINGS_KEYS
         (persisted to disk like every other setting) and a new
         "↳ Сумма скальпинга" row in the settings UI, right under the
         scalp autotrade toggle — same percent-of-balance/fixed-$
         dropdown+input as the shared control above it. Also surfaced
         in /api/scalp/status's config block for visibility.

v0.64.0 - fixed a real gap reported by user (screenshots: 13 open orders
         on one symbol in Gate's UI, plus the autotrade log directly
         showing it — EMA opened MMT_USDT SHORT at 17:03, Breakout
         opened MMT_USDT LONG at 17:46, completely independently).
         Each module (Volume/Divergence/EMA/Scalp/Session) only ever
         checked its OWN signal list before firing — has_open_signal(),
         has_open_divergence_signal(), has_open_ema_signal(), and two
         inline checks for scalp/session. Nothing stopped a SECOND
         module from opening a position on a symbol another module
         already held, each placing its own independent market order +
         TP + SL. Across five modules scanning the same universe, a
         popular/volatile symbol accumulates a pile of uncoordinated
         orders — and it wasn't visible in any single module's own log,
         because no module's log ever saw the whole picture.
         New has_open_signal_any_module(symbol, exclude=None): checks
         all five signal lists (STATE["signals"]/div_signals/ema_signals/
         scalp_signals/session_signals) for an OPEN entry on this
         symbol. Called in ADDITION to each module's own existing check,
         everywhere a new signal gets created — it's a cross-module
         veto layered on top, not a replacement for any module's
         existing per-symbol/interval dedup.
         exclude lets a module skip checking its OWN list here, since
         it already checked that separately (and EMA's own check is
         interval-aware — it deliberately allows several simultaneously-
         open EMA signals on the same symbol across DIFFERENT intervals
         for comparison, which excluding ema_signals here preserves;
         without the exclude, EMA would have started vetoing its own
         multi-interval feature).
         Session never had its own per-symbol open check at all before
         this (only a per-session_open_ts cooldown) — this fix is the
         first thing that stops it opening on a symbol another module
         already holds.
         state_lock is a plain, non-reentrant threading.Lock() — the
         scalp call site had its own dedup check inside a `with
         state_lock:` block already, so has_open_signal_any_module()
         (which takes the lock itself) had to be called AFTER that
         block exits, not nested inside it, or it would deadlock.
         Verified none of the other four call sites were nested inside
         a state_lock block either before adding the call there.
         Does NOT retroactively touch any already-open duplicate
         positions/orders (like the ones on SNDK_USDT in the report) —
         only prevents new ones going forward. Existing pileups need a
         manual check on Gate; the bot has no reliable way to guess
         which of several already-open positions on one symbol was the
         "intended" one to keep.

v0.65.0 - ATR-based SL for EMA, per direct user request, motivated by
         hard evidence from the module's own MFE/MAE-at-close numbers:
         WIN MFE at close averaged 7.17R against a nominal RR of 3.75,
         and LOSS MAE at close averaged 2.187R against a nominal 1R —
         both roughly double their nominal level, meaning a single 1h
         candle routinely blew through the fixed 0.4% SL and 1.5% TP by
         a wide margin. Not noise: the stop was simply sized far too
         tight for what a 1h candle on these symbols actually moves,
         and a fixed % can't adapt per-symbol where ATR can.
         New EMA_SL_MODE ("atr" default, or "fixed_pct" to reproduce
         the exact old behavior) and EMA_SL_ATR_MULT (default 1.5).
         compute_ema_tp_sl() rewritten: TP stays a fixed % of entry
         (EMA_TP_PCT, unchanged) but SL = ATR(EMA_DIAG_ATR_PERIOD, i.e.
         the same ATR the v0.62.0 diagnostics already computed) *
         EMA_SL_ATR_MULT, falling back to the old EMA_RR-derived SL
         when ATR is unavailable for that signal (or EMA_SL_MODE is
         "fixed_pct"). The ATR value used is the exact same atr_pct
         already computed by _ema_signal_diagnostics() at signal-
         detection time (converted back to price units) — no separate
         calculation, no chance of the two disagreeing.
         Consequence flagged by the user before implementing: RR is no
         longer one constant (it depended on a fixed SL), it now varies
         signal to signal — a volatile symbol gets a wider ATR-based
         stop and therefore a lower per-trade RR than a calm one, for
         the same fixed TP %. So:
         - compute_ema_tp_sl() now returns (sl, tp, risk, rr) instead of
           (sl, tp, risk) — rr computed FROM the actual resulting
           distances, not assumed.
         - Every EMA signal record now carries its own "rr" field.
         - compute_ema_stats() gained rr_all/rr_wins/rr_losses
           (avg/median/p25/p75, same agg() pattern as everything else).
         - The EMA panel header (previously "RR ${cfg.rr}", one fixed
           number) now shows "RR ср. X (медиана Y)" from rr_all, plus
           "SL: ATR×1.5" (or "фикс. RR N" in fixed_pct mode) so it's
           clear at a glance which mode is active.
         - New RR column in the EMA signals table, showing each
           individual trade's actual RR rather than implying one
           constant applied to all of them.
         - /api/ema/status's config block: "rr" replaced with
           "sl_mode"/"sl_atr_mult"/"rr_fallback" (renamed from the old
           "rr" key, now clearly labeled as the fallback, not the
           active value).
         Old signals created before this change have no "rr" key at
         all — every read site uses .get()/None-checks, never bare
         indexing, so they render as "-" in the table and are simply
         excluded from the new rr_* aggregates rather than erroring.

v0.66.0 - fixed a real sign bug in the divergence pivot-confirmation-
         delay stat, caught by direct user question: they run with
         DIV_INVERT_SIGNALS on, and asked whether the "вход раньше в
         среднем на +X% лучше" figure accounted for that. It didn't.
         simulate_pivot_stability()'s gain sign convention assumes the
         NATURAL trade direction per pivot kind (SHORT on a high/
         bearish pivot, LONG on a low/bullish one — see its own
         docstring). With DIV_INVERT_SIGNALS on, every live divergence
         trade goes the OPPOSITE direction, so "earlier entry is
         better" should flip to "earlier entry is worse" by the same
         magnitude — the stat was silently reporting the gain for a
         direction that was never actually being traded.
         Fixed in the periodic stability cycle (not inside
         simulate_pivot_stability() itself, which stays a neutral,
         direction-agnostic measurement): gains are now negated when
         DIV_INVERT_SIGNALS is on, before accumulating into gain_sum/
         gain_count. UI text also fixed to say "лучше"/"хуже" based on
         the actual sign instead of always appending "лучше" with a
         raw +/- number (which read oddly negative, e.g. "-0.822%
         лучше"), and the panel's caption now notes when the figure
         already accounts for reverse mode.
         STATE["div_pivot_stability"] reset on this deploy — the
         running gain_sum accumulated under the OLD (wrong-for-
         reversed-mode) sign convention for as long as reverse mode has
         been on, so old and newly-correct-signed data would otherwise
         mix in the same running average until enough new data diluted
         it out. Starting clean avoids that transition period being
         misleading.

v0.67.0 - fixed a real bug reported by user ("simulator doesn't remember
         trades after restart"): save_state() only ever persisted
         SETTLED paper trades — any still-PENDING (open) sim trade was
         silently dropped on every restart, because it held a live
         Python object reference (_signal_ref) to its originating
         signal, which obviously can't survive a process restart. That
         wasn't just a display gap: the trade's margin/fee had already
         been deducted from sim_balance at open, but its eventual real
         PnL (win, loss, or timeout) could now never be credited back,
         since the trade record itself was gone and could never
         resolve. Effectively silent money loss from the paper balance
         on every restart, worse the more frequently the app restarts
         relative to how long trades take to resolve.
         Fix: save_state() now persists ALL sim trades (PENDING and
         SETTLED), still stripping _signal_ref (a raw object reference
         can't serialize meaningfully). New _relink_sim_trade(trade) in
         load_state(): for each restored PENDING trade, searches the
         matching module's just-reloaded signal list (bounce/breakout →
         STATE["signals"], divergence → div_signals, etc.) for an OPEN
         signal with the same symbol+direction and detected_at within
         10s of the trade's own creation time — sim trades are created
         moments after their signal in the same code path, so anything
         further apart is treated as no real match rather than risking
         a wrong attachment. Critically, this re-attaches the trade to
         the SAME live dict object now sitting in STATE[<list>], not a
         detached copy — sweep_sim_trades() reads through _signal_ref
         to see when that signal's status flips to CLOSED, so a copy
         would just freeze the trade as PENDING forever, silently
         re-introducing the exact bug this fix is for.
         A PENDING trade whose own signal ALSO didn't survive (e.g. it
         fell out of that module's own history maxlen) can't be
         re-linked — dropped rather than left permanently stuck, and
         counted in the startup log line ("N pending trades couldn't be
         re-linked and were dropped") so this stays visible instead of
         silently recurring in a different form.

v0.68.0 - surfaced the scanner error log (STATE["errors"]) in the UI —
         it was already returned by /api/status as "errors" (last 10
         entries), but nothing ever rendered it; the only visible error
         signal was an unrelated numeric "ошибок: N" count on the
         Автоторговля tab (counting autotrade ORDER failures, not scan-
         level exceptions like a failed candle fetch). Found this gap
         when the user asked where to see scan errors after the Volume
         module went quiet (v0.66.0's "искл. неликвид" swung 96 -> 23
         between two consecutive scans on a near-identical universe
         size — too fast to be real liquidity change, more likely
         symbols intermittently failing data_quality_check's "too few
         candles" path from a flaky/incomplete fetch).
         New block in the Volume panel: "Последние ошибки сканера (N)"
         — timestamp + message for each of the last 10, newest first.
         Purely a display fix — no change to what gets logged or when,
         just makes the existing data visible instead of only reachable
         by hitting /api/status directly as raw JSON.

v0.69.0 - root cause found for the "искл. неликвид" swing (96 -> 23 in
         2 minutes) the user asked about, once v0.68.0's new error panel
         made it visible: DNS resolution failures for api.gateio.ws
         ("Failed to resolve... No address associated with hostname"),
         clustered in a ~35s window — a transient mobile-network blip,
         not a persistent issue (no repeats afterward in the same log).
         Two fixes:
         (1) get_candles() now retries GET_CANDLES_RETRIES (default 2)
         times specifically on requests.exceptions.ConnectionError
         (covers DNS failures and refused/reset connections), with
         GET_CANDLES_RETRY_DELAY (default 1.5s) between attempts, before
         giving up — a brief blip shouldn't cost a symbol its whole
         cycle. Deliberately does NOT retry HTTP error responses or read
         timeouts — only "couldn't even reach the host" failures, so a
         real outage or rate limit doesn't turn into a retry pile-up.
         Every caller (scan_symbol's own fetch, and fetch_candles_
         concurrent()'s per-symbol calls used by the Divergence/EMA
         shared cache) gets this for free, no per-caller changes needed.
         (2) New excluded_fetch_error counter, separate from
         excluded_low_quality — scan_symbol() now catches
         ConnectionError specifically (after retries are exhausted) and
         counts it here instead of falling into the generic error log
         un-counted. Reset alongside the other per-cycle counters in all
         three existing reset sites, exposed in /api/status, and shown
         in the header scan-status line as ", N сетевых сбоев" (only
         appears when nonzero) — so a network blip is now visibly
         distinguishable from genuine low-liquidity exclusions at a
         glance, instead of the two being indistinguishable in the
         header and the real cause only visible by reading raw error
         text.
         Also confirmed from the same log: the recurring "reconcile_
         positions_and_orders: cancelled N orphaned trigger order(s)"
         entries are the existing cleanup mechanism working as intended
         (an orphaned TP or SL left behind after its position closed),
         not a new problem — mentioned here only because they showed up
         in the same error-panel screenshot and were worth ruling out
         explicitly rather than leaving ambiguous.

v0.70.0 - two fixes from direct user reports off the ATR-SL rollout:
         (1) REAL SAFETY BUG: user reported live cases where the
         computed SL sat further from entry than the exchange's own
         liquidation price at the resolved leverage — meaning Gate
         would forcibly liquidate the position before that SL order
         could ever trigger, turning a bounded intended loss into an
         uncontrolled one. Root cause: only the scalp module ever
         checked SL distance against the liquidation buffer; every
         other mode (bounce/breakout/divergence/ema/session) placed its
         SL with no such check at all. Harmless while EMA's SL was a
         tight fixed 0.4%, far short of any real liquidation distance —
         stopped being harmless the moment EMA's SL went ATR-based
         (v0.65.0) and started coming out wider on volatile symbols.
         New check in execute_autotrade() (shared by every mode, not
         just EMA): after leverage is resolved, computes the
         liquidation buffer via compute_scalp_liquidation_move_pct()
         (its math isn't actually scalp-specific, just first written
         there) using mmr_pct from STATE["scalp_mmr_map"] — MMR is a
         Gate contract property, not a per-module one, so reusing that
         already-refreshed cache is correct rather than a shortcut —
         falling back to SCALP_DEFAULT_MMR_PCT for a symbol the scalp
         universe hasn't covered. If the liquidation buffer doesn't
         clear the SL distance by at least SCALP_SAFETY_MARGIN (1.5x,
         the same constant scalp already uses for this exact purpose),
         the trade is SKIPPED with a clear log reason instead of placing
         an SL that could never actually fire.
         (2) RR got worse after ATR-based SL, per direct user question
         asking for a filter to cut trade count. Since TP is fixed and
         SL is ATR-based, RR is directly 1/ATR — a minimum-RR filter is
         really a maximum-ATR filter expressed in the unit that
         actually matters (risk relative to reward), so it was the
         obvious direct choice over some indirect volatility proxy. New
         EMA_MIN_RR (default 0 = disabled): scan_symbol_ema() now
         checks the computed rr against it BEFORE consuming the
         cooldown slot (a filtered-out signal must not block a later,
         better one on the same symbol+interval — moved the whole
         entry/atr/rr computation earlier in the function to make this
         ordering possible). Filtered count tracked in filtered_by_
         min_rr, shown in the EMA panel header next to the threshold
         when active. Wired through get_settings()/apply_settings()/
         SETTINGS_KEYS and a new "↳ EMA мин. RR" field in the settings
         UI, right under the EMA leverage row — adjustable live, no
         restart needed, 0 always means off.

v0.71.0 - EMA gets its own signal timeout, per direct user request
         ("расширим тайм-аут для сделок EMA, если недавно этого не
         делали" — checked: hadn't). SIGNAL_TIMEOUT_SEC (6h) was shared
         by Volume, Divergence, AND EMA — widening it for EMA alone
         needed its own constant, not a shared-value change that would
         have also affected the other two modules.
         New EMA_SIGNAL_TIMEOUT_SEC, default 12h (doubled from the
         shared 6h) — a starting point given EMA's timeout rate looked
         high (12/46 closed) at 6h. update_ema_outcomes() now checks
         against this instead of SIGNAL_TIMEOUT_SEC; Volume and
         Divergence's own outcome-tracking functions are untouched,
         still on the original shared constant.
         Wired through get_settings()/apply_settings()/SETTINGS_KEYS as
         "ema_signal_timeout_hours" (stored/edited in hours for a
         friendlier UI number than raw seconds, converted to/from
         EMA_SIGNAL_TIMEOUT_SEC internally) and a new "↳ EMA тайм-аут
         (ч)" row in settings, right under the min-RR field — adjustable
         live, no restart needed. Also added to /api/ema/status's config
         block as signal_timeout_hours.

v0.72.0 - ADX regime filter for EMA, per direct user request to research
         real improvements for the whipsaw problem rather than guessing.
         Virtually every source on EMA crossover strategies converges on
         the same finding: raw crossovers run ~35-40% win rate in
         choppy/range-bound conditions, and the standard, decades-old
         fix (Wilder, 1978) is requiring ADX above ~20-25 before trading
         a crossover — ADX measures trend STRENGTH directly, unlike
         recent_crossover_count (v0.62.0), which was always just a
         home-grown proxy for the same idea.
         New _dm_series() + compute_adx(): proper Wilder DM/DI/DX/ADX,
         reusing _true_range_series()/_atr_series() for the smoothing
         (same Wilder-smoothing math, applied twice — once for DM/TR,
         once more for DX itself). adx is now a diagnostic field on
         every EMA signal (same pattern as atr_pct/ema_slope_pct/
         ema_gap_pct), plus a new win/loss breakdown in compute_ema_
         stats().
         Unlike EMA_MIN_RR/EMA_MIN_GAP_PCT (both default off, no
         universal right answer without our own data first),
         EMA_ADX_FILTER_ENABLED defaults ON with EMA_ADX_MIN=20 — this
         one's a well-established literature threshold, not a guess,
         checked before the cooldown-consuming block (same ordering
         reasoning as the RR filter: a filtered signal must not block a
         later, better one).
         Also added, off by default per the same reasoning as EMA_MIN_
         RR: EMA_MIN_GAP_PCT, a minimum EMA7/EMA14 separation at signal
         time (the "buffer zone before confirming a cross" idea several
         sources also recommend) — reuses the existing ema_gap_pct
         diagnostic, no new calculation. Needs its own win/loss
         breakdown data before a sensible default exists, unlike ADX.
         New filtered_by_adx / filtered_by_min_gap counters, both shown
         in the EMA panel header when their filter is active. New ADX
         column in the EMA signals table. All three new settings
         (ema_adx_filter_enabled, ema_adx_min, ema_min_gap_pct) wired
         through get_settings()/apply_settings()/SETTINGS_KEYS and new
         "↳ EMA фильтр ADX" (toggle + threshold) / "↳ EMA мин. зазор
         EMA7/14 (%)" rows in settings — all adjustable live, no restart
         needed.

v0.73.0 - get_candles() now also retries on requests.exceptions.Timeout
         (read timeouts, not just connect-level ConnectionError from
         v0.69.0), per a live error-log screenshot showing "Read timed
         out (read timeout=10)" recurring across many different symbols
         over several minutes. v0.69.0 deliberately excluded read
         timeouts from retries, reasoning that a real outage or rate
         limit shouldn't turn into a retry pile-up — reversed against
         this actual evidence: the pattern (many different symbols,
         spread over minutes, not one symbol repeatedly) looks like
         WORKERS (12 concurrent requests) routinely exceeding
         HTTP_TIMEOUT under real mobile-network conditions, not a hard
         outage, so retrying is the right call here. Still bounded by
         GET_CANDLES_RETRIES either way, so even if this read is wrong
         for some future genuine outage, it only adds a few seconds of
         latency per symbol, not an unbounded pile-up.
         scan_symbol()'s specific error handler broadened to match
         (ConnectionError, Timeout) and count both into the same
         excluded_fetch_error counter / "N сетевых сбоев" header
         display from v0.69.0 — both represent the same underlying
         thing (couldn't get fresh data for this symbol due to network
         conditions), so splitting them into separate counters wouldn't
         add useful information.
         Also in progress, not yet wired up or pushed as a working
         feature: generic signal-snapshot save/replay infrastructure
         (save_signal_snapshot()/list_signal_snapshots()/replay_signal_
         snapshot(), STATE["signal_snapshots"]) — per user request, to
         freeze a module's closed signals and instantly test a
         candidate filter threshold against them offline instead of
         waiting for new live data. Paused mid-implementation (no Flask
         endpoints or UI yet, not in save_state()/load_state()) pending
         the user's decision on whether/how to continue it — the
         functions exist but nothing calls them yet, so this is inert,
         not broken.

v0.74.0 - get_tickers() gets the same retry protection get_candles() got
         in v0.69.0/v0.73.0 (ConnectionError + Timeout, GET_CANDLES_
         RETRIES/GET_CANDLES_RETRY_DELAY, reused not duplicated). User
         showed a raw Termux crash traceback: a DNS blip during
         build_universe() -> get_tickers() propagated all the way up
         with no [ERR]-style catch, unlike the other background loops
         (scalp_loop/session_loop/telegram) which DID catch the same
         DNS failure gracefully in that same log excerpt. Checked
         scan_loop() itself first: its try/except (added some time ago,
         wraps the entire cycle body including build_universe()) DOES
         already catch this in the current code — the crash traceback's
         own line number (7436) is far below where build_universe() is
         called in the current source (7611+), meaning the process that
         crashed was running a meaningfully older version, most likely
         from well before several of today's pushes. So the crash itself
         isn't reproducible against current code; user needs to restart
         the Termux process to actually pick up everything pushed today
         (v0.69.0 through this one) rather than keep running whatever's
         been up for hours.
         Added the retry anyway as real defense in depth: even with
         scan_loop()'s outer catch preventing a crash, a single DNS blip
         on the tickers fetch with no retry would previously cost an
         entire scan cycle (SCAN_INTERVAL_SEC, 45s+) instead of
         recovering in a couple seconds.
         Did not sweep every other raw requests.get/post call in the
         file for the same treatment this round — scan_loop()'s outer
         catch already prevents any of them from crashing that thread,
         and the other background loops already have their own [ERR]-
         style catches per the same log excerpt, so the remaining
         exposure is "costs a cycle," not "kills a thread" — lower
         priority than the two highest-traffic endpoints (candles,
         tickers) fixed here and in v0.73.0.

v0.75.0 - get_candles_range() gets the same network-error retry as
         get_candles()/get_tickers(), per a live error-log screenshot
         (v0.74.0 running, confirming that version's own network fixes
         work — this is a genuinely separate function that was never
         covered). Errors showed as SSLEOFError ("UNEXPECTED_EOF_
         WHILE_READING") from "magnified profile" and "session
         process_one" — both consumers of get_candles_range(), not
         get_candles(). requests.exceptions.SSLError is itself a
         subclass of requests.exceptions.ConnectionError (confirmed
         against the requests source), so the existing except clause
         pattern already covers it with no new exception class needed.
         get_candles_range() paginates in a loop with its own inner
         retry for HTTP 400 (shrinks chunk_points and retries same
         chunk) — added a SEPARATE counter (net_attempt, capped at
         GET_CANDLES_RETRIES) for (ConnectionError, Timeout) specifically,
         so a network blip retries a few times before giving up, without
         being confused with or interfering with the existing chunk-
         size-shrink retry logic (different problem, different fix,
         kept as two distinct except clauses on the same try). A range
         fetch makes many more individual requests than a single
         get_candles() call, so it's proportionally more likely to hit
         a transient blip somewhere in the middle — previously any
         single one aborted the ENTIRE range fetch with zero retry.
         Whatever gets past this still surfaces via the caller's own
         [ERR]-prefixed catch (magnified profile / session process_one
         each already have their own), same safety net as before —
         this just reduces how often that fallback is needed.

v0.76.0 - WORKERS lowered 12 -> 8, HTTP_TIMEOUT raised 10 -> 15s (now
         env-configurable via VP_HTTP_TIMEOUT, was hardcoded), per
         direct user request. Live error logs kept showing "network
         error after 2 retries" on read timeouts even with v0.73.0's/
         v0.75.0's retry logic in place — retries alone weren't enough,
         pointing at 12 concurrent requests routinely saturating actual
         available mobile bandwidth rather than any single request
         being unlucky. Both levers address that directly: fewer
         simultaneous requests competing for the same limited
         bandwidth, and more room per request before giving up. Trade-
         off is a slower full-universe scan cycle in exchange for fewer
         failed fetches — accepted as the right call given how often
         retries were still coming up short.

v0.77.0 - get_futures_risk_limit_tiers() gets the same network-error
         retry as the other fetch functions — last remaining gap, found
         after v0.76.0's WORKERS/HTTP_TIMEOUT change cut the error log
         from 10 entries down to 1 (confirms that fix worked well). This
         function pages through Gate's risk_limit_tiers endpoint
         (SCALP_REFRESH_SEC apart, hours between runs) and previously
         had zero retry on any single page's fetch — a network blip
         mid-pagination meant losing every page not yet fetched for
         that entire cycle, even though the outer try/except already
         degrades gracefully (keeps whatever pages DID succeed rather
         than crashing). Same (ConnectionError, Timeout) + GET_CANDLES_
         RETRIES/GET_CANDLES_RETRY_DELAY policy as get_candles()/
         get_tickers()/get_candles_range() before it, applied per-page
         inside the existing pagination loop.

v0.78.0 - VOL_CONFIRM_RATIO lowered 1.4 -> 1.25, per direct user request
         after checking the actual per-cycle rejection breakdown they'd
         asked to see ("За этот скан отклонено — ... объём: 12") —
         volume was the leading rejection reason that cycle, well above
         trend (0) and staleness (2). 1.15x (the original default) was
         found too weak in v0.57.0; 1.4x now looks too strict once
         actually observed against live rejection counts. 1.25x is a
         middle ground between the two, not a return to either extreme.

v0.79.0 - SIGNAL_MAX_STALENESS_SEC raised 180s -> 300s, per direct user
         follow-up after "still zero signals" — this time with actual
         evidence pointing at a specific, previously-invisible cause.
         The v0.78.0 rejection breakdown showed "устарел: 17" leading
         Volume's own count (ahead of объём: 11), for a cycle where
         candidates were genuinely being found (not the earlier all-
         zero problem from before v0.78.0's volume-ratio fix). Root
         cause: v0.76.0 deliberately lowered WORKERS 12->8 to fix
         network reliability, which as an unavoidable side effect
         slowed the full scan cycle back down — now observed at ~296s
         live. The 180s staleness threshold (last set in v0.62.1, back
         when cycles were faster) was never revisited after that
         slowdown, so symbols scanned in the back half of a now-~5-
         minute cycle were routinely aging past 180s before the scan
         even reached them — real signals were being thrown away
         purely because of how far into the cycle their symbol
         happened to sit, not because anything was wrong with them.
         Raised to 300s to roughly match the observed full-cycle
         duration instead of leaving the two mismatched. Confirmed via
         code search this only affects Volume (line ~7446, the only
         reference to this constant) — Divergence has no equivalent
         check and runs on 1h candles anyway, where this kind of gap
         is proportionally trivial, so its own continued quiet period
         has a different (unconfirmed, likely just genuinely quiet
         market conditions plus occasional network-related fetch
         misses) cause, not this one.

v0.80.0 - reverse mode for the Session module, per direct user request
         after its live winrate looked bad (~11%). Mirrors DIV_INVERT_
         SIGNALS/EMA_INVERT_SIGNALS in spirit, but with its own sizing
         spec the user was explicit about: the inverted trade's SL uses
         the SAME risk distance the non-inverted trade's stop would
         have had (sweep_extreme + SESSION_SL_BUFFER_PCT), just applied
         on the opposite side of entry since direction flips — TP is
         fixed at 2x that risk (RR=2), NOT the original TP (opposite
         side of the consolidation range, a distance tied to range
         width rather than to risk, so it wouldn't make sense to reuse
         for a differently-sized inverted stop).
         New SESSION_INVERT_SIGNALS (default off). Implemented directly
         inside detect_session_manipulation() itself — the single
         function already shared by both live scanning and the
         historical backtest ranking — rather than as a separate post-
         processing step, so live signals and the backtest-driven
         symbol ranking automatically agree on which direction is
         actually being traded. This sidesteps the exact class of bug
         found and fixed for divergence's pivot-stability stat (v0.66.0),
         where a metric computed outside the core detection function
         didn't know about the invert flag and reported the wrong sign
         for months.
         Wired through get_settings()/apply_settings()/SETTINGS_KEYS and
         a new "↳ Реверс сигналов (RR 2)" toggle right under the Session
         enable switch — adjustable live, no restart needed. Session's
         own panel header now also shows "РЕВЕРС ВКЛЮЧЁН (RR 2)" when
         active, matching how Divergence's panel already flags its own
         reverse state — closes the same gap noted earlier: reverse
         status needs to be visible at a glance, not just inferred.

v0.81.0 - realized-R tracking for TIMEOUT closes, per direct user
         question about why EMA's account balance was quietly drifting
         negative despite a strong-looking 70.5% winrate. Diagnosis:
         EV from winrate*avg_RR was genuinely positive (+0.355R/trade),
         but median RR (0.696) sat well below the average (0.922) —
         a few high-RR outlier wins were propping up the average, so
         the TYPICAL trade's edge was thinner than the headline number
         suggested (+0.196R at median RR). On top of that, 24 TIMEOUTs
         out of 156 closed trades (15.4%) were invisible to the win/
         loss-only winrate entirely, yet TIMEOUT closes at whatever the
         market price happens to be when the window expires (see
         update_ema_outcomes' "last_price") — not at breakeven, not
         excluded from PnL — so a batch of them closing slightly
         negative on average would be real, quiet money leaving the
         account with no trace in the 70.5% figure.
         close_ema_signal() now computes exit_r (realized R at the
         actual close price, signed by direction) for every close, not
         just WIN/LOSS — previously only mfe_r_at_close/mae_r_at_close
         were captured, nothing recorded the actual realized outcome
         for a TIMEOUT. compute_ema_stats() gained exit_r_timeouts
         (same avg/median/p25/p75/n shape as the other agg() stats),
         and the EMA panel's MFE/MAE block shows it as a new "TIMEOUT
         реализованный R" line — explicitly labeled as not part of the
         winrate but real balance impact, so it doesn't get missed the
         same way again.
         Old signals closed before this change have no exit_r (agg()
         quietly excludes them, no error) — the new stat starts thin
         and fills in as new TIMEOUTs occur going forward, same
         backward-compat pattern as every other diagnostic field added
         this way (atr_pct, adx, rr, etc.).

v0.82.0 - orphaned trigger orders now get cleaned up on a fixed 2-minute
         timer, per direct user report with a screenshot: Gate showing
         16 open orders against only 2 open positions. Root cause was
         in reconcile_positions_and_orders()'s own design, stated
         plainly in its old docstring: it was called only "at the
         moment a new real trade is about to open," piggybacking on
         however often trades happened rather than running on its own
         schedule — during a quiet stretch with no new trades, orphaned
         orders (leftover TP or SL after the other leg already closed
         the position) just sat there accumulating indefinitely.
         New reconcile_loop() + RECONCILE_INTERVAL_SEC (default 120s,
         the 2-minute cadence directly requested) — runs
         reconcile_positions_and_orders() on its own timer, registered
         as a new daemon thread in __main__. This is additive, not a
         replacement: execute_autotrade() still also calls it
         opportunistically right before opening a new position, same
         as before — the timer just closes the gap for whenever no new
         trade happens to trigger that call. Skipped in dry-run mode
         (nothing to reconcile against if nothing real is being placed).

v0.83.0 - EMA_MIN_RR default enabled (0 -> 0.3), per direct user request
         after a concrete live example: a UB_USDT SHORT (entry 0.12947,
         SL 0.150056, TP 0.127528) worked out to RR≈0.094 — risk 15.9%
         of price against a 1.5% reward, since TP stays fixed but SL is
         ATR-based and this symbol's 1h ATR was huge. A ~7x-worse
         outlier even against the already-low median RR (0.627 at the
         time). User asked to enable the filter but left the exact
         threshold to judgment; 0.3 was picked to clear that specific
         bad case with room to spare while staying below the median, so
         it should mainly cut tail outliers rather than the typical
         trade — not validated against a win/loss-by-RR-bucket
         breakdown, a reasonable starting point pending that data
         (filtered_by_min_rr will show how many signals it's actually
         catching).
         Important persistence note, called out directly to the user:
         save_settings() writes the FULL current settings dict (via
         get_settings()) on every save, so anyone who has saved settings
         since EMA_MIN_RR existed (v0.72.0) almost certainly already has
         "ema_min_rr": 0 pinned in their settings.json — load_settings()
         will apply that saved 0 at startup, silently overriding this
         new code-level default of 0.3. The code default only takes
         effect on a fresh install with no settings.json yet. Existing
         users need to set the "↳ EMA мин. RR" field to 0.3 once via the
         settings UI (added in v0.72.0) for it to actually take effect —
         flagged so this doesn't become a second "why didn't my fix
         apply" investigation like the earlier raw.githubusercontent.com
         caching one.

v0.84.0 - SESSION_SL_MULT (default 1.5), per direct user request after
         a live example (CYS_USDT, inverted-mode LONG) hit its SL:
         entry 0.5815, SL 0.563719, risk 3.06% of price. Multiplies the
         base risk distance (sweep_extreme + SESSION_SL_BUFFER_PCT vs
         entry) by 1.5 before it's used for BOTH the inverted trade's
         SL and its RR=2 TP, so risk and reward scale together and RR
         stays exactly 2 at the new, wider stop — not a case of loosening
         the stop while leaving the take behind. Applied in both
         direction branches of detect_session_manipulation(), only
         inside the SESSION_INVERT_SIGNALS path — the non-inverted
         trade keeps its original sizing (sweep-based stop, opposite-
         range-edge take) untouched, since that path was never part of
         this request and isn't RR-based the same way. No settings-
         persistence caveat here unlike EMA_MIN_RR's v0.83.0 note — this
         constant was never added to SETTINGS_KEYS/the settings UI, so
         there's no saved-settings value that could override this new
         code default; the 1.5x takes effect immediately on restart.

v0.85.0 - EMA_MIN_RR raised 0.3 -> 0.7, per direct user request after
         live stats showed the average/median RR gap actually mattered:
         avg RR 0.923 gave EV≈+0.075R at the live 55.9% winrate, but
         median RR 0.717 gave EV≈-0.040R at that same winrate — the
         TYPICAL trade was already losing money on average even though
         the headline average RR looked fine. 0.3 (v0.83.0) was picked
         only to clear one extreme outlier (UB_USDT, RR≈0.094) and was
         nowhere near this. Breakeven RR at 55.9% winrate works out to
         ≈0.789; 0.7 sits just under that deliberately, cutting sub-
         breakeven trades without also catching ones right at the
         margin (winrate itself is an estimate with its own noise, so
         filtering exactly at the calculated breakeven would over-cut).
         Confirmed same persistence caveat as v0.83.0 applies: if
         settings.json already has ema_min_rr saved (0.3 or otherwise),
         it overrides this new code default of 0.7 at startup — needs
         the "↳ EMA мин. RR" settings field updated to 0.7 manually,
         same as before.

v0.86.0 - Session's "Открытие" column now shows date+time, not just
         time, per direct user observation: session open is the same
         fixed 10:00 every single day by design (SESSION_OPEN_HOUR_
         LOCAL), so the existing fmtTime() (hour:minute only) gave zero
         way to tell which day's session a row belonged to — every row
         just read "10:00" regardless of when it actually happened.
         New fmtDateTime() (day, month, hour, minute) used specifically
         for session_open in both places it's rendered: the main
         session signals table and the per-symbol sessionDayLink history
         list. fmtTime() itself is untouched and still used everywhere
         else (Volume/Divergence/EMA/Scalp tables, error log timestamps,
         exit-time tooltips) — those show each row's own varying
         creation time throughout the day, where time-only is
         sufficient context, unlike Session's fixed daily open.

v0.87.0 - SCALP_SL_BUFFER_MULT raised back 0.05 -> 0.25, per direct
         user request to improve scalp's real profitability (not just
         RR cosmetics). The 0.05 cut (an earlier version) was explicitly
         made cautious because it was based on n=1 loss — now n=26 real
         losses show avg LOSS MAE -1.167R / median -1.065R, meaning
         actual adverse excursion overshoots the nominal -1.0R stop by
         ~17% on average (slippage/wicks the historical p90_adverse_pct
         measurement doesn't fully capture). Recomputed EV using a live
         example (SKYAI_USDT, RR≈0.479, 70.8% live winrate): by nominal
         stop, EV≈+0.047R (thin positive); by the REAL overshot stop
         (-1.167R instead of -1.0R), EV≈-0.002R — essentially zero. The
         decent winrate was very likely being fully absorbed by this
         overshoot rather than showing up as real account profit, which
         is what the user's "хороший винрейт, но толку мало" complaint
         actually looks like once the math is done — a more concrete,
         fixable target than "RR isn't great" (which alone is expected
         and already accounted for by the EV-based scoring from v0.61.0).
         0.25 aims to bring the stop back in line with where real losses
         land rather than an arbitrary round number, following the same
         "watch live data, don't just theorize" approach the original
         0.2->0.05 change used — needs verifying against the next batch
         of losses under the new buffer. Not in SETTINGS_KEYS, so no
         settings-persistence override risk here (unlike EMA_MIN_RR).

v0.88.0 - ATR-based SL for Divergence, per direct user request after
         reviewing live MFE/MAE data with reverse mode confirmed off
         (so the numbers were trustworthy, unlike the earlier pivot-
         stability sign bug period). Root cause: DIV_RR-derived SL was
         a fixed 0.5% (DIV_TP_PCT/DIV_RR) regardless of the symbol's
         actual volatility — LOSS MAE at close averaged 3.23R / median
         1.851R, meaning losses overshot the nominal -1.0R stop by
         3x+ on average, an even bigger gap than EMA had before its
         own ATR fix (v0.65.0, ~2x overshoot). Exact same mirror of
         that fix: new DIV_SL_MODE ("atr" default, or "fixed_pct" to
         reproduce the old exact behavior) and DIV_SL_ATR_MULT (default
         1.5, same multiplier EMA uses). compute_div_tp_sl() rewritten
         to match compute_ema_tp_sl()'s shape: TP stays a fixed % of
         entry (DIV_TP_PCT, unchanged), SL = ATR(EMA_DIAG_ATR_PERIOD,
         the same period constant EMA's own ATR already uses — not a
         separate one) * DIV_SL_ATR_MULT, falling back to the old
         DIV_RR-derived SL when ATR is unavailable or DIV_SL_MODE is
         "fixed_pct". scan_symbol_divergence() computes ATR directly
         from the candles it already has in hand (reuses _true_range_
         series()/_atr_series(), no new fetch) rather than needing a
         separate diagnostics pass the way EMA originally grew one.
         Same downstream consequences as EMA's v0.65.0: compute_div_
         tp_sl() now returns (sl, tp, risk, rr) instead of (sl, tp,
         risk); every divergence signal carries its own "rr" and
         "atr_pct" fields; compute_divergence_stats() gained rr_all/
         rr_wins/rr_losses and atr_pct_wins/atr_pct_losses (same agg()
         shape as everything else); the panel header (previously "RR
         ${cfg.rr}", one fixed number) now shows "RR ср. X (медиана Y)"
         plus "SL: ATR×1.5" (or "фикс. RR N" in fixed_pct mode); new RR
         column in the divergence signals table; /api/status's div
         config block replaced "rr" with "sl_mode"/"sl_atr_mult"/
         "rr_fallback". Old signals from before this change have no
         "rr"/"atr_pct" keys — every read site uses .get()/None-checks,
         so they render as "-" and are simply excluded from the new
         aggregates rather than erroring, same backward-compat pattern
         used for every other diagnostic field added this way.

v0.89.0 - mobile layout fixes, per direct user request with a live
         screenshot showing the header's 7 reset/settings buttons
         wrapping across ~4 lines on a phone (eating most of the
         visible screen before any actual data), and the 12-column
         tables (EMA's is the worst case: Symbol/Dir/TF/Entry/SL/TP/RR/
         ADX/MFE/MAE/Status/Time) rendering all columns crushed into
         barely-legible widths at that viewport.
         CSS-only fix, no JS or markup changes: a new @media (max-width:
         640px) block. Header buttons switch from wrapping to a single
         horizontally-scrollable row (#headerTop flex-direction:column
         so the title sits above it, button container gets overflow-x:
         auto). Tabs get the same horizontal-scroll treatment instead of
         wrapping. Tables get `display:block; overflow-x:auto; white-
         space:nowrap` — the standard scrollable-table CSS trick, which
         applies to any <table> element on the page rather than needing
         per-table markup changes. This is why it works for the three
         static tables (signals/div/ema) AND the dynamically-generated
         ones (scalp/session panels build their own <table> via
         innerHTML) with a single rule — the CSS targets the element
         itself, not a specific id, so nothing rendered later needs its
         own wrapper. Minor font/padding reductions for header text and
         table cells at this width too.

v0.90.0 - disabled the header's `position:sticky` specifically inside
         the v0.89.0 mobile media query, per a direct live screenshot
         showing a real rendering glitch: after pinch-zooming out on
         the phone, the header's own stats text ("откр.27" etc.) was
         visibly duplicated/overlapping onto table rows further down
         the page — a known WebKit/Chromium-mobile artifact where
         `position:sticky` combined with a zoom transform can smear a
         stale paint of the sticky element onto scrolled content below
         it. Added `header { position:static; }` inside the existing
         @media (max-width:640px) block from v0.89.0 — narrow/mobile
         viewports lose the "header stays pinned while scrolling"
         convenience in exchange for not having this overlap bug;
         desktop (outside that breakpoint) keeps sticky as before,
         since the bug was specific to the mobile+zoom combination, not
         sticky positioning in general.

v0.91.0 - fixed a real bug in recommend_scalp_config()'s target
         selection, found while answering a direct user question about
         why scalp was "barely profitable despite a good winrate" —
         stops kept coming out wider than the fixed target. Root cause:
         the target loop was sorted largest-first and `break`d after
         the FIRST (i.e. largest) target clearing SCALP_MIN_HIT_RATE,
         never even computing smaller targets' actual EV — a leftover
         assumption from the OLD score (hit_rate*trades_per_day, where
         a bigger target only ever meant fewer trades/day, so stopping
         early was a safe shortcut). Under the CURRENT EV-based score
         (ev_per_trade_pct = hit_frac*pct - (1-hit_frac)*sl_pct_est,
         since v0.61.0), that assumption is simply wrong: a smaller
         target usually clears a much higher hit-rate, and that can
         easily beat a bigger target's raw size in the real EV math.
         The break meant every qualifying symbol mechanically locked
         onto its largest clearing target from SCALP_TARGET_PCTS
         without ever checking whether a smaller one scored better —
         exactly what the live data showed: every SKYAI_USDT scalp
         signal used target=3% (the largest configured option), and
         with SL frequently exceeding that fixed target, the account
         was staying positive on a thin margin only because the 70%+
         hit-rate was carrying stops that were routinely bigger than
         the reward.
         Fix: removed the `break` and the largest-first sort — now
         every (interval, direction)'s qualifying targets get scored,
         and whichever genuinely has the best EV wins, which may well
         be a smaller target with a much better hit-rate on symbols
         where that's true. Docstring updated to match. No new
         constant/filter needed — this was a real logic bug in the
         existing EV-based selection, not a missing threshold.

v0.92.0 - new SCALP_MIN_RR (default 0.5) in recommend_scalp_config(),
         per direct user follow-up right after v0.91.0's target-
         selection fix: "стоп может быть другим, а то сейчас в среднем
         в 3 раза больше тейка" (SL averaging ~3x the target). v0.91.0
         fixed the mechanism CHOOSING among targets but didn't cap how
         lopsided a still-EV-positive winner's SL:target ratio could
         be. Deliberately does NOT touch the SL calculation itself
         (sl_pct_est, p90_adverse_pct-based, deliberately widened in
         v0.87.0 to match real adverse excursion) — artificially
         tightening a stop below what real losses actually reach would
         just convert would-be wins into losses and undo that fix, not
         improve anything. Instead this REJECTS any (interval,
         direction, target) candidate where target_pct/sl_pct_est
         falls under 0.5 (SL more than 2x the target), same "filter,
         don't distort the underlying measurement" approach EMA_MIN_RR
         already uses. Placed right after sl_pct_est is computed, before
         EV/score — a symbol can still end up with no qualifying
         candidate at all if none of its targets clear both this and
         SCALP_MIN_HIT_RATE, same legitimate "not a safe candidate"
         outcome the function already returns None for. Candidate dicts
         also gained an "rr" field (target_pct/sl_pct_est) for
         visibility, though no UI column was added for it this round —
         the fix itself was the priority requested.

v0.93.0 - Risk auto-tune: a new system that periodically nudges risk-
         related constants based on live win/loss data, per direct user
         request to automate the recurring pattern of this whole session
         — screenshot stats, Claude computes breakeven RR / overshoot /
         reverse-EV, Claude picks a new number. User explicitly chose
         full automation including reverse over an advisory-only or
         partial-automation option.
         NOT the same system as auto_tune_cycle()/AUTO_TUNE_ENABLED
         (pre-existing — searches Volume Profile detection parameters
         per symbol, unrelated). This one is named RISK_AUTOTUNE_* to
         avoid the collision.
         Three generic rule types, applied per module:
         - _risk_autotune_min_rr: nudges a *_MIN_RR filter toward 95% of
           the RR that would break even at the module's live winrate —
           the same reasoning manually used for EMA_MIN_RR (0.3->0.7)
           and SCALP_MIN_RR (0.5).
         - _risk_autotune_sl_mult: nudges an SL-width multiplier based on
           whether realized LOSS MAE (in R) overshoots -1.0 — same logic
           manually used for SCALP_SL_BUFFER_MULT (0.05->0.25).
         - _risk_autotune_reverse: flips an *_INVERT_SIGNALS flag if the
           CURRENTLY active direction's own EV has been solidly negative
           over a large sample. Explicitly weaker evidence than the
           other two (live data never shows the mirror direction's
           outcome, only whichever was actually traded) — gets a higher
           sample bar (RISK_AUTOTUNE_MIN_SAMPLE_REVERSE=30 vs 20) and a
           much longer cooldown (24h vs 6h) specifically to prevent
           flip-flopping on noise, since a wrong flip reverses every
           future signal until the next one, not just one trade.
         Applied to: EMA_MIN_RR/EMA_SL_ATR_MULT/EMA_INVERT_SIGNALS,
         DIV_MIN_RR (NEW, see below)/DIV_SL_ATR_MULT/DIV_INVERT_SIGNALS,
         SCALP_MIN_RR/SCALP_SL_BUFFER_MULT (scalp has no reverse flag —
         direction comes from recommend_scalp_config's own EV ranking,
         not an invertible indicator), and SESSION_INVERT_SIGNALS only
         (SESSION_SL_MULT can't be auto-tuned the overshoot way — Session
         signals never got MFE/MAE tracking added, a real pre-existing
         gap being surfaced here rather than silently worked around;
         session's reverse check computes realized R directly from
         entry/sl/exit_price instead, using RR=2 fixed by construction
         from SESSION_INVERT_SIGNALS's own v0.80.0 sizing).
         New DIV_MIN_RR filter added for symmetry with EMA_MIN_RR (0 =
         disabled by default) — found already partially wired (constant
         + gating check in scan_symbol_divergence, referencing a v0.93.0
         comment) but with an uninitialized STATE["filtered_by_div_min_rr"]
         that would have KeyError'd at runtime; completed to full parity
         with EMA_MIN_RR (settings persistence, /api/divergence/status,
         panel header display).
         Fixed a real pre-existing display bug while touching this code:
         EMA's panel header read filtered_by_min_rr/filtered_by_adx/
         filtered_by_min_gap from `s` (=status.stats), but the API
         actually returns all three as siblings of "stats", not inside
         it — meaning the "(отсеяно: N)" counts next to these filters
         had always silently shown 0 regardless of the real count. Fixed
         for EMA and applied correctly for the new DIV_MIN_RR display.
         SCALP_MIN_RR, SCALP_SL_BUFFER_MULT, SESSION_SL_MULT, EMA_SL_ATR_
         MULT, DIV_SL_ATR_MULT — none of these five were in the settings
         system before this (plain module constants, no persistence at
         all — not even the settings.json-overrides-code-default kind of
         persistence). Moved all five in, since an auto-tuned value that
         reverts on every restart defeats the point; this also fixes a
         latent gap for anyone who'd been setting them via env var only.
         New STATE["risk_autotune_log"] (capped 200, newest-first) and
         STATE["risk_autotune_last_change"] (cooldown timestamps per
         param) — both now persisted through save_state()/load_state()
         (log for the history, cooldowns so a restart can't bypass the
         anti-thrash protection by resetting them to "never tuned").
         risk_autotune_pass() runs hourly via new risk_autotune_loop()
         daemon thread; each module wrapped in its own try/except so one
         module's bad data doesn't block the others.
         Surfaced in /api/status under "risk_autotune" (distinct key from
         the pre-existing "auto_tune") and in a new collapsed-by-default
         "Авто-тюнинг риска" details element in the header, showing the
         most recent changes with old→new values and the reasoning
         string logged for each. No settings-UI toggles were added for
         the five newly-settings-backed constants this round (readable/
         writable via the API, and being tuned automatically per the
         user's request) — noted as a scope decision, not an oversight.

v0.94.0 - Session NY: a full, independent duplicate of the Session module
         (London/Frankfurt open, 10:00 Moscow) for the New York open
         (16:30 Moscow / 13:30 UTC), per direct user request after the
         original showed a promising live streak (6W/0L, though on a
         tiny sample — the actual larger per-symbol backtest table
         showed a more modest 50-67%, flagged directly to the user
         before building this). Explicitly NOT a generalization of the
         original into a multi-session system — user was specific that
         Session must stay completely untouched, zero refactor risk to
         something already working, even at the cost of duplicating a
         genuinely large amount of code. Every constant (SESSION_NY_*),
         function, STATE key, background thread, and API endpoint below
         has its own independent name; the original session_* code path
         was not modified anywhere except the one shared, generic
         cross-module check (has_open_signal_any_module gained a
         "session_ny_signals" entry in its own lists dict — skipping
         that would let this module stack a position on a symbol
         another module already has open).
         New York's 16:30 open isn't a whole hour like the original's
         10:00, so session_ny_open_utc_ts() needed its own minute-aware
         implementation (SESSION_NY_OPEN_MINUTE_LOCAL) — the original
         session_open_utc_ts() hardcodes minute=0. Consolidation range
         for the NY variant starts at SESSION_NY_RANGE_START_UTC_HOUR=7
         (07:00 UTC = the ORIGINAL session's own open) — i.e. the
         London/Frankfurt session becomes the "prior session" range for
         New York's manipulation check, the same relationship the
         original has to the Asian session before it.
         Fully duplicated: detect_session_ny_manipulation() (same
         sweep-and-reject pattern logic, own SESSION_NY_* constants,
         including its own SESSION_NY_INVERT_SIGNALS/SESSION_NY_SL_MULT
         reverse-mode sizing mirroring v0.80.0/v0.84.0), track_session_
         ny_outcome(), backtest_session_ny_symbol(), build_session_ny_
         universe(), scan_symbol_session_ny_live() (own autotrade mode
         string "session_ny", own AUTOTRADE_ENABLED_SESSION_NY/
         AUTOTRADE_LEVERAGE_SESSION_NY, own Telegram category with its
         own TELEGRAM_ALERTS_SESSION_NY toggle), update_session_ny_
         signal_outcomes(), compute_session_ny_signal_stats(), session_
         ny_loop() (daily batch backtest) and session_ny_live_loop()
         (daily live-window scan) as new daemon threads, five new API
         endpoints (/api/session_ny/status, /signals, /symbol/<symbol>,
         /chart/<symbol>, /api/reset/session_ny) mirroring the
         originals exactly. summarize_session_backtest() turned out to
         already be generic (doesn't reference any SESSION_* constant)
         — reused directly rather than duplicated.
         New settings: session_ny_enabled, session_ny_invert_signals,
         autotrade_session_ny, autotrade_leverage_session_ny — full
         SETTINGS_KEYS/get_settings/apply_settings wiring, plus a new
         "Сессия NY" settings group (own toggle + reverse toggle) and
         autotrade leverage row, independent of the original Session's
         settings UI.
         New "Сессия NY" tab + panel, JS render (refreshSessionNy,
         fmtSessionNyRow, wireSessionNyRowClicks, openSessionNyDetail)
         duplicated with independent names/DOM ids, and its own reset
         button (resetSessionNyBtn -> /api/reset/session_ny). ONE
         deliberate exception to "full duplicate": the chart modal
         (canvas drawing of a session's candles/range/entry/SL/TP) is
         reused rather than copied — openSessionChart() gained an
         optional 3rd endpoint parameter (default '/api/session/chart',
         so existing 2-arg calls are unaffected) and openSessionNyChart()
         is a thin wrapper passing '/api/session_ny/chart'. Justified
         because this is pure display code with zero effect on trading
         behavior, unlike everything else in this entry which IS fully
         duplicated — ~150 lines of canvas machinery duplicated for a
         read-only chart viewer wasn't worth the risk/reward the same
         way the detection and execution logic was.
         session_ny_signals persisted through save_state()/load_state()
         (same as every other signal list), and added to
         SNAPSHOT_MODULE_KEYS and the sim-trade relink module_lists
         mapping for full feature parity with every other module.

v0.95.0 - EXPERIMENTAL: XAU Liquidity Grab, per direct user request after
         sharing an Instagram post (trendwisdom/pranamghagare) claiming a
         76% win rate / <2% drawdown XAU/USD strategy. Treated with real
         skepticism, not taken at face value — flagged this to the user
         before building: the claim is an unverifiable ~1-month backtest
         screenshot with a "comment for the full report in DMs" / "comment
         for a free prop-firm guide" structure, i.e. a lead-generation
         funnel, not a checkable published result. Built anyway because
         the underlying PATTERN (sweep a level, close back inside, trade
         the reversal with a trend filter) is genuinely testable and
         structurally close to what Session/Session NY already do — worth
         backtesting on this app's own data rather than trusting the
         screenshot's numbers.
         User explicitly asked for this to be easy to delete later if it
         doesn't hold up — every name in the module is prefixed XAU_LG_/
         xau_lg_ specifically so the whole thing can be found and removed
         with one search. Marked EXPERIMENTAL throughout: a distinct
         header-comment block, a ⚠️ in the tab label and settings group
         title, and an explicit warning box at the top of the panel
         itself restating the source skepticism in the UI, not just code
         comments.
         Strategy as described: EMA(30) trend filter (close > EMA = longs
         only, < EMA = shorts only), support/resistance from swing pivots
         at LEFT=1/RIGHT=1 bars (deliberately tight/noisy, matching the
         source's own LuxAlgo settings — not the app's other pivot
         configs elsewhere), a confirmed "liquidity grab" when a candle
         wicks past a level but closes back inside it, entry at that
         candle's high/low, stop at its low/high, fixed 1:1 risk:reward.
         xau_lg_detect_signals() implements this as a single no-lookahead
         walk-forward pass — pivots only become active pivot_right bars
         after they form (the same confirmation delay a real pivot
         indicator has), and each signal only uses its own trigger bar's
         close/EMA — used identically for both backtesting (feed the
         whole history) and live scanning (feed recent history, check if
         the LAST bar produced a new signal), same principle as detect_
         session_manipulation() serving both callers.
         Universe restricted to XAU_USDT/XAUT_USDT/PAXG_USDT (actual
         gold-tracking symbols) rather than the app's usual 150-200
         symbol universe, per the user's own framing ("индикатор ПО
         ЗОЛОТУ") — diluting across everything would test a different,
         unstated hypothesis. AUTOTRADE_ENABLED_XAU_LG defaults OFF
         (unlike every other module's live-trading toggle, which follows
         whatever the user last set) — this one starts disabled
         specifically because the strategy is unverified; the user has
         to deliberately opt in after seeing real backtest numbers, not
         just because the module exists.
         Full module: xau_lg_detect_signals()/xau_lg_track_outcome()/
         xau_lg_backtest_symbol()/xau_lg_summarize_backtest() (backtest),
         xau_lg_scan_symbol_live()/update_xau_lg_signal_outcomes()/
         compute_xau_lg_signal_stats() (live), xau_lg_backtest_loop()/
         xau_lg_live_loop() (daemon threads), three API endpoints (/api/
         xau_lg/status, /signals, /api/reset/xau_lg — no per-symbol
         history or chart-modal endpoints, deliberately leaner than
         Session NY's given this is provisional), xau_lg_signals STATE
         persisted through save_state()/load_state(), added to has_open_
         signal_any_module's lists and the sim-trade relink module_lists
         mapping for consistency with every other module, new "XAU LG ⚠️"
         tab + panel (refreshXauLg — simpler than refreshSession/
         refreshSessionNy, no per-symbol day-history modal), new
         "XAU Liquidity Grab ⚠️ Экспериментально" settings group with a
         single enable toggle (autotrade toggle/leverage reachable via
         the settings API, no dedicated UI row this round — same "scope
         decision, not oversight" pattern used for risk_autotune's five
         constants in v0.93.0). Deliberately excluded from risk_autotune_
         pass() — this whole module is provisional, auto-tuning an
         unverified strategy's parameters isn't a sensible next step
         before the strategy itself has been validated.

v0.95.1 - fixed a real startup crash, per a direct Termux traceback
         screenshot: NameError: name "XAU_LG_SIGNAL_HISTORY" is not
         defined, at the STATE dict's "xau_lg_signals": deque(maxlen=
         XAU_LG_SIGNAL_HISTORY) line. Root cause: v0.95.0 defined the
         whole XAU_LG_* constants block right next to the module's
         functions (near the API section, far down the file), but STATE
         is constructed much earlier — Python executes top-to-bottom, so
         referencing a constant before its own definition line is a
         NameError, not something a docstring comment can paper over.
         Testing-methodology note, stated plainly rather than glossed
         over: every "compiles cleanly" claim across this session (and
         specifically for v0.95.0) was from py_compile, which only
         checks syntax — it does NOT execute module-level code, so it
         cannot catch a NameError caused by execution-order issues like
         this one. This bug should have been caught before shipping;
         it wasn't, because compiling isn't the same as running. Added
         an actual runtime smoke test to the verification process this
         time (timeout 8 python3 vp_poc_screener.py, checked stderr for
         a traceback) — confirmed the fixed version starts cleanly and
         all daemon threads (including xau_lg_backtest_loop/xau_lg_
         live_loop) run without error; the only errors seen were 403s
         from api.gateio.ws, which is this sandbox's own network
         restriction (no route to Gate.io here), not a code issue.
         Fix: moved the entire XAU_LG_* constants block (with its full
         explanatory header comment) to right after SESSION_NY_SIGNAL_
         HISTORY, before STATE is built — same position pattern already
         used for every other module's constants (Session/Session NY's
         own constants sit early for the same reason). Left a short
         pointer comment at the old location, next to the functions,
         explaining where the constants moved and why, so the code
         doesn't look like something's missing when read top-to-bottom
         from that point.

v0.95.2 - stopped _risk_autotune_log() from also calling log_error(),
         per a direct user screenshot showing 4 of 5 entries in the
         "Последние ошибки сканера" panel were routine RISK-AUTOTUNE
         adjustments, not errors — the user sent the screenshot
         specifically asking what had gone wrong, when nothing had.
         Root cause: v0.93.0 deliberately dual-logged risk-autotune
         entries through log_error() "for visibility," but STATE
         ["risk_autotune_log"] already has its own dedicated collapsible
         "Авто-тюнинг риска" panel in the header (built in that same
         version) — the log_error() call was pure redundancy that had
         the side effect of painting normal automated behavior red under
         an "ошибки" (errors) heading. Removed the log_error() call;
         the STATE list append (which feeds the dedicated panel) is
         untouched. reconcile_positions_and_orders()'s own "cancelled N
         orphaned trigger order(s)" line has the same informational-not-
         error framing and predates this session's work, but has no
         separate display location the way risk-autotune's entries do —
         left as-is rather than removing its only visibility, flagged
         here for awareness rather than silently left unmentioned.
         Verification for this release included an actual runtime smoke
         test (not just py_compile), per the lesson from v0.95.1's
         startup crash — confirmed clean.

v0.95.3 - fixed a real formula bug in _risk_autotune_min_rr(), per direct
         user evidence: a live scalp trade (CYS_USDT, RR=0.415) passed
         SCALP_MIN_RR despite that filter having been auto-tuned to
         0.368 using math that assumed every loss costs exactly -1R.
         Real scalp LOSS MAE averaged -1.171R at the time — the SAME
         overshoot _risk_autotune_sl_mult() was separately, correctly
         reacting to (scalp_sl_buffer_mult 0.65->0.7) in the very same
         autotune pass. The two rules were using inconsistent pictures
         of reality: sl_mult tuning knew losses cost 1.171R, but min_rr
         tuning's breakeven formula silently assumed 1.0R, computing a
         breakeven of ~0.36 instead of the honest ~0.42 once the same
         overshoot data both rules already had is actually used. At
         0.415, the CYS_USDT trade sat between those two numbers — it
         should have been rejected, and wasn't, specifically because of
         this gap.
         Fix: _risk_autotune_min_rr() gained an avg_loss_mae_r parameter
         (optional, defaults to no adjustment for backward compat);
         breakeven_rr is now (1-winrate)/winrate * abs(avg_loss_mae_r)
         instead of assuming the multiplier is 1. risk_autotune_pass()
         reordered in all three call sites (EMA/Divergence/Scalp) so the
         loss-MAE stat each module already computes for its own sl_mult
         tuning call gets computed first and passed into the min_rr call
         too, rather than each rule pulling its own inconsistent picture
         of the same underlying data. Session has no reverse-eligible
         min_rr call, so it's unaffected. Verified with both py_compile
         and an actual runtime start (per the v0.95.1 lesson) before
         pushing.

v0.95.4 - same overshoot fix as v0.95.3, applied to _risk_autotune_
         reverse() — found by the user asking about a Divergence
         screenshot right after the min_rr fix, which prompted checking
         whether the sibling function had the identical bug. It did:
         the div_invert_signals flip logged earlier ("ev=-0.195") used
         the same assume-losses-cost-exactly-1R math. Real Divergence
         LOSS MAE averaged -4.382R (median -1.84R) — honest EV was
         between -0.6R (by median, less outlier-sensitive) and -1.8R
         (by average), both far more solidly negative than -0.195
         suggested. The nominal number wasn't WRONG about direction
         (still negative, flip was still the right call) but understated
         by how much, which matters for judging how much margin the
         RISK_AUTOTUNE_REVERSE_EV_THRESHOLD cutoff (-0.03) actually has.
         _risk_autotune_reverse() gained the same avg_loss_mae_r
         parameter and overshoot multiplier as _risk_autotune_min_rr();
         EMA's and Divergence's reverse call sites now pass their
         already-computed loss_mae stat through, matching the min_rr
         call sites right next to them. Session's reverse call is
         unchanged — no MFE/MAE tracking exists for Session's signals to
         compute an overshoot from (same known gap noted in v0.94.0), so
         it keeps using the nominal assumption, honestly the best
         available given that data limitation rather than a remaining
         bug. Verified with both py_compile and an actual runtime start
         before pushing.

v0.95.5 - new TP-extend rule for risk-autotune, per direct user request
         to have the system also catch the "winning trades run well past
         the current target" pattern it had been missing entirely — every
         existing rule only ever tightened risk (MIN_RR filters, SL
         width, reverse flags), nothing ever extended a target even when
         evidence pointed that way. Found manually for Volume/breakout
         earlier in this session (median WIN MFE 3.641R against a fixed
         RR=2 target — wins running nearly double the target before
         reversing), the same underlying pattern the app's own UI hint
         text already names ("если WIN MFE заметно больше текущего RR —
         тейк можно двигать дальше").
         New _risk_autotune_tp_extend(): scales a fixed TP_PCT by (win_
         mfe_r / current_rr), bounded to +/-10% per pass (RISK_AUTOTUNE_
         TP_STEP_RATIO) within a 0.3%-5% range (RISK_AUTOTUNE_TP_PCT_
         BOUNDS), ignoring anything within 15% of current (RISK_
         AUTOTUNE_TP_TOLERANCE_RATIO) — same bounded-step, cooldown-
         gated, sample-size-gated shape as every other nudge in this
         system, mirroring _risk_autotune_sl_mult()'s two-directional
         design but for the reward side instead of risk. Deliberately
         uses mfe_r_wins_AT_CLOSE, not the full-24h-window MFE stat — the
         UI already labels that window "не для оценки конкретной
         сделки" since it includes post-close movement that isn't
         tradeable under the current exit logic, and feeding it into an
         automatic adjustment would be inconsistent with that existing
         caution.
         Applies ONLY to EMA_TP_PCT and DIV_TP_PCT (both newly added to
         the settings system this round, same persistence reasoning as
         every other constant risk-autotune touches). Explicitly does
         NOT apply to Volume or Scalp: both already run their own
         per-symbol grid search over multiple target sizes (PARAM_GRID_RR
         for Volume, SCALP_TARGET_PCTS for Scalp) — a second, separate
         global TP nudge would just fight that existing per-symbol
         search rather than complement it. Also doesn't apply to
         Session/Session NY: non-inverted TP is the opposite edge of
         that day's range, a different value every signal, not a single
         fixed constant there's anything to nudge.
         risk_autotune_pass() extended for EMA and Divergence to also
         call this after their existing min_rr/sl_mult/reverse checks,
         using the mfe_r_wins_at_close and rr_all stats those blocks
         already compute rather than re-fetching anything. Verified with
         both py_compile and an actual runtime start before pushing.

v0.95.6 - fixed a real bug in Volume's per-symbol grid search (_optimize_
         for_reason(), feeding SYMBOL_OVERRIDES), found by directly
         checking whether it was actually exploring PARAM_GRID_RR's wider
         options in practice or just defaulting to the easiest one, per
         a direct user follow-up question. It was: the selection
         criterion picked whichever (lookback, hvn, rr, buffer) combo had
         the HIGHEST RAW WINRATE, tie-broken only by trade count — never
         weighing the target size itself. This mechanically biases
         toward the SMALLEST rr in PARAM_GRID_RR (1.5) almost regardless
         of true edge, since a nearer target is inherently easier to
         touch before price reverses — the exact same class of oversight
         already found and fixed for Scalp's own target selection in
         v0.91.0 (that one had a premature `break` after the largest
         qualifying target; this one never even weighed target size at
         all). Confirmed this genuinely reaches live trading, not just
         display: scan_symbol() reads SYMBOL_OVERRIDES[symbol]["breakout"]
         ["rr"] directly for real entries/SL/TP, falling back to RR_
         BREAKOUT only when no override exists yet.
         Fix: selection now maximizes EV (winrate*rr - (1-winrate)*1)
         instead of raw winrate. No overshoot correction applied here
         (unlike risk-autotune's v0.95.3/v0.95.4 fixes) — backtest_
         params() simulates SL/TP hits directly against historical
         candle highs/lows with no slippage modeled, so within this
         specific backtest a loss genuinely costs exactly -1R by
         construction; nominal EV is the internally-consistent metric
         for it, not an approximation that needs correcting.
         /api/overrides (pre-existing endpoint, just newly relevant) now
         reflects the corrected per-symbol rr choices as the optimizer
         re-runs on its normal 48h refresh cycle — useful for directly
         checking the resulting RR distribution across symbols instead
         of assuming the mechanism works. Verified with both py_compile
         and an actual runtime start before pushing.

v0.95.7 - full audit pass, per direct user request ("найди все проблемы
         и баги еще вдруг есть") rather than a specific symptom report.
         Ran pyflakes (found and cleaned up 2 genuinely dead variables —
         interval_sec in the scalp signal path, left over from before
         timeouts were removed; lookback_sec in xau_lg_scan_symbol_live,
         left over from an earlier draft — and 5 redundant `global`
         declarations in apply_settings() for leverage constants that
         are actually mutated via globals()[name]=v in a loop, not
         direct assignment; all cosmetic, zero behavior change).
         Cross-checked SETTINGS_KEYS against get_settings()'s return
         dict both directions — fully consistent (telegram_configured
         is the only get_settings()-only field, and that's intentional:
         a read-only derived flag, not a user-set value). Checked every
         apply_settings() handler and every risk-autotune _set_*
         function for assignments missing their `global` declaration
         (which would silently create a local variable instead of
         mutating the module global, and the change would appear to
         "work" per the caller's return value but never actually
         persist) — none found.
         Found ONE real, high-impact bug via systematic cross-reference
         (every function signature using an ALL-CAPS default parameter,
         checked against every constant that's ever reassigned via
         `global` anywhere in the file): compute_ema_tp_sl() and
         compute_div_tp_sl() declared tp_pct=EMA_TP_PCT/DIV_TP_PCT and
         atr_mult=EMA_SL_ATR_MULT/DIV_SL_ATR_MULT as literal default
         parameter values. Python evaluates a default parameter value
         ONCE, at function-definition time (module load) — not on every
         call — so whatever EMA_TP_PCT/DIV_TP_PCT/EMA_SL_ATR_MULT/
         DIV_SL_ATR_MULT happened to be at process startup got frozen
         into these two functions' own __defaults__ forever. Confirmed
         both real call sites (scan_symbol_divergence, the EMA
         equivalent) call with only direction/entry/atr, relying
         entirely on the (broken) default — meaning every risk_autotune_
         pass() adjustment to these four values since process start was
         successfully computed, logged to STATE["risk_autotune_log"],
         AND persisted to settings.json (save_settings() genuinely wrote
         the new number), but had ZERO effect on actual live SL/TP
         calculation: real signals kept using the ORIGINAL startup
         value the whole time. This was silent — no error, no crash,
         the log entries looked exactly like every other successful
         adjustment. Not found from a live symptom; found by directly
         auditing for this exact class of bug after fixing an unrelated
         one (v0.93.0's own persistence work) raised the general
         question of whether a "successful" auto-tune write actually
         reaches live behavior.
         Fix: both functions' tp_pct/atr_mult/fallback_rr parameters now
         default to None and get resolved to the CURRENT global inside
         the function body on every call, instead of being bound as
         literals in the signature. Verified BEHAVIORALLY, not just by
         reading the code: imported the module, called compute_ema_tp_sl
         once, mutated EMA_TP_PCT directly (same as risk-autotune's own
         setter does), called it again, confirmed the returned TP
         actually changed between the two calls.
         Systematically checked every other function in the file using
         an ALL-CAPS constant as a default parameter value (49 found)
         against every constant that's mutated anywhere via `global` —
         confirmed these were the only two instances of this bug
         pattern; everything else either defaults to a genuinely fixed
         constant (safe, since "evaluated once" and "never changes" are
         equivalent) or is a settings-controlled toggle that's already
         read fresh from the global inside the function body (like
         EMA_MIN_RR's own `if EMA_MIN_RR > 0` filter check) rather than
         captured as a default parameter.
"""

import os
import json
import time
import math
import threading
import traceback
import queue
import datetime
import hmac
import hashlib
from decimal import Decimal
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, jsonify, request, Response

APP_VERSION = "0.95.7"

# ----------------------------------------------------------------------------
# Config (env-overridable, no secrets required for base functionality)
# ----------------------------------------------------------------------------
GATE_BASE = "https://api.gateio.ws/api/v4"
GATE_BASE_HOST = "https://api.gateio.ws"  # host only, no /api/v4 — gate_signed_request builds the full path itself since the signature needs the /api/v4-prefixed path separately from the host

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
WORKERS = int(os.environ.get("VP_WORKERS", 8))  # was 12 (before that, 8) — lowered back per direct user request after live error logs showed repeated "network error after 2 retries" on read timeouts even WITH the v0.73.0/v0.75.0 retry logic in place, suggesting 12 concurrent requests was routinely saturating the actual available mobile bandwidth rather than any single request being unlucky
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
SIGNAL_TIMEOUT_SEC = int(os.environ.get("VP_SIGNAL_TIMEOUT", 6 * 3600))  # close as TIMEOUT if neither TP/SL hit — shared by Volume and Divergence
EMA_SIGNAL_TIMEOUT_SEC = int(os.environ.get("VP_EMA_SIGNAL_TIMEOUT", 12 * 3600))  # separate from SIGNAL_TIMEOUT_SEC above, per direct user request — widened to 12h (doubled from the shared 6h default) since EMA's timeout rate looked high (12/46 closed) at the current 6h; adjustable live via settings, doesn't touch Volume/Divergence's shared timeout
SIGNAL_MAX_STALENESS_SEC = int(os.environ.get("VP_SIGNAL_MAX_STALENESS_SEC", 300))  # 5 min (raised from 3 min — 60s before that, 5 min before that) — a full universe scan cycle now regularly takes ~296s (observed live), since v0.76.0 deliberately lowered WORKERS 12->8 to fix network reliability, which slowed the cycle back down. 180s was too tight for that slower cadence: live data showed "устарел: 17" leading Volume's own rejection counts for a cycle where candidates were actually being found (not the earlier zero-candidate problem) — most of them just aged past 180s before the scan reached them. Raised to roughly match the observed full-cycle duration rather than picked arbitrarily. Entry/SL/TP are computed off that candle's close (sig["price"]), but the real market order fills at whatever price exists NOW — if too much time has passed, price has likely already moved well past where the signal detected it, so the trade enters late into an already-spent move rather than near its start. Reject (skip) the signal if now - candle_close_time exceeds this.
MFE_TRACK_SEC = int(os.environ.get("VP_MFE_TRACK_SEC", 24 * 3600))  # keep measuring max favorable/adverse excursion this long after detection, past TP/SL/timeout
# Breakeven stop-move for breakout signals only (bounce is disabled by
# default — see BOUNCE_ENABLED below). Live stats showed ~25% of breakout
# losses had traveled over 1R in favor before reversing to hit the
# original stop — moving the stop to breakeven once price proves the
# trade right by BREAKOUT_BREAKEVEN_TRIGGER_R turns those into scratches
# instead of full losses, without touching TP.
BREAKOUT_BREAKEVEN_TRIGGER_R = float(os.environ.get("VP_BREAKOUT_BREAKEVEN_TRIGGER_R", 0.8))
BREAKOUT_BREAKEVEN_BUFFER_PCT = float(os.environ.get("VP_BREAKOUT_BREAKEVEN_BUFFER_PCT", 0.001))  # 0.1% beyond pure entry, in the trade's favor — so a dead-even wick still covers fees/slippage instead of landing exactly on entry

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
# ATR-based SL for divergence, v0.88.0 — mirrors EMA's v0.65.0 fix, per
# direct user request after live MFE/MAE data showed the same root
# cause: DIV_RR-derived SL is a fixed 0.5% (DIV_TP_PCT/DIV_RR) regardless
# of the symbol's actual volatility, and LOSS MAE at close averaged
# 3.23R / median 1.851R — losses were overshooting the nominal -1.0R
# stop by 3x+ on average, an even bigger gap than EMA's original ~2x
# before its own ATR fix. A fixed % can't adapt per-symbol; ATR can.
DIV_SL_MODE = os.environ.get("VP_DIV_SL_MODE", "atr")  # "atr" or "fixed_pct" — fixed_pct reproduces the exact old DIV_RR-derived behavior, for comparison/rollback
DIV_SL_ATR_MULT = float(os.environ.get("VP_DIV_SL_ATR_MULT", 1.5))  # SL = ATR(EMA_DIAG_ATR_PERIOD) * this, in price units — same period constant EMA's own ATR diagnostic/SL already uses, not a separate one
DIV_MIN_RR = float(os.environ.get("VP_DIV_MIN_RR", 0))  # 0 = disabled by default — mirrors EMA_MIN_RR, added for symmetry so the auto-tuner (v0.93.0) has the same lever on divergence that it already has on EMA
# TP stays a fixed % of entry (DIV_TP_PCT) — only the STOP moves to ATR,
# same split EMA uses. RR is no longer one constant; every signal now
# carries its own "rr" field (tp_dist / atr-based-risk), and
# compute_divergence_stats() exposes rr_all/rr_wins/rr_losses for the
# header display that used to just show the old fixed DIV_RR.
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
SESSION_INVERT_SIGNALS = os.environ.get("VP_SESSION_INVERT_SIGNALS", "0") == "1"  # per direct user request after live session winrate looked bad (~11%) — mirrors DIV_INVERT_SIGNALS/EMA_INVERT_SIGNALS, but with its OWN sizing rather than just flipping direction and reusing the original sl/tp: the ORIGINAL sl distance (sweep_extreme + SESSION_SL_BUFFER_PCT, i.e. the same risk a non-inverted trade would have taken) becomes the inverted trade's own SL distance too, applied on the opposite side of entry — TP is fixed at 2x that same risk (RR=2), not the original TP (opposite side of the consolidation range, an arbitrary distance tied to range width rather than to risk). Implemented inside detect_session_manipulation() itself (not as a separate post-processing step) so both live scanning AND the historical backtest ranking see the same inverted direction/sizing consistently — avoids the kind of sign mismatch found and fixed for divergence's pivot-stability stat, where the live/backtest paths could disagree about which direction was "the one actually traded."
SESSION_SL_MULT = float(os.environ.get("VP_SESSION_SL_MULT", 1.5))  # per direct user request after a live example (CYS_USDT) hit its SL — multiplies the base risk distance (sweep_extreme + SESSION_SL_BUFFER_PCT vs entry) before it's used for the inverted trade's SL AND its RR=2 TP, so both scale together and RR stays exactly 2 at the new, wider stop. Only affects SESSION_INVERT_SIGNALS's own sizing (see its comment above) — the non-inverted trade still uses its original sl/tp (sweep-based stop, opposite-range-edge take), untouched by this.
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
EMA_TP_PCT = float(os.environ.get("VP_EMA_TP_PCT", 0.015))  # kept at round 3's value — user only wanted the stop reverted, not the take
EMA_RR = float(os.environ.get("VP_EMA_RR", 3.75))  # SL reverted to round 2's 0.4% while keeping TP at round 3's 1.5% (RR = 1.5/0.4 = 3.75) — round 3's SL=0.3%/RR=5.0 dropped the win rate to 35.5% (11W/20L); even though that was still profitable on paper (breakeven ~16.7% at RR=5), the user wants the wider round-2 stop back, just not a smaller take. NOW ONLY a fallback (see EMA_SL_MODE below) for when ATR isn't available — not the primary SL basis anymore.
# ATR-based SL, v0.65.0 — per direct user request, after the fixed-%
# stop's own MFE/MAE-at-close numbers exposed the real problem: WIN MFE
# at close averaged 7.17R against a nominal RR of 3.75, and LOSS MAE at
# close averaged 2.187R against a nominal risk of 1R — both roughly 2x
# their nominal levels, meaning a single 1h candle routinely blows
# through both the fixed 0.4% SL and the 1.5% TP by a wide margin. That
# isn't noise, it's the stop being sized far too tight for what a 1h
# candle on these symbols actually moves — a fixed % can't adapt
# per-symbol, ATR can.
EMA_SL_MODE = os.environ.get("VP_EMA_SL_MODE", "atr")  # "atr" or "fixed_pct" — fixed_pct reproduces the old EMA_RR-derived behavior exactly, for comparison/rollback
EMA_SL_ATR_MULT = float(os.environ.get("VP_EMA_SL_ATR_MULT", 1.5))  # SL = ATR(EMA_DIAG_ATR_PERIOD) * this, in price units
EMA_MIN_RR = float(os.environ.get("VP_EMA_MIN_RR", 0.7))  # was 0.3 — raised per direct user request after live stats showed a real gap between the average RR (0.923, EV≈+0.075R at 55.9% winrate) and the median RR (0.717, EV≈-0.040R at the same winrate) — the "typical" trade was already sub-breakeven even though the average looked fine, and 0.3 (picked only to clear one extreme outlier, UB_USDT at RR≈0.094) was nowhere near catching that. Breakeven RR at the live 55.9% winrate works out to ≈0.789 (from winrate*RR = 1-winrate); 0.7 sits just under that on purpose — cuts sub-breakeven trades without also cutting ones sitting right at the margin, which could still be fine as winrate estimate itself has noise. TIMEOUT closes told the same story from another angle: avg realized R was +0.142 but median was -0.142 — opposite signs, meaning a few large positive outliers were carrying the average while the typical timeout was already a small loss.
# ADX regime filter, v0.72.0 — per direct user request to research and
# propose an actual filter for EMA's whipsaw problem (rather than the
# home-grown recent_crossover_count proxy from v0.62.0). ADX (Wilder,
# 1978) is the standard, decades-old answer to exactly this: it measures
# trend STRENGTH directly, and the near-universal finding across
# sources is that raw EMA crossovers run ~35-40% win rate in choppy/
# range-bound conditions, while requiring ADX above ~20-25 before
# trading a crossover is the standard fix. Enabled by default (unlike
# EMA_MIN_RR/EMA_MIN_GAP_PCT below) because this is a well-established,
# literature-backed threshold, not a guess needing our own data first.
EMA_ADX_FILTER_ENABLED = os.environ.get("VP_EMA_ADX_FILTER_ENABLED", "1") == "1"
EMA_ADX_MIN = float(os.environ.get("VP_EMA_ADX_MIN", 20))  # Wilder's own "trending" cutoff is 25; 20 is the more commonly cited "at least not dead flat" floor — starting here since it's the least aggressive cut, easy to raise toward 25 later if 20 doesn't do enough
# Minimum EMA7/EMA14 separation at signal time — the "buffer zone
# before confirming a cross" idea several sources also recommend,
# using the ema_gap_pct diagnostic we already log (v0.62.0). Off by
# default (unlike ADX above): there's no established universal
# threshold for this the way there is for ADX, and it needs to be
# calibrated against ema_gap_pct's own win/loss breakdown once enough
# adx-filtered data has accumulated, not guessed at.
EMA_MIN_GAP_PCT = float(os.environ.get("VP_EMA_MIN_GAP_PCT", 0))  # 0 = disabled, in the same % units as ema_gap_pct
# TP stays a fixed % of entry (EMA_TP_PCT) — only the STOP moves to ATR.
# Consequence: RR is no longer one constant, it varies signal to signal
# (tp_pct-distance / atr-based-risk) depending on each symbol's own
# volatility at signal time. Every signal now carries its own "rr" field
# instead of relying on a single global; compute_ema_stats() exposes
# rr_avg/rr_median across closed signals for the header display that
# used to just show the old constant.
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
SCALP_SL_BUFFER_MULT = float(os.environ.get("VP_SCALP_SL_BUFFER_MULT", 0.25))  # SL = p90_adverse_pct * (1 + this) — raised back up from 0.05, per direct user request after live LOSS MAE data (now n=26, a real sample — the earlier 0.05 cut was explicitly made cautious because it was based on n=1 loss) showed avg -1.167R / median -1.065R: losses were overshooting the nominal -1.0R stop by ~17% on average, meaning the 0.05 buffer wasn't actually covering real adverse excursion including slippage/wicks. Back-of-envelope from that overshoot: current_sl_pct = p90_adverse*1.05, and avg realized loss = -1.167*current_sl_pct ≈ p90_adverse*1.225 — so the true P90 estimate itself was being undershot by roughly that much once real execution is factored in. 0.25 targets bringing the stop back in line with what real losses actually reach, rather than picking an arbitrary round number; still needs verifying against the NEXT batch of live losses once they accumulate under the new buffer, same as the original 0.2->0.05 decision was based on watching real data rather than theory alone.
SCALP_SIGNAL_TOP_N = int(os.environ.get("VP_SCALP_SIGNAL_TOP_N", 1))  # only fire a live signal for the top-N ranked symbols by score each cycle, not every qualifying one
SCALP_SAFETY_MARGIN = float(os.environ.get("VP_SCALP_SAFETY_MARGIN", 1.5))  # liquidation buffer must exceed the coin's own historical p90 adverse move by this factor before a target/leverage combo is flagged "safe"
SCALP_MIN_HIT_RATE = float(os.environ.get("VP_SCALP_MIN_HIT_RATE", 60.0))  # a target below this hit-rate isn't worth recommending even if technically "safe"
SCALP_MIN_RR = float(os.environ.get("VP_SCALP_MIN_RR", 0.5))  # per direct user request after live data showed the SL averaging ~3x the target (RR~0.33) even on EV-positive configs — real SL is p90_adverse_pct-based (v0.87.0's SCALP_SL_BUFFER_MULT), left untouched here on purpose: rather than artificially tightening a stop below what real adverse moves actually reach (which would just convert would-be wins into losses, undermining the whole point of the P90-based sizing), this REJECTS candidates whose target/sl_pct_est ratio doesn't clear this bar — same "filter, don't distort the underlying measurement" approach as EMA_MIN_RR. 0.5 means SL can be at most 2x the target, down from the ~3x average that prompted this.

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
BOUNCE_ENABLED = os.environ.get("VP_BOUNCE_ENABLED", "0") == "1"  # disabled by default per user request — live stats showed bounce winrate ~16.7% (1W/5L) vs breakout's ~56% (5W/4L); module code kept intact (toggle only) so it can be re-enabled for comparison later rather than ripped out
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
VOL_CONFIRM_RATIO = float(os.environ.get("VP_VOL_CONFIRM_RATIO", 1.25))  # trigger bar volume must be >= this multiple of the average of the preceding VOL_CONFIRM_LOOKBACK bars — was 1.15x (too weak), raised to 1.4x, now lowered to this middle ground per direct user request after live stats showed "объём: 12" leading the rejection counts for a scan cycle — 1.4x looked too strict once actually observed against live data

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
TELEGRAM_ALERTS_SESSION_NY = os.environ.get("VP_TG_ALERTS_SESSION_NY", "1") == "1"
TELEGRAM_ALERTS_XAU_LG = os.environ.get("VP_TG_ALERTS_XAU_LG", "1") == "1"
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
SESSION_MAX_TREND_RATIO = float(os.environ.get("VP_SESSION_MAX_TREND_RATIO", 0.5))  # net directional drift across the range, as a fraction of range height — reject if the "consolidation" is really still trending in one direction rather than choppy/flat (per user's annotated screenshot: the zone before the session should be flat, no clear trend)
SESSION_MAX_THRUST_BARS = int(os.environ.get("VP_SESSION_MAX_THRUST_BARS", 3))  # the sweep and the close-back-inside confirmation can be up to this many bars apart — a short thrust, not strictly the same candle, per the reference chart (2-3 candle burst, not a single bar)
SESSION_BACKTEST_DAYS = int(os.environ.get("VP_SESSION_BACKTEST_DAYS", 30))  # was 60 — Gate enforces a hard "from" floor of ~10000 candles back from now (added without notice ~Feb 2026); for 5m candles that's ~34.7 days, so 30 leaves margin
SESSION_UNIVERSE_SIZE = int(os.environ.get("VP_SESSION_UNIVERSE_SIZE", 50))  # reduced from 100 — user wants the most liquid coins specifically, not a broad tail; already sorted by 24h volume descending, this just cuts deeper into that ranking
SESSION_MIN_SAMPLE = int(os.environ.get("VP_SESSION_MIN_SAMPLE", 8))  # don't rank a symbol's backtest as meaningful with fewer closed sessions than this
SESSION_SIGNAL_HISTORY = 200
SESSION_REFRESH_SEC = int(os.environ.get("VP_SESSION_REFRESH_SEC", 24 * 3600))  # batch backtest job — once a day is plenty, one new day of data per cycle anyway

# ----------------------------------------------------------------------------
# Session-open manipulation, New York variant (v0.94.0) — per direct user
# request after the original (London/Frankfurt, 10:00 Moscow) session module
# showed a promising live streak. Explicitly a FULL, INDEPENDENT duplicate,
# not a generalization of the original into a multi-session system — the
# user was specific that the original must stay completely untouched (zero
# refactor risk to something already working), even at the cost of code
# duplication across this whole section. Every constant, function, STATE
# key, thread, and API endpoint below has its own SESSION_NY_ name; nothing
# here is imported or reused from the original except pure, already-generic
# helpers that don't know or care which session they're serving (get_candles_
# range, get_tickers, INTERVAL_SECONDS, fetch_candles_concurrent, has_open_
# signal_any_module — which DOES get a new "session_ny_signals" entry added
# to its own lists dict, the one deliberate touch to shared code, since
# skipping that would let this module stack a position on a symbol another
# module already has open, defeating the whole point of that check).
# New York open: 16:30 Moscow time (13:30 UTC) — the half-hour offset is why
# session_ny_open_utc_ts() needs its own minute-aware implementation; the
# original session_open_utc_ts() hardcodes minute=0.
# ----------------------------------------------------------------------------
SESSION_NY_ENABLED = os.environ.get("VP_SESSION_NY_ENABLED", "1") == "1"
SESSION_NY_UTC_OFFSET_HOURS = float(os.environ.get("VP_SESSION_NY_UTC_OFFSET_HOURS", 3))  # same Moscow reference as the original — no DST, fixed UTC+3
SESSION_NY_OPEN_HOUR_LOCAL = int(os.environ.get("VP_SESSION_NY_OPEN_HOUR_LOCAL", 16))  # 16:30 Moscow = New York open
SESSION_NY_OPEN_MINUTE_LOCAL = int(os.environ.get("VP_SESSION_NY_OPEN_MINUTE_LOCAL", 30))
SESSION_NY_RANGE_TF = os.environ.get("VP_SESSION_NY_RANGE_TF", "5m")
SESSION_NY_RANGE_START_UTC_HOUR = int(os.environ.get("VP_SESSION_NY_RANGE_START_UTC_HOUR", 7))  # consolidation range spans [this UTC hour, NY open) — starts at the ORIGINAL session's own open (07:00 UTC = 10:00 Moscow), i.e. the London/Frankfurt session itself, mirroring how the original range starts at the PRIOR (Asian) session's boundary
SESSION_NY_MANIPULATION_WINDOW_MIN = int(os.environ.get("VP_SESSION_NY_MANIPULATION_WINDOW_MIN", 30))
SESSION_NY_SL_BUFFER_PCT = float(os.environ.get("VP_SESSION_NY_SL_BUFFER_PCT", 0.005))
SESSION_NY_MIN_RANGE_PCT = float(os.environ.get("VP_SESSION_NY_MIN_RANGE_PCT", 0.003))
SESSION_NY_MAX_TREND_RATIO = float(os.environ.get("VP_SESSION_NY_MAX_TREND_RATIO", 0.5))
SESSION_NY_MAX_THRUST_BARS = int(os.environ.get("VP_SESSION_NY_MAX_THRUST_BARS", 3))
SESSION_NY_BACKTEST_DAYS = int(os.environ.get("VP_SESSION_NY_BACKTEST_DAYS", 30))
SESSION_NY_UNIVERSE_SIZE = int(os.environ.get("VP_SESSION_NY_UNIVERSE_SIZE", 50))
SESSION_NY_MIN_SAMPLE = int(os.environ.get("VP_SESSION_NY_MIN_SAMPLE", 8))
SESSION_NY_SIGNAL_HISTORY = 200

# ============================================================================
# EXPERIMENTAL: XAU Liquidity Grab (v0.95.0) — constants
# ----------------------------------------------------------------------------
# Every name in this module is prefixed XAU_LG_ / xau_lg_ specifically so the
# WHOLE module can be found and deleted later with one search, per direct
# user request ("делай так, чтобы потом удалить можно было") — this reflects
# genuine uncertainty about whether the underlying idea holds up, not just
# code hygiene. Source: an Instagram post (trendwisdom/pranamghagare)
# claiming 76% win rate / <2% drawdown on a XAU/USD strategy — treated with
# real skepticism, not taken at face value: the claim is an unverifiable
# screenshot over a ~1-month window, with a "comment for the full report in
# DMs" / "comment for a free prop-firm guide" structure, i.e. a lead-
# generation funnel, not a published, checkable result. Implemented anyway
# because the underlying PATTERN (sweep a level, close back inside, trade
# the reversal with a trend filter) is a real, testable idea structurally
# similar to what Session/Session NY already do — worth actually
# backtesting on this app's own data rather than trusting the screenshot.
# Strategy as described across the 8 slides:
#   1. EMA(30) trend filter: close > EMA -> longs only, close < EMA -> shorts
#   2. Support/resistance from swing pivots, LEFT=1/RIGHT=1 bars (LuxAlgo's
#      "Support and Resistance Levels with Breaks" indicator at its default-
#      minus-14 sensitivity — deliberately tight/noisy, not a generalized
#      pivot config elsewhere in this app)
#   3. On a 15m candle: wick below support but CLOSE back above it (or wick
#      above resistance but close back below) = confirmed "liquidity grab"
#   4. Entry at the top of that candle (its high) for a long, stop at the
#      candle's low, fixed 1:1 risk:reward — mirrored for shorts
# Universe restricted to actual gold-tracking symbols only, per the user's
# own framing ("индикатор ПО ЗОЛОТУ") rather than the app's usual full
# 150-200 symbol universe — this was never claimed to generalize beyond
# gold, and diluting it across everything would just be testing a different,
# unstated hypothesis.
# Constants are placed HERE (not next to the module's functions further
# down) specifically because STATE (constructed shortly after this point)
# references XAU_LG_SIGNAL_HISTORY at construction time — Python executes
# top-to-bottom, so the constant must exist before STATE does. Functions
# stay where they were, right before the API section; see that location's
# own short pointer comment.
# ============================================================================
XAU_LG_ENABLED = os.environ.get("VP_XAU_LG_ENABLED", "1") == "1"
XAU_LG_SYMBOLS = [s.strip() for s in os.environ.get("VP_XAU_LG_SYMBOLS", "XAU_USDT,XAUT_USDT,PAXG_USDT").split(",") if s.strip()]
XAU_LG_TF = os.environ.get("VP_XAU_LG_TF", "15m")
XAU_LG_EMA_PERIOD = int(os.environ.get("VP_XAU_LG_EMA_PERIOD", 30))
XAU_LG_PIVOT_LEFT = int(os.environ.get("VP_XAU_LG_PIVOT_LEFT", 1))
XAU_LG_PIVOT_RIGHT = int(os.environ.get("VP_XAU_LG_PIVOT_RIGHT", 1))
XAU_LG_RR = float(os.environ.get("VP_XAU_LG_RR", 1.0))  # fixed 1:1, per the source's own stated rule — not auto-tuned by risk_autotune_pass(), deliberately excluded since this whole module is provisional
XAU_LG_BACKTEST_DAYS = int(os.environ.get("VP_XAU_LG_BACKTEST_DAYS", 30))
XAU_LG_SIGNAL_HISTORY = 200
XAU_LG_REFRESH_SEC = int(os.environ.get("VP_XAU_LG_REFRESH_SEC", 3600))  # hourly backtest refresh — small fixed symbol list, cheap compared to Session's 50-symbol universe scan
XAU_LG_SCAN_INTERVAL_SEC = int(os.environ.get("VP_XAU_LG_SCAN_INTERVAL_SEC", 300))  # live scan cadence — 15m candles, checking every 5 min is plenty

SESSION_NY_REFRESH_SEC = int(os.environ.get("VP_SESSION_NY_REFRESH_SEC", 24 * 3600))
SESSION_NY_INVERT_SIGNALS = os.environ.get("VP_SESSION_NY_INVERT_SIGNALS", "0") == "1"
SESSION_NY_SL_MULT = float(os.environ.get("VP_SESSION_NY_SL_MULT", 1.5))


# ----------------------------------------------------------------------------
# Auto-trading — places real orders on Gate.io futures off the signals the
# modules above already generate. Opt-in per mode (Volume further split into
# bounce/breakout specifically, per direct request), market-order entry,
# DRY_RUN on by default so a fresh install never fires a real order until the
# person explicitly turns it off having seen dry-run behavior first. Position
# sizing is either a % of the current futures wallet balance or a flat $
# amount regardless of leverage, switched by AUTOTRADE_SIZE_MODE rather than
# both being live at once. Leverage: each mode uses ITS OWN signal's leverage
# field when the signal carries one (scalp already computes this per trade);
# modes whose signals don't carry a leverage recommendation (Volume/
# Divergence/EMA/Session) fall back to a configurable per-mode leverage.
# ----------------------------------------------------------------------------
AUTOTRADE_DRY_RUN = os.environ.get("VP_AUTOTRADE_DRY_RUN", "1") == "1"  # default ON — log what WOULD happen, no real orders, until explicitly turned off
AUTOTRADE_ENABLED_BOUNCE = os.environ.get("VP_AUTOTRADE_BOUNCE", "0") == "1"
AUTOTRADE_ENABLED_BREAKOUT = os.environ.get("VP_AUTOTRADE_BREAKOUT", "0") == "1"
AUTOTRADE_ENABLED_DIVERGENCE = os.environ.get("VP_AUTOTRADE_DIVERGENCE", "0") == "1"
AUTOTRADE_ENABLED_EMA = os.environ.get("VP_AUTOTRADE_EMA", "0") == "1"
AUTOTRADE_ENABLED_SCALP = os.environ.get("VP_AUTOTRADE_SCALP", "0") == "1"
AUTOTRADE_ENABLED_SESSION = os.environ.get("VP_AUTOTRADE_SESSION", "0") == "1"
AUTOTRADE_ENABLED_SESSION_NY = os.environ.get("VP_AUTOTRADE_SESSION_NY", "0") == "1"
AUTOTRADE_SIZE_MODE = os.environ.get("VP_AUTOTRADE_SIZE_MODE", "percent")  # "percent" or "fixed" — the single size value below is interpreted according to this
AUTOTRADE_SIZE_VALUE = float(os.environ.get("VP_AUTOTRADE_SIZE_VALUE", 2.0))  # percent: % of futures wallet balance; fixed: raw USD margin, leverage-independent either way
# Scalp gets its OWN size config, separate from the shared one above — per
# direct user request, by analogy with how leverage is already per-mode for
# bounce/breakout/divergence/ema/session. Defaults mirror AUTOTRADE_SIZE_MODE/
# VALUE at import time so an existing setup's scalp sizing doesn't silently
# change until the user actually customizes it via settings.
SCALP_SIZE_MODE = os.environ.get("VP_SCALP_SIZE_MODE", AUTOTRADE_SIZE_MODE)
SCALP_SIZE_VALUE = float(os.environ.get("VP_SCALP_SIZE_VALUE", AUTOTRADE_SIZE_VALUE))
AUTOTRADE_LEVERAGE_BOUNCE = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_BOUNCE", 10))
AUTOTRADE_LEVERAGE_BREAKOUT = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_BREAKOUT", 10))
AUTOTRADE_LEVERAGE_DIVERGENCE = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_DIVERGENCE", 10))
AUTOTRADE_LEVERAGE_EMA = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_EMA", 10))
AUTOTRADE_LEVERAGE_SESSION = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_SESSION", 10))
AUTOTRADE_LEVERAGE_SESSION_NY = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_SESSION_NY", 10))
AUTOTRADE_ENABLED_XAU_LG = os.environ.get("VP_AUTOTRADE_XAU_LG", "0") == "1"  # off by default — see the XAU_LG module's own header comment on why this strategy is treated as unverified
AUTOTRADE_LEVERAGE_XAU_LG = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_XAU_LG", 10))
AUTOTRADE_TRADE_HISTORY = 300

# ----------------------------------------------------------------------------
# Balance simulator — mirrors the real/dry-run auto-trader exactly: fires
# for the same signals, gated by the same per-mode autotrade-enabled
# toggles and the same sizing/leverage settings, just tracking a paper
# balance instead of (or alongside) a real/dry-run order — answers "what
# would my balance actually look like if my current auto-trade config had
# been running for real". Settles against each signal's own REAL eventual
# outcome (WIN/LOSS/TIMEOUT, whatever price it actually closed at) rather
# than a theoretical R-multiple, by keeping a live reference to the
# originating signal record and reading its outcome once resolved.
# ----------------------------------------------------------------------------
AUTOTRADE_SIM_START_BALANCE = float(os.environ.get("VP_AUTOTRADE_SIM_START_BALANCE", 30.0))
AUTOTRADE_SIM_FEE_PCT = float(os.environ.get("VP_AUTOTRADE_SIM_FEE_PCT", 0.0005))  # taker fee per side, matches SCALP_TAKER_FEE_PCT's own default
AUTOTRADE_SIM_TRADE_HISTORY = 500

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

HTTP_TIMEOUT = int(os.environ.get("VP_HTTP_TIMEOUT", 15))  # was a hardcoded 10 — raised per direct user request after repeated "Read timed out (read timeout=10)" errors persisted even with retries, giving each request more room before giving up under real mobile-network conditions

# --- basic runtime settings: scan modes + notifications, exposed through
# the header's settings button. Deliberately NOT the detailed indicator
# knobs (RR, buffer, thresholds, etc.) — those stay env-var-only. Backed
# by a small JSON file so a change made in the UI survives a restart.
SETTINGS_FILE = os.environ.get(
    "VP_SETTINGS_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "vp_poc_settings.json"),
)
# Kept in its own file, deliberately separate from SETTINGS_FILE — that file's
# whole contents get echoed back via GET /api/settings, and a secret has no
# business ever going out over that response, even to the same local UI.
CREDENTIALS_FILE = os.environ.get(
    "VP_CREDENTIALS_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "vp_poc_credentials.json"),
)
SETTINGS_KEYS = ("volume_profile_enabled", "divergence_enabled", "div_invert_signals", "div_min_rr", "bounce_enabled", "breakout_enabled",
                  "ema_enabled", "ema_invert_signals", "scalp_enabled", "scalp_signals_enabled", "session_enabled", "session_invert_signals", "session_ny_enabled", "session_ny_invert_signals", "xau_lg_enabled", "hourly_stats_enabled", "telegram_enabled",
                  "telegram_alerts_vp", "telegram_alerts_div", "telegram_alerts_ema", "telegram_alerts_hourly", "telegram_alerts_session",
                  "autotrade_dry_run", "autotrade_bounce", "autotrade_breakout", "autotrade_divergence", "autotrade_ema", "autotrade_scalp", "autotrade_session", "autotrade_session_ny", "autotrade_xau_lg",
                  "autotrade_size_mode", "autotrade_size_value",
                  "scalp_size_mode", "scalp_size_value",
                  "ema_min_rr", "ema_signal_timeout_hours",
                  "ema_adx_filter_enabled", "ema_adx_min", "ema_min_gap_pct",
                  "autotrade_leverage_bounce", "autotrade_leverage_breakout", "autotrade_leverage_divergence", "autotrade_leverage_ema", "autotrade_leverage_session", "autotrade_leverage_session_ny", "autotrade_leverage_xau_lg",
                  # v0.93.0 — moved into the settings system specifically so
                  # auto_tune_pass() can persist adjustments to these via the
                  # same save_settings() path everything else already uses,
                  # rather than inventing a second, separate persistence
                  # mechanism just for auto-tuned values. Also fixes a real
                  # (if minor) pre-existing gap: before this, these three were
                  # plain module constants with NO persistence at all, so any
                  # manual env-var override would silently revert on restart
                  # too — now they follow the same rules as ema_min_rr etc.
                  "scalp_min_rr", "scalp_sl_buffer_mult", "session_sl_mult", "ema_sl_atr_mult", "div_sl_atr_mult",
                  "ema_tp_pct", "div_tp_pct")


def get_settings():
    return {
        "volume_profile_enabled": VOLUME_PROFILE_ENABLED,
        "divergence_enabled": DIVERGENCE_ENABLED,
        "div_invert_signals": DIV_INVERT_SIGNALS,
        "div_min_rr": DIV_MIN_RR,
        "bounce_enabled": BOUNCE_ENABLED,
        "breakout_enabled": BREAKOUT_ENABLED,
        "ema_enabled": EMA_ENABLED,
        "ema_invert_signals": EMA_INVERT_SIGNALS,
        "scalp_enabled": SCALP_ENABLED,
        "scalp_signals_enabled": SCALP_SIGNALS_ENABLED,
        "session_enabled": SESSION_ENABLED,
        "session_invert_signals": SESSION_INVERT_SIGNALS,
        "session_ny_enabled": SESSION_NY_ENABLED,
        "session_ny_invert_signals": SESSION_NY_INVERT_SIGNALS,
        "xau_lg_enabled": XAU_LG_ENABLED,
        "hourly_stats_enabled": HOURLY_STATS_ENABLED,
        "telegram_enabled": TELEGRAM_ENABLED,
        "telegram_alerts_vp": TELEGRAM_ALERTS_VP,
        "telegram_alerts_div": TELEGRAM_ALERTS_DIV,
        "telegram_alerts_ema": TELEGRAM_ALERTS_EMA,
        "telegram_alerts_hourly": TELEGRAM_ALERTS_HOURLY,
        "telegram_alerts_session": TELEGRAM_ALERTS_SESSION,
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "autotrade_dry_run": AUTOTRADE_DRY_RUN,
        "autotrade_bounce": AUTOTRADE_ENABLED_BOUNCE,
        "autotrade_breakout": AUTOTRADE_ENABLED_BREAKOUT,
        "autotrade_divergence": AUTOTRADE_ENABLED_DIVERGENCE,
        "autotrade_ema": AUTOTRADE_ENABLED_EMA,
        "autotrade_scalp": AUTOTRADE_ENABLED_SCALP,
        "autotrade_session": AUTOTRADE_ENABLED_SESSION,
        "autotrade_session_ny": AUTOTRADE_ENABLED_SESSION_NY,
        "autotrade_xau_lg": AUTOTRADE_ENABLED_XAU_LG,
        "autotrade_size_mode": AUTOTRADE_SIZE_MODE,
        "autotrade_size_value": AUTOTRADE_SIZE_VALUE,
        "scalp_size_mode": SCALP_SIZE_MODE,
        "scalp_size_value": SCALP_SIZE_VALUE,
        "autotrade_leverage_bounce": AUTOTRADE_LEVERAGE_BOUNCE,
        "autotrade_leverage_breakout": AUTOTRADE_LEVERAGE_BREAKOUT,
        "autotrade_leverage_divergence": AUTOTRADE_LEVERAGE_DIVERGENCE,
        "autotrade_leverage_ema": AUTOTRADE_LEVERAGE_EMA,
        "ema_min_rr": EMA_MIN_RR,
        "ema_signal_timeout_hours": round(EMA_SIGNAL_TIMEOUT_SEC / 3600, 2),
        "ema_adx_filter_enabled": EMA_ADX_FILTER_ENABLED,
        "ema_adx_min": EMA_ADX_MIN,
        "ema_min_gap_pct": EMA_MIN_GAP_PCT,
        "autotrade_leverage_session": AUTOTRADE_LEVERAGE_SESSION,
        "autotrade_leverage_session_ny": AUTOTRADE_LEVERAGE_SESSION_NY,
        "autotrade_leverage_xau_lg": AUTOTRADE_LEVERAGE_XAU_LG,
        "scalp_min_rr": SCALP_MIN_RR,
        "scalp_sl_buffer_mult": SCALP_SL_BUFFER_MULT,
        "session_sl_mult": SESSION_SL_MULT,
        "ema_sl_atr_mult": EMA_SL_ATR_MULT,
        "div_sl_atr_mult": DIV_SL_ATR_MULT,
        "ema_tp_pct": EMA_TP_PCT,
        "div_tp_pct": DIV_TP_PCT,
    }



def apply_settings(updates):
    """Mutates the module-level flags directly — every place that checks
    them (scan_loop, scan_symbol, send_telegram, ...) reads the name at
    call time, not at import time, so this takes effect on the very next
    scan cycle / next alert, no restart needed."""
    global VOLUME_PROFILE_ENABLED, DIVERGENCE_ENABLED, DIV_INVERT_SIGNALS, DIV_MIN_RR, BOUNCE_ENABLED, BREAKOUT_ENABLED, EMA_ENABLED, EMA_INVERT_SIGNALS, SCALP_ENABLED, SCALP_SIGNALS_ENABLED, SESSION_ENABLED, SESSION_INVERT_SIGNALS, SESSION_NY_ENABLED, SESSION_NY_INVERT_SIGNALS, XAU_LG_ENABLED, HOURLY_STATS_ENABLED
    global TELEGRAM_ENABLED, TELEGRAM_ALERTS_VP, TELEGRAM_ALERTS_DIV, TELEGRAM_ALERTS_EMA, TELEGRAM_ALERTS_HOURLY, TELEGRAM_ALERTS_SESSION
    global AUTOTRADE_DRY_RUN, AUTOTRADE_ENABLED_BOUNCE, AUTOTRADE_ENABLED_BREAKOUT, AUTOTRADE_ENABLED_DIVERGENCE, AUTOTRADE_ENABLED_EMA, AUTOTRADE_ENABLED_SCALP, AUTOTRADE_ENABLED_SESSION, AUTOTRADE_ENABLED_SESSION_NY, AUTOTRADE_ENABLED_XAU_LG
    global AUTOTRADE_SIZE_MODE, AUTOTRADE_SIZE_VALUE
    global SCALP_SIZE_MODE, SCALP_SIZE_VALUE
    global EMA_MIN_RR
    global EMA_SIGNAL_TIMEOUT_SEC
    global EMA_ADX_FILTER_ENABLED, EMA_ADX_MIN, EMA_MIN_GAP_PCT
    global SCALP_MIN_RR, SCALP_SL_BUFFER_MULT, SESSION_SL_MULT
    global EMA_SL_ATR_MULT, DIV_SL_ATR_MULT
    global EMA_TP_PCT, DIV_TP_PCT
    if "volume_profile_enabled" in updates:
        VOLUME_PROFILE_ENABLED = bool(updates["volume_profile_enabled"])
    if "divergence_enabled" in updates:
        DIVERGENCE_ENABLED = bool(updates["divergence_enabled"])
    if "div_invert_signals" in updates:
        DIV_INVERT_SIGNALS = bool(updates["div_invert_signals"])
    if "div_min_rr" in updates:
        try:
            v = float(updates["div_min_rr"])
            if v >= 0:
                DIV_MIN_RR = v
        except (TypeError, ValueError):
            pass
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
    if "session_invert_signals" in updates:
        SESSION_INVERT_SIGNALS = bool(updates["session_invert_signals"])
    if "session_ny_enabled" in updates:
        SESSION_NY_ENABLED = bool(updates["session_ny_enabled"])
    if "session_ny_invert_signals" in updates:
        SESSION_NY_INVERT_SIGNALS = bool(updates["session_ny_invert_signals"])
    if "xau_lg_enabled" in updates:
        XAU_LG_ENABLED = bool(updates["xau_lg_enabled"])
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
    if "autotrade_dry_run" in updates:
        AUTOTRADE_DRY_RUN = bool(updates["autotrade_dry_run"])
    if "autotrade_bounce" in updates:
        AUTOTRADE_ENABLED_BOUNCE = bool(updates["autotrade_bounce"])
    if "autotrade_breakout" in updates:
        AUTOTRADE_ENABLED_BREAKOUT = bool(updates["autotrade_breakout"])
    if "autotrade_divergence" in updates:
        AUTOTRADE_ENABLED_DIVERGENCE = bool(updates["autotrade_divergence"])
    if "autotrade_ema" in updates:
        AUTOTRADE_ENABLED_EMA = bool(updates["autotrade_ema"])
    if "autotrade_scalp" in updates:
        AUTOTRADE_ENABLED_SCALP = bool(updates["autotrade_scalp"])
    if "autotrade_session" in updates:
        AUTOTRADE_ENABLED_SESSION = bool(updates["autotrade_session"])
    if "autotrade_session_ny" in updates:
        AUTOTRADE_ENABLED_SESSION_NY = bool(updates["autotrade_session_ny"])
    if "autotrade_xau_lg" in updates:
        AUTOTRADE_ENABLED_XAU_LG = bool(updates["autotrade_xau_lg"])
    if "autotrade_size_mode" in updates and updates["autotrade_size_mode"] in ("percent", "fixed"):
        AUTOTRADE_SIZE_MODE = updates["autotrade_size_mode"]
    if "autotrade_size_value" in updates:
        try:
            v = float(updates["autotrade_size_value"])
            if v > 0:
                AUTOTRADE_SIZE_VALUE = v
        except (TypeError, ValueError):
            pass
    if "scalp_size_mode" in updates and updates["scalp_size_mode"] in ("percent", "fixed"):
        SCALP_SIZE_MODE = updates["scalp_size_mode"]
    if "scalp_size_value" in updates:
        try:
            v = float(updates["scalp_size_value"])
            if v > 0:
                SCALP_SIZE_VALUE = v
        except (TypeError, ValueError):
            pass
    if "ema_min_rr" in updates:
        try:
            v = float(updates["ema_min_rr"])
            if v >= 0:  # 0 is a valid value here (disables the filter), unlike the size fields above
                EMA_MIN_RR = v
        except (TypeError, ValueError):
            pass
    if "ema_signal_timeout_hours" in updates:
        try:
            v = float(updates["ema_signal_timeout_hours"])
            if v > 0:
                EMA_SIGNAL_TIMEOUT_SEC = int(v * 3600)
        except (TypeError, ValueError):
            pass
    if "ema_adx_filter_enabled" in updates:
        EMA_ADX_FILTER_ENABLED = bool(updates["ema_adx_filter_enabled"])
    if "ema_adx_min" in updates:
        try:
            v = float(updates["ema_adx_min"])
            if v >= 0:
                EMA_ADX_MIN = v
        except (TypeError, ValueError):
            pass
    if "ema_min_gap_pct" in updates:
        try:
            v = float(updates["ema_min_gap_pct"])
            if v >= 0:  # 0 disables the filter, same convention as ema_min_rr
                EMA_MIN_GAP_PCT = v
        except (TypeError, ValueError):
            pass
    for key, glob_name in (
        ("autotrade_leverage_bounce", "AUTOTRADE_LEVERAGE_BOUNCE"),
        ("autotrade_leverage_breakout", "AUTOTRADE_LEVERAGE_BREAKOUT"),
        ("autotrade_leverage_divergence", "AUTOTRADE_LEVERAGE_DIVERGENCE"),
        ("autotrade_leverage_ema", "AUTOTRADE_LEVERAGE_EMA"),
        ("autotrade_leverage_session", "AUTOTRADE_LEVERAGE_SESSION"),
        ("autotrade_leverage_session_ny", "AUTOTRADE_LEVERAGE_SESSION_NY"),
        ("autotrade_leverage_xau_lg", "AUTOTRADE_LEVERAGE_XAU_LG"),
    ):
        if key in updates:
            try:
                lev = int(updates[key])
                if 1 <= lev <= 125:
                    globals()[glob_name] = lev
            except (TypeError, ValueError):
                pass
    if "telegram_alerts_hourly" in updates:
        TELEGRAM_ALERTS_HOURLY = bool(updates["telegram_alerts_hourly"])
    if "scalp_min_rr" in updates:
        try:
            v = float(updates["scalp_min_rr"])
            if v >= 0:
                SCALP_MIN_RR = v
        except (TypeError, ValueError):
            pass
    if "scalp_sl_buffer_mult" in updates:
        try:
            v = float(updates["scalp_sl_buffer_mult"])
            if v >= 0:
                SCALP_SL_BUFFER_MULT = v
        except (TypeError, ValueError):
            pass
    if "session_sl_mult" in updates:
        try:
            v = float(updates["session_sl_mult"])
            if v > 0:
                SESSION_SL_MULT = v
        except (TypeError, ValueError):
            pass
    if "ema_sl_atr_mult" in updates:
        try:
            v = float(updates["ema_sl_atr_mult"])
            if v > 0:
                EMA_SL_ATR_MULT = v
        except (TypeError, ValueError):
            pass
    if "div_sl_atr_mult" in updates:
        try:
            v = float(updates["div_sl_atr_mult"])
            if v > 0:
                DIV_SL_ATR_MULT = v
        except (TypeError, ValueError):
            pass
    if "ema_tp_pct" in updates:
        try:
            v = float(updates["ema_tp_pct"])
            if v > 0:
                EMA_TP_PCT = v
        except (TypeError, ValueError):
            pass
    if "div_tp_pct" in updates:
        try:
            v = float(updates["div_tp_pct"])
            if v > 0:
                DIV_TP_PCT = v
        except (TypeError, ValueError):
            pass


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
# Gate.io private API — HMAC-SHA512 request signing (APIv4 scheme) and
# credential storage. Kept fully separate from the public GATE_BASE calls
# used everywhere else in this file: those never need a key/secret at all.
# ----------------------------------------------------------------------------
GATE_API_KEY = ""
GATE_API_SECRET = ""
_credentials_lock = threading.Lock()


def save_credentials(api_key, api_secret):
    """Writes to CREDENTIALS_FILE, chmod 600 (owner read/write only) — best
    effort on platforms that support it; Termux/Android generally does."""
    global GATE_API_KEY, GATE_API_SECRET
    with _credentials_lock:
        GATE_API_KEY = api_key
        GATE_API_SECRET = api_secret
        try:
            tmp_path = CREDENTIALS_FILE + ".tmp"
            with open(tmp_path, "w") as f:
                json.dump({"api_key": api_key, "api_secret": api_secret}, f)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, CREDENTIALS_FILE)
        except Exception as e:
            log_error(f"save_credentials: {e}")


def load_credentials():
    global GATE_API_KEY, GATE_API_SECRET
    if not os.path.exists(CREDENTIALS_FILE):
        return
    try:
        with open(CREDENTIALS_FILE) as f:
            saved = json.load(f)
        with _credentials_lock:
            GATE_API_KEY = saved.get("api_key", "")
            GATE_API_SECRET = saved.get("api_secret", "")
    except Exception as e:
        log_error(f"load_credentials: {e}")


def gate_signed_request(method, url_path, query_string="", body=None, timeout=HTTP_TIMEOUT):
    """One request to Gate's authenticated futures API. url_path is the path
    only (e.g. "/futures/usdt/orders"), no host/prefix. body, if given, is
    the dict that will become the JSON payload — signed over its exact
    serialized bytes, so build it once and reuse the same object for both
    signing and sending rather than re-serializing (a different key order
    would still hash the same content, but simpler to just sign what's
    actually sent).
    Signature scheme (Gate APIv4): SIGN = HexEncode(HMAC_SHA512(secret,
    Method + "\\n" + URL + "\\n" + QueryString + "\\n" + HexEncode(SHA512(Payload)) + "\\n" + Timestamp))."""
    if not GATE_API_KEY or not GATE_API_SECRET:
        raise RuntimeError("Gate.io API credentials not configured")
    payload_str = json.dumps(body) if body is not None else ""
    hashed_payload = hashlib.sha512(payload_str.encode("utf-8")).hexdigest()
    ts = str(time.time())
    full_url_path = "/api/v4" + url_path
    sign_string = f"{method}\n{full_url_path}\n{query_string}\n{hashed_payload}\n{ts}"
    sign = hmac.new(GATE_API_SECRET.encode("utf-8"), sign_string.encode("utf-8"), hashlib.sha512).hexdigest()
    headers = {
        "KEY": GATE_API_KEY, "Timestamp": ts, "SIGN": sign,
        "Accept": "application/json", "Content-Type": "application/json",
    }
    url = f"{GATE_BASE_HOST}{full_url_path}"
    if query_string:
        url += f"?{query_string}"
    r = requests.request(method, url, headers=headers, data=payload_str if body is not None else None, timeout=timeout)
    if not r.ok:
        # Gate's error responses carry a JSON body ({"label":..., "message":...})
        # that raise_for_status()'s generic "400 Client Error" text throws away —
        # exactly the detail needed to diagnose a rejected order without guessing.
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise requests.exceptions.HTTPError(f"{r.status_code} error for {method} {url_path}: {detail}", response=r)
    return r.json() if r.text else None


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
    "excluded_fetch_error": 0,
    "filtered_by_trend": 0,
    "filtered_by_volume": 0,
    "filtered_by_oi": 0,
    "filtered_by_staleness": 0,
    "filtered_by_min_rr": 0,
    "filtered_by_div_min_rr": 0,
    "filtered_by_adx": 0,
    "filtered_by_min_gap": 0,
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
    # Signal snapshots (v0.73.0) — a frozen copy of a module's CLOSED
    # signal list, with all its diagnostic fields, saved on demand so a
    # candidate filter threshold can be tested against it instantly
    # (recomputing win/loss/winrate offline) instead of waiting for new
    # live signals to accumulate under the new threshold. Keyed by an
    # opaque snapshot id; see save_signal_snapshot()/replay_signal_
    # snapshot(). Persisted via save_state()/load_state() like
    # everything else in STATE.
    "signal_snapshots": {},
    # Risk auto-tune (v0.93.0) — NOT the same system as auto_tune_cycle()/
    # AUTO_TUNE_ENABLED above (that one searches Volume Profile detection
    # parameters per symbol). This is a separate system that periodically
    # nudges risk-related constants (EMA_MIN_RR, SCALP_MIN_RR, SCALP_SL_
    # BUFFER_MULT, SESSION_SL_MULT, and the three *_INVERT_SIGNALS flags)
    # based on live win/loss stats, replacing what had been the user
    # manually screenshotting stats each time and asking for the same kind
    # of adjustment — see risk_autotune_pass()'s own docstring.
    "risk_autotune_log": deque(maxlen=200),
    "risk_autotune_last_change": {},  # param_key -> unix ts, for cooldown enforcement
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
    # New York session variant (v0.94.0) — fully independent STATE, mirrors
    # every key above with its own "session_ny_" prefix.
    "session_ny_universe": [],
    "session_ny_backtest_results": {},
    "session_ny_backtest_summary": {},
    "session_ny_last_backtest_started": None,
    "session_ny_last_backtest_finished": None,
    "session_ny_last_backtest_duration": None,
    "session_ny_symbols_done": 0,
    "session_ny_signals": deque(maxlen=SESSION_NY_SIGNAL_HISTORY),
    "session_ny_next_open_ts": None,
    # EXPERIMENTAL XAU Liquidity Grab (v0.95.0) — see that module's own
    # header comment. All keys prefixed xau_lg_ for easy removal.
    "xau_lg_signals": deque(maxlen=XAU_LG_SIGNAL_HISTORY),
    "xau_lg_backtest_results": {},
    "xau_lg_backtest_summary": {},
    "xau_lg_last_backtest_finished": None,
    "xau_lg_last_backtest_duration": None,
    "autotrade_log": deque(maxlen=AUTOTRADE_TRADE_HISTORY),  # every attempted auto-trade, dry-run or real, with its outcome
    "sim_balance": AUTOTRADE_SIM_START_BALANCE,
    "sim_trades": deque(maxlen=AUTOTRADE_SIM_TRADE_HISTORY),  # pending + settled paper trades
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
_session_ny_signal_cooldowns = {}  # same purpose, fully separate — New York variant
_session_ny_signal_cooldowns_lock = threading.Lock()


def has_open_signal(symbol):
    """True if this symbol already has an unresolved (OPEN) signal —
    simplest fix for the "repeat signal on the same level every scan"
    problem: don't stack a second signal on a symbol that already has one
    running, regardless of which exact zone/direction produced it."""
    with state_lock:
        return any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in STATE["signals"])


def has_open_signal_any_module(symbol, exclude=None):
    """True if ANY module (Volume/Divergence/EMA/Scalp/Session) already
    has an OPEN signal on this symbol. Each module previously only
    checked its OWN signal list before firing — real gap found live:
    EMA opened MMT_USDT SHORT, and 43 minutes later Breakout opened
    MMT_USDT LONG, completely independently, each placing its own
    market order + TP + SL. Multiplied across five modules all watching
    the same universe, a single popular/volatile symbol accumulates a
    pile of orders from different sources with no coordination between
    them (the reported case: 13 open orders on one symbol on Gate,
    nothing in any single module's own log looking obviously wrong,
    because no module's log ever saw the whole picture).
    Called in ADDITION to each module's existing own-list check, not
    instead of it — this only adds a cross-module veto, it doesn't
    change any module's internal per-symbol/interval dedup logic.
    exclude: STATE key name to skip (e.g. "ema_signals") — EMA
    deliberately allows multiple simultaneously-open signals on the same
    symbol across DIFFERENT intervals (its own has_open_ema_signal is
    interval-aware and already handles that within-module case), so its
    call here excludes ema_signals to avoid vetoing itself; the other
    four modules only ever want at most one open signal per symbol
    regardless of interval, so they pass their own list name too, purely
    for clarity (their own already-called check makes it a no-op)."""
    lists = {
        "signals": STATE["signals"], "div_signals": STATE["div_signals"],
        "ema_signals": STATE["ema_signals"], "scalp_signals": STATE["scalp_signals"],
        "session_signals": STATE["session_signals"], "session_ny_signals": STATE["session_ny_signals"],
        "xau_lg_signals": STATE["xau_lg_signals"],
    }
    with state_lock:
        for name, lst in lists.items():
            if name == exclude:
                continue
            if any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in lst):
                return True
    return False


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


def _true_range_series(candles):
    """Per-bar true range: max(high-low, |high-prev_close|,
    |low-prev_close|). First bar has no prior close, so its TR is just
    high-low."""
    tr = [None] * len(candles)
    for i, c in enumerate(candles):
        if i == 0:
            tr[i] = c["high"] - c["low"]
        else:
            prev_close = candles[i - 1]["close"]
            tr[i] = max(c["high"] - c["low"], abs(c["high"] - prev_close), abs(c["low"] - prev_close))
    return tr


def _atr_series(tr, period):
    """Wilder's ATR: SMA seed over the first `period` true-range values,
    then Wilder smoothing (an EMA with alpha=1/period, not the standard
    2/(period+1) — this is the original ATR definition, not compute_ema
    reused with a different period)."""
    n = len(tr)
    atr = [None] * n
    if n < period:
        return atr
    seed = sum(tr[:period]) / period
    atr[period - 1] = seed
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def _dm_series(candles):
    """Wilder's directional movement per bar: +DM is the up-move when it
    exceeds the down-move (and is positive), -DM is the down-move when
    IT exceeds the up-move (and is positive) — never both nonzero on the
    same bar. First bar has no prior bar to compare against, so both
    are 0 there."""
    n = len(candles)
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        up_move = candles[i]["high"] - candles[i - 1]["high"]
        down_move = candles[i - 1]["low"] - candles[i]["low"]
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move
    return plus_dm, minus_dm


def compute_adx(candles, period=14):
    """Wilder's ADX — measures trend STRENGTH (0-100), not direction;
    +DI/-DI (also returned) show which direction currently dominates.
    Standard, decades-old regime filter for exactly the whipsaw problem
    recent_crossover_count (v0.62.0) was trying to approximate with a
    home-grown proxy: ADX<20 means weak/no trend (chop — crossovers
    here are mostly noise), 20-25 an emerging trend, >25 confirmed.
    Reuses _true_range_series()/_atr_series() for the TR and DM
    smoothing (Wilder smoothing, same math as ATR) — DX = 100*|+DI-
    -DI|/(+DI+-DI) per bar, and ADX itself is that same Wilder
    smoothing applied a second time, to DX. Needs roughly 2*period bars
    of warm-up before the first real value; returns None for indices
    before that. Returns (plus_di, minus_di, adx), all same length as
    candles."""
    n = len(candles)
    plus_di = [None] * n
    minus_di = [None] * n
    adx = [None] * n
    if n < period * 2:
        return plus_di, minus_di, adx
    tr = _true_range_series(candles)
    plus_dm, minus_dm = _dm_series(candles)
    smooth_tr = _atr_series(tr, period)
    smooth_plus_dm = _atr_series(plus_dm, period)
    smooth_minus_dm = _atr_series(minus_dm, period)
    dx = [None] * n
    for i in range(n):
        if smooth_tr[i] is not None and smooth_plus_dm[i] is not None and smooth_minus_dm[i] is not None and smooth_tr[i] > 0:
            plus_di[i] = 100 * smooth_plus_dm[i] / smooth_tr[i]
            minus_di[i] = 100 * smooth_minus_dm[i] / smooth_tr[i]
            di_sum = plus_di[i] + minus_di[i]
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / di_sum if di_sum else 0.0
    dx_start = next((i for i, v in enumerate(dx) if v is not None), None)
    if dx_start is not None:
        dx_tail = [v if v is not None else 0.0 for v in dx[dx_start:]]
        adx_tail = _atr_series(dx_tail, period)
        for j, v in enumerate(adx_tail):
            adx[dx_start + j] = v
    return plus_di, minus_di, adx


# EMA diagnostics — v0.62.0, per direct user request to understand the
# EMA module's low win rate before touching its filters/SL. NONE of
# these affect whether a signal fires or its TP/SL; they're attached to
# each signal purely so compute_ema_stats()'s win/loss breakdown (and
# /api/ema/status) can show whether losses cluster on high-ATR bars,
# weak/flat EMA28 slope, marginal EMA7/14 separation, or choppy
# recent-crossover conditions — actual evidence to decide a real filter
# on, instead of guessing.
EMA_DIAG_ATR_PERIOD = int(os.environ.get("VP_EMA_DIAG_ATR_PERIOD", 14))
EMA_DIAG_SLOPE_LOOKBACK = int(os.environ.get("VP_EMA_DIAG_SLOPE_LOOKBACK", 5))  # bars back for the EMA28 slope measurement
EMA_DIAG_CHOP_LOOKBACK = int(os.environ.get("VP_EMA_DIAG_CHOP_LOOKBACK", 20))  # bars back to count EMA7/EMA14 crossovers in
EMA_ADX_PERIOD = int(os.environ.get("VP_EMA_ADX_PERIOD", 14))  # Wilder's standard period — see compute_adx()


def _ema_signal_diagnostics(closes, ema7, ema14, ema28, i, direction, candles):
    """Computes the diagnostic-only fields described above for the
    signal at bar i. candles (with high/low) is needed for ATR/ADX — if
    not given, those are left None rather than guessed at from closes
    alone."""
    diag = {"atr_pct": None, "ema_slope_pct": None, "ema_gap_pct": None, "recent_crossover_count": None, "adx": None}
    price = closes[i]
    if price:
        diag["ema_gap_pct"] = round((ema7[i] - ema14[i]) / price * 100, 4)

    lb = EMA_DIAG_SLOPE_LOOKBACK
    if i - lb >= 0 and ema28[i - lb]:
        raw_slope_pct = (ema28[i] - ema28[i - lb]) / ema28[i - lb] * 100
        # Signed so positive always means "EMA28 is moving WITH this
        # trade's direction" regardless of LONG/SHORT — lets win/loss
        # aggregation compare apples to apples across both directions.
        diag["ema_slope_pct"] = round(raw_slope_pct if direction == "LONG" else -raw_slope_pct, 4)

    chop_lb = EMA_DIAG_CHOP_LOOKBACK
    start = max(1, i - chop_lb + 1)
    count = 0
    for j in range(start, i + 1):
        if _crossover(ema7, ema14, j) or _crossunder(ema7, ema14, j):
            count += 1
    diag["recent_crossover_count"] = count

    if candles is not None and len(candles) == len(closes):
        tr = _true_range_series(candles)
        atr = _atr_series(tr, EMA_DIAG_ATR_PERIOD)
        if atr[i] and price:
            diag["atr_pct"] = round(atr[i] / price * 100, 4)
        _plus_di, _minus_di, adx = compute_adx(candles, EMA_ADX_PERIOD)
        if adx[i] is not None:
            diag["adx"] = round(adx[i], 3)

    return diag


def detect_ema_signal(closes, len7=EMA_LEN_7, len14=EMA_LEN_14, len28=EMA_LEN_28,
                       signal_type=EMA_SIGNAL_TYPE, trend_filter=EMA_TREND_FILTER, candles=None):
    """Same three signal definitions as the Pine Script's "Тип сигнала"
    input: price/EMA7 cross, EMA7/EMA14 cross, or "combined" (price
    crosses EMA7 while EMA7 is already positioned on the trade's side of
    EMA14) — plus the optional EMA28 trend filter. Only looks at the
    latest bar, mirroring how the indicator plots live on a chart.
    candles (optional, with high/low) enables the ATR diagnostic field;
    omitting it just leaves atr_pct as None, no other behavior changes."""
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

    if buy or sell:
        direction = "LONG" if buy else "SHORT"
        result = {"direction": direction, "ema7": ema7[i], "ema14": ema14[i], "ema28": ema28[i]}
        result.update(_ema_signal_diagnostics(closes, ema7, ema14, ema28, i, direction, candles))
        return result
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


def session_ny_open_utc_ts(ref_ts):
    """New York counterpart of session_open_utc_ts() — same Moscow-fixed-
    offset arithmetic, but with minute precision (SESSION_NY_OPEN_MINUTE_
    LOCAL) since 16:30 Moscow isn't a whole hour, unlike the original's
    10:00. Fully independent function, not a generalization of the
    original — see this section's own header comment for why."""
    dt_utc = datetime.datetime.fromtimestamp(ref_ts, tz=datetime.timezone.utc)
    local_shifted = dt_utc + datetime.timedelta(hours=SESSION_NY_UTC_OFFSET_HOURS)
    open_shifted = local_shifted.replace(hour=SESSION_NY_OPEN_HOUR_LOCAL, minute=SESSION_NY_OPEN_MINUTE_LOCAL, second=0, microsecond=0)
    open_utc = open_shifted - datetime.timedelta(hours=SESSION_NY_UTC_OFFSET_HOURS)
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
    longer applicable.
    Since v0.55.0, the range must also be flat/choppy rather than
    still trending in one direction (SESSION_MAX_TREND_RATIO) — a
    range can pass SESSION_MIN_RANGE_PCT just by being the tail end
    of a directional move, which isn't a real consolidation.
    Since v0.80.0, SESSION_INVERT_SIGNALS flips direction AND uses its
    own RR=2 sizing (same risk distance as the non-inverted stop, TP at
    2x that) instead of reusing the original tp (opposite side of the
    range) — see that constant's own comment for the reasoning."""
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

    range_height = range_high - range_low
    net_move = abs(range_candles[-1]["close"] - range_candles[0]["open"])
    trend_ratio = net_move / range_height
    if trend_ratio > SESSION_MAX_TREND_RATIO:
        return None  # range is still trending directionally, not a genuine flat consolidation

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
            orig_sl = sweep_extreme * (1 + SESSION_SL_BUFFER_PCT)
            risk = abs(entry - orig_sl)
            if SESSION_INVERT_SIGNALS:
                risk *= SESSION_SL_MULT
                direction, sl, tp = "LONG", entry - risk, entry + risk * 2
            else:
                direction, sl, tp = "SHORT", orig_sl, range_low
            return {"direction": direction, "entry": entry, "sl": sl, "tp": tp,
                    "range_high": range_high, "range_low": range_low,
                    "sweep_extreme": sweep_extreme, "confirm_time": c["time"]}
        if cluster_lows_below:
            entry = c["close"]
            sweep_extreme = min(cluster_lows_below)
            orig_sl = sweep_extreme * (1 - SESSION_SL_BUFFER_PCT)
            risk = abs(entry - orig_sl)
            if SESSION_INVERT_SIGNALS:
                risk *= SESSION_SL_MULT
                direction, sl, tp = "SHORT", entry + risk, entry - risk * 2
            else:
                direction, sl, tp = "LONG", orig_sl, range_high
            return {"direction": direction, "entry": entry, "sl": sl, "tp": tp,
                    "range_high": range_high, "range_low": range_low,
                    "sweep_extreme": sweep_extreme, "confirm_time": c["time"]}
    return None


def detect_session_ny_manipulation(candles, session_open_ts):
    """New York counterpart of detect_session_manipulation() — identical
    pattern logic (consolidation range -> sweep beyond it within the
    manipulation window -> close back inside = confirmed manipulation),
    just reading the SESSION_NY_* constants instead of SESSION_*. See
    that function's own docstring for the pattern rationale; not
    repeated here beyond what differs. Kept as a fully separate function
    rather than parameterizing the original, per the user's explicit
    request that the original stay untouched."""
    open_dt = datetime.datetime.fromtimestamp(session_open_ts, tz=datetime.timezone.utc)
    range_start_dt = open_dt.replace(hour=SESSION_NY_RANGE_START_UTC_HOUR, minute=0, second=0, microsecond=0)
    range_start = range_start_dt.timestamp()
    range_duration_sec = session_open_ts - range_start
    range_candles = [c for c in candles if range_start <= c["time"] < session_open_ts]
    expected_bars = range_duration_sec / INTERVAL_SECONDS.get(SESSION_NY_RANGE_TF, 300)
    if expected_bars <= 0 or len(range_candles) < expected_bars * 0.6:
        return None
    range_high = max(c["high"] for c in range_candles)
    range_low = min(c["low"] for c in range_candles)
    if range_low <= 0:
        return None
    range_pct = (range_high - range_low) / range_low
    if range_pct < SESSION_NY_MIN_RANGE_PCT:
        return None

    range_height = range_high - range_low
    net_move = abs(range_candles[-1]["close"] - range_candles[0]["open"])
    trend_ratio = net_move / range_height
    if trend_ratio > SESSION_NY_MAX_TREND_RATIO:
        return None

    window_end = session_open_ts + SESSION_NY_MANIPULATION_WINDOW_MIN * 60
    window_candles = [c for c in candles if session_open_ts <= c["time"] < window_end]

    for i, c in enumerate(window_candles):
        closed_back_inside = range_low <= c["close"] <= range_high
        if not closed_back_inside:
            continue
        cluster = window_candles[max(0, i - (SESSION_NY_MAX_THRUST_BARS - 1)):i + 1]
        cluster_highs_above = [cc["high"] for cc in cluster if cc["high"] > range_high]
        cluster_lows_below = [cc["low"] for cc in cluster if cc["low"] < range_low]
        if cluster_highs_above and cluster_lows_below:
            continue
        if cluster_highs_above:
            entry = c["close"]
            sweep_extreme = max(cluster_highs_above)
            orig_sl = sweep_extreme * (1 + SESSION_NY_SL_BUFFER_PCT)
            risk = abs(entry - orig_sl)
            if SESSION_NY_INVERT_SIGNALS:
                risk *= SESSION_NY_SL_MULT
                direction, sl, tp = "LONG", entry - risk, entry + risk * 2
            else:
                direction, sl, tp = "SHORT", orig_sl, range_low
            return {"direction": direction, "entry": entry, "sl": sl, "tp": tp,
                    "range_high": range_high, "range_low": range_low,
                    "sweep_extreme": sweep_extreme, "confirm_time": c["time"]}
        if cluster_lows_below:
            entry = c["close"]
            sweep_extreme = min(cluster_lows_below)
            orig_sl = sweep_extreme * (1 - SESSION_NY_SL_BUFFER_PCT)
            risk = abs(entry - orig_sl)
            if SESSION_NY_INVERT_SIGNALS:
                risk *= SESSION_NY_SL_MULT
                direction, sl, tp = "SHORT", entry + risk, entry - risk * 2
            else:
                direction, sl, tp = "LONG", orig_sl, range_high
            return {"direction": direction, "entry": entry, "sl": sl, "tp": tp,
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


def track_session_ny_outcome(candles, sig, max_wait_sec=24 * 3600):
    """New York counterpart of track_session_outcome() — identical
    walk-forward logic."""
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


def backtest_session_ny_symbol(symbol, days=SESSION_NY_BACKTEST_DAYS):
    """New York counterpart of backtest_session_symbol() — identical
    walk-forward-by-calendar-day logic, reading SESSION_NY_* constants
    and calling detect_session_ny_manipulation()/track_session_ny_
    outcome()/session_ny_open_utc_ts() throughout."""
    now = time.time()
    fetch_start = now - days * 86400 - 25 * 3600
    candles = get_candles_range(symbol, SESSION_NY_RANGE_TF, fetch_start, now)
    if len(candles) < 50:
        return []

    results = []
    cur = session_ny_open_utc_ts(fetch_start) + 86400
    cutoff = now - SESSION_NY_MANIPULATION_WINDOW_MIN * 60
    seen_days = 0
    while cur < cutoff and seen_days < days:
        sig = detect_session_ny_manipulation(candles, cur)
        if sig:
            result, exit_time = track_session_ny_outcome(candles, sig)
            results.append({
                "session_open": cur, "direction": sig["direction"],
                "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
                "range_high": sig["range_high"], "range_low": sig["range_low"],
                "result": result, "exit_time": exit_time,
            })
        cur = session_ny_open_utc_ts(cur + 86400)
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


def build_session_ny_universe():
    """New York counterpart of build_session_universe() — identical
    ticker-volume ranking, capped to SESSION_NY_UNIVERSE_SIZE."""
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
    return [s[0] for s in ranked[:SESSION_NY_UNIVERSE_SIZE]]


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
        # Exclude the currently-forming candle — its OHLC is still changing
        # until it actually closes, so evaluating it mid-formation risks
        # firing on a transient wick+close-back-inside that won't hold up
        # once the candle finalizes (confirmed as the cause of a live
        # signal that later showed no manipulation on the chart, since the
        # chart re-derives from the now-finalized candle).
        interval_sec = INTERVAL_SECONDS.get(SESSION_RANGE_TF, 300)
        now = time.time()
        candles = [c for c in candles if c["time"] + interval_sec <= now]
        sig = detect_session_manipulation(candles, session_open_ts)
        if not sig:
            return
        if has_open_signal_any_module(symbol, exclude="session_signals"):
            return  # another module already has an open position on this symbol — see has_open_signal_any_module's docstring for why this check exists
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
        if AUTOTRADE_ENABLED_SESSION:
            execute_autotrade("session", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"],
                               AUTOTRADE_LEVERAGE_SESSION, extra={"session_open": session_open_ts})
            sim_execute_trade("session", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"],
                               AUTOTRADE_LEVERAGE_SESSION, record)
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        send_telegram(
            f"{arrow} {symbol} (открытие сессии — манипуляция)\n"
            f"entry: {sig['entry']:.6g}\n"
            f"SL: {sig['sl']:.6g}  TP: {sig['tp']:.6g}",
            category="session",
        )
    except Exception as e:
        log_error(f"session_live {symbol}: {e}")


def scan_symbol_session_ny_live(symbol, session_open_ts):
    """New York counterpart of scan_symbol_session_live() — identical
    logic, own STATE list/cooldowns/constants, and its own autotrade
    "session_ny" mode string so autotrade_log/simulator entries are
    distinguishable from the original session's."""
    if not SESSION_NY_ENABLED:
        return
    with _session_ny_signal_cooldowns_lock:
        if _session_ny_signal_cooldowns.get(symbol) == session_open_ts:
            return
    try:
        range_start_dt = datetime.datetime.fromtimestamp(session_open_ts, tz=datetime.timezone.utc).replace(
            hour=SESSION_NY_RANGE_START_UTC_HOUR, minute=0, second=0, microsecond=0)
        candles = get_candles_range(symbol, SESSION_NY_RANGE_TF, range_start_dt.timestamp(), time.time())
        interval_sec = INTERVAL_SECONDS.get(SESSION_NY_RANGE_TF, 300)
        now = time.time()
        candles = [c for c in candles if c["time"] + interval_sec <= now]
        sig = detect_session_ny_manipulation(candles, session_open_ts)
        if not sig:
            return
        if has_open_signal_any_module(symbol, exclude="session_ny_signals"):
            return
        with _session_ny_signal_cooldowns_lock:
            if _session_ny_signal_cooldowns.get(symbol) == session_open_ts:
                return
            _session_ny_signal_cooldowns[symbol] = session_open_ts
        record = {
            "symbol": symbol, "direction": sig["direction"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
            "range_high": sig["range_high"], "range_low": sig["range_low"],
            "session_open": session_open_ts, "confirm_time": sig["confirm_time"],
            "detected_at": time.time(), "status": "OPEN", "result": None,
            "exit_price": None, "exit_time": None, "app_version": APP_VERSION,
        }
        with state_lock:
            STATE["session_ny_signals"].appendleft(record)
        if AUTOTRADE_ENABLED_SESSION_NY:
            execute_autotrade("session_ny", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"],
                               AUTOTRADE_LEVERAGE_SESSION_NY, extra={"session_open": session_open_ts})
            sim_execute_trade("session_ny", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"],
                               AUTOTRADE_LEVERAGE_SESSION_NY, record)
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        send_telegram(
            f"{arrow} {symbol} (открытие Нью-Йорка — манипуляция)\n"
            f"entry: {sig['entry']:.6g}\n"
            f"SL: {sig['sl']:.6g}  TP: {sig['tp']:.6g}",
            category="session_ny",
        )
    except Exception as e:
        log_error(f"session_ny_live {symbol}: {e}")


def update_session_signal_outcomes():
    now = time.time()
    with state_lock:
        open_signals = [s for s in STATE["session_signals"] if s["status"] == "OPEN"]
    all_candles = fetch_candles_concurrent([(s["symbol"], SESSION_RANGE_TF, 300) for s in open_signals])
    for sig, candles in zip(open_signals, all_candles):
        try:
            if candles is None:
                continue
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


def update_session_ny_signal_outcomes():
    """New York counterpart of update_session_signal_outcomes() — same
    walk-forward SL/TP check and 24h timeout, own STATE list/constants."""
    now = time.time()
    with state_lock:
        open_signals = [s for s in STATE["session_ny_signals"] if s["status"] == "OPEN"]
    all_candles = fetch_candles_concurrent([(s["symbol"], SESSION_NY_RANGE_TF, 300) for s in open_signals])
    for sig, candles in zip(open_signals, all_candles):
        try:
            if candles is None:
                continue
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
            log_error(f"session_ny_outcome {sig['symbol']}: {e}")


def compute_session_ny_signal_stats():
    with state_lock:
        signals = list(STATE["session_ny_signals"])
    closed = [s for s in signals if s["status"] == "CLOSED" and s["result"] in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = sum(1 for s in closed if s["result"] == "LOSS")
    timeouts = sum(1 for s in signals if s.get("result") == "TIMEOUT")
    open_n = sum(1 for s in signals if s["status"] == "OPEN")
    total_closed = len(closed)
    winrate = round(wins / total_closed * 100, 1) if total_closed else None
    return {"total": len(signals), "wins": wins, "losses": losses, "timeouts": timeouts,
            "open": open_n, "winrate": winrate}


def compute_ema_tp_sl(direction, entry, atr=None, tp_pct=None, atr_mult=None, fallback_rr=None):
    """TP is always a fixed % of entry (tp_pct) — the source Pine Script
    only plots BUY/SELL labels, no TP/SL, so this was always synthetic.
    SL depends on EMA_SL_MODE:
      - "atr" (default): SL = atr * atr_mult in price units, on the
        losing side of entry. Needs atr (price units, not %) — pass
        None or 0 to force the fixed_rr fallback for this call even in
        atr mode (e.g. ATR unavailable for this candle set).
      - "fixed_pct" or ATR unavailable: reproduces the old behavior —
        risk = tp_distance / fallback_rr (EMA_RR), same math as before
        this function grew ATR support.
    Returns (sl, tp, risk, rr) — rr is now always computed FROM the
    actual sl/tp distances rather than assumed, since ATR mode makes it
    vary signal to signal instead of being one fixed constant.
    v0.95.7: tp_pct/atr_mult/fallback_rr now default to None and get
    resolved to the CURRENT EMA_TP_PCT/EMA_SL_ATR_MULT/EMA_RR globals
    inside the function body — NOT bound as literal default parameter
    values in the signature. Python evaluates a default parameter value
    ONCE, at function-definition time (module load), not on each call —
    so `tp_pct=EMA_TP_PCT` froze whatever EMA_TP_PCT happened to be at
    startup into this function's own __defaults__ forever. Every actual
    call site (scan_symbol_ema) calls this with only direction/entry/atr,
    relying entirely on that default — meaning every risk_autotune_pass()
    adjustment to EMA_TP_PCT or EMA_SL_ATR_MULT since process start was
    successfully logged and persisted to settings.json, but had ZERO
    effect on real signals: they kept computing SL/TP off the ORIGINAL
    startup value. Found via direct audit ("найди все проблемы"), not a
    live symptom someone noticed — this could have been silently
    inert for the rest of this session otherwise."""
    if tp_pct is None:
        tp_pct = EMA_TP_PCT
    if atr_mult is None:
        atr_mult = EMA_SL_ATR_MULT
    if fallback_rr is None:
        fallback_rr = EMA_RR
    if direction == "SHORT":
        tp = entry * (1 - tp_pct)
        tp_dist = entry - tp
        if EMA_SL_MODE == "atr" and atr:
            risk = atr * atr_mult
        else:
            risk = tp_dist / fallback_rr
        sl = entry + risk
    else:
        tp = entry * (1 + tp_pct)
        tp_dist = tp - entry
        if EMA_SL_MODE == "atr" and atr:
            risk = atr * atr_mult
        else:
            risk = tp_dist / fallback_rr
        sl = entry - risk
    rr = round(tp_dist / risk, 3) if risk else None
    return sl, tp, risk, rr


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


def compute_div_tp_sl(direction, entry, atr=None, tp_pct=None, atr_mult=None, fallback_rr=None):
    """TP is always a fixed % of entry (tp_pct) — the divergence pattern
    itself doesn't imply a TP, this was always synthetic. SL depends on
    DIV_SL_MODE:
      - "atr" (default): SL = atr * atr_mult in price units. Pass None
        or 0 for atr to force the fixed_rr fallback for this call even
        in atr mode (e.g. ATR unavailable for this candle set).
      - "fixed_pct" or ATR unavailable: reproduces the old behavior —
        risk = tp_distance / fallback_rr (DIV_RR).
    Returns (sl, tp, risk, rr) — rr computed FROM the actual resulting
    distances rather than assumed, since ATR mode makes it vary signal
    to signal instead of being one fixed constant.
    v0.95.7: same fix as compute_ema_tp_sl() — tp_pct/atr_mult/
    fallback_rr now resolve to the CURRENT DIV_TP_PCT/DIV_SL_ATR_MULT/
    DIV_RR globals inside the function body instead of being frozen as
    literal default parameter values at module-load time. See that
    function's docstring for the full explanation; same bug, same fix,
    found in the same audit pass."""
    if tp_pct is None:
        tp_pct = DIV_TP_PCT
    if atr_mult is None:
        atr_mult = DIV_SL_ATR_MULT
    if fallback_rr is None:
        fallback_rr = DIV_RR
    if direction == "SHORT":
        tp = entry * (1 - tp_pct)
        tp_dist = entry - tp
        if DIV_SL_MODE == "atr" and atr:
            risk = atr * atr_mult
        else:
            risk = tp_dist / fallback_rr
        sl = entry + risk
    else:
        tp = entry * (1 + tp_pct)
        tp_dist = tp - entry
        if DIV_SL_MODE == "atr" and atr:
            risk = atr * atr_mult
        else:
            risk = tp_dist / fallback_rr
        sl = entry - risk
    rr = round(tp_dist / risk, 3) if risk else None
    return sl, tp, risk, rr


def has_open_divergence_signal(symbol):
    with state_lock:
        return any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in STATE["div_signals"])


def scan_symbol_divergence(symbol, candles=None):
    if not DIVERGENCE_ENABLED:
        return
    try:
        if candles is None:
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
        if has_open_divergence_signal(symbol) or has_open_signal_any_module(symbol, exclude="div_signals"):
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
        atr_pct = None
        atr_price = None
        if len(candles) >= EMA_DIAG_ATR_PERIOD * 2:
            tr = _true_range_series(candles)
            atr_series = _atr_series(tr, EMA_DIAG_ATR_PERIOD)
            last_atr = atr_series[-1]
            if last_atr and entry:
                atr_price = last_atr
                atr_pct = round(last_atr / entry * 100, 4)
        sl, tp, risk, rr = compute_div_tp_sl(sig["direction"], entry, atr=atr_price)
        if DIV_MIN_RR > 0 and rr is not None and rr < DIV_MIN_RR:
            with state_lock:
                STATE["filtered_by_div_min_rr"] += 1
            return  # ATR-based stop came out too wide relative to the fixed TP — mirrors EMA_MIN_RR. Applied AFTER the cooldown consumption above (unlike EMA, where it's checked before) since divergence's cooldown is keyed by symbol only, not symbol+interval — restructuring the order wasn't worth the risk for this addition; a filtered signal here does still consume the symbol's cooldown slot, a minor inconsistency versus EMA's ordering, not a correctness issue
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
            "rr": rr,  # varies per signal in ATR mode — see DIV_SL_MODE / compute_div_tp_sl
            "atr_pct": atr_pct,
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
        if AUTOTRADE_ENABLED_DIVERGENCE:
            execute_autotrade("divergence", symbol, sig["direction"], entry, sl, tp,
                               AUTOTRADE_LEVERAGE_DIVERGENCE, extra={"kind": sig["kind"]})
            sim_execute_trade("divergence", symbol, sig["direction"], entry, sl, tp,
                               AUTOTRADE_LEVERAGE_DIVERGENCE, record)
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        rr_txt = f"{rr:g}" if rr is not None else "?"
        send_telegram(
            f"{arrow} {symbol} (RSI {sig['kind']} divergence)\n"
            f"entry: {entry:.6g}\n"
            f"SL: {sl:.6g}  TP: {tp:.6g}  (RR {rr_txt})",
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
    all_candles = fetch_candles_concurrent([(s["symbol"], DIV_INTERVAL, 300) for s in active])
    for sig, candles in zip(active, all_candles):
        try:
            if candles is None:
                continue
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


def scan_symbol_ema(symbol, interval=EMA_INTERVAL, candles=None):
    if not EMA_ENABLED:
        return
    try:
        if candles is None:
            candles = get_candles(symbol, interval=interval, limit=EMA_FETCH_LIMIT)
        min_needed = max(EMA_LEN_7, EMA_LEN_14, EMA_LEN_28) + 20
        if len(candles) < min_needed:
            return
        ok, _reason = data_quality_check(candles[-min(len(candles), 100):])
        if not ok:
            return
        closes = [c["close"] for c in candles]
        sig = detect_ema_signal(closes, EMA_LEN_7, EMA_LEN_14, EMA_LEN_28, EMA_SIGNAL_TYPE, EMA_TREND_FILTER, candles=candles)
        if not sig:
            return
        if has_open_ema_signal(symbol, interval) or has_open_signal_any_module(symbol, exclude="ema_signals"):
            return

        if EMA_ADX_FILTER_ENABLED:
            adx_val = sig.get("adx")
            if adx_val is not None and adx_val < EMA_ADX_MIN:
                with state_lock:
                    STATE["filtered_by_adx"] += 1
                return  # weak/no trend (Wilder's regime filter) — the crossover is more likely chop than a real signal here
        if EMA_MIN_GAP_PCT > 0:
            gap_val = sig.get("ema_gap_pct")
            if gap_val is not None and abs(gap_val) < EMA_MIN_GAP_PCT:
                with state_lock:
                    STATE["filtered_by_min_gap"] += 1
                return  # EMA7/EMA14 barely separated — marginal cross, not a decisive one

        entry = candles[-1]["close"]
        atr_pct = sig.get("atr_pct")
        atr_price = (atr_pct / 100 * entry) if atr_pct else None
        sl, tp, risk, rr = compute_ema_tp_sl(sig["direction"], entry, atr=atr_price)
        if EMA_MIN_RR > 0 and rr is not None and rr < EMA_MIN_RR:
            with state_lock:
                STATE["filtered_by_min_rr"] += 1
            return  # ATR-based stop came out too wide relative to the fixed TP — checked BEFORE the cooldown below so a filtered signal doesn't block a later, better one on the same (symbol, interval)

        now = time.time()
        cooldown_key = (symbol, interval)
        with _ema_cooldowns_lock:
            last_ts = _ema_cooldowns.get(cooldown_key, 0)
            allowed = now - last_ts >= EMA_COOLDOWN_SEC
            if allowed:
                _ema_cooldowns[cooldown_key] = now
        if not allowed:
            return

        record = {
            "symbol": symbol,
            "interval": interval,
            "direction": sig["direction"],
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "risk": risk,
            "rr": rr,  # varies per signal in ATR mode — see EMA_SL_MODE / compute_ema_tp_sl
            "ema7": sig["ema7"], "ema14": sig["ema14"], "ema28": sig["ema28"],
            # Diagnostic-only (v0.62.0) — see _ema_signal_diagnostics().
            # Not used by any live logic, purely for compute_ema_stats()'s
            # win/loss breakdown to ground a future filter decision.
            "atr_pct": sig.get("atr_pct"),
            "ema_slope_pct": sig.get("ema_slope_pct"),
            "ema_gap_pct": sig.get("ema_gap_pct"),
            "recent_crossover_count": sig.get("recent_crossover_count"),
            "adx": sig.get("adx"),
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
        if AUTOTRADE_ENABLED_EMA:
            execute_autotrade("ema", symbol, sig["direction"], entry, sl, tp,
                               AUTOTRADE_LEVERAGE_EMA, extra={"interval": interval})
            sim_execute_trade("ema", symbol, sig["direction"], entry, sl, tp,
                               AUTOTRADE_LEVERAGE_EMA, record)
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        rr_txt = f"{rr:g}" if rr is not None else "?"
        send_telegram(
            f"{arrow} {symbol} (EMA {EMA_SIGNAL_TYPE}, {interval})\n"
            f"entry: {entry:.6g}\n"
            f"SL: {sl:.6g}  TP: {tp:.6g}  (RR {rr_txt})",
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
        # Realized R at whatever price actually closed the trade — for
        # WIN/LOSS this is redundant with the R implied by hitting TP/SL,
        # but for TIMEOUT it's the only place this ever gets computed.
        # TIMEOUT closes at "last_price" (see update_ema_outcomes), not
        # at breakeven or any fixed value — a batch of timeouts closing
        # slightly negative on average is real money leaving the account
        # that the plain WIN/LOSS winrate never shows, since TIMEOUT sits
        # outside that count entirely.
        risk = sig.get("risk")
        if risk and exit_price is not None and sig.get("entry") is not None:
            raw = exit_price - sig["entry"] if sig["direction"] == "LONG" else sig["entry"] - exit_price
            sig["exit_r"] = round(raw / risk, 4)
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
    all_candles = fetch_candles_concurrent([(s["symbol"], s.get("interval", EMA_INTERVAL), 300) for s in active])
    for sig, candles in zip(active, all_candles):
        try:
            if candles is None:
                continue
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

            if sig["status"] == "OPEN" and now - sig["detected_at"] > EMA_SIGNAL_TIMEOUT_SEC:
                last_price = candles[-1]["close"] if candles else entry
                close_ema_signal(sig, "TIMEOUT", last_price)
        except Exception as e:
            log_error(f"update_ema_outcomes {sig.get('symbol')}: {e}")


SNAPSHOT_MODULE_KEYS = {
    "volume": "signals",
    "divergence": "div_signals",
    "ema": "ema_signals",
    "scalp": "scalp_signals",
    "session": "session_signals",
    "session_ny": "session_ny_signals",
}


def save_signal_snapshot(module, limit=100, name=None):
    """Freezes up to `limit` of the module's most recent CLOSED signals
    (every field they carry, diagnostics included — adx/rr/ema_gap_pct/
    atr_pct/etc. for EMA, whatever the module tracks) under a new
    snapshot id. Only CLOSED signals are kept — a replay recomputes
    win/loss stats, which needs a resolved result; an OPEN one would
    just be dead weight. STATE[<list>] is stored newest-first
    (appendleft on creation), so signals[:limit] is already "most
    recent N", no sorting needed. Returns the snapshot's metadata, or
    None if the module name isn't recognized or there's nothing closed
    yet to save."""
    state_key = SNAPSHOT_MODULE_KEYS.get(module)
    if state_key is None:
        return None
    with state_lock:
        signals = list(STATE.get(state_key, []))
    closed = [s for s in signals if s.get("status") == "CLOSED" and s.get("result") in ("WIN", "LOSS", "TIMEOUT", "BREAKEVEN")]
    closed = closed[:limit]
    if not closed:
        return None
    snap_id = f"{module}-{int(time.time())}"
    snapshot = {
        "id": snap_id, "module": module, "name": name or snap_id,
        "saved_at": time.time(), "signals": closed, "count": len(closed),
    }
    with state_lock:
        STATE["signal_snapshots"][snap_id] = snapshot
    save_state()
    return {"id": snap_id, "module": module, "name": snapshot["name"], "saved_at": snapshot["saved_at"], "count": snapshot["count"]}


def list_signal_snapshots(module=None):
    with state_lock:
        snaps = list(STATE["signal_snapshots"].values())
    if module:
        snaps = [s for s in snaps if s["module"] == module]
    snaps.sort(key=lambda s: -s["saved_at"])
    return [{"id": s["id"], "module": s["module"], "name": s["name"], "saved_at": s["saved_at"], "count": s["count"]} for s in snaps]


_SNAPSHOT_REPLAY_OPS = {
    "gte": lambda v, threshold: v >= threshold,
    "lte": lambda v, threshold: v <= threshold,
    "abs_gte": lambda v, threshold: abs(v) >= threshold,
    "abs_lte": lambda v, threshold: abs(v) <= threshold,
}


def _signal_passes_replay_filters(sig, filters):
    """filters: list of {"field": str, "op": one of _SNAPSHOT_REPLAY_OPS,
    "value": number}. A signal passes only if EVERY condition holds; a
    condition on a field the signal doesn't have (None — e.g. an old
    signal saved before that diagnostic existed) fails CLOSED, treated
    as not passing rather than silently skipped, matching how a live
    filter would treat missing data (see EMA_MIN_RR's own `rr is not
    None and rr < threshold` guard — same "missing means can't confirm
    it clears the bar" logic, not "missing means let it through")."""
    for f in filters:
        val = sig.get(f["field"])
        if val is None:
            return False
        op = _SNAPSHOT_REPLAY_OPS.get(f["op"])
        if op is None or not op(val, f["value"]):
            return False
    return True


def replay_signal_snapshot(snap_id, filters):
    """Recomputes win/loss/winrate and an MFE/MAE-at-close breakdown
    (same agg() shape compute_ema_stats() etc. already use) against a
    saved snapshot, keeping only signals that pass `filters`. Entirely
    offline against already-stored data — no live scanning, no network
    calls, no waiting for new signals. This can only ever narrow what a
    snapshot already contains: a signal that a filter active AT SAVE
    TIME already rejected was never created in the first place, so it
    isn't in the snapshot to test a looser threshold against — replay
    can simulate a STRICTER version of an existing filter, not recover
    what an even-stricter one back then would have thrown away, and
    obviously can't simulate an entirely new detection rule that never
    ran. Returns None if the snapshot id doesn't exist."""
    with state_lock:
        snapshot = STATE["signal_snapshots"].get(snap_id)
    if snapshot is None:
        return None
    survivors = [s for s in snapshot["signals"] if _signal_passes_replay_filters(s, filters)]
    wins = sum(1 for s in survivors if s.get("result") == "WIN")
    losses = sum(1 for s in survivors if s.get("result") == "LOSS")
    timeouts = sum(1 for s in survivors if s.get("result") == "TIMEOUT")
    breakevens = sum(1 for s in survivors if s.get("result") == "BREAKEVEN")
    total = wins + losses
    winrate = round(wins / total * 100, 1) if total else None

    def agg(key, subset):
        vals = [s[key] for s in subset if s.get(key) is not None]
        if not vals:
            return None
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        return {
            "avg": round(sum(vals) / n, 3), "median": round(vals_sorted[n // 2], 3),
            "p25": round(vals_sorted[int(n * 0.25)], 3),
            "p75": round(vals_sorted[min(int(n * 0.75), n - 1)], 3), "n": n,
        }

    win_set = [s for s in survivors if s.get("result") == "WIN"]
    loss_set = [s for s in survivors if s.get("result") == "LOSS"]
    return {
        "snapshot_id": snap_id, "original_count": snapshot["count"], "surviving_count": len(survivors),
        "wins": wins, "losses": losses, "timeouts": timeouts, "breakevens": breakevens,
        "total": total, "winrate": winrate,
        "rr_all": agg("rr", survivors), "rr_wins": agg("rr", win_set), "rr_losses": agg("rr", loss_set),
        "mfe_r_wins_at_close": agg("mfe_r_at_close", win_set), "mae_r_wins_at_close": agg("mae_r_at_close", win_set),
        "mfe_r_losses_at_close": agg("mfe_r_at_close", loss_set), "mae_r_losses_at_close": agg("mae_r_at_close", loss_set),
    }


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
    timeout_set = [s for s in dataset if s.get("result") == "TIMEOUT"]

    return {
        "open": open_count, "wins": wins, "losses": losses,
        "timeouts": timeouts, "winrate": winrate, "closed_total": total,
        "mfe_r_all": agg("mfe_r", dataset), "mae_r_all": agg("mae_r", dataset),
        "mfe_r_wins": agg("mfe_r", win_set), "mae_r_wins": agg("mae_r", win_set),
        "mfe_r_losses": agg("mfe_r", loss_set), "mae_r_losses": agg("mae_r", loss_set),
        "mfe_r_open": agg("mfe_r", open_set), "mae_r_open": agg("mae_r", open_set),
        "mfe_r_wins_at_close": agg("mfe_r_at_close", win_set), "mae_r_wins_at_close": agg("mae_r_at_close", win_set),
        "mfe_r_losses_at_close": agg("mfe_r_at_close", loss_set), "mae_r_losses_at_close": agg("mae_r_at_close", loss_set),
        # Realized R for TIMEOUT closes specifically — see close_ema_
        # signal()'s comment: this is the only place TIMEOUT's actual $
        # impact is visible, since the plain winrate excludes it
        # entirely. If this comes out net negative, timeouts are a real
        # (if quiet) drag on the account that the headline winrate
        # can't show.
        "exit_r_timeouts": agg("exit_r", timeout_set),
        "dataset_count": len(dataset),
        # Diagnostic breakdown (v0.62.0) — win vs loss comparison for the
        # fields _ema_signal_diagnostics() attaches at signal time. None
        # of these were used to decide whether a signal fired; this is
        # purely to see whether losses cluster on high ATR, weak/flat
        # EMA28 slope, marginal EMA7/14 separation, or choppy recent-
        # crossover conditions, before committing to any actual filter.
        "atr_pct_wins": agg("atr_pct", win_set), "atr_pct_losses": agg("atr_pct", loss_set),
        "ema_slope_pct_wins": agg("ema_slope_pct", win_set), "ema_slope_pct_losses": agg("ema_slope_pct", loss_set),
        "ema_gap_pct_wins": agg("ema_gap_pct", win_set), "ema_gap_pct_losses": agg("ema_gap_pct", loss_set),
        "recent_crossover_count_wins": agg("recent_crossover_count", win_set),
        "recent_crossover_count_losses": agg("recent_crossover_count", loss_set),
        "adx_wins": agg("adx", win_set), "adx_losses": agg("adx", loss_set),
        # rr is per-signal now (v0.65.0, ATR-based SL) instead of one
        # global constant — this is what the header display shows in
        # place of the old fixed EMA_RR value.
        "rr_all": agg("rr", dataset), "rr_wins": agg("rr", win_set), "rr_losses": agg("rr", loss_set),
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
        # rr is per-signal now (v0.88.0, ATR-based SL) instead of one
        # global constant — this is what the header display shows in
        # place of the old fixed DIV_RR value.
        "rr_all": agg("rr", dataset), "rr_wins": agg("rr", win_set), "rr_losses": agg("rr", loss_set),
        "atr_pct_wins": agg("atr_pct", win_set), "atr_pct_losses": agg("atr_pct", loss_set),
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


GET_CANDLES_RETRIES = int(os.environ.get("VP_GET_CANDLES_RETRIES", 2))  # extra attempts on connection-level failures (DNS, connect timeout) before giving up — a brief network blip shouldn't get a symbol miscounted as illiquid, see excluded_fetch_error below
GET_CANDLES_RETRY_DELAY = float(os.environ.get("VP_GET_CANDLES_RETRY_DELAY", 1.5))  # seconds between retries


def get_candles(symbol, interval=INTERVAL, limit=LOOKBACK + 5):
    """Fetches candles for one symbol. Retries GET_CANDLES_RETRIES times
    on requests.exceptions.ConnectionError (DNS resolution failures,
    refused/reset connections) AND requests.exceptions.Timeout (covers
    both connect and READ timeouts), with a short delay between
    attempts. Read timeouts were deliberately excluded from retries in
    an earlier version, reasoning that a real outage or rate limit
    shouldn't turn into a retry pile-up — reversed here against actual
    evidence: a live error-log screenshot showed "Read timed out (read
    timeout=10)" recurring across many different symbols over several
    minutes, consistent with WORKERS (12 concurrent requests) routinely
    exceeding HTTP_TIMEOUT under real mobile-network conditions, not a
    hard outage — retrying is the right call for that pattern. The
    retry count stays capped at GET_CANDLES_RETRIES either way, so even
    if this guess is wrong for some future real outage, it adds bounded
    extra latency (a few seconds per symbol), not an unbounded pile-up.
    Does NOT retry on HTTP error responses (4xx/5xx) — the request DID
    complete there, and a 4xx/5xx is a real answer, not a connectivity
    blip, so retrying wouldn't change the outcome."""
    last_err = None
    for attempt in range(GET_CANDLES_RETRIES + 1):
        try:
            r = requests.get(
                f"{GATE_BASE}/futures/usdt/candlesticks",
                params={"contract": symbol, "interval": interval, "limit": limit},
                timeout=HTTP_TIMEOUT,
            )
            r.raise_for_status()
            # Gate.io returns oldest->newest already; fields: t,v,c,h,l,o,sum (varies by version)
            return _parse_candles(r.json())
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_err = e
            if attempt < GET_CANDLES_RETRIES:
                time.sleep(GET_CANDLES_RETRY_DELAY)
    raise last_err


def fetch_candles_concurrent(fetch_specs, workers=WORKERS):
    """Fetches candles for many (symbol, interval, limit) specs at once,
    in a thread pool, instead of one blocking get_candles() call at a
    time. Every update_*_outcomes() function used to do exactly that —
    `for sig in active: candles = get_candles(...)` — which serializes
    what's actually independent network I/O across however many active
    signals that module is tracking; with MFE tracking running for 24h
    past close on top of whatever's still OPEN, that list adds up, and
    doing it one request at a time was the single biggest cost in a
    full scan cycle. Returns a list of candle-lists in the SAME ORDER
    as fetch_specs; a spec whose fetch failed gets None at that
    position (logged, not raised) rather than derailing the rest of
    the batch."""
    results = [None] * len(fetch_specs)
    if not fetch_specs:
        return results

    def _one(i, spec):
        symbol, interval, limit = spec
        try:
            return i, get_candles(symbol, interval=interval, limit=limit)
        except Exception as e:
            log_error(f"fetch_candles_concurrent {symbol}: {e}")
            return i, None

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_one, i, spec) for i, spec in enumerate(fetch_specs)]
        for fut in as_completed(futs):
            i, candles = fut.result()
            results[i] = candles
    return results


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
        net_attempt = 0
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
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                # Same retry policy as get_candles()/get_tickers() — a
                # multi-chunk range fetch (used by "magnified profile"
                # and session backtests) has many more individual
                # requests than either of those, so it's proportionally
                # more likely to hit a transient network blip somewhere
                # in the middle; previously any single one would abort
                # the whole range fetch with no retry at all.
                net_attempt += 1
                if net_attempt > GET_CANDLES_RETRIES:
                    raise
                time.sleep(GET_CANDLES_RETRY_DELAY)
        for c in _parse_candles(r.json()):
            seen[c["time"]] = c
        cur = chunk_end
    return sorted(seen.values(), key=lambda x: x["time"])


def get_tickers():
    """Fetches the full USDT futures ticker list — build_universe() (and
    therefore the entire scan cycle) depends on this succeeding. Retries
    on the same (ConnectionError, Timeout) classes and policy as
    get_candles() (GET_CANDLES_RETRIES/GET_CANDLES_RETRY_DELAY, reused
    rather than duplicated) — a DNS blip or slow response here shouldn't
    cost a whole scan cycle (SCAN_INTERVAL_SEC, currently 45s+) when a
    couple of quick retries could recover it in a few seconds instead.
    scan_loop()'s own try/except still catches whatever gets past this
    (any exception, not just network ones) so one bad cycle was never
    able to kill the scan thread outright — but that fallback means
    losing the whole cycle, this retry means usually not needing to."""
    last_err = None
    for attempt in range(GET_CANDLES_RETRIES + 1):
        try:
            r = requests.get(f"{GATE_BASE}/futures/usdt/tickers", timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_err = e
            if attempt < GET_CANDLES_RETRIES:
                time.sleep(GET_CANDLES_RETRY_DELAY)
    raise last_err


_contract_spec_cache = {}
_contract_spec_cache_lock = threading.Lock()
CONTRACT_SPEC_CACHE_TTL_SEC = 3600  # contract specs (multiplier, min size, max leverage) change rarely — an hour-old value is fine


def get_contract_spec(symbol):
    """quanto_multiplier: how much of the underlying one contract represents
    — position notional in USD = size_in_contracts * quanto_multiplier *
    mark_price, so this is what turns a target $ notional into a contract
    count. order_size_min: smallest order Gate accepts for this contract
    (usually 1, but not guaranteed). leverage_max: highest leverage Gate
    allows on this specific contract — the EMA-screener project hit real
    bugs assuming a flat leverage cap across all coins; this fetches the
    real per-contract value instead. order_price_round: the tick size —
    every order/trigger price must be an exact multiple of this or Gate
    rejects it with AUTO_INVALID_PARAM_TRIGGER_PRICE (hit this live: a
    computed SL/TP price with more decimal places than the contract
    allows got rejected outright)."""
    with _contract_spec_cache_lock:
        cached = _contract_spec_cache.get(symbol)
        if cached and time.time() - cached["fetched_at"] < CONTRACT_SPEC_CACHE_TTL_SEC:
            return cached["spec"]
    r = requests.get(f"{GATE_BASE}/futures/usdt/contracts/{symbol}", timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    spec = {
        "quanto_multiplier": float(data.get("quanto_multiplier", 0) or 0),
        "order_size_min": float(data.get("order_size_min", 1) or 1),
        "leverage_max": float(data.get("leverage_max", 20) or 20),
        "order_price_round": float(data.get("order_price_round", 0) or 0) or None,
    }
    with _contract_spec_cache_lock:
        _contract_spec_cache[symbol] = {"spec": spec, "fetched_at": time.time()}
    return spec


def round_to_tick(price, tick_size):
    """Snaps price to the nearest exact multiple of tick_size — Gate
    rejects trigger/order prices that aren't. Falls back to the raw price
    unchanged if tick_size is missing/zero (better to try the original
    value than silently mangle it when we don't actually know the tick)."""
    if not tick_size or tick_size <= 0:
        return price
    return round(round(price / tick_size) * tick_size, 12)


def format_price_str(price, tick_size=None):
    """Converts a price float to a plain fixed-point decimal string, never
    scientific notation. Python's str()/repr() silently switches to
    scientific notation for small floats (str(0.0000034) -> '3.4e-06'),
    and place_tp_sl_orders() was sending that straight through as Gate's
    trigger.price JSON value. Gate rejected it as an invalid trigger
    price (code 1009, AUTO_INVALID_PARAM_TRIGGER_PRICE) — silent on
    cheap/meme contracts (e.g. RATS_USDT) whose price sits below ~1e-4,
    never on ordinary-priced symbols, which is why this only showed up
    on some scalp signals.
    Decimal places are derived from tick_size's own string form (via
    Decimal, not float math — float log10 on a tick_size like 0.00001
    can itself be off by a rounding hair) so the output has exactly the
    precision the contract actually uses. Falls back to a generous 10
    decimals if tick_size is missing, still always fixed-point."""
    if tick_size:
        try:
            exponent = Decimal(str(tick_size)).as_tuple().exponent
            decimals = max(0, -exponent) if isinstance(exponent, int) else 10
        except Exception:
            decimals = 10
    else:
        decimals = 10
    return f"{price:.{decimals}f}"


def set_leverage(symbol, leverage):
    """POST /futures/usdt/positions/{contract}/leverage — must be set
    before placing an order at that leverage; Gate doesn't take leverage as
    an order-placement parameter itself, it's a standing per-contract
    position setting. Takes `leverage` as a query-string value."""
    return gate_signed_request(
        "POST", f"/futures/usdt/positions/{symbol}/leverage",
        query_string=f"leverage={leverage}",
    )


def compute_position_size(symbol, entry_price, size_mode, size_value, leverage, wallet_balance=None):
    """Turns the configured sizing (percent-of-wallet or flat $ margin) into
    a contract count. margin * leverage = notional; notional / (quanto_
    multiplier * price) = raw contract count, then snapped to the
    contract's own lot step (order_size_min).

    A real lesson from the EMA-screener project: on an expensive contract
    (large quanto_multiplier), the raw count can round to less than one
    lot — Gate simply can't place a sub-minimum order. That project forced
    a minimum-1-contract position in that case, which silently OVERSIZES
    the trade beyond what the sizing config actually asked for. That's the
    wrong default for real money: if hitting the minimum lot would need
    more than 1.5x the intended notional, skip the trade instead of
    silently taking on extra risk; only round up if the gap is small.

    Returns (contracts, notional_usd, margin_usd, skip_reason). skip_reason
    is None on success, otherwise a human-readable string and contracts=0."""
    spec = get_contract_spec(symbol)
    if size_mode == "percent":
        if wallet_balance is None:
            return 0, 0, 0, "wallet balance unavailable for percent-based sizing"
        margin_usd = wallet_balance * (size_value / 100.0)
    else:
        margin_usd = size_value
    if margin_usd <= 0:
        return 0, 0, 0, f"computed margin is {margin_usd} — check sizing config/wallet balance"
    # Fixed mode has no built-in relationship to the account balance, so it
    # never naturally scales down — with several positions already open
    # consuming margin, a flat $X request can easily exceed what's actually
    # free, and every attempt fails the same way (INSUFFICIENT_AVAILABLE)
    # until something closes. Check against real availability regardless of
    # mode rather than letting Gate reject it after the fact every time.
    if wallet_balance is not None and margin_usd > wallet_balance * 0.98:
        return 0, 0, 0, (f"computed margin ${margin_usd:.2f} exceeds available balance "
                          f"${wallet_balance:.2f} (with a 2% safety margin) — skipping rather than sending a doomed order")
    notional_usd = margin_usd * leverage
    multiplier = spec["quanto_multiplier"]
    if multiplier <= 0 or entry_price <= 0:
        return 0, 0, 0, f"invalid contract spec (multiplier={multiplier}) or price ({entry_price}) for {symbol}"
    min_size = spec["order_size_min"] or 1
    raw_contracts = notional_usd / (multiplier * entry_price)
    if raw_contracts < min_size:
        min_size_notional = min_size * multiplier * entry_price
        if min_size_notional > notional_usd * 1.5:
            return 0, 0, 0, (f"minimum order size for {symbol} ({min_size} contracts = "
                              f"${min_size_notional:.2f} notional) is more than 1.5x the intended "
                              f"${notional_usd:.2f} — skipping rather than oversizing")
        contracts = min_size  # gap is small enough to accept rounding up to the minimum lot
    else:
        contracts = math.floor(raw_contracts / min_size) * min_size
    actual_notional = contracts * multiplier * entry_price
    return contracts, actual_notional, actual_notional / leverage, None


def place_market_order(symbol, direction, contracts, reduce_only=False):
    """Market order, tif=ioc (the only tif Gate accepts at price=0/market).
    size sign encodes direction: positive=long, negative=short."""
    size = contracts if direction == "LONG" else -contracts
    body = {"contract": symbol, "size": size, "price": "0", "tif": "ioc"}
    if reduce_only:
        body["reduce_only"] = True
    return gate_signed_request("POST", "/futures/usdt/orders", body=body)


def _close_order_initial(symbol, direction, dual):
    """Builds the "initial" close-order payload for a price-triggered
    order. Position-mode-dependent (see place_close_trigger_order
    docstring) — split out so both the normal TP/SL placement and a
    later breakeven-move replacement build it identically."""
    auto_size = "close_long" if direction == "LONG" else "close_short"
    if dual:
        return {"contract": symbol, "size": 0, "price": "0", "tif": "ioc", "auto_size": auto_size, "reduce_only": True}
    return {"contract": symbol, "size": 0, "price": "0", "close": True, "tif": "ioc"}


def place_close_trigger_order(symbol, direction, price, rule, tick=None, price_type=0):
    """Places a single price-triggered close order (used for TP, SL, and
    later for replacing an SL at breakeven). rule follows Gate's
    price_orders convention: 1 = trigger when mark/last price rises to
    meet `price`, 2 = trigger when it falls to meet it — caller picks
    whichever matches what this particular order should do.
    The "initial" close-order schema genuinely differs by account
    position mode (confirmed the hard way — a request built for single
    mode 400'd under dual/hedge mode): single mode closes via
    size=0/close=true; dual mode instead needs auto_size ("close_long"/
    "close_short") plus reduce_only=true, and doesn't use `close` at all.
    tick is passed through to format_price_str() so trigger.price is
    always sent as plain fixed-point decimal, never Python's scientific
    notation for small floats (the cause of a real AUTO_INVALID_PARAM_
    TRIGGER_PRICE failure on cheap/meme contracts like RATS_USDT)."""
    try:
        dual = get_dual_mode()
    except Exception as e:
        log_error(f"place_close_trigger_order {symbol}: couldn't determine position mode ({e}), assuming single-mode")
        dual = False
    initial = _close_order_initial(symbol, direction, dual)
    return gate_signed_request("POST", "/futures/usdt/price_orders", body={
        "initial": initial,
        "trigger": {"strategy_type": 0, "price_type": price_type, "price": format_price_str(price, tick), "rule": rule, "expiration": 0},
    })


def place_tp_sl_orders(symbol, direction, tp_price, sl_price, tick=None, price_type=0):
    """Places both the TP and SL as separate price-triggered close orders,
    via place_close_trigger_order(). Returns (tp_order, sl_order, errors)
    — errors is a list of (which, msg) for whichever leg failed, so one
    failing doesn't silently hide the other's success or failure."""
    if direction == "LONG":
        tp_rule, sl_rule = 1, 2
    else:
        tp_rule, sl_rule = 2, 1
    errors = []
    tp_order = sl_order = None
    try:
        tp_order = place_close_trigger_order(symbol, direction, tp_price, tp_rule, tick, price_type)
    except Exception as e:
        errors.append(("tp", str(e)))
    try:
        sl_order = place_close_trigger_order(symbol, direction, sl_price, sl_rule, tick, price_type)
    except Exception as e:
        errors.append(("sl", str(e)))
    return tp_order, sl_order, errors


def move_stop_to_breakeven(symbol, direction, sl_order_id, entry, tick, buffer_pct=None):
    """Cancels the existing SL trigger order and replaces it with one at
    breakeven — entry plus a small buffer in the trade's favor
    (BREAKOUT_BREAKEVEN_BUFFER_PCT), so a dead-even wick still covers
    fees/slippage rather than landing exactly on entry.
    Returns the new SL order's id, or None if either step failed (logged
    via log_error, not raised — caller marks the signal as "already
    tried" regardless, so a failure here doesn't retry every cycle and
    spam the API/log).
    Order matters: the old SL is cancelled FIRST, then the new one is
    placed. If the new placement then fails, the position is briefly
    unprotected (no SL at all) until the next reconcile/manual check —
    the alternative (place-then-cancel) risks briefly having two live
    SL orders that could both fire, which is worse (a double-close
    attempt) than a short unprotected gap on what should be an already-
    favorable trade."""
    buffer_pct = BREAKOUT_BREAKEVEN_BUFFER_PCT if buffer_pct is None else buffer_pct
    try:
        cancel_price_order(sl_order_id)
    except Exception as e:
        log_error(f"move_stop_to_breakeven {symbol}: failed to cancel old SL {sl_order_id}: {e}")
        return None
    breakeven_price = entry * (1 + buffer_pct) if direction == "LONG" else entry * (1 - buffer_pct)
    sl_rule = 2 if direction == "LONG" else 1
    try:
        new_sl = place_close_trigger_order(symbol, direction, breakeven_price, sl_rule, tick)
    except Exception as e:
        log_error(f"move_stop_to_breakeven {symbol}: old SL cancelled but new breakeven SL failed to place ({e}) — position may be UNPROTECTED, check manually")
        return None
    return new_sl.get("id") if isinstance(new_sl, dict) else None


def get_futures_wallet_balance():
    """GET /futures/usdt/accounts — returns the USDT futures wallet's
    available balance, used for percent-of-deposit position sizing."""
    data = gate_signed_request("GET", "/futures/usdt/accounts")
    return float(data.get("available", 0) or 0)


_dual_mode_cache = {"value": None, "fetched_at": 0}
_dual_mode_cache_lock = threading.Lock()
DUAL_MODE_CACHE_TTL_SEC = 3600  # this is an account-level setting that essentially never changes mid-session


def get_dual_mode():
    """Whether the account is in two-side (hedge) position mode — GET
    /futures/usdt/accounts returns in_dual_mode. This matters because
    Gate's close-position order schema is genuinely different between
    modes: single mode closes with size=0/close=true; dual mode instead
    needs auto_size ("close_long"/"close_short") + reduce_only=true, and
    a request built for one mode gets rejected under the other — the
    exact 400 that happened before this existed."""
    now = time.time()
    with _dual_mode_cache_lock:
        if _dual_mode_cache["value"] is not None and now - _dual_mode_cache["fetched_at"] < DUAL_MODE_CACHE_TTL_SEC:
            return _dual_mode_cache["value"]
    data = gate_signed_request("GET", "/futures/usdt/accounts")
    dual = bool(data.get("in_dual_mode", False))
    with _dual_mode_cache_lock:
        _dual_mode_cache["value"] = dual
        _dual_mode_cache["fetched_at"] = now
    return dual


def get_open_positions():
    """GET /futures/usdt/positions — all positions, filtered to non-zero
    size (Gate returns every contract ever touched, most with size=0)."""
    data = gate_signed_request("GET", "/futures/usdt/positions")
    return [p for p in data if float(p.get("size", 0) or 0) != 0]


def get_open_price_orders():
    """GET /futures/usdt/price_orders?status=open — every still-pending
    price-triggered (TP/SL) order."""
    return gate_signed_request("GET", "/futures/usdt/price_orders", query_string="status=open")


_unprotected_alerted = set()  # contracts already flagged — avoids re-alerting on every single new trade while the same position stays unprotected


def cancel_price_order(order_id):
    """DELETE /futures/usdt/price_orders/{order_id} — cancels one still-
    pending trigger order."""
    return gate_signed_request("DELETE", f"/futures/usdt/price_orders/{order_id}")


def reconcile_positions_and_orders():
    """One combined pass over live positions + live trigger orders,
    fetched once and reused for both checks (rather than two separate
    functions each re-fetching the same data):
    (1) positions with NO attached trigger order at all — alerted via
        Telegram, deduped so the same still-unprotected contract doesn't
        re-alert on every subsequent trade.
    (2) trigger orders whose position has ALREADY closed — Gate has no
        native OCO, so when TP fires and closes a position, the paired
        SL order (or vice versa) just sits there as a live trigger with
        nothing left to close, and would fire against whatever NEW
        position might later open on that same contract if left alone.
        These get cancelled outright.
    Called both opportunistically (right before a new real trade opens)
    AND on its own timer (reconcile_loop(), RECONCILE_INTERVAL_SEC) —
    the opportunistic call alone left orphaned orders sitting for as
    long as the market stayed quiet with no new trades to piggyback the
    cleanup on, which is exactly what a live example showed (16 open
    orders against only 2 open positions after a lull with nothing new
    triggering a reconcile pass).
    Returns (unprotected_contracts, cancelled_contracts)."""
    try:
        positions = get_open_positions()
        triggers = get_open_price_orders()
    except Exception as e:
        log_error(f"reconcile_positions_and_orders: {e}")
        return [], []

    open_contracts = {p["contract"] for p in positions if p.get("contract")}
    triggered_contracts = {t.get("initial", {}).get("contract") for t in triggers if t.get("initial", {}).get("contract")}

    unprotected = [c for c in open_contracts if c not in triggered_contracts]
    with _scalp_signal_cooldowns_lock:  # reusing an existing lock for this tiny bit of shared state rather than adding a new one
        new_ones = [c for c in unprotected if c not in _unprotected_alerted]
        _unprotected_alerted.intersection_update(unprotected)
        _unprotected_alerted.update(unprotected)
    if new_ones:
        send_telegram(
            f"⚠️ Незащищённые позиции без TP/SL: {', '.join(new_ones)} — проверь вручную на бирже",
            category=None,
        )

    cancelled = []
    for t in triggers:
        contract = t.get("initial", {}).get("contract")
        order_id = t.get("id")
        if contract and contract not in open_contracts and order_id is not None:
            try:
                cancel_price_order(order_id)
                cancelled.append(contract)
            except Exception as e:
                log_error(f"reconcile_positions_and_orders: failed to cancel orphaned order {order_id} ({contract}): {e}")
    if cancelled:
        log_error(f"reconcile_positions_and_orders: cancelled {len(cancelled)} orphaned trigger order(s): {cancelled}")

    return unprotected, cancelled


def execute_autotrade(mode, symbol, direction, entry, sl, tp, leverage, extra=None, size_mode=None, size_value=None):
    """The single entry point every signal source calls to (maybe) fire a
    real trade. `mode` is a short label (e.g. "bounce", "ema", "scalp") used
    for the auto-trade-enabled toggle lookup and the log. `extra` is any
    signal-specific context worth keeping in the log (reason, interval,
    etc.) — purely informational, not used for trading logic.
    size_mode/size_value override the shared AUTOTRADE_SIZE_MODE/VALUE for
    this call only — used by scalp to trade its own configured amount
    (SCALP_SIZE_MODE/VALUE) instead of the one shared by every other mode.
    Left as None (the default), which is what every OTHER mode's call site
    still does, this behaves exactly as before.

    Always writes exactly one entry to STATE["autotrade_log"], whether it
    trades, skips, or dry-runs, so the log is a complete record of every
    signal that was even considered, not just the ones that fired."""
    size_mode = AUTOTRADE_SIZE_MODE if size_mode is None else size_mode
    size_value = AUTOTRADE_SIZE_VALUE if size_value is None else size_value
    record = {
        "time": time.time(), "mode": mode, "symbol": symbol, "direction": direction,
        "entry": entry, "sl": sl, "tp": tp, "leverage": leverage,
        "dry_run": AUTOTRADE_DRY_RUN, "extra": extra or {},
        "status": None, "detail": None, "contracts": None, "order_id": None,
    }
    try:
        wallet_balance = None
        if not AUTOTRADE_DRY_RUN:
            wallet_balance = get_futures_wallet_balance()
        elif size_mode == "percent":
            # dry-run with percent sizing still needs a balance to show a
            # realistic contract count in the log, but shouldn't require
            # live credentials just to preview — fall back to a nominal
            # $1000 for the estimate and say so.
            if GATE_API_KEY and GATE_API_SECRET:
                try:
                    wallet_balance = get_futures_wallet_balance()
                except Exception:
                    wallet_balance = 1000.0
                    record["extra"]["balance_note"] = "fetch failed, used nominal $1000 for dry-run estimate"
            else:
                wallet_balance = 1000.0
                record["extra"]["balance_note"] = "no credentials configured, used nominal $1000 for dry-run estimate"

        try:
            leverage_max = get_contract_spec(symbol).get("leverage_max")
            if leverage_max and leverage > leverage_max:
                record["extra"]["leverage_requested"] = leverage
                leverage = leverage_max
        except Exception as e:
            log_error(f"execute_autotrade {symbol}: couldn't fetch leverage_max ({e}), using requested leverage as-is")

        # Liquidation-safety check, v0.70.0 — previously only the scalp
        # module ever compared its SL distance against the liquidation
        # buffer at the chosen leverage; every other mode (bounce/
        # breakout/divergence/ema/session) placed its SL with no such
        # check at all. That was always a latent risk, but harmless in
        # practice while EMA's SL was a tight fixed 0.4% — nowhere near
        # a typical liquidation distance. It stopped being harmless the
        # moment EMA's SL became ATR-based (v0.65.0) and started coming
        # out WIDER than before on volatile symbols: user directly
        # reported live cases where the computed SL sat further from
        # entry than the exchange's own liquidation price — meaning
        # Gate would forcibly liquidate the position before that SL
        # order could ever trigger, turning a bounded, intended loss
        # into an uncontrolled one at whatever the liquidation engine's
        # own (worse) price ends up being.
        # Reuses compute_scalp_liquidation_move_pct() — despite the
        # name, its math (Gate's isolated-margin liquidation formula)
        # isn't scalp-specific, just first written for that module.
        # mmr_pct comes from the same STATE["scalp_mmr_map"] the scalp
        # module already refreshes every SCALP_REFRESH_SEC — MMR is a
        # property of the Gate contract itself, not of which module is
        # trading it, so reusing that cache instead of a fresh fetch is
        # correct, not a shortcut. Falls back to SCALP_DEFAULT_MMR_PCT
        # (a deliberately conservative default) for a symbol the scalp
        # universe hasn't covered yet.
        try:
            with state_lock:
                mmr_map = STATE.get("scalp_mmr_map", {})
            mmr_pct = mmr_map.get(symbol, SCALP_DEFAULT_MMR_PCT)
            liq_buffer_pct = compute_scalp_liquidation_move_pct(direction, leverage, mmr_pct)
            sl_distance_pct = abs(entry - sl) / entry * 100 if entry else None
            if liq_buffer_pct is not None and sl_distance_pct is not None:
                if liq_buffer_pct < sl_distance_pct * SCALP_SAFETY_MARGIN:
                    record["status"] = "SKIPPED"
                    record["detail"] = (
                        f"SL distance {sl_distance_pct:.3f}% at {leverage}x leverage doesn't clear the "
                        f"liquidation buffer ({liq_buffer_pct:.3f}%, needs >= {SCALP_SAFETY_MARGIN}x margin) — "
                        f"skipping rather than placing an SL that could never actually trigger"
                    )
                    with state_lock:
                        STATE["autotrade_log"].appendleft(record)
                    return record
        except Exception as e:
            log_error(f"execute_autotrade {symbol}: liquidation-safety check failed ({e}), proceeding without it — this is exactly the gap this check exists to close, so treat any recurrence of this log line as worth investigating")

        contracts, notional, margin, skip_reason = compute_position_size(
            symbol, entry, size_mode, size_value, leverage, wallet_balance)
        record["leverage"] = leverage  # reflect the (possibly clamped) value actually used, not the originally requested one
        record["contracts"] = contracts
        record["notional_usd"] = round(notional, 2) if notional else notional
        record["margin_usd"] = round(margin, 2) if margin else margin

        if skip_reason:
            record["status"] = "SKIPPED"
            record["detail"] = skip_reason
            with state_lock:
                STATE["autotrade_log"].appendleft(record)
            return record

        if AUTOTRADE_DRY_RUN:
            record["status"] = "DRY_RUN"
            record["detail"] = f"would open {direction} {contracts} contracts on {symbol} @ {leverage}x, TP {tp} / SL {sl}"
            with state_lock:
                STATE["autotrade_log"].appendleft(record)
            return record

        try:
            reconcile_positions_and_orders()
        except Exception as e:
            log_error(f"execute_autotrade {symbol}: reconcile before open failed: {e}")

        set_leverage(symbol, leverage)
        order = place_market_order(symbol, direction, contracts)
        record["order_id"] = order.get("id") if isinstance(order, dict) else None
        fill_price = None
        if isinstance(order, dict):
            fp = order.get("fill_price")
            if fp:
                try:
                    fill_price = float(fp)
                except (TypeError, ValueError):
                    fill_price = None
        record["fill_price"] = fill_price

        try:
            tick = get_contract_spec(symbol).get("order_price_round")
        except Exception:
            tick = None
        tp_rounded = round_to_tick(tp, tick)
        sl_rounded = round_to_tick(sl, tick)
        record["tp_rounded"] = tp_rounded
        record["sl_rounded"] = sl_rounded
        tp_order, sl_order, tp_sl_errors = place_tp_sl_orders(symbol, direction, tp_rounded, sl_rounded, tick=tick)
        record["tick"] = tick
        record["tp_order_id"] = tp_order.get("id") if isinstance(tp_order, dict) else None
        record["sl_order_id"] = sl_order.get("id") if isinstance(sl_order, dict) else None
        if tp_sl_errors:
            record["status"] = "OPENED_TP_SL_FAILED"
            record["detail"] = f"position opened but TP/SL placement had errors: {tp_sl_errors} — check the position manually"
        else:
            record["status"] = "OPENED"
            record["detail"] = f"opened {direction} {contracts} contracts on {symbol} @ {leverage}x"
        with state_lock:
            STATE["autotrade_log"].appendleft(record)
        return record
    except Exception as e:
        record["status"] = "ERROR"
        record["detail"] = str(e)
        log_error(f"execute_autotrade {mode} {symbol}: {e}")
        with state_lock:
            STATE["autotrade_log"].appendleft(record)
        return record


def sim_execute_trade(mode, symbol, direction, entry, sl, tp, leverage, signal_record, size_mode=None, size_value=None):
    """Opens a paper trade against the running simulated balance, sized
    with the SAME AUTOTRADE_SIZE_MODE/AUTOTRADE_SIZE_VALUE config real
    auto-trading uses by default (so the simulation reflects whatever
    sizing the person actually has configured, not a separate hardcoded
    scheme). size_mode/size_value override this for one call — scalp
    passes its own SCALP_SIZE_MODE/VALUE here so the paper simulation
    matches what its real trades actually use, same override pattern as
    execute_autotrade().
    Keeps a direct reference to signal_record so sweep_sim_trades() can
    read its real eventual outcome later — that record gets mutated in
    place by the module's own outcome-tracking function when it resolves,
    so no separate lookup is needed, just checking the same dict again."""
    size_mode = AUTOTRADE_SIZE_MODE if size_mode is None else size_mode
    size_value = AUTOTRADE_SIZE_VALUE if size_value is None else size_value
    with state_lock:
        balance = STATE["sim_balance"]
    if balance <= 0:
        return None  # busted — stop opening new paper trades until manually reset
    if size_mode == "percent":
        margin = balance * (size_value / 100.0)
    else:
        margin = size_value
    margin = min(margin, balance)  # can't risk more than the paper account actually has
    if margin <= 0:
        return None
    notional = margin * leverage
    entry_fee = notional * AUTOTRADE_SIM_FEE_PCT
    trade = {
        "time": time.time(), "mode": mode, "symbol": symbol, "direction": direction,
        "entry": entry, "sl": sl, "tp": tp, "leverage": leverage,
        "margin": round(margin, 4), "notional": round(notional, 4), "entry_fee": round(entry_fee, 4),
        "status": "PENDING", "result": None, "pnl": None, "balance_after": None,
        "_signal_ref": signal_record,
    }
    with state_lock:
        STATE["sim_balance"] = round(STATE["sim_balance"] - entry_fee, 6)
        STATE["sim_trades"].append(trade)
    return trade


def sweep_sim_trades():
    """Settles any pending paper trade whose originating signal has since
    resolved. PnL is computed from the ACTUAL exit_price the signal closed
    at (whichever of TP/SL/timeout-close it really was), not an assumed
    R-multiple — the whole point is reflecting what genuinely happened."""
    with state_lock:
        pending = [t for t in STATE["sim_trades"] if t["status"] == "PENDING"]
    for t in pending:
        rec = t.get("_signal_ref")
        if rec is None or rec.get("status") != "CLOSED":
            continue
        exit_price = rec.get("exit_price")
        result = rec.get("result")
        if exit_price is None:
            log_error(f"sweep_sim_trades: {t['symbol']} closed with result={result} but no exit_price — leaving pending")
            continue
        entry = t["entry"]
        if entry <= 0:
            continue
        move_pct = (exit_price - entry) / entry if t["direction"] == "LONG" else (entry - exit_price) / entry
        gross_pnl = t["notional"] * move_pct
        exit_fee = t["notional"] * AUTOTRADE_SIM_FEE_PCT
        net_pnl = gross_pnl - exit_fee
        with state_lock:
            STATE["sim_balance"] = round(STATE["sim_balance"] + net_pnl, 6)
            t["status"] = "SETTLED"
            t["result"] = result
            t["pnl"] = round(net_pnl, 4)
            t["balance_after"] = STATE["sim_balance"]
            t["_signal_ref"] = None  # drop the reference once settled, nothing more to read from it


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
            net_attempt = 0
            while True:
                try:
                    r = requests.get(f"{GATE_BASE}/futures/usdt/risk_limit_tiers",
                                      params={"limit": limit, "offset": offset}, timeout=HTTP_TIMEOUT)
                    r.raise_for_status()
                    break
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                    # Same retry policy as get_candles()/get_tickers()/
                    # get_candles_range() — this runs infrequently
                    # (SCALP_REFRESH_SEC, hours apart), but a network
                    # blip mid-pagination previously meant losing
                    # whatever pages hadn't been fetched yet for that
                    # entire cycle rather than just retrying the one
                    # page that failed.
                    net_attempt += 1
                    if net_attempt > GET_CANDLES_RETRIES:
                        raise
                    time.sleep(GET_CANDLES_RETRY_DELAY)
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
    single best (interval, direction, target%) combination by actual EV
    (see ev_per_trade_pct below) among every target that clears
    SCALP_MIN_HIT_RATE, needs no more leverage than the exchange
    actually allows for this contract (max_leverage — confirmed by the
    user that this varies a lot by coin, e.g. 10x on VELVET_USDT vs
    125x on majors; a target the math likes but the exchange won't let
    you execute isn't a real recommendation), and where the liquidation
    buffer at that leverage exceeds the coin's own historical p90
    adverse move by SCALP_SAFETY_MARGIN. Returns None if nothing on
    this symbol clears all three bars at any interval/direction/target
    — that's a legitimate, informative result (this coin isn't a safe,
    executable candidate for the stated goal), not an error.
    v0.91.0: previously stopped at the FIRST (largest) target clearing
    the hit-rate bar per (interval, direction), assuming a bigger
    target was always at least as good — true under the old hit_rate*
    frequency score, false under the current EV-based one, where a
    smaller target's usually-higher hit-rate can win on real EV. Now
    checks every qualifying target and keeps whichever scores best.
    v0.92.0: also requires target/sl_pct_est >= SCALP_MIN_RR — a
    positive-EV candidate can still have a SL disproportionately wider
    than its target (real losses do cost more than real wins), and this
    caps how lopsided that's allowed to get, on top of (not instead of)
    the EV ranking above."""
    best = None
    for interval, dirs in symbol_data.items():
        interval_sec = INTERVAL_SECONDS.get(interval, 300)
        for direction, summary in dirs.items():
            # v0.91.0: used to be sorted largest-target-first with a
            # `break` after the first one clearing SCALP_MIN_HIT_RATE —
            # correct under the OLD score (hit_rate*frequency, where a
            # bigger target only ever meant fewer trades/day, so
            # stopping early was a safe shortcut), but NOT under the
            # current EV-based score (ev_per_trade_pct = hit_frac*pct -
            # (1-hit_frac)*sl_pct_est): a smaller target usually clears
            # a much HIGHER hit-rate, and that can easily beat a bigger
            # target's raw size in the actual EV math. The old break
            # meant every qualifying symbol mechanically locked onto
            # its LARGEST clearing target without ever computing what
            # a smaller one's real EV would have been — exactly what a
            # live user complaint showed: every SKYAI_USDT signal used
            # target=3% (the largest in SCALP_TARGET_PCTS), and the
            # account was only barely profitable specifically because
            # stops kept coming out wider than that target. Now checks
            # every target this (interval, direction) offers and keeps
            # whichever genuinely scores best.
            for pct_str in summary.keys():
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
                # Previously: score = hit_rate * trades_per_day_est — ranked
                # purely on how many WINS/day to expect, completely blind to
                # how big a loss costs. A symbol with a wider stop (bigger
                # p90_adverse_pct) can out-rank one with a much better
                # hit-rate just by firing more often, even though its actual
                # expected return per trade is worse — exactly what happened
                # with KOMA_USDT outranking AKE_USDT despite AKE's clearly
                # better hit-rate, per direct user question about the
                # ranking. sl_pct_est mirrors the real SL that scan_symbol_
                # scalp_signal() actually places (p90_adverse_pct scaled by
                # the same SCALP_SL_BUFFER_MULT), so this uses the real risk
                # side, not the liquidation buffer (a different, unrelated
                # safety margin — liq_buffer_pct — that was never the right
                # basis for this and wasn't previously used in score either).
                sl_pct_est = s["p90_adverse_pct"] * (1 + SCALP_SL_BUFFER_MULT)
                if sl_pct_est <= 0 or pct / sl_pct_est < SCALP_MIN_RR:
                    continue  # SL too wide relative to this target — see SCALP_MIN_RR's own comment
                hit_frac = s["hit_rate"] / 100
                ev_per_trade_pct = hit_frac * pct - (1 - hit_frac) * sl_pct_est
                score = round(ev_per_trade_pct * trades_per_day_est, 4)
                candidate = {
                    "interval": interval, "direction": direction, "target_pct": pct,
                    "hit_rate": s["hit_rate"], "n": s["n"],
                    "median_bars_to_hit": s["median_bars_to_hit"],
                    "time_to_hit_hours": round(time_to_hit_hours, 2),
                    "trades_per_day_est": trades_per_day_est,
                    "rr": round(pct / sl_pct_est, 3),
                    "leverage": round(leverage, 2),
                    "max_leverage": max_leverage,
                    "liq_buffer_pct": round(liq_buffer, 3),
                    "p90_adverse_pct": s["p90_adverse_pct"],
                    "sl_pct_est": round(sl_pct_est, 3),
                    "ev_per_trade_pct": round(ev_per_trade_pct, 4),
                    "score": score,
                }
                if best is None or candidate["score"] > best["score"]:
                    best = candidate
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
        if has_open_signal_any_module(symbol, exclude="scalp_signals"):
            return  # another module already has an open position on this symbol — see has_open_signal_any_module's docstring for why this check exists

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
        # Timeout removed per direct request — a signal now waits as long as
        # it takes to hit either the target or the stop, never expiring into
        # an ambiguous TIMEOUT result. A very large finite number (not
        # float('inf')) keeps timeout_at safe to persist to disk — inf
        # serializes as the non-standard JSON token 'Infinity', which isn't
        # something to rely on for a value that gets saved via save_state().
        timeout_sec = 10 ** 12  # ~31,700 years — never actually reached, just avoids inf

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
            "mfe_price": entry, "mae_price": entry,  # best-favorable / worst-adverse price reached while OPEN
            "mfe_r_at_close": None, "mae_r_at_close": None,  # R-multiples (R = sl_pct), frozen once the trade resolves
        }
        with state_lock:
            STATE["scalp_signals"].appendleft(record)
        if AUTOTRADE_ENABLED_SCALP:
            execute_autotrade("scalp", symbol, direction, entry, sl_price, target_price,
                               rec["leverage"], extra={"interval": interval, "score": rec["score"]},
                               size_mode=SCALP_SIZE_MODE, size_value=SCALP_SIZE_VALUE)
            sim_execute_trade("scalp", symbol, direction, entry, sl_price, target_price,
                               rec["leverage"], record,
                               size_mode=SCALP_SIZE_MODE, size_value=SCALP_SIZE_VALUE)
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
    all_candles = fetch_candles_concurrent([(s["symbol"], s["interval"], 200) for s in open_signals])
    for sig, candles in zip(open_signals, all_candles):
        try:
            if candles is None:
                continue
            future = [c for c in candles if c["time"] >= sig["time"]]
            result = None
            exit_price = None
            exit_time = None
            sl_price = sig.get("sl_price")  # older signals created before SL existed won't have this — falls back to WIN/TIMEOUT only, same as before
            entry = sig["entry"]
            direction = sig["direction"]
            mfe_price = sig.get("mfe_price", entry)
            mae_price = sig.get("mae_price", entry)
            for c in future:
                if direction == "LONG":
                    mfe_price = max(mfe_price, c["high"])
                    mae_price = min(mae_price, c["low"])
                else:
                    mfe_price = min(mfe_price, c["low"])
                    mae_price = max(mae_price, c["high"])

                if sl_price is not None:
                    if direction == "LONG" and c["low"] <= sl_price:
                        result = "LOSS"
                        exit_price = sl_price
                        exit_time = c["time"]
                        break
                    if direction == "SHORT" and c["high"] >= sl_price:
                        result = "LOSS"
                        exit_price = sl_price
                        exit_time = c["time"]
                        break
                if direction == "LONG" and c["high"] >= sig["target_price"]:
                    result = "WIN"
                    exit_price = sig["target_price"]
                    exit_time = c["time"]
                    break
                if direction == "SHORT" and c["low"] <= sig["target_price"]:
                    result = "WIN"
                    exit_price = sig["target_price"]
                    exit_time = c["time"]
                    break

            risk_pct = sig.get("sl_pct")  # the R unit — % distance from entry to SL
            def r_multiple(price):
                if not risk_pct or entry <= 0:
                    return None
                move_pct = (price - entry) / entry * 100 if direction == "LONG" else (entry - price) / entry * 100
                return round(move_pct / risk_pct, 4)

            with state_lock:
                sig["mfe_price"] = mfe_price
                sig["mae_price"] = mae_price
                if result:
                    sig["status"] = "CLOSED"
                    sig["result"] = result
                    sig["exit_price"] = exit_price
                    sig["exit_time"] = exit_time
                    sig["mfe_r_at_close"] = r_multiple(mfe_price)
                    sig["mae_r_at_close"] = r_multiple(mae_price)
                elif now >= sig["timeout_at"]:
                    sig["status"] = "CLOSED"
                    sig["result"] = "TIMEOUT"
                    sig["exit_price"] = candles[-1]["close"] if candles else None
                    sig["exit_time"] = candles[-1]["time"] if candles else None
                    sig["mfe_r_at_close"] = r_multiple(mfe_price)
                    sig["mae_r_at_close"] = r_multiple(mae_price)
        except Exception as e:
            log_error(f"scalp_outcome {sig['symbol']}: {e}")


def compute_scalp_tuning_stats():
    """MFE/MAE (R-multiples, R = each signal's own sl_pct) split by
    WIN/LOSS at close — the same style of breakdown compute_tuning_stats()
    gives Volume and the EMA/divergence equivalents already have, added
    here specifically so a future scalp SL-buffer retune can be grounded
    in real excursion data instead of a guess."""
    with state_lock:
        signals = list(STATE["scalp_signals"])
    dataset = [s for s in signals if s.get("mfe_r_at_close") is not None and s.get("status") == "CLOSED"]
    wins = [s for s in dataset if s["result"] == "WIN"]
    losses = [s for s in dataset if s["result"] == "LOSS"]

    def agg(key, rows):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if not vals:
            return None
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        return {
            "avg": round(sum(vals) / n, 3), "median": round(vals_sorted[n // 2], 3),
            "p25": round(vals_sorted[int(n * 0.25)], 3), "p75": round(vals_sorted[min(int(n * 0.75), n - 1)], 3),
            "n": n,
        }

    return {
        "count": len(dataset), "wins_n": len(wins), "losses_n": len(losses),
        "mfe_r_wins_at_close": agg("mfe_r_at_close", wins), "mae_r_wins_at_close": agg("mae_r_at_close", wins),
        "mfe_r_losses_at_close": agg("mfe_r_at_close", losses), "mae_r_losses_at_close": agg("mae_r_at_close", losses),
    }


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
PARAM_GRID_RR = [1.5, 2.0, 2.5, 3.0]              # added 3.0 — full-window (24h) WIN MFE ran median 3.94R (bounce) vs the 2.0-2.5R the current grid tops out at capturing, so let auto-tune test whether a further target does better per symbol
PARAM_GRID_BUFFER = [0.20, 0.35, 0.50, 0.65]  # added 0.65 — full-window (24h) LOSS MFE averaged 2.737R (would have exceeded the TP itself before reversing) vs 0.343-0.461R at the moment the tight stop actually closed the trade, suggesting many "losses" reverse in the intended direction but the stop is too close to survive the noise; testing whether a wider buffer catches more of those per symbol

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
            sim_trades_out = [
                {k: v for k, v in t.items() if k != "_signal_ref"}
                for t in STATE["sim_trades"]
            ]
            data = {
                "overrides": SYMBOL_OVERRIDES,
                "signals": list(STATE["signals"]),
                "div_signals": list(STATE["div_signals"]),
                "ema_signals": list(STATE["ema_signals"]),
                "scalp_signals": list(STATE["scalp_signals"]),
                "session_signals": list(STATE["session_signals"]),
                "session_ny_signals": list(STATE["session_ny_signals"]),
                "xau_lg_signals": list(STATE["xau_lg_signals"]),
                "autotrade_log": list(STATE["autotrade_log"]),
                "sim_balance": STATE["sim_balance"],
                # Both PENDING and SETTLED now (previously PENDING was
                # excluded outright — see load_state()'s _relink_sim_trade()
                # for why that silently lost real money from the paper
                # balance on every restart). _signal_ref is dropped either
                # way since it's an in-memory object reference that can't
                # serialize meaningfully; load_state() re-attaches it to the
                # actual reloaded signal object, not a detached copy.
                "sim_trades": sim_trades_out,
                "risk_autotune_log": list(STATE["risk_autotune_log"]),
                "risk_autotune_last_change": STATE["risk_autotune_last_change"],
                "saved_at": time.time(),
            }
        tmp_path = STATE_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f)
        os.replace(tmp_path, STATE_FILE)
    except Exception as e:
        log_error(f"save_state: {e}")


def _relink_sim_trade(trade):
    """Best-effort re-link for a persisted PENDING sim trade: finds the
    OPEN signal in the matching module's just-reloaded list with the
    same symbol+direction and the closest detected_at to the trade's own
    creation time. Must be called AFTER the STATE[<module>_signals]
    deques are already populated in load_state() — it reads directly
    from STATE, not from the raw JSON.
    Needed because sweep_sim_trades() reads the trade's status through
    _signal_ref, which has to be the SAME object as the one living in
    STATE[<list>] for later mutations (WIN/LOSS/TIMEOUT) to be visible —
    a deserialized standalone copy of the old signal dict would never
    update again, silently freezing that trade as PENDING forever.
    10s tolerance: a sim trade is created moments after its signal in
    the same code path (never more than a couple seconds apart in
    practice), so anything wider is treated as "no real match" rather
    than risk attaching to the wrong signal.
    Returns the signal dict, or None if nothing close enough was found
    (e.g. that signal itself fell out of its own history maxlen)."""
    module_lists = {
        "bounce": STATE["signals"], "breakout": STATE["signals"],
        "divergence": STATE["div_signals"], "ema": STATE["ema_signals"],
        "scalp": STATE["scalp_signals"], "session": STATE["session_signals"],
        "session_ny": STATE["session_ny_signals"],
        "xau_lg": STATE["xau_lg_signals"],
    }
    candidates = module_lists.get(trade.get("mode"))
    if not candidates:
        return None
    best, best_dt = None, None
    for s in candidates:
        if s.get("status") != "OPEN":
            continue
        if s.get("symbol") != trade.get("symbol") or s.get("direction") != trade.get("direction"):
            continue
        dt = abs((s.get("detected_at") or 0) - (trade.get("time") or 0))
        if dt > 10:
            continue
        if best is None or dt < best_dt:
            best, best_dt = s, dt
    return best


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
        scalp_signals = data.get("scalp_signals", [])
        session_signals = data.get("session_signals", [])
        session_ny_signals = data.get("session_ny_signals", [])
        xau_lg_signals = data.get("xau_lg_signals", [])
        autotrade_log = data.get("autotrade_log", [])
        sim_trades = data.get("sim_trades", [])
        risk_autotune_log = data.get("risk_autotune_log", [])
        risk_autotune_last_change = data.get("risk_autotune_last_change", {})
        with state_lock:
            STATE["signals"] = deque(signals, maxlen=SIGNAL_HISTORY)
            STATE["div_signals"] = deque(div_signals, maxlen=DIV_SIGNAL_HISTORY)
            STATE["ema_signals"] = deque(ema_signals, maxlen=EMA_SIGNAL_HISTORY)
            STATE["scalp_signals"] = deque(scalp_signals, maxlen=SCALP_SIGNAL_HISTORY)
            STATE["session_signals"] = deque(session_signals, maxlen=SESSION_SIGNAL_HISTORY)
            STATE["session_ny_signals"] = deque(session_ny_signals, maxlen=SESSION_NY_SIGNAL_HISTORY)
            STATE["xau_lg_signals"] = deque(xau_lg_signals, maxlen=XAU_LG_SIGNAL_HISTORY)
            STATE["autotrade_log"] = deque(autotrade_log, maxlen=AUTOTRADE_TRADE_HISTORY)
            STATE["risk_autotune_log"] = deque(risk_autotune_log, maxlen=200)
            STATE["risk_autotune_last_change"] = risk_autotune_last_change
            if "sim_balance" in data:
                STATE["sim_balance"] = data["sim_balance"]
            restored_trades = []
            dropped_pending = 0
            for t in sim_trades:
                if t.get("status") == "PENDING":
                    match = _relink_sim_trade(t)
                    if match is None:
                        dropped_pending += 1
                        continue  # its own signal didn't survive either — can't ever resolve, drop rather than keep a permanently-stuck PENDING entry
                    t["_signal_ref"] = match
                restored_trades.append(t)
            STATE["sim_trades"] = deque(restored_trades, maxlen=AUTOTRADE_SIM_TRADE_HISTORY)
        print(f"Loaded persisted state: {len(SYMBOL_OVERRIDES)} overrides, {len(signals)} signals, {len(div_signals)} divergence signals, {len(ema_signals)} EMA signals, {len(scalp_signals)} scalp signals, {len(session_signals)} session signals, {len(autotrade_log)} autotrade log entries, {len(restored_trades)} sim trades ({dropped_pending} pending trades couldn't be re-linked and were dropped)")
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
    best_ev = None
    tried = []
    for lb in PARAM_GRID_LOOKBACK:
        for hvn in PARAM_GRID_HVN:
            for rr in PARAM_GRID_RR:
                for buf in PARAM_GRID_BUFFER:
                    res = backtest_params(candles, lb, hvn, rr, buffer_pct=buf, allowed_reasons={reason})
                    tried.append({**res, "lookback": lb, "hvn_top_n": hvn, "rr": rr, "buffer_pct": buf})
                    if res["trades"] < MIN_BACKTEST_TRADES or res["winrate"] is None:
                        continue
                    # v0.95.6: selection criterion changed from raw winrate to
                    # EV, per direct user question about whether the grid
                    # search was actually exploring wider targets or just
                    # picking the easiest one to hit. It was picking the
                    # easiest one: winrate alone is mechanically biased
                    # toward the SMALLEST rr in PARAM_GRID_RR almost
                    # regardless of true edge, since a nearer target is
                    # inherently easier to touch before price reverses —
                    # the exact same class of oversight already found and
                    # fixed for Scalp's target selection in v0.91.0. This
                    # backtest simulates SL/TP hits directly on historical
                    # candles with no slippage modeled, so within it a loss
                    # genuinely costs exactly -1R by construction — no
                    # overshoot correction needed here the way risk-
                    # autotune's live-execution stats needed one.
                    wr = res["winrate"] / 100
                    ev = wr * rr - (1 - wr) * 1.0
                    if best is None or ev > best_ev or (ev == best_ev and res["trades"] > best["trades"]):
                        best = {**res, "lookback": lb, "hvn_top_n": hvn, "rr": rr, "buffer_pct": buf}
                        best_ev = ev

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
                if DIV_INVERT_SIGNALS:
                    # simulate_pivot_stability's sign convention assumes the
                    # NATURAL trade direction for each pivot kind (SHORT on
                    # a high/bearish pivot, LONG on a low/bullish one) — see
                    # its own docstring. With DIV_INVERT_SIGNALS on, every
                    # live trade goes the OPPOSITE direction, so "earlier
                    # entry is better" flips to "earlier entry is worse" by
                    # the same magnitude — caught by direct user question
                    # about why this stat didn't seem to account for reverse
                    # mode being active. Flipping here (not in
                    # simulate_pivot_stability itself, which stays a neutral
                    # measurement) makes gain_sum/gain_count — and therefore
                    # the "vход раньше в среднем на X% лучше/хуже" figure —
                    # correct for whichever direction is ACTUALLY being
                    # traded right now.
                    gains = [-g for g in gains]
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
_telegram_send_queue = queue.Queue(maxsize=200)  # bounded — during a long enough outage, a message every scan cycle could otherwise accumulate without limit


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
    if category == "session_ny" and not TELEGRAM_ALERTS_SESSION_NY:
        return
    if category == "xau_lg" and not TELEGRAM_ALERTS_XAU_LG:
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

    try:
        _telegram_send_queue.put_nowait(_do_send)
    except queue.Full:
        log_error("telegram queue: full (200 pending), dropping this message rather than blocking the caller")


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


def scan_symbol(symbol, candles=None):
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
        # A shared pre-fetched candle set (from scan_loop's dedup cache) is
        # used as-is ONLY if it's long enough for THIS symbol's tuned
        # lookback — per-symbol auto-tune overrides can ask for more
        # history than the default the cache was built with. Falling back
        # to a fresh fetch here only affects the (rare) tuned-override
        # symbols, never silently truncates anyone's actual lookback.
        if candles is None or len(candles) < max_lookback + 5:
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

        if sig:
            staleness_sec = time.time() - sig["time"]
            if staleness_sec > SIGNAL_MAX_STALENESS_SEC:
                with state_lock:
                    STATE["filtered_by_staleness"] += 1
                sig = None  # candle closed too long ago — price has likely already moved past this signal's entry level, entering now would chase a stale/spent move rather than catch it near its start

        if sig and (has_open_signal(symbol) or has_open_signal_any_module(symbol, exclude="signals")):
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
                    # breakeven-stop bookkeeping (breakout only — see
                    # BREAKOUT_BREAKEVEN_TRIGGER_R): sl_order_id/tick are
                    # only ever populated for a REAL (non-dry-run) trade,
                    # since a dry-run/sim-only signal has no live order to
                    # amend. breakeven_moved guards against retrying every
                    # cycle once an attempt has been made, success or fail.
                    "sl_order_id": None,
                    "tick": None,
                    "breakeven_moved": False,
                    "breakeven_active": False,
                }
                with state_lock:
                    STATE["signals"].appendleft(record)
                autotrade_enabled = AUTOTRADE_ENABLED_BOUNCE if sig["reason"] == "bounce" else AUTOTRADE_ENABLED_BREAKOUT
                autotrade_leverage = AUTOTRADE_LEVERAGE_BOUNCE if sig["reason"] == "bounce" else AUTOTRADE_LEVERAGE_BREAKOUT
                if autotrade_enabled:
                    autotrade_result = execute_autotrade(sig["reason"], symbol, sig["direction"], sig["price"], sl, tp,
                                       autotrade_leverage, extra={"reason": sig["reason"]})
                    if autotrade_result and autotrade_result.get("status") in ("OPENED", "OPENED_TP_SL_FAILED"):
                        with state_lock:
                            record["sl_order_id"] = autotrade_result.get("sl_order_id")
                            record["tick"] = autotrade_result.get("tick")
                    sim_execute_trade(sig["reason"], symbol, sig["direction"], sig["price"], sl, tp,
                                       autotrade_leverage, record)
                arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
                send_telegram(
                    f"{arrow} {symbol} ({sig['reason']})\n"
                    f"entry: {sig['price']:.6g}\n"
                    f"SL: {sl:.6g}  TP: {tp:.6g}  (RR {rr:g})\n"
                    f"HVN zone: {sig['zone']['bottom']:.6g} - {sig['zone']['top']:.6g}",
                    category="vp",
                )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        with state_lock:
            STATE["excluded_fetch_error"] += 1
        log_error(f"{symbol}: network error after {GET_CANDLES_RETRIES} retries — {e}")
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
    all_candles = fetch_candles_concurrent([(s["symbol"], INTERVAL, 300) for s in active])
    for sig, candles in zip(active, all_candles):
        try:
            if candles is None:
                continue
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

                # --- Breakeven stop-move (breakout only, real trades only) ---
                # Runs after MFE is updated for this candle so it can act on
                # fav_r reaching the trigger threshold on this SAME candle,
                # and before TP/SL resolution below so a later check in this
                # same candle already sees the moved stop.
                if (sig["status"] == "OPEN" and sig.get("reason") == "breakout"
                        and not sig.get("breakeven_moved") and sig.get("sl_order_id")
                        and fav_r >= BREAKOUT_BREAKEVEN_TRIGGER_R):
                    new_sl_id = move_stop_to_breakeven(sig["symbol"], direction, sig["sl_order_id"], entry, sig.get("tick"))
                    with state_lock:
                        sig["breakeven_moved"] = True  # only ever attempt once per signal, whether it succeeds or fails — a failure logs via move_stop_to_breakeven itself, retrying every cycle would just spam the API against the same likely-persistent error
                        if new_sl_id:
                            sig["sl_order_id"] = new_sl_id
                            buf = BREAKOUT_BREAKEVEN_BUFFER_PCT
                            sig["sl"] = entry * (1 + buf) if direction == "LONG" else entry * (1 - buf)
                            sig["breakeven_active"] = True  # distinct from breakeven_moved: this one only True on actual success, used below to label the eventual close as BREAKEVEN rather than LOSS

                # --- TP/SL resolution (only while still open) ---
                if sig["status"] == "OPEN":
                    if direction == "LONG":
                        if c["low"] <= sig["sl"]:
                            result = "BREAKEVEN" if sig.get("breakeven_active") else "LOSS"
                            close_signal(sig, result, sig["sl"], exit_candle=c)
                        elif c["high"] >= sig["tp"]:
                            close_signal(sig, "WIN", sig["tp"], exit_candle=c)
                    else:
                        if c["high"] >= sig["sl"]:
                            result = "BREAKEVEN" if sig.get("breakeven_active") else "LOSS"
                            close_signal(sig, result, sig["sl"], exit_candle=c)
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
                STATE["excluded_fetch_error"] = 0
                STATE["filtered_by_trend"] = 0
                STATE["filtered_by_volume"] = 0
                STATE["filtered_by_oi"] = 0
                STATE["filtered_by_staleness"] = 0

            # Dedup candle fetches across Divergence and EMA: by default
            # both run on DIV_INTERVAL/EMA_INTERVAL = "1h", so without this
            # every symbol was fetched twice for the identical timeframe.
            # Volume isn't included here — its interval (15m default)
            # differs from Divergence/EMA's, AND its per-symbol lookback
            # can vary via SYMBOL_OVERRIDES (auto-tune), so a shared fixed-
            # limit cache wouldn't reliably cover it; scan_symbol() still
            # fetches its own candles, same as before.
            # Keyed by interval -> the largest limit any enabled module
            # needs at that interval, so one fetch covers every consumer
            # of that (symbol, interval) pair regardless of their
            # individual limit — more candles than a given consumer needs
            # is harmless, fewer would be (which is why scan_symbol()
            # above still falls back to its own fetch on a length miss).
            shared_interval_limits = {}
            if DIVERGENCE_ENABLED:
                shared_interval_limits[DIV_INTERVAL] = max(shared_interval_limits.get(DIV_INTERVAL, 0), DIV_FETCH_LIMIT)
            if EMA_ENABLED:
                for interval in EMA_INTERVALS:
                    shared_interval_limits[interval] = max(shared_interval_limits.get(interval, 0), EMA_FETCH_LIMIT)

            candle_cache = {}
            if shared_interval_limits:
                cache_specs = [(s, interval, limit) for s in universe for interval, limit in shared_interval_limits.items()]
                fetched = fetch_candles_concurrent(cache_specs)
                for (s, interval, _limit), candles in zip(cache_specs, fetched):
                    candle_cache[(s, interval)] = candles

            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futs = []
                if VOLUME_PROFILE_ENABLED:
                    futs += [ex.submit(scan_symbol, s) for s in universe]
                if DIVERGENCE_ENABLED:
                    futs += [ex.submit(scan_symbol_divergence, s, candle_cache.get((s, DIV_INTERVAL))) for s in universe]
                if EMA_ENABLED:
                    futs += [ex.submit(scan_symbol_ema, s, interval, candle_cache.get((s, interval))) for s in universe for interval in EMA_INTERVALS]
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
            sweep_sim_trades()
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


def session_ny_loop():
    """New York counterpart of session_loop() — same daily batch-backtest
    cadence, own STATE/constants throughout."""
    while True:
        try:
            if not SESSION_NY_ENABLED:
                time.sleep(60)
                continue
            t0 = time.time()
            with state_lock:
                STATE["session_ny_last_backtest_started"] = t0
                STATE["session_ny_symbols_done"] = 0

            universe = build_session_ny_universe()
            with state_lock:
                STATE["session_ny_universe"] = universe
                STATE["session_ny_backtest_results"] = {}
                STATE["session_ny_backtest_summary"] = {}

            def process_one(symbol):
                try:
                    results = backtest_session_ny_symbol(symbol)
                    summary = summarize_session_backtest(results)
                    with state_lock:
                        STATE["session_ny_backtest_results"][symbol] = results
                        STATE["session_ny_backtest_summary"][symbol] = summary
                        STATE["session_ny_symbols_done"] += 1
                except Exception as e:
                    log_error(f"session_ny process_one {symbol}: {e}")

            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futs = [ex.submit(process_one, s) for s in universe]
                for _ in as_completed(futs):
                    pass

            t1 = time.time()
            with state_lock:
                STATE["session_ny_last_backtest_finished"] = t1
                STATE["session_ny_last_backtest_duration"] = round(t1 - t0, 1)
        except Exception as e:
            log_error(f"session_ny_loop: {e}")
        time.sleep(max(60, SESSION_NY_REFRESH_SEC))


def session_ny_live_loop():
    """New York counterpart of session_live_loop() — same sleep-until-
    next-open, scan-during-window pattern, own STATE/constants."""
    while True:
        try:
            if not SESSION_NY_ENABLED:
                time.sleep(60)
                continue
            now = time.time()
            next_open = session_ny_open_utc_ts(now)
            if next_open <= now:
                next_open = session_ny_open_utc_ts(now + 86400)
            with state_lock:
                STATE["session_ny_next_open_ts"] = next_open

            while True:
                remaining = next_open - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 1800))

            with state_lock:
                summaries = dict(STATE["session_ny_backtest_summary"])
                universe = list(STATE["session_ny_universe"]) or list(summaries.keys())
            candidates = [s for s in universe
                          if summaries.get(s, {}).get("n", 0) >= SESSION_NY_MIN_SAMPLE
                          and (summaries.get(s, {}).get("win_rate") or 0) >= 50]
            window_end = next_open + SESSION_NY_MANIPULATION_WINDOW_MIN * 60
            while time.time() < window_end:
                with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                    futs = [ex.submit(scan_symbol_session_ny_live, s, next_open) for s in candidates]
                    for _ in as_completed(futs):
                        pass
                time.sleep(60)
        except Exception as e:
            log_error(f"session_ny_live_loop: {e}")
            time.sleep(60)


RECONCILE_INTERVAL_SEC = int(os.environ.get("VP_RECONCILE_INTERVAL_SEC", 120))  # 2 min, per direct user request — reconcile_positions_and_orders() was previously only called opportunistically (right before a new trade opens), so orphaned orders sat uncleaned for as long as the market stayed quiet with nothing new to piggyback the cleanup on; a live example showed 16 open orders against only 2 open positions after such a lull


def reconcile_loop():
    """Runs reconcile_positions_and_orders() on its own fixed timer,
    independent of whether any new trade happens to be opening —
    complements (doesn't replace) the opportunistic call still made
    inside execute_autotrade() right before a new position opens, so
    cleanup isn't left waiting on new trades during a quiet market."""
    while True:
        try:
            if not AUTOTRADE_DRY_RUN:
                reconcile_positions_and_orders()
        except Exception as e:
            log_error(f"reconcile_loop: {e}")
        time.sleep(max(30, RECONCILE_INTERVAL_SEC))


# ----------------------------------------------------------------------------
# Risk auto-tune (v0.93.0) — periodically nudges risk-related constants based
# on live win/loss data, automating what had been the user manually
# screenshotting stats each session and asking for the same handful of
# recurring adjustments (RR-vs-breakeven, SL-overshoot, reverse-direction
# EV). NOT the same system as auto_tune_cycle()/AUTO_TUNE_ENABLED above,
# which searches Volume Profile detection parameters per symbol — this one
# tunes EMA_MIN_RR, DIV_MIN_RR, SCALP_MIN_RR (a floor on target/stop ratio),
# EMA_SL_ATR_MULT, DIV_SL_ATR_MULT, SCALP_SL_BUFFER_MULT (stop width), and
# DIV_INVERT_SIGNALS/EMA_INVERT_SIGNALS/SESSION_INVERT_SIGNALS (direction).
# Per direct user request for FULL automation including reverse — the
# safeguards below (min sample sizes, bounded step sizes, cooldowns) aren't
# a hedge against that choice, just how "automatic" avoids being self-
# destructive on noisy data: a fixed formula chasing every small sample
# would thrash a parameter back and forth on noise alone.
# Known gap: Session has no MFE/MAE tracking on its signals at all (never
# added), so SESSION_SL_MULT can't be auto-tuned the same overshoot-based
# way as the other three SL-width knobs — only its reverse flag is tunable
# here, computed directly from entry/sl/exit_price instead.
# ----------------------------------------------------------------------------
RISK_AUTOTUNE_ENABLED = os.environ.get("VP_RISK_AUTOTUNE_ENABLED", "1") == "1"
RISK_AUTOTUNE_INTERVAL_SEC = int(os.environ.get("VP_RISK_AUTOTUNE_INTERVAL_SEC", 3600))  # hourly
RISK_AUTOTUNE_MIN_SAMPLE = int(os.environ.get("VP_RISK_AUTOTUNE_MIN_SAMPLE", 20))  # closed trades needed before nudging an RR/SL-width knob
RISK_AUTOTUNE_MIN_SAMPLE_REVERSE = int(os.environ.get("VP_RISK_AUTOTUNE_MIN_SAMPLE_REVERSE", 30))  # higher bar for flipping direction — wrong evidence there reverses every future trade, not just widens/narrows one number
RISK_AUTOTUNE_COOLDOWN_SEC = int(os.environ.get("VP_RISK_AUTOTUNE_COOLDOWN_SEC", 6 * 3600))  # 6h between changes to the SAME knob
RISK_AUTOTUNE_REVERSE_COOLDOWN_SEC = int(os.environ.get("VP_RISK_AUTOTUNE_REVERSE_COOLDOWN_SEC", 24 * 3600))  # 24h between flips of the SAME direction flag — the main defense against flip-flopping back and forth on noise
RISK_AUTOTUNE_RR_STEP = float(os.environ.get("VP_RISK_AUTOTUNE_RR_STEP", 0.1))  # max change per pass for any *_MIN_RR filter
RISK_AUTOTUNE_MULT_STEP = float(os.environ.get("VP_RISK_AUTOTUNE_MULT_STEP", 0.05))  # max change per pass for any *_SL_ATR_MULT / SCALP_SL_BUFFER_MULT
RISK_AUTOTUNE_RR_BOUNDS = (0.0, 2.0)  # 2.0 would already be extremely strict for any of these filters
RISK_AUTOTUNE_MULT_BOUNDS = (0.5, 3.0)  # below 0.5 is an unrealistically tight stop, above 3.0 an unrealistically wide one
RISK_AUTOTUNE_RR_TOLERANCE = 0.02  # don't nudge an RR filter already within this of its target — avoids chasing noise
RISK_AUTOTUNE_MULT_TOLERANCE_R = 0.08  # don't nudge an SL-width multiplier if realized LOSS MAE is already within this many R of -1.0
RISK_AUTOTUNE_REVERSE_EV_THRESHOLD = -0.03  # only flip a direction flag if the CURRENT mode's EV is negative by at least this much — a small negative EV could just be noise
# v0.95.5 — TP-extend rule, per direct user request to have auto-tune also
# catch the "WIN MFE far exceeds current RR" pattern (found manually for
# Volume/breakout earlier: median WIN MFE 3.641R against a fixed RR=2
# target) rather than only ever tightening risk. Only applies to EMA_TP_PCT/
# DIV_TP_PCT — Volume and Scalp already run their own per-symbol grid
# search over multiple target sizes (PARAM_GRID_RR / SCALP_TARGET_PCTS),
# so a second, separate global nudge would just fight that existing
# search; Session's non-inverted TP is the opposite range edge each time,
# not a single tunable constant, so there's nothing fixed to nudge there.
RISK_AUTOTUNE_TP_TOLERANCE_RATIO = 0.15  # ignore if WIN MFE is within 15% of the current RR — avoid chasing noise
RISK_AUTOTUNE_TP_STEP_RATIO = 0.1  # max 10% change to TP_PCT per pass — same bounded-step philosophy as the RR/SL-mult nudges
RISK_AUTOTUNE_TP_PCT_BOUNDS = (0.003, 0.05)  # 0.3%-5% — sane range; below is barely worth the fees, above is an unrealistic single fixed target


def _risk_autotune_log(module, param, old_value, new_value, reason, sample_n):
    entry = {"ts": time.time(), "module": module, "param": param,
             "old": old_value, "new": new_value, "reason": reason, "n": sample_n}
    with state_lock:
        STATE["risk_autotune_log"].appendleft(entry)
    # v0.95.2: used to ALSO call log_error() here for visibility in the
    # "Последние ошибки" panel — removed after a live screenshot showed
    # this made routine automated adjustments (not errors at all) sit
    # under a red "ошибки" header, confusing enough that the user sent
    # the screenshot specifically asking what had gone wrong. Redundant
    # anyway: STATE["risk_autotune_log"] already has its own dedicated
    # collapsible "Авто-тюнинг риска" display in the header (built at
    # the same time this dual-logging was added) — the entry above is
    # the only write this function needs.


def _risk_autotune_cooldown_ok(param_key, cooldown_sec):
    with state_lock:
        last = STATE["risk_autotune_last_change"].get(param_key)
    return last is None or (time.time() - last) >= cooldown_sec


def _risk_autotune_mark(param_key):
    with state_lock:
        STATE["risk_autotune_last_change"][param_key] = time.time()


def _risk_autotune_min_rr(module, param_key, current_value, median_rr, winrate_pct, sample_n, setter, avg_loss_mae_r=None):
    """Nudges a *_MIN_RR filter toward (a small margin under) the RR that
    would just break even at the module's own live winrate — same
    reasoning applied manually for EMA_MIN_RR (0.3->0.7) and SCALP_MIN_RR
    (0.5). breakeven_rr = (1-winrate)/winrate * overshoot, where overshoot
    is how many R a LOSS actually costs on average (abs(avg_loss_mae_r)),
    not an assumed exactly-1R. target sits 5% under that, matching the
    margin picked for EMA_MIN_RR=0.7 at the time.
    v0.95.3: the overshoot factor was missing entirely until a live
    example caught it — scalp_min_rr had been loosened to 0.368 using
    the nominal (assume-1R-losses) formula, but real LOSS MAE averaged
    -1.171R (the exact same overshoot _risk_autotune_sl_mult() was
    separately, correctly reacting to for scalp_sl_buffer_mult at the
    same time) — so a trade at RR 0.415 passed a filter that, accounting
    for the SAME overshoot data already available, should have sat
    around ~0.42 and rejected it. avg_loss_mae_r is optional and
    defaults to no adjustment (overshoot=1.0) so callers that don't have
    this stat handy still work, just without the correction."""
    if not RISK_AUTOTUNE_ENABLED or sample_n < RISK_AUTOTUNE_MIN_SAMPLE:
        return
    if median_rr is None or winrate_pct is None:
        return
    if not _risk_autotune_cooldown_ok(param_key, RISK_AUTOTUNE_COOLDOWN_SEC):
        return
    winrate = winrate_pct / 100
    if winrate <= 0 or winrate >= 1:
        return
    overshoot = abs(avg_loss_mae_r) if avg_loss_mae_r else 1.0
    breakeven_rr = (1 - winrate) / winrate * overshoot
    target = breakeven_rr * 0.95
    diff = target - current_value
    if abs(diff) < RISK_AUTOTUNE_RR_TOLERANCE:
        return
    step = max(-RISK_AUTOTUNE_RR_STEP, min(RISK_AUTOTUNE_RR_STEP, diff))
    lo, hi = RISK_AUTOTUNE_RR_BOUNDS
    new_value = round(min(hi, max(lo, current_value + step)), 3)
    if new_value == current_value:
        return
    setter(new_value)
    _risk_autotune_mark(param_key)
    _risk_autotune_log(module, param_key, current_value, new_value,
                        f"median_rr={median_rr:.3f} winrate={winrate_pct:.1f}% breakeven={breakeven_rr:.3f}", sample_n)


def _risk_autotune_sl_mult(module, param_key, current_value, loss_mae_avg_r, sample_n, setter):
    """Nudges an SL-width multiplier toward matching real adverse
    excursion: if realized LOSS MAE (in R, where R is that trade's own
    SL distance) averages beyond -1.0, the stop is too tight relative to
    where losses actually go — widen it. If comfortably inside -1.0, the
    stop has slack it doesn't need — tighten it, since a needlessly wide
    stop only worsens RR for no real safety benefit. Same logic applied
    manually for SCALP_SL_BUFFER_MULT (0.05->0.25)."""
    if not RISK_AUTOTUNE_ENABLED or sample_n < RISK_AUTOTUNE_MIN_SAMPLE:
        return
    if loss_mae_avg_r is None:
        return
    if not _risk_autotune_cooldown_ok(param_key, RISK_AUTOTUNE_COOLDOWN_SEC):
        return
    overshoot = abs(loss_mae_avg_r) - 1.0
    if abs(overshoot) < RISK_AUTOTUNE_MULT_TOLERANCE_R:
        return
    step = RISK_AUTOTUNE_MULT_STEP if overshoot > 0 else -RISK_AUTOTUNE_MULT_STEP
    lo, hi = RISK_AUTOTUNE_MULT_BOUNDS
    new_value = round(min(hi, max(lo, current_value + step)), 3)
    if new_value == current_value:
        return
    setter(new_value)
    _risk_autotune_mark(param_key)
    _risk_autotune_log(module, param_key, current_value, new_value,
                        f"loss_mae_avg_r={loss_mae_avg_r:+.3f} overshoot={overshoot:+.3f}", sample_n)


def _risk_autotune_reverse(module, param_key, current_flag, winrate_pct, rr, sample_n, setter, avg_loss_mae_r=None):
    """Flips an *_INVERT_SIGNALS flag if the CURRENTLY active direction's
    own EV (winrate*rr - (1-winrate)*overshoot) has been solidly negative
    over a large-enough sample. Weaker evidence than the two nudges
    above — live data only ever shows the outcome of whichever direction
    was actually traded, never a parallel "what if the opposite" — so
    this gets a higher sample bar (RISK_AUTOTUNE_MIN_SAMPLE_REVERSE) and
    a much longer cooldown (RISK_AUTOTUNE_REVERSE_COOLDOWN_SEC): a wrong
    flip doesn't just cost one trade, it reverses the direction of every
    signal until the next flip.
    v0.95.4: gained the same avg_loss_mae_r overshoot correction as
    _risk_autotune_min_rr() — a live example (Divergence) showed EV
    computed assuming -1R losses coming out -0.195, while real LOSS MAE
    averaged -4.382R (median -1.84R): the honest EV was -1.8R by the
    average or -0.6R by the (less outlier-sensitive) median — either
    way much more solidly negative than the nominal number suggested,
    for the exact same reason the min_rr formula was wrong: losses
    don't actually cost exactly -1R, and pretending otherwise
    understates how bad (or overstates how good) a direction's real EV
    is."""
    if not RISK_AUTOTUNE_ENABLED or sample_n < RISK_AUTOTUNE_MIN_SAMPLE_REVERSE:
        return
    if winrate_pct is None or rr is None or rr <= 0:
        return
    if not _risk_autotune_cooldown_ok(param_key, RISK_AUTOTUNE_REVERSE_COOLDOWN_SEC):
        return
    winrate = winrate_pct / 100
    overshoot = abs(avg_loss_mae_r) if avg_loss_mae_r else 1.0
    ev = winrate * rr - (1 - winrate) * overshoot
    if ev >= RISK_AUTOTUNE_REVERSE_EV_THRESHOLD:
        return
    new_flag = not current_flag
    setter(new_flag)
    _risk_autotune_mark(param_key)
    _risk_autotune_log(module, param_key, current_flag, new_flag,
                        f"ev={ev:+.3f} winrate={winrate_pct:.1f}% rr={rr:.3f} overshoot={overshoot:.3f}", sample_n)


def _risk_autotune_tp_extend(module, param_key, current_tp_pct, win_mfe_r, current_rr, sample_n, setter):
    """Nudges a fixed TP_PCT (EMA_TP_PCT / DIV_TP_PCT) toward matching the
    R-multiple winning trades actually reach before closing (win_mfe_r —
    pass mfe_r_wins_at_close specifically, NOT the full-24h-window MFE,
    since that includes post-close movement that isn't tradeable under
    the current exit logic and the app's own UI already labels it "не
    для оценки конкретной сделки"). If wins consistently run well past
    the R-multiple the current TP sits at (current_rr — pass rr_all's
    median or avg), the target is cutting profit short: extend it. If
    wins rarely get anywhere near it, the target may be unrealistic:
    trim it. Mirrors _risk_autotune_sl_mult()'s two-directional nudge,
    just for the reward side instead of the risk side.
    Since SL is ATR-based (varies per trade) while TP_PCT is one fixed %
    for everyone, R and TP_PCT move proportionally — scaling TP_PCT by
    (win_mfe_r / current_rr) is the direct translation, bounded to a
    max step per pass same as every other nudge here."""
    if not RISK_AUTOTUNE_ENABLED or sample_n < RISK_AUTOTUNE_MIN_SAMPLE:
        return
    if win_mfe_r is None or current_rr is None or current_rr <= 0:
        return
    if not _risk_autotune_cooldown_ok(param_key, RISK_AUTOTUNE_COOLDOWN_SEC):
        return
    ratio = win_mfe_r / current_rr
    if abs(ratio - 1.0) < RISK_AUTOTUNE_TP_TOLERANCE_RATIO:
        return
    ratio = max(1 - RISK_AUTOTUNE_TP_STEP_RATIO, min(1 + RISK_AUTOTUNE_TP_STEP_RATIO, ratio))
    lo, hi = RISK_AUTOTUNE_TP_PCT_BOUNDS
    new_value = round(min(hi, max(lo, current_tp_pct * ratio)), 5)
    if new_value == current_tp_pct:
        return
    setter(new_value)
    _risk_autotune_mark(param_key)
    _risk_autotune_log(module, param_key, current_tp_pct, new_value,
                        f"win_mfe_r={win_mfe_r:.3f} current_rr={current_rr:.3f} ratio={ratio:.3f}", sample_n)


# --- setters: each applies the change AND persists it via save_settings(),
# same pattern the settings API endpoint itself already uses ---

def _set_ema_min_rr(v):
    global EMA_MIN_RR
    EMA_MIN_RR = v
    save_settings()


def _set_ema_sl_atr_mult(v):
    global EMA_SL_ATR_MULT
    EMA_SL_ATR_MULT = v
    save_settings()


def _set_ema_tp_pct(v):
    global EMA_TP_PCT
    EMA_TP_PCT = v
    save_settings()


def _set_ema_invert(v):
    global EMA_INVERT_SIGNALS
    EMA_INVERT_SIGNALS = v
    save_settings()


def _set_div_min_rr(v):
    global DIV_MIN_RR
    DIV_MIN_RR = v
    save_settings()


def _set_div_sl_atr_mult(v):
    global DIV_SL_ATR_MULT
    DIV_SL_ATR_MULT = v
    save_settings()


def _set_div_tp_pct(v):
    global DIV_TP_PCT
    DIV_TP_PCT = v
    save_settings()


def _set_div_invert(v):
    global DIV_INVERT_SIGNALS
    DIV_INVERT_SIGNALS = v
    save_settings()


def _set_scalp_min_rr(v):
    global SCALP_MIN_RR
    SCALP_MIN_RR = v
    save_settings()


def _set_scalp_sl_buffer_mult(v):
    global SCALP_SL_BUFFER_MULT
    SCALP_SL_BUFFER_MULT = v
    save_settings()


def _set_session_invert(v):
    global SESSION_INVERT_SIGNALS
    SESSION_INVERT_SIGNALS = v
    save_settings()


def _scalp_closed_rr_stats():
    """Median target_pct/sl_pct ratio across closed scalp trades — scalp
    doesn't carry a stats-function-level rr_all the way EMA/Divergence
    do, so this reads it directly off STATE instead."""
    with state_lock:
        signals = list(STATE["scalp_signals"])
    closed = [s for s in signals if s.get("status") == "CLOSED" and s.get("result") in ("WIN", "LOSS") and s.get("sl_pct")]
    rrs = sorted(s["target_pct"] / s["sl_pct"] for s in closed if s.get("target_pct") and s.get("sl_pct"))
    if not rrs:
        return None, 0
    n = len(rrs)
    return rrs[n // 2], n


def _scalp_loss_mae_avg_r():
    with state_lock:
        signals = list(STATE["scalp_signals"])
    vals = [s["mae_r_at_close"] for s in signals
            if s.get("status") == "CLOSED" and s.get("result") == "LOSS" and s.get("mae_r_at_close") is not None]
    if not vals:
        return None, 0
    return sum(vals) / len(vals), len(vals)


def _session_reverse_stats():
    """Session has no MFE/MAE tracking on its signals (never added — a
    real gap, not silently worked around), so this computes realized R
    directly from entry/sl/exit_price on CLOSED trades instead. Only
    meaningful while SESSION_INVERT_SIGNALS is on: only the inverted
    sizing is risk/RR-based (see detect_session_manipulation()) — the
    non-inverted TP sits at the opposite range edge, an arbitrary
    distance unrelated to risk, so there's no consistent "R" to compute
    for that side. Returns (winrate_pct, rr, n); rr is fixed at
    SESSION_SL_MULT-derived RR=2 by construction when inverted."""
    with state_lock:
        signals = list(STATE["session_signals"])
    closed = [s for s in signals if s.get("status") == "CLOSED" and s.get("result") in ("WIN", "LOSS")]
    n = len(closed)
    if not n:
        return None, None, 0
    wins = sum(1 for s in closed if s["result"] == "WIN")
    winrate_pct = round(wins / n * 100, 1)
    return winrate_pct, 2.0, n  # RR=2 fixed by SESSION_INVERT_SIGNALS's own construction (v0.80.0)


def risk_autotune_pass():
    """One tuning pass across all four modules. Each module's checks are
    wrapped separately so one module's bad data doesn't block the rest."""
    try:
        s = compute_ema_stats()
        rr_all = s.get("rr_all")
        winrate = s.get("winrate")
        closed_n = s.get("closed_total", 0) or 0
        loss_mae = s.get("mae_r_losses_at_close")
        if rr_all:
            _risk_autotune_min_rr("ema", "ema_min_rr", EMA_MIN_RR, rr_all["median"], winrate, closed_n, _set_ema_min_rr,
                                   avg_loss_mae_r=loss_mae["avg"] if loss_mae else None)
        if loss_mae:
            _risk_autotune_sl_mult("ema", "ema_sl_atr_mult", EMA_SL_ATR_MULT, loss_mae["avg"], s.get("losses", 0) or 0, _set_ema_sl_atr_mult)
        if rr_all:
            _risk_autotune_reverse("ema", "ema_invert_signals", EMA_INVERT_SIGNALS, winrate, rr_all["avg"], closed_n, _set_ema_invert,
                                    avg_loss_mae_r=loss_mae["avg"] if loss_mae else None)
        win_mfe = s.get("mfe_r_wins_at_close")
        if win_mfe and rr_all:
            _risk_autotune_tp_extend("ema", "ema_tp_pct", EMA_TP_PCT, win_mfe["median"], rr_all["median"], closed_n, _set_ema_tp_pct)
    except Exception as e:
        log_error(f"risk_autotune ema: {e}")

    try:
        s = compute_divergence_stats()
        rr_all = s.get("rr_all")
        winrate = s.get("winrate")
        closed_n = (s.get("wins", 0) or 0) + (s.get("losses", 0) or 0)
        loss_mae = s.get("mae_r_losses_at_close")
        if rr_all:
            _risk_autotune_min_rr("divergence", "div_min_rr", DIV_MIN_RR, rr_all["median"], winrate, closed_n, _set_div_min_rr,
                                   avg_loss_mae_r=loss_mae["avg"] if loss_mae else None)
        if loss_mae:
            _risk_autotune_sl_mult("divergence", "div_sl_atr_mult", DIV_SL_ATR_MULT, loss_mae["avg"], s.get("losses", 0) or 0, _set_div_sl_atr_mult)
        if rr_all:
            _risk_autotune_reverse("divergence", "div_invert_signals", DIV_INVERT_SIGNALS, winrate, rr_all["avg"], closed_n, _set_div_invert,
                                    avg_loss_mae_r=loss_mae["avg"] if loss_mae else None)
        win_mfe = s.get("mfe_r_wins_at_close")
        if win_mfe and rr_all:
            _risk_autotune_tp_extend("divergence", "div_tp_pct", DIV_TP_PCT, win_mfe["median"], rr_all["median"], closed_n, _set_div_tp_pct)
    except Exception as e:
        log_error(f"risk_autotune divergence: {e}")

    try:
        median_rr, rr_n = _scalp_closed_rr_stats()
        scalp_stats = compute_scalp_signal_stats()
        winrate = scalp_stats.get("win_rate")
        closed_n = (scalp_stats.get("wins", 0) or 0) + (scalp_stats.get("losses", 0) or 0)
        loss_mae_avg, loss_n = _scalp_loss_mae_avg_r()
        if median_rr is not None:
            _risk_autotune_min_rr("scalp", "scalp_min_rr", SCALP_MIN_RR, median_rr, winrate, rr_n, _set_scalp_min_rr,
                                   avg_loss_mae_r=loss_mae_avg)
        if loss_mae_avg is not None:
            _risk_autotune_sl_mult("scalp", "scalp_sl_buffer_mult", SCALP_SL_BUFFER_MULT, loss_mae_avg, loss_n, _set_scalp_sl_buffer_mult)
        # No reverse flag exists for scalp (it picks direction from
        # recommend_scalp_config's own EV ranking, not a fixed indicator
        # to invert) — nothing to tune here.
    except Exception as e:
        log_error(f"risk_autotune scalp: {e}")

    try:
        if SESSION_INVERT_SIGNALS:  # see _session_reverse_stats' docstring — only meaningful in inverted mode
            winrate, rr, n = _session_reverse_stats()
            if winrate is not None:
                _risk_autotune_reverse("session", "session_invert_signals", SESSION_INVERT_SIGNALS, winrate, rr, n, _set_session_invert)
        # session_sl_mult intentionally not auto-tuned — no MFE/MAE data
        # exists to base an overshoot check on (see module docstring above).
    except Exception as e:
        log_error(f"risk_autotune session: {e}")


def risk_autotune_loop():
    while True:
        try:
            if RISK_AUTOTUNE_ENABLED:
                risk_autotune_pass()
        except Exception as e:
            log_error(f"risk_autotune_loop: {e}")
        time.sleep(max(300, RISK_AUTOTUNE_INTERVAL_SEC))


# ============================================================================
# EXPERIMENTAL: XAU Liquidity Grab (v0.95.0) — functions
# ----------------------------------------------------------------------------
# Constants (XAU_LG_ENABLED, XAU_LG_SYMBOLS, etc.) are defined much earlier
# in the file, right after the SESSION_NY_* constants — moved there in
# v0.95.1 after a live NameError: the STATE dict (which references
# XAU_LG_SIGNAL_HISTORY at construction time) is built long before this
# point in the file's top-to-bottom execution order, so the constant has to
# exist before STATE does, not just before these functions do. py_compile
# only checks syntax, not execution order, so this class of bug doesn't
# show up until the script actually runs — caught here from a live Termux
# traceback, not from compiling locally beforehand.
# ============================================================================


def xau_lg_detect_signals(candles, ema_period=XAU_LG_EMA_PERIOD, pivot_left=XAU_LG_PIVOT_LEFT, pivot_right=XAU_LG_PIVOT_RIGHT):
    """Single walk-forward pass over `candles` (must be XAU_LG_TF, oldest
    first) — maintains the nearest active (unbroken) pivot support/
    resistance level as it goes, exactly like a live indicator would, and
    returns every confirmed liquidity-grab signal found. No lookahead: a
    pivot at bar j only becomes "active" once bar j+pivot_right has been
    seen (the same confirmation delay real pivot indicators have — you
    can't know bar j was a local extreme until pivot_right bars later
    confirm nothing higher/lower followed), and each signal only uses the
    close/EMA of its own trigger bar.
    A level is "consumed" (retired) either by triggering a grab signal off
    it, or by price closing cleanly through it without wicking back — in
    both cases the next-confirmed pivot becomes the new active level.
    Used identically for backtesting (feed the whole history) and live
    scanning (feed recent history, check whether the LAST bar produced a
    new signal) — same principle as detect_session_manipulation() serving
    both callers."""
    n = len(candles)
    if n < ema_period + pivot_left + pivot_right + 2:
        return []
    closes = [c["close"] for c in candles]
    ema = compute_ema(closes, ema_period)
    signals = []
    active_support = None
    active_resistance = None
    for i in range(n):
        confirm_idx = i - pivot_right
        if confirm_idx - pivot_left >= 0:
            cc = candles[confirm_idx]
            is_high = (all(cc["high"] >= candles[confirm_idx - j]["high"] for j in range(1, pivot_left + 1)) and
                       all(cc["high"] >= candles[confirm_idx + j]["high"] for j in range(1, pivot_right + 1)))
            if is_high:
                active_resistance = cc["high"]
            is_low = (all(cc["low"] <= candles[confirm_idx - j]["low"] for j in range(1, pivot_left + 1)) and
                      all(cc["low"] <= candles[confirm_idx + j]["low"] for j in range(1, pivot_right + 1)))
            if is_low:
                active_support = cc["low"]
        c = candles[i]
        if active_support is not None:
            if c["low"] < active_support <= c["close"]:
                if c["close"] > ema[i]:
                    entry, sl = c["high"], c["low"]
                    risk = entry - sl
                    if risk > 0:
                        tp = entry + risk * XAU_LG_RR
                        signals.append({"index": i, "time": c["time"], "direction": "LONG",
                                         "entry": entry, "sl": sl, "tp": tp, "level": active_support})
                active_support = None
            elif c["close"] < active_support:
                active_support = None
        if active_resistance is not None:
            if c["high"] > active_resistance >= c["close"]:
                if c["close"] < ema[i]:
                    entry, sl = c["low"], c["high"]
                    risk = sl - entry
                    if risk > 0:
                        tp = entry - risk * XAU_LG_RR
                        signals.append({"index": i, "time": c["time"], "direction": "SHORT",
                                         "entry": entry, "sl": sl, "tp": tp, "level": active_resistance})
                active_resistance = None
            elif c["close"] > active_resistance:
                active_resistance = None
    return signals


def xau_lg_track_outcome(candles, sig, max_wait_bars=200):
    """Walks forward from sig['index']+1 looking for TP/SL touch — SL
    checked first on any bar covering both, same conservative convention
    as track_session_outcome()."""
    n = len(candles)
    for k in range(sig["index"] + 1, min(n, sig["index"] + 1 + max_wait_bars)):
        c = candles[k]
        if sig["direction"] == "LONG":
            if c["low"] <= sig["sl"]:
                return "LOSS", c["time"]
            if c["high"] >= sig["tp"]:
                return "WIN", c["time"]
        else:
            if c["high"] >= sig["sl"]:
                return "LOSS", c["time"]
            if c["low"] <= sig["tp"]:
                return "WIN", c["time"]
    return "TIMEOUT", None


def xau_lg_backtest_symbol(symbol, days=XAU_LG_BACKTEST_DAYS):
    """Fetches XAU_LG_BACKTEST_DAYS of XAU_LG_TF history and runs the
    detector + outcome tracker over the WHOLE window in one pass — much
    cheaper than Session's per-day walk since this pattern isn't anchored
    to a specific time of day, just scanned continuously."""
    now = time.time()
    fetch_start = now - days * 86400
    candles = get_candles_range(symbol, XAU_LG_TF, fetch_start, now)
    if len(candles) < XAU_LG_EMA_PERIOD + 10:
        return []
    sigs = xau_lg_detect_signals(candles)
    results = []
    for sig in sigs:
        result, exit_time = xau_lg_track_outcome(candles, sig)
        results.append({
            "time": sig["time"], "direction": sig["direction"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
            "result": result, "exit_time": exit_time,
        })
    return results


def xau_lg_summarize_backtest(results):
    total = len(results)
    if not total:
        return {"n": 0, "win_rate": None, "wins": 0, "losses": 0, "timeouts": 0}
    wins = sum(1 for r in results if r["result"] == "WIN")
    losses = sum(1 for r in results if r["result"] == "LOSS")
    timeouts = sum(1 for r in results if r["result"] == "TIMEOUT")
    closed = wins + losses
    win_rate = round(wins / closed * 100, 1) if closed else None
    return {"n": total, "win_rate": win_rate, "wins": wins, "losses": losses, "timeouts": timeouts}


_xau_lg_signal_cooldowns = {}  # symbol -> last signaled bar time
_xau_lg_signal_cooldowns_lock = threading.Lock()


def xau_lg_scan_symbol_live(symbol):
    """Live counterpart to xau_lg_backtest_symbol() — fetches recent
    history, runs the SAME detector, and fires only if the LAST candle
    produced a brand-new signal not already seen for this symbol."""
    if not XAU_LG_ENABLED:
        return
    try:
        candles = get_candles(symbol, interval=XAU_LG_TF, limit=XAU_LG_EMA_PERIOD + 80)
        interval_sec = INTERVAL_SECONDS.get(XAU_LG_TF, 900)
        now = time.time()
        candles = [c for c in candles if c["time"] + interval_sec <= now]  # drop still-forming candle, same reasoning as scan_symbol_session_live
        if len(candles) < XAU_LG_EMA_PERIOD + 10:
            return
        sigs = xau_lg_detect_signals(candles)
        if not sigs:
            return
        sig = sigs[-1]
        if sig["index"] != len(candles) - 1:
            return  # most recent signal isn't off the latest closed candle — already stale/handled
        with _xau_lg_signal_cooldowns_lock:
            if _xau_lg_signal_cooldowns.get(symbol) == sig["time"]:
                return
            _xau_lg_signal_cooldowns[symbol] = sig["time"]
        if has_open_signal_any_module(symbol, exclude="xau_lg_signals"):
            return
        record = {
            "symbol": symbol, "direction": sig["direction"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
            "level": sig["level"], "time": sig["time"],
            "detected_at": time.time(), "status": "OPEN", "result": None,
            "exit_price": None, "exit_time": None, "app_version": APP_VERSION,
        }
        with state_lock:
            STATE["xau_lg_signals"].appendleft(record)
        if AUTOTRADE_ENABLED_XAU_LG:
            execute_autotrade("xau_lg", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"],
                               AUTOTRADE_LEVERAGE_XAU_LG)
            sim_execute_trade("xau_lg", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"],
                               AUTOTRADE_LEVERAGE_XAU_LG, record)
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        send_telegram(
            f"{arrow} {symbol} (XAU liquidity grab — ЭКСПЕРИМЕНТАЛЬНО)\n"
            f"entry: {sig['entry']:.6g}\n"
            f"SL: {sig['sl']:.6g}  TP: {sig['tp']:.6g}",
            category="xau_lg",
        )
    except Exception as e:
        log_error(f"xau_lg_live {symbol}: {e}")


def update_xau_lg_signal_outcomes():
    now = time.time()
    with state_lock:
        open_signals = [s for s in STATE["xau_lg_signals"] if s["status"] == "OPEN"]
    all_candles = fetch_candles_concurrent([(s["symbol"], XAU_LG_TF, 300) for s in open_signals])
    for sig, candles in zip(open_signals, all_candles):
        try:
            if candles is None:
                continue
            future = [c for c in candles if c["time"] >= sig["time"]]
            result = None
            exit_price = None
            exit_time = None
            for c in future:
                if sig["direction"] == "LONG":
                    if c["low"] <= sig["sl"]:
                        result, exit_price, exit_time = "LOSS", sig["sl"], c["time"]
                        break
                    if c["high"] >= sig["tp"]:
                        result, exit_price, exit_time = "WIN", sig["tp"], c["time"]
                        break
                else:
                    if c["high"] >= sig["sl"]:
                        result, exit_price, exit_time = "LOSS", sig["sl"], c["time"]
                        break
                    if c["low"] <= sig["tp"]:
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
            log_error(f"xau_lg_outcome {sig['symbol']}: {e}")


def compute_xau_lg_signal_stats():
    with state_lock:
        signals = list(STATE["xau_lg_signals"])
    closed = [s for s in signals if s["status"] == "CLOSED" and s["result"] in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = sum(1 for s in closed if s["result"] == "LOSS")
    timeouts = sum(1 for s in signals if s.get("result") == "TIMEOUT")
    open_n = sum(1 for s in signals if s["status"] == "OPEN")
    total_closed = len(closed)
    winrate = round(wins / total_closed * 100, 1) if total_closed else None
    return {"total": len(signals), "wins": wins, "losses": losses, "timeouts": timeouts,
            "open": open_n, "winrate": winrate}


def xau_lg_backtest_loop():
    while True:
        try:
            if not XAU_LG_ENABLED:
                time.sleep(60)
                continue
            t0 = time.time()
            results_by_symbol = {}
            summary_by_symbol = {}
            for symbol in XAU_LG_SYMBOLS:
                try:
                    results = xau_lg_backtest_symbol(symbol)
                    results_by_symbol[symbol] = results
                    summary_by_symbol[symbol] = xau_lg_summarize_backtest(results)
                except Exception as e:
                    log_error(f"xau_lg_backtest {symbol}: {e}")
            with state_lock:
                STATE["xau_lg_backtest_results"] = results_by_symbol
                STATE["xau_lg_backtest_summary"] = summary_by_symbol
                STATE["xau_lg_last_backtest_finished"] = time.time()
                STATE["xau_lg_last_backtest_duration"] = round(time.time() - t0, 1)
        except Exception as e:
            log_error(f"xau_lg_backtest_loop: {e}")
        time.sleep(max(300, XAU_LG_REFRESH_SEC))


def xau_lg_live_loop():
    while True:
        try:
            if not XAU_LG_ENABLED:
                time.sleep(60)
                continue
            with ThreadPoolExecutor(max_workers=min(WORKERS, len(XAU_LG_SYMBOLS) or 1)) as ex:
                futs = [ex.submit(xau_lg_scan_symbol_live, s) for s in XAU_LG_SYMBOLS]
                for _ in as_completed(futs):
                    pass
            update_xau_lg_signal_outcomes()
        except Exception as e:
            log_error(f"xau_lg_live_loop: {e}")
        time.sleep(max(60, XAU_LG_SCAN_INTERVAL_SEC))


# ============================================================================
# END EXPERIMENTAL: XAU Liquidity Grab
# ============================================================================


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
            "excluded_fetch_error": STATE["excluded_fetch_error"],
            "filtered_by_trend": STATE["filtered_by_trend"],
            "filtered_by_volume": STATE["filtered_by_volume"],
            "filtered_by_oi": STATE["filtered_by_oi"],
            "filtered_by_staleness": STATE["filtered_by_staleness"],
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
            # Distinct from "auto_tune" above (that one is Volume Profile
            # detection-parameter search per symbol) — this is the risk-
            # parameter tuner from v0.93.0 (EMA_MIN_RR, SL-width multipliers,
            # reverse flags). Log entries are newest-first, capped at 200.
            "risk_autotune": {
                "enabled": RISK_AUTOTUNE_ENABLED,
                "interval_hours": round(RISK_AUTOTUNE_INTERVAL_SEC / 3600, 2),
                "log": list(STATE["risk_autotune_log"])[:30],
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
            "filtered_by_min_rr": STATE["filtered_by_div_min_rr"],
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
                "sl_mode": DIV_SL_MODE, "sl_atr_mult": DIV_SL_ATR_MULT, "rr_fallback": DIV_RR, "min_rr": DIV_MIN_RR, "tp_pct": DIV_TP_PCT, "rsi_period": DIV_RSI_PERIOD,
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
                "sl_mode": EMA_SL_MODE, "sl_atr_mult": EMA_SL_ATR_MULT, "rr_fallback": EMA_RR, "tp_pct": EMA_TP_PCT,
                "min_rr": EMA_MIN_RR,
                "signal_timeout_hours": round(EMA_SIGNAL_TIMEOUT_SEC / 3600, 2),
                "adx_filter_enabled": EMA_ADX_FILTER_ENABLED, "adx_min": EMA_ADX_MIN, "adx_period": EMA_ADX_PERIOD,
                "min_gap_pct": EMA_MIN_GAP_PCT,
                "len7": EMA_LEN_7, "len14": EMA_LEN_14, "len28": EMA_LEN_28,
                "signal_type": EMA_SIGNAL_TYPE, "trend_filter": EMA_TREND_FILTER, "invert_signals": EMA_INVERT_SIGNALS,
                "cooldown": EMA_COOLDOWN_SEC,
            },
            "filtered_by_min_rr": STATE["filtered_by_min_rr"],
            "filtered_by_adx": STATE["filtered_by_adx"],
            "filtered_by_min_gap": STATE["filtered_by_min_gap"],
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
            "size_mode": SCALP_SIZE_MODE, "size_value": SCALP_SIZE_VALUE,
        },
        "top": ranked,
        "signals_stats": compute_scalp_signal_stats(),
        "tuning_stats": compute_scalp_tuning_stats(),
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
            "invert_signals": SESSION_INVERT_SIGNALS,
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


@app.route("/api/session_ny/status")
def api_session_ny_status():
    """New York counterpart of api_session_status() — identical shape,
    own STATE/constants throughout."""
    with state_lock:
        universe = list(STATE["session_ny_universe"])
        summaries = dict(STATE["session_ny_backtest_summary"])
        last_backtest_finished = STATE["session_ny_last_backtest_finished"]
        last_backtest_duration = STATE["session_ny_last_backtest_duration"]
        symbols_done = STATE["session_ny_symbols_done"]
        next_open_ts = STATE["session_ny_next_open_ts"]
    ranked = []
    zero_manipulation_count = 0
    not_yet_processed_count = 0
    for symbol in universe:
        s = summaries.get(symbol)
        if s is None:
            not_yet_processed_count += 1
            continue
        if not s.get("n"):
            zero_manipulation_count += 1
            continue
        row = dict(s)
        row["symbol"] = symbol
        row["meets_min_sample"] = s["n"] >= SESSION_NY_MIN_SAMPLE
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
        "enabled": SESSION_NY_ENABLED,
        "universe_size": len(universe),
        "symbols_done": symbols_done,
        "zero_manipulation_count": zero_manipulation_count,
        "not_yet_processed_count": not_yet_processed_count,
        "watch_symbols": watch_symbols,
        "last_backtest_finished": last_backtest_finished,
        "last_backtest_duration": last_backtest_duration,
        "next_open_ts": next_open_ts,
        "signals_stats": compute_session_ny_signal_stats(),
        "config": {
            "utc_offset_hours": SESSION_NY_UTC_OFFSET_HOURS, "open_hour_local": SESSION_NY_OPEN_HOUR_LOCAL,
            "open_minute_local": SESSION_NY_OPEN_MINUTE_LOCAL,
            "range_tf": SESSION_NY_RANGE_TF, "range_start_utc_hour": SESSION_NY_RANGE_START_UTC_HOUR,
            "manipulation_window_min": SESSION_NY_MANIPULATION_WINDOW_MIN,
            "min_sample": SESSION_NY_MIN_SAMPLE, "backtest_days": SESSION_NY_BACKTEST_DAYS,
            "invert_signals": SESSION_NY_INVERT_SIGNALS,
        },
        "top": ranked,
    })


@app.route("/api/session_ny/signals")
def api_session_ny_signals():
    with state_lock:
        return jsonify(list(STATE["session_ny_signals"]))


@app.route("/api/session_ny/symbol/<symbol>")
def api_session_ny_symbol(symbol):
    with state_lock:
        results = STATE["session_ny_backtest_results"].get(symbol)
        summary = STATE["session_ny_backtest_summary"].get(symbol)
    if results is None:
        return jsonify({"error": "no data for this symbol yet"}), 404
    return jsonify({"symbol": symbol, "summary": summary, "results": results})


@app.route("/api/session_ny/chart/<symbol>")
def api_session_ny_chart(symbol):
    """New York counterpart of api_session_chart() — same re-derive-from-
    fresh-candles approach, own detection/outcome functions."""
    try:
        session_open = float(request.args.get("session_open"))
        range_start_dt = datetime.datetime.fromtimestamp(session_open, tz=datetime.timezone.utc).replace(
            hour=SESSION_NY_RANGE_START_UTC_HOUR, minute=0, second=0, microsecond=0)
        fetch_start = range_start_dt.timestamp() - 2 * 3600
        fetch_end = session_open + SESSION_NY_MANIPULATION_WINDOW_MIN * 60 + 8 * 3600
        candles = get_candles_range(symbol, SESSION_NY_RANGE_TF, fetch_start, fetch_end)
        sig = detect_session_ny_manipulation(candles, session_open)
        result = None
        exit_time = None
        exit_price = None
        if sig:
            result, exit_time = track_session_ny_outcome(candles, sig)
            if result == "WIN":
                exit_price = sig["tp"]
            elif result == "LOSS":
                exit_price = sig["sl"]
        return jsonify({
            "symbol": symbol, "candles": candles, "session_open": session_open,
            "signal": sig, "result": result, "exit_time": exit_time, "exit_price": exit_price,
        })
    except Exception as e:
        log_error(f"api_session_ny_chart {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset/session_ny", methods=["POST"])
def api_reset_session_ny():
    try:
        with state_lock:
            STATE["session_ny_universe"] = []
            STATE["session_ny_backtest_results"] = {}
            STATE["session_ny_backtest_summary"] = {}
            STATE["session_ny_last_backtest_started"] = None
            STATE["session_ny_last_backtest_finished"] = None
            STATE["session_ny_last_backtest_duration"] = None
            STATE["session_ny_symbols_done"] = 0
            STATE["session_ny_signals"].clear()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_session_ny: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/xau_lg/status")
def api_xau_lg_status():
    """EXPERIMENTAL — see the XAU_LG module's own header comment."""
    with state_lock:
        summary = dict(STATE["xau_lg_backtest_summary"])
        last_backtest_finished = STATE["xau_lg_last_backtest_finished"]
        last_backtest_duration = STATE["xau_lg_last_backtest_duration"]
    ranked = [dict(s, symbol=sym) for sym, s in summary.items()]
    ranked.sort(key=lambda r: (r["win_rate"] or 0, r["n"]), reverse=True)
    return jsonify({
        "enabled": XAU_LG_ENABLED,
        "symbols": XAU_LG_SYMBOLS,
        "last_backtest_finished": last_backtest_finished,
        "last_backtest_duration": last_backtest_duration,
        "signals_stats": compute_xau_lg_signal_stats(),
        "config": {
            "tf": XAU_LG_TF, "ema_period": XAU_LG_EMA_PERIOD,
            "pivot_left": XAU_LG_PIVOT_LEFT, "pivot_right": XAU_LG_PIVOT_RIGHT,
            "rr": XAU_LG_RR, "backtest_days": XAU_LG_BACKTEST_DAYS,
        },
        "top": ranked,
    })


@app.route("/api/xau_lg/signals")
def api_xau_lg_signals():
    with state_lock:
        return jsonify(list(STATE["xau_lg_signals"]))


@app.route("/api/reset/xau_lg", methods=["POST"])
def api_reset_xau_lg():
    try:
        with state_lock:
            STATE["xau_lg_backtest_results"] = {}
            STATE["xau_lg_backtest_summary"] = {}
            STATE["xau_lg_last_backtest_finished"] = None
            STATE["xau_lg_last_backtest_duration"] = None
            STATE["xau_lg_signals"].clear()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_xau_lg: {e}")
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


@app.route("/api/credentials", methods=["GET"])
def api_get_credentials():
    return jsonify({"gate_api_configured": bool(GATE_API_KEY and GATE_API_SECRET)})


@app.route("/api/credentials", methods=["POST"])
def api_post_credentials():
    try:
        body = request.get_json(force=True, silent=True) or {}
        api_key = (body.get("api_key") or "").strip()
        api_secret = (body.get("api_secret") or "").strip()
        if not api_key or not api_secret:
            return jsonify({"ok": False, "error": "both api_key and api_secret are required"}), 400
        save_credentials(api_key, api_secret)
        return jsonify({"ok": True, "gate_api_configured": True})
    except Exception as e:
        log_error(f"api_post_credentials: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/credentials", methods=["DELETE"])
def api_delete_credentials():
    try:
        save_credentials("", "")
        if os.path.exists(CREDENTIALS_FILE):
            os.remove(CREDENTIALS_FILE)
        return jsonify({"ok": True, "gate_api_configured": False})
    except Exception as e:
        log_error(f"api_delete_credentials: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/autotrade/log")
def api_autotrade_log():
    with state_lock:
        return jsonify(list(STATE["autotrade_log"]))


@app.route("/api/autotrade/status")
def api_autotrade_status():
    with state_lock:
        log = list(STATE["autotrade_log"])
    opened = sum(1 for e in log if e["status"] in ("OPENED", "OPENED_TP_SL_FAILED"))
    dry_run_n = sum(1 for e in log if e["status"] == "DRY_RUN")
    skipped = sum(1 for e in log if e["status"] == "SKIPPED")
    errors = sum(1 for e in log if e["status"] == "ERROR")
    return jsonify({
        "dry_run": AUTOTRADE_DRY_RUN,
        "gate_api_configured": bool(GATE_API_KEY and GATE_API_SECRET),
        "total": len(log), "opened": opened, "dry_run_count": dry_run_n,
        "skipped": skipped, "errors": errors,
        "enabled": {
            "bounce": AUTOTRADE_ENABLED_BOUNCE, "breakout": AUTOTRADE_ENABLED_BREAKOUT,
            "divergence": AUTOTRADE_ENABLED_DIVERGENCE, "ema": AUTOTRADE_ENABLED_EMA,
            "scalp": AUTOTRADE_ENABLED_SCALP, "session": AUTOTRADE_ENABLED_SESSION,
            "session_ny": AUTOTRADE_ENABLED_SESSION_NY, "xau_lg": AUTOTRADE_ENABLED_XAU_LG,
        },
    })


@app.route("/api/simulator/status")
def api_simulator_status():
    with state_lock:
        trades = list(STATE["sim_trades"])
        balance = STATE["sim_balance"]
    settled = [t for t in trades if t["status"] == "SETTLED"]
    pending = [t for t in trades if t["status"] == "PENDING"]
    wins = sum(1 for t in settled if t["result"] == "WIN")
    losses = sum(1 for t in settled if t["result"] == "LOSS")
    timeouts = sum(1 for t in settled if t["result"] == "TIMEOUT")
    total_pnl = sum(t["pnl"] for t in settled) if settled else 0
    return jsonify({
        "balance": round(balance, 4), "start_balance": AUTOTRADE_SIM_START_BALANCE,
        "pnl_total": round(total_pnl, 4),
        "pnl_pct": round((balance - AUTOTRADE_SIM_START_BALANCE) / AUTOTRADE_SIM_START_BALANCE * 100, 2) if AUTOTRADE_SIM_START_BALANCE else None,
        "settled": len(settled), "pending": len(pending),
        "wins": wins, "losses": losses, "timeouts": timeouts,
        "win_rate": round(wins / (wins + losses) * 100, 1) if (wins + losses) else None,
        "size_mode": AUTOTRADE_SIZE_MODE, "size_value": AUTOTRADE_SIZE_VALUE,
        "fee_pct": AUTOTRADE_SIM_FEE_PCT,
    })


@app.route("/api/simulator/trades")
def api_simulator_trades():
    with state_lock:
        trades = list(STATE["sim_trades"])
    clean = [{k: v for k, v in t.items() if k != "_signal_ref"} for t in trades]
    return jsonify(clean)


@app.route("/api/simulator/reset", methods=["POST"])
def api_simulator_reset():
    try:
        with state_lock:
            STATE["sim_balance"] = AUTOTRADE_SIM_START_BALANCE
            STATE["sim_trades"].clear()
        return jsonify({"ok": True, "balance": AUTOTRADE_SIM_START_BALANCE})
    except Exception as e:
        log_error(f"api_simulator_reset: {e}")
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
            STATE["excluded_fetch_error"] = 0
            STATE["filtered_by_trend"] = 0
            STATE["filtered_by_volume"] = 0
            STATE["filtered_by_oi"] = 0
            STATE["filtered_by_staleness"] = 0
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
            STATE["excluded_fetch_error"] = 0
            STATE["filtered_by_trend"] = 0
            STATE["filtered_by_volume"] = 0
            STATE["filtered_by_oi"] = 0
            STATE["filtered_by_staleness"] = 0
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
  #resetVolumeBtn, #resetDivBtn, #resetEmaBtn, #resetScalpBtn, #resetSessionBtn, #resetSessionNyBtn, #resetXauLgBtn, #resetSimulatorBtn { background:#3a1e22; border:none; color:#ff9b9b; padding:6px 12px; border-radius:8px; font-size:12px; white-space:nowrap; }
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

  /* Mobile layout, v0.89.0 — per direct user request after a live
     screenshot showed the header button row wrapping across ~4 lines
     (eating most of the visible screen before any actual data) and the
     12-column tables (EMA's, worst case) rendering all columns crushed
     into unreadable widths on a narrow phone viewport. Deliberately
     CSS-only: no JS/markup changes needed, since it works for BOTH the
     three static <table> elements (signals/div/ema) AND the
     dynamically-generated ones (scalp/session panels build their own
     <table> via innerHTML) — the `table { display:block; overflow-x:
     auto }` rule applies to any table on the page, present now or
     injected later, without needing to touch each render function. */
  @media (max-width: 640px) {
    header { padding:8px 10px; position:static; }
    header h1 { font-size:15px; margin-bottom:6px; }
    #headerTop { flex-direction:column; align-items:stretch; gap:2px; }
    #headerTop > div:last-child {
      display:flex; flex-wrap:nowrap; overflow-x:auto; gap:6px;
      -webkit-overflow-scrolling:touch; padding-bottom:4px;
    }
    #headerTop > div:last-child button { flex-shrink:0; font-size:11px; padding:6px 10px; }
    #status, #overview, #autotradeBanner { font-size:10.5px; }
    .tabs { flex-wrap:nowrap; overflow-x:auto; -webkit-overflow-scrolling:touch; padding-bottom:2px; }
    .tab { flex-shrink:0; font-size:12px; padding:6px 10px; }
    table { display:block; overflow-x:auto; white-space:nowrap; -webkit-overflow-scrolling:touch; max-width:100%; }
    th, td { padding:6px 8px; font-size:12px; }
  }
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
      <button id="resetSessionNyBtn">Очистить сессию NY</button>
      <button id="resetXauLgBtn">Очистить XAU LG</button>
      <button id="resetSimulatorBtn">Сбросить симулятор</button>
    </div>
  </div>
  <div id="status">загрузка...</div>
  <div id="overview" class="dim" style="margin-top:2px;font-size:12px;"></div>
  <div id="autotradeBanner" style="margin-top:2px;font-size:12px;"></div>
  <details id="riskAutotuneBox" style="margin-top:4px;font-size:11.5px;display:none;">
    <summary class="dim" style="cursor:pointer;">Авто-тюнинг риска</summary>
    <div id="riskAutotuneLog" class="dim" style="margin-top:4px;"></div>
  </details>
</header>
<div class="tabs">
  <div class="tab active" data-tab="signals">Volume</div>
  <div class="tab" data-tab="divergence">Дивергенции</div>
  <div class="tab" data-tab="ema">EMA</div>
  <div class="tab" data-tab="scalp">Скальпинг</div>
  <div class="tab" data-tab="session">Сессия</div>
  <div class="tab" data-tab="session_ny">Сессия NY</div>
  <div class="tab" data-tab="xau_lg" style="color:#e0a030;">XAU LG ⚠️</div>
  <div class="tab" data-tab="autotrade">Автоторговля</div>
  <div class="tab" data-tab="simulator">Симулятор</div>
</div>
<div class="panel">
  <div id="tuningPanel" style="display:none;padding:10px 4px;font-size:13px;"></div>
  <table id="signalsTable" style="display:table">
    <thead><tr><th>Symbol</th><th>Dir</th><th>Reason</th><th>Entry</th><th>SL</th><th>TP</th><th>MFE(R)</th><th>MAE(R)</th><th>Status</th><th>Time</th></tr></thead>
    <tbody></tbody>
  </table>
  <div id="divStatsPanel" style="display:none;padding:10px 4px;font-size:13px;"></div>
  <table id="divTable" style="display:none">
    <thead><tr><th>Symbol</th><th>Dir</th><th>Kind</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>MFE(R)</th><th>MAE(R)</th><th>Status</th><th>Time</th></tr></thead>
    <tbody></tbody>
  </table>
  <div id="emaStatsPanel" style="display:none;padding:10px 4px;font-size:13px;"></div>
  <table id="emaTable" style="display:none">
    <thead><tr><th>Symbol</th><th>Dir</th><th>TF</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>ADX</th><th>MFE(R)</th><th>MAE(R)</th><th>Status</th><th>Time</th></tr></thead>
    <tbody></tbody>
  </table>
  <div id="scalpPanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
  <div id="sessionPanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
  <div id="sessionNyPanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
  <div id="xauLgPanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
  <div id="autotradePanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
  <div id="simulatorPanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
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
      <div class="settingRow">
        <div>
          <div class="label">↳ Реверс сигналов (RR 2)</div>
          <div class="sub">торговать в обратную сторону; риск как у обычного стопа, тейк = 2×риска</div>
        </div>
        <label class="switch"><input type="checkbox" id="setSessionInvert"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="settingsGroup">
      <div class="settingsGroupTitle">Сессия NY</div>
      <div class="settingRow">
        <div>
          <div class="label">Манипуляция на открытии (Нью-Йорк)</div>
          <div class="sub">та же логика, что и обычная Сессия, но на открытии Нью-Йорка (16:30 Москва) — полностью независимый модуль, не влияет на Сессию выше</div>
        </div>
        <label class="switch"><input type="checkbox" id="setSessionNy"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Реверс сигналов (RR 2)</div>
          <div class="sub">торговать в обратную сторону; риск как у обычного стопа, тейк = 2×риска</div>
        </div>
        <label class="switch"><input type="checkbox" id="setSessionNyInvert"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="settingsGroup">
      <div class="settingsGroupTitle" style="color:#e0a030;">XAU Liquidity Grab ⚠️ Экспериментально</div>
      <div class="settingRow">
        <div>
          <div class="label">Сканирование (только золото)</div>
          <div class="sub">идея из непроверенного источника — см. предупреждение на вкладке. Автоторговля ниже выключена по умолчанию.</div>
        </div>
        <label class="switch"><input type="checkbox" id="setXauLg"><span class="switchSlider"></span></label>
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

    <div class="settingsGroup">
      <div class="settingsGroupTitle">Автоторговля</div>
      <div class="settingRow">
        <div>
          <div class="label">API-ключи Gate.io</div>
          <div class="sub" id="setGateApiSub">проверка...</div>
        </div>
      </div>
      <div class="settingRow" style="flex-direction:column;align-items:stretch;gap:8px;">
        <input type="text" id="setGateApiKey" placeholder="API Key" style="background:#0d1220;border:1px solid #1c2433;color:#fff;padding:8px 10px;border-radius:8px;font-size:13px;">
        <input type="password" id="setGateApiSecret" placeholder="API Secret" style="background:#0d1220;border:1px solid #1c2433;color:#fff;padding:8px 10px;border-radius:8px;font-size:13px;">
        <div style="display:flex;gap:8px;">
          <button id="saveGateApiBtn" style="flex:1;background:#1e2a3f;border:none;color:#fff;padding:8px;border-radius:8px;font-size:13px;">Сохранить ключи</button>
          <button id="clearGateApiBtn" style="background:#3a1e22;border:none;color:#ff9b9b;padding:8px 12px;border-radius:8px;font-size:13px;">Удалить</button>
        </div>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">Бумажная торговля (dry-run)</div>
          <div class="sub">без реальных ордеров, только лог того, что было бы сделано — выключи только когда уверен</div>
        </div>
        <label class="switch"><input type="checkbox" id="setAutotradeDryRun"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">Размер позиции</div>
          <div class="sub">режим и значение — либо % от баланса фьючерсного кошелька, либо фикс. $ маржи (плечо не влияет на это число)</div>
        </div>
      </div>
      <div class="settingRow" style="gap:8px;">
        <select id="setAutotradeSizeMode" style="background:#0d1220;border:1px solid #1c2433;color:#fff;padding:8px 10px;border-radius:8px;font-size:13px;">
          <option value="percent">% от депозита</option>
          <option value="fixed">Фикс. $</option>
        </select>
        <input type="number" id="setAutotradeSizeValue" step="0.1" min="0.1" style="background:#0d1220;border:1px solid #1c2433;color:#fff;padding:8px 10px;border-radius:8px;font-size:13px;width:100px;">
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Bounce</div>
          <div class="sub">плечо, если включено</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="number" id="setAutotradeLevBounce" min="1" max="125" style="width:60px;background:#0d1220;border:1px solid #1c2433;color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;">
          <label class="switch"><input type="checkbox" id="setAutotradeBounce"><span class="switchSlider"></span></label>
        </div>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Breakout</div>
          <div class="sub">плечо, если включено</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="number" id="setAutotradeLevBreakout" min="1" max="125" style="width:60px;background:#0d1220;border:1px solid #1c2433;color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;">
          <label class="switch"><input type="checkbox" id="setAutotradeBreakout"><span class="switchSlider"></span></label>
        </div>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Дивергенции</div>
          <div class="sub">плечо, если включено</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="number" id="setAutotradeLevDivergence" min="1" max="125" style="width:60px;background:#0d1220;border:1px solid #1c2433;color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;">
          <label class="switch"><input type="checkbox" id="setAutotradeDivergence"><span class="switchSlider"></span></label>
        </div>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ EMA</div>
          <div class="sub">плечо, если включено</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="number" id="setAutotradeLevEma" min="1" max="125" style="width:60px;background:#0d1220;border:1px solid #1c2433;color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;">
          <label class="switch"><input type="checkbox" id="setAutotradeEma"><span class="switchSlider"></span></label>
        </div>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ EMA мин. RR</div>
          <div class="sub">0 = выключено. Сигнал пропускается, если ATR-стоп даёт RR ниже этого</div>
        </div>
        <input type="number" id="setEmaMinRr" step="0.1" min="0" style="background:#0d1220;border:1px solid #1c2433;color:#fff;padding:8px 10px;border-radius:8px;font-size:13px;width:100px;">
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ EMA тайм-аут (ч)</div>
          <div class="sub">закрыть как TIMEOUT, если ни TP, ни SL не сработали за это время — отдельно от Volume/Дивергенций</div>
        </div>
        <input type="number" id="setEmaSignalTimeoutHours" step="1" min="1" style="background:#0d1220;border:1px solid #1c2433;color:#fff;padding:8px 10px;border-radius:8px;font-size:13px;width:100px;">
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ EMA фильтр ADX</div>
          <div class="sub">не торговать кроссовер, если тренд слишком слабый (Уайлдер, стандартный порог)</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="number" id="setEmaAdxMin" step="1" min="0" style="width:60px;background:#0d1220;border:1px solid #1c2433;color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;">
          <label class="switch"><input type="checkbox" id="setEmaAdxFilterEnabled"><span class="switchSlider"></span></label>
        </div>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ EMA мин. зазор EMA7/14 (%)</div>
          <div class="sub">0 = выключено. Отсекает пограничные, почти незаметные пересечения</div>
        </div>
        <input type="number" id="setEmaMinGapPct" step="0.01" min="0" style="background:#0d1220;border:1px solid #1c2433;color:#fff;padding:8px 10px;border-radius:8px;font-size:13px;width:100px;">
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Скальпинг</div>
          <div class="sub">плечо берётся из самого сигнала, не отсюда</div>
        </div>
        <label class="switch"><input type="checkbox" id="setAutotradeScalp"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow" style="gap:8px;">
        <div>
          <div class="label">↳ Сумма скальпинга</div>
          <div class="sub">своя, отдельно от общего размера позиции выше</div>
        </div>
        <select id="setScalpSizeMode" style="background:#0d1220;border:1px solid #1c2433;color:#fff;padding:8px 10px;border-radius:8px;font-size:13px;">
          <option value="percent">% от депозита</option>
          <option value="fixed">Фикс. $</option>
        </select>
        <input type="number" id="setScalpSizeValue" step="0.1" min="0.1" style="background:#0d1220;border:1px solid #1c2433;color:#fff;padding:8px 10px;border-radius:8px;font-size:13px;width:100px;">
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Сессия</div>
          <div class="sub">плечо, если включено</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="number" id="setAutotradeLevSession" min="1" max="125" style="width:60px;background:#0d1220;border:1px solid #1c2433;color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;">
          <label class="switch"><input type="checkbox" id="setAutotradeSession"><span class="switchSlider"></span></label>
        </div>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Сессия NY</div>
          <div class="sub">плечо, если включено</div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <input type="number" id="setAutotradeLevSessionNy" min="1" max="125" style="width:60px;background:#0d1220;border:1px solid #1c2433;color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;">
          <label class="switch"><input type="checkbox" id="setAutotradeSessionNy"><span class="switchSlider"></span></label>
        </div>
      </div>
    </div>

    <div class="dim" style="font-size:12px;margin-top:16px;">Изменения применяются сразу, без перезапуска, и сохраняются на диск. Здесь только общие переключатели — детальные параметры (RR, буферы, пороги фильтров) настраиваются через переменные окружения при запуске.</div>
  </div>
</div>

<script>
const fmt = (n, d=6) => n === null || n === undefined ? '-' : Number(n).toPrecision(d).replace(/\\.?0+$/,'').replace(/\\.$/, '');
const fmtTime = (t) => t ? new Date(t*1000).toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'}) : '-';
const fmtDateTime = (t) => t ? new Date(t*1000).toLocaleString('ru-RU', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}) : '-';  // date+time, not just time — Session's own open time is the SAME 10:00 every day by design, so time-only gives no way to tell which day's session a row belongs to

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
    document.getElementById('sessionNyPanel').style.display = activeTab === 'session_ny' ? 'block' : 'none';
    document.getElementById('xauLgPanel').style.display = activeTab === 'xau_lg' ? 'block' : 'none';
    document.getElementById('autotradePanel').style.display = activeTab === 'autotrade' ? 'block' : 'none';
    document.getElementById('simulatorPanel').style.display = activeTab === 'simulator' ? 'block' : 'none';
    if (activeTab === 'signals') refreshTuning();
    if (activeTab === 'divergence') refreshDivergence();
    if (activeTab === 'ema') refreshEma();
    if (activeTab === 'scalp') refreshScalp();
    if (activeTab === 'session') refreshSession();
    if (activeTab === 'session_ny') refreshSessionNy();
    if (activeTab === 'xau_lg') refreshXauLg();
    if (activeTab === 'autotrade') refreshAutotrade();
    if (activeTab === 'simulator') refreshSimulator();
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
    const fetchErrTxt = s.excluded_fetch_error ? `, ${s.excluded_fetch_error} сетевых сбоев` : '';
    const scanTxt = s.last_scan_finished ? `скан ${s.last_scan_duration}s, ${s.universe_size} пар (искл. ${s.excluded_low_quality||0} неликвид${fetchErrTxt})` : 'сканирование...';
    el.textContent = `v${s.version} · ${scanTxt}`;
    const ra = s.risk_autotune;
    const raBox = document.getElementById('riskAutotuneBox');
    if (ra && ra.log && ra.log.length) {
      raBox.style.display = 'block';
      const paramLabels = {ema_min_rr: 'EMA мин.RR', ema_sl_atr_mult: 'EMA ATR-мульт.', ema_invert_signals: 'EMA реверс',
        div_min_rr: 'Див мин.RR', div_sl_atr_mult: 'Див ATR-мульт.', div_invert_signals: 'Див реверс',
        scalp_min_rr: 'Скальп мин.RR', scalp_sl_buffer_mult: 'Скальп SL-буфер',
        session_invert_signals: 'Сессия реверс'};
      raBox.querySelector('summary').textContent = `Авто-тюнинг риска (${ra.enabled ? 'вкл' : 'выкл'}, последних: ${ra.log.length})`;
      document.getElementById('riskAutotuneLog').innerHTML = ra.log.map(e => {
        const label = paramLabels[e.param] || e.param;
        const oldTxt = typeof e.old === 'boolean' ? (e.old ? 'вкл' : 'выкл') : e.old;
        const newTxt = typeof e.new === 'boolean' ? (e.new ? 'вкл' : 'выкл') : e.new;
        return `${fmtDateTime(e.ts)} — <b>${e.module}</b>.${label}: ${oldTxt} → ${newTxt} <span class="dim">(${e.reason}, n=${e.n})</span>`;
      }).join('<br>');
    } else {
      raBox.style.display = 'none';
    }
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
  const errList = s.errors || [];
  const errHtml = errList.length ? `
    <div class="dim" style="margin-top:10px;padding-top:10px;border-top:1px solid #1c2433;">
      <b class="loss">Последние ошибки сканера (${errList.length}):</b><br>
      <span style="font-size:12px;">${errList.slice().reverse().map(e => `${fmtTime(e.t)} — ${e.msg}`).join('<br>')}</span>
    </div>` : '';
  const detailHtml = `
    <div class="dim" style="margin-bottom:10px;">
      <b>Volume</b> · Винрейт: ${wr} (${st.wins||0}W / ${st.losses||0}L, timeout ${st.timeouts||0}) · ${bounceTxt} · ${breakoutTxt} · открытых: ${st.open||0} · RR ${s.config ? s.config.rr : ''}<br>
      ${atTxt}<br>
      За этот скан отклонено — тренд: ${s.filtered_by_trend||0}, объём: ${s.filtered_by_volume||0}, OI: ${s.filtered_by_oi||0}, устарел: ${s.filtered_by_staleness||0} · ${cvTxt}
    </div>${errHtml}`;
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
      <td class="dim">${r.rr !== null && r.rr !== undefined ? r.rr : '-'}</td>
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
    const gainTxt = v.avg_pct_gain !== null && v.avg_pct_gain !== undefined
      ? ` · вход раньше в среднем на ${Math.abs(v.avg_pct_gain)}% ${v.avg_pct_gain >= 0 ? 'лучше' : 'хуже'}`
      : '';
    return total
      ? `right=${r}: <b>${v.rate}%</b> согласия (${v.agree}/${total})${gainTxt}`
      : `right=${r}: пока нет данных`;
  }).join('<br>');
  const psBlock = psRows ? `
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid #1c2433;">
      <b>Насколько можно уменьшить задержку подтверждения пивота (right=${cfg.pivot_right} сейчас):</b><br>
      <span class="dim" style="font-size:12px;">процент случаев, когда укороченное окно указало бы на ту же точку, что и строгая (текущая) проверка — не ретроспективно на уже известном ответе, а по факту вживую${cfg.invert_signals ? ' · знак "лучше/хуже" уже учитывает реверс — считается для того направления, которое реально торгуется' : ''}</span><br>
      <span style="font-size:13px;">${psRows}</span>
    </div>` : '';
  panel.innerHTML = `
    <div class="dim" style="margin-bottom:10px;">
      RSI-дивергенции${cfg.invert_signals ? ' <span style="color:#ffcc55;font-weight:bold;">· РЕВЕРС ВКЛЮЧЁН</span>' : ''} · ТФ ${status.interval} · скан ${status.last_scan_duration!==null && status.last_scan_duration!==undefined ? status.last_scan_duration+'s' : '...'} ·
      Винрейт: ${wr} (${s.wins||0}W / ${s.losses||0}L, timeout ${s.timeouts||0}) · открытых: ${s.open||0} · RR ср. ${s.rr_all ? s.rr_all.avg : '?'} (медиана ${s.rr_all ? s.rr_all.median : '?'}) · SL: ${cfg.sl_mode === 'atr' ? `ATR×${cfg.sl_atr_mult}` : `фикс. RR ${cfg.rr_fallback}`}${cfg.min_rr > 0 ? ` · мин. RR ${cfg.min_rr} (отсеяно: ${status.filtered_by_min_rr||0})` : ''}
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
      <td class="dim">${r.rr !== null && r.rr !== undefined ? r.rr : '-'}</td>
      <td class="dim">${r.adx !== null && r.adx !== undefined ? r.adx : '-'}</td>
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
      <span class="loss">LOSS MAE: ${fmtStat(s.mae_r_losses_at_close)}</span><br>
      <span class="dim">TIMEOUT реализованный R (не входит в винрейт, но реально двигает баланс): ${fmtStat(s.exit_r_timeouts)}</span>
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
      Винрейт (всё вместе): ${wr} (${s.wins||0}W / ${s.losses||0}L, timeout ${s.timeouts||0}) · открытых: ${s.open||0} · RR ср. ${s.rr_all ? s.rr_all.avg : '?'} (медиана ${s.rr_all ? s.rr_all.median : '?'}) · SL: ${cfg.sl_mode === 'atr' ? `ATR×${cfg.sl_atr_mult}` : `фикс. RR ${cfg.rr_fallback}`}${cfg.min_rr > 0 ? ` · мин. RR ${cfg.min_rr} (отсеяно: ${status.filtered_by_min_rr||0})` : ''}${cfg.adx_filter_enabled ? ` · ADX ≥ ${cfg.adx_min} (отсеяно: ${status.filtered_by_adx||0})` : ''}${cfg.min_gap_pct > 0 ? ` · мин. зазор ${cfg.min_gap_pct}% (отсеяно: ${status.filtered_by_min_gap||0})` : ''}
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
  const ts = status.tuning_stats || {};
  const mfeMaeHtml = ts.count ? `
    <div style="margin-bottom:8px;"><b>MFE/MAE (R, R = свой SL% каждой сделки) на закрытии</b> — сколько реально было хода в плюс/минус к моменту исхода (n=${ts.count}: ${ts.wins_n}W/${ts.losses_n}L):<br>
      <span class="win">WIN MFE: ${fmtStat(ts.mfe_r_wins_at_close)}</span><br>
      <span class="win">WIN MAE: ${fmtStat(ts.mae_r_wins_at_close)}</span><br>
      <span class="loss">LOSS MFE: ${fmtStat(ts.mfe_r_losses_at_close)}</span><br>
      <span class="loss">LOSS MAE: ${fmtStat(ts.mae_r_losses_at_close)}</span><br>
      <span class="dim" style="font-size:11px;">Если WIN MFE заметно больше 1.0 (текущий тейк = target_pct/sl_pct в R) — тейк можно двигать дальше. Если WIN MAE близко к -1.0 — почти дошло до стопа перед тем как выиграть, стоп можно чуть шире. Если LOSS MAE заметно меньше -1.0 по модулю — стоп теснее, чем нужно.</span>
    </div>` : '<div class="dim" style="margin-bottom:8px;">MFE/MAE статистика пока копится — нужны закрытые сделки.</div>';
  const headerHtml = `
    <div class="dim" style="margin-bottom:8px;">
      Цель: $${cfg.target_profit_usd} со счёта $${cfg.account_usd} · ТФ: ${(cfg.intervals||[]).join(', ')} ·
      мин. hit-rate ${cfg.min_hit_rate}% · запас безопасности x${cfg.safety_margin} · комиссия ${(cfg.taker_fee_pct*100).toFixed(3)}%/сторону<br>
      ${buildTxt} · без безопасной конфигурации: ${status.no_safe_config_count}<br>
      <b>Живые сигналы</b> (вход на закрытии свечи, топ-${cfg.signal_top_n || 1} по score): ${ssWr} (${ss.wins||0}W/${ss.losses||0}L/${ss.timeouts||0}TIMEOUT) · открытых: ${ss.open||0} · всего: ${ss.total||0}<br>
      <span style="font-size:11px;">~ рядом с буфером = MMR не подтверждён с Gate.io, используется консервативный дефолт ${(cfg.default_mmr_pct*100).toFixed(2)}%<br>
      ~ рядом с плечом = макс. плечо биржи для монеты не подтверждено, используется дефолт ${cfg.default_max_leverage}x — проверь реальный лимит на бирже перед входом</span>
    </div>
    ${mfeMaeHtml}`;
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
      окно манипуляции: первые ${cfg.manipulation_window_min} мин после открытия · мин. выборка для ранжирования: ${cfg.min_sample}${cfg.invert_signals ? ' · <span style="color:#ffcc55;font-weight:bold;">РЕВЕРС ВКЛЮЧЁН (RR 2)</span>' : ''}<br>
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
      <td>${statusHtml}</td><td class="dim">${fmtDateTime(s.session_open)}</td>
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
      return `<span class="sessionDayLink" data-symbol="${symbol}" data-session-open="${r.session_open}" style="cursor:pointer;text-decoration:underline dotted;">${fmtDateTime(r.session_open)}: <span class="${dirClass}">${r.direction}</span> <span class="${resClass}">${r.result}</span></span>`;
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

// ---------------- Session NY (New York open, v0.94.0) ----------------
// Full duplicate of the block above, own STATE var/functions/endpoints
// throughout — reuses only the already-generic formatters (fmt, fmtTime,
// fmtDateTime) shared by the whole page, same as the Python side reuses
// only pure helpers like get_candles_range/get_tickers.
let sessionNyExpanded = null;

function fmtSessionNyRow(r, rank) {
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

async function refreshSessionNy() {
  const status = await (await fetch('/api/session_ny/status')).json();
  const signals = await (await fetch('/api/session_ny/signals')).json();
  const panel = document.getElementById('sessionNyPanel');
  const cfg = status.config || {};
  const ss = status.signals_stats || {};
  const buildTxt = status.last_backtest_finished
    ? `последний бэктест: ${fmtTime(status.last_backtest_finished)} (${status.last_backtest_duration}s) · монет обработано: ${status.symbols_done}/${status.universe_size}`
    : `первый бэктест ещё не завершился (${status.symbols_done}/${status.universe_size || '?'})`;
  const nextOpenTxt = status.next_open_ts ? `следующее открытие Нью-Йорка: ${fmtTime(status.next_open_ts)}` : '';
  const ssWr = ss.winrate !== null && ss.winrate !== undefined ? `${ss.winrate}%` : '-';
  const watchTxt = Object.entries(status.watch_symbols || {}).map(([sym, w]) => {
    const label = {ranked: 'в рейтинге', zero_manipulations_found: 'манипуляций не найдено', not_yet_processed: 'ещё считается', not_in_universe: 'не в вселенной'}[w.status] || w.status;
    return `${sym}: ${label}${w.n !== null && w.n !== undefined ? ' (n='+w.n+')' : ''}`;
  }).join(' · ');
  const openMinTxt = String(cfg.open_minute_local || 0).padStart(2, '0');
  const headerHtml = `
    <div class="dim" style="margin-bottom:8px;">
      Открытие Нью-Йорка: ${cfg.open_hour_local}:${openMinTxt} (UTC+${cfg.utc_offset_hours}, фикс.) · диапазон проторговки: с ${cfg.range_start_utc_hour}:00 UTC до открытия, ТФ ${cfg.range_tf} ·
      окно манипуляции: первые ${cfg.manipulation_window_min} мин после открытия · мин. выборка для ранжирования: ${cfg.min_sample}${cfg.invert_signals ? ' · <span style="color:#ffcc55;font-weight:bold;">РЕВЕРС ВКЛЮЧЁН (RR 2)</span>' : ''}<br>
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
      <td>${statusHtml}</td><td class="dim">${fmtDateTime(s.session_open)}</td>
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
    wireSessionNyRowClicks();
    return;
  }
  const rows = status.top.map((r, i) => fmtSessionNyRow(r, i + 1)).join('');
  panel.innerHTML = headerHtml + signalsTableHtml + `
    <div id="sessionNyDetail" style="margin-bottom:12px;"></div>
    <div class="dim" style="margin-bottom:6px;"><b>Бэктест по монетам</b> (сортировка: сначала прошедшие мин. выборку, потом по винрейту):</div>
    <div style="overflow-x:auto;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>#</th><th>Symbol</th><th>Win-rate</th><th>n</th><th>W</th><th>L</th><th>T</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    </div>`;
  wireSessionNyRowClicks();
}

function wireSessionNyRowClicks() {
  document.querySelectorAll('#sessionNyPanel tbody tr[data-session-open]').forEach(tr => {
    tr.onclick = () => openSessionNyChart(tr.dataset.symbol, tr.dataset.sessionOpen);
  });
  document.querySelectorAll('#sessionNyPanel tbody tr[data-symbol]:not([data-session-open])').forEach(tr => {
    tr.onclick = () => openSessionNyDetail(tr.dataset.symbol);
  });
}

async function openSessionNyDetail(symbol) {
  const detail = document.getElementById('sessionNyDetail');
  if (sessionNyExpanded === symbol) {
    detail.innerHTML = '';
    sessionNyExpanded = null;
    return;
  }
  sessionNyExpanded = symbol;
  detail.innerHTML = '<div class="dim">загрузка...</div>';
  try {
    const j = await (await fetch(`/api/session_ny/symbol/${symbol}`)).json();
    if (j.error) { detail.innerHTML = `<div class="dim">${j.error}</div>`; return; }
    const rows = (j.results || []).map(r => {
      const dirClass = r.direction === 'LONG' ? 'long' : 'short';
      const resClass = r.result === 'WIN' ? 'win' : (r.result === 'LOSS' ? 'loss' : 'status-timeout');
      return `<span class="sessionNyDayLink" data-symbol="${symbol}" data-session-open="${r.session_open}" style="cursor:pointer;text-decoration:underline dotted;">${fmtDateTime(r.session_open)}: <span class="${dirClass}">${r.direction}</span> <span class="${resClass}">${r.result}</span></span>`;
    }).join(' · ');
    detail.innerHTML = `<div style="border-top:1px solid #1c2433;padding-top:8px;"><b>${symbol}</b> — история по дням (клик открывает график):<br>
      <span style="font-size:11px;">${rows || 'нет данных'}</span></div>`;
    detail.querySelectorAll('.sessionNyDayLink').forEach(el => {
      el.onclick = () => openSessionNyChart(el.dataset.symbol, el.dataset.sessionOpen);
    });
  } catch (e) {
    detail.innerHTML = `<div class="dim">ошибка загрузки: ${e}</div>`;
  }
}

// ---------------- XAU Liquidity Grab (EXPERIMENTAL, v0.95.0) ----------------
// Deliberately simpler than Session/Session NY — no per-symbol day-history
// modal, no chart viewer. This is a provisional module built to test an
// unverified Instagram-sourced strategy idea, not a polished feature; kept
// minimal on purpose so it stays easy to find and delete if it doesn't
// hold up (see the Python module's own header comment for the full
// reasoning and source skepticism).
async function refreshXauLg() {
  const status = await (await fetch('/api/xau_lg/status')).json();
  const signals = await (await fetch('/api/xau_lg/signals')).json();
  const panel = document.getElementById('xauLgPanel');
  const cfg = status.config || {};
  const ss = status.signals_stats || {};
  const ssWr = ss.winrate !== null && ss.winrate !== undefined ? `${ss.winrate}%` : '-';
  const buildTxt = status.last_backtest_finished
    ? `последний бэктест: ${fmtTime(status.last_backtest_finished)} (${status.last_backtest_duration}s)`
    : 'бэктест ещё не завершился';
  const warnHtml = `
    <div style="background:#2a1f0e;border:1px solid #e0a030;border-radius:10px;padding:10px 14px;margin-bottom:12px;">
      <b style="color:#e0a030;">⚠️ Экспериментально</b><br>
      <span style="font-size:12px;color:#d9c08a;">Идея взята из поста в Instagram (заявлено 76% winrate / &lt;2% просадка) — источник непроверяемый, доверять цифрам со скриншота нельзя. Здесь — честный бэктест по нашим собственным данным без заглядывания вперёд. Автоторговля выключена по умолчанию.</span>
    </div>`;
  const headerHtml = `
    <div class="dim" style="margin-bottom:8px;">
      Символы: ${(status.symbols||[]).join(', ')} · ТФ ${cfg.tf} · EMA(${cfg.ema_period}) фильтр тренда · пивоты L${cfg.pivot_left}/R${cfg.pivot_right} · RR фикс. ${cfg.rr}<br>
      ${buildTxt}<br>
      <b>Живые сигналы</b>: ${ssWr} (${ss.wins||0}W/${ss.losses||0}L, timeout ${ss.timeouts||0}) · открытых: ${ss.open||0} · всего: ${ss.total||0}
    </div>`;
  const signalsRows = signals.map(s => {
    const dirClass = s.direction === 'LONG' ? 'long' : 'short';
    let statusHtml;
    if (s.status === 'OPEN') statusHtml = '<span class="status-open">OPEN</span>';
    else if (s.result === 'WIN') statusHtml = `<span class="win">WIN @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else if (s.result === 'LOSS') statusHtml = `<span class="loss">LOSS @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else statusHtml = '<span class="status-timeout">TIMEOUT</span>';
    return `<tr>
      <td>${s.symbol}</td><td class="${dirClass}">${s.direction}</td>
      <td>${fmt(s.entry)}</td><td class="dim">${fmt(s.sl)}</td><td class="dim">${fmt(s.tp)}</td>
      <td>${statusHtml}</td><td class="dim">${fmtDateTime(s.time)}</td>
    </tr>`;
  }).join('');
  const signalsTableHtml = signals.length ? `
    <div style="overflow-x:auto;margin-bottom:14px;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>Status</th><th>Время</th></tr></thead>
      <tbody>${signalsRows}</tbody>
    </table>
    </div>` : '<div class="dim" style="margin-bottom:14px;">Живых сигналов пока нет.</div>';
  const btRows = (status.top || []).map(r => {
    const wrClass = (r.win_rate === null || r.win_rate === undefined) ? 'dim' : (r.win_rate >= 50 ? 'win' : 'loss');
    return `<tr>
      <td>${r.symbol}</td>
      <td class="${wrClass}">${r.win_rate !== null && r.win_rate !== undefined ? r.win_rate+'%' : '-'}</td>
      <td class="dim">n=${r.n}</td>
      <td class="win">${r.wins}W</td>
      <td class="loss">${r.losses}L</td>
      <td class="status-timeout">${r.timeouts}T</td>
    </tr>`;
  }).join('');
  const btTableHtml = (status.top || []).length ? `
    <div class="dim" style="margin-bottom:6px;"><b>Бэктест по монетам</b> (${cfg.backtest_days} дней истории, без заглядывания вперёд):</div>
    <div style="overflow-x:auto;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>Win-rate</th><th>n</th><th>W</th><th>L</th><th>T</th></tr></thead>
      <tbody>${btRows}</tbody>
    </table>
    </div>` : '<div class="dim">Бэктест ещё не готов.</div>';
  panel.innerHTML = warnHtml + headerHtml + signalsTableHtml + btTableHtml;
}

async function refreshAutotradeBanner() {
  try {
    const s = await (await fetch('/api/autotrade/status')).json();
    const anyEnabled = Object.values(s.enabled).some(v => v);
    const el = document.getElementById('autotradeBanner');
    if (!anyEnabled) {
      el.innerHTML = '';
    } else if (!s.dry_run) {
      el.innerHTML = '<span style="color:#ff6b6b;font-weight:700;">⚠️ РЕАЛЬНЫЕ ОРДЕРА ВКЛЮЧЕНЫ</span>';
    } else {
      el.innerHTML = '<span style="color:#3ddc97;">✓ автоторговля: dry-run</span>';
    }
  } catch(e) {}
}

async function refreshAutotrade() {
  const [status, log] = await Promise.all([
    (await fetch('/api/autotrade/status')).json(),
    (await fetch('/api/autotrade/log')).json(),
  ]);
  const panel = document.getElementById('autotradePanel');
  const modeLabels = {bounce: 'Bounce', breakout: 'Breakout', divergence: 'Дивергенции', ema: 'EMA', scalp: 'Скальпинг', session: 'Сессия', session_ny: 'Сессия NY', xau_lg: 'XAU LG'};
  const enabledTxt = Object.entries(status.enabled)
    .map(([k, v]) => `<span class="${v ? 'win' : 'dim'}">${modeLabels[k]}: ${v ? 'вкл' : 'выкл'}</span>`)
    .join(' &nbsp;·&nbsp; ');

  let bannerHtml = '';
  if (!status.dry_run) {
    bannerHtml = `<div style="background:#3a1e22;border:1px solid #ff6b6b;border-radius:10px;padding:12px 14px;margin-bottom:14px;">
      <b style="color:#ff6b6b;">⚠️ РЕАЛЬНЫЕ ОРДЕРА ВКЛЮЧЕНЫ</b><br>
      <span style="font-size:12px;color:#ffb3b3;">Dry-run выключен — включённые режимы будут открывать настоящие позиции на бирже за реальные деньги.</span>
    </div>`;
  } else {
    bannerHtml = `<div style="background:#132018;border:1px solid #3ddc97;border-radius:10px;padding:10px 14px;margin-bottom:14px;">
      <span style="color:#3ddc97;font-size:12px;">✓ Dry-run включён — реальные ордера не отправляются, только лог того, что было бы сделано.</span>
    </div>`;
  }

  const apiTxt = status.gate_api_configured
    ? '<span class="win">ключи Gate.io сохранены</span>'
    : '<span class="loss">ключи Gate.io не заданы — реальные ордера невозможны</span>';

  const headerHtml = `
    ${bannerHtml}
    <div class="dim" style="margin-bottom:8px;">
      ${apiTxt}<br>
      Режимы: ${enabledTxt}<br>
      Всего попыток: ${status.total} · <span class="win">открыто: ${status.opened}</span> ·
      <span class="status-open">dry-run: ${status.dry_run_count}</span> ·
      <span class="dim">пропущено: ${status.skipped}</span> · <span class="loss">ошибок: ${status.errors}</span>
    </div>`;

  const rows = log.map(e => {
    const dirClass = e.direction === 'LONG' ? 'long' : (e.direction === 'SHORT' ? 'short' : 'dim');
    const statusClass = {OPENED: 'win', OPENED_TP_SL_FAILED: 'loss', DRY_RUN: 'status-open', SKIPPED: 'dim', ERROR: 'loss'}[e.status] || 'dim';
    return `<tr>
      <td class="dim">${fmtTime(e.time)}</td><td>${modeLabels[e.mode] || e.mode}</td><td>${e.symbol}</td>
      <td class="${dirClass}">${e.direction || '-'}</td>
      <td class="${statusClass}">${e.status}</td>
      <td class="dim" style="max-width:280px;white-space:normal;">${e.detail || ''}</td>
    </tr>`;
  }).join('');

  const tableHtml = log.length ? `
    <div style="overflow-x:auto;">
    <table style="font-size:11px;">
      <thead><tr><th>Время</th><th>Режим</th><th>Symbol</th><th>Dir</th><th>Статус</th><th>Детали</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    </div>` : '<div class="dim">Пока нет попыток автоторговли.</div>';

  panel.innerHTML = headerHtml + tableHtml;
}

async function refreshSimulator() {
  const [status, trades, autotradeStatus] = await Promise.all([
    (await fetch('/api/simulator/status')).json(),
    (await fetch('/api/simulator/trades')).json(),
    (await fetch('/api/autotrade/status')).json(),
  ]);
  const panel = document.getElementById('simulatorPanel');
  const modeLabels = {bounce: 'Bounce', breakout: 'Breakout', divergence: 'Дивергенции', ema: 'EMA', scalp: 'Скальпинг', session: 'Сессия', session_ny: 'Сессия NY', xau_lg: 'XAU LG'};

  const pnlClass = status.pnl_total >= 0 ? 'win' : 'loss';
  const sizeTxt = status.size_mode === 'percent' ? `${status.size_value}% от баланса` : `фикс. $${status.size_value}`;
  const enabledTxt = Object.entries(autotradeStatus.enabled || {})
    .map(([k, v]) => `<span class="${v ? 'win' : 'dim'}">${modeLabels[k]}: ${v ? 'вкл' : 'выкл'}</span>`)
    .join(' &nbsp;·&nbsp; ');

  const headerHtml = `
    <div class="dim" style="margin-bottom:10px;">
      Симулятор повторяет ровно те же сделки, что и автоторговля выше (те же тумблеры режимов, тот же размер/плечо) — показывает, каким был бы баланс на реальных или dry-run сделках. Размер: ${sizeTxt} · комиссия ${(status.fee_pct*100).toFixed(3)}%/сторону.<br>
      Режимы: ${enabledTxt}
    </div>
    <div style="margin-bottom:10px;">
      <div style="font-size:28px;font-weight:700;">$${status.balance.toFixed(2)}</div>
      <div class="${pnlClass}" style="font-size:14px;">
        ${status.pnl_total >= 0 ? '+' : ''}${status.pnl_total.toFixed(2)}$
        (${status.pnl_pct !== null ? (status.pnl_pct >= 0 ? '+' : '') + status.pnl_pct + '%' : '-'})
        от старта $${status.start_balance.toFixed(2)}
      </div>
    </div>
    <div class="dim" style="margin-bottom:10px;">
      Сделок: ${status.settled} закрыто, ${status.pending} в ожидании ·
      <span class="win">${status.wins}W</span>/<span class="loss">${status.losses}L</span>/<span class="status-timeout">${status.timeouts}T</span> ·
      винрейт: ${status.win_rate !== null ? status.win_rate+'%' : '-'}
    </div>`;

  const rows = trades.map(t => {
    const dirClass = t.direction === 'LONG' ? 'long' : 'short';
    const statusHtml = t.status === 'PENDING'
      ? '<span class="status-open">PENDING</span>'
      : (t.result === 'WIN' ? '<span class="win">WIN</span>' : (t.result === 'LOSS' ? '<span class="loss">LOSS</span>' : '<span class="status-timeout">TIMEOUT</span>'));
    const pnlTxt = t.pnl !== null && t.pnl !== undefined
      ? `<span class="${t.pnl >= 0 ? 'win' : 'loss'}">${t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(3)}$</span>`
      : '<span class="dim">-</span>';
    return `<tr>
      <td class="dim">${fmtTime(t.time)}</td><td>${modeLabels[t.mode] || t.mode}</td><td>${t.symbol}</td>
      <td class="${dirClass}">${t.direction}</td>
      <td class="dim">${fmt(t.entry)}</td>
      <td class="loss">${t.sl !== null && t.sl !== undefined ? fmt(t.sl) : '-'}</td>
      <td class="win">${t.tp !== null && t.tp !== undefined ? fmt(t.tp) : '-'}</td>
      <td class="dim">${fmt(t.margin,4)}$ x${t.leverage}</td>
      <td>${statusHtml}</td><td>${pnlTxt}</td>
      <td class="dim">${t.balance_after !== null && t.balance_after !== undefined ? '$'+t.balance_after.toFixed(2) : '-'}</td>
    </tr>`;
  }).join('');

  const tableHtml = trades.length ? `
    <div style="overflow-x:auto;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Время</th><th>Режим</th><th>Symbol</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>Маржа/плечо</th><th>Статус</th><th>PnL</th><th>Баланс</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    </div>` : '<div class="dim">Пока нет сделок симулятора.</div>';

  panel.innerHTML = headerHtml + tableHtml;
}

async function refreshAll() {
  await refreshStatus();
  await refreshOverview();
  await refreshAutotradeBanner();
  await refreshSignals();
  if (activeTab === 'signals') await refreshTuning();
  if (activeTab === 'divergence') await refreshDivergence();
  if (activeTab === 'ema') await refreshEma();
  if (activeTab === 'scalp') await refreshScalp();
  if (activeTab === 'session') await refreshSession();
  if (activeTab === 'session_ny') await refreshSessionNy();
  if (activeTab === 'xau_lg') await refreshXauLg();
  if (activeTab === 'autotrade') await refreshAutotrade();
  if (activeTab === 'simulator') await refreshSimulator();
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
wireResetButton('resetSessionNyBtn', '/api/reset/session_ny',
  'Удалить накопленный бэктест и сигналы по манипуляции на открытии Нью-Йорка? Остальное (включая обычную Сессию) не тронет. Это необратимо.',
  'Очистить сессию NY');
wireResetButton('resetXauLgBtn', '/api/reset/xau_lg',
  'Удалить накопленный бэктест и сигналы экспериментального XAU Liquidity Grab? Остальное не тронет. Это необратимо.',
  'Очистить XAU LG');
wireResetButton('resetSimulatorBtn', '/api/simulator/reset',
  'Сбросить симулятор баланса к стартовому значению и удалить всю историю сделок? Это необратимо.',
  'Сбросить симулятор');

// ---------------- Settings modal ----------------
const settingsModal = document.getElementById('settingsModal');
const setInputs = {
  volume_profile_enabled: document.getElementById('setVolumeProfile'),
  bounce_enabled: document.getElementById('setBounce'),
  breakout_enabled: document.getElementById('setBreakout'),
  divergence_enabled: document.getElementById('setDivergence'),
  div_invert_signals: document.getElementById('setDivInvert'),
  session_invert_signals: document.getElementById('setSessionInvert'),
  ema_enabled: document.getElementById('setEma'),
  ema_invert_signals: document.getElementById('setEmaInvert'),
  ema_adx_filter_enabled: document.getElementById('setEmaAdxFilterEnabled'),
  scalp_enabled: document.getElementById('setScalp'),
  scalp_signals_enabled: document.getElementById('setScalpSignals'),
  session_enabled: document.getElementById('setSession'),
  session_ny_enabled: document.getElementById('setSessionNy'),
  session_ny_invert_signals: document.getElementById('setSessionNyInvert'),
  xau_lg_enabled: document.getElementById('setXauLg'),
  telegram_enabled: document.getElementById('setTelegram'),
  telegram_alerts_vp: document.getElementById('setTelegramVp'),
  telegram_alerts_div: document.getElementById('setTelegramDiv'),
  telegram_alerts_ema: document.getElementById('setTelegramEma'),
  telegram_alerts_hourly: document.getElementById('setTelegramHourly'),
  telegram_alerts_session: document.getElementById('setTelegramSession'),
  autotrade_dry_run: document.getElementById('setAutotradeDryRun'),
  autotrade_bounce: document.getElementById('setAutotradeBounce'),
  autotrade_breakout: document.getElementById('setAutotradeBreakout'),
  autotrade_divergence: document.getElementById('setAutotradeDivergence'),
  autotrade_ema: document.getElementById('setAutotradeEma'),
  autotrade_scalp: document.getElementById('setAutotradeScalp'),
  autotrade_session: document.getElementById('setAutotradeSession'),
  autotrade_session_ny: document.getElementById('setAutotradeSessionNy'),
};

const setValueInputs = {
  autotrade_size_mode: document.getElementById('setAutotradeSizeMode'),
  autotrade_size_value: document.getElementById('setAutotradeSizeValue'),
  scalp_size_mode: document.getElementById('setScalpSizeMode'),
  scalp_size_value: document.getElementById('setScalpSizeValue'),
  ema_min_rr: document.getElementById('setEmaMinRr'),
  ema_signal_timeout_hours: document.getElementById('setEmaSignalTimeoutHours'),
  ema_adx_min: document.getElementById('setEmaAdxMin'),
  ema_min_gap_pct: document.getElementById('setEmaMinGapPct'),
  autotrade_leverage_bounce: document.getElementById('setAutotradeLevBounce'),
  autotrade_leverage_breakout: document.getElementById('setAutotradeLevBreakout'),
  autotrade_leverage_divergence: document.getElementById('setAutotradeLevDivergence'),
  autotrade_leverage_ema: document.getElementById('setAutotradeLevEma'),
  autotrade_leverage_session: document.getElementById('setAutotradeLevSession'),
  autotrade_leverage_session_ny: document.getElementById('setAutotradeLevSessionNy'),
};

function applySettingsToInputs(s) {
  for (const key in setInputs) {
    if (s[key] !== undefined) setInputs[key].checked = s[key];
  }
  for (const key in setValueInputs) {
    if (s[key] !== undefined) setValueInputs[key].value = s[key];
  }
  document.getElementById('setTelegramSub').textContent = s.telegram_configured
    ? 'токен найден'
    : 'токен не найден — уведомления не уйдут, даже если включено';
}

async function refreshGateApiStatus() {
  try {
    const s = await (await fetch('/api/credentials')).json();
    document.getElementById('setGateApiSub').textContent = s.gate_api_configured
      ? 'ключи сохранены'
      : 'ключи не заданы — реальные ордера невозможны, работает только dry-run';
  } catch (e) {}
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
  await refreshGateApiStatus();
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

for (const key in setValueInputs) {
  setValueInputs[key].onchange = async (e) => {
    const input = e.target;
    input.disabled = true;
    try {
      const res = await (await fetch('/api/settings', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({[key]: input.value}),
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

document.getElementById('saveGateApiBtn').onclick = async () => {
  const key = document.getElementById('setGateApiKey').value.trim();
  const secret = document.getElementById('setGateApiSecret').value.trim();
  if (!key || !secret) { alert('Заполни оба поля'); return; }
  try {
    const res = await (await fetch('/api/credentials', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({api_key: key, api_secret: secret}),
    })).json();
    if (res.ok) {
      document.getElementById('setGateApiKey').value = '';
      document.getElementById('setGateApiSecret').value = '';
      await refreshGateApiStatus();
    } else {
      alert('Не удалось сохранить ключи: ' + (res.error || ''));
    }
  } catch (err) {
    alert('Не удалось сохранить ключи: ' + err);
  }
};

document.getElementById('clearGateApiBtn').onclick = async () => {
  if (!confirm('Удалить сохранённые API-ключи Gate.io?')) return;
  try {
    await fetch('/api/credentials', {method: 'DELETE'});
    await refreshGateApiStatus();
  } catch (err) {
    alert('Не удалось удалить ключи: ' + err);
  }
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
    const entryIdx = findCandleIndex(candles, signalRow.time);
    if (entryIdx >= 0) {
      drawEntryMarker(ctx, entryIdx * slot + slot / 2, y(signalRow.entry), '#5aa8ff');
    }
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

function findCandleIndex(candles, targetTime) {
  if (targetTime === undefined || targetTime === null) return -1;
  let best = -1, bestDiff = Infinity;
  for (let i = 0; i < candles.length; i++) {
    const diff = Math.abs(candles[i].time - targetTime);
    if (diff < bestDiff) { bestDiff = diff; best = i; }
  }
  return best;
}

function drawEntryMarker(ctx, cx, cy, color) {
  ctx.save();
  ctx.fillStyle = color;
  ctx.strokeStyle = '#05070c';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
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
    const entryIdx = findCandleIndex(candles, row.time);
    if (entryIdx >= 0) {
      drawEntryMarker(ctx, entryIdx * slot + slot / 2, yP(row.entry), '#5aa8ff');
    }
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
    const entryIdx = findCandleIndex(candles, row.time);
    if (entryIdx >= 0) {
      drawEntryMarker(ctx, entryIdx * slot + slot / 2, yP(row.entry), '#5aa8ff');
    }
  }
}

// ---------------- Session chart modal ----------------
const sessionModal = document.getElementById('sessionModal');
document.getElementById('sessionCloseBtn').onclick = () => sessionModal.classList.remove('open');
let currentSessionData = null;

function openSessionNyChart(symbol, sessionOpen) {
  // Thin wrapper, not a duplicate — reuses the exact same modal/canvas
  // (openSessionChart/drawSessionChart) since this is pure chart-display
  // code with zero effect on trading behavior, unlike the detection/
  // execution logic above which IS fully duplicated per the user's
  // explicit request. The optional 3rd param only changes which API
  // endpoint gets fetched.
  return openSessionChart(symbol, sessionOpen, '/api/session_ny/chart');
}

async function openSessionChart(symbol, sessionOpen, endpoint = '/api/session/chart') {
  document.getElementById('sessionModalTitle').textContent = symbol;
  document.getElementById('sessionModalParams').textContent = 'загрузка...';
  sessionModal.classList.add('open');
  try {
    const data = await (await fetch(`${endpoint}/${symbol}?session_open=${sessionOpen}`)).json();
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
    const entryIdx = findCandleIndex(candles, sig.confirm_time);
    if (entryIdx >= 0) {
      drawEntryMarker(ctx, entryIdx * slot + slot / 2, yP(sig.entry), '#e8b93d');
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
    load_credentials()
    _load_alert_cfg()
    threading.Thread(target=_telegram_sender_worker, daemon=True).start()
    t = threading.Thread(target=scan_loop, daemon=True)
    t.start()
    threading.Thread(target=scalp_loop, daemon=True).start()
    threading.Thread(target=hourly_stats_loop, daemon=True).start()
    threading.Thread(target=session_loop, daemon=True).start()
    threading.Thread(target=session_live_loop, daemon=True).start()
    threading.Thread(target=session_ny_loop, daemon=True).start()
    threading.Thread(target=session_ny_live_loop, daemon=True).start()
    threading.Thread(target=xau_lg_backtest_loop, daemon=True).start()
    threading.Thread(target=xau_lg_live_loop, daemon=True).start()
    threading.Thread(target=reconcile_loop, daemon=True).start()
    threading.Thread(target=risk_autotune_loop, daemon=True).start()
    port = int(os.environ.get("VP_PORT", 8080))
    tg_status = "настроен" if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) else "не настроен"
    print(f"VP-POC Screener v{APP_VERSION} — http://127.0.0.1:{port} — Telegram: {tg_status}")
    app.run(host="0.0.0.0", port=port, threaded=True)
