# Changelog — vp-poc-screener

Full version history, moved out of `vp_poc_screener.py`'s own module
docstring (v0.99.122, per direct user request — "может вынести
информацию о новых версиях в отдельный файл а в основном оставить
инфу о его названии в гитхабе") since it had grown to ~10,470 lines
and was making the main file's own header unwieldy to scroll past.

The main file's docstring now just has the project name/description
and a pointer here. This file is the actual source of truth for every
version's own changes going forward.

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

v0.96.0 - EXPERIMENTAL: FT5, a port of freqtrade-strategies' Strategy005
         (github.com/freqtrade/freqtrade-strategies, author Gerald
         Lonlas), per direct user request after researching freqtrade
         and asking for "the full version... a separate tab with live
         signals and parameter re-optimization." That repo's own
         published backtest table showed Strategy005 as the most-traded
         strategy (180 trades) — but the backtest window was 2018-01-10
         to 2018-01-30, a 20-day stretch during the post-2017-top crash,
         and the repo's own README says outright that results depend
         heavily on pairs/timeframe/timerange and to run your own
         backtests. The specific hyperopt-tuned parameter values in the
         source (buy_rsi=26, buy_fishRsiNorma=5, etc.) are a near-
         textbook overfitting case — flagged to the user before
         building, same treatment as XAU_LG's Instagram source.
         Kept the STRUCTURE (which 6 indicators, which entry/exit
         conditions, the time-decaying ROI ladder, the fixed stoploss)
         but does NOT copy the specific parameter values — instead
         re-derives them via ft5_optimize_symbol()'s own grid search
         against this app's live Gate.io data, same "test on real data,
         don't trust the source's numbers" principle already applied to
         XAU_LG and (after v0.95.6's fix) Volume's own optimizer.
         Found and did NOT replicate a likely bug in the literal
         freqtrade source: one sell condition compares dataframe['fisher
         _rsi'] (range -1 to 1) against self.sell_fishRsiNorma (an
         IntParameter with range 1-100) — that comparison can only ever
         be true in a razor-thin edge case given fisher_rsi tops out at
         1 and the threshold's own minimum is 1, which looks like
         comparing against the wrong variable (fisher_rsi_norma, scaled
         0-100, matches the parameter's own range) rather than a
         deliberate design choice. FT5 uses fisher_rsi_norma there
         instead, documented as a deliberate deviation, not a silent
         difference.
         New pure-Python indicator helpers (no pandas/talib, matching
         this app's existing style): compute_sma, compute_macd,
         compute_stoch_fast (TA-Lib STOCHF-equivalent), compute_fisher_
         rsi (inverse Fisher transform of RSI), compute_sar (Wilder's
         Parabolic SAR) — kept as generic, reusable helpers alongside
         compute_rsi/compute_ema/compute_adx rather than FT5-prefixed,
         since none of them are specific to this one module. Every one
         individually verified behaviorally against synthetic candle
         data (sensible ranges: stoch/fisher_norma in 0-100, fisher in
         -1..1, SAR tracking price direction correctly) before being
         used in the strategy logic itself.
         ft5_run_backtest(): single no-lookahead walk-forward simulator
         — computes every indicator once, then walks forward checking
         entry (volume spike x4 avg, price below SMA40, stochastic
         cross, RSI, Fisher-RSI-norma) and, once "in a trade," exits in
         priority order (stoploss -10% first, then the ROI ladder
         [(1440min,1%),(80min,2%),(40min,3%),(20min,4%),(0min,5%)], then
         either sell-signal condition) — returns (closed_trades,
         open_position_at_window_end), the latter used by the live
         scanner to detect a fresh entry on the very last candle. Long-
         only, matching Strategy005's own design. Verified end-to-end on
         synthetic random-walk candles with occasional volume spikes —
         produced internally consistent trades (result matches pnl_pct
         sign in every case).
         ft5_optimize_symbol(): 36-combo grid search (buy_rsi x
         buy_fisher x sell_rsi — the params freqtrade's own hyperopt run
         varied most) selecting by mean pnl_pct per trade directly
         (FT5's trades are already %-based, not a fixed-RR system, so
         there's no separate winrate-vs-RR translation needed the way
         Volume's v0.95.6 fix required). Verified end-to-end via a
         monkeypatched get_candles_range call, confirmed it picks the
         same combo a manual grid search of the same data finds.
         Deliberately does NOT wire real autotrade or the shared paper
         simulator (AUTOTRADE_ENABLED_FT5 exists in settings, defaults
         off, currently a no-op) — unlike every other module here, FT5's
         real exit logic isn't a fixed (SL, TP) price pair, and execute_
         autotrade()/sim_execute_trade() are both built around exactly
         that shape. Approximating it with a single static TP (e.g. the
         largest ROI rung) would silently misrepresent FT5's actual exit
         behavior to real money or the simulator; faithfully trading it
         would need active position management (a loop sending a real
         close-order the moment ROI-ladder/signal/stoploss conditions
         are met), which hasn't been built. ft5_signals are
         informational only, with their own pnl_pct tracked via update_
         ft5_signal_outcomes() (re-runs the same deterministic walk-
         forward on an extended window using the signal's own recorded
         params — reproduces the same entry, then naturally continues
         to find the exit, rather than a separate resume-from-open-
         position code path).
         Full plumbing: ft5_build_universe() (same top-by-24h-volume
         shape as build_session_universe), ft5_backtest_loop()/ft5_live_
         loop() daemon threads, three API endpoints (/api/ft5/status,
         /signals, /api/reset/ft5), ft5_signals + ft5_symbol_overrides
         persisted through save_state()/load_state(), added to has_
         open_signal_any_module's lists, new "FT5 ⚠️" tab + panel
         (refreshFt5, with the same in-UI source-skepticism warning box
         XAU_LG has) + reset button, ft5_enabled/autotrade_ft5/autotrade
         _leverage_ft5 wired through the full settings system.
         Process note: while editing the JS template for this UI panel,
         a str_replace accidentally deleted the `async function
         refreshAutotradeBanner() {` declaration line — Python's own
         py_compile does NOT catch this class of error, since the
         entire HTML/JS template is just a string literal to the Python
         parser, syntax-invalid JS inside it doesn't fail Python
         compilation. Caught it by manually reviewing the diff, not by
         any automated check — which is itself the finding: added a new
         verification step to the release process from here on,
         extracting the embedded <script> block and running `node
         --check` against it (node is available in this environment),
         the same way py_compile + an actual runtime start already
         became standard practice after v0.95.1's NameError. Confirmed
         both clean for this release.

v0.96.1 - FT5: RR display and a chart modal, per direct user request
         ("можно тоже сделать графическое отображение сигналов? надо
         еще rr показывать как в других индикаторах").
         RR: FT5 has no single fixed reward target the way a fixed-TP
         module does (exits via stoploss OR a time-decaying ROI ladder
         OR either of two sell-signal conditions), so instead of
         inventing a fictional target RR, "rr" is the REALIZED R-
         multiple — pnl_pct divided by the fixed stoploss risk (FT5_
         STOPLOSS_PCT) — computed once a signal closes, in update_ft5_
         signal_outcomes(), and aggregated (avg + median) in compute_
         ft5_signal_stats(). Shown per-signal in the live signals table
         and as "RR ср. X (медиана Y)" in the panel header, same wording
         pattern EMA/Divergence/Session already use. The backtest/
         optimizer leaderboard shows an equivalent RR derived client-
         side from avg_pnl_pct/stoploss_pct (no backend change needed
         for that table, since it's a pure function of numbers already
         returned).
         Chart: new /api/ft5/chart/<symbol>?entry_time=... endpoint —
         re-runs ft5_run_backtest() on an appropriate window using that
         specific signal's own recorded params (same reuse-the-
         deterministic-detector principle update_ft5_signal_outcomes()
         already uses), returning candles + entry + the fixed stoploss
         price + exit info. New dedicated ft5Modal/openFt5Chart/
         drawFt5Chart — deliberately NOT reusing Session's chart modal
         the way Session NY did in v0.94.0: FT5's shape genuinely
         differs (no session range box, no single TP price to draw —
         entry/stoploss lines plus the actual realized exit point
         marker instead), so force-reusing drawSessionChart would need
         extra branching inside a function that's currently working
         cleanly for two other modules; a new ~90-line self-contained
         function was the safer choice, matching this app's existing
         reuse-when-truly-identical, duplicate-when-meaningfully-
         different judgment call (same reasoning already applied when
         XAU_LG/Session NY were built). Signal rows in the FT5 table are
         now clickable, opening the chart with entry/SL lines and a
         colored exit marker (green/red/amber for WIN/LOSS/TIMEOUT).
         Process note: while extracting the embedded <script> block for
         this release's mandatory JS syntax check (standard practice
         since v0.96.0's own process-note), the extraction helper itself
         produced a false SyntaxError — its naive regex search matched
         the FIRST literal "<script>" substring in the whole file, which
         turned out to be inside a changelog comment (this file's own
         v0.96.0 entry mentions "<script>" in backticks) rather than the
         real HTML template's script tag, and since there is only ONE
         real "</script>" closing tag in the entire file, the regex
         spanned from that comment all the way down to it, capturing
         ~450KB of unrelated Python source as "JS" and failing to parse
         it. Fixed by taking the LAST literal "<script>" occurrence
         instead (the real HTML template's script tag reliably comes
         last in the file) before searching forward for its closing tag
         — a lesson that the verification tooling itself needs the same
         scrutiny as the code it's checking, not blind trust that a
         failing check means the checked code is wrong.

v0.96.2 - added a Telegram close alert for FT5 signals, per direct user
         request ("добавь алерты в тг, когда открывать и после сигнала
         закрытия тоже"). The entry alert already existed (ft5_scan_
         symbol_live, since v0.96.0) — this adds the missing exit side.
         Notably, no OTHER module in this app currently sends a close
         alert either (checked before building this — every send_
         telegram() call site across Volume/Divergence/EMA/Session/
         XAU_LG only fires on entry), so this isn't copying an existing
         pattern, it's a new one, built carefully: update_ft5_signal_
         outcomes() collects every signal that transitions OPEN->CLOSED
         during that pass into a plain list (just_closed) while still
         holding state_lock for the mutation itself, then sends all the
         Telegram messages in a separate loop AFTER the lock is
         released — sending a network call while holding state_lock
         would block every other thread waiting on it (scan_loop, other
         modules' outcome-updaters, the settings API, etc.) for however
         long Telegram takes to respond or retry.
         Message includes result (WIN/LOSS/TIMEOUT with a matching
         icon), which of the three exit paths fired (stoploss/roi/
         signal/max_hold_timeout), exit price, realized pnl_pct, and
         the realized RR from v0.96.1 — verified the exact message
         formatting behaviorally (both a WIN and a LOSS case) rather
         than just reading the f-string and assuming it's right.

v0.96.3 - fixed a real gap, per a direct user question ("галочка
         уведомлений точно есть в настройках?"): TELEGRAM_ALERTS_
         SESSION_NY, TELEGRAM_ALERTS_XAU_LG, and TELEGRAM_ALERTS_FT5
         all existed as constants and were correctly checked inside
         send_telegram()'s category filter, but none of the three were
         ever wired into SETTINGS_KEYS/get_settings/apply_settings, and
         none had an actual checkbox in the settings UI — meaning they
         were stuck at their env-var default (on) with no way to turn
         them off short of editing code and restarting. This wasn't
         just an FT5 gap: checked Session NY and XAU_LG too rather than
         fixing only what was asked about, and both had the identical
         hole. Notably, this contradicts what their own changelog
         entries claimed at the time — v0.94.0 said Session NY got "its
         own TELEGRAM_ALERTS_SESSION_NY toggle" and v0.95.0 said the
         same for XAU_LG's category — both entries described the
         constant-plus-filter-check as a complete toggle when the
         settings/UI wiring was actually missing; worth naming plainly
         rather than letting it pass as a minor detail.
         Fixed for all three at once, matching Session's own already-
         complete pattern exactly: added telegram_alerts_session_ny/
         xau_lg/ft5 to SETTINGS_KEYS, get_settings(), apply_settings()
         (global declarations + handlers), and three new checkbox rows
         in the Telegram settings group (setTelegramSessionNy/XauLg/
         Ft5, the latter two carrying their modules' own ⚠️ marker),
         wired into the shared setInputs object that already handles
         loading/saving every other toggle generically.

v0.96.4 - clarified FT5's RR display, per direct user correction ("Про
         re когда я говорил я имел ввиду соотношение тейка и стопа" —
         they meant the classic take:stop ratio EMA/Divergence/Session
         show, not the realized-outcome RR v0.96.1 built. Both concepts
         are legitimately called "RR" and the earlier build picked the
         wrong one without checking.
         The honest complication, explained in the UI rather than
         picking one number and hiding the nuance: FT5's stoploss IS a
         single fixed price (10%), but its "take profit" isn't — it's a
         time-decaying ladder (5% right after entry, down to 1% after
         24h) plus two signal-based exits with no price target at all.
         So there's no single planned take:stop ratio the way EMA's
         fixed TP_PCT/SL gives one. Added the closest honest equivalent:
         each ROI ladder rung divided by the fixed stoploss gives its
         own ratio (0.1 at the low end up to 0.5 right after entry),
         computed and shown as a range ("план. тейк:стоп (лесенка)
         0.10–0.50") in the panel header — pure client-side arithmetic
         from data the API already returns (config.roi_ladder, config.
         stoploss_pct), no backend change needed. Verified the exact
         computation behaviorally against the real ladder values (node
         -e reproducing the same math), not just read as correct.
         Kept the realized-RR display from v0.96.1 alongside it (now
         labeled "реализ. RR" in the header and "RR (факт)" in both
         table column headers) rather than replacing it — it answers a
         different, still-useful question (what actually happened),
         and removing it would lose real information the user didn't
         ask to lose.

v0.97.0 - removed the routine TIMEOUT close from every module that had
         one, per direct user request after a screenshot showed EMA's
         live signals table dominated by TIMEOUT results — several with
         MFE already well past 1.0 (favorable movement that had already
         exceeded what a win would need), cut off by the clock rather
         than ever actually reaching TP or SL. A signal now waits as
         long as it takes to hit either one, never expiring into an
         ambiguous third outcome.
         Found and removed in four places, not just EMA: Volume and
         Divergence shared SIGNAL_TIMEOUT_SEC (6h), EMA had its own
         separate EMA_SIGNAL_TIMEOUT_SEC (12h, widened from the shared
         default earlier this session for the same underlying reason),
         and XAU_LG had an inline 24h cutoff (`24 * 3600`, not a named
         constant — found on a second, more careful pass specifically
         because the first search for "every module's timeout constant"
         only caught named constants and missed this one; worth naming
         plainly that the first pass was incomplete). Session/Session
         NY/Scalp were checked and confirmed to have no equivalent live
         routine-timeout (Scalp's was already removed in the v0.87 era,
         Session's TIMEOUT concept only exists inside the backtest
         walk-forward window, not for live open signals).
         Cleaned up EMA_SIGNAL_TIMEOUT_SEC's full settings-system
         footprint rather than leaving a dead setting behind that would
         silently do nothing: removed from SETTINGS_KEYS, get_settings(),
         apply_settings() (global declaration + handler), api_ema_
         status()'s config block, the "↳ EMA тайм-аут (ч)" settings row,
         and its setInputs binding — both now-orphaned constants (SIGNAL_
         TIMEOUT_SEC, EMA_SIGNAL_TIMEOUT_SEC) deleted outright rather
         than left defined-but-unused.
         FT5_MAX_HOLD_SEC (7 days) deliberately left untouched — asked
         the user directly rather than assuming, since it's structurally
         different from the other four: a genuine safety backstop for
         the case where neither the ROI ladder, sell-signal, nor
         stoploss ever resolves a position (which the ROI ladder's own
         design should make very unlikely, but isn't literally
         impossible on a coin trading sideways in a narrow band
         indefinitely), not a routine early cutoff of an otherwise-
         healthy trade the way the other four were. Confirmed to keep it
         as-is.
         Verified with py_compile, an actual runtime start, pyflakes
         (caught and removed one now-genuinely-unused local variable in
         update_xau_lg_signal_outcomes left over from the timeout
         removal), and node --check on the extracted <script> block —
         all clean.

v0.97.1 - split FT5's single universe into an analysis pool and a
         live-scan subset, per direct user request ("используем 200
         монет для анализа, но в сигналах топ 5"). Previously
         FT5_UNIVERSE_SIZE (default 40) controlled both what got
         backtested/optimized AND what got live-scanned — one number
         for two different jobs. Now FT5_UNIVERSE_SIZE (raised to 200)
         controls only the analysis pool, and a new FT5_LIVE_TOP_N
         (default 5) controls how many of those 200 — ranked by the
         optimizer's own avg_pnl_pct, same metric/sort key api_ft5_
         status()'s "top" display already used — actually get scanned
         for live signals. Analyze broadly, trade narrowly on the best
         performers only.
         ft5_backtest_loop() computes this ranking once per full pass
         (after all 200 symbols are optimized) and stores it as STATE[
         "ft5_live_universe"]; ft5_live_loop() now reads that instead of
         the full STATE["ft5_universe"]. Symbols with no result, an
         error, or too few backtested trades sort to the bottom
         (avg_pnl_pct treated as worst-case) and naturally never make
         the live cut — verified this behaviorally with a synthetic
         overrides dict mixing valid results, None, and error entries,
         not just by reading the sort key. Neither ft5_universe nor
         ft5_live_universe is persisted across restarts (matching the
         pre-existing choice not to persist ft5_universe) — both rebuild
         within the first backtest cycle after startup regardless.
         /api/ft5/status now returns live_universe and live_top_n
         alongside the existing universe_size; the panel header shows
         both explicitly ("анализ: N/200 монет · живой скан: топ-5
         (SYM1, SYM2, ...)") rather than one ambiguous count.
         Scale note, flagged rather than silently absorbed: 200 symbols
         x 36 grid-search combos is 7200 backtest runs per daily cycle,
         5x the work the previous 40-symbol default did — should still
         comfortably finish within FT5_REFRESH_SEC's 24h cadence, but
         worth knowing if the "последний перебор параметров" timestamp
         starts lagging noticeably behind schedule.

v0.97.2 - added a risk-autotune reset button, per direct user question
         about whether one was worth having given the tuning rules are
         already bidirectional (they are — confirmed by re-reading each
         rule's step logic before answering). Argued for building it
         anyway on a concrete precedent already in this session: v0.95.3/
         v0.95.4/v0.95.6 each fixed a tuning FORMULA after it had
         already computed and persisted bad values with the old, buggy
         one — without a reset, those stale values only limp back
         toward correct over several more cooldown-gated passes (6-24h
         apart) instead of restarting clean right after a fix.
         New /api/reset/risk_autotune: resets every parameter risk_
         autotune_pass() touches (ema_min_rr, ema_sl_atr_mult, ema_
         invert_signals, ema_tp_pct, div_min_rr, div_sl_atr_mult, div_
         invert_signals, div_tp_pct, scalp_min_rr, scalp_sl_buffer_mult,
         session_invert_signals) to its own code-level default — the
         literal fallback value in that constant's own os.environ.get()
         call, hardcoded into the endpoint since the live global may
         already be tuned away from it, which is exactly the state this
         button undoes — then clears STATE["risk_autotune_log"] and
         every cooldown timestamp in STATE["risk_autotune_last_change"]
         so the next pass evaluates fresh. New "Сбросить авто-тюнинг"
         button in the header, wired via the existing wireResetButton
         confirm-dialog pattern.
         Process note, found while wiring this: repeated the EXACT same
         class of mistake as v0.96.0's refreshAutotradeBanner incident —
         a str_replace's old_str included the next function's `@app.
         route(...)`/`def api_reset_ema():` lines for uniqueness, but
         the new_str dropped them, decapitating that function. Caught
         it manually again rather than by an automated check, which
         prompted actually building the check this time instead of
         just noting the near-miss: a small script scanning the whole
         file for every `@app.route(...)` and confirming a `def` line
         follows within a couple lines, run once to confirm this
         specific incident was fully fixed and nothing else in the file
         had the same problem (it hadn't, elsewhere). Also surfaced,
         independently, while auditing: resetFt5Btn (added in v0.96.0)
         had a button in the HTML/CSS but was NEVER wired to wireReset
         Button — clicking "Очистить FT5" has done nothing since it was
         added. Fixed alongside the new button rather than left for
         later, since it was found in the course of this same work.

v0.97.3 - FT5_LIVE_TOP_N raised 5 -> 10, per direct follow-up request.
         No other logic changed — same ranking (by the optimizer's own
         avg_pnl_pct), same 200-symbol analysis pool, just a wider
         live-scan slice off the top of it.

v0.98.0 - VGI: full integration of the user's own separate repo
         (github.com/mambaleylo/vgi-trader), per direct request —
         "возьми его логику и интегрируй нам новой вкладкой со всеми
         плюшками, уведомления, автоторговлю, графическое отображение".
         Source is a Python re-implementation of the TradingView
         indicator "Volume Gaps & Imbalances (Zeiierman)" (CC BY-NC-SA
         4.0 — the original Pine isn't reproduced, this is a further
         independent re-port of the author's own already-independent
         port): builds a row-based volume profile over a rolling
         lookback window, finds zero-volume "gap" zones (merged runs of
         empty adjacent rows — "price magnets"), and per-section delta
         ((Bull-Bear)/Total*100) for local bias. Direction comes from
         local delta first, falls back to the nearest zone if delta is
         neutral, and skips entirely if delta and the nearest zone
         disagree (source's own "too much noise" reasoning). TP = far
         edge of the nearest zone; SL = reward/min_rr, guaranteeing
         RR >= min_rr by construction (stop sized FROM the target, not
         measured independently).
         Ported to pure Python (vgi_build_profile/vgi_section_at_price/
         vgi_nearest_zone/vgi_evaluate_signal) — no numpy, unlike the
         source, staying consistent with this whole app's stdlib-only
         style rather than adding a dependency for one module on a
         phone/Termux setup. Verified behaviorally against synthetic
         candle data before building anything on top: zones/sections
         computed correctly, RR exactly matched the configured minimum.
         Found and fixed the symbol-selection bug the user reported
         ("сейчас тупо по алфавиту первые 40 чтоли берет"): the source's
         own resolve_symbols() (trader.py) sorts by volume_24h_quote
         from Gate.io's /contracts endpoint, which this app already
         learned (building ft5_build_universe/build_session_universe)
         is frequently empty there — an always-zero sort key makes
         Python's stable sort a no-op, silently preserving whatever
         order /contracts happened to return (plausibly close to
         alphabetical/ID order, matching exactly what was observed).
         vgi_build_universe() uses get_tickers() with the same fallback
         field chain already proven correct for FT5/Session instead.
         Unlike FT5, VGI genuinely has ONE fixed (SL, TP) pair per
         signal — so real autotrade and the shared paper simulator ARE
         wired (execute_autotrade()/sim_execute_trade(), both called
         from vgi_scan_symbol_live() when AUTOTRADE_ENABLED_VGI is on,
         off by default same as every other module here), with a real
         settings-UI leverage/toggle row (unlike FT5/XAU_LG, which
         deliberately left autotrade UI-less as a scope decision — VGI
         gets the full row since the user asked for autotrade as a
         first-class feature and the fixed-TP/SL shape makes it honest
         to offer).
         vgi_run_backtest(): walk-forward backtest the source repo
         doesn't have at all (it's a live-only "online" screener) — built
         anyway per this session's standing discipline of testing before
         trusting a source's own design. At each closed bar, rebuilds
         the profile using ONLY candles up to that bar (no lookahead),
         evaluates a signal, and tracks forward for TP/SL touch, one
         position at a time. Verified on synthetic random-walk data:
         132 trades, all internally consistent, win rate slightly below
         the RR=3 breakeven (25%) — exactly what a real edge-free random
         walk should produce, not a red flag.
         Telegram alerts on both open (vgi_scan_symbol_live) and close
         (update_vgi_signal_outcomes, same lock-then-send-after-release
         pattern FT5's v0.96.2 established, to avoid holding state_lock
         during network I/O), each with their own settings toggle.
         Chart modal: own dedicated modal (vgiModal/openVgiChart/
         drawVgiChart) rather than reusing FT5's or Session's — VGI's
         shape (fixed entry/sl/tp, no ROI ladder, no session range box)
         doesn't match either closely enough to force a clean reuse, so
         a new ~90-line self-contained function was the safer choice,
         same judgment call already applied for FT5's own chart.
         Full plumbing otherwise matches the established per-module
         shape: STATE persistence through save_state()/load_state(),
         has_open_signal_any_module() cross-module guard, sim-trade
         relink module_lists entry (VGI participates in the shared
         simulator, unlike FT5), daemon threads (vgi_backtest_loop/
         vgi_live_loop), three-plus-one API endpoints (/api/vgi/status,
         /signals, /chart/<symbol>, /api/reset/vgi), new "VGI" tab (no
         warning-color styling, unlike XAU_LG/FT5 — this is the user's
         own carefully-reasoned indicator with a real RR guarantee, not
         a shaky external source, though the panel does note real
         performance is still unverified until backtest numbers exist).
         Process discipline notes: while inserting the core math
         functions, a str_replace's old_str matched only the first line
         of ft5_run_backtest()'s multi-line signature, and the new_str
         dropped the rest — decapitating it again, same class of mistake
         as v0.96.0's refreshAutotradeBanner and v0.97.2's api_reset_ema
         incidents. This time py_compile caught it immediately (genuine
         Python syntax breakage, unlike the JS-in-string case), fixed in
         one step. Ran the established route/def integrity check and
         the mutable-global-as-default-parameter check across the whole
         file (not just new code) before pushing — both clean.

v0.98.1 - graphical chart display for Scalp signals, per the second half
         of the same request that produced VGI. Scalp's own signal
         shape (fixed entry/target_price/sl_price) is structurally
         identical to VGI's (v0.98.0) — rather than duplicating ~90
         lines of canvas drawing code a third time, openVgiChart()
         gained an optional (endpoint, extraQuery) pair (default '/api/
         vgi/chart', '' — existing 2-arg calls unaffected) and a thin
         openScalpChart(symbol, interval, sigTime) wrapper points it at
         a new /api/scalp/chart/<symbol> endpoint instead. Same reuse-
         when-genuinely-identical judgment call already applied to
         Session NY's chart in v0.94.0 and just reasoned through again
         for VGI itself.
         New endpoint returns the same response shape api_vgi_chart
         does (entry/sl/tp/rr/result/exit/candles) so the shared modal
         needs no branching — interval is a required extra query param
         (unlike VGI/FT5, Scalp runs multiple timeframes per symbol at
         once via SCALP_INTERVALS, so symbol+time alone doesn't uniquely
         identify a signal). rr computed as target_pct/sl_pct — verified
         against the exact CYS_USDT example from earlier in this session
         (RR 0.415), not just trusted as an obviously-correct formula.
         Signal rows in the Scalp panel are now clickable — used a
         distinct data-signal-* attribute set (data-signal-symbol/
         -interval/-time) rather than reusing data-symbol, since the
         panel's OTHER table (per-symbol recommendations) already uses
         data-symbol for its own click handler (opens openScalpDetail);
         reusing the same attribute would have silently double-wired or
         misrouted clicks on one of the two tables. Verified the actual
         resulting URL template resolves correctly (node -e), not just
         read as correct.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, and the route/
         def integrity check — all clean.

v0.98.2 - fixed a real complaint about VGI, per direct user report
         ("сразу стоп выбивает") and a request to verify against the
         actual original Pine indicator (which the user then uploaded).
         Confirmed from the real Pine source: it's a pure visual
         indicator (indicator(), not strategy() — no strategy.entry,
         no alert, no stop-loss concept anywhere in it at all). Every
         piece of trading logic (direction, TP/SL, leverage, position
         sizing) lives entirely in the user's own vgi-trader repo
         (signal_engine.py/trader.py), layered on top of the visual
         indicator — confirmed this is explicitly how the repo's own
         README describes it ("min_zone_rows/delta_threshold_pct/
         max_zone_distance_pct не из оригинального индикатора").
         Also cleared up a mix-up while re-verifying trader.py/config.
         example.json directly rather than from memory: leverage is 5
         in the source (matches this app's own default exactly) — the
         "10" the user recalled is risk_usdt: 10.0, a separate dollar-
         risk-per-trade sizing field, not leverage at all.
         Root cause of the immediate-stopout complaint, confirmed
         against the source's own formula (which this port already
         matches exactly): SL = reward/min_rr sizes the stop from an
         UNRELATED quantity — distance to the nearest zero-volume zone
         — not actual price volatility. When that zone happens to sit
         close to price, the resulting stop can end up tighter than
         ordinary 1h candle noise for that symbol, so it gets hit by
         normal wicks rather than a genuine invalidation. This is a
         real property of the source's own design, not a fidelity gap
         introduced by porting it.
         Also surfaced, while re-reading trader.py's size_from_risk():
         the source sizes POSITION SIZE from a fixed dollar risk (qty =
         risk_usdt / |entry-sl| — tighter stop means MORE contracts, to
         hold dollar risk constant), but this app's VGI integration
         currently uses the shared AUTOTRADE_SIZE_MODE/SIZE_VALUE
         mechanism instead, same as every other module — meaning a
         tight stop here does NOT get a correspondingly smaller/larger
         position the way the source's own sizing would. Flagged
         directly, left unchanged this round per explicit user
         instruction (keep the app's shared sizing mechanism), not
         silently absorbed.
         Fix chosen after presenting the tradeoff directly and getting
         a clear answer: added VGI_MIN_SL_DISTANCE_PCT (default 0.5%)
         — vgi_evaluate_signal() gained an optional min_sl_distance_pct
         parameter (resolves to the live global at call time if not
         given, avoiding the exact v0.95.7-class stale-default bug this
         session already found and fixed elsewhere) and now rejects a
         signal outright if its computed SL distance is tighter than
         this floor, rather than letting it fire with an unrealistically
         tight stop. Doesn't touch TP or the RR math at all — a
         rejected signal is simply never taken, not resized. Verified
         behaviorally with two synthetic profiles (a close zone
         producing a sub-threshold stop, correctly rejected; a farther
         zone producing a ~2.3% stop, correctly passed through with
         RR still exactly 3.0) rather than trusting the logic by
         inspection alone. Exposed in /api/vgi/status's config block
         and in the panel's own header text, explaining directly why
         some setups won't fire.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, and both the
         route/def integrity and stale-default-parameter checks across
         the whole file — all clean.

v0.98.3 - fixed FT5's top-symbol selection to weigh sample frequency, per
         direct user report ("по ft5 ни одного сигнала за вечер и
         ночь"). Diagnosed rather than guessed: FT5's entry conditions
         (4x volume spike + price below SMA40 + RSI/Fisher thresholds
         all at once) are genuinely rare — with the bare FT5_MIN_
         BACKTEST_TRADES=5 floor, ranking by raw avg_pnl_pct let a
         combo with a single lucky trade in a tiny sample outrank a
         combo firing far more often at a slightly lower average. The
         "top 10" that actually got live-scanned could therefore be
         structurally rare setups rather than reliably active ones —
         illustrated the math directly (n=5 trades over 30 days ≈ once
         every 6 days per symbol; pooled across 10 symbols, a single
         evening+night having zero signals is well within normal
         variance even for a healthy setup, let alone a rare-by-
         selection one).
         Fix (user picked this option directly over two alternatives —
         raising the min-trades floor, or just surfacing n in the UI
         unchanged): new ft5_ranking_score(avg_pnl_pct, n, k) — score =
         total_pnl/(n+K) = avg_pnl_pct * n/(n+K), a Bayesian/Wilson-
         style shrinkage that discounts the average toward zero at
         small n and converges to the raw average as n grows, so a
         combo needs both a real edge AND enough trades behind it to
         rank highly. New FT5_RANK_SHRINKAGE_K (default 15) controls
         how aggressively small samples get discounted; resolved from
         the live global at call time (default parameter is None, not
         a frozen literal), avoiding the exact v0.95.7-class stale-
         default bug this session already found and fixed elsewhere.
         Verified the formula's behavior with worked examples before
         wiring it in (n=30/avg=0.35% correctly outscores n=5/avg=0.5%;
         a genuinely strong n=5/avg=1.0% outlier can still win, so this
         isn't a blunt "frequency always wins" rule).
         Applied consistently everywhere FT5 picks a "best" option:
         ft5_optimize_symbol()'s within-symbol combo selection (36
         combos), ft5_backtest_loop()'s cross-symbol live_universe
         selection (which of the 200 analyzed symbols become the live-
         scanned FT5_LIVE_TOP_N), and api_ft5_status()'s own display
         ranking (so what the user sees ranked matches what actually
         got selected for live scanning, rather than showing one order
         while a different one determined the real cut). UI: leaderboard
         table gained a Score column and a green-dot marker on symbols
         currently in the live pool, with the sorting explanation
         rewritten to say why (small lucky samples no longer win).
         Verified end-to-end on synthetic candle data: computed all 21
         valid grid combos' raw average AND score independently, found
         a genuine divergence beyond just the #1 spot (a combo with
         n=17 at nearly the same average correctly outranks one with
         n=9 that used to rank higher under raw-average sorting), then
         confirmed ft5_optimize_symbol() actually selects the score-
         ranked winner in practice — not just read the code and assumed
         it was correct.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, and both the
         route/def integrity and stale-default-parameter checks — all
         clean.

v0.98.4 - fixed VGI's backtest loop silently stalling, diagnosed live
         from a direct user report ("Vgi молчит") plus two screenshots
         rather than guessed at. First screenshot showed universe_size
         still "?" (STATE["vgi_universe"] never populated) with zero
         signals and "бэктест ещё не готов" — ruled out the obvious
         guesses first: VGI's enable toggle was confirmed ON, and
         vgi_run_backtest() itself was measured at 0.02s for a full
         720-candle (30-day, 1h) walk-forward, so compute speed wasn't
         it. Second screenshot's error panel showed exactly one entry:
         a "Read timed out" on api.gateio.ws from an unrelated function
         (reconcile_positions_and_orders) — independent evidence Gate.io
         was responding slowly for this user right then. That pointed
         at the real bug: vgi_backtest_loop() fetched each universe
         symbol's candles in a plain sequential `for symbol in universe`
         loop, unlike the live scan loops (which already use a
         ThreadPoolExecutor per symbol) — under normal conditions this
         was merely slower than it needed to be, but under a live
         network slowdown, one symbol's fetch retrying/stalling blocks
         every symbol queued behind it, so total wall-clock time scales
         with the SUM of fetch times rather than the worst one — easily
         explaining an empty universe that never even got far enough to
         log a real error.
         Fixed by extracting _vgi_backtest_one_symbol() (fetch + backtest
         + summarize for one symbol, exceptions caught internally so one
         bad symbol can't take down the batch) and running it through a
         ThreadPoolExecutor across the whole universe, matching the
         concurrency pattern already used elsewhere in this app rather
         than inventing a new one. Verified behaviorally, not just read
         as correct: mocked get_candles_range with one deliberately slow
         ("SLOW_USDT", +0.3s) symbol among five, confirmed total wall-
         clock time matched the single slowest fetch (~0.37s) rather
         than the sum of all five (~0.55s), and that all five symbols'
         results still came back correctly.
         Noted, not fixed this round: ft5_backtest_loop() has the
         identical sequential-fetch structure (`for symbol in universe:
         ft5_optimize_symbol(symbol)`), across up to 200 symbols by
         default — an even larger version of the same vulnerability.
         Flagged directly rather than silently left inconsistent; not
         changed here since the live report was specifically about VGI
         and FT5 wasn't reported as currently broken.
         Verified with py_compile, an actual runtime start, and pyflakes
         — clean. (Session's own RR/SL-mult autotune work, requested in
         the same conversation, was paused mid-way to handle this
         time-sensitive live issue first — continues next.)

v0.98.5 - Session's RR is now managed by risk-autotune end to end, per
         direct user request ("Надо чтобы этим управлял автотюнинг")
         after establishing that SESSION_REVERSE_RR was a permanently
         hardcoded "2" (the tp = entry +/- risk*2 formula, literal in
         the code) and SESSION_SL_MULT couldn't be overshoot-tuned like
         EMA/Divergence/Scalp's own SL-width knobs because Session had
         no MFE/MAE tracking on its signals at all — a real, previously
         acknowledged gap, not silently worked around.
         Added MFE/MAE tracking to Session (update_session_signal_
         outcomes(), mirroring update_divergence_outcomes()'s live-
         tracking shape but without the post-close continued-tracking
         window, since risk_autotune_pass() only ever needs the at-
         close values) — R = abs(entry-sl), the actual risk used at
         signal creation, which correctly covers both non-inverted
         trades (sweep-based stop) and inverted trades (risk*SESSION_SL_
         MULT-widened stop) since sl was already set correctly per-mode
         when the record was created. compute_session_signal_stats()
         gained the same mfe_r_wins_at_close/mae_r_losses_at_close
         aggregates (avg/median/p25/p75) EMA/Divergence/Scalp already
         expose.
         New SESSION_REVERSE_RR constant (default 2.0) replaces the
         literal "2" in both reverse-mode TP formulas (LONG and SHORT
         branches), wired through the full settings system (SETTINGS_
         KEYS/get_settings/apply_settings/setter) same as SESSION_SL_
         MULT already was.
         _risk_autotune_tp_extend() (previously EMA/DIV-only, %-of-price
         scale) gained an optional bounds parameter so Session could
         reuse it directly for an RR-scale value instead of duplicating
         the function — passing SESSION_REVERSE_RR as both current_tp_
         pct and current_rr works cleanly since Session's target is
         already natively expressed as a pure R-multiple, no %-of-price
         translation needed the way EMA/DIV require. New RISK_AUTOTUNE_
         SESSION_RR_BOUNDS (0.5-5.0), since a valid RR range and a valid
         %-of-price range (0.3%-5%) share nothing but both being "some
         positive number." Verified behaviorally, not just read as
         correct: called the rule with win_mfe_r=3.0 against current
         RR=2.0, confirmed it moved to 2.2 (the bounded per-pass step,
         not jumping straight to 3.0) using the RR-scale bounds rather
         than the %-scale ones that would have clamped it to ~0.05.
         risk_autotune_pass()'s Session block rewritten to call compute_
         session_signal_stats() directly (matching EMA's own structure)
         instead of the old _session_reverse_stats() helper (deleted —
         it only had this one call site, and its whole reason to exist,
         "no MFE/MAE data," no longer applies). All three rules — reverse
         flag, SL-mult, RR-extend — only run while SESSION_INVERT_
         SIGNALS is on, since only the inverted sizing is risk/RR-based;
         noted the same caveat the codebase already accepts elsewhere in
         this system: records don't distinguish which mode a closed
         trade opened under, so this reacts to recent aggregate stats
         under the assumption the reverse flag hasn't flipped recently
         (its own 24h cooldown usually makes that true), not a per-trade
         exact reconstruction.
         api_reset_risk_autotune() now also resets SESSION_SL_MULT/
         SESSION_REVERSE_RR to their code defaults, matching every other
         tuned parameter. api_session_status()'s config gained sl_mult/
         reverse_rr; the panel header's hardcoded "РЕВЕРС ВКЛЮЧЁН (RR 2)"
         text now shows the real live values, and a new MFE/MAE display
         block (matching Scalp's own) was added to the Session panel.
         Also fixed the same hardcoded "(RR 2)" text in the settings
         modal's Session row (Session NY's own row correctly keeps it —
         that module wasn't touched this round, still genuinely fixed
         at 2, noted explicitly as a known, currently out-of-scope
         parallel gap rather than silently left inconsistent).
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, and both the
         route/def integrity and stale-default-parameter checks — all
         clean.

v0.98.6 - CRITICAL FIX: outcome-tracking across seven functions in five
         modules was including the entry candle's OWN high/low in the
         SL/TP check, even though entry happens at that candle's CLOSE
         — meaning a wick that formed before we were even in the trade
         could falsely trigger an immediate "LOSS". Found from a direct
         user report with a VGI chart screenshot (BMT_USDT SHORT, LOSS
         @ SL) and a precise diagnosis of why it looked wrong: "стоп не
         зайдет, разве что на свече входа, но мы то входим на закрытии."
         Confirmed by reading the code: every affected function built
         its forward-looking window as `c["time"] >= sig["time"]` (or
         `>= sig["confirm_time"]`) — since sig["time"]/confirm_time IS
         the entry candle's own timestamp (set at signal creation from
         that same candle's close), >= includes that candle in the SL/
         TP scan. Checked every module systematically rather than just
         fixing the one reported: EMA (update_ema_outcomes), Divergence
         (update_divergence_outcomes), and Volume (update_signal_
         outcomes) already used strict > and were correct; Session,
         Session NY, Scalp, XAU_LG, and VGI all had the bug.
         Fixed all seven: track_session_outcome() and track_session_ny_
         outcome() (both used for BACKTESTING — meaning this wasn't
         just a live-tracking bug for Session/Session NY, the backtest-
         derived win rates users have been looking at all session were
         also affected, always in the pessimistic direction since it
         could only ever manufacture false LOSSes, never false WINs,
         given SL is checked before TP on any bar), update_session_
         signal_outcomes(), update_session_ny_signal_outcomes(),
         update_scalp_signal_outcomes(), update_xau_lg_signal_
         outcomes(), and update_vgi_signal_outcomes() (the one from the
         live report). VGI's own vgi_run_backtest() was independently
         verified NOT to have this bug — its position-tracking control
         flow structurally never checks the entry bar's own high/low
         (the position only exists starting the NEXT loop iteration),
         so VGI's backtest numbers were always honest; only its LIVE
         tracker had the problem.
         Process note, stated plainly: while applying this fix, two
         separate str_replace edits (Session's live tracker, then
         Scalp's) each accidentally dropped 3-5 lines of surrounding
         code the same way v0.96.0/v0.97.2/v0.98.0's incidents did —
         both caught this time by manually re-reading the full edited
         function immediately after each change, not by py_compile or
         pyflakes (verified directly: pyflakes does NOT catch a
         variable assigned only inside one conditional branch and read
         outside it, confirmed with a minimal reproduction before
         relying on that conclusion). Every one of the seven edited
         functions was individually re-read in full after editing, not
         just compile-checked, specifically because of this repeated
         failure mode.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, the route/def
         integrity check, and the stale-default-parameter check — all
         clean. Confirmed zero remaining `>= sig[` occurrences and ten
         correct `> sig[` occurrences across the file.

v0.98.7 - fixed a real flaw in FT5's ranking formula, per direct user
         report with a concrete counterexample from the live leaderboard:
         UB_USDT (21W/7L, avg +1.353%) outranked AKE_USDT (13W/2L, avg
         +1.488%) — a combo with MORE losses AND a lower average beat
         one with fewer losses and a higher average, purely because
         UB's larger n gave it a smaller size-based discount under the
         v0.98.3 formula (avg_pnl_pct * n/(n+K)). That formula rewarded
         sample size unconditionally but never separately weighed how
         much of that sample was actual losses — "варианты с бо́льшим
         количеством стопов должны меньше веса иметь."
         Replaced with a proper lower-confidence-bound on the mean:
         ft5_ranking_score(pnls) now computes score = mean - Z*stderr
         (stderr = sample_std/sqrt(n)) directly from the list of per-
         trade pnl_pct values, instead of just avg+n. This fixes the
         reported issue as a natural CONSEQUENCE of the statistics,
         not a bolted-on second penalty: frequent large losses mixed
         with modest wins directly inflate the variance (std), which
         inflates stderr, which lowers the score — the same mechanism
         that already discounted small samples (small n also inflates
         stderr) now also discounts high-variance ones, with one
         formula and one constant (FT5_RANK_Z, default 1.0 — the "one-
         standard-error rule", replacing FT5_RANK_SHRINKAGE_K) instead
         of needing a second, separately-tuned loss-count penalty.
         Verified twice, not just derived and trusted: first on
         reconstructed synthetic data matching the real screenshot
         numbers (confirmed AKE's profile scores higher, reversing the
         old ranking exactly as reported), then again by calling the
         actual ft5_ranking_score() function as it now exists in the
         file (not a standalone draft) with the same reconstructed
         data, confirming the real code produces the same reversal.
         Updated both docstrings (ft5_optimize_symbol, the ranking
         comment in ft5_backtest_loop) and the leaderboard's own UI
         hint text (visible in the reported screenshot, "урезанному под
         размер выборки") to describe the new formula honestly rather
         than leaving stale text that no longer matched what the code
         does.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, and both the
         route/def integrity and stale-default-parameter checks — all
         clean.

v0.98.8 - two more real flaws in FT5's ranking formula, each found from
         a direct user report with a concrete leaderboard example, each
         fixed and behaviorally verified in sequence — and the full
         combination re-verified against every prior counterexample at
         the end, since fixing the second one initially reintroduced
         the first.
         (1) A second concurrent finding, unrelated to ranking: eight
         outcome-tracking functions across five modules (Session,
         Session NY, Divergence, EMA, Scalp, Volume, XAU_LG, VGI) were
         checking SL/TP against the STILL-FORMING, not-yet-closed
         candle — fetch_candles_concurrent() doesn't filter it out
         (confirmed by reading its implementation), and unlike every
         signal-DETECTION function in this app (which all correctly
         drop it), only FT5's own outcome tracker happened to already
         filter correctly. Found from a live VGI report: a SHORT on
         HYPE_USDT hit LOSS just 5 minutes after entry despite VGI
         running on a 1h timeframe — mechanically impossible from a
         genuinely closed candle. Fixed all seven missing spots with
         the same `candles = [c for c in candles if c["time"] +
         interval_sec <= now]` filter every live scanner already uses,
         each re-read in full after editing (not just compile-checked)
         given this session's repeated line-dropping mistakes. Verified
         behaviorally with a synthetic still-forming candle, confirmed
         it gets excluded.
         (2) FT5's ranking formula (v0.98.7's lower-confidence-bound)
         had two more real gaps, per a direct leaderboard screenshot:
         DEXE_USDT (n=5, 5W/0L, avg +2.957%) outranked 龙虾_USDT (n=24,
         22W/2L, avg +1.084%) — a 5-trade all-win streak's OBSERVED
         variance looked deceptively tiny simply because it hadn't hit
         a loss yet, not because it was actually lower-risk. Two-step
         fix: t_critical(n-1) (a hardcoded, interpolated Student's-t
         table — computed once via scipy.stats.t.ppf and embedded as
         plain numbers rather than adding scipy as an app dependency,
         same reasoning as avoiding numpy for VGI) replaced the fixed
         Z=1.0 from v0.98.7, accounting for a small sample's extra
         uncertainty in its own variance ESTIMATE. Verified against
         real scipy output (max 0.0004 interpolation error across
         tested df) — but alone this wasn't enough to fully close the
         DEXE gap (no reasonable fixed multiplier fixes a near-zero
         observed variance). Added a Bayesian prior: since FT5's
         stoploss is a FIXED, KNOWN quantity, max(0, FT5_RANK_PRIOR_
         TARGET - losses_count) pseudo-trades at -FT5_STOPLOSS_PCT are
         blended in before computing mean/variance. Tested a flat
         +3-always version first — it fixed DEXE but flipped the
         ORIGINAL UB/AKE case back the wrong way, since a fixed prior
         count lands disproportionately harder on a smaller-but-still-
         real sample (AKE, 2 real losses) than a larger one that
         already has plenty of honest loss experience (UB, 7 real
         losses) — caught by re-testing both original counterexamples
         together, not just the new one in isolation. Switched to
         tapering by ACTUAL losses_count (FT5_RANK_PRIOR_TARGET=1, so
         only combos with zero or one real observed loss get any
         adjustment at all) — confirmed via the real ft5_ranking_score()
         function in the file, both original reported cases correct
         simultaneously.
         ft5_ranking_score()'s signature changed to require losses_count
         explicitly (was pnls-only) — its one call site in ft5_optimize_
         symbol() now computes wins/losses before scoring instead of
         after. FT5_RANK_Z (v0.98.7) removed as dead code, replaced by
         FT5_RANK_PRIOR_TARGET.
         Verified with py_compile, an actual runtime start, pyflakes,
         the route/def integrity check, and the stale-default-parameter
         check — all clean.

v0.98.9 - VGI now has a reverse mode and full risk-autotune coverage,
         per direct user request ("Vgi и ft5 надо чтобы тоже
         автотюнились и имели режим реверса... надо чтобы отслеживались
         и параметры движения, аналогия с другими индикаторами"). FT5's
         half of this request is bigger (its ROI-ladder exit logic is
         hardcoded LONG-only throughout) and follows in a later pass —
         this round is VGI only.
         vgi_evaluate_signal() gained an invert parameter. Unlike EMA/
         Session's own invert (flip direction, repurpose the original
         sizing), VGI already computes BOTH zone_up and zone_down every
         evaluation, so inverting retargets the OPPOSITE zone (the one
         NOT selected by the normal delta/magnet read) instead of
         flipping direction while keeping a target that no longer makes
         directional sense — keeps VGI's own "trade toward a magnet
         zone" reasoning coherent even inverted, betting the other zone
         is the real magnet rather than an arbitrary sign-flip. Same
         risk=reward/min_rr sizing applies to the new target's own
         distance. Verified behaviorally: direction flips, target
         becomes the opposite zone, RR still guaranteed by construction.
         New VGI_INVERT_SIGNALS, wired through vgi_run_backtest() (both
         backtest and live scanning see the same inverted logic
         consistently, same reasoning as Session's own invert
         implementation) and the full settings system.
         VGI gained MFE/MAE tracking (update_vgi_signal_outcomes()),
         mirroring Session's own pattern exactly — R = abs(entry-sl),
         correctly covering both normal and inverted trades since sl is
         already set correctly per-mode at signal creation. compute_
         vgi_signal_stats() gained the same mfe_r_wins_at_close/etc
         aggregates every other tuned module exposes.
         risk_autotune_pass() gained a VGI block: the reverse-flag rule
         and an RR-extend rule for VGI_MIN_RR (reusing _risk_autotune_
         tp_extend, same mechanism as Session's own RR — VGI's target
         is already natively an R-multiple). Simpler than Session's own
         three-rule treatment: VGI's sizing is IDENTICAL whether
         inverted or not (no "only in inverted mode" gating needed), and
         there's no separate SL-width knob to tune since SL is fully
         DERIVED from (reward, min_rr) — only min_rr itself and the
         reverse flag are independent, tunable quantities. New
         RISK_AUTOTUNE_VGI_RR_BOUNDS (1.0-8.0, VGI's own RR-scale range).
         api_reset_risk_autotune() now also resets vgi_invert_signals/
         vgi_min_rr. UI: new reverse-mode toggle in VGI's settings row,
         "РЕВЕРС ВКЛЮЧЁН" indicator and an MFE/MAE display block added
         to VGI's panel (same shape as Session's own).
         Caught by this session's own automated stale-default-parameter
         check before shipping, not by inspection: vgi_run_backtest()'s
         signature had `min_rr=VGI_MIN_RR` as a frozen default — safe
         when VGI_MIN_RR was truly constant, but this change made it
         settings-mutable, so the exact v0.95.7-class bug would have
         applied (auto-tune changing VGI_MIN_RR would silently never
         reach a caller relying on the default). Fixed to `min_rr=None`
         resolved at call time, verified behaviorally (changed VGI_
         MIN_RR live via the real setter, confirmed a fresh backtest
         call picked up the new value immediately rather than staying
         frozen at whatever it was when the module loaded).
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, the route/def
         integrity check, and the stale-default-parameter check — all
         clean.

v0.98.10 - FT5 gains reverse mode + MFE/MAE tracking + a reverse-flag
         autotune rule, completing the same direct user request v0.98.9
         addressed for VGI ("Vgi и ft5 надо чтобы тоже автотюнились и
         имели режим реверса... надо чтобы отслеживались и параметры
         движения, аналогия с другими индикаторами").
         ft5_run_backtest() gained an invert parameter (resolved from
         the live FT5_INVERT_SIGNALS global at call time, not frozen as
         a signature default). The same entry trigger fires but opens a
         SHORT instead of LONG; stoploss and the ROI ladder are both
         mirrored exactly (pure %-of-entry rules, safe to reflect). The
         sell-signal exit (RSI cross + MACD + MinusDI, or SAR flip +
         Fisher) is deliberately NOT mirrored for inverted trades —
         it's tuned to detect bullish exhaustion for exiting a LONG,
         and MinusDI/SAR/Fisher don't reduce to their bearish-
         exhaustion equivalents via a mechanical sign flip the way
         PlusDI/MinusDI genuinely mirror each other; building a properly
         redesigned bearish-exhaustion detector was judged out of scope
         for this pass. Inverted trades exit only via stoploss or the
         ROI ladder — same "own, simplified exit rather than reusing
         original complexity" pattern this app's other invert modes
         already use.
         Verified behaviorally at multiple levels rather than trusted
         from the math alone: unit-level (SHORT ROI exits land below
         entry with positive pnl_pct; searched across 50 seeds to find
         a SHORT stoploss exit specifically, confirmed it lands above
         entry with negative pnl_pct exactly as a real short-side stop
         should), and end-to-end (ran the full ft5_optimize_symbol()
         pipeline in both directions on synthetic data, confirmed clean
         completion with sane, genuinely different results each way).
         MFE/MAE added to FT5 for the first time (it never tracked this
         at all before) — added directly inside ft5_run_backtest()'s
         walk-forward loop itself, since FT5's outcome-checking already
         works by fully RE-DERIVING via a fresh backtest call each poll
         (unlike every other module's incremental live-update pattern),
         so tracking had to live inside the walk-forward itself rather
         than as a separate polling update. R-unit is entry*stoploss_pct,
         matching FT5's own existing RR convention (pnl_pct/(stoploss_
         pct*100)). Verified behaviorally: searched seeds for an actual
         stoploss-exit trade, confirmed its mae_r landed at ~1.0 (should
         reach almost exactly the full risked distance by definition).
         Two real, pre-existing bugs found and fixed while wiring this
         through, unrelated to the new invert logic itself: (1) the live
         signal record's direction field and its Telegram entry alert
         were both hardcoded to "LONG" — harmless before this change
         since FT5 really was LONG-only, but would have silently
         mislabeled every inverted SHORT signal. (2) api_ft5_chart()'s
         SL-price calculation was hardcoded to the LONG-side formula
         (entry*(1-stoploss_pct)) — for a SHORT trade this is simply
         wrong (the stop sits above entry, not below); fixed to branch
         on the signal's own recorded direction.
         risk_autotune_pass() gained an FT5 block — but ONLY the
         reverse-flag rule (via _risk_autotune_reverse, using the new
         MFE/MAE data), not a stoploss-width nudge: FT5's own "RR" is
         DEFINED relative to FT5_STOPLOSS_PCT (rr = pnl_pct/(stoploss_
         pct*100)), so auto-tuning that constant would retroactively
         change what every already-recorded trade's RR even means, and
         would also need coordinating with the grid-search optimizer's
         own use of it (FT5_RANK_PRIOR_TARGET's pseudo-loss level) —
         judged a comparably subtle new inconsistency not worth
         introducing this round, left alone deliberately rather than
         silently.
         FT5 also gained real settings UI for the first time — it
         previously had only a Telegram-alerts checkbox, no "enabled"
         toggle or anything else, unlike every other module. New
         settings group with both an enabled toggle and the reverse-
         mode toggle. Panel gains a direction column in the signals
         table (previously omitted entirely, since direction was always
         implicitly LONG), a "РЕВЕРС ВКЛЮЧЁН" indicator, an MFE/MAE
         display block (matching Session/VGI's own), and corrected
         warning text that previously said "только LONG" unconditionally.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, the route/def
         integrity check, and the stale-default-parameter check — all
         clean.

v0.98.11 - CRITICAL FIX: KeyError: 'mfe_r' crashing outcome-checking for
         Session and VGI (and, latently, FT5/Divergence/EMA/Volume too,
         though not yet observed in the wild), caught from a direct
         error-log screenshot ("session_outcome NIL_USDT: 'mfe_r'",
         "vgi_outcome ...: 'mfe_r'" repeated across many symbols).
         Root cause: this session added MFE/MAE tracking to six modules
         (Session, EMA, Divergence, Volume, VGI, FT5) at different
         points, and several of their outcome functions access sig[
         "mfe_r"]/sig["mae_r"] directly rather than via .get() — correct
         for any signal created AFTER that module gained MFE/MAE, but
         a signal persisted to disk BEFORE that point (loaded back via
         load_state() on the next restart) has no such key at all,
         so a direct dict access raises KeyError. Every affected
         signal's outcome-checking pass then failed silently into the
         scanner's error log instead of ever resolving — exactly what
         the screenshot showed happening repeatedly, every scan cycle.
         Fixed with a single centralized backfill (_backfill_mfe_mae())
         at the one place all persisted signals get loaded from disk,
         rather than patching each individual direct-access site —
         considered patching every site instead (~30 occurrences across
         6 functions found by grep) and deliberately rejected it: that
         many edits to multi-line blocks would have meant that many
         chances to repeat this session's own recurring line-dropping
         mistake, for a fix a single well-placed .setdefault() sweep
         handles at once and covers any future direct-access site too,
         not just the ones found today. Applied to exactly the six
         signal lists confirmed to have direct mfe_r/mae_r access
         (signals, div_signals, ema_signals, session_signals, ft5_
         signals, vgi_signals) — session_ny_signals, xau_lg_signals, and
         scalp_signals never gained MFE/MAE tracking this session and
         were confirmed to have no such access, left untouched rather
         than backfilled unnecessarily.
         Verified behaviorally, not just read as correct: constructed an
         old-shape signal dict with no mfe_r/mae_r keys at all alongside
         a new-shape one that already had real values, ran the actual
         _backfill_mfe_mae() from the file, confirmed the old one got
         safe defaults for every missing field, the new one's real
         values were left untouched, and that direct sig["mfe_r"] access
         on the backfilled record no longer raises.
         Verified with py_compile, an actual runtime start, pyflakes,
         and the route/def integrity check — all clean.

v0.99.0 - new EXPERIMENTAL "MSNR ⚠️" tab — per direct user request, built
         from screenshots of the @xaubymedovyk Telegram channel's "MSNR
         education by Medovyk" slide deck (line-chart A-shape/V-shape/
         SBR/RBS/QM diagrams) plus a forwarded chat screenshot showing
         the full H1->M15->M5 cascade in practice. Cross-checked against
         the wider public "Malaysian SNR" material (an established named
         retail methodology, not the channel's own invention) to pin
         down what OCL/A-shape/V-shape/SBR/RBS/QM actually mean before
         writing any detection code.
         Translation into a precise no-lookahead algorithm:
           - OCL levels built from a CLOSE-only line chart on the
             structure timeframe (msnr_build_pivots()), never high/low.
           - A-shape = confirmed pivot HIGH on that close line, V-shape =
             confirmed pivot LOW — only kept if the leg from the
             previous opposite pivot is >= MSNR_MIN_LEG_ATR x ATR (a
             real impulsive "Storyline" leg, not chop).
           - Entry is the SBR/RBS mechanism itself: a QM (sweep through
             the active OCL level, close back on the origin side within
             MSNR_QM_LOOKBACK_BARS) on the faster MSNR_ENTRY_TF —
             msnr_detect_signals(), mirroring detect_session_
             manipulation()'s sweep-then-reject-cluster shape.
           - TP is the OTHER active OCL level of the current A/V pair
             (the Storyline target) — structural, not a fixed multiple,
             which is what gives this its very high R:R by construction
             (matches the source's own 10-24R screenshotted examples).
             Falls back to MSNR_FALLBACK_RR only if that side isn't
             confirmed yet.
         Two-stage cascade (structure TF for A/V levels, entry TF for the
         QM trigger) rather than the full H1->M15->M5 three-stage
         waterfall shown in one screenshot — deliberately collapsed for
         a first testable cut, same "ship the core mechanism, refine
         later" approach as XAU_LG/FT5's own introduction.
         Full module: msnr_build_pivots()/msnr_detect_signals()/msnr_
         track_outcome() (detection), msnr_backtest_symbol()/msnr_
         summarize_backtest() (backtest), msnr_scan_symbol_live()/
         update_msnr_signal_outcomes()/compute_msnr_signal_stats()
         (live), msnr_backtest_loop()/msnr_live_loop() (daemon threads),
         four API endpoints (/api/msnr/status, /signals, /chart/<symbol>,
         /api/reset/msnr), msnr_signals STATE deque + backtest results/
         summary, settings wiring (msnr_enabled, telegram_alerts_msnr,
         autotrade_msnr, autotrade_leverage_msnr — same shape as XAU_LG's
         own settings keys), new "MSNR ⚠️" tab + panel (refreshMsnr,
         table of live signals with A-shape/V-shape column) + its own
         chart modal (msnrModal/openMsnrChart/drawMsnrChart) drawing the
         candles, both OCL levels (orange A-shape, teal V-shape), and
         entry/SL/TP — unlike XAU_LG this DOES get a chart view, per
         direct user request to actually see the levels drawn.
         Same treatment as XAU_LG/FT5: symbols restricted to XAU_USDT/
         XAUT_USDT/PAXG_USDT (channel is gold-only), autotrade OFF by
         default (AUTOTRADE_ENABLED_MSNR), status UNVERIFIED — this is a
         faithful translation of the source material into code, not a
         backtested-and-proven edge; the tab's own warning banner says
         so explicitly, same wording pattern as XAU_LG's.
         Verified: synthetic-data smoke test (consolidation -> impulsive
         drop -> slow return) confirmed msnr_build_pivots() correctly
         finds the A-shape/V-shape pair and msnr_detect_signals() fires
         the expected SHORT QM signal on retest with TP at the V-shape
         level. py_compile, ast.parse, node --check on the extracted
         <script> block (taking the LAST "<script>" occurrence per the
         v0.96.0 lesson above, not the first), and the route/def
         integrity check — all clean, zero duplicate routes or defs
         introduced.

v0.99.1 - MSNR: per direct user request, added real R:R visibility to the
         backtest table (win-rate alone doesn't tell you if a ~50% rate
         is actually good when targets are structural, not fixed) and a
         way to inspect individual backtest trades on the chart, not
         just live signals.
         Each backtest trade now carries its own rr (reward/risk from
         that specific A/V pair, not a module-wide constant — this
         strategy's whole premise is that R:R varies trade to trade
         based on how far apart the Storyline levels are).
         msnr_summarize_backtest() gains avg_rr, median_rr, and
         expectancy_r — expectancy computed per-trade (each WIN scores
         its own rr, each LOSS scores -1, TIMEOUTs excluded as no real
         outcome) rather than win_rate x avg_rr, since a flat average
         RR would hide whether the wins are disproportionately the
         high-RR trades or not.
         New /api/msnr/backtest/<symbol> endpoint returns the full
         per-trade list (the status endpoint only ever had aggregates).
         Backtest table rows are now clickable (toggleMsnrBacktestTrades)
         and expand a per-symbol trade list inline, each trade itself
         clickable into openMsnrChart() — same chart/level-drawing code
         already built for live signals, so backtest trades get the
         identical "see the A-shape/V-shape and the QM zone" view. This
         is what actually answers the user's "are the levels even being
         built correctly" question, not just a win-rate number.
         Verified: msnr_summarize_backtest() on a synthetic 4-trade set
         (2W at 10R/12R, 1L, 1 timeout) returns expectancy_r=7.0, i.e.
         (10+12-1)/3 — confirms the per-trade (not average-RR-based)
         formula. py_compile, ast.parse, node --check on the extracted
         <script> block, and the route/def integrity check — all clean.

v0.99.2 - CRITICAL FIX: MSNR backtest-trades row would expand once, then
         hang on "загрузка..." forever on every subsequent open — found
         live by direct user report ("1 раз список увидел, потом он
         сбросился, раскрываю заново и висит загрузка").
         Root cause: refreshMsnr() fully replaces panel.innerHTML on
         every auto-refresh tick (same as every other tab), which
         silently collapsed any row the user had open AND reset its
         body content back to "загрузка..." — but the v0.99.1 stale-
         fetch guard (_msnrTradesLoaded[symbol]) was a plain JS object
         living OUTSIDE that rebuild, so it kept remembering "already
         loaded" across the rebuild even though the actual DOM content
         had just been wiped. Next click: guard says skip fetching,
         body stays on its post-rebuild "загрузка..." text forever.
         Fix: replaced the loaded-flag cache with _msnrExpanded, a Set
         that is the single source of truth for which rows the user
         wants open. New restoreMsnrExpansion(), called at the end of
         every refreshMsnr(), re-applies display:table-row AND re-
         fetches (via extracted loadMsnrTrades()) for every symbol in
         that set — so an open row survives auto-refresh instead of
         silently collapsing, and always actually has fresh content
         instead of getting stuck. Row arrow (▸/▾) now reflects real
         expanded state too.
         Verified: node --check + py_compile clean; traced the fix
         manually against the exact repro in the user's report (open ->
         auto-refresh tick -> re-open) to confirm loadMsnrTrades() now
         fires on that second open instead of being skipped.

v0.99.3 - MSNR chart: fixed level-label text overlapping itself — per
         direct user report + screenshot showing "A-shape 4357.86" and
         another A-shape label drawn on top of each other, illegible.
         Cause: the shared drawLevelLine() helper (used by every other
         experimental tab's chart too) prints each level's label right
         at that line's own y — fine when a chart has 2-3 well-spaced
         lines, but MSNR routinely has several close A-shape/V-shape
         pivots PLUS entry/SL/TP all sitting within a narrow price band
         (the whole point of the QM entry is that it fires right next
         to the level it just rejected off), so labels collided.
         Left drawLevelLine() itself untouched (other tabs' charts don't
         have this problem and don't need the extra complexity) — MSNR's
         own drawMsnrChart() now draws each dashed line immediately at
         its true y via a small local helper, but collects all labels
         into a list and calls the new layoutMsnrLabels() once at the
         end, which greedily spaces overlapping labels 12px apart
         top-to-bottom before drawing any text. Lines stay exactly where
         the price says; only the text moves.
         Verified: py_compile, node --check on the extracted <script>
         block — clean.

v0.99.4 - CRITICAL FIX: MSNR TP could land on the wrong side of entry —
         found by direct user chart review of a backtest trade: a LONG
         signal (entry 4333.52, SL 4320.51) had TP at 4259.99, BELOW
         both entry AND the stop. That trade could only ever "WIN" by
         accident, not by the Storyline actually playing out.
         Root cause: TP = "the opposite active OCL level" was taken
         unconditionally. active_a/active_v just track whichever pivot
         of each type was MOST RECENTLY CONFIRMED chronologically — with
         no check that it's still positioned ahead of current price. In
         the reported trade, the paired A-shape (4259.99) had been
         confirmed well before the V-shape it was paired with (4328.32)
         and price had since moved past it, leaving it stranded below
         entry — a used-up level, not a real unmet Storyline target, but
         msnr_detect_signals() didn't know the difference.
         Every prior MSNR backtest number (win-rate, RR, expectancy) the
         user has seen was computed with this bug live, so likely
         includes some fraction of trades that could only "WIN" by TP
         being trivially close to (or on the wrong side of) entry —
         inflating win-rate in a way that has nothing to do with the
         actual QM/Storyline mechanism working.
         Fix: msnr_detect_signals() now only uses the opposite active
         level as TP when it's genuinely on the correct side of entry
         (below entry for SHORT, above for LONG) — otherwise falls back
         to the existing fixed-RR placeholder, same as when that side
         hasn't confirmed yet at all. Same guard added symmetrically to
         both the SHORT (off A-shape) and LONG (off V-shape) branches.
         Old signals/backtest results already sitting in state.json were
         computed under the bug and are not meaningful — NOT auto-
         cleared on deploy (state.json persists across restarts via
         load_state(), a version bump alone doesn't touch it); the
         existing "Очистить MSNR" button / /api/reset/msnr already does
         exactly this and should be pressed once after updating.
         Verified: two targeted unit tests (LONG and SHORT), each
         monkeypatching msnr_build_pivots() to force the exact bug shape
         (a stale opposite-type pivot confirmed earlier than the
         triggering level but priced on the wrong side of it) and
         asserting the resulting signal's tp is no longer the invalid
         stale level and is correctly falls back to fixed RR on the
         right side of entry — both pass. py_compile clean.

v0.99.5 - MSNR: added autotune, per direct user request ("можно какой-то
         автотюнинг сделать для улучшения результатов? Какие параметры
         можно перебирать"). Same grid-search + confidence-bound-scoring
         shape this app already uses for FT5 (ft5_optimize_symbol()/
         ft5_ranking_score()) and, going further back, Volume's own
         PARAM_GRID_* optimizer — adapted from "% pnl" to "R multiple"
         since MSNR trades don't have a fixed stoploss %: each trade's
         reward is whatever the paired opposite OCL level happens to be,
         so results compare in R (risk-normalized), not raw price %.
         Grid: MSNR_PARAM_GRID_MIN_LEG_ATR (1.5/2.5/3.5 — how big an
         impulse counts as a real A/V leg) x MSNR_PARAM_GRID_QM_ZONE_PCT
         (0.3/0.6/1.0% — how close price must get to "be testing" a
         level) x MSNR_PARAM_GRID_QM_LOOKBACK (4/6/9 bars — how many
         bars the sweep+reject cluster can span), 27 combos. Left
         MSNR_STRUCTURE_TF/MSNR_ENTRY_TF and MSNR_SL_BUFFER_PCT out of
         the grid — timeframes would mean re-fetching different candles
         per combo (expensive, 27x the network calls), and the SL
         buffer only nudges risk size, not the actual mechanism.
         New msnr_optimize_symbol(): fetches candles ONCE per symbol,
         then msnr_run_backtest() (extracted from the old msnr_
         backtest_symbol(), now a thin fetch-then-delegate wrapper) runs
         all 27 combos as pure CPU — same cost shape as FT5's 36-combo
         search. New msnr_ranking_score(): lower-confidence-bound on
         mean R (mean - t_critical*stderr), with max(0,
         MSNR_RANK_PRIOR_TARGET - losses_count) synthetic -1R pseudo-
         losses blended in — same technique as ft5_ranking_score() but
         simpler, since MSNR's structural loss is already exactly -1R
         by construction (no stoploss_pct lookup needed, unlike FT5).
         Winning combo per symbol stored in STATE["msnr_symbol_
         overrides"] (persisted, mirrors ft5_symbol_overrides) and used
         by BOTH msnr_scan_symbol_live() (via new msnr_symbol_params()
         helper) and api_msnr_chart() — the chart now always reflects
         the exact params that actually produced whatever signal it's
         showing, not the module defaults. api_msnr_status()'s "top"
         list now ranks by score (not raw win-rate) and carries each
         symbol's winning params. Falls back to the middle of the grid
         if no combo clears MSNR_MIN_BACKTEST_TRADES closed trades,
         same as FT5's insufficient-data fallback, with a visible note
         in the UI.
         Frontend: backtest table gains Score and Параметры columns
         (per-symbol tuned min-leg-ATR/QM-zone/QM-lookback, plus a ⚠️
         note when a symbol fell back to grid-middle defaults).
         Also fixed, found while touching this code path: msnr_signals
         was being read back from state.json on load_state() but never
         actually assigned into STATE — every MSNR live signal was lost
         on every server restart since the tab shipped in v0.99.0. Now
         assigned like every other module's signal deque.
         Verified: msnr_ranking_score() reproduces the same qualitative
         effect FT5's fix was built for — a small all-win sample (n=2,
         raw mean 11.0) scored LOWER (1.66) than a larger sample with
         real losses mixed in (n=8, 3L, raw mean only 4.625) scored
         HIGHER (2.79), confirming the confidence-bound correctly
         penalizes the lucky-small-sample case. msnr_optimize_symbol()
         exercised end-to-end against a mocked candle fetcher, correctly
         falling back to grid-middle defaults with a note when the
         synthetic data didn't produce enough closed trades per combo.
         py_compile, node --check on the extracted <script> block, and
         the route/def integrity check — all clean.

v0.99.6 - Synced from GitHub first (local sandbox copy was stale at
         v0.98.11; actual repo had moved to v0.99.5 — downloaded the
         real current file via the raw content URL, since GitHub's
         Contents API omits the base64 `content` field for files over
         ~1MB, before making any further edits, to avoid overwriting
         work already pushed).
         CRITICAL FIX: Session's auto-tune reverse rule had a chicken-
         and-egg bug — the entire block including _risk_autotune_
         reverse() was nested inside `if SESSION_INVERT_SIGNALS:`,
         meaning it could only ever run once reverse was ALREADY on, so
         it was structurally impossible for auto-tune to ever turn
         reverse ON from the OFF state, no matter how negative normal-
         mode's own EV was. Found from a direct user report: Session
         sitting at 17.1% winrate (7W/34L, n=41) after 30 auto-tune
         passes, reverse never triggered despite a winrate nowhere near
         breakeven for any plausible RR. Confirmed by comparing against
         EMA's own block, which correctly runs its reverse rule
         unconditionally (gated only on data availability, not on
         EMA_INVERT_SIGNALS's current value).
         Fixed by moving the reverse-flag rule OUTSIDE the invert-mode
         gate — SESSION_SL_MULT and SESSION_REVERSE_RR's own tp_extend
         rule correctly stay gated (they tune the INVERTED trade's own
         sizing specifically, meaningless data otherwise), but the
         reverse decision itself must not be gated by the very flag
         it's deciding whether to flip. The rr passed to the reverse
         check now depends on which mode is CURRENTLY active: SESSION_
         REVERSE_RR (exact, fixed by construction) when already
         inverted; win_mfe_r's own average (already expressed in R-
         multiples, the same data the tp_extend rule already uses) as
         the best available empirical stand-in when not inverted, since
         normal-mode's TP sits at the opposite range edge with no
         single fixed RR to reference directly.
         Verified behaviorally with the exact numbers from the report
         (winrate=17.1%, n=41): confirmed the rule now actually flips
         the flag from False, where before this same call would never
         even execute. Verified the round-trip too, not just the one
         direction: reverse correctly stays on when performing well
         (winrate=65%, no flip) and correctly flips back off if it also
         turns out unprofitable (winrate=15%, flips False) — a fix here
         needed to work in both directions, not just unstick the one
         case that was reported.
         Also searched systematically for the same gating pattern
         (reverse-rule call nested inside its own INVERT_SIGNALS check)
         across the entire file rather than assuming Session was the
         only instance — confirmed no other module (including the new
         MSNR module, unfamiliar territory after the version sync) has
         this bug; Session was the only affected block.
         Verified with py_compile, an actual runtime start, pyflakes,
         and the route/def integrity and stale-default-parameter
         checks — all clean.

v0.99.7 - MSNR autotrade, per direct user request. Investigated before
         building anything new, since MSNR is a module built while this
         session's sandbox copy was stale (only discovered on syncing
         for v0.99.6) — found the backend infrastructure (AUTOTRADE_
         ENABLED_MSNR/AUTOTRADE_LEVERAGE_MSNR constants, full settings
         wiring, the actual execute_autotrade()/sim_execute_trade()
         call site in the live scanner) already existed and was
         correctly built, off by default same as XAU_LG/FT5's own
         "unverified source" treatment. What was actually missing:
         (1) msnr_signals wasn't registered in has_open_signal_any_
         module()'s lists dict — a real gap, not cosmetic: this meant
         MSNR's own open positions were invisible to every OTHER
         module's cross-module duplicate-position guard, and vice
         versa, so multiple modules could pile into the same symbol
         simultaneously, defeating the whole point of that guard.
         Fixed by adding the missing entry. (2) No settings-UI row
         existed for the autotrade toggle/leverage at all (only the
         backend constants + generic settings-key wiring were present)
         — added one, matching VGI's own established template exactly,
         marked ⚠️ same as MSNR's own experimental-warning styling
         elsewhere in the app. (3) /api/autotrade/status's own "enabled"
         summary dict was also missing an "msnr" key — fixed too, found
         while double-checking every place a per-module autotrade flag
         gets surfaced, not just the one the user could see directly.
         One suspected issue investigated and ruled out rather than
         "fixed": sim_execute_trade() being called INSIDE the `if
         AUTOTRADE_ENABLED_MSNR:` block looked at first like it might
         be gating the paper simulator behind the real-autotrade toggle
         incorrectly — checked against VGI's and Session's own call
         sites (the newest and the most mature module respectively) and
         confirmed both have the IDENTICAL structure: this is this
         app's established, intentional design (the simulator mirrors
         what autotrade would do only once a module's own toggle is on,
         not a shadow-mode for every signal unconditionally), not a bug
         needing correction — left MSNR's code exactly as it already
         was for that part.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, the route/def
         integrity check, and the stale-default-parameter check — all
         clean.

v0.99.8 - get_candles() now retries on HTTP 429 (Too Many Requests)
         instead of failing immediately, per a direct user report that
         XAU_USDT was silently absent from MSNR's backtest results
         while XAUT_USDT/PAXG_USDT showed up fine. Diagnosed via the
         same error-log-screenshot approach that's worked repeatedly
         this session: confirmed XAU_USDT is a real, valid Gate.io
         contract (checked directly rather than assumed) — the actual
         error was a 429, and critically, the SAME 429 was hitting
         XAU_USDT across THREE unrelated modules (Volume's fetch_
         candles_concurrent, Session NY's process_one, MSNR's own
         backtest) within the same minute, alongside unrelated symbols
         (CL_USDT, SOXL_USDT, ETH_USDT, BTC_USDT...) — pointing at this
         app's overall concurrent request volume across modules
         occasionally exceeding Gate.io's rate limit as a whole, not a
         XAU_USDT-specific or MSNR-specific problem.
         Root cause in the code: get_candles()'s own docstring stated
         "Does NOT retry on HTTP error responses (4xx/5xx) — a 4xx/5xx
         is a real answer, not a connectivity blip" — true for a
         genuine 404/400, but wrong for 429 specifically: that status
         code is explicitly DEFINED to mean "you're being rate-limited,
         back off and retry," not a final answer. Applying the general
         4xx/5xx rule to this one exception case was the actual bug —
         confirmed msnr_backtest_loop()'s per-symbol try/except was
         working exactly as designed (catch, log, move on), so a failed
         XAU_USDT fetch correctly never got an entry in results_by_
         symbol at all, matching what was observed as "just missing,"
         not shown as an explicit error — the real fix belonged in
         get_candles() itself, not in how MSNR handles its failure.
         Implementation: new GET_CANDLES_RATE_LIMIT_RETRIES (3) and
         GET_CANDLES_RATE_LIMIT_DELAY (4s base, doubling per attempt —
         deliberately longer than the existing 1.5s connection-retry
         delay, since a rate-limit window needs more time to clear than
         a transient blip), tracked as its own independent budget
         separate from GET_CANDLES_RETRIES/conn_attempt. Honors Gate.io's
         own Retry-After header when present, falling back to the
         exponential default otherwise. Rewrote the retry loop from a
         `for attempt in range(...)` (sized only for the connection-
         retry count) to a `while True` with two independently-tracked
         counters — caught during implementation, before shipping, that
         nesting the 429 retry inside the connection-sized for-loop
         would have capped its own budget prematurely whenever both
         retry types fired in the same call. Every OTHER 4xx/5xx status
         code still gets zero retries, unchanged.
         Verified behaviorally with three mocked-request scenarios, not
         just read as correct: (1) two 429s followed by success still
         succeeds within budget; (2) a permanently-429ing endpoint fails
         cleanly after exhausting its budget (4 total attempts) rather
         than hanging forever; (3) a Retry-After: 7 header is actually
         honored — the real sleep duration used was confirmed to be
         exactly 7.0s, not just assumed from reading the code.
         Verified with py_compile, an actual runtime start, pyflakes,
         and the route/def integrity and stale-default-parameter
         checks — all clean.

v0.99.9 - MSNR's backtest now also explores the top-30 most liquid
         symbols, per direct user request ("может где-то тоже такая
         логика сигналов прокатит, пока только для бэктеста") — live
         scanning stays exactly gold-only (MSNR_SYMBOLS), unchanged.
         New msnr_build_backtest_universe(): MSNR_SYMBOLS UNION'd with
         the top MSNR_BACKTEST_UNIVERSE_SIZE (30) symbols by real 24h
         volume, same get_tickers() fallback-field pattern already
         proven correct for VGI/FT5/Session's own universe-builders —
         union rather than replace, so gold stays backtested even if
         its own liquidity wouldn't independently place it in a top-30
         cut. Verified behaviorally with mocked tickers: union produced
         the expected size, all three gold symbols present even with a
         deliberately-low mocked volume for one of them, no duplicates.
         msnr_backtest_loop() switched from sequential (`for symbol in
         MSNR_SYMBOLS`) to a ThreadPoolExecutor, applying VGI's own
         v0.98.4 concurrency fix PROACTIVELY here rather than waiting
         for a live 429 report to force it — the exact same rate-limit
         pressure this session already diagnosed (v0.99.8) is far more
         likely to bite with 30+ symbols than the original 3, and a
         sequential loop over that many would be both slower and more
         exposed to it. Factored the per-symbol work into _msnr_
         backtest_one_symbol() (exceptions caught internally, matching
         every other per-symbol worker in this app) submitted to the
         pool.
         msnr_backtest_universe added to STATE (was about to be
         referenced without an initial declaration — caught and fixed
         before it could ship as a silently-created-on-first-write key,
         inconsistent with how every other STATE entry in this app is
         declared upfront).
         api_msnr_status() gained backtest_universe_size, and each
         ranked leaderboard entry gained a live boolean (symbol in
         MSNR_SYMBOLS) so the UI can honestly distinguish gold (actually
         tradeable) from the broader exploration set (backtest-only,
         nothing wired to autotrade or live scanning). Panel header
         rewritten to say this explicitly instead of just listing
         "Символы: ..." as if that were the whole scanned set; each
         leaderboard row now shows a green dot for live-tradeable
         symbols or a "бэктест" label for exploration-only ones.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, the route/def
         integrity check, and the stale-default-parameter check — all
         clean.

v0.99.10 - CRITICAL FIX: MSNR's chart modal showed "подтверждённого
         QM-сигнала в этом окне нет" for a backtest trade the user
         clicked directly from the leaderboard's own expandable trades
         table — meaning the exact trade being displayed as historical
         evidence couldn't be re-confirmed by the chart meant to show
         it. Root cause: api_msnr_chart() always blindly RE-DERIVED
         everything by re-running msnr_detect_signals() with msnr_
         symbol_params(symbol) — the symbol's CURRENT live parameter
         override, not whatever combo actually produced the clicked
         trade. If a newer backtest/autotune cycle ran since (very
         plausible right after v0.99.9 expanded MSNR to 30+ symbols,
         triggering fresh optimize passes for many of them), the
         winning params can differ enough that the same historical
         signal simply doesn't get re-detected at all.
         Fixed by having the endpoint check for the actual stored
         record FIRST — both STATE["msnr_signals"] (live) and STATE[
         "msnr_backtest_results"][symbol] (backtest) — before ever
         attempting re-derivation. Every stored trade (msnr_run_
         backtest()'s own return shape) and every live signal record
         already carries complete entry/sl/tp/direction/level/result/
         exit_time — there was never a need to re-derive an already-
         known signal from scratch with parameters that could have
         since drifted. Re-derivation is now purely a fallback, used
         only for genuinely browsing the CURRENT live Storyline (no
         `time` given, or a `time` that matches nothing stored) — same
         principle FT5's api_ft5_chart() already uses its own stored
         trade data for, applied here where MSNR's own chart endpoint
         had drifted from it.
         Verified behaviorally with two scenarios, not just read as
         correct: (1) a stored backtest trade with entry/sl/tp values
         deliberately different from whatever `msnr_detect_signals`
         would freshly compute — confirmed the endpoint returns the
         STORED values unchanged, not re-derived ones; (2) a `time`
         matching nothing stored anywhere — confirmed the fallback
         path still runs cleanly with no error, same as before this
         fix for that case.
         Verified with py_compile, an actual runtime start, pyflakes,
         the route/def integrity check, and the stale-default-parameter
         check — all clean.
         Also added, per direct user follow-up before pushing: an exit
         marker (a dot at the SL or TP price, on the candle where the
         trade actually closed, colored green WIN / red LOSS) alongside
         the existing entry marker — MSNR's chart previously only ever
         marked entry, unlike VGI's own chart (openVgiChart/
         drawVgiChart), which this mirrors exactly for consistency.
         Reused the existing shared drawEntryMarker() and findCandleIndex()
         helpers rather than adding new ones — findCandleIndex() already
         finds the nearest candle rather than requiring an exact time
         match, so no special-casing was needed for exit_time not
         landing precisely on a candle boundary.

v0.99.11 - MSNR gains an RR ceiling driven by real statistics, per direct
         user request: "по statistike должно быть видно, а автотюнинг
         должен ориентироваться на статистику" — off a concrete
         observation (SPCX: trades with rr>6 consistently hit stop,
         essentially never reaching TP).
         MSNR's TP is the genuine opposite structural level (the
         Storyline pair), not a risk-derived point — "shortening the
         take" the way the user offered as one option would mean
         inventing an arbitrary price with no structural meaning, so
         instead reused the ALREADY-EXISTING fallback path (fixed
         fallback_rr, previously triggered only when no valid opposite
         level exists at all) — a signal whose genuine opposite level
         would produce rr > MSNR_MAX_RR now falls through that exact
         same path instead of a new mechanism. New MSNR_MAX_RR (default
         8.0), resolved from the live global at call time (not frozen
         as a signature default, learning proactively from the exact
         v0.95.7-class mistake this session already made and fixed for
         VGI_MIN_RR — applied here BEFORE shipping, not after a report).
         New msnr_rr_bucket_stats(): buckets closed trades (MSNR_RR_
         BUCKETS = 0-3/3-5/5-7/7-10/10+) by their own realized rr,
         win-rate per bucket — the user's own point that pooled stats
         hide this pattern verified directly: reconstructed the SPCX-
         like scenario synthetically (60% win-rate at rr~2.5 vs 6.7% at
         rr~8) and confirmed the bucket table makes it directly visible
         where one pooled average couldn't.
         New _risk_autotune_msnr_max_rr(): pools trades across ALL
         symbols' backtest results (a single symbol's own sample is
         usually too small to bucket reliably — MSNR_MAX_RR is one
         global cap, not a per-symbol tuned param), finds the lowest
         bucket failing its own breakeven with sufficient sample
         (RISK_AUTOTUNE_MIN_SAMPLE), steps the cap toward it by a
         bounded 10%-per-pass — deliberately one-directional (only ever
         tightens off solid evidence, never guesses at loosening back
         up): the two mistakes aren't symmetric, a too-tight cap just
         costs some upside, a too-loose one keeps letting the reported
         problem through.
         Two real bugs in this rule's own logic caught by behavioral
         testing before shipping, not by inspection: (1) a cap value
         set below MSNR_FALLBACK_RR (4.0) is self-defeating — the
         fallback trade it falls through to would itself exceed the
         "cap" supposedly being enforced. Fixed by keeping RISK_
         AUTOTUNE_MSNR_MAX_RR_BOUNDS' lower bound (5.5) safely above
         it. (2) The breakeven check originally used each bucket's
         LOWER boundary as the reference RR — broke down for the first
         bucket (lo=0), whose implied breakeven of 100% made the rule
         fire almost unconditionally even on healthy synthetic data (a
         "nothing should change" test case incorrectly triggered a
         change). Fixed by computing each bucket's own actual average
         realized rr instead and using that for the breakeven
         comparison; re-verified both the false-positive case (now
         correctly inert) and the real-failure case (still correctly
         fires) after the fix.
         Full plumbing: MSNR_MAX_RR wired through the complete settings
         system (SETTINGS_KEYS/get_settings/apply_settings/_set_msnr_
         max_rr), reset by api_reset_risk_autotune() alongside every
         other tuned parameter, exposed in api_msnr_status()'s config
         and as a new pooled rr_buckets field. Panel header now states
         the current ceiling and what it does in plain language; new RR-
         bucket win-rate table added to the MSNR panel so the pattern
         the user described is directly visible, not just assumed.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, the route/def
         integrity check, and the stale-default-parameter check — all
         clean.

v0.99.12 - CRITICAL FIX: the MSNR tab went completely black (empty panel,
         every other tab fine) immediately after v0.99.11 shipped — a
         real live regression, reported directly and reproduced exactly
         via a screenshot showing the empty tab.
         Root cause: msnr_rr_bucket_stats() (new in v0.99.11) included a
         raw "hi" field in each returned bucket dict — MSNR_RR_BUCKETS'
         last bucket has hi=float("inf"), and Flask's jsonify() happily
         serializes that as the literal token `Infinity`, which is NOT
         valid JSON (RFC 8259 only allows finite numbers). refreshMsnr()'s
         very first line (`await response.json()`) then throws a
         SyntaxError parsing it — confirmed directly, not just inferred:
         reproduced the exact failure with `node -e "JSON.parse('...
         Infinity...')"`, which threw "Unexpected token 'I'", the exact
         class of error that would abort refreshMsnr() before panel.
         innerHTML was ever set (no try/catch wraps that fetch), leaving
         the tab empty — matching the screenshot precisely.
         This exact lesson (float('inf') → invalid JSON → don't persist
         or serialize it) was ALREADY learned and explicitly documented
         in this codebase twice before (Scalp's timeout_sec, XAU_LG-
         adjacent code) — noted honestly rather than glossed over: this
         wasn't a novel discovery, it was the same known trap re-
         introduced fresh while adding a new feature, the prior
         documentation didn't get checked against before writing
         MSNR_RR_BUCKETS.
         Fixed by removing "hi" from the returned bucket dicts entirely
         — it was never actually consumed anywhere (the "range" label
         already encodes both boundaries as text for display, and _risk_
         autotune_msnr_max_rr() only ever reads "lo", which is always
         finite: 0/3/5/7/10). Chose dropping the field over sanitizing
         inf->None at the jsonify boundary, since it eliminates the
         whole class of "some other future numeric field might also
         carry inf into a JSON response," not just patches this one
         instance.
         Verified end-to-end with the real function, not just read as
         fixed: built realistic STATE data with a trade deliberately
         placed in the top ("10+") bucket — exactly the case that
         previously broke — called the actual api_msnr_status() function,
         confirmed the raw response body contains no "Infinity" token,
         and confirmed Node's own JSON.parse() succeeds on it where it
         previously threw. Also searched the whole file for any other
         place MSNR_RR_BUCKETS or a raw "hi" value might reach a
         jsonify() call — none found; this was the only leak.
         Verified with py_compile, an actual runtime start, pyflakes,
         and the route/def integrity check — all clean.

v0.99.13 - Diagnosed a direct user follow-up: gold symbols (XAU_USDT/
         XAUT_USDT/PAXG_USDT) missing entirely from MSNR's leaderboard,
         including their green "live" dot, after v0.99.12's fix.
         Confirmed msnr_build_backtest_universe() itself is correct —
         MSNR_SYMBOLS is always unioned in first, gold can't be excluded
         by that logic. Asked directly whether the scanner's error log
         showed any msnr_backtest XAU_USDT/XAUT_USDT/PAXG_USDT entries —
         user checked and found none for gold specifically, but the very
         next screenshot showed the app under heavy, ACTIVE rate-limit
         pressure right then: 429s hitting many DIFFERENT modules
         simultaneously (session, ft5_optimize, msnr_backtest — on BNB_
         USDT/PROM_USDT, not gold) within the same minute.
         Root cause identified, not just theorized: STATE["errors"] is a
         30-entry deque, but the API only ever returned the LAST 10 of
         it. During a burst like the one just witnessed — many symbols
         across many modules all failing within the same short window —
         an earlier failure (plausibly gold's own) gets pushed out of
         the visible 10 long before the underlying 30-entry buffer would
         have discarded it, making a real error look like "no error
         happened" when it's actually just "scrolled out of a too-short
         display window."
         Fixed by showing the full 30-entry buffer instead of slicing
         to the last 10 — a genuinely useful diagnostic improvement on
         its own (this exact kind of ambiguity — "did X actually fail,
         or did something else's spam just push it out of view" — has
         come up multiple times this session), not a fix for MSNR
         specifically. The panel's own "(N)" count label was already
         dynamic (${errList.length}), so no separate text change needed
         — it now correctly shows the true count instead of always
         capping at 10.
         Honest about scope: this doesn't confirm gold's own failure was
         rate-limiting rather than something else — it makes the NEXT
         occurrence (or the next few minutes, once this burst settles)
         actually diagnosable instead of guessed at, rather than
         claiming a root cause that wasn't directly observed this time.
         Verified with py_compile, an actual runtime start, pyflakes,
         and node --check on the extracted <script> block — all clean.

v0.99.14 - MSNR_BACKTEST_UNIVERSE_SIZE lowered 30 -> 10, per direct
         follow-up request. Confirmed first (via the panel's own status
         text, not assumed) that "bэктест пустой" wasn't a new bug —
         MSNR's own panel still said "бэктест ещё не завершился", i.e.
         the cycle was genuinely still running, not stuck or crashed;
         v0.99.13's error-log fix and the confirmed active rate-limit
         burst already explained why. With 33 symbols (3 gold + 30
         liquid) each potentially needing multiple retry-with-backoff
         candle fetches under the current sustained Gate.io pressure,
         a full cycle was taking long enough to look indistinguishable
         from broken. Reducing the exploration set to 13 total (3 gold
         + 10 liquid) directly cuts how much retry-backoff exposure one
         cycle can accumulate, without touching gold's own guaranteed
         inclusion (msnr_build_backtest_universe() still unions MSNR_
         SYMBOLS in first, verified behaviorally: mocked 40 tickers,
         confirmed the universe comes out to exactly 13 with all three
         gold symbols present).
         Verified with py_compile, an actual runtime start, and
         pyflakes — all clean.

v0.99.15 - Two things, per direct user follow-up after the backtest
         eventually completed but took much longer than before: (1)
         investigate where the real bottleneck is, (2) add a progress
         bar for MSNR specifically — symbol-loading progress and overall
         status, not just a binary "завершился/не завершился".
         Investigation: confirmed msnr_optimize_symbol() does NOT
         re-fetch candles per grid-search combo (candles fetched ONCE
         per symbol, msnr_run_backtest() is pure CPU per combo — the
         function's own docstring already documented this correctly,
         verified it still matches the actual code). Found a real,
         separate gap instead: get_candles_range() — used for MSNR's
         structure/entry candles (and session's multi-week backtests,
         and the "magnified profile" data) — has its OWN request loop,
         entirely separate from get_candles(), and NEVER got the 429-
         retry fix from v0.99.8. A multi-day range fetch needs several
         paginated chunk requests (chunk_points=900 per request), and
         previously ANY single chunk hitting a 429 aborted the WHOLE
         symbol's fetch with zero retry — unlike get_candles()'s own
         single-shot fetches, which already retry generously. Checked
         honestly before claiming it as THE root cause: an unretried
         429 fails FAST, not slow, so this alone doesn't explain a
         multi-minute hang — but it's a real, separate reliability gap
         worth closing regardless, and under the currently-confirmed
         heavy concurrent rate-limit pressure across many modules, it
         meaningfully increases how often a symbol's fetch fails outright
         rather than gracefully retrying through it.
         Fixed by applying the identical 429-retry-with-backoff logic
         (GET_CANDLES_RATE_LIMIT_RETRIES, GET_CANDLES_RATE_LIMIT_DELAY,
         Retry-After header support) to get_candles_range()'s chunk
         loop. Verified behaviorally with realistic current timestamps
         (an earlier attempt using stale hardcoded 2023-era timestamps
         silently short-circuited via the function's own "too old, don't
         even try" clamp — caught and corrected before trusting a false
         negative): two consecutive 429s followed by success now
         succeeds; a permanently-429ing endpoint still fails cleanly
         after exhausting its budget (4 total attempts) rather than
         hanging forever.
         Progress bar: new STATE fields (msnr_backtest_total/_done/
         _in_flight/_running/_started_at) updated live as each symbol
         resolves — _msnr_backtest_one_symbol() marks itself "in flight"
         on start and removes itself (via try/finally, so this can't
         leak even on an exception) on completion. msnr_backtest_loop()
         itself wraps its whole cycle body in try/finally too, so
         "running" always clears even if the cycle dies partway through
         (e.g. msnr_build_backtest_universe() itself failing) — a stale
         "still running" flag left on after a real failure would be
         worse than the original "no detail" problem this is meant to
         fix. api_msnr_status() exposes all of this; the panel now shows
         a live percentage bar plus which symbols are currently being
         fetched (up to 6 named, "+N" for the rest), and the status text
         switches between "выполняется: X/Y монет · идёт Zс" while
         running and the existing last-finished text once done.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, the route/def
         integrity check, and the stale-default-parameter check — all
         clean.

v0.99.16 - MSNR_BACKTEST_UNIVERSE_SIZE raised 10 -> 70, per direct
         follow-up request (73 symbols total with gold, more than
         double v0.99.9's original 30). Reasonable now that v0.99.15
         closed get_candles_range()'s own missing 429-retry gap and
         added live per-symbol progress tracking — a longer cycle is at
         least visibly progressing (done/total count, which symbols are
         currently in flight) rather than looking indistinguishable from
         stuck, which was the real problem the smaller universe was
         papering over rather than fixing directly. Verified
         behaviorally: mocked 100 tickers, confirmed the universe comes
         out to exactly 73 with all three gold symbols still present.
         Verified with py_compile, an actual runtime start, and
         pyflakes — all clean.

v0.99.17 - MSNR gains automatic live-scan promotion: a symbol from the
         wider backtest exploration set now gets added to LIVE scanning
         once its winning combo's win-rate/sample clear a bar, per
         direct user request: "для монет более 50% винрейт и с выборкой
         более 40 сигналов на бэктесте добавлять их в онлайн торговлю."
         New MSNR_LIVE_PROMOTE_MIN_WINRATE (50%) and MSNR_LIVE_PROMOTE_
         MIN_SAMPLE (40). Sample size deliberately checked against
         wins+losses (closed trades), not the raw "trades" count — that
         also includes timeouts, which say nothing about win-rate
         reliability and would let a mostly-timing-out symbol qualify on
         volume alone.
         New msnr_compute_live_universe(overrides): MSNR_SYMBOLS (gold)
         union'd with every symbol clearing both bars — a pure function
         of the overrides dict, no locks or I/O, so it's cheap to call
         and easy to test directly. Gold stays live unconditionally
         regardless of its own backtest numbers, matching its existing
         role as the floor MSNR_SYMBOLS always represents — this only
         ever ADDS symbols on top, never removes gold.
         msnr_backtest_loop() computes this right alongside the rest of
         each cycle's results (same state_lock write, so live_universe
         and backtest_results/overrides always reflect the SAME cycle,
         never a stale mix) into a new STATE["msnr_live_universe"].
         msnr_live_loop() now scans that instead of the static MSNR_
         SYMBOLS constant directly — falls back to MSNR_SYMBOLS itself
         if the backtest hasn't populated it yet (e.g. right after a
         fresh restart), so live scanning can never end up empty.
         Noted directly, not silently: MSNR's existing AUTOTRADE_ENABLED_
         MSNR toggle (off by default) applies to WHATEVER gets live-
         scanned — if a user already has it on, a newly-promoted symbol
         starts trading real money on its very next signal, same as any
         other live-scanned symbol. This is the natural, intended
         consequence of "add them to live scanning," not a separate
         decision snuck in — surfaced explicitly in the panel's own
         header text so it's not a silent behavior change: "Автоторговля
         MSNR (если включена) применяется ко всем монетам из живого
         скана, включая только что квалифицированные — не только к
         золоту."
         api_msnr_status()'s "live" flag on each leaderboard row (the
         green-dot indicator) switched from checking the static
         MSNR_SYMBOLS constant to checking the dynamic live_universe —
         it was checking the wrong thing as soon as promotion existed.
         Panel header rewritten entirely — the old text explicitly
         claimed "только это торгуется" (only gold trades) and
         "автоторговля/живой скан их не касаются" (autotrade/live scan
         don't touch the wider set), both now false; new text states
         the promotion criteria directly and lists the actual current
         live set.
         Verified behaviorally at two levels: (1) msnr_compute_live_
         universe() directly against six synthetic cases — a symbol
         clearing both bars (promoted), clearing win-rate but not
         sample size (rejected), clearing sample size but not win-rate
         (rejected), clearing both but flagged with a backtest error
         (rejected regardless of good numbers), and both non-gold and
         gold-with-terrible-numbers cases confirming gold's
         unconditional inclusion; (2) end-to-end through the actual
         api_msnr_status() function with realistic STATE data, confirming
         valid JSON (no stray Infinity — checked directly, not assumed,
         given v0.99.12's exact incident), the promoted symbol appearing
         in live_universe, and its leaderboard row correctly showing
         live=true.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, the route/def
         integrity check, and the stale-default-parameter check — all
         clean.

v0.99.18 - MSNR gains sortable backtest columns and 6 individual per-
         symbol autotrade toggles, per direct follow-up request:
         "сделай сортировку по винрейту и количеству сигналов бектеста,
         добавь возможность включать автоторговлю не только по золоту,
         но и по топ 3 после сортировки не считая золота, то есть всего
         6 полей для автоторговли."
         New msnr_rank_by_winrate_sample(overrides, exclude): sorts by
         winrate DESC, closed-trade sample (wins+losses) as tiebreaker.
         New msnr_autotrade_eligible_symbols(): MSNR_SYMBOLS (gold,
         unconditional) + the current top 3 non-gold by that ranking —
         exactly the 6 the user asked for. Both pure functions of the
         overrides dict, directly testable. Verified behaviorally: six
         synthetic cases covering ties (same winrate, different sample
         size correctly breaks the tie), an errored-but-good-numbers
         symbol correctly excluded regardless, and gold's unconditional
         inclusion regardless of its own numbers.
         Replaced the single AUTOTRADE_ENABLED_MSNR gate entirely with a
         new per-symbol STATE dict (msnr_autotrade_symbols) — deliberately
         NOT validated at write time by its own setter (_set_msnr_
         autotrade_symbol doesn't check current eligibility, so a
         previously-set toggle for a symbol that later falls out of the
         top 3 survives dormant rather than being deleted, and resumes
         if that symbol re-qualifies later) but IS re-validated at both
         the API layer (api_msnr_autotrade_toggle rejects toggling a
         symbol that isn't currently one of the 6, HTTP 400) and at the
         actual trade-trigger point in msnr_scan_symbol_live() (requires
         BOTH the saved toggle AND current eligibility before calling
         execute_autotrade/sim_execute_trade) — a demoted symbol's stale
         "on" toggle can't silently keep trading real money just because
         it once qualified. Verified behaviorally end-to-end through the
         real endpoint: a genuinely-eligible symbol and gold both toggle
         successfully; an ineligible symbol is rejected with a clear
         error and confirmed to NOT land in the saved state at all.
         Wired into persistence (save_state/load_state) — survives a
         restart, unlike a purely in-memory dict would.
         api_msnr_status() gained autotrade_eligible (the current 6) and
         each leaderboard row gained autotrade_eligible/autotrade_on, so
         the panel can render exactly 6 checkboxes, correctly pre-
         checked, without a separate round-trip. api_reset_msnr() now
         also clears msnr_live_universe (stale derived data, same
         reasoning as clearing overrides) but deliberately does NOT
         clear msnr_autotrade_symbols — that's the user's own stated
         preference, not derived backtest state that should vanish just
         because old backtest numbers did.
         Panel: Win-rate and n column headers are now clickable (msnr
         SortBy()), with a small ▾/▴ indicator showing the active sort
         key and direction; sort state lives outside the render function
         (same pattern _msnrExpanded already used) so it survives the
         panel's full re-render on every auto-refresh tick. New "Авто"
         column with a checkbox for eligible rows (— for the rest),
         wired to a new msnrToggleAutotrade() that reverts the checkbox
         and shows a clear error if the server rejects the change (the
         eligible-6 set can shift between page load and click, if a new
         backtest cycle finished in between).
         Removed the old single MSNR autotrade checkbox from the
         settings modal (repurposed that row to explain the new per-
         symbol mechanism and point at the panel; kept the shared
         leverage input, since leverage is still one value across all 6
         symbols, not per-symbol). Caught and fixed a real crash this
         removal would otherwise have caused, before it could ship: the
         settings-modal JS iterates a fixed `setInputs` map and directly
         sets `.checked` on each mapped DOM element — the entry pointing
         at the now-removed checkbox would have resolved to null, and
         `null.checked = ...` throws every single time the settings
         modal opens. Removed that dead mapping entry entirely rather
         than leaving it dangling.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, the route/def
         integrity check, and the stale-default-parameter check — all
         clean.

v0.99.19 - Two direct follow-ups from the same v0.99.18 feature.
         (1) "Чекбоксы есть, сортировки не вижу, монеты с галочками
         разбросаны по всему списку, дай возможность ставить галочки
         для топ 10." Verified the sort logic itself was actually
         correct (simulated it directly in Node against sample data
         before touching anything) — the real problem was UX, not a
         bug: the table's default order was still by score (unchanged
         from before sortable columns existed), so opening the panel
         never visibly showed a winrate/n-sorted view without an
         explicit click, and eligible (checkbox-showing) rows could
         land anywhere in that order.
         Fixed the "scattered checkboxes" complaint directly: eligible
         rows now group to the top of the table UNCONDITIONALLY, ahead
         of whatever sort key is active — verified behaviorally (Node
         simulation: an eligible low-score row correctly outranks an
         ineligible high-score one). Added a visible separator row
         exactly at the eligible/rest boundary so the grouping is
         obvious rather than requiring the reader to notice checkboxes
         stop appearing partway down.
         MSNR_AUTOTRADE_TOP_N raised 3->10 (13 total fields with gold) —
         msnr_autotrade_eligible_symbols() genuinely already supported
         an arbitrary N via this one constant, not a hardcoded 3, so
         this was a one-line change. Verified behaviorally: 15 synthetic
         candidates in, confirmed exactly 13 come out (3 gold + 10).
         (2) "Не только по винрейту, важно ещё количество сделок" — a
         second, sharper follow-up after the first fix shipped. The
         previous ranking (raw winrate DESC, sample size only as a
         tiebreaker for EXACT ties) still let a small lucky sample
         (e.g. 7 trades at 70%) outrank a large steady one (100 trades
         at 55%) in the completely ordinary case where their winrates
         merely differ — a tiebreaker does nothing there. Switched
         msnr_rank_by_winrate_sample() to rank by `score` instead — the
         SAME lower-confidence-bound-on-mean-R metric this app already
         built and uses to pick each symbol's own winning grid-search
         combo (msnr_ranking_score()), reused here rather than inventing
         a second, differently-tuned formula for the identical
         underlying problem (a small sample's apparent edge needing to
         be discounted, not just tie-broken). Verified behaviorally
         with the exact small-lucky-vs-large-steady scenario: the
         large-sample, lower-winrate symbol now correctly outranks the
         small-sample, higher-winrate one. Function name kept as-is
         (renaming would have touched many more call sites/docs for a
         cosmetic gain) — its own docstring now explains explicitly why
         it ranks by score despite the name.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the extracted <script> block, the route/def
         integrity check, and the stale-default-parameter check — all
         clean.

v0.99.20 - Fixed a real structural gap in MSNR's autotrade ranking, per
         a direct follow-up with a concrete reported case: "иногда
         монеты с 42 винрейта держат средний RR больше 3, и выборкой
         больше 50 но даже в топ 10 не попали. А в топ 10 при этом
         выборка с 10 монетами есть, потому что винрейт 50."
         Reproduced the exact case directly, not just read as plausible:
         built a 55-trade sample at 42% winrate with wide-variance wins
         (some near breakeven, some near MSNR_MAX_RR — genuinely
         realistic for MSNR specifically, since its TP is a real
         structural level rather than a bounded ROI-ladder step, unlike
         FT5's) against a 10-trade sample at 50% winrate with tightly-
         clustered wins — confirmed the smaller sample's score (0.60)
         DID outrank the larger one's (0.48). The lower-confidence-bound
         formula (v0.99.19) was doing its statistically correct job —
         genuinely wide variance legitimately lowers confidence in a
         mean, even at n=55 — but that exposed a deeper, separate gap:
         msnr_rank_by_winrate_sample() (the autotrade-eligibility
         ranking) had NO minimum sample size at all, while msnr_compute_
         live_universe() (which decides LIVE-SCAN promotion) already
         requires closed_n > MSNR_LIVE_PROMOTE_MIN_SAMPLE. A tiny-sample
         symbol could therefore rank into the autotrade top N purely via
         score, showing the user a checkbox that would be entirely
         INERT in practice — msnr_live_loop() only ever scans symbols
         already in the promoted live_universe, so a symbol that never
         cleared the promotion sample floor can never actually fire
         regardless of what its autotrade toggle says. The autotrade-
         eligibility gate being LOOSER than the live-scan-visibility
         gate was backwards.
         Fixed by requiring the SAME MSNR_LIVE_PROMOTE_MIN_SAMPLE floor
         in msnr_rank_by_winrate_sample() before a symbol is even
         considered for ranking — the two gates are now consistent.
         Re-verified the exact reproduced case after the fix: the n=10
         symbol (whose raw score was still numerically higher) is now
         correctly excluded from the ranking entirely, while the n=55
         symbol remains eligible and gets a fair shot at the top N.
         Verified with py_compile, an actual runtime start, pyflakes,
         the route/def integrity check, and the stale-default-parameter
         check — all clean.

v0.99.21 - CRITICAL FIX: get_tickers() gained the same HTTP 429 retry
         logic get_candles() already got in v0.99.8 — this function was
         somehow never given that fix at the time, and it's a much more
         severe gap here than it looked: msnr_build_backtest_universe()
         calls get_tickers() BEFORE msnr_backtest_loop() ever sets
         STATE["msnr_backtest_running"]=True, so an un-retried 429 here
         meant the whole backtest cycle could fail before the progress
         bar (v0.99.15) had any chance to show anything at all — worse
         than the original "stuck, no detail" problem that progress bar
         was specifically built to fix, since now there was no visible
         indication a cycle was even being attempted. Direct user
         report: "версия обновилась, но минут 20 ничего не происходит,
         шкалы загрузки нет" — exactly this symptom, especially given
         this session's own confirmed sustained Gate.io rate-limit
         pressure hitting many other endpoints throughout.
         Caught and fixed a self-inflicted bug while implementing the
         fix, before shipping: first pass left TWO separate docstring
         literals in a row (the second one silently became a no-op
         expression statement, not documentation) and an unreachable
         trailing `raise last_err` after the while-True loop — same
         class of mistake this session already made once for get_
         candles() itself. Caught by re-viewing the whole function
         after editing (not just running py_compile, which doesn't
         flag either issue) — merged into one docstring, removed the
         dead code and the now-unused last_err variable.
         Verified behaviorally, not just read as fixed: mocked two
         consecutive 429 responses followed by success, confirmed
         get_tickers() retries through them and returns the data.
         Also searched systematically for the same unretried-429
         pattern across every other function making a direct requests.
         get() call — found four more (get_contracts, get_contract_
         stats, get_contract_spec, get_futures_risk_limit_tiers).
         get_contracts() turned out to be genuinely dead code (defined,
         never called anywhere) — not worth touching. The other three
         ARE used, and two of them (get_contract_spec, get_futures_
         risk_limit_tiers) sit on the AUTOTRADE order-placement path
         (leverage, tick size, risk limits) — deliberately left alone
         this round rather than rushing a change to real-money-order
         code without the same careful behavioral verification given to
         everything else this session; flagged directly instead of
         silently left for later.
         Verified with py_compile, an actual runtime start, pyflakes,
         and the route/def integrity check — all clean.

v0.99.22 - Per direct user request, following a screenshot review of the
         MSNR backtest's expanded per-symbol trade list: the displayed
         "avg R / med R" is avg_rr/median_rr from msnr_summarize_
         backtest() — averaged over EVERY closed trade's TARGET rr,
         including LOSSES, not the trade's actual realized outcome. A
         losing trade whose TP target was 6.89R away still counts as
         +6.89R toward that average even though it hit SL, which is why
         the number looked implausibly good next to a sub-50% win rate.
         Confirmed this doesn't affect scoring/ranking (msnr_ranking_
         score() already uses each WIN's own rr and -1.0 per LOSS,
         correctly) or the existing Expectancy column (expectancy_r,
         same correct math) — purely a misleading-if-misread display
         label, not a functional bug.
         User's actual ask, though, wasn't "fix the average" — it was
         "per coin, find RR ranges that are statistically bad and skip
         those signals for that coin", i.e. a system-stability filter,
         not a return-chasing one. MSNR_MAX_RR already does something
         adjacent (_risk_autotune_msnr_max_rr(), via msnr_rr_bucket_
         stats()) but pools trades across ALL symbols specifically
         because a single symbol's own sample is usually too small to
         trust — leaving no way to catch a symbol whose OWN pattern is
         bad even though the pooled average looks fine.
         New msnr_symbol_rr_skip_min(trades): per-symbol counterpart —
         buckets THIS symbol's own closed backtest trades by rr (same
         msnr_rr_bucket_stats()), finds the lowest bucket with >=
         MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE (new setting, default 15 —
         deliberately higher than the pooled rule's sample bar, since
         this judges one symbol off its own trades only) of this
         symbol's own trades AND failing breakeven at its own actual
         average realized rr (not the bucket's lower edge — same fix
         the pooled rule already needed, lo=0 on the first bucket
         implies a nonsensical 100% breakeven). One-directional like
         the pooled rule: only ever adds a skip floor off solid
         evidence, never loosens one back out on its own.
         msnr_optimize_symbol() now computes this off the winning
         combo's own best_results (not re-run per grid combo) and
         stores it as "skip_rr_min" in STATE["msnr_symbol_overrides"].
         New msnr_symbol_skip_rr_min(symbol) reads it back — kept
         DELIBERATELY separate from msnr_symbol_params(), whose return
         value gets spread as **params straight into msnr_detect_
         signals() at three call sites with no skip_rr_min kwarg in
         that signature; folding it in there would have thrown
         TypeError at all three, not just the live scanner that needs
         it. Caught this before shipping by grepping every msnr_symbol_
         params() call site, not just the one being edited.
         msnr_scan_symbol_live() computes the live signal's own rr
         (same reward/risk formula msnr_run_backtest() uses — msnr_
         detect_signals() itself doesn't compute rr) and skips firing
         entirely (not a fallback target, an actual skip — matches
         "пропускать" in the user's own request) once rr >= this
         symbol's skip_rr_min, if one is set.
         UI: backtest table's params column now appends "skip rr≥X" in
         loss-red when a symbol has an active skip floor, so it's
         visible at a glance which coins are being filtered and where.
         Verified with py_compile, an actual runtime start (incl. a
         synthetic 20-trade bucket to confirm msnr_symbol_rr_skip_min()
         actually returns the failing edge), pyflakes, node --check on
         the extracted JS (first extraction attempt grabbed the WRONG
         <script> occurrence — this changelog literally contains the
         string "<script>" earlier in this same entry's own explanation
         of a past instance of that exact mistake — switched to the
         last-occurrence approach per that established convention), the
         Flask route/def integrity check, and grep across every msnr_
         symbol_params() call site for the **params spread issue above.
         (The wrong-<script>-occurrence mistake reproduced here was
         against an EARLIER changelog entry elsewhere in this same
         docstring that happens to mention the literal string
         "<script>" in its own prose — a naive first-occurrence regex
         grabs that prose instead of the real HTML template, which
         reliably comes last in the file; fixed by taking the LAST
         occurrence instead, same lesson already learned once before.)

v0.99.23 - Direct user follow-up to v0.99.22: "so maybe backtest signals
         failing skip_rr_min shouldn't be counted/shown either" — v0.99.22
         only stopped FIRING new live signals past a symbol's own skip
         floor; the backtest trade list and its aggregate stats (n/W/L/T,
         avg/med R, Expectancy, Score) still included every trade,
         including the ones the skip floor says shouldn't count as part
         of this symbol's system.
         msnr_optimize_symbol() now filters best_results in this exact
         order: (1) run the winning grid combo's full backtest, (2)
         derive skip_rr_min off that FULL unfiltered set (msnr_symbol_
         rr_skip_min() needs the complete sample for its own min-sample
         gate to mean anything), (3) ONLY THEN drop every trade whose
         own rr >= skip_rr_min (closed trades AND timeouts alike — a
         timeout in a bad bucket is still evidence against it, no
         reason to keep it) and recompute trades/wins/losses/timeouts/
         winrate/avg_rr/median_rr/expectancy_r/score off what's left.
         Filtering before deriving the threshold would have shrunk the
         very evidence msnr_symbol_rr_skip_min()'s sample-size gate
         relies on — checked this ordering explicitly before shipping.
         This filtered best_results is what both /api/msnr/backtest/
         <symbol> (the expanded per-trade list) and the summary table
         (n/W/L/T/avg/med/Expectancy/Score columns) now show — the
         numbers on screen and the numbers backing autotrade eligibility
         are the same numbers a user drilling into a symbol would see.
         Caught a real side effect before shipping, not after: msnr_
         backtest_results (the same dict the filtered trades now live
         in) was ALSO the pooled source for two things that need the
         FULL unfiltered picture — _risk_autotune_msnr_max_rr()'s
         global cap tuning and /api/msnr/status's rr_buckets display,
         both of which pool trades across every symbol specifically
         BECAUSE any one symbol's own sample is usually too small to
         trust (that's the whole reason MSNR_MAX_RR is a single global
         cap instead of per-symbol in the first place — see that
         function's own docstring). Pointing them at the newly-filtered
         dict would have quietly starved them of exactly the bad-RR
         evidence they exist to catch, once a symbol's own skip filter
         had already removed it. Fixed by keeping a SEPARATE raw copy:
         msnr_optimize_symbol() now returns (override, filtered_
         results, raw_results) instead of two values; new STATE key
         msnr_backtest_results_raw holds the unfiltered per-symbol
         trades, and both call sites (_risk_autotune_msnr_max_rr's
         pooling and api_msnr_status's rr_buckets) were switched to
         read from it instead of the now-filtered msnr_backtest_results.
         Also cleared on /api/reset/msnr alongside the existing key.
         Verified with py_compile, an actual runtime start (synthetic
         30-trade set: a bad 5.5R bucket at 2W/18L alongside a good 2.0R
         bucket at 6W/4L — confirmed skip_rr_min=5 and the filtered
         summary reports exactly the surviving 10 trades, 60% win rate),
         pyflakes, node --check on the correctly-last <script> block,
         the Flask route/def integrity check (still 63 routes), and an
         AST walk for duplicate top-level defs (none introduced).

v0.99.24 - Direct user request: compute a real $ profit figure per symbol
         in the backtest, described exactly as "$40 margin at 10x on the
         first trade, then the WHOLE resulting balance at the same
         leverage on the next trade, and so on through every trade" —
         a compounding position-sizing simulation, deliberately
         separate from the R-multiple stats (avg/med R, Expectancy)
         already shown, which measure the strategy's edge independent
         of how much money is actually put behind each trade.
         New msnr_compound_return(trades, start_balance=None,
         leverage=None): walks a symbol's CLOSED (WIN/LOSS) trades in
         chronological order (the order they're already stored in),
         starting at MSNR_COMPOUND_START_BALANCE (new setting, default
         $40, matching the user's own example) at AUTOTRADE_LEVERAGE_
         MSNR (existing setting, already defaults to 10x — reused
         rather than a new separate leverage constant so the
         simulation always matches whatever leverage this symbol would
         actually trade at live, not a number that can drift out of
         sync with it). Each trade's own entry/sl/tp (not the stored
         rr field) gives the exact price-move %, scaled by leverage
         against the CURRENT balance — genuinely "reinvest it all,"
         not a fixed-fraction model. TIMEOUT trades are skipped (no
         exit price is ever recorded for them — msnr_track_outcome()'s
         own return shape — so there's no realized P&L to compound
         with); floors a single loss at -100% of margin (isolated-
         margin liquidation, same as real Gate.io futures — can't lose
         more than what was put up) and stops the whole simulation the
         moment balance hits 0, since every trade after that is a
         mathematically guaranteed $0-in-$0-out no-op.
         msnr_optimize_symbol() computes this off best_results — the
         SAME post-skip_rr_min-filtered list the R-multiple stats now
         use (v0.99.23), not raw_results — so the compounding
         simulation reflects what this symbol's system would actually
         trade, not signals it's already been told to skip. Stored as
         compound_final_balance/compound_return_pct/compound_blown_at
         in the symbol override dict.
         UI: per direct user instruction ("в строке параметров" — in
         the params row), appended to the SAME params-column string
         skip_rr_min already writes to (v0.99.22), not a new table
         column — e.g. "доход +187.3% ($40→$114.92)", red with a
         "слив на #N" note when the account hit zero partway through.
         api_msnr_status()'s config block gained compound_start_
         balance/compound_leverage so the UI can show the real $
         figures the simulation ran with, not hardcoded ones.
         Verified with py_compile, an actual runtime start with two
         hand-checked synthetic cases (a WIN then a LOSS: 40 -> 120 ->
         60, exactly matching manual arithmetic; a single >100%-of-
         margin LOSS: confirmed balance floors at exactly 0, return
         -100%, blown_at_trade=1, and a trailing WIN after it is
         correctly never counted), pyflakes, node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (still 63 routes), an AST walk for duplicate top-level
         defs (none introduced), and confirmed msnr_compound_return()'s
         start_balance/leverage defaults resolve live at call time (not
         frozen at def time) — same stale-default class of bug already
         fixed once this session for msnr_detect_signals()'s max_rr.

v0.99.25 - Direct user follow-up, after screenshotting the live table:
         APR_USDT ranked #2 by score (0.5501) despite its own compound
         "доход" reading -100% ($40→$0, слив на #40) — the user wants
         to see the compounding balance next to EACH trade once a
         symbol's row is expanded, to verify the math trade-by-trade
         BEFORE deciding whether/how top-10 ranking needs to account
         for this kind of blow-up risk (score currently only reflects
         R-multiple stats, nothing about compounding survival).
         Refactored msnr_compound_return() around a new msnr_compound_
         trail(trades, start_balance=None, leverage=None): the exact
         same per-trade walk (entry/sl/tp-derived price move × leverage
         against the CURRENT balance, TIMEOUT/malformed trades skipped,
         isolated-margin -100% floor, stops the moment balance hits 0),
         but returns one row per actually-compounded trade — {time,
         direction, result, pnl_pct, balance_before, balance_after} —
         instead of collapsing straight to a final number. msnr_
         compound_return() is now a thin reduction over this same
         trail (final row's balance_after, len(trail) as trades_
         compounded), so the per-trade display and the summary "доход"
         figure share one calculation and can never silently disagree.
         /api/msnr/backtest/<symbol> now runs msnr_compound_trail() on
         that symbol's trades and annotates each with compound_
         balance_before/after/pnl_pct before returning them. Matched
         back to trades by (time, direction), not time alone — caught
         before shipping that an A-shape and V-shape level can
         structurally resolve on the exact same entry candle (msnr_
         detect_signals() checks them in separate if-blocks, not
         elif), which would collide on a time-only key and silently
         attribute one trade's balance to the other; verified with a
         synthetic same-timestamp LONG+SHORT pair that each correctly
         got its own distinct balance back. A trade past the point the
         account hit $0 (or a TIMEOUT) has no trail entry — balance_
         before/after come back null for it rather than a misleading
         $0, same "never actually reached" reasoning the compounding
         functions already used.
         UI: loadMsnrTrades() gained a "Баланс" column showing each
         trade's own balance_after and pnl_pct (green/red by sign),
         dim "—" for trades with no trail entry — right next to the
         existing per-trade Entry/SL/TP/RR/Result columns, so the
         compounding math is checkable trade-by-trade exactly where
         the user asked for it.
         Explicitly NOT touched this round, per the user's own
         sequencing ("сначала проверить, потом пересмотреть топ-10"):
         msnr_ranking_score()/the score column itself — still pure
         R-multiple, no compounding/ruin-risk awareness yet. Flagged
         directly rather than silently bundled in, since that's a
         separate decision (how to weigh blow-up risk against
         win-rate) waiting on the user confirming this trade-by-trade
         math is correct first.
         Verified with py_compile, an actual runtime start (5-trade
         synthetic case — WIN/LOSS/TIMEOUT/blow-up-LOSS/trailing-WIN —
         confirmed the trail has exactly 3 rows [40→120→60→0], the
         TIMEOUT and the post-blow-up WIN are correctly absent, and
         msnr_compound_return() built from the SAME trail agrees
         exactly: -100%, blown_at_trade=3; a separate same-timestamp
         LONG+SHORT synthetic pair confirmed the (time, direction) key
         keeps their balances distinct), pyflakes, node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (still 63 routes), and an AST walk for duplicate
         top-level defs (none introduced).

v0.99.26 - Direct user follow-up, after confirming the compounding math
         (v0.99.25's per-trade "Баланс" column) checked out on
         APR_USDT: the trade that blew the account to $0 had a SL 12.25%
         wide, which at 10x leverage means a -122.5% margin move —
         floored to -100%, but structurally that same 12.25% move would
         have hit Gate.io's own liquidation price BEFORE ever reaching
         that SL, at roughly a 9.3% adverse move (confirmed by hand:
         compute_scalp_liquidation_move_pct('SHORT', 10, 0.6%) = 9.29%).
         Two asks: (1) "фильтр по ширине стопа" — a statistical filter
         by SL width, symmetric to skip_rr_min; (2) "узнавать
         максимальное плечо на бирже... уже где-то в коде реализовано" —
         and it was: execute_autotrade() has run exactly this
         liquidation check since v0.70.0 for every OTHER mode
         (bounce/breakout/divergence/ema/session), just never wired
         into MSNR's backtest/live-signal path — only applied reactively
         at real order time, too late to keep a bad trade out of the
         backtest stats or a live signal from ever showing up.
         New msnr_sl_bucket_stats()/msnr_symbol_sl_skip_min(): SL-width
         counterparts to msnr_rr_bucket_stats()/msnr_symbol_rr_skip_min()
         — same MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE bar, same one-directional
         stance, bucketed by SL-distance % (new MSNR_SL_PCT_BUCKETS:
         0-2/2-4/4-6/6-10/10+) instead of rr. Deliberately separate from
         the RR filter: a symbol can have fine RR ratios while still
         routinely eating unusually WIDE-in-%-terms stops — RR alone
         doesn't capture that.
         New msnr_symbol_effective_leverage(symbol): AUTOTRADE_LEVERAGE_
         MSNR clamped to this contract's own leverage_max (get_
         contract_spec()) — the EXACT clamp execute_autotrade() already
         applies before a real order, reused rather than reimplemented.
         New msnr_trade_beyond_liquidation(symbol, direction, entry, sl,
         leverage=None): the EXACT liquidation-safety check execute_
         autotrade() already runs (same compute_scalp_liquidation_
         move_pct() formula, same STATE["scalp_mmr_map"] source with
         its own "MMR is a property of the contract, not the module"
         reasoning quoted verbatim, same SCALP_SAFETY_MARGIN buffer) —
         deterministic, not statistical, applied proactively here
         instead of only reactively at order time.
         msnr_optimize_symbol() now runs three filters on best_results
         in sequence, each recomputing trades/wins/losses/timeouts/
         winrate/avg_rr/median_rr/expectancy_r/score before the next:
         skip_rr_min (v0.99.23) -> beyond-liquidation (unconditional,
         new "liquidation_filtered_count" field) -> skip_sl_pct_min
         (new). Factored the repeated recompute block into a new
         _msnr_recompute_summary_score() helper — was about to become a
         third near-identical copy, which is exactly the kind of thing
         that quietly drifts apart over time. New "effective_leverage"
         field stored per symbol; msnr_compound_return() now runs at
         THIS symbol's effective_leverage instead of always the flat
         configured AUTOTRADE_LEVERAGE_MSNR, so a coin the exchange caps
         lower no longer shows an unrealistically optimistic "доход".
         msnr_scan_symbol_live() gained the same two live-signal gates
         (liquidation check, skip_sl_pct_min) alongside the existing
         skip_rr_min one — a signal failing either never fires, matching
         what execute_autotrade() would also reject at order time.
         New msnr_symbol_skip_sl_min(symbol) lookup, same "separate from
         msnr_symbol_params() to avoid a **params TypeError" reasoning
         msnr_symbol_skip_rr_min() already documented.
         UI: params row gained "skip SL≥X%" (loss-red), "N за
         ликвидацией" when the liquidation filter actually dropped
         trades, and "плечо Nx (лимит биржи)" when this symbol's
         effective leverage is clamped below the configured setting —
         all appended to the same string skip_rr_min/доход already
         write to, per the user's own established "в строке параметров"
         placement.
         Verified with py_compile, an actual runtime start (msnr_
         symbol_sl_skip_min on a synthetic wide-stop/bad-winrate bucket
         vs a narrow-stop/good-winrate bucket correctly isolated the
         bad one at its 6% edge; msnr_trade_beyond_liquidation() on the
         EXACT APR_USDT numbers from the screenshot — entry=0.19948,
         sl=0.223915, 10x — returned True, and a narrow-stop trade from
         the same symbol's own history returned False; confirmed the
         liquidation filter alone drops exactly the one trade that blew
         the account from a 2-trade synthetic list; confirmed msnr_
         symbol_effective_leverage() degrades to the configured default
         rather than raising when get_contract_spec() fails over the
         network), pyflakes, node --check on the correctly-last
         <script> block, the Flask route/def integrity check (still 63
         routes), an AST walk for duplicate top-level defs (none
         introduced, 6 new functions all present), and confirmed msnr_
         trade_beyond_liquidation()'s leverage default resolves live at
         call time rather than being frozen — same stale-default class
         already fixed twice this session.

v0.99.27 - Direct user follow-up, with a real live example: SKHY_USDT
         ranked highly by score (0.4006, expectancy +0.75R) despite its
         own $ compound simulation losing -67.6% ($40→$12.96) even
         AFTER the v0.99.26 liquidation filter dropped 8 of its own
         trades. Discussed three options (rank by geometric/compound
         return instead of R; keep R-based score but add a penalty for
         a weak compound result; or a hard gate — fails the $ stress
         test, doesn't rank at all, regardless of score). User picked
         the gate: "давай 3 пункт, просто не попадает в топ."
         New "stress_test_failed" field on the symbol override dict,
         set in msnr_optimize_symbol() right after the compound
         simulation: True when compound_return_pct is not None and <=
         0 (covers any loss, including a full blow-up to 0) — None
         (no compound result at all, e.g. zero trades survived
         filtering) deliberately reads as "no evidence either way," not
         silently as "passed."
         This is a HARD GATE, not a score penalty, applied in two
         places so it can't be outweighed by an otherwise-strong score:
         msnr_rank_by_winrate_sample() now excludes stress_test_failed
         symbols from its candidate list entirely — this is what feeds
         msnr_autotrade_eligible_symbols(), so a failed symbol can never
         become autotrade-eligible no matter its score. api_msnr_
         status()'s own `ranked` sort (the full table's default order)
         now sorts by (not stress_test_failed, score) instead of score
         alone, so a failed symbol sinks below every symbol that
         passed regardless of how good its score looks — it can still
         be found by scrolling, but structurally can't land near the
         top of the table the user actually looks at.
         UI: loadMsnrTrades()'s own client-side re-sort (which
         overrides backend order and already groups autotrade_eligible
         to the top) gained the same stress_test_failed tier, one level
         below eligible — mirrors the same "sort key doesn't matter,
         this tier wins" logic used for the existing eligible/not-
         eligible split, and can't collide with it since msnr_rank_by_
         winrate_sample() already keeps a failed symbol out of
         eligibility in the first place, so within the eligible group
         this check is always false. New separator row ("— провалили
         $-симуляцию депозита ... —", red) at exactly the boundary
         where failed rows begin, same v0.99.19 pattern already used
         for the eligible/rest boundary.
         Verified with py_compile, an actual runtime start (a synthetic
         two-symbol case — BAD_USDT at score 0.6 but stress_test_
         failed=True vs GOOD_USDT at score 0.3, stress_test_failed=
         False — confirmed msnr_rank_by_winrate_sample() returns ONLY
         GOOD_USDT despite BAD_USDT's higher raw score; confirmed the
         stress_test_failed condition against three concrete cases:
         -67.6% -> True, +108.1% -> False, no compound result at all
         -> False), pyflakes, node --check on the correctly-last
         <script> block, the Flask route/def integrity check (still 63
         routes), and an AST walk for duplicate top-level defs (none
         introduced).

v0.99.28 - Direct user request after a live portrait-mode phone
         screenshot of the MSNR backtest table: "может сделать мельче
         и с меньшим отступом чтобы больше в ширину влазило инфы?" —
         the mobile @media (max-width:640px) block (v0.89.0) already
         shrank table cells once (from the 8px 10px / 13px desktop
         default down to 6px 8px / 12px), but on a genuinely narrow
         phone in portrait that still wasn't tight enough for a wide
         multi-column table like MSNR's (Symbol/Авто/Win-rate/n/W/L/T/
         RR/Expectancy/Score/Параметры) — most of the visible width
         went to padding rather than data, forcing horizontal scroll
         for columns that could otherwise fit.
         th, td padding tightened 6px 8px -> 4px 6px, font-size 12px
         -> 10.5px (matching the size already used for #status/
         #overview/#autotradeBanner on mobile, not an arbitrary new
         number). CSS-only, one shared rule — applies to every table on
         the page (the same "works for both static and dynamically-
         injected tables" reasoning the v0.89.0 comment above it
         already documented), not just MSNR's, since every other
         module's backtest table (FT5/VGI/session/etc) is built the
         same dense multi-column way and benefits equally.
         behaviorally re-verify beyond confirming nothing else broke.

v0.99.29 - Direct user report: expanding a signals/trade list and
         swiping right on the resulting wide table kept snapping back
         to the left every couple seconds — impossible to actually
         read anything past the first few columns. Root cause:
         refreshAll() re-fetches and rebuilds EVERY module panel on a
         15s timer (setInterval(refreshAll, 15000)), and each refresh*
         function does a full `panel.innerHTML = ...` rebuild — which
         tears down and recreates every DOM element inside it,
         discarding whatever scrollLeft the person's mid-swipe had set
         on the wide table. Not an MSNR-only bug: every module panel
         (scalp/session/session_ny/xau_lg/msnr/ft5/vgi/autotrade/
         simulator) rebuilds the exact same way on the same timer —
         grepped every `panel.innerHTML =` call site (13 total) rather
         than patching only the one in the screenshot. Two were
         checked and correctly excluded: refreshDivergence and
         refreshEma's panels are plain stat divs, no <table> at all,
         nothing to preserve.
         New setPanelHtml(panel, html): captures scrollLeft from every
         scrollable element in the panel (scrollWidth > clientWidth)
         BEFORE the innerHTML rebuild, then restores those same values
         onto the Nth scrollable element found AFTER the rebuild —
         positional matching, not id-based, since the HTML is rebuilt
         from scratch every cycle with no stable element ids to match
         against, but which tables appear and in what order is stable
         cycle-to-cycle in the overwhelmingly common case (same
         symbols, same sort). Swapped in at all 11 applicable call
         sites (9 single-line statements plus 3 multi-line template
         literals, where only the opening `panel.innerHTML = ` and the
         closing `` `; `` needed to change to `setPanelHtml(panel, `
         and `` `); `` respectively — the HTML content itself
         untouched) via precise line-number edits rather than str_
         replace, since three of these lines are textually identical
         to each other and wouldn't have matched uniquely.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the correctly-last <script> block, a
         standalone Node simulation of setPanelHtml() against a mock
         DOM (a fake scrollable element starting at scrollLeft=157,
         whose innerHTML setter mimics real DOM behavior by resetting
         scrollLeft to 0 on assignment — confirmed the wrapped call
         restores exactly 157 afterward, where an unwrapped assignment
         would have left it at the reset 0), a grep confirming exactly
         13 setPanelHtml( occurrences (12 call sites + the function's
         own definition) and zero unintended remaining bare `panel.
         innerHTML =` assignments outside the helper itself and the
         two intentionally-untouched table-less panels, the Flask
         route/def integrity check (still 63 routes), and an AST walk
         for duplicate top-level defs (none introduced — this was a
         JS-only change, but re-ran the check as a matter of course).

v0.99.30 - Direct user follow-up ("давай закрепим") after v0.99.29 fixed
         horizontal scroll actually surviving a refresh cycle: sitting
         on a stable scroll position for a few seconds without any way
         to tell which ROW you're looking at (Symbol is the first
         column, scrolled off to the left) was the next obvious
         friction point on a wide table.
         Mobile-only (@media max-width:640px, same scope as every other
         table-density rule already in this block): `th:first-child,
         td:first-child { position:sticky; left:0; }`. Works precisely
         BECAUSE the table itself is the horizontal-scroll container
         (v0.89.0's `table { overflow-x:auto }` rule) — sticky sticks
         relative to its nearest SCROLLING ancestor, so pinning against
         page-level scroll would've done nothing here; it had to be
         this specific rule that made it work. Needed an explicit
         background color (#0b0e14, the body background) rather than
         leaving it transparent — a "sticky" cell with no opaque
         background just lets every other column's text visibly scroll
         underneath it, defeating the entire point; added a matching
         `tr:active td:first-child` background too so the pinned Symbol
         cell doesn't look visually disconnected from the rest of a
         tapped row's highlight.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the correctly-last <script> block, and the
         Flask route/def integrity check (still 63 routes) — CSS-only,
         no Python logic or JS control flow changed.

v0.99.31 - Direct user report: "Шапка относительно таблицы съезжает" —
         the header row drifting out of alignment with the body as a
         wide table gets scrolled. Root cause, found by auditing every
         <table> in the page: the v0.89.0 mobile rule put `display:
         block; overflow-x:auto` directly ON every <table> element,
         making the table ITSELF a scroll container — fine for the 4
         tables that had no OTHER scroll container (the 3 static
         signals/div/ema tables, and loadMsnrTrades()'s per-trade
         table), but 17 other dynamically-built tables (MSNR backtest,
         session, ft5, vgi, etc) were ALREADY wrapped in their own
         `<div style="overflow-x:auto;">`, so those ended up with TWO
         independent, nested horizontal scroll containers per table.
         That double-nesting is exactly what broke it: v0.99.30's
         `position:sticky` resolves against whichever scroll container
         is nearest, and with two stacked ones, which one actually
         ends up "nearest" doesn't reliably match where the visible
         scroll offset lives; separately, `display:block` on <table>
         also breaks the browser's native guarantee that thead and
         tbody share one column grid, letting each auto-size
         independently — a second, unrelated source of the exact same
         symptom.
         Fixed at the root rather than patched around: <table> no
         longer overrides display or scrolls on its own at all (stays
         native `display:table`, keeping thead/tbody on one shared
         column grid) — ALL horizontal scrolling now goes through the
         div wrapper alone, everywhere, so there's exactly one scroll
         ancestor per table for sticky to resolve against, never two.
         Added the missing wrapper to the 4 tables that didn't have
         one: the 3 static tables in the HTML skeleton (signalsTable/
         divTable/emaTable — their existing id-based `.style.display`
         JS toggles keep working unchanged, since wrapping in a div
         doesn't move or rename the table element itself) and
         loadMsnrTrades()'s per-trade table. New `div[style*=
         "overflow-x:auto"]` attribute-substring selector picks up
         momentum scrolling (-webkit-overflow-scrolling:touch) and
         max-width:100% on every EXISTING wrapper div without touching
         17+ render functions just to add a shared class name to
         each's already-consistent inline style — checked it doesn't
         accidentally also match .tabs or #headerTop's own div (both
         get overflow-x:auto from an external class/media rule, not an
         inline style attribute, so the substring genuinely isn't
         present in their markup).
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 63 routes), an AST walk for
         duplicate top-level defs (none introduced), and manually
         re-inspected the edited static-table skeleton and the
         loadMsnrTrades() template string for balanced div/table
         nesting (every opened div has exactly one matching close).

v0.99.32 - Direct user question: "Был недавно сигнал но уведомления не
         было как и авто открытия, условий не нужно дополнительных,
         достаточно топ 10 плюс галочка." Traced msnr_live_loop() end to
         end and found a real architecture gap between two DIFFERENT
         promotion criteria that were never reconciled: the autotrade
         checkbox's own eligibility (msnr_autotrade_eligible_symbols(),
         top MSNR_AUTOTRADE_TOP_N by SCORE — a lower-confidence-bound on
         mean R) is entirely separate from msnr_live_universe (msnr_
         compute_live_universe(), v0.99.17 — requires winrate > 50% AND
         >40 closed trades). Nothing guarantees a symbol clearing one
         also clears the other: score and raw winrate measure different
         things, so a symbol can rank comfortably in the autotrade top
         10 while sitting at, say, 44% winrate — well under the live-
         promotion bar. Confirmed with a synthetic symbol at exactly
         that shape: eligible for autotrade, absent from live_universe.
         The consequence was silent and total: msnr_live_loop() only
         ever calls msnr_scan_symbol_live() for symbols IN live_
         universe — a symbol outside it is simply never scanned, so
         checking its autotrade box did nothing whatsoever. No signal
         gets recorded, no Telegram notification fires, no order gets
         placed — not "blocked by a filter," literally never evaluated
         — regardless of how the checkbox looks in the UI. This matches
         the report exactly: an eligible, checked symbol producing
         neither a notification nor an order.
         Fixed in msnr_live_loop(): live_universe is now unioned with
         every symbol the person has explicitly toggled autotrade ON
         for AND that's currently autotrade-eligible (top-N by score,
         not stress_test_failed) — so checking that box is now
         sufficient on its own to guarantee the symbol gets scanned,
         matching the user's own stated expectation, without touching
         msnr_live_universe's existing winrate-based promotion for
         everything else (still drives what's scanned but NOT
         individually toggled — unaffected).
         Explicitly did NOT touch, and want to be clear these are a
         different category from the bug above: the skip_rr_min/skip_
         sl_pct_min/liquidation checks inside msnr_scan_symbol_live()
         itself (v0.99.22/26) — those were added at this same user's own
         earlier direct request this session and are deliberate safety
         filters a signal must still pass even once scanned, not an
         accidental gap; nor has_open_signal_any_module()'s cross-module
         open-position lock, which is an intentional guard against
         stacking multiple modules' positions on the same symbol.
         Verified with py_compile, an actual runtime start (synthetic
         symbol at winrate 44.4%/score 0.5: confirmed msnr_autotrade_
         eligible_symbols() includes it while msnr_compute_live_
         universe() excludes it — reproducing the gap directly — then
         confirmed the union logic correctly merges it back in once
         autotrade_symbols marks it toggled-on), pyflakes, the Flask
         route/def integrity check (still 63 routes), and an AST walk
         for duplicate top-level defs (none introduced).

v0.99.33 - Direct user request: "чёткий размер позиции, 40 долларов для
         первой сделки, размер второй сделки зависит от исхода первой,
         по сути как на бэктесте... начинать с 40," hard-capped at $500,
         and only for LIVE signals — the backtest's own compounding
         simulation (msnr_compound_return/trail, v0.99.24-25) stays
         exactly as-is, unaffected. Until now every MSNR autotrade order
         used the shared AUTOTRADE_SIZE_MODE/VALUE every OTHER mode
         also uses — no connection at all to a symbol's own trade
         history.
         New MSNR_LIVE_BALANCE_MAX (500.0) alongside the existing
         MSNR_COMPOUND_START_BALANCE ($40, already used by the backtest
         sim — reused here rather than a second constant for the same
         number). New STATE["msnr_live_balance"]: symbol -> current
         REAL margin in USD; missing means never autotrade-fired yet.
         New msnr_live_balance_for_symbol(symbol): returns the stored
         balance clamped to [0, MSNR_LIVE_BALANCE_MAX], or MSNR_
         COMPOUND_START_BALANCE if the symbol has none yet — this IS
         the size a new order gets.
         New msnr_update_live_balance(symbol, result, entry, sl, tp,
         leverage): the live counterpart of msnr_compound_trail()'s own
         per-trade math — deliberately the EXACT same formula (price
         move % from entry/sl/tp, scaled by leverage, isolated-margin
         floor at -100%), not a parallel reimplementation that could
         drift from it. Result additionally capped at MSNR_LIVE_
         BALANCE_MAX (the backtest sim has no such ceiling — a real
         account isn't supposed to compound unbounded) and floored at
         0 (a wiped symbol prices future orders at $0 margin, which
         compute_position_size() already skips rather than sending a
         doomed order — same passive-stop the backtest's own blown
         trail already has, no separate kill-switch needed).
         msnr_scan_symbol_live() now resolves this symbol's effective
         (contract-capped) leverage ONCE via msnr_symbol_effective_
         leverage() and passes it straight to execute_autotrade()
         together with size_mode="fixed", size_value=msnr_live_
         balance_for_symbol(symbol) — replacing the flat AUTOTRADE_
         LEVERAGE_MSNR/shared-size call. Each live signal record now
         also carries autotrade_fired/live_size_usd/leverage_used, so
         update_msnr_signal_outcomes() can tell WHICH closed signals
         actually had real money behind them (only those should move
         the balance — a signal nobody traded touching TP/SL by chance
         must not compound anything) and calls msnr_update_live_balance()
         with the exact leverage that specific order used, called
         OUTSIDE the state_lock block since that function takes its
         own lock and state_lock isn't reentrant (threading.Lock(), not
         RLock — checked before writing the call site, not after).
         UI: the live-signals table gained a "Размер" column showing
         "$X @ Yx" for autotrade-fired signals, dim "—" otherwise.
         Caught and fixed a self-inflicted mistake before shipping: an
         early str_replace edit adding the two new functions
         accidentally swallowed msnr_trade_beyond_liquidation()'s own
         `def` line and docstring opening, leaving orphaned docstring
         body text with no function header — caught immediately by
         re-grepping for that function's def line, found it missing,
         and repaired the exact three-line header before proceeding to
         any further edits or verification.
         Verified with py_compile, an actual runtime start (synthetic
         symbol: confirmed the very first balance reads exactly $40;
         a +200%-move WIN scaled it to $120, a second identical WIN to
         $360, a third correctly clamped at the $500 cap instead of
         continuing to compound past it; a separate synthetic LOSS with
         an 11%-wide stop at 10x correctly floored the balance at $0),
         pyflakes, node --check on the correctly-last <script> block,
         the Flask route/def integrity check (still 63 routes), and an
         AST walk for duplicate top-level defs (none introduced — all
         three new functions present exactly once).

v0.99.34 - Direct user question: "как добавить сигналы по mnsr в
         симулятор?" Confirmed the wiring already exists — sim_
         execute_trade() gets called for every MSNR signal an autotrade
         order actually fires for, same as every other module, by
         DESIGN: the paper simulator mirrors what real autotrade would
         do once a module's own per-symbol toggle is on, not a shadow-
         mode running for every signal unconditionally, regardless of
         the toggle — this exact question was investigated and
         confirmed intentional once before, back in v0.99.7. So the
         answer to "how do I add MSNR to the simulator" is: check the
         autotrade box for at least one eligible MSNR symbol (gold, or
         a top-MSNR_AUTOTRADE_TOP_N-by-score symbol) — no separate
         simulator-only setting exists or is needed.
         Found and fixed a real gap while re-checking this call site,
         though: v0.99.33 wired the new per-symbol live-balance
         compounding sizing into the REAL execute_autotrade() call
         (size_mode="fixed", size_value=<this symbol's own compounding
         balance>) but missed updating the sim_execute_trade() call
         right next to it, which was left defaulting to the shared
         AUTOTRADE_SIZE_MODE/VALUE — meaning the paper simulator would
         have silently shown a DIFFERENT position size than what the
         real order actually risked, for every MSNR trade, undermining
         the entire point of it being a faithful mirror. Passed the
         same size_mode="fixed"/size_value=live_size to sim_execute_
         trade() too, so both now agree.
         Verified with py_compile, an actual runtime start, pyflakes,
         the Flask route/def integrity check (still 63 routes), and an
         AST walk for duplicate top-level defs (none introduced).

v0.99.35 - Direct user question about the green ● dot: after v0.99.32
         unioned toggled-on+eligible symbols into what msnr_live_loop()
         actually scans, that union was built INLINE inside the loop
         itself and never written back anywhere api_msnr_status() could
         see — so the dot the person actually looks at kept reading the
         narrower, OLDER msnr_live_universe alone (gold + winrate>50%+
         sample>40, msnr_compute_live_universe(), v0.99.17). Net effect:
         since v0.99.32 shipped, a symbol toggled on and eligible but
         below the 50% winrate bar has been genuinely scanned live with
         no dot to show for it — exactly the mismatch the question
         surfaced, and confirmed with the QQQX_USDT example in the
         screenshot (54.2% winrate, n=49, autotrade checked — the dot's
         absence there specifically prompted the question).
         New msnr_effective_live_universe(live_universe, overrides,
         autotrade_symbols): the exact union v0.99.32 built inline,
         pulled out into its own function so it has ONE definition
         instead of two copies that can silently drift apart again.
         msnr_live_loop() now calls it instead of building the union
         itself; api_msnr_status() now runs live_universe through it
         too before computing each row's "live" flag — so the dot
         means "genuinely being scanned right now," not "cleared the
         old promotion criterion," matching what msnr_live_loop() is
         actually doing byte-for-byte, by construction, not by two
         independently-maintained pieces of logic staying in sync by
         accident.
         Verified with py_compile, an actual runtime start (synthetic
         two-symbol case reproducing the screenshot's shape — GOODWR_
         USDT at 54.2% winrate promoted by the old rule alone;
         BADWR_USDT at 44.4% winrate, toggled autotrade-on, absent from
         the old promoted set — confirmed msnr_effective_live_universe()
         correctly adds BADWR_USDT via the union, matching what msnr_
         live_loop() has been doing since v0.99.32), pyflakes, node
         --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 63 routes), and an AST walk
         for duplicate top-level defs (none introduced).

v0.99.36 through v0.99.44 - made by a different session/device on this
         same repo between this file's v0.99.35 push and this entry;
         documented inline near each change rather than here (that
         session's own convention, not this changelog's usual one) —
         see the "v0.99.3[6-9]"/"v0.99.4[0-4]" comments scattered through
         the file for the full detail. Briefly, since a future audit
         shouldn't have to re-grep all of that cold: v0.99.36 fixed a
         REAL bug where each MSNR backtest cycle wholesale-overwrote
         STATE's results/overrides instead of merging, silently dropping
         any symbol that merely errored THIS cycle (looked exactly like
         "часовой бэктест слетает без причины" from the outside) — now
         merges and only drops symbols that fell out of the universe
         entirely; v0.99.37/38 added a global cross-loop HTTP semaphore
         + rate gate after live logs showed Gate.io 500s from this app's
         AGGREGATE request volume across its 14 independent background
         loops, not any single loop; v0.99.39/43/44 iterated MSNR's
         top-10 ranking metric (avg_rr alone -> compound_return_pct
         alone -> a weighted composite of both, MSNR_TOP10_INCOME_
         WEIGHT) chasing "больше веса для дохода" without losing score's
         noise-guarding; v0.99.40 made "Очистить MSNR" actually kick off
         a fresh backtest cycle immediately (MSNR_BACKTEST_TRIGGER)
         instead of clearing the display and then sitting idle for up
         to an hour; v0.99.41 raised MSNR_BACKTEST_DAYS 30->40; v0.99.42
         is the big one worth flagging on its own — a genuine LOOKAHEAD
         bug in msnr_build_pivots(): confirm_time used the pivot bar's
         OWN timestamp instead of the confirming bar's (pivot_right bars
         later), letting both backtest AND live scanning treat a level
         as tradeable up to pivot_right x MSNR_STRUCTURE_TF early —
         inflating backtest win-rate/avg-RR on trades that used
         information not actually available yet at signal time. Fixed
         to the actual confirming bar's close time.

v0.99.45 - Direct user request: "изучи новые логи, поищи баги" (после
         обновления с v0.99.35 до v0.99.44). No runtime log access from
         this session (the app runs locally on the user's own device,
         not reachable from here) — audited the current MSNR code
         directly instead, focusing on what changed since this file's
         own last known-good state.
         Found one live bug that survived all nine of the other
         session's versions: msnr_scan_symbol_live()'s execute_
         autotrade("msnr", ...) call discarded its own return value and
         set record["autotrade_fired"] = True unconditionally right
         after — regardless of whether a real order actually opened.
         execute_autotrade() can legitimately return without opening
         anything (status "SKIPPED" from its own order-time liquidation-
         safety re-check or compute_position_size() rejecting the size;
         "ERROR" from a network/API failure; "DRY_RUN" if AUTOTRADE_
         DRY_RUN is set) — any of those still marked the signal as
         autotrade-fired, so once it later resolved WIN/LOSS, msnr_
         update_live_balance() (v0.99.33's per-symbol compounding
         balance) would compound real P&L math onto a trade that was
         NEVER ACTUALLY PLACED, silently corrupting the exact number
         the NEXT real order's size comes from — the live counterpart
         of a bug that would otherwise take weeks of drifting numbers
         to even notice.
         Fixed by capturing execute_autotrade()'s own return value and
         gating both sim_execute_trade() and the autotrade_fired/
         live_size_usd/leverage_used bookkeeping on status being
         "OPENED" or "OPENED_TP_SL_FAILED" — matching the EXACT same
         status-check idiom already used at the bounce/breakout call
         site (line ~13261, `autotrade_result.get("status") in
         ("OPENED", "OPENED_TP_SL_FAILED")`), confirmed by reading that
         call site directly rather than inventing a new convention.
         Also reviewed (no changes needed, confirmed correct): update_
         msnr_signal_outcomes() only ever processes a signal once (its
         own open_signals list is re-filtered by status=="OPEN" fresh
         each call, so a signal already flipped to CLOSED can't be
         double-compounded on a later pass); msnr_rank_by_winrate_
         sample()'s new weighted-composite ranking (min-max normalize
         compound_return_pct and score, guard divide-by-zero when all
         candidates share a value); MSNR_BACKTEST_DAYS's UI label
         (${cfg.backtest_days} — confirmed templated, not a stale
         hardcoded "30 дней" left over from the v0.99.41 30->40 change);
         MSNR_PARAM_GRID_* (still 3x3x3=27, no drift from the "27
         комбинаций" UI copy); msnr_effective_live_universe() (my own
         v0.99.35 fix, confirmed it survived the other session's changes
         intact).
         Verified with py_compile, an actual runtime start (confirmed
         all 5 execute_autotrade statuses map to the correct order_
         opened boolean: OPENED/OPENED_TP_SL_FAILED -> True, SKIPPED/
         ERROR/DRY_RUN -> False), pyflakes, node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (still 63 routes), and an AST walk for duplicate
         top-level defs (none introduced).

v0.99.46 - Direct user request, following a live example: "skhynix
         сигнал пришел, стоп меньше 1 доллара, давай ориентировать на
         стоп, 10 плечо по умолчанию, но нужно чтобы по стопу терялось
         не менее 10%." At the flat AUTOTRADE_LEVERAGE_MSNR (10x), a
         stop that tight barely dents the account if hit — the position
         is effectively too small to matter either way, wasting most of
         the trade's real risk budget.
         New MSNR_TARGET_STOP_LOSS_PCT (10.0): the target fraction of
         margin a stop-out should cost. New msnr_symbol_contract_max_
         leverage(symbol): the RAW exchange leverage_max, deliberately
         NOT pre-clamped to AUTOTRADE_LEVERAGE_MSNR the way msnr_symbol_
         effective_leverage() is — clamping to the default here would
         defeat the entire point of scaling leverage up. New msnr_
         leverage_for_stop(entry, sl, ceiling_leverage): leverage =
         target_pct / stop_distance_pct, floored at AUTOTRADE_LEVERAGE_
         MSNR (only ever scales UP for a tight stop, never down for a
         wide one — a wide stop already carries full weight at the
         default, and reducing leverage for THOSE is a different,
         already-solved problem: msnr_symbol_sl_skip_min()/msnr_trade_
         beyond_liquidation() skip a signal outright rather than under-
         sizing it), capped at ceiling_leverage.
         msnr_compound_trail()/msnr_compound_return() (the backtest's
         own $ simulation) no longer take a flat `leverage` — replaced
         with `ceiling_leverage`, and each trade now resolves its OWN
         leverage via msnr_leverage_for_stop() off that trade's own
         stop width, instead of one number for the whole walk. msnr_
         optimize_symbol() now stores a new "leverage_ceiling" field
         (msnr_symbol_contract_max_leverage()) alongside the existing
         "effective_leverage", and passes THAT (not effective_leverage)
         into the compound simulation — per direct user follow-up
         confirming this: since the backtest's own $ simulation used to
         run at one flat leverage too, recomputing it with per-trade
         dynamic leverage can swing some symbols' "доход" figures
         substantially (a symbol with historically tight stops was
         being systematically under-leveraged in the old simulation,
         same as live) — this recomputes automatically on the symbol's
         next backtest cycle, no separate migration needed.
         msnr_scan_symbol_live() now resolves dyn_leverage from this
         signal's own stop width BEFORE the liquidation-safety check
         (moved earlier in the function specifically so that check
         evaluates the leverage this trade will ACTUALLY use, not the
         old flat default), walks it back DOWN in 0.5x steps toward
         AUTOTRADE_LEVERAGE_MSNR if the target-driven value would push
         the trade past the liquidation buffer (msnr_leverage_for_
         stop() has no awareness of this symbol's live MMR on its own),
         and reuses that same checked value for the real order's
         leverage, size compounding, and record["leverage_used"] —
         one resolved value, not three independent re-derivations that
         could drift.
         api_msnr_backtest_trades() now passes the symbol's own
         leverage_ceiling into msnr_compound_trail() so the expanded
         per-trade view's numbers match what the summary row's "доход"
         was actually computed with, instead of silently falling back
         to the flat default.
         UI: the summary row's leverage indicator now shows the actual
         [default, ceiling] range ("плечо 10-40x (по стопу)") instead
         of one flat number, only falling back to the old "лимит биржи"
         wording when the exchange's own cap sits at or below the
         configured default (no room to scale up at all). The expanded
         per-trade table gained a "Плечо" column showing each trade's
         own resolved leverage, right next to the existing per-trade
         "Баланс" column.
         Verified with py_compile, an actual runtime start (synthetic
         SKHYNIX-shaped case: a 0.25%-wide stop against a 75x contract
         ceiling resolved to 39.5x, matching MSNR_TARGET_STOP_LOSS_PCT /
         stop_pct exactly; a normal 2%-wide stop correctly stayed at the
         10x floor since 10/2=5 < 10; a wide 15%-wide stop also stayed
         at the floor, not reduced; a two-trade compound trail — one
         tight-stop, one normal-stop — confirmed each trade's own
         leverage/pnl_pct differs correctly within the SAME walk; a
         backward-compatibility check confirmed msnr_compound_trail()
         called with no ceiling_leverage at all still defaults to the
         flat AUTOTRADE_LEVERAGE_MSNR, unchanged from pre-v0.99.46
         behavior for any caller that doesn't pass one), pyflakes, node
         --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 63 routes), and an AST walk
         for duplicate top-level defs (none introduced).

v0.99.47 - Direct user follow-up to v0.99.46: "чёт лучше не стало,
         будто даже хуже" -> "может как-то для каждой монеты в рамках
         автотюнинга автоматически выбирать оптимальное плечо для
         долгосрочного роста?" Root cause of the regression: v0.99.46's
         "lose exactly MSNR_TARGET_STOP_LOSS_PCT on a stop-out" rule
         scaled leverage up SYMMETRICALLY — it amplified the WIN side
         by the exact same factor as the loss side on every tight-stop
         trade. Under full-reinvestment compounding, higher variance
         can REDUCE long-run geometric growth even at an unchanged (or
         better) arithmetic edge — the Kelly-criterion "over-betting
         past optimal hurts compounded growth" point already raised
         earlier this session about the sizing model in general, now
         confirmed live: a target-% heuristic has no way to know it's
         on the wrong side of that curve for a given symbol, only
         actually testing against that symbol's own history can tell.
         REPLACED msnr_leverage_for_stop() (removed entirely — no
         longer referenced anywhere) with new msnr_optimal_leverage_
         for_symbol(trades, ceiling_leverage): finds the single flat
         leverage L, applied to EVERY trade in the symbol's own
         history (not varied per-trade by stop width), that maximizes
         E[log(1 + pnl_frac(L))] over that history — the textbook
         "optimal f" / Kelly-criterion objective, since maximizing
         expected log-growth is exactly what maximizes long-run
         COMPOUNDED wealth (a consequence of the strong law of large
         numbers applied to a sequence of multiplicative returns, not
         a heuristic). Any candidate leverage where even ONE historical
         trade's own pnl_frac(L) <= -1 (would have wiped the account)
         scores -infinity outright for that candidate — ruin is
         absorbing. Searched as a plain 0.5x-step grid from AUTOTRADE_
         LEVERAGE_MSNR up to ceiling_leverage (not a smarter optimizer
         — this objective is well-behaved/concave for realistic trade
         distributions, and a grid is simpler to verify correct at
         negligible extra compute). Floored at AUTOTRADE_LEVERAGE_MSNR,
         same "never go below the default" stance v0.99.46 already had
         — a symbol whose own history says even the default is past
         Kelly-optimal is a stress_test_failed/skip_sl_pct_min
         candidate handled elsewhere already.
         msnr_compound_trail()/msnr_compound_return() reverted to ONE
         flat `leverage` parameter (undoing v0.99.46's per-trade
         ceiling_leverage variant) — Kelly-optimal is inherently a
         single number for the whole betting sequence, not something
         that varies signal-by-signal off one visible feature.
         msnr_optimize_symbol() now computes best["optimal_leverage"]
         (via msnr_optimal_leverage_for_symbol()) against best_results
         AFTER every filter (skip_rr_min/liquidation/skip_sl_pct_min)
         has already run, and passes it flat into msnr_compound_return()
         — replacing the ceiling_leverage/per-trade call from v0.99.46.
         New msnr_symbol_optimal_leverage(symbol) live lookup (same
         separate-lookup pattern msnr_symbol_skip_rr_min()/msnr_symbol_
         skip_sl_pct_min() already established, since msnr_symbol_
         params()'s return value gets spread as **params into msnr_
         detect_signals(), which has no matching kwarg). msnr_scan_
         symbol_live() now resolves dyn_leverage via this lookup
         instead of computing it fresh per-signal off stop width —
         same downstream liquidation-safety walk-down as v0.99.46 kept
         intact (the symbol's own optimal leverage still has no
         awareness of live MMR at firing time).
         api_msnr_backtest_trades() now passes the symbol's own
         optimal_leverage (not leverage_ceiling) into msnr_compound_
         trail() so the expanded per-trade view matches the summary
         row's "доход" again.
         UI: summary row's leverage indicator now reads "плечо Xx
         (Kelly-оптимум)" when optimal_leverage clears the configured
         default, plain "плечо Xx" otherwise, with the exchange-cap
         note ("лимит биржи Xx") shown separately when relevant instead
         of conflated into one range string.
         Verified with py_compile, an actual runtime start (synthetic
         bad-quality narrow-stop symbol at 40% win-rate correctly
         stayed at the 10x floor — no unjustified leverage-up; a good-
         quality narrow-stop symbol at 70% win-rate/RR=2 correctly
         climbed to the 75x ceiling; a synthetic history containing one
         historically-ruinous wide-stop trade correctly forced the
         floor regardless of ceiling, since every candidate above it
         also scored -infinity via that same trade; an end-to-end
         comparison on the good-quality symbol — msnr_compound_return()
         at the found optimal leverage vs. the flat default — showed
         $1024.63 (+2461.6%) at the Kelly-optimal 75x against $68.48
         (+71.2%) at the flat 10x on the identical 20-trade history,
         confirming the optimizer captures real upside a flat default
         leaves on the table when a symbol's own quality justifies it),
         pyflakes, node --check on the correctly-last <script> block,
         the Flask route/def integrity check (still 63 routes), and an
         AST walk for duplicate top-level defs (msnr_leverage_for_stop
         confirmed fully removed, no duplicates among the 313 total).

v0.99.48 - Direct user request: "может не выбирать топ 70 ликвидных
         монет, а в целом выбирать из всех десятку лучших." msnr_build_
         backtest_universe() used to slice ranked-by-volume symbols
         down to the top MSNR_BACKTEST_UNIVERSE_SIZE (70) BEFORE the
         top-10 score ranking ever ran — meaning a symbol with a
         genuinely better score/compound_return_pct could never even
         be considered if ~70 other symbols happened to trade more
         24h volume that day. Liquidity rank and signal quality are
         different things; the cap was silently using one as a gate
         on the other.
         Dropped the `[:MSNR_BACKTEST_UNIVERSE_SIZE]` slice — every
         _USDT symbol clearing the existing MIN_VOL_USD floor (same
         liquidity gate used elsewhere in this app, $500k 24h volume
         by default) is now backtested, not just the 70 most liquid
         among them. MSNR_BACKTEST_UNIVERSE_SIZE itself left defined
         (its own comment updated to say so) rather than deleted, in
         case a future session wants to reintroduce a cap deliberately
         — nothing reads it by default anymore.
         Named trade-off in the function's own docstring rather than
         silently absorbed: this backtests noticeably more symbols per
         cycle now (every liquid pair, likely 180+ based on this app's
         own liquid-universe counts elsewhere, not the 70-symbol cap
         this replaces) — a longer cycle and more aggregate Gate.io
         API load per cycle. Not mitigated here on the assumption
         that's an acceptable trade for genuinely considering the full
         pool: GLOBAL_HTTP_SEMAPHORE/_global_rate_gate() (v0.99.37/38,
         the other session's fix for exactly this class of problem)
         already cap the aggregate request rate/concurrency app-wide
         regardless of how many symbols any one loop works through, so
         this doesn't reopen the rate-limiting problem those fixes
         addressed — it just makes MSNR's own cycle take longer to
         grind through a bigger list within that same shared budget.
         Verified with py_compile, an actual runtime start (mocked
         get_tickers() with 150 synthetic liquid symbols: confirmed all
         150 + gold now appear in the built universe, where the old
         cap would have kept it at 70 + gold; a separate liquidity-
         floor check confirmed a symbol below MIN_VOL_USD is still
         correctly excluded — the floor itself wasn't touched, only
         the additional rank-based cap on top of it), pyflakes, node
         --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 63 routes), and an AST walk
         for duplicate top-level defs (none introduced).

v0.99.49 - Direct user request: "надо дать возможность ставить галочки
         и над не топ 10, вижу там просто сумасшедшие результаты
         которые в топ не попадают из-за выборки, на свой страх и риск
         как эксперимент." Autotrade toggling was gated behind msnr_
         autotrade_eligible_symbols() (top-N by score, minimum sample)
         at three independent points — the write-time API validation,
         the live-firing gate, and the live-scan union — a symbol with
         a genuinely strong compound_return_pct but too small a sample
         to rank in the top 10 could never be manually enabled at all.
         New msnr_manual_toggle_allowed_symbols(overrides): every
         symbol with completed, non-errored backtest data, EXCLUDING
         only stress_test_failed ones — a losing $ compound simulation
         stays a hard block even for this manual override (a much more
         fundamental "this literally lost money in its own history"
         signal than "didn't make the top 10 by score/sample," which is
         specifically what this request asks to bypass). Swapped in at
         all three gates: api_msnr_autotrade_toggle() (write
         validation), msnr_scan_symbol_live()'s firing condition, and
         msnr_effective_live_universe()'s union (feeding both the
         actual scan set AND the green-dot display) — using the
         narrower eligible-set at any ONE of these three while widening
         the others would reproduce the exact "checkbox does nothing"
         bug already found and fixed once before (v0.99.32, for a
         different mismatch between two gates).
         api_msnr_status() now also returns manual_toggle_allowed per
         symbol so the UI knows which rows get a checkbox.
         UI, same request's second half ("на планшете даже в ширину не
         влазит, сократи инфу"): the MSNR backtest table's checkbox
         column is now ALSO pinned via position:sticky (previously only
         Symbol was) — scoped to a new .msnr-bt-table class rather than
         a blanket rule, since a second sticky column needs a matching
         FIXED width on column 1 to avoid column 2 overlapping it, and
         only this table's short-ticker first column is narrow/
         predictable enough to safely fix (92px, tuned to fit a ~12-
         char symbol like SKHYNIX_USDT plus its arrow/dot markers
         without truncating in the common case; longer names degrade
         gracefully via text-overflow:ellipsis rather than breaking
         layout). Shortened the "бэктест" text label next to non-live
         symbols to a small dim ○ (mirroring the existing colored ●
         "live" dot's own visual language) specifically so column 1
         could be narrow enough for this to work at all. Manually-
         toggled-on rows OUTSIDE the top 10 get a distinct orange
         checkbox outline + warning tooltip ("вручную, вне топ-10 — на
         свой страх и риск") so it's visually obvious which checkboxes
         are auto-ranked vs a deliberate manual pick. The old "———
         остальные (только бэктест, автоторговля недоступна) ———"
         separator wording updated — autotrade is no longer unavailable
         past that line, just not auto-ranked.
         Also compacted the table itself per the same request: merged
         the W/L/T columns into one ("20W/22L/1T"), shortened "Win-rate"
         to "WR" and "Expectancy" to "Exp" — 11 columns down to 9,
         updated colspan="11" -> colspan="9" at all three dependent
         spots (the two section separators and the expanded-trades row).
         Verified with py_compile, an actual runtime start (synthetic
         3-symbol case: a small-sample-but-good symbol correctly
         excluded from the top-10 ranking but present in the manual-
         allowed set; a stress_test_failed symbol correctly excluded
         from BOTH; an end-to-end check confirmed a manually-toggled
         small-sample symbol actually lands in msnr_effective_live_
         universe()'s result — the real scanned set, not just a UI
         checkbox with no effect), pyflakes, node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (still 63 routes), and an AST walk for duplicate
         top-level defs (none introduced).

v0.99.50 - Direct live bug report, with a screenshot: "почему-то 2 раза
         одна и та же сделка в живых" — two identical TIA_USDT LONG
         V-shape rows (same entry/SL/TP) in the live signals table.
         Root cause: msnr_scan_symbol_live()'s ONLY internal dedup
         against re-firing the exact same signal was the _msnr_signal_
         cooldowns dict — a plain in-memory module-level dict, never
         part of STATE, never written by save_state() or restored by
         load_state(). A process restart (this app has a documented
         history of those — Gate.io rate-limit pressure, and Android
         killing the background Termux process during idle screen-off
         time, per the earlier watchdog discussion this session) wipes
         that dict back to empty, while STATE["msnr_signals"] itself
         (the actual persisted record of what already fired) survives
         the restart intact. If the same active V-shape/A-shape level
         is still the most recent qualifying signal after restart —
         which needs nothing about the market to have changed, since
         msnr_detect_signals() has no memory between calls at all
         (v_fired/a_fired are local variables, reset fresh every single
         call) — the freshly-empty cooldown dict has no record of
         having already fired it, and it fires again: a second,
         genuinely duplicate OPEN record for a symbol that already has
         one open.
         has_open_signal_any_module() (the cross-module veto) doesn't
         catch this either, and was never supposed to — its own
         docstring is explicit that it's called "IN ADDITION to each
         module's existing own-list check," and it deliberately
         EXCLUDES msnr_signals from its own scan when MSNR calls it, on
         the assumption MSNR has its own internal per-symbol dedup.
         MSNR never actually had that self-check — only the fragile
         time-based cooldown above, which is a different, narrower
         guard (catches "already fired THIS EXACT candle," not "already
         has ANY open position on this symbol").
         Added the missing self-check directly: before firing, msnr_
         scan_symbol_live() now also checks STATE["msnr_signals"]
         itself for an existing OPEN record on this symbol — reading
         PERSISTED state instead of the fragile in-memory cooldown
         closes the gap regardless of WHY the time-based cooldown alone
         failed to catch it (restart being the concrete case here, but
         this is a strictly more robust guard than the narrower one it
         sits next to, not a replacement for it — kept both).
         Verified with py_compile, an actual runtime start (synthetic
         STATE["msnr_signals"] with an OPEN TIA_USDT record: confirmed
         the new check correctly returns True for that same symbol and
         False for an unrelated one, matching exactly the block/allow
         behavior msnr_scan_symbol_live() now applies before firing),
         pyflakes, node --check on the correctly-last <script> block,
         the Flask route/def integrity check (still 63 routes), and an
         AST walk for duplicate top-level defs (none introduced).

v0.99.51 - Direct user report: "есть баг с сбросом видимого окна при
         скролле и масштабировании, когда смотрю сделки и листаю
         список монет." Two compounding causes, both in setPanelHtml()/
         loadMsnrTrades() territory:
         (1) setPanelHtml() (v0.99.29) only ever preserved HORIZONTAL
         scrollLeft inside individual tables — it never touched the
         PAGE's own vertical scroll (window.scrollY) at all. Every 15s
         refreshAll() tick rebuilds the whole panel via panel.innerHTML
         = ..., and while the pixel value of window.scrollY doesn't
         necessarily change just because content below it shrinks, the
         CONTENT at that same pixel offset does — which is exactly what
         "the visible window resets" looks like from the outside, even
         though technically nothing browser-side moved the scrollbar.
         Now also saves/restores window.scrollY around the rebuild, the
         same save-before/restore-after shape the horizontal fix
         already used.
         (2) The actual height-shifting culprit underneath that:
         restoreMsnrExpansion() re-calls loadMsnrTrades() for every
         already-expanded coin on EVERY refresh tick, and that function
         unconditionally blanked the trade table back to one line of
         "загрузка..." text before re-fetching — so an expanded coin's
         section briefly collapsed to nothing and then re-expanded to
         full height on every single 15s tick, regardless of whether
         window.scrollY itself got restored correctly. Restoring a
         scroll position doesn't help when the content actually AT
         that position keeps disappearing and reappearing underneath
         it. Fixed by only showing the "загрузка..." placeholder the
         FIRST time a coin is expanded (body genuinely empty) — a
         routine refresh of an already-populated table now keeps
         showing the OLD data while the new fetch is in flight, and
         only swaps it in once the response actually arrives, removing
         the height oscillation for the by-far most common case.
         Also named as a likely contributing factor in the same
         report, not separately mitigated: some mobile browsers reset
         pinch-zoom level alongside an unexpected scroll jump on a
         large synchronous DOM replacement like this one — the
         window.scrollY restore above is expected to reduce this too,
         since it's the same underlying "big reflow moved the visible
         viewport" trigger, though this wasn't independently verified
         (no way to test pinch-zoom behavior from this environment).
         Verified with py_compile, an actual runtime start, pyflakes,
         a standalone Node simulation of setPanelHtml()'s scrollY save/
         restore against a mock window object that resets scrollY
         mid-rebuild (confirmed the final value matches what was saved
         beforehand, not the reset-to-0 the mock injected), a second
         standalone check confirming loadMsnrTrades()'s new hasContent
         condition correctly distinguishes "body already has a table"
         (skip the placeholder) from "body is empty" (show it), node
         --check on the correctly-last <script> block, a grep
         confirming exactly one definition each of setPanelHtml()/
         loadMsnrTrades() (no accidental duplication from the edit),
         the Flask route/def integrity check (still 63 routes), and an
         AST walk for duplicate top-level defs (none introduced).

v0.99.52 - Direct user follow-up to a question about the MSNR RR-bucket
         table's own displayed n counts (e.g. 32W/124L, n=156 in the
         7-10R bucket, pooled across ~180 backtested symbols): "давай
         вообще уберём не работу, оставим для вида, мне кажется без
         неё будет лучше." That n=156 pooled across ~180 symbols is
         under one trade per symbol on average — real-looking at the
         pooled level, but not an actual per-symbol sample. Adjusting a
         single GLOBAL MSNR_MAX_RR off that pooled-but-per-symbol-thin
         evidence risked exactly the "looks fine in aggregate, wrong
         for the one symbol it's actually capping" failure mode this
         whole session's per-symbol filters (skip_rr_min, skip_sl_
         pct_min, Kelly-optimal leverage, stress_test_failed) were
         built specifically to avoid — this pooled global knob was the
         one place that reasoning had never been applied.
         Disabled the _risk_autotune_msnr_max_rr() call inside risk_
         autotune_pass()'s msnr block — commented out rather than
         deleted, in case a future session wants it back, with the
         reasoning above recorded right there. MSNR_MAX_RR itself, the
         function definition, and _set_msnr_max_rr() are all left fully
         intact — only the automatic pooled-evidence-driven adjustment
         stopped; MSNR_MAX_RR now just sits at whatever value it's
         configured/last set to.
         The RR-bucket table itself keeps showing in the UI exactly as
         before ("для вида") — api_msnr_status() computes rr_buckets
         independently, straight from msnr_backtest_results_raw, with
         no dependency on the now-disabled autotune call; confirmed by
         reading that call site directly rather than assuming.
         Verified with py_compile, an actual runtime start (confirmed
         MSNR_MAX_RR still reads normally, unaffected), pyflakes (no
         unused-name complaints from the now-dead call — the function/
         setter stay referenced elsewhere), node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (still 63 routes), and an AST walk for duplicate
         top-level defs (none introduced).

v0.99.53 - Direct user question: "а проверка на уже открытую сделку на
         бирже есть?" Answer was no — every duplicate-position guard in
         this app until now (has_open_signal_any_module(), and MSNR's
         own v0.99.50 fix) only checked this app's OWN internal STATE,
         never the actual exchange. reconcile_positions_and_orders()
         (already called right before every real order) does something
         different: alerts on unprotected positions and cancels
         orphaned trigger orders, it was never a duplicate-position
         gate. If STATE ever drifts from reality — a position closed on
         Gate before this app's own outcome-tracking loop caught up, a
         manual close via the Gate app itself, STATE getting reset/
         corrupted while a real position stayed open, two app instances
         sharing one Gate account — every STATE-only check would wave a
         genuinely duplicate order straight through with no way to
         catch it, since none of them ever asked the exchange itself.
         Added a direct get_open_positions() check inside execute_
         autotrade() (the single shared entry point every module's
         signal source already calls — bounce/breakout/divergence/ema/
         scalp/session/msnr/ft5/vgi all get this for free, not just
         MSNR), right before a real order would be placed: if this
         symbol already has a nonzero position on the exchange, skip
         with status "SKIPPED" and a clear detail message instead of
         stacking a second one. Placed after the AUTOTRADE_DRY_RUN
         branch (a dry-run never touches the real account, nothing to
         check) and before reconcile_positions_and_orders() (no reason
         to run that cleanup pass first if this is about to skip
         anyway). Same fail-open shape as the existing liquidation-
         safety check right above it in the same function: if the
         exchange query itself errors, log it and proceed rather than
         blocking every future trade on one flaky API call — this is
         additive insurance on top of the existing STATE-based guards,
         not their replacement, so losing it for one cycle isn't fatal
         the way losing the STATE-based checks entirely would be.
         Verified with py_compile, an actual runtime start (synthetic
         open-positions list: confirmed a symbol present in it correctly
         matches for skipping, a symbol absent correctly doesn't),
         pyflakes, node --check on the correctly-last <script> block,
         the Flask route/def integrity check (still 63 routes), and an
         AST walk for duplicate top-level defs (none introduced).

v0.99.54 - Direct user request: "сделай вкладку mnsr главной и убери
         предупреждения, это уже основной индикатор." MSNR started as
         an EXPERIMENTAL tab (v0.99.0) with a "⚠️" tab label and a big
         orange warning box at the top of its own panel — after this
         entire session's worth of work (per-symbol filters, Kelly-
         optimal leverage, duplicate-signal fixes, exchange-position
         checks, wider backtest universe), the user no longer considers
         it experimental.
         Made MSNR the default tab: activeTab now starts as 'msnr'
         (was 'signals'/Volume), swapped which tab has the initial
         "active" CSS class and which panel starts visible (signals
         Table now display:none, msnrPanel now display:block) so the
         static HTML skeleton and the JS default agree with each other
         from first paint, not just after the first refreshAll() tick.
         Removed the "⚠️" from the MSNR tab label itself (XAU LG and
         FT5 keep theirs — this request was specifically about MSNR).
         Removed the warning presentation in three more places: the
         orange-bordered "⚠️ Экспериментально" box at the top of the
         MSNR panel (kept the actual methodology description — source
         channel, OCL/QM logic — just without the alarm styling or
         the now-stale "автоторговля выключена по умолчанию" aside,
         since the user has been actively configuring MSNR autotrade
         all session); the Telegram signal notification's own
         "— ЭКСПЕРИМЕНТАЛЬНО" suffix (XAU LG's own notification text
         is untouched, only MSNR's); the settings panel's "Алерты
         MSNR ⚠️" label and "экспериментально —" prefix on its
         description.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the correctly-last <script> block, a grep
         confirming exactly one tab carries the "active" class and
         that signalsTable/msnrPanel's initial display values are the
         intended none/block swap, the Flask route/def integrity check
         (still 63 routes), and an AST walk for duplicate top-level
         defs (none introduced) — this was a markup/copy-only change,
         no Python logic touched.

v0.99.55 - Direct user request: "добавь в уведы телеграмм ещё плечо."
         The MSNR Telegram notification fires for EVERY detected
         signal, not just ones autotrade actually fired for — but the
         block that computes live_leverage/record["leverage_used"]
         only runs inside the "this symbol's autotrade is on AND
         eligible" branch, so record.get("leverage_used") is None for
         a signal that's only being logged (the far more common case,
         since most symbols shown in the backtest table don't have
         autotrade toggled on). Falls back to msnr_symbol_optimal_
         leverage(symbol) — the same Kelly-optimal value the UI already
         shows next to this symbol's row — so the message always says
         something useful, labeled differently ("плечо (реком.):" vs
         plain "плечо:") specifically so a signal that never actually
         placed an order can't be misread as having used that leverage
         for real.
         Verified with py_compile, an actual runtime start (synthetic
         check of both branches: a record with leverage_used=39.5
         formats as "плечо: 39.5x", one with leverage_used=None falls
         back to "плечо (реком.): 22.0x"), pyflakes, node --check on
         the correctly-last <script> block, the Flask route/def
         integrity check (still 63 routes), and an AST walk for
         duplicate top-level defs (none introduced).

v0.99.56 - Direct user follow-up to a discussion about which filter
         would be most effective to add next: time-of-day, per symbol.
         Reasoning discussed first: the whole QM/SNR pattern bets that
         a sweep-and-reclaim reflects REAL institutional order flow,
         not noise — and that's exactly the kind of thing that varies
         by session (London/NY open genuinely has that flow behind it,
         thin overnight hours often don't; this app's own separate
         "Сессия" module already trades that same premise directly).
         Symmetric with the existing skip_rr_min/skip_sl_pct_min
         filters, not a single global "only trade London" rule (which
         would repeat the same overfitting mistake already found and
         fixed for the liquid-universe cap) — per-symbol, since one
         symbol's bad hour can be another's fine one.
         New msnr_hour_bucket_stats(trades): buckets closed trades by
         the UTC hour (0-23, via time.gmtime()) of their own entry
         candle, computing win-rate and avg_rr per hour — same shape as
         msnr_rr_bucket_stats()/msnr_sl_bucket_stats(). New msnr_
         symbol_skip_hours(trades): same sample bar (MSNR_SYMBOL_RR_
         SKIP_MIN_SAMPLE) and per-bucket-breakeven test as the RR/SL
         filters, but returns a SET of specific bad hours rather than a
         single threshold — hour-of-day has no natural "everything past
         this point is bad" ordering the way RR/SL width does, a symbol
         could be fine at both 2:00 and 22:00 UTC but bad specifically
         at 14:00.
         Wired into msnr_optimize_symbol() in the same filter chain as
         skip_rr_min/liquidation/skip_sl_pct_min — derives skip_hours
         off the full surviving sample, THEN filters best_results and
         recomputes stats, same ordering reasoning already established
         for the other two. Runs BEFORE the Kelly-optimal-leverage
         computation, so leverage search sees the final, fully-filtered
         trade set. New msnr_symbol_skip_hours_live(symbol) lookup
         (same separate-lookup pattern as msnr_symbol_skip_rr_min()/
         msnr_symbol_skip_sl_min(), for the same **params-spread-into-
         msnr_detect_signals() reason) wired into msnr_scan_symbol_
         live()'s existing filter chain.
         UI: params row gained "skip часы(UTC) 14,22" (loss-red, same
         styling as the other skip indicators) when a symbol has any
         flagged hours.
         Verified with py_compile, an actual runtime start (synthetic
         two-hour case: hour 14 at 15% win-rate/RR=4 — below that RR's
         20% breakeven — correctly flagged; hour 3 at 70% correctly
         wasn't; also confirmed a NAIVE-looking-bad 30% win-rate at
         RR=4 correctly does NOT get flagged, since 30% clears that
         RR's own 20% breakeven — the same RR-adjusted judgment the
         RR/SL filters already use, not a flat win-rate cutoff; an
         end-to-end filter pass on a 40-trade synthetic set correctly
         dropped exactly the 20 bad-hour trades and kept the 20 good-
         hour ones), pyflakes, node --check on the correctly-last
         <script> block, the Flask route/def integrity check (still 63
         routes), and an AST walk for duplicate top-level defs (none
         introduced, all three new functions present exactly once).

v0.99.57 - Direct user follow-up to v0.99.56: "теперь количество сделок
         снизится и монеты могут перестать проходить по выборке, может
         выборку считать как раньше, но потом просто писать сколько
         сделок отмечено по такой-то причине." Real gap: msnr_rank_by_
         winrate_sample()/msnr_compute_live_universe() gate top-10/
         live-promotion eligibility on wins+losses — the POST-FILTER,
         DISPLAYED count, which had already been shrinking since
         v0.99.23 (skip_rr_min) and kept shrinking further with every
         filter added since (liquidation, skip_sl_pct_min, and now
         skip_hours). A symbol with a genuinely large real trade
         history could fall below the sample-size bar purely from
         filtering, even though the underlying data was never actually
         thin — filtering was never meant to also silently tighten the
         eligibility gate it gets judged against.
         New best["raw_closed_n"], captured in msnr_optimize_symbol()
         at the very start of the filter chain (right after the
         winning grid combo is chosen, before skip_rr_min/liquidation/
         skip_sl_pct_min/skip_hours run) — the symbol's TRUE closed-
         trade count, immune to how many filters exist or how much
         they end up removing. msnr_rank_by_winrate_sample()/msnr_
         compute_live_universe() now gate on THIS instead of wins+
         losses (falling back to wins+losses for a pre-existing STATE
         override that predates this field, so nothing silently reads
         as sample-size zero on upgrade). wins/losses/winrate/trades
         themselves are UNCHANGED — still the filtered, displayed
         values, since the v0.99.23 reasoning ("filtered trades
         shouldn't count as part of this coin's system") still holds
         for what's shown and what fires live; only the ELIGIBILITY
         gate needed decoupling from that shrinking count, not the
         count itself.
         Second half of the request — "просто писать сколько сделок
         отмечено по такой-то причине": each filter step now also
         records how many trades IT specifically removed (new best[
         "rr_filtered_count"]/["sl_filtered_count"]/["hours_filtered_
         count"], alongside the existing liquidation_filtered_count) —
         before/after diffs at each step, purely informational, no
         effect on raw_closed_n above. UI: each skip indicator (skip
         rr≥X / skip SL≥X% / skip часы(UTC)) now shows its own count in
         parens, e.g. "skip rr≥4 (12)"; the n= cell gained "(было N)"
         showing the pre-filter total whenever it's larger than what's
         displayed, so the gap between "real sample" and "shown sample"
         is visible at a glance instead of needing to add up every
         individual filter's own count by hand.
         Verified with py_compile, an actual runtime start (synthetic
         symbol: raw_closed_n=60, wins+losses=25 — well under both
         MSNR_AUTOTRADE_TOP_MIN_SAMPLE=35 and MSNR_LIVE_PROMOTE_MIN_
         SAMPLE=40 — confirmed it now clears BOTH gates on raw_closed_n
         alone; a second synthetic pre-existing override with no raw_
         closed_n field at all and wins+losses=40 confirmed the
         fallback path still correctly passes, matching pre-v0.99.57
         behavior for any override saved before this version), pyflakes,
         node --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 63 routes), and an AST walk
         for duplicate top-level defs (none introduced).

v0.99.58 - Direct user request ("актуализировать описание... короткий
         содержательный и более тезисный"), plus a live report in the
         same message ("ночью несколько часов прошло а ребэктеста не
         было давно" — the exact scenario this session's own earlier
         watchdog discussion predicted, left undone at the time per
         direct user choice: "Пока забей").
         Rewrote the MSNR panel's description from two dense prose
         paragraphs (methodology explained in running sentences, then
         a full config dump in one more long sentence) into a short
         bulleted <ul> — same facts, none of the connective wording.
         Fixed a stale framing bug while rewriting: "топ-N ликвидных
         монет" implied a liquidity-rank CUTOFF still exists, but
         v0.99.48 removed that cap entirely — every symbol clearing
         MIN_VOL_USD gets backtested now, not just the top N by volume
         — now reads "N ликвидных монет" without the misleading "топ-"
         prefix. The live-scan symbol list (unbounded — grows as more
         symbols qualify) is now truncated to the first 8 with a
         "+N ещё" tail, same pattern the progress bar's own in-flight
         list already used.
         Second half — the stale-backtest report: added a prominent
         red warning box when the last completed cycle is older than
         max(1h, 2.5×MSNR_REFRESH_SEC) — new cfg.refresh_sec exposes
         MSNR_REFRESH_SEC to the frontend for this. This is detection,
         not a fix: the app can't restart its own OS process from
         inside itself, and the most likely real cause (Android
         suspending/killing the background Termux process during idle
         screen-off time, discussed earlier this session) isn't
         something server-side code can prevent — this at least makes
         the person SEE a stall happened instead of discovering it by
         chance hours or days later. The generous threshold (2.5x, not
         1x) is specifically to avoid false-positiving on one genuinely
         slow cycle now that the backtest universe is substantially
         larger since v0.99.48 dropped the old 70-symbol cap.
         Verified with py_compile, an actual runtime start, pyflakes,
         a standalone Node simulation of the staleness math against
         the EXACT reported scenario (last backtest 2.87h ago, i.e.
         01:40 -> 04:32, refresh_sec=3600 -> 2.5h threshold: correctly
         warns) and a normal case (finished 20 minutes ago: correctly
         doesn't), a grep confirming backtest_universe_size is a real
         backend field (len(backtest_universe), not a template typo —
         the "?" seen in one screenshot was pre-first-load, not a bug),
         node --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 63 routes), and an AST walk
         for duplicate top-level defs (none introduced).

v0.99.60 - Two pieces of work landing in this one push, since the first
         (originally going to be v0.99.59) never shipped separately —
         a direct user follow-up request arrived and changed its design
         before it was ever pushed, so the pieces below are folded into
         a single version bump. Inline comments referencing "v0.99.59"
         throughout this diff describe that original, since-superseded
         design intent accurately; "v0.99.60" comments describe what
         changed relative to it.
         (1) The SECOND per-symbol filter from the "which filter would
         be most effective" discussion (v0.99.56 built the first, time-
         of-day): volume confirmation on the sweep candle. The QM/SNR
         pattern's whole premise is that a sweep-and-reclaim reflects
         REAL institutional order flow — a sweep on conspicuously LOW
         relative volume is a plausible tell that it doesn't, which
         tests the pattern's own stated mechanism more directly than
         the time-of-day filter (a proxy for WHEN flow tends to show
         up). msnr_detect_signals() now computes volume_ratio (this
         signal candle's own volume ÷ mean of the MSNR_VOLUME_LOOKBACK_
         BARS=20 bars immediately before it, excluding the signal
         candle itself) once per bar and attaches it to whichever
         signal fires — threaded through msnr_run_backtest()'s per-
         trade records and msnr_scan_symbol_live()'s live signal alike,
         since both share the same detector. New msnr_symbol_volume_
         skip_below(): same per-bucket-breakeven test and MSNR_SYMBOL_
         RR_SKIP_MIN_SAMPLE bar as the RR/SL/hour filters, but skips
         BELOW a ceiling instead of above a floor — opposite direction
         from RR/SL (their hypothesis: too HIGH is bad; this one's: too
         LOW is). Wired into msnr_optimize_symbol()'s filter chain
         (after skip_hours, before Kelly-leverage) and msnr_scan_
         symbol_live()'s live gate, with the same raw_closed_n/
         volume_filtered_count bookkeeping v0.99.57 already established
         for the other filters — per direct user reminder ("про n как в
         первом не забудь") this session had already learned the hard
         way once, not repeated here.
         (2) Direct user follow-up ("может добавить вариативность...
         авто перебор параметров фильтра") — with an explicit warning
         given back before implementing it: searching for whichever
         threshold gives the best-LOOKING result, without a
         significance test, would just be curve-fitting the filter
         itself to backtest noise, the exact overfitting failure mode
         already found and fixed elsewhere this session (liquid-
         universe cap, pooled RR-bucket autotune). User chose "оба
         варианта вместе" from two significance-preserving options:
         REPLACED the volume filter's fixed MSNR_VOLUME_RATIO_BUCKETS
         (0-0.5/0.5-0.8/0.8-1.2/1.2-2/2+, tuned for one assumed
         "typical" distribution) with new msnr_volume_quantile_
         buckets(trades, k): splits THIS symbol's own volume_ratio
         values into k roughly-EQUAL-sized groups by sorted rank —
         adapts to each symbol's own distribution shape instead of
         assuming a universal one. msnr_symbol_volume_skip_below() now
         searches MSNR_VOLUME_QUANTILE_GROUPS=[5,4,3] from finest to
         coarsest, using the first k where some group BOTH fails the
         breakeven test AND clears the sample bar — every candidate k
         still runs the exact same significance test, only the
         grouping varies, never "pick whichever k scores best."
         msnr_hour_bucket_stats() gained a `group_width` parameter
         (new MSNR_HOUR_GROUP_WIDTHS=[1,2,3]) for the same idea applied
         to the time-of-day filter — quantile splitting doesn't apply
         to hour-of-day (already 24 natural discrete bins), so this is
         granularity search alone: msnr_symbol_skip_hours() tries
         single-hour resolution first, then 2h/3h groupings as a
         fallback for a symbol whose per-hour sample is too thin to
         ever individually clear the bar. A flagged wide group skips
         every individual hour it covers.
         Verified with py_compile, an actual runtime start: (volume)
         100-trade synthetic case with the bottom quintile deliberately
         bad (15% win-rate at RR=4, breakeven 20%) — k=5 correctly gave
         5 groups of exactly 20 each and flagged the bottom one at its
         own upper edge; a 45-trade case where k=5 and k=4 groups were
         individually too thin (9 and 11, under the 15-sample bar) but
         k=3 (15 each) correctly caught the same pattern, confirming
         the cascade; (hours) a 40-trade two-hour case where the bad
         hours (14, 15) are adjacent confirmed the cascade lands
         exactly on width=2 and returns precisely [14,15], not a wider
         group pulling in an unrelated hour; a companion case with
         non-adjacent-under-width-2 bad hours (13 alone, 14 alone, each
         paired with an empty neighbor) confirmed the cascade correctly
         falls through to width=3 where they merge into one group with
         enough combined sample, returning [12,13,14] — the empty hour
         12 included because it's structurally part of that flagged
         group, not a bug; both filters confirmed to degrade cleanly on
         edge cases (empty trade list, records missing volume_ratio/
         time entirely) with no exceptions, matching old-STATE-override
         backward compatibility already established for the other
         filters), pyflakes, node --check on the correctly-last
         <script> block, the Flask route/def integrity check (still 63
         routes), and an AST walk for duplicate top-level defs (none
         introduced — all five touched/new functions present exactly
         once each).

v0.99.61 - Direct user question: "в описании потолок 8rr, это правда?"
         Confirmed: MSNR_MAX_RR's own env default genuinely is 8.0, and
         the UI text (cfg.max_rr) pulls the live value dynamically, not
         a hardcoded string — so whatever the panel shows IS the real
         current cap, not stale copy. The v0.99.58 description rewrite
         had already dropped the "авто-тюнится по статистике ниже"
         claim correctly (verified by re-reading the current template),
         so the user-visible text wasn't the problem.
         Found a REAL staleness while checking, though: MSNR_MAX_RR's
         own source comment still said "Auto-tuned by risk_autotune_
         pass() off pooled RR-bucket win-rate stats" — describing
         behavior that v0.99.52 disabled (per direct user request,
         "уберём не работу, оставим для вида") by commenting out the
         _risk_autotune_msnr_max_rr() call inside risk_autotune_pass()'s
         msnr block. Nothing about that disabling touched THIS
         constant's own comment, so it kept describing present-tense
         behavior that hadn't been true for 9 versions — exactly the
         kind of comment that could mislead a future session (or
         person) auditing this code into thinking auto-tuning was still
         live. Rewritten to state plainly that the value only ever
         changes via manual settings now (_set_msnr_max_rr()), or
         wherever the autotune last left it before v0.99.52 disabled
         it (settings persist — disabling the autotune didn't reset the
         value back to this env default on its own, only stopped moving
         it further).
         Verified with py_compile, an actual runtime start (confirmed
         MSNR_MAX_RR reads exactly 8.0 on a fresh import with no
         persisted settings override — matches the env default, though
         a real device with a differently-persisted settings file could
         legitimately show something else, which is exactly the caveat
         given directly to the user rather than assumed away), pyflakes,
         node --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 63 routes) — comment-only
         change, no logic touched.

v0.99.62 - Direct user request: "ещё планшет huawei mate 12.2 2025 в
         ширину все не влазит, надо скролить, немного буквально."
         Found a real bug while investigating: skipVolumeTxt (v0.99.60's
         volume-filter indicator) was defined but never actually
         inserted into the paramsTxt template string — it's been
         computed every render since v0.99.60 and never once shown.
         Fixed by adding it into the concatenation, in the same
         skip-indicator order the others already follow.
         For the actual width request: trimmed the RR column from
         "avg XR / med YR" down to just "avg XR" (median moved to a
         hover title instead of taking permanent column width — score
         already accounts for sample-size/variance concerns the median
         was partly there to hint at, so dropping it from the always-
         visible text loses little). Also trimmed the global mobile
         table cell padding 6px -> 4px horizontal (vertical unchanged)
         — a small, uniform saving across every column of every table
         under this same rule, not just MSNR's.
         Verified with py_compile, an actual runtime start, pyflakes, a
         grep confirming paramsTxt's template literal now references
         skipVolumeTxt exactly where the other four skip indicators
         already sit, node --check on the correctly-last <script>
         block, the Flask route/def integrity check (still 63 routes),
         and an AST walk for duplicate top-level defs (none introduced
         — no Python functions touched, JS/CSS-only change).

v0.99.63 - Direct user follow-up, with a screenshot circling the exact
         cause: v0.99.62's padding/RR trims weren't enough — the real
         width driver is the Параметры column itself, which packs grid
         params + up to 4 skip indicators + liquidation count + Kelly
         leverage + доход into ONE unbroken single-line string (the
         circled ALLO_USDT row: "1.5×ATR / 0.30% / 96 · skip rr≥3 (21)
         · 4 за ликвидацией · плечо 17.5x (Kelly-оптимум) · доход
         +677.7% ($40→$311.07)" — comfortably over 100 characters on
         one line, however tight the padding/font get). Every other
         column in this table is short and bounded (a percentage, a
         count, a couple of letters); this ONE column's variable,
         unbounded length was what forced the whole table wider than
         the viewport, not the padding.
         Fixed by letting ONLY this column wrap (white-space:normal,
         min-width:220px inline on the <td>) instead of trying to
         shrink its content further — the table itself still sets
         white-space:nowrap (.msnr-bt-table), but an inline style on
         one cell always wins that cascade regardless of specificity,
         so every other column stays single-line/compact while this
         one grows TALLER (wraps to a few lines) instead of forcing the
         table WIDER. Trades a slightly taller row for a table that
         actually fits the viewport, which is the trade the person
         asked for specifically after v0.99.62's padding/RR trims
         still left this one column overflowing.
         Verified with py_compile, an actual runtime start, pyflakes,
         a grep confirming the table's own white-space:nowrap rule and
         this cell's inline white-space:normal override coexist as
         intended (inline style takes precedence over the tag-level
         rule regardless of load order), node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (still 63 routes), and an AST walk for duplicate
         top-level defs (none introduced — no Python functions
         touched, JS/CSS-only change).

v0.99.64 - In-progress groundwork for a direct user request to bring
         XAU LG to feature parity with the other modules: chart display
         on signal click, an invert mode with honest stop/take re-
         fitting and RR, and auto-tuning — all "как везде." Not yet
         complete (interrupted by the v0.99.65 fix below, resuming
         after); this version bump covers only the safe, inert pieces
         landed so far, nothing behavior-changing yet:
         New XAU_LG_INVERT_SIGNALS (mirrors DIV/EMA/SESSION_INVERT_
         SIGNALS) and XAU_LG_SL_BUFFER_MULT (mirrors SESSION_SL_MULT/
         EMA_SL_ATR_MULT/DIV_SL_ATR_MULT) constants, defaulting to off/
         1.0 (no-op) — not yet read anywhere. XAU_LG_RR's own comment
         updated: no longer "deliberately excluded" from auto-tuning,
         since the whole point of this request is to change that.
         New RISK_AUTOTUNE_XAU_LG_RR_BOUNDS (same range as Session's
         own RR bounds). New setters _set_xau_lg_invert()/_set_xau_lg_
         sl_buffer_mult()/_set_xau_lg_rr() (save_settings() pattern,
         unused so far). Wired all three into apply_settings()/get_
         settings()/SETTINGS_KEYS so a future manual or auto-tuned
         change to any of them actually persists across a restart —
         this part matters NOW even before the feature is wired up,
         since leaving it out would be a silent gap once it is.
         Remaining work (chart endpoint + frontend, xau_lg_detect_
         signals() actually applying invert/sl_buffer_mult and storing
         rr, MFE/MAE tracking, the risk_autotune_pass() block) picks
         back up in a later version.

v0.99.65 - CRITICAL FIX, direct user report with a live screenshot:
         VGI winrate near-zero (6W/154L, 3.8%) while auto-tune had
         pushed vgi_min_rr 5 -> 7.78 (toward its own 8.0 ceiling) —
         the WRONG direction, actively making things worse, not
         better. User's own instinct ("логичнее инверсию включать и
         переосмысливать тейк и стоп") pointed at the right area;
         investigation found the actual mechanism, which persisted
         even with reverse already on (confirming it wasn't primarily
         a direction problem).
         Root cause #1: vgi_evaluate_signal()'s own formula is risk =
         reward/min_rr — min_rr doesn't just FILTER signals here, it
         directly SETS the stop distance, inversely. Raising min_rr
         shrinks the stop for every taken signal, making it easier to
         get stopped out by ordinary noise before price reaches the
         (unchanged) target — mechanically WORSENS win-rate, the
         opposite of what a normal *_MIN_RR filter does elsewhere
         (there RR is computed independently of an ATR/structure-based
         stop, so raising the bar only rejects more low-quality
         setups without touching accepted ones' own stops).
         Root cause #2, compounding #1 in the same wrong direction:
         the auto-tune rule feeding this (_risk_autotune_tp_extend,
         via win_mfe_r) had a structural, near-tautological upward
         bias specific to VGI — update_vgi_signal_outcomes() records
         mfe_r off the SAME win-triggering candle's own high/low
         BEFORE checking for the win and breaking, so a winning
         candle's ordinary wick past the exact TP price (typical, not
         an edge case) makes fav_r >= min_rr almost every single pass
         — because R itself (risk = reward/min_rr) is defined in terms
         of the very parameter being tuned. "Did wins run past the
         target" is near-circular here, not genuine evidence quality
         improved, unlike Session/EMA/DIV where R comes from an
         independent stop untouched by the target being tuned.
         Fixed by disabling that specific _risk_autotune_tp_extend
         call for vgi_min_rr (commented out with the full reasoning
         in place, not deleted — matches the same "disable a confirmed-
         broken rule, don't rush a replacement in the same pass"
         approach already used for MSNR_MAX_RR's pooled-bucket autotune
         in v0.99.52). A properly-designed VGI-specific rule (reacting
         to real adverse excursion the way _risk_autotune_sl_mult()
         does elsewhere, but inverted — here HIGHER min_rr means a
         TIGHTER stop, opposite of a normal multiplier) needs its own
         careful design as separate follow-up work, not a rushed
         substitute found in the same debugging pass. The reverse-flag
         rule (_risk_autotune_reverse) is untouched — VGI's own sizing
         is identical whichever direction is active (only WHICH zone
         gets targeted changes), so that rule doesn't share the same
         structural flaw and should react more sensibly once real
         (unbiased) performance data comes in post-fix.
         Also added a one-time corrective reset at startup: disabling
         the broken rule alone wouldn't undo the damage already
         persisted in settings.json — load_settings() would keep
         reloading the same bad 7.78 every future startup otherwise.
         If the loaded vgi_min_rr exceeds a 5.0 sanity ceiling
         (comfortably above the 3.0 default, so a genuine future
         manual choice in that range survives untouched), it's reset
         to 3.0 and logged — bounded, one-time migration for this
         specific incident, not a permanent ongoing clamp.
         Verified with py_compile, an actual runtime start (confirmed
         RISK_AUTOTUNE_VGI_RR_BOUNDS unchanged at (1.0, 8.0) — the
         value was inside its own bounds the whole time, this was
         never a bounds-violation bug, purely a wrong-direction-and-
         biased-input one; confirmed a fresh import's own VGI_MIN_RR
         default reads 3.0 as expected), pyflakes, node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (still 63 routes), and an AST walk for duplicate
         top-level defs (none introduced).

v0.99.66 - Completes the XAU LG feature-parity request from v0.99.64
         (interrupted mid-work by the v0.99.65 VGI fix): chart display
         on signal click, invert mode with honest stop/take refitting +
         RR, and auto-tuning — all "как везде."
         New _xau_lg_signal_dict(i, c, direction, entry, extreme,
         level) — shared construction helper (was inlined twice
         before), computes risk = abs(entry-extreme) * XAU_LG_SL_
         BUFFER_MULT (1.0 = old un-buffered behavior, unchanged) and
         tp = entry ± risk*XAU_LG_RR, stores "rr" on the signal (never
         existed before). xau_lg_detect_signals() now checks XAU_LG_
         INVERT_SIGNALS at both signal sites (support-break, resistance-
         break): inverted fires the OPPOSITE direction using the SAME
         risk distance (this candle's own range) on the swapped side,
         TP re-derived via the same risk*RR formula — never just
         flipping direction while keeping a now-meaningless original
         TP/SL, same principle SESSION_INVERT_SIGNALS already
         established. Verified via synthetic candle sequence: inverted
         signal's entry/sl are exactly the non-inverted signal's sl/
         entry swapped, same risk magnitude either way.
         "rr" threaded through xau_lg_backtest_symbol()'s results and
         xau_lg_scan_symbol_live()'s live record (which also gained
         mfe_r/mae_r/mfe_price/mae_price/mfe_r_at_close/mae_r_at_close,
         initialized the same way every other module's live record is).
         update_xau_lg_signal_outcomes() now tracks mfe_r/mae_r while
         walking forward and freezes them at close — same shape as
         update_session_signal_outcomes(). compute_xau_lg_signal_stats()
         gained the same agg()-based mfe_r_wins_at_close/mae_r_losses_
         at_close stats every autotuned module already returns.
         New risk_autotune_pass() xau_lg block: reverse-flip (_risk_
         autotune_reverse), SL-buffer nudge (_risk_autotune_sl_mult),
         RR/TP nudge (_risk_autotune_tp_extend, new RISK_AUTOTUNE_
         XAU_LG_RR_BOUNDS). Deliberately re-verified this does NOT
         repeat v0.99.65's VGI mistake before writing it: XAU LG's own
         R (risk = abs(entry-sl), set at signal time) is NOT defined in
         terms of XAU_LG_RR the way VGI's risk=reward/min_rr was — it
         comes from the raw candle's own range times SL_BUFFER_MULT,
         completely independent of the RR multiplier being tuned. Same
         safe shape Session/EMA/DIV already use, not VGI's self-
         referential trap. Both nudges apply unconditionally regardless
         of XAU_LG_INVERT_SIGNALS (unlike Session, which needed invert-
         only gating) — _xau_lg_signal_dict()'s formula is identical in
         both directions.
         New /api/xau_lg/chart/<symbol> endpoint: looks up the signal's
         OWN already-recorded entry/sl/tp/direction/rr from stored data
         (live STATE["xau_lg_signals"] first, then this symbol's own
         backtest results) rather than re-deriving via a fresh xau_lg_
         detect_signals() call with CURRENT live params — same fix
         already applied to api_msnr_chart() after a real incident (see
         that route's own docstring): XAU_LG_RR/SL_BUFFER_MULT/INVERT_
         SIGNALS are now all auto-tuned and can drift between when a
         trade was found and when its chart is later opened.
         New openXauLgChart(symbol, sigTime) — thin wrapper reusing
         openVgiChart/drawVgiChart (XAU LG's signal shape is
         structurally identical to VGI's, same reuse judgment already
         applied to Scalp/Session NY rather than duplicating canvas
         code a third time). refreshXauLg()'s signal rows gained data-
         symbol/data-time + a post-render click handler, same pattern
         refreshVgi() already uses. Header now shows RR/reverse-mode/
         SL-buffer state (only shown when buffer != 1, matching how
         other modules only surface a multiplier when it's actually
         non-default).
         Verified with py_compile, an actual runtime start (synthetic
         60-candle sequence with a deliberate support-break wick:
         confirmed non-inverted vs inverted signals share the identical
         risk magnitude with entry/sl exactly swapped; confirmed every
         detected signal carries a non-None "rr" field), pyflakes, node
         --check on the correctly-last <script> block, a grep
         confirming exactly one definition each of api_xau_lg_chart()/
         _xau_lg_signal_dict()/openXauLgChart() (no accidental
         duplication across all these edits), the Flask route/def
         integrity check (64 routes — up from 63, exactly the one new
         chart endpoint), and an AST walk for duplicate top-level defs
         (none introduced).

v0.99.67 - Direct user report with screenshots: "возле сделок я не вижу
         rr, я не вижу средний rr по всем сделкам, я вижу просто в
         тексте rr2." Root cause, found by reading the actual record
         construction: Volume's bounce/breakout signal record NEVER
         stored "rr" at all — `rr = bounce_rr if ... else breakout_rr`
         (this SYMBOL's own tuned value, from optimize_symbol()'s
         per-symbol grid search over PARAM_GRID_RR — genuinely varies
         trade to trade, as the earlier conversation about breakout's
         RR-tuning mechanism established) was computed and used to
         build sl/tp, then silently discarded — never written onto the
         record itself. Every other RR-bearing module (VGI, Scalp,
         EMA/DIV reverse mode, XAU LG since v0.99.66) already stores
         its own per-trade rr; Volume/bounce/breakout was the one place
         that got skipped, which is exactly why the header could only
         ever show one flat global RR/RR_BREAKOUT constant text ("RR
         2") instead of anything real — there was no per-trade data to
         aggregate from.
         Fixed at the source: record now stores "rr". compute_signal_
         stats() gained a new _agg_rr() helper (avg/median/p25/p75,
         same shape EMA/DIV's own rr_all already returns) — both
         overall (new "rr_all") and per-reason (by_reason[reason][
         "rr"]), computed from the actual stored per-trade values.
         Trades closed before this fix have no "rr" and are correctly
         excluded from the aggregate rather than counted as 0.
         UI: the header's bounce/breakout summary now shows each
         reason's own real avg RR inline (replacing the removed flat
         "RR ${config.rr}" text that never reflected per-symbol tuning
         at all); the main signals table gained an "RR" column between
         TP and MFE(R), showing each individual trade's own value.
         Verified with py_compile, an actual runtime start (synthetic
         5-signal STATE: 3 breakout trades with rr 2.0/1.5/2.5 ->
         avg 2.0 exactly; 1 bounce trade with rr=3.0 plus 1 legacy
         bounce trade with rr=None -> bounce aggregate correctly shows
         n=1, not diluted or zero-filled by the missing-rr trade;
         overall rr_all correctly aggregates all 4 rr-bearing trades
         together), pyflakes, node --check on the correctly-last
         <script> block, the Flask route/def integrity check (still 64
         routes — this was a data/display fix, no new endpoints), and
         a grep confirming no stale colspan was left pointing at the
         signals table's old 10-column count now that it has 11.

v0.99.68 - Direct user report: "в оригинале по задумке автора эта
         стратегия msnr ловит движения с очень большим rr, даже если
         winrate около 20-30, у нас так не получается." Investigation
         confirmed a real conflict: msnr_detect_signals() (both the
         A-shape/SHORT and V-shape/LONG branches) was silently
         substituting a much smaller MSNR_FALLBACK_RR=4.0 fixed target
         for ANY genuinely-far opposite level whose implied RR exceeded
         MSNR_MAX_RR (8.0, and — since v0.99.52 disabled the pooled-
         bucket autotune that used to move it — permanently stuck
         there) — directly preventing the large-RR/low-winrate trades
         this strategy is designed around from ever being taken as
         designed. Worse: since the record only ever stored the
         ALREADY-capped rr, msnr_symbol_rr_skip_min()'s own per-symbol
         statistical test (exactly the right tool for judging "is this
         RR bucket actually profitable for THIS symbol despite a low
         win-rate" via its own breakeven-at-sufficient-sample check)
         never even saw a trade's true RR to judge in the first place —
         the cap and the filter meant to replace it were fighting each
         other, not cooperating.
         Discussed the tension directly rather than picking a fix
         unilaterally, given how consequential a live-trading change
         this is; user chose "снять потолок полностью — довериться
         skip_rr_min целиком" over raising the cap to 15 (the top of
         its own already-provisioned RISK_AUTOTUNE_MSNR_MAX_RR_BOUNDS)
         or discussing further.
         Removed the RR-cap check entirely from both branches of msnr_
         detect_signals() — a paired opposite level is now used as TP
         whenever it's genuinely still ahead of price, at whatever RR
         that implies; msnr_symbol_rr_skip_min() (already built,
         already correctly per-symbol and sample-gated) is now fully
         trusted to reject a high-RR bucket where it's actually failing
         breakeven for a given symbol, and allow it through everywhere
         it isn't — a distinction a blanket global ceiling could never
         make. The now-fully-unused `max_rr` parameter was removed from
         msnr_detect_signals()'s own signature (confirmed via grep: no
         caller anywhere ever passed a non-default value) rather than
         left as dead, silently-ignored plumbing. MSNR_MAX_RR the
         constant itself, its setter, and its settings/UI wiring are
         all left fully intact — nothing in signal generation reads it
         anymore, but it's one line to reintroduce a cap deliberately
         if a future session ever wants to. MSNR_RR_BUCKETS' own top
         bucket (10, inf) already had no upper bound, so no bucket-grid
         change was needed for the statistics to absorb whatever RR
         values start showing up now. Updated the now-inaccurate "потолок
         RR" line in the MSNR panel's own description (was still
         claiming the removed behavior) to describe the new skip_rr_min-
         only stance instead. MSNR_MAX_RR's own top-level comment and
         msnr_detect_signals()'s docstring rewritten to describe what
         changed and why, not just delete the old explanation.
         Verified with py_compile, an actual runtime start (confirmed
         msnr_detect_signals()'s own signature no longer has a max_rr
         parameter at all), pyflakes (0 warnings — confirmed the now-
         dead `rr_cap` local variable was fully removed, not just
         unused), a grep confirming zero remaining references to
         `rr_cap` in actual code, only in explanatory comments, node
         --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 64 routes), and an AST walk
         for duplicate top-level defs (none introduced).

v0.99.69 - Direct user report with a screenshot: a live OPEN MSNR
         signal's own "РАЗМЕР" column showed "$40 @ 15x" while the
         backtest table's "плечо ... (Kelly-оптимум)" for the SAME
         symbol showed 19.5x, and the expanded per-trade table showed
         19.5x on every row too — looked like a display bug, wasn't
         one, but was genuinely confusing without an explanation.
         Confirmed by reading the actual data flow: leverage_used (the
         live signal's own value) is frozen at the exact moment THAT
         signal fired — an already-placed order's leverage can't
         retroactively change just because the recommendation moved
         later. The backtest table's Kelly value is the CURRENT
         recommendation and keeps updating every backtest cycle (this
         session already established these per-symbol values can shift
         meaningfully cycle to cycle), so it can genuinely diverge from
         what was true when a still-OPEN signal fired. A second,
         independent reason they can differ even at the exact same
         instant: msnr_scan_symbol_live()'s own liquidation-safety
         check (v0.99.46) walks leverage DOWN from the Kelly value
         specifically for a trade whose own SL width would otherwise
         breach the buffer — so a live value below the currently-shown
         Kelly number is expected either way, never a sign anything's
         broken.
         No logic changed (there was nothing to fix) — added a hover
         tooltip on the live signals table's "РАЗМЕР" cell explaining
         both reasons in place, so this doesn't need re-explaining from
         scratch the next time it comes up.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the correctly-last <script> block, and the
         Flask route/def integrity check (still 64 routes) — UI-only
         change, no Python logic touched.

v0.99.70 - CRITICAL FIX, direct user follow-up to v0.99.69's own
         explanation: "получается на бэктесте плечо выходящее за рамки
         ликвидации?" Confirmed yes: msnr_optimal_leverage_for_symbol()
         only ever guarded against a NOMINAL isolated-margin ruin
         (pnl_frac <= -1.0, i.e. move_pct*leverage >= 100%) — never the
         REAL exchange maintenance-margin liquidation price, which
         compute_scalp_liquidation_move_pct()'s own docstring already
         states is ALWAYS at or before that naive point ("a non-
         negative MMR+fee can only ever SHRINK this buffer... never
         enlarge it"). That's exactly the same real liquidation check
         msnr_trade_beyond_liquidation() already runs before a live
         signal fires and before a backtest trade counts toward stats
         — but the Kelly-optimal SEARCH itself never checked its own
         candidate leverages against it, so the search could (and, per
         a synthetic reproduction below, does) select and report a
         leverage where a historical LOSS trade's own SL sits PAST
         where the exchange would have actually force-liquidated the
         position first.
         This meant: the "Kelly-оптимум" shown in the backtest table
         and used for the $ compound simulation was not necessarily a
         leverage genuinely safe for every trade it was computed
         against — msnr_scan_symbol_live()'s own liquidation walk-down
         (v0.99.46) was doing ALL the real safety work for live orders,
         while the backtest's own number (and the "доход" figures
         computed at it) stayed unaware of the constraint entirely.
         Fixed at the source: msnr_optimal_leverage_for_symbol() gained
         an optional `symbol` parameter — when given, each candidate
         leverage's own log-growth evaluation now ALSO checks every
         historical LOSS trade's SL distance against that symbol's
         real liquidation buffer (same compute_scalp_liquidation_move_
         pct()/STATE["scalp_mmr_map"]/SCALP_DEFAULT_MMR_PCT/SCALP_
         SAFETY_MARGIN this app's other liquidation checks already
         use) — a leverage that would have breached it scores -inf,
         same absorbing-ruin treatment the nominal check already had.
         Both call sites in msnr_optimize_symbol() (the fallback branch
         and the main branch) now pass symbol=symbol. Backward-
         compatible: omitting `symbol` skips the new check entirely,
         same "can't evaluate, don't penalize" stance already used
         elsewhere for missing data, not a silent behavior change for
         any other caller.
         Verified with py_compile, an actual runtime start (synthetic
         20-trade 80%-winrate history with a 2%-wide stop: without a
         symbol, Kelly search picked 30x exactly as before the fix
         (confirmed unchanged backward-compat behavior); with a
         synthetic symbol at MMR=5%, the search correctly dropped to
         12.5x — and directly confirmed WHY via compute_scalp_
         liquidation_move_pct() itself: at the old 30x/MMR=5%, the real
         liquidation buffer is only 1.81%, tighter than the trade's own
         2% stop, meaning the exchange would have force-liquidated
         before price ever reached the nominal SL — exactly the
         scenario the user's question was asking about, now
         reproduced and fixed), pyflakes, node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (still 64 routes), and an AST walk for duplicate
         top-level defs (none introduced).

v0.99.71 - Direct user request: "проведи глобальную проверку всех
         индикаторов, найди проблемы и сделай исправления будто ты
         профессиональный трейдер." Systematic pass across every
         module for the same classes of issue already found this
         session:
         (1) Checked every _risk_autotune_tp_extend() call site (EMA,
         DIV, Session, XAU LG) for VGI's own self-referential-R trap
         (v0.99.65) — confirmed all four are safe: each module's own R
         (SL distance) comes from an independent source (ATR for EMA/
         DIV, SESSION_SL_MULT/XAU_LG_SL_BUFFER_MULT for the other two)
         that doesn't depend on the RR/TP parameter being tuned, unlike
         VGI's risk=reward/min_rr. No changes needed.
         (2) Checked liquidation safety across every module — confirmed
         execute_autotrade() (v0.70.0) already runs the SAME liquidation
         check for every mode (bounce/breakout/divergence/ema/session/
         msnr/ft5/vgi/xau_lg) at order time, not just MSNR. No gap
         found.
         (3) Found and fixed a REAL issue: msnr_optimal_leverage_for_
         symbol()'s Kelly-search objective and msnr_compound_trail()'s
         $ simulation both computed pnl_frac with ZERO taker-fee
         deduction, despite AUTOTRADE_SIM_FEE_PCT already existing in
         this codebase for exactly this purpose (used elsewhere for the
         paper simulator and liquidation-price math, never wired into
         either of these). Round-trip fee cost, as a fraction of
         MARGIN, is `2 * AUTOTRADE_SIM_FEE_PCT * leverage` — it scales
         LINEARLY with leverage, since fees are charged on notional
         (margin * leverage) at both entry and exit. A fee-blind Kelly
         search finds the leverage optimal in a zero-fee world, a
         strict overestimate of the true fee-inclusive optimum — as
         leverage grows, fee drag grows right along with it. Both
         functions now subtract fee_frac = 2*AUTOTRADE_SIM_FEE_PCT*
         leverage from every trade's pnl_frac, win or lose (the
         exchange collects it either way), same ruin/isolated-margin
         treatment applying on top of the fee-adjusted figure.
         Verified with a synthetic 20-trade 80%-winrate/2%-stop
         history: Kelly-optimal leverage correctly dropped from 30x
         (fee-blind) to 27.5x (fee-aware) — a real, if modest, shift in
         the SELECTED leverage; far more strikingly, the simulated
         compound balance dropped from $1888.95 (fee-blind, at the old
         30x) to $1062.39 (fee-aware, at the new, slightly lower
         27.5x) — a ~44% overstatement in the previously-displayed
         "доход" figure purely from ignoring a fee that was already
         one line away in the same file. At the found leverage, the
         round-trip fee alone costs 2.75% of margin on every single
         trade regardless of outcome.
         Audit scope note: this pass focused on the highest-impact
         "would a professional trader lose real money to this"
         categories — leverage/liquidation safety and fee-inclusive
         sizing — across every module. A few smaller modules (Scalp,
         FT5, plain Volume bounce/breakout) don't run a $ leverage
         simulation the way MSNR does, so this specific fee-blindness
         class doesn't apply to them the same way; their own R-multiple
         statistics aren't leverage-scaled and weren't flagged by this
         pass.
         Verified with py_compile, an actual runtime start (the
         synthetic reproduction above), pyflakes, node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (still 64 routes), and an AST walk for duplicate
         top-level defs (none introduced).

v0.99.72 - Direct user report with screenshots: a live MSNR signal
         (TRX_USDT) opened, but no Telegram notification arrived. The
         report itself connected this to the symbol's autotrade
         checkbox being off — investigation confirmed msnr_scan_symbol_
         live()'s own send_telegram() call is unconditional, NOT gated
         by the per-symbol checkbox at all (already documented at that
         call site since v0.99.55), so that specific theory doesn't
         hold — but the investigation surfaced a real, separate bug
         while checking: TELEGRAM_ALERTS_MSNR is properly defined (env
         default, wired into get_settings()/apply_settings(), a real
         "Алерты MSNR" checkbox in the settings UI) but send_telegram()
         never actually checked it — every other module's own category
         (vp/div/ema/hourly/session/session_ny/xau_lg/ft5/vgi) has a
         matching gate, msnr's was simply missing. Toggling "Алерты
         MSNR" off in settings had zero effect — a dead control. Fixed
         by adding the matching check. Note this direction (a missing
         check) can't itself explain a MISSING notification — it only
         means messages were never blocked by this setting, not more
         likely to be — so it doesn't fully explain the reported
         symptom.
         The more likely explanation for the actual missing
         notification, documented in place rather than fixed this
         turn (would mean touching the shared Telegram delivery
         pipeline every module relies on, a bigger and riskier change
         than this pass's scope): _telegram_send_queue is a plain in-
         memory queue.Queue, never persisted. If the background process
         restarts (this app has documented restart issues — see the
         MSNR staleness warning this same session's screenshots showed
         firing again, "последний бэктест был 2.8 ч назад", same
         Android/Termux-kill suspicion already raised then) between a
         signal being queued for Telegram and the background sender
         worker actually draining it, the queued message is lost for
         good — while STATE["msnr_signals"] itself (persisted via
         save_state()) survives the restart intact, which is exactly
         why the signal correctly shows as OPEN in the UI/table with no
         corresponding Telegram message ever having arrived. Not
         implemented as a fix in this pass — flagged as a real,
         higher-effort follow-up (persisting pending Telegram sends
         the same way signal state already is) rather than rushed into
         the same turn as an unrelated confirmed bug fix.
         Verified with py_compile, an actual runtime start (confirmed
         TELEGRAM_ALERTS_MSNR is a real, already-existing module-level
         constant, not something that needed defining from scratch),
         pyflakes, node --check on the correctly-last <script> block,
         and the Flask route/def integrity check (still 64 routes) —
         one-line logic fix, no new endpoints.

v0.99.73 - Direct user follow-up, alarmed: "уведомления и нет потому
         что это правильно, монета не в топ 10, галочки нет, тогда
         какого фига по ней открылась сделка, TRX?" — the previous
         turn had misread the report; this is about whether a REAL
         trade opened on a symbol with no autotrade checkbox, not about
         the missing notification.
         Re-verified by reading msnr_scan_symbol_live()'s actual record
         construction directly: record["status"]="OPEN" is set
         UNCONDITIONALLY the instant any signal is detected — BEFORE
         the autotrade-eligibility check (`if autotrade_symbols.get(
         symbol) and symbol in msnr_manual_toggle_allowed_symbols(...)`)
         even runs. That later block is the ONLY place execute_
         autotrade() gets called and autotrade_fired/live_size_usd/
         leverage_used get set — for a symbol with no checkbox, that
         whole block is skipped, so autotrade_fired stays False and
         live_size_usd/leverage_used stay None, exactly matching the
         "РАЗМЕР: —" the report's own screenshot already showed. No
         real order was placed for TRX_USDT — confirmed, not assumed.
         "OPEN" here has always meant "this signal is being tracked
         toward a WIN/LOSS outcome for statistics" (so a symbol outside
         the top-10 keeps accumulating its own track record even while
         not being traded — the record's own existing comment already
         explains why msnr_update_live_balance() specifically needs
         autotrade_fired=False signals to NOT move real money), never
         "a real position is open." The green live-scan dot means "in
         the scan universe" (getting checked for signals at all), a
         different question from "being traded" — nothing in the UI
         made that distinction obvious, which is what actually caused
         the alarm.
         Fixed the display gap rather than treating this as a false
         alarm to dismiss: the live signals table's STATUS cell now
         shows "OPEN (сигнал)" instead of a bare "OPEN" specifically
         when autotrade_fired is false, with a hover tooltip spelling
         out why — a tracked-only signal no longer reads the same as a
         real, funded position. s.autotrade_fired itself (the actual
         data) is untouched; this is display-only.
         Verified with py_compile, an actual runtime start, pyflakes,
         node --check on the correctly-last <script> block, and the
         Flask route/def integrity check (still 64 routes) — JS/display
         change only, no Python logic touched.

v0.99.74 - Direct user request, immediate follow-up to v0.99.73's own
         clarification: "мне не нужны уведомления в тг по монетам,
         которые не в автоторговле." msnr_scan_symbol_live()'s
         send_telegram() call now fires ONLY when record["autotrade_
         fired"] is True — the exact same flag set (alongside
         leverage_used/live_size_usd) inside the order_opened branch a
         few lines above, not a separate approximation of it. Before
         this, v0.99.55 sent a notification for EVERY detected signal
         regardless of whether real money was ever at risk, with a
         "плечо (реком.)" fallback label specifically for the not-
         autotraded case — that fallback and the notification it
         labeled are both gone now; a signal on a symbol with no
         autotrade checkbox simply doesn't message at all. The signal
         itself is still logged and tracked toward WIN/LOSS exactly as
         before (record["status"]="OPEN" above is unconditional,
         unchanged — same v0.99.73 "OPEN (сигнал)" UI distinction
         still applies for that case) — only the Telegram send became
         conditional, not the underlying per-symbol statistics
         collection this session has repeatedly relied on (raw_closed_n,
         skip_rr_min, the hour/volume filters, etc. all still need
         every symbol's full history regardless of whether it trades).
         Verified with py_compile, an actual runtime start, a direct
         check of the new condition against both cases (autotrade_
         fired=True correctly notifies, False correctly doesn't),
         pyflakes, node --check on the correctly-last <script> block,
         the Flask route/def integrity check (still 64 routes), and an
         AST walk for duplicate top-level defs (none introduced).

v0.99.75 - Direct user request: "делаем новую сортировку для топ 10 и
         остального списка, золото принудительно пока убираем,
         ранжирует по винрейта, количеству в выборке до (фильтров),
         доход. Эти параметре по убыванию главные. Я должен увидеть
         плавное убывание в топ 10 и последующее продолжение убывание
         вне списка." Flagged once, briefly, before implementing
         exactly as asked: a pure lexicographic sort checks winrate
         FIRST, so a thin sample with a lucky high winrate can outrank
         a large, steady one — precisely what msnr_ranking_score()'s
         lower-confidence-bound existed to prevent. Implemented with
         eyes open per the explicit request for something simple and
         transparent over that protection, and reproduced the trade-off
         concretely in testing (a synthetic 2-trade/100%-winrate symbol
         ranked #1, above a 70%-winrate/80-trade one) so it's a known,
         demonstrated consequence, not a surprise later.
         New msnr_symbol_rank_key(ov): a plain 3-key tuple (winrate,
         raw_closed_n, compound_return_pct), each DESCENDING, in the
         exact priority order requested. Replaces TWO previously
         DIFFERENT sorts that used to disagree with each other — msnr_
         rank_by_winrate_sample()'s own weighted income/score composite
         (which decided top-10 membership) and api_msnr_status()'s
         separate score-only sort (which decided the overall table's
         display order) — that mismatch is exactly what produced the
         "не плавное убывание" the request describes: a symbol's table
         position didn't necessarily track its own top-10 standing.
         Both now read this same function, so scrolling from #1 through
         #10 into "the rest" is one continuous ordering.
         msnr_rank_by_winrate_sample() also DROPPED the MSNR_AUTOTRADE_
         TOP_MIN_SAMPLE hard exclusion it used to apply — per the same
         request's own "продолжение убывание вне списка": a hard
         sample-size cutoff would carve a GAP out of the ranking instead
         of a smooth decline, and raw_closed_n is now the ranking's own
         second key anyway, so a thin sample naturally sinks toward the
         bottom of ties rather than disappearing from the list outright.
         Gold's forced inclusion removed from BOTH places it existed —
         msnr_autotrade_eligible_symbols() (used to always prepend
         MSNR_SYMBOLS regardless of the top-10 ranking) and msnr_
         compute_live_universe() (used to always seed `promoted` with
         MSNR_SYMBOLS before the separate winrate>50%+sample>40 rule) —
         gold now competes for both a top-10 slot and live-scan
         inclusion purely on the same footing as every other symbol,
         per "золото принудительно пока убираем." Nothing about gold's
         own detection/backtesting itself changed.
         Frontend: _msnrSortKey's default changed from 'score' to null
         (found while implementing — a client-side re-sort by a
         DIFFERENT single field on every render was silently undoing
         the backend's own new continuity the moment the table
         rendered, a second, separate source of the same "не плавное
         убывание" complaint). null means "trust the backend's already-
         sorted order," preserved via a same-array-order comparator
         return; clicking a column header (WR/n) still overrides with a
         single-field sort exactly as before. Updated the MSNR panel's
         own description text (was still claiming "золото всегда",
         no longer accurate) and added a one-line note explaining the
         new unified ranking rule.
         Verified with py_compile, an actual runtime start (synthetic
         5-symbol case: confirmed a stress_test_failed symbol is
         excluded regardless of its own numbers; confirmed the small-
         sample trade-off concretely, as described above; confirmed
         gold no longer sorts first by construction, landing wherever
         its own numbers place it; confirmed msnr_compute_live_universe()
         correctly excludes a low-winrate gold symbol that no longer
         clears the promotion rule on its own), pyflakes, node --check
         on the correctly-last <script> block, the Flask route/def
         integrity check (still 64 routes), and an AST walk for
         duplicate top-level defs (none introduced — all four touched
         functions present exactly once).

v0.99.76 - Direct user follow-up to v0.99.75, immediate: "Так для того
         я и написал 3 параметра, чтобы на выборку и доход тоже
         учитывало" — v0.99.75's plain lexicographic (winrate,
         raw_closed_n, доход) tuple checked winrate FIRST and only
         consulted the other two on an exact tie, which essentially
         never happens with continuous values — in practice that was
         ranking by winrate ALONE, not genuinely factoring in all
         three as intended.
         Replaced with a normalized weighted composite. New msnr_
         compute_rank_bounds(overrides): min/max bounds for winrate,
         raw_closed_n, and compound_return_pct across every non-errored
         symbol — computed ONCE as a single canonical reference, not
         separately per view. This mattered as much as the formula
         change: normalizing over two DIFFERENT candidate subsets (e.g.
         top-10-eligible vs the whole table) would let the same
         symbol's composite score DIFFER depending on which one asked,
         reintroducing v0.99.75's own "не плавное убывание"
         discontinuity in a new place. New msnr_symbol_rank_score(ov,
         bounds): min-max normalizes each metric to [0,1] against those
         shared bounds, combines via MSNR_RANK_WINRATE_WEIGHT (0.5) +
         MSNR_RANK_SAMPLE_WEIGHT (0.3) + MSNR_RANK_INCOME_WEIGHT (0.2)
         — winrate weighted heaviest, sample next, доход last, matching
         "эти параметре по убыванию главные" now read as descending
         WEIGHT rather than descending sort-key precedence. A symbol
         missing a metric scores 0.0 (worst) on that term rather than
         being skipped or defaulting to the population average.
         msnr_rank_by_winrate_sample()/msnr_autotrade_eligible_symbols()
         both gained an optional `bounds` param (falls back to a fresh
         per-call computation when omitted, for a caller — mainly tests
         — that only needs one ranking in isolation). api_msnr_status()
         now computes msnr_rank_bounds ONCE and passes the same dict to
         both eligibility and the overall table's own sort, guaranteeing
         a symbol's score is identical everywhere it's used — same
         continuity property v0.99.75 established, preserved through
         this formula change rather than accidentally lost.
         Verified with py_compile, an actual runtime start (synthetic
         5-symbol case, same as v0.99.75's own reproduction: confirmed
         ETH_USDT (70% winrate, 80 trades, 500% income) now correctly
         OUTRANKS TINY_USDT (100% winrate, only 2 trades) — composite
         0.75 vs 0.5 — reversing v0.99.75's own demonstrated small-
         sample-luck outcome, which was exactly the point of this
         follow-up; confirmed stress_test_failed symbols still excluded
         from ranking while still contributing to the shared bounds;
         confirmed msnr_autotrade_eligible_symbols() and msnr_compute_
         rank_bounds() agree when bounds are threaded through explicitly),
         pyflakes, node --check on the correctly-last <script> block, the
         Flask route/def integrity check (still 64 routes), and an AST
         walk for duplicate top-level defs (none introduced — all four
         new/touched functions present exactly once, old msnr_symbol_
         rank_key() fully removed, no dangling references left in code,
         only in historical changelog/comment text).

v0.99.77 - Direct user follow-up to v0.99.76, immediate: "А доход
         учтен? Все три компонента должны быть хорошими." Confirmed
         income (доход) genuinely was already being read into v0.99.76's
         weighted sum — but "все три компонента должны быть хорошими"
         is a stronger requirement a weighted ARITHMETIC sum can't
         actually guarantee: addition always lets a large value on one
         metric COMPENSATE for weakness on another, and with an
         unbounded metric like compound_return_pct (no natural ceiling
         the way winrate has), there's always some extreme-enough
         income figure that could offset a mediocre winrate/sample
         regardless of how the weights are tuned.
         msnr_symbol_rank_score() switched from a weighted sum to a
         WEIGHTED GEOMETRIC MEAN (product) of the same three normalized
         factors: winrate_norm^w1 * sample_norm^w2 * income_norm^w3,
         same weights (0.5/0.3/0.2) reused directly as exponents. A
         product structurally cannot be rescued by strength elsewhere —
         if any one normalized factor is 0, the whole composite is 0,
         which is the actual mathematical shape of "all three must be
         good," not something weight-tuning under addition could ever
         fully deliver. Bounds computation (msnr_compute_rank_bounds())
         and the shared-bounds-across-both-callers design are completely
         unchanged — only the combination step changed.
         Documented (not hidden) a real consequence of the switch: min-
         max normalization gives the single worst symbol in the current
         pool on any one metric an exact 0.0 there, and under a product
         that zeroes its ENTIRE composite even if the other two metrics
         are fine — can look harsh for a symbol only marginally the
         pool's worst on one axis. Left as-is rather than softening
         with an artificial floor, which would just be a smaller-scale
         reintroduction of the same compensation this change exists to
         remove; for ranking purposes only relative order matters.
         Verified with py_compile, an actual runtime start (re-ran the
         same 5-symbol synthetic case used to verify v0.99.76: LOTTERY_
         USDT — 20% winrate, 10 trades, but a 2000% income 10x anything
         else in the pool — now scores EXACTLY 0.0 despite that income,
         confirming no amount of one strong metric rescues being the
         pool's worst on another; also surfaced the documented floor
         consequence directly in this same test, AVG3_USDT independently
         hit 0.0 too purely for being the pool's lowest-income entry,
         despite unremarkable-but-not-worst winrate/sample — exactly the
         harsh-floor trade-off called out above, now demonstrated, not
         just described; confirmed backward-compatible default bounds
         still work when omitted), pyflakes, node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (still 64 routes), and updated the MSNR panel's own
         description text (was still describing "→" priority ordering,
         now describes the product/none-can-compensate design).

v0.99.78 - Direct user request, pointing at a screenshot of the panel's
         own description text: "Убери эту квалификацию с вирейтоп 50 и
         выборкой 40, что раз просил убрать это, технически." Correct
         catch — an earlier ask_user_input in this same ranking-redesign
         thread had asked exactly this ("Убрать это старое правило
         (винрейт>50%+выборка>40)..."), but the reply that followed
         redirected into designing the new top-10 ranking instead of
         answering yes/no, and v0.99.75's own gold-removal pass only
         stripped GOLD's special case OUT OF this rule — the rule
         itself (MSNR_LIVE_PROMOTE_MIN_WINRATE/MIN_SAMPLE) kept running
         the whole time, which is exactly why TRX_USDT could still earn
         the live-scan dot in the original live report despite no
         top-10 standing and no manual checkbox — the very confusion
         this whole ranking redesign started from was never actually
         fully closed off.
         msnr_compute_live_universe() rewritten to simply delegate to
         msnr_autotrade_eligible_symbols() (current top-10 by msnr_
         symbol_rank_score()) — the standalone winrate>50%+sample>40
         promotion loop is gone, not just gold's exemption from it. A
         symbol now earns the live-scan dot through exactly two paths:
         top-10 standing, or msnr_effective_live_universe()'s own
         separate manual-toggle union — nothing else. Threaded `bounds`
         through this function too (matching msnr_autotrade_eligible_
         symbols()'s own v0.99.76 parameter) so the backtest-loop call
         site computes rank bounds once and passes them through,
         staying consistent with the same-cycle top-10 selection rather
         than silently recomputing its own.
         MSNR_LIVE_PROMOTE_MIN_WINRATE/MIN_SAMPLE left defined (their
         own comments updated to note the retirement) rather than
         deleted, matching this session's established "leave vestigial
         constants for a possible future reintroduction" pattern (same
         treatment MSNR_MAX_RR got in v0.99.68) — removed from the API
         config dict and the panel's own description text instead,
         since displaying a threshold nothing enforces anymore would be
         actively misleading, the same complaint that started this fix.
         Verified with py_compile, an actual runtime start (synthetic
         13-symbol case: a TRX_USDT-shaped entry — 56.1% winrate, 59
         trades, well clear of the old 50%/40 thresholds on its own —
         placed among 12 stronger competitors correctly does NOT appear
         in the live universe now, confirming the old rule's standalone
         promotion path is truly gone and not just gold's exemption
         from it; also confirmed a small pool where every candidate
         naturally fits within top-10 still includes it, for the
         mundane reason of clearing top-10 on the merits, not the
         retired rule), pyflakes, a grep confirming zero remaining
         references to the removed config fields anywhere in the JS,
         node --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 64 routes), and an AST walk
         for duplicate top-level defs (none introduced).

v0.99.79 - Direct user request: "Skip RR>3, давай подобную проверку
         тоже уберем, пока важно все RR торговать." Same treatment as
         v0.99.68's MSNR_MAX_RR removal — skip_rr_min was exactly the
         per-symbol statistical filter that removal said should be
         "fully trusted" to judge which RR ranges are worth trading
         ("довериться skip_rr_min целиком"); now even that gets
         disabled so no RR range is excluded at all while more raw data
         accumulates across the full spectrum, matching the strategy's
         own stated design (catch large-RR/low-winrate moves).
         Disabled at both the two places it was applied, same
         "comment out, don't delete" pattern used throughout this
         session for reversible experiments (MSNR_MAX_RR's pooled
         autotune in v0.99.52, VGI's tp_extend rule in v0.99.65):
         msnr_optimize_symbol() now hardcodes best["skip_rr_min"]=None
         instead of calling msnr_symbol_rr_skip_min() — the filtering
         block right after it (guarded by `if best["skip_rr_min"] is
         not None`) becomes a natural no-op rather than needing its own
         separate disable, and rr_filtered_count stays a real (not
         hardcoded-elsewhere) computation off before/after len(), so it
         self-corrects to 0 automatically rather than needing to
         remember updating it too if this is ever reintroduced.
         msnr_scan_symbol_live()'s own live-firing check (would have
         become a no-op naturally after the next backtest cycle refreshed
         the now-always-None override anyway) was also commented out
         directly, for immediate effect rather than waiting on a stale
         cached value. Both msnr_symbol_rr_skip_min() (backtest-side
         computation) and msnr_symbol_skip_rr_min() (live-side lookup)
         are left fully defined and untouched, same as MSNR_MAX_RR's own
         vestigial treatment — one call away from reintroduction if a
         future session wants it back. Updated the MSNR panel's own
         description text (was still describing skip_rr_min as actively
         filtering) to say it's disabled and every RR range trades.
         Verified with py_compile, an actual runtime start (confirmed
         both msnr_symbol_rr_skip_min() and msnr_symbol_skip_rr_min()
         remain defined and callable, just no longer invoked from either
         call site), pyflakes, node --check on the correctly-last
         <script> block, the Flask route/def integrity check (still 64
         routes), and an AST walk for duplicate top-level defs (none
         introduced — no Python functions added or removed, only two
         call sites disabled).

v0.99.80 - CRITICAL FIX, direct user report with a live number: "в топ
         [10] попадают монеты с доходом 2% за 52 сделки, это нелогая
         фигня." Also asked directly whether Kelly leverage-fitting
         literally maximizes income — confirmed NO (its objective is
         E[log(1+pnl_frac)], the log-growth/Kelly criterion, specifically
         NOT the same as maximizing raw return, which would be reckless
         under repeated compounding) — that wasn't the cause here.
         Root cause was in msnr_symbol_rank_score() itself (v0.99.76-79's
         weighted geometric mean, weights 0.5/0.3/0.2 descending):
         reproduced with a synthetic case matching the report exactly
         (65% WR/60 trades/800% доход vs 62% WR/52 trades/2% доход) — the
         2%-доход symbol still scored 0.4943, essentially half the
         maximum. Cause: raising a normalized value x∈[0,1] to a SMALL
         exponent w compresses it toward 1 regardless of how bad x is
         (0.061^0.2 ≈ 0.57) — a weight in a geometric mean sets both "how
         much a good value helps" AND "how much a bad value hurts" at
         once, they can't be tuned independently. "Доход matters least"
         (low weight) and "доход must still be good" (v0.99.77's own
         stated goal) were mathematically in tension the entire time,
         not an edge case — any low-weighted factor would have shown
         this same dilution given a bad-enough value.
         Presented two fixes (equal weights vs. a hard floor gate on
         доход, mirroring stress_test_failed); user chose "Равные веса —
         настоящее «all must be good», без приоритета." MSNR_RANK_
         WINRATE_WEIGHT/SAMPLE_WEIGHT/INCOME_WEIGHT all changed from
         0.5/0.3/0.2 to 1/3 each — every factor now punishes and rewards
         identically, trading away the descending-priority ordering
         v0.99.76 had tried (and, per this report, failed) to express
         through weight alone, in exchange for actually delivering "all
         three must be good."
         Verified with py_compile, an actual runtime start: re-ran the
         exact reproduction case — the 2%-доход symbol's composite
         dropped from 0.4943 to 0.3431 (a real, meaningful punishment,
         though still nonzero since 2% isn't the pool's absolute worst
         in a 3-symbol test); a more realistic 16-symbol pool (15
         reasonably competitive alternatives plus the same FLAT symbol)
         confirmed it correctly falls to position 15 of 16, well outside
         top-10, resolving the actual reported symptom. Updated the MSNR
         panel's own description text (was still saying "винрейт важнее
         всего, доход меньше всего," no longer true). pyflakes, node
         --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 64 routes) — constants-and-
         docstring change only, no new functions.

v0.99.81 - Direct user report: "термукс был жив, сигналы работали, но
         бэктест не выполнялся больше 5 часов, проверь почему так может
         быть." Investigated thoroughly rather than defaulting back to
         the earlier Android-kill theory (which the report itself rules
         out — a killed process wouldn't leave live signals running):
         confirmed every individual HTTP request in get_candles_range()
         is bounded (HTTP_TIMEOUT=15s, capped retries on both 429 and
         connection-error paths, no unbounded inner loop) — no literal
         infinite hang exists in that function. Worst-case arithmetic
         (every chunk of every symbol maxing out every retry, 150+
         symbols across 8 workers) only reaches ~1.8h, well short of the
         reported ~5h — the exact mechanism for the gap between that
         calculation and the live report remains genuinely unconfirmed
         (likely compounding delay under sustained bad network
         conditions and/or GLOBAL_HTTP_SEMAPHORE contention shared
         across this app's 14 other background loops, but not proven).
         Presented this honestly rather than overclaiming a fix, and
         offered three options; user chose "Только диагностика...
         ничего не менять" — observability only, no change to actual
         cycle timing/retry/wait behavior.
         New msnr_backtest_watchdog(): an independent daemon thread
         (separate from msnr_backtest_loop() itself, so it keeps
         checking in even if that loop really were stuck on something
         invisible to it) polling every MSNR_BACKTEST_WATCHDOG_
         INTERVAL_SEC (5 min) — if STATE["msnr_backtest_running"] has
         been true longer than MSNR_BACKTEST_WATCHDOG_THRESHOLD_SEC (20
         min, comfortably above the ~6-9 min baseline this app's own
         logs have shown), logs STATE["msnr_backtest_in_flight"] (the
         same list _msnr_backtest_one_symbol() already maintains, no
         new tracking needed) plus done/total progress — so a repeat
         leaves a concrete trail of exactly which symbol(s) were still
         pending, instead of another silent multi-hour gap with nothing
         to diagnose from afterward. Warns once per threshold-crossing
         per cycle (resets the moment the loop observes the cycle isn't
         running anymore), not every 5 minutes for hours.
         Verified with py_compile, an actual runtime start (synthetic
         STATE: backtest "running" for 25 simulated minutes with two
         symbols still in msnr_backtest_in_flight — confirmed the
         watchdog's own threshold check correctly fires and would log
         exactly those two symbols plus the done/total progress),
         pyflakes, node --check on the correctly-last <script> block,
         the Flask route/def integrity check (still 64 routes), and an
         AST walk for duplicate top-level defs (none introduced).

v0.99.82 - Direct user report with a screenshot (CHIP_USDT, an older
         breakout signal): "volume криво отображает график, точка входа
         не на графике, стопа или тейка не видно тоже." Investigated
         and found the real cause wasn't a rendering/scale bug at all:
         api_profile() (the Volume Profile chart endpoint) always
         fetched "the latest N candles" via get_candles(limit=...), with
         no way to anchor to a SPECIFIC past signal's own time. Clicking
         an older/resolved signal — especially one where price has since
         moved a lot — showed TODAY's candles with that old trade's
         entry/sl/tp lines overlaid at their own historical price
         levels; if price moved far enough, those levels genuinely sit
         outside the displayed window, matching "точка входа не на
         графике" exactly. Same class of bug already found and fixed
         for MSNR's own chart (api_msnr_chart()'s own docstring has that
         fuller incident) — re-deriving/re-fetching against CURRENT
         state instead of anchoring to the historical moment actually
         being reviewed.
         Fixed: openChart()/the "Оптимизировать" re-fetch now pass
         `time` (the clicked row's own signal time — already present on
         every row, already used for fmtTime(r.time) in the same table,
         nothing new to track) to api_profile(). When given, the
         backend now fetches via get_candles_range() anchored around
         THAT time (lookback+10 bars before, 90 after) instead of
         "whatever's most recent" — and the volume PROFILE itself is
         built only from candles AT OR BEFORE the signal's own time,
         matching what the original trade's own zones would actually
         have been computed from (no lookahead into price action the
         trade couldn't have known about at the time). Omitting `time`
         keeps the exact original "latest N candles" behavior — fully
         backward compatible for any other caller of this endpoint.
         Verified with py_compile, an actual runtime start, pyflakes,
         a synthetic candle-filtering test (200 candles, signal at
         index 100: confirmed the profile-source list correctly stops
         at the signal's own time — 101 candles, last one's time <=
         sig_time — while the DISPLAY candle list correctly still
         extends past it, so the chart can show the trade's own
         resolution), node --check on the correctly-last <script>
         block, and the Flask route/def integrity check (still 64
         routes — no new endpoints, existing one extended).

v0.99.83 - Direct user request: "можно удалить все что связано с
         дивергенцией, ема, сессия, сессия ny, xau lg, vgi, аккуратно,
         с перепроверкой чтобы не удалить лишнего, а так прям все, из
         настроек и тп все убрать будто и небыло." A large, multi-turn
         removal across six modules — this version covers ONLY the
         first, VGI, done completely and verified before moving to the
         next (given the file's scale and the risk of a blind mass
         edit, each module gets its own full removal + verification
         pass rather than all six at once).
         Found one important cross-module dependency BEFORE removing
         anything, per the "не удалить лишнего" part of the request:
         openVgiChart()/drawVgiChart() (the chart modal/canvas) is
         genuinely SHARED infrastructure — openScalpChart() and
         openXauLgChart() both reuse it (v0.94.0/v0.99.66's own "thin
         wrapper, not a duplicate" reasoning) rather than each
         duplicating ~90 lines of canvas code. Since Scalp isn't being
         removed, this modal/canvas had to stay — only VGI's OWN usage
         of it (a direct call with no endpoint override, from VGI's
         now-deleted signals table) was removed. openVgiChart()'s
         `endpoint` parameter lost its default value (used to point at
         '/api/vgi/chart', now a deleted route) since both remaining
         callers always pass their own explicit endpoint — a future
         caller that forgets one now gets an immediate error instead
         of silently 404ing.
         Removed: vgi_build_profile/vgi_section_at_price/vgi_nearest_
         zone/vgi_evaluate_signal (the ported math), all VGI_* constants,
         AUTOTRADE_ENABLED_VGI/AUTOTRADE_LEVERAGE_VGI/TELEGRAM_ALERTS_
         VGI, every VGI STATE key (universe/backtest_results/summary/
         signals/timestamps) including its entries in has_open_signal_
         any_module() and the full-state snapshot, the entire backtest/
         live-scan/outcomes infrastructure (vgi_build_universe through
         vgi_live_loop, ~340 lines), all 4 API routes (status/signals/
         chart/reset), the risk_autotune_pass() vgi block, both setters
         (_set_vgi_invert/_set_vgi_min_rr) and their own now-dead
         one-time-migration startup code (v0.99.65's vgi_min_rr
         death-spiral correction — meaningless once VGI_MIN_RR itself
         is gone), all SETTINGS_KEYS/apply_settings/get_settings wiring
         (3 lists + 2 update blocks + 3 dict entries + 2 global
         declarations), the send_telegram() category gate, both
         background thread starts, and the entire frontend footprint:
         tab button, panel div, refreshVgi() (~75 lines), the reset
         button + its wireResetButton() call + CSS selector, both
         settings-panel rows (Telegram alerts, autotrade+leverage), and
         all activeTab==='vgi' branches (4 places).
         Historical changelog text describing VGI's own past development
         (top-of-file docstring, ~150+ lines across v0.98.0-v0.98.9)
         deliberately LEFT AS-IS — matches this file's own established
         pattern of preserving historical reasoning for removed/replaced
         features elsewhere (e.g. MSNR_MAX_RR's comment still describes
         its now-disabled autotune history) rather than erasing project
         history; it's dead documentation with zero effect on runtime,
         not a functional trace of the module "как будто было".
         Verified with py_compile, an actual runtime start, pyflakes
         (iterated to a fully clean run — caught 7 live references
         py_compile alone couldn't: a dangling vgi_signals STATE restore
         in load_state(), both setters still called from api_reset_
         risk_autotune() AND the (now also removed) startup migration,
         and both background thread starts — none of these are syntax
         errors, only real NameErrors at runtime, exactly the class of
         bug py_compile structurally cannot catch), node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (60 routes — down from 64, exactly the 4 VGI endpoints
         removed, none of the other 60 touched), an AST walk confirming
         zero VGI functions remain at module level and no duplicates
         were introduced, and a grep confirming every remaining "vgi"
         hit in the file is either the shared openVgiChart infrastructure
         (correctly kept) or historical changelog text (inert).

v0.99.84 - CRITICAL FOLLOW-UP FIX, found while starting the next
         module's removal (Divergence) and doing a fresh exhaustive
         sweep for VGI leftovers before touching anything new: v0.99.83's
         own VGI removal had genuinely missed several live references —
         pyflakes came back clean at the time, but pyflakes only checks
         Python NAME resolution, not dict STRING KEYS or unused MODULE-
         level constants, so several classes of leftover reference
         couldn't have been caught by it in the first place, only by
         re-reading with fresh eyes.
         Found and fixed: (1) a second `global VGI_ENABLED, VGI_INVERT_
         SIGNALS, VGI_MIN_RR, ...` declaration in apply_settings() (a
         DIFFERENT settings-related function than the one already
         cleaned), plus the matching get_settings() dict entries and
         apply_settings() if-blocks that actually assigned them —
         apparently VGI had its own plain "enabled" toggle beyond the
         AUTOTRADE_ENABLED_VGI/TELEGRAM_ALERTS_VGI ones already found,
         never caught in the original sweep; (2) two leftover
         SETTINGS_KEYS entries ("vgi_enabled"/"vgi_invert_signals" in
         one list, "vgi_min_rr" in another); (3) a dead module-level
         constant, RISK_AUTOTUNE_VGI_RR_BOUNDS (pyflakes doesn't flag
         unused module globals the way it flags unused locals); (4) the
         actually SERIOUS one — _relink_sim_trade()'s own module_lists
         dict still had a `"vgi": STATE["vgi_signals"]` entry. Since
         Python evaluates dict literal VALUES eagerly at construction
         time (not lazily per key access), this meant STATE["vgi_
         signals"] was evaluated — and threw KeyError — on EVERY single
         call to this function, for ANY trade's mode, not just VGI
         ones. This one wasn't cosmetic dead code like the others; it
         was a live crash in a function every module's own simulator
         trade-relinking path depends on.
         Verified with py_compile, an actual runtime start (directly
         called _relink_sim_trade({"mode": "vgi", ...}) — confirmed it
         now returns None cleanly instead of raising KeyError), pyflakes
         (clean), an exhaustive grep for VGI_ENABLED/VGI_INVERT_SIGNALS/
         VGI_MIN_RR/RISK_AUTOTUNE_VGI_RR_BOUNDS and any remaining
         "vgi_"-prefixed string key anywhere in the file (only
         historical changelog text remains), node --check on the
         correctly-last <script> block, and the Flask route/def
         integrity check (still 60 routes, unaffected — none of these
         were route-level).
         Lesson for the remaining 5 modules' own removal passes: do a
         dedicated final sweep for dict STRING KEYS (STATE[...] access,
         module_lists-style dispatch dicts) and module-level constants
         specifically, not just trust py_compile+pyflakes+node --check
         to catch everything — they structurally can't catch either of
         those two categories.

v0.99.85 - Direct user request continued: 2nd of 6 modules removed
         entirely — Divergence. Same "будто и не было" scope as VGI
         (v0.99.83): code, STATE, routes, settings, autotrade/Telegram
         wiring, frontend. Structurally different from VGI though —
         Divergence was integrated into the SHARED scan_loop() via `if
         DIVERGENCE_ENABLED:` blocks appending to one futures list
         alongside Volume/EMA/Scalp/Session (which stay), not its own
         independent background loop — required surgically removing 3
         such blocks rather than deleting a whole function.
         Two real correctness bugs found and fixed along the way, both
         the same class as v0.99.84's own critical VGI fix (dict string
         keys py_compile/pyflakes structurally can't see): (1) _relink_
         sim_trade()'s module_lists dict still had "divergence": STATE[
         "div_signals"] — same eager-dict-literal KeyError-on-every-call
         bug as VGI's own; (2) SNAPSHOT_MODULE_KEYS (a separate .get()-
         based dispatch dict for a different snapshot feature) also had
         a "divergence": "div_signals" entry — safe via .get() but dead
         weight pointing at a removed STATE key.
         One near-miss, caught before it caused damage: initially
         deleted compute_rsi() alongside find_pivots()/simulate_pivot_
         stability() (all three sat in the same "RSI divergence" code
         block) — but a fresh pyflakes/grep check found FT5's own
         run_ft5_backtest() calls compute_rsi() directly as part of its
         own indicator stack (compute_fisher_rsi/compute_macd/compute_
         adx/compute_stoch_fast/compute_sma/compute_sar), unrelated to
         Divergence despite living in the same file section — genuinely
         shared infrastructure, the same category openVgiChart() turned
         out to be during the VGI pass. Restored compute_rsi() alone
         (find_pivots()/simulate_pivot_stability() confirmed truly
         divergence-only via a dedicated grep before leaving them
         removed), with period's default changed from the now-deleted
         DIV_RSI_PERIOD constant to its own literal former value (14) —
         FT5's call site never passed period explicitly either way.
         Also found and fixed TWO leftover VGI settings-UI elements
         missed in v0.99.83/84's own removal passes — a full "VGI
         (Volume Gaps & Imbalances)" settingsGroup (scan toggle +
         invert-signals row) and their own vgi_enabled/vgi_invert_
         signals entries in the JS settings-mapping object — found only
         because this pass's own exhaustive frontend grep happened to
         pattern-match "div" broadly enough to also catch "individual"-
         adjacent VGI leftovers sitting nearby; confirms the earlier
         lesson generalizes past just Python dict keys to frontend
         markup too.
         Removed: detect_divergence()/_rsi_cut_through() (the ported
         math), compute_div_tp_sl()/has_open_divergence_signal()/scan_
         symbol_divergence()/close_div_signal()/update_divergence_
         outcomes()/compute_divergence_stats() (infrastructure), find_
         pivots()/simulate_pivot_stability() (confirmed divergence-only,
         unlike compute_rsi), div_stability_cycle() and its own _div_
         stability_cursor/DIV_STABILITY_PER_CYCLE, all 4 setters, the
         risk_autotune_pass() divergence block, all 4 API routes
         (status/signals/chart/reset), all DIV_* constants (one 63-line
         block), AUTOTRADE_ENABLED_DIVERGENCE/AUTOTRADE_LEVERAGE_
         DIVERGENCE/TELEGRAM_ALERTS_DIV and every settings/dispatch-dict
         reference to them, _div_cooldowns/_div_cooldowns_lock, div_
         signals/div_pivot_stability/div_last_scan_finished/div_last_
         scan_duration/filtered_by_div_min_rr STATE keys and every read/
         write site (load_state, save/snapshot, scan_loop, api_reset()),
         and the entire frontend footprint (tab, table+stats-panel pair,
         refreshDivergence(), reset button, settings group, both
         modeLabels dict entries, the vpModeChecked fallback redirect —
         now points at 'ema' instead of the deleted 'divergence' tab).
         Verified with py_compile, an actual runtime start (confirmed
         _relink_sim_trade() no longer raises KeyError for either
         "divergence" or "vgi" trade modes; confirmed compute_rsi()
         still produces correct-length output), pyflakes (clean),
         node --check on the correctly-last <script> block, the Flask
         route/def integrity check (56 routes — down from 60, exactly
         the 4 divergence endpoints removed), an AST walk confirming
         zero divergence functions remain at module level with no
         duplicates introduced, and an exhaustive grep pass confirming
         every remaining div_*/DIV_* hit in the file is either an inline
         comment on an unrelated constant or historical changelog text.

v0.99.86 - Direct user request: "много слабых результатов в mnsr, по
         50 сделок а доход околонулевой, при этом винрейт от 30 до 50,
         может надо переосмыслить что-то, RR, отсечение всегда
         убыточного диапазона RR, как снизу так и сверху, придумать
         новые фильтры. Еще, хочу видеть не только сделок до и после
         фильтров, а так же винрейт и доход до и после, чтобы понимать
         эффективность фильтров и менять их на другие своевременно."
         Two-sided RR filtering: new msnr_symbol_rr_range() replaces
         msnr_symbol_rr_skip_min() (v0.99.79 had fully disabled the old
         one-sided version, per an earlier direct request to trade
         every RR range while more data accumulated — this
         reintroduces filtering, but as a genuinely different symmetric
         design, not a plain revert). Same bucket-and-breakeven test
         every other MSNR filter already uses, applied from BOTH ends:
         a ceiling (unchanged meaning from the old rule) AND a new
         floor, found by scanning buckets from RR=0 upward for the
         longest contiguous run of failing buckets starting at the
         bottom. Caught and fixed a real logic bug before shipping via
         a synthetic 3-scenario test: the ceiling search initially
         didn't exclude the floor's own failing buckets, so a failing
         low-RR bucket could itself get mistaken for "the ceiling,"
         producing a nonsensical ceiling=0 that would have skipped
         everything — fixed by having ceiling search only buckets past
         the floor's own contiguous run. Verified against 3 cases (both
         ends failing, only-high failing matching the old rule's
         behavior, and nothing failing) — all three now correct.
         Re-enabled in msnr_scan_symbol_live() (was commented out since
         v0.99.79) checking both skip_rr_min (ceiling) and the new
         skip_rr_max (floor, msnr_symbol_skip_rr_max() added as its own
         lookup, same separate-lookup pattern as skip_rr_min's own).
         Before/after filter diagnostics: new _msnr_filter_checkpoint()
         snapshots {n, winrate, income_pct} for a trade list, using a
         FRESH Kelly leverage search at that specific checkpoint rather
         than reusing the symbol's final leverage — reusing one fixed
         value would conflate "did this filter change the edge" with
         "does the final leverage happen to suit this intermediate
         set." msnr_optimize_symbol()'s filter pipeline (rr_range ->
         liquidation -> sl_pct -> hours -> volume) now builds a
         filter_checkpoints chain, one snapshot per STAGE TRANSITION
         (not two per filter) — each filter's "before" is exactly the
         previous filter's "after," so this costs one extra leverage-
         search+compound-sim per filter, not two. Exposed automatically
         via api_msnr_status()'s existing dict(v, ...) spread (no new
         endpoint needed) and rendered as a compact "фильтры: N→M · WR
         X%→Y% · доход A%→B%" summary (raw vs final checkpoint) in each
         row, with the full per-stage chain still available in the raw
         API response for anyone wanting per-filter granularity beyond
         this summary line. Updated the MSNR panel's own description
         text (was still saying skip_rr_min was disabled) and the
         skip-indicator display to show the new floor (skip rr<X)
         alongside the existing ceiling (skip rr≥X).
         Verified with py_compile, an actual runtime start (msnr_
         symbol_rr_range()'s own 3-scenario synthetic test described
         above; _msnr_filter_checkpoint() against an 80-trade realistic
         synthetic set — confirmed both winrate and income compute
         sensibly), pyflakes (clean), node --check on the correctly-
         last <script> block, the Flask route/def integrity check
         (still 56 routes — no new endpoints, existing one extended),
         an AST walk for duplicate top-level defs (none introduced),
         and a manual check that all new JS variables (skipRrMaxTxt,
         filterImpactTxt) are declared before their use in paramsTxt's
         own template string.

v0.99.87 - Direct user request: "По умолчанию индикатор msnr должен
         быть первым." Reordered the tab bar's markup — MSNR moved from
         7th position to 1st (kept its existing "active" class, which
         was already correctly making it the default-open tab content-
         wise; only its position in the tab BAR itself was off). Volume
         moved to 2nd. Checked for any code depending on tab ORDER
         (indexed access like tabs[0], next/prev-tab logic) before
         moving anything — found none; every reference to a specific
         tab already goes through its own data-tab name
         (querySelector('.tab[data-tab="msnr"]')-style), never a
         positional index, so reordering the markup couldn't silently
         break anything else.
         Also investigated a live report from the same message ("в
         телефоне не видно volume"): confirmed refreshStatus() fully
         hides the Volume tab (display:none, not just off-screen) when
         s.volume_profile_enabled is false — this is a genuine settings
         toggle (Настройки -> Volume Profile -> "Volume Profile
         сканер"), not a scroll/CSS cutoff; the mobile @media block's
         own .tabs rule is overflow-x:auto (horizontally scrollable,
         tabs stay reachable), which wouldn't produce a fully-missing
         tab the way this toggle would. Pointed the user at that
         specific toggle rather than guessing further or touching code
         for a setting that may simply be off — flagged as the likely
         cause, not yet confirmed fixed pending their check.
         Verified with py_compile, an actual runtime start, the Flask
         route/def integrity check (still 56 routes — markup-only
         change), and node --check on the correctly-last <script>
         block.

v0.99.88 - Direct user follow-up: "По умолчанию стал ема а не msnr" —
         v0.99.87's own tab reorder hadn't actually fixed the default
         tab after all. Root cause: refreshStatus()'s vpModeChecked
         fallback (v0.99.85's own "redirect to 'ema' instead of the
         deleted 'divergence' tab") — this existed from back when
         Volume/'signals' WAS the default active tab, specifically to
         avoid landing on a broken empty Volume tab when volume_
         profile_enabled is false. It unconditionally called .click()
         on the 'ema' tab the first time refreshStatus() ran (i.e. on
         every page load) whenever that setting was off — completely
         independent of which tab the MARKUP actually marked as
         default. Once MSNR became the default tab (v0.99.87), this
         redirect kept firing on load and immediately overriding it —
         exactly matching the user's own report from the previous
         message (Volume Profile scanner setting appears to be off on
         their instance, which is what triggers this path) landing on
         both symptoms from the same root cause.
         Fixed by removing the whole redirect block, not just changing
         its target tab: now that MSNR (not Volume) is the default,
         the ORIGINAL problem this redirect solved doesn't exist
         anymore — MSNR doesn't depend on volume_profile_enabled at
         all, so there's no "broken empty default tab" scenario left
         to redirect away from. Also removed the now-fully-unused
         vpModeChecked variable declaration (its only other reference
         was inside the block just deleted) rather than leaving a dead
         flag nothing reads or sets — activeTab is already correctly
         initialized to 'msnr' as its own separate variable, so no
         replacement redirect/flag was needed.
         Verified with py_compile, an actual runtime start, a grep
         confirming zero remaining references to vpModeChecked outside
         historical changelog text, node --check on the correctly-last
         <script> block, and the Flask route/def integrity check
         (still 56 routes — markup/JS-only change).

v0.99.89 - Direct user report: "На некоторых монетах фильтры никакие
         не применены." Root cause: v0.99.86's own new msnr_symbol_rr_
         range() (and the pre-existing msnr_symbol_sl_skip_min()) each
         used a FIXED 5-bucket scheme with no fallback, unlike the
         hour/volume filters (msnr_symbol_skip_hours()/msnr_symbol_
         volume_skip_below(), both v0.99.60) which already cascade from
         finer to coarser groupings when the fine split can't clear
         MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE=15 per bucket. A modest total
         sample — the same ~50-trade symbols the ORIGINAL report that
         motivated v0.99.86 itself described — splits into ~10/bucket
         on average across 5 fixed RR (or SL) buckets, already under
         the 15-per-bucket bar even before accounting for any real
         unevenness in the distribution, so BOTH the RR-range and
         SL-width filters could end up finding nothing significant at
         any single symbol with a merely-modest sample, regardless of
         how bad its actual pattern was — explaining the report
         directly, and closing a design inconsistency between filters
         that should never have existed once the hour/volume cascade
         precedent was already established.
         Fixed by extending the exact same cascade pattern to both:
         msnr_rr_bucket_stats()/msnr_sl_bucket_stats() gained an
         optional `bucket_scheme` parameter (defaults to the existing
         fixed MSNR_RR_BUCKETS/MSNR_SL_PCT_BUCKETS, so the pooled/
         display table's own behavior is completely unchanged). New
         MSNR_RR_BUCKET_SCHEMES/MSNR_SL_PCT_BUCKET_SCHEMES (5 buckets
         -> 3 -> 2, progressively coarser) — msnr_symbol_rr_range()/
         msnr_symbol_sl_skip_min() now try each scheme in turn, finest
         first, stopping at the first one that finds ANYTHING
         significant on either side, same "first width that clears the
         bar wins" philosophy MSNR_HOUR_GROUP_WIDTHS/MSNR_VOLUME_
         QUANTILE_GROUPS already established.
         Verified with py_compile, an actual runtime start (two
         targeted synthetic tests: (1) RR — 50 trades split evenly
         across 5 buckets (10 each, all under the 15 floor) with two
         adjacent buckets genuinely failing their own breakeven —
         confirmed the fine scheme finds nothing, but the cascade
         correctly falls through to the 3-bucket scheme and catches
         the merged bad region (floor=5); (2) SL-width — same shape,
         confirmed skip_sl_pct_min correctly resolves to 4 via cascade
         where the fine scheme alone would find nothing; both also
         re-verified against a large single-bucket sample to confirm
         the fine scheme still fires immediately without falling
         through, unchanged from pre-cascade behavior), pyflakes
         (clean), node --check on the correctly-last <script> block,
         the Flask route/def integrity check (still 56 routes — no new
         endpoints), and an AST walk for duplicate top-level defs (none
         introduced).

v0.99.90 - CRITICAL FIX, direct user report with a screenshot: 3
         identical error-log lines within the same minute — "save_state:
         [Errno 2] No such file or directory: '....json.tmp' ->
         '....json'". save_state()'s tmp-write-then-os.replace() pair is
         a standard atomic-save pattern, but it ran OUTSIDE any lock —
         only the `data = {...}` snapshot itself was protected by
         state_lock, briefly, before the file I/O. save_state() is
         called from ~26 different places across this app's many
         independent background loops (backtest cycles, live scans,
         sim-trade sweeps, settings changes, etc.), all sharing the
         exact same tmp_path (STATE_FILE + ".tmp", no per-call unique
         suffix) — if two callers' save_state() calls overlapped even
         slightly, the SECOND caller's os.replace() would find the tmp
         file already consumed by the FIRST caller's own replace (which
         atomically renames it away, so it no longer exists under that
         name), throwing exactly the reported ENOENT.
         Fixed with a dedicated _save_state_file_lock serializing just
         the write+replace pair — deliberately NOT reusing the broader
         state_lock for the file I/O itself, so a slow disk write never
         blocks unrelated state-reading/mutating code across the app's
         many other threads; the data snapshot still only needs
         state_lock briefly, exactly as before.
         Verified with py_compile, an actual runtime start — reproduced
         the exact reported error first on a deliberately-unlocked copy
         of the old write pattern (500 concurrent calls across 10
         threads against a throwaway state file: 121 failures, all the
         identical "[Errno 2] No such file or directory: '...tmp' ->
         '...'" message from the screenshot), then confirmed the actual
         fixed save_state() produces ZERO errors under the same 200-call/
         10-thread concurrent stress (double-checking the fix isn't just
         "didn't happen to trigger this time" but genuinely eliminates
         the race) — pyflakes (clean), node --check on the correctly-
         last <script> block, and the Flask route/def integrity check
         (still 56 routes — no new endpoints).
         Also noted for the record (not a bug, no action needed): the
         screenshot's 4th log line — "msnr_backtest_watchdog: cycle
         running 20.0min (done 77/190), still in flight: [...]" — is
         v0.99.81's own diagnostic firing exactly as designed, and
         confirms a real slow backtest cycle happened on this device
         (matches the earlier "5+ hour stall" investigation's own
         unresolved territory) — informational by design, not something
         this version needed to fix.

v0.99.91 - NEW MODULE: MIRROR — "зеркальный уровень" (support/resistance
         polarity-flip) reversal strategy. Built per direct user request
         after 7 screenshots of a manual trader's methodology (Instagram,
         "bigtrader88"): a support or resistance level gets BROKEN, and
         on price's later RETURN to that same level, it flips to the
         OPPOSITE role — broken support becomes resistance (SHORT setup),
         broken resistance becomes support (LONG setup). The moment this
         flip is confirmed by price touching back is "рождение зеркалки"
         ("birth of the mirror"). Entry is timed with one of four
         candlestick reversal patterns confirming rejection right at that
         level — user explicitly chose all four (over a lighter subset)
         and the full module (backtest + live scan + autotrade, over a
         lighter detection-only first pass) when scoped.
         Core detection (mirror_is_inside_bar/tweezers/rails/engulfing_
         doji, mirror_find_pivots, mirror_detect_signals): standard
         fractal HIGH/LOW pivots (deliberately NOT MSNR's own OCL/close-
         based pivots — a different, strategy-specific choice there; a
         "mirror level" is a classic wick-based S/R concept matching
         every screenshot's own level lines). A walk-forward state
         machine tracks each confirmed pivot level through: watched ->
         broken (a bar CLOSES past it, not just wicks through — a wick
         poke that immediately reclaims isn't a genuine "зеркалка") ->
         awaiting return (capped at MIRROR_MAX_BARS_TO_RETURN bars before
         going stale) -> pattern-confirmed signal, checked in a fixed
         order (inside_bar, tweezers, rails, engulfing_doji), first match
         wins, one signal per level. Entry = confirming bar's close;
         SL = just beyond the PATTERN's own extreme (the natural stop
         the source material itself draws — not a fixed %/ATR multiple
         like this app's more mechanical indicators); TP = entry ±
         risk×MIRROR_RR (a fixed RR target — the source trader's own
         exits are discretionary, watching for another reversal at the
         next level, but a mechanical pipeline needs a concrete rule;
         MIRROR_RR defaults within the 1:3–1:20 range the screenshots
         themselves report).
         Full standard infrastructure matching this session's own
         established module shape (closest to XAU LG's — single-
         timeframe, no per-symbol grid-search optimizer needed since
         pattern-matching is deterministic given fixed tolerances):
         mirror_build_universe() (capped, FT5-style), mirror_backtest_
         symbol()/mirror_track_outcome()/mirror_summarize_backtest(),
         mirror_scan_symbol_live() (dedup, has_open_signal_any_module
         guard, autotrade + sim + Telegram wiring with the pattern name
         spelled out in Russian), update_mirror_signal_outcomes() (MFE/
         MAE tracking), compute_mirror_signal_stats() (with a PER-
         PATTERN winrate breakdown — which of the 4 patterns is actually
         pulling its weight, same motivation as Volume's own per-reason
         stats), mirror_backtest_loop()/mirror_live_loop(), 4 API routes
         (status/chart/signals/reset — the chart route follows the same
         "look up stored data, don't re-derive with current params" fix
         already applied to MSNR/XAU LG's own charts), full settings
         wiring (SETTINGS_KEYS, get/apply_settings, autotrade+leverage,
         Telegram alerts), and the full frontend (tab now second only to
         MSNR, panel, refreshMirror(), reset button, settings groups,
         chart reuse via a thin openMirrorChart() wrapper around
         openVgiChart() — same "genuinely identical signal shape, don't
         duplicate ~90 lines of canvas code" judgment already applied to
         Scalp/XAU LG's own charts).
         Applied the session's own hard-won lessons proactively rather
         than discovering them the same painful way VGI/Divergence's
         removals did: STATE keys, has_open_signal_any_module()'s and
         _relink_sim_trade()'s own dispatch dicts, SNAPSHOT_MODULE_KEYS,
         and save_state()/load_state()'s own snapshot/restore all got
         their "mirror" entries added IMMEDIATELY alongside the STATE
         dict itself, not as a late follow-up fix. One real bug still
         caught and fixed mid-build via pyflakes: MIRROR_* constants
         were initially placed near the module's own logic (end of
         file), but STATE's own construction (much earlier in the file)
         needed MIRROR_SIGNAL_HISTORY already defined — moved the whole
         constant block next to every other module's own constants
         (right before STATE), matching why FT5_SIGNAL_HISTORY etc. all
         live there and not near their own modules' logic either. Also
         caught (via the SAME "no UI template already exists" discovery
         process): autotrade toggle+leverage rows for a module needed
         building from scratch by hand (following Session/EMA's own
         settings-modal pattern) since XAU LG/MSNR/FT5 — the modules
         checked first as templates — turned out to have NO such UI
         control at all (XAU LG's autotrade can only be toggled via a
         raw API call; MSNR's is per-symbol elsewhere; FT5 has none by
         design) — not a bug in any of them, just not a copyable
         template for what MIRROR itself needed.
         Verified with py_compile, an actual runtime start throughout
         (core pattern functions tested individually with hand-built
         synthetic candles; the full mirror_detect_signals() pipeline
         tested end-to-end on a realistic support-break-then-return-then-
         inside-bar sequence, producing a correctly-priced SHORT signal;
         mirror_track_outcome()/mirror_summarize_backtest() verified
         against the same signal resolving to a WIN; a live settings
         round-trip via get_settings()/apply_settings() confirmed all 7
         mirror_*/autotrade_mirror*/telegram_alerts_mirror fields read
         and write correctly), pyflakes (clean throughout, including
         mid-build — used specifically to catch the constant-ordering
         bug and a duplicate mirror_rr mapping entry before they could
         ship), node --check on the correctly-last <script> block, the
         Flask route/def integrity check (60 routes — up from 56, the
         4 new MIRROR endpoints, nothing else touched), and an AST walk
         for duplicate top-level defs (none introduced — 13 new mirror_*
         functions, each present exactly once).

v0.99.92 - Direct user follow-up: "покажи как графически это выглядит...
         придумай лучший фильтр для этого типа торговли, потом по
         статистике обязательно показывать до после как в msnr. В живых
         сигналах использовать только бэктестовые монеты с винрейтом
         более 35%." Showed a diagram of the level-flip mechanism
         (support forms -> breaks -> price returns -> inside bar
         confirms -> role flips to resistance -> short entry) before
         touching any code.
         New filter: mirror_symbol_sl_skip_min()/mirror_sl_bucket_
         stats() — SL-width filter, same shape as MSNR's own skip_sl_
         pct_min, chosen because MIRROR's own stop is entirely pattern-
         derived (not a fixed %/ATR) — a wide, sloppy-pattern stop is
         exactly the kind of "the pattern only loosely matched" case
         worth filtering. Built WITH the granularity cascade (MIRROR_
         SL_PCT_BUCKET_SCHEMES, 5->3->2 buckets) from day one this
         time, applying the MSNR v0.99.89 lesson proactively rather
         than discovering the same gap again later. One real test-
         design mistake caught and fixed before shipping: an initial
         synthetic test put the "bad" trades at NARROW SL widths, but
         this filter is deliberately one-sided (skip ABOVE a floor,
         matching "wide stop = bad") — the test's own direction was
         inverted from what the filter actually checks, producing a
         nonsensical skip_sl_pct_min=0 (skip everything) that looked
         like a bug until the test itself was corrected to put failing
         performance at WIDE SL widths instead, matching the real
         hypothesis; re-ran and confirmed correct (skip=4, catching two
         under-threshold adjacent fine buckets merged via cascade).
         Before/after diagnostics: new _mirror_checkpoint() — since
         every MIRROR signal shares one fixed RR (unlike MSNR's
         variable per-trade RR), "income" is expressed as R-expectancy
         (expected R per trade at that checkpoint's own win rate)
         rather than a compounded %, an honest proxy without inventing
         an unrelated leverage/compounding model MIRROR doesn't use.
         mirror_backtest_symbol() now returns (filtered_results, meta)
         with a 2-stage checkpoint chain (raw -> sl_filter); wired into
         api_mirror_status()'s per-symbol response and rendered as a
         "n → n · WR X%→Y% · expR" column in the backtest table.
         Live-universe winrate gate: mirror_backtest_loop() now derives
         mirror_live_universe (symbols whose POST-filter winrate clears
         MIRROR_LIVE_MIN_WINRATE=35%) each cycle; mirror_live_loop()
         scans only that list instead of the raw universe (falls back
         to the raw universe only before the first backtest cycle
         completes, same "don't sit idle" reasoning MSNR's own
         fallback uses). mirror_scan_symbol_live() also now checks the
         firing signal's own SL width against that symbol's stored
         skip_sl_pct_min before firing — same "trust this symbol's own
         bucket evidence" live-firing check MSNR's own filters use.
         New STATE keys (mirror_symbol_overrides, mirror_live_universe)
         added immediately alongside their own logic and wired into
         save_state()/load_state()'s snapshot/restore and api_reset_
         mirror(), not as a later follow-up fix.
         Verified with py_compile, an actual runtime start (mirror_
         symbol_sl_skip_min() tested against both a correctly- and an
         incorrectly-directioned synthetic dataset, confirming the
         cascade catches an under-threshold pair of adjacent bad
         buckets; a full backtest-shaped pipeline test — detect ->
         track_outcome -> checkpoint — run end to end on a realistic
         support-break-return-inside-bar sequence; a live test_client()
         round-trip against /api/mirror/status confirming live_min_
         winrate/live_universe/top all serialize correctly), pyflakes
         (clean throughout), node --check on the correctly-last
         <script> block, the Flask route/def integrity check (still 60
         routes — no new endpoints, existing ones extended), and an
         AST walk for duplicate top-level defs (none introduced — 3 new
         mirror_*/_mirror_* functions, each present exactly once).

v0.99.93 - Direct user follow-up: "почему я вижу сигналы раньше чем
         бэктест... Бэктест быстро проходит, так что лучше ждать, просто
         в сигналах живых вижу сигнал не удовлетворяющие условию 35%
         винрейта." Confirmed the cause: v0.99.92's own mirror_live_
         loop() fell back to scanning the RAW (unfiltered) universe
         whenever mirror_live_universe was still empty — i.e. before the
         first backtest cycle ever completed — so early signals weren't
         gated by the new 35% winrate threshold at all. Flagged this
         directly against MSNR's own history before changing anything:
         msnr_compute_live_universe() (v0.99.75-78) had gone through the
         EXACT same arc — a winrate-only promotion path that let a
         symbol reach live-scan status without clearing the real gate,
         retired after a live report of that identical symptom. Given
         the backtest cycle here is fast (per the user's own report),
         removed the fallback outright rather than reintroducing a
         version of the problem MSNR's own history already closed:
         mirror_live_loop() now scans nothing for NEW signals until
         mirror_live_universe has been populated at least once by a
         completed backtest cycle. update_mirror_signal_outcomes()
         still runs unconditionally on every loop iteration regardless
         — already-open trades keep getting their MFE/MAE/outcome
         tracked even while new-signal scanning is paused, so nothing
         about existing positions is affected. Also updated the panel's
         own "бэктест ещё не завершился" message to say explicitly that
         live scanning is paused for this reason, not just silent.
         Verified with py_compile, an actual runtime start (inspected
         mirror_live_loop()'s own source to confirm mirror_build_
         universe() is no longer called from it at all, and that
         update_mirror_signal_outcomes() still runs unconditionally),
         pyflakes (clean), node --check on the correctly-last <script>
         block, the Flask route/def integrity check (still 60 routes —
         no endpoints touched), and an AST walk for duplicate top-level
         defs (none introduced).

v0.99.94 - CRITICAL FIX, direct user report: "монета делает 3000% по
         ней, проходит следующий бэктест, монета даёт уже 10 процентов,
         улетает из топа, это точно надо править." This wasn't just
         that ONE symbol's own score was noisy — msnr_compute_rank_
         bounds() takes a plain min/max of compound_return_pct across
         the WHOLE pool as the shared normalization ceiling for every
         symbol's income_norm term, so a single symbol's rare
         compounding outlier (one lucky extreme-RR trade sequence,
         already a known documented instability — "MSNR live ranking
         still volatile due to grid-search-combo sensitivity to rare
         extreme-RR trades") silently set the ceiling EVERY other
         symbol's income got measured against that cycle — compressing
         everyone else's normalized income toward 0 while the outlier
         was present, then springing back once it faded. A confirmed
         mid-pool symbol whose own income never changed at all could
         swing from score 0.15 to 0.53 across two cycles purely because
         of a DIFFERENT symbol's noise, reproduced directly with a
         synthetic 21-symbol pool before touching the fix.
         Fixed by winsorizing the income ceiling at the pool's own 90th
         percentile (new MSNR_RANK_INCOME_WINSORIZE_PCT, using the
         existing _percentile() helper MFE/MAE stats already use)
         rather than the raw max — nothing below that percentile is
         affected at all, and msnr_symbol_rank_score()'s own _norm()
         already clamps anything above the (now-capped) ceiling to
         income_norm=1.0, so several genuinely strong symbols simply
         tie at "very good" instead of one outlier distorting the whole
         pool. Chosen as percentile-based (self-adjusting to whatever
         the pool's overall performance level is that cycle) over a
         fixed constant that would eventually need its own re-tuning.
         Verified with py_compile, an actual runtime start — reproduced
         the exact reported instability on a synthetic pool (a fixed
         mid-pool symbol's score before the fix: 0.150 with the outlier
         present -> 0.526 once it dropped to 10%, a 0.38 swing from
         another symbol's noise alone; after the fix: 0.518 -> 0.543,
         an 8x smaller swing), plus edge cases (small 2-symbol pool,
         every value identical, empty pool — all degrade sensibly, no
         crashes or nonsensical bounds), and a full msnr_rank_by_
         winrate_sample() integration check confirming a maxed-income
         outlier with only mediocre winrate/sample no longer auto-wins
         top rank purely off an absurd income figure — pyflakes
         (clean), the Flask route/def integrity check (still 60 routes
         — no endpoints touched, this is a pure ranking-math fix).

v0.99.95 - Direct user request continued: "Продолжи нашу работу по
         удалению индикаторов, в первую очередь убери вкладки и
         настройки." 3rd of 6 modules — EMA — removal begun, frontend
         phase only (tab + settings), per explicit instruction to do
         those first. Backend logic (scan_symbol_ema, the scan_loop()
         if EMA_ENABLED: integration, risk_autotune wiring, all EMA_*
         constants except compute_ema() itself, get/apply_settings,
         SETTINGS_KEYS, STATE keys, API routes) is UNTOUCHED and still
         fully functional in this version — EMA keeps running in the
         background exactly as before, just with no UI to see or
         control it until the backend removal follows in a later
         version. A safe, valid, non-broken intermediate checkpoint,
         not a partial/broken state.
         Checked compute_ema() itself for shared usage BEFORE removing
         anything, per the lesson from Divergence's own removal (compute_
         rsi() turned out to be FT5 infrastructure) — confirmed compute_
         ema() is used by THREE things: EMA's own module (being
         removed), compute_macd() (FT5's own indicator stack — staying),
         and xau_lg_detect_signals() (XAU LG — also on the removal list,
         but not this pass). compute_ema() itself is therefore permanent
         shared infrastructure and was never touched.
         Removed: the tab, the signals table + stats panel, the reset
         button + its wireResetButton() call + CSS selector, both
         activeTab==='ema' panel-visibility/refresh call sites, both
         modeLabels dict entries, the settings-modal "EMA" group (scan
         toggle + invert), 4 rows in the autotrade/leverage settings
         group (leverage, min RR, ADX filter, min EMA7/14 gap), the
         Telegram-alerts checkbox, the risk-autotune log's own EMA
         param-label entries, and all 11 corresponding entries in the
         JS settings-mapping object (ema_enabled/ema_invert_signals/
         ema_adx_filter_enabled/autotrade_ema/ema_min_rr/ema_adx_min/
         ema_min_gap_pct/autotrade_leverage_ema, found and removed one
         at a time as each subsequent one shifted into view).
         Verified with py_compile after every single edit (not batched
         — this session's own established discipline for large multi-
         step removals), pyflakes (clean — confirms no orphaned frontend
         JS references were left dangling, though pyflakes itself only
         checks the Python half; a manual grep for any remaining "setEma"/
         '"ema_' hits confirmed every survivor is backend Python code,
         zero live frontend references left), node --check on the
         correctly-last <script> block, and the Flask route/def
         integrity check (still 60 routes — no routes touched in this
         frontend-only pass).

v0.99.96 - Direct user request continued: "Продолжи." EMA removal (3rd
         of 6) finished — backend phase, completing v0.99.95's frontend-
         only checkpoint. Surgically removed the 3 if EMA_ENABLED:
         blocks from the SHARED scan_loop() (same discipline as
         Divergence's own removal — Volume/Scalp/Session untouched).
         Deleted has_open_ema_signal/scan_symbol_ema/close_ema_signal/
         update_ema_outcomes/compute_ema_stats, the risk_autotune_pass()
         EMA block, all 3 API routes (status/signals/chart) plus api_
         reset_ema, all 4 setters, _ema_cooldowns/_lock, and every EMA_*
         constant EXCEPT compute_ema() itself — confirmed at the start
         of v0.99.95 to be genuinely shared infra (FT5's own compute_
         macd() and XAU LG's own xau_lg_detect_signals() both still call
         it) and left fully untouched throughout both passes.
         Applied every hard-won lesson from this session's earlier
         module removals proactively: fixed has_open_signal_any_module()
         and _relink_sim_trade()'s own module_lists dict (the same
         eager-dict-literal-KeyError class of bug found for VGI and
         Divergence) BEFORE anything else, verified live via direct
         calls with mode="ema" — confirmed clean immediately, not
         discovered as a follow-up fix like the earlier two modules.
         Two things pyflakes caught that a plain py_compile pass alone
         would have missed entirely: (1) a stray f-string in load_
         state()'s own startup print() still referencing the just-
         deleted `ema_signals` local; (2) three whole EMA-only functions
         living OUTSIDE the main EMA constants/logic block entirely —
         _ema_signal_diagnostics(), detect_ema_signal(), and compute_
         ema_tp_sl() — each in a different, unrelated part of the file
         (near session/scalp code), missed in the first sweep and only
         surfaced once their own constants were deleted and pyflakes
         flagged the resulting undefined names.
         The EMA_* constant block itself required SURGICAL (not whole-
         range) deletion for the same reason the Divergence pass needed
         it for SNAPSHOT_MODULE_KEYS-style dicts: SESSION_INVERT_
         SIGNALS/SESSION_SL_MULT/SESSION_REVERSE_RR (a different
         module, staying) were physically interleaved inside the same
         constants section — split the deletion into two ranges around
         those three lines rather than one block delete, then verified
         directly that all three Session constants survived untouched.
         Verified with py_compile after every single edit, an actual
         runtime start (direct calls confirming compute_ema()/compute_
         macd() still produce correct output, and _relink_sim_trade()
         raises no KeyError for mode="ema"), pyflakes (clean — this is
         what actually caught the two gaps above; a bare py_compile
         pass would have shipped both), node --check on the correctly-
         last <script> block, the Flask route/def integrity check (56
         routes — down from 60, exactly the 4 EMA endpoints removed),
         an AST walk confirming zero ema_* functions remain at module
         level besides the intentionally-kept compute_ema() (no
         duplicates introduced), and a final grep confirming zero live
         EMA_* constant references remain anywhere in the file (only
         historical changelog text).

v0.99.97 - CRITICAL FIX, live crash reports with screenshots: repeated
         "msnr_backtest MRNA_USDT: not enough values to unpack (expected
         3, got 2)" — same for this symbol across multiple backtest
         cycles, not a one-off. Root cause: msnr_optimize_symbol()'s own
         early-exit path (fires when a symbol's fetched candle history
         is too thin to even attempt the 27-combo grid search — e.g. a
         newly-listed contract without much history yet) had drifted
         out of sync with the function's own documented contract
         ("Returns (override_dict, trades_list, raw_trades_list)" — a
         3-tuple) and was returning only 2 values: `{"error": "not
         enough history"}, []`. The sole caller, _msnr_backtest_one_
         symbol(), always unpacks assuming 3 (`override, results, raw_
         results = msnr_optimize_symbol(symbol)`) — any symbol landing
         on this path crashed that unpacking on EVERY single backtest
         cycle it was included in, not intermittently. Fixed to match
         the documented contract: `{"error": "not enough history"}, [],
         []` — both trade lists empty, since there's genuinely no
         backtest to report for a symbol that never had enough history.
         Also investigated the screenshots' OTHER recurring error
         ("NameResolutionError... Failed to resolve 'api.gateio.ws'")
         — NOT a new bug: this exact error class was already found,
         explained, and mitigated back in v0.69.0 (a transient mobile-
         network DNS blip, with get_candles() already retrying on
         ConnectionError before giving up) — a sustained cluster of
         these simply means the retry window was shorter than the
         actual outage, which is correct/expected behavior, not
         something to chase further unless it becomes a SUSTAINED
         pattern rather than an occasional cluster.
         Verified with py_compile, an actual runtime start (mocked
         get_candles_range() to force the exact insufficient-history
         path, confirmed msnr_optimize_symbol() now unpacks cleanly
         into 3 values instead of raising ValueError, then confirmed
         the FULL call chain through _msnr_backtest_one_symbol() — the
         actual crashing caller — also completes cleanly end to end),
         pyflakes (clean), node --check on the correctly-last <script>
         block, and the Flask route/def integrity check (still 56
         routes — a pure return-value fix, no routes touched).
         Also synced this session's own local copy from GitHub before
         starting (per direct user instruction) — another session had
         pushed a real, unrelated MSNR ranking change (pure sort by
         compound_return_pct with a hard winrate>=45% gate, replacing
         the geometric-mean composite) without bumping APP_VERSION
         past 0.99.96; verified py_compile/pyflakes/routes clean on
         the downloaded copy before adopting it as this session's base.

v0.99.98 - MIRROR statistical-hygiene batch, source: code review by
         another AI (external prompt provided by the user, "код-ревью
         другого ИИ, батч 1 из 2" — 6 cheap/high-confidence fixes,
         explicitly scoped to defer a larger batch 2 — volume filter,
         ATR tolerance, SL buffer, BE move — until real numbers from
         this batch are visible).
         (1) Min-sample gate on live eligibility: mirror_backtest_loop()
         previously gated live-universe entry on winrate alone — a 2/2
         or 3/3 symbol read as "100%" and qualified identically to a
         genuinely-tested 40+ trade symbol. Added closed_n >=
         MIRROR_SYMBOL_SKIP_MIN_SAMPLE alongside the existing winrate
         check (reusing the same constant every other MIRROR filter's
         significance bar already uses).
         (2) TIMEOUT parity — investigated, NOT implemented as proposed.
         The review's premise (mirror_track_outcome()'s own backtest-
         side max_wait_bars=200 has no live-side counterpart, so a live
         signal stays OPEN forever) is factually correct, but its
         suggested fix (add a timeout, modeled on XAU LG) contradicts an
         established, DELIBERATE, repeatedly-applied convention: XAU
         LG's own live tracker (and Session's, Divergence's, and
         others') had TIMEOUT explicitly REMOVED per direct user
         request, specifically so "a signal waits as long as it takes,
         never expiring into an ambiguous TIMEOUT result." Flagged this
         conflict directly rather than silently picking a side; user
         said to continue, so kept MIRROR consistent with every other
         module (no timeout added) — documented the reasoning inline in
         update_mirror_signal_outcomes() so a future pass doesn't
         rediscover the same tension.
         (3) MIRROR_BACKTEST_DAYS 40 -> 90 (env-overridable, matching
         every other MIRROR_* constant's own pattern) — 40 days produced
         too few trades per symbol (5-20) to trust winrate even with
         fix #1's new sample floor.
         (4) bars_since_break tracking: mirror_detect_signals() now
         records how many bars passed between a level's own break and
         the confirming touch, threaded through into mirror_backtest_
         symbol()'s raw_results and mirror_scan_symbol_live()'s live
         record. Pure data collection, no filter yet — deferred to
         batch 2 once the real distribution is visible.
         (5) by_direction breakdown: mirror_summarize_backtest() now
         reports LONG/SHORT separately (n/wins/losses/win_rate each),
         same shape as compute_mirror_signal_stats()'s existing
         by_pattern. Informational only, no gate.
         (6) Auto-gate by pattern: new mirror_symbol_pattern_skip() —
         same significance bar and breakeven test as mirror_symbol_
         sl_skip_min(), but deliberately WITHOUT a granularity cascade:
         unlike SL width (a continuous scale with natural coarser
         bucketings to fall back to), pattern is a fixed 4-category
         field with nothing to merge into — each pattern either clears
         MIRROR_SYMBOL_SKIP_MIN_SAMPLE on its own or doesn't. Wired into
         mirror_backtest_symbol() as a third filter stage (raw ->
         sl_filter -> pattern_filter, derived off whatever survived the
         SL filter, not raw again — same evidence-ordering discipline
         as every other filter chain in this file), stored as
         meta["skip_pattern"], and checked again in mirror_scan_
         symbol_live() before firing (would need STATE["mirror_symbol_
         overrides"] wiring matching skip_sl_pct_min's own live check —
         confirmed present).
         API/UI: api_mirror_status()'s existing dict-spread already
         surfaces by_direction (from summary) and skip_pattern (from
         overrides) with zero route changes needed — verified via a
         live test_client() round-trip. refreshMirror() updated to
         render both, plus the before/after checkpoint summary now
         correctly points at the FINAL chain stage (pattern_filter, not
         the now-intermediate sl_filter) so "после" reflects both
         filters, not just the first one.
         Verified with py_compile after every edit, an actual runtime
         start (mirror_symbol_pattern_skip() tested against a synthetic
         set confirming a genuinely-failing, sufficiently-sampled
         pattern gets skipped while an equally-bad but under-sampled one
         doesn't; mirror_summarize_backtest()'s by_direction verified
         against a mixed LONG/SHORT/TIMEOUT set; a live test_client()
         call against /api/mirror/status confirming backtest_days=90 and
         the full config surface correctly), pyflakes (clean throughout),
         node --check on the correctly-last <script> block, and the
         Flask route/def integrity check (still 56 routes — no new
         endpoints, existing ones extended).

v0.99.99 - Direct user follow-up: "продолжи, тайм аут тоже добавь но
         надо знать как закрылась сделка по таймауту в плюс или минус."
         Reverses v0.99.98's own declined-with-explanation decision on
         this exact point — that version investigated the same request
         (from an external code review) and left MIRROR's live tracker
         without a TIMEOUT branch specifically because every other
         module's own live tracker had TIMEOUT deliberately removed;
         this direct follow-up is the user's explicit, informed choice
         to diverge MIRROR from that convention on purpose, with a
         concrete added requirement (know the sign of the outcome) the
         original review's own proposal hadn't specified.
         New shared MIRROR_MAX_WAIT_BARS=200 constant (env-overridable)
         — mirror_track_outcome()'s own backtest-side cutoff (previously
         a hardcoded default) and update_mirror_signal_outcomes()'s new
         live-side one now both read from the same source, genuine
         parity in HOW LONG a signal gets before timing out, not just
         that both sides eventually have SOME cutoff.
         update_mirror_signal_outcomes() now closes a signal as TIMEOUT
         once MIRROR_MAX_WAIT_BARS bars have passed since entry with no
         TP/SL touch — using the bar's own REAL close as exit_price
         (not None, unlike the original review's own suggestion), plus
         a new timeout_pnl_r field (the signed R-multiple at that exact
         moment) so the frontend doesn't need to re-derive direction
         logic from a raw price comparison. compute_mirror_signal_
         stats()'s own winrate calculation already only counted WIN/LOSS
         (built that way from the start, even though TIMEOUT never
         actually fired before this version) — confirmed TIMEOUT closes
         still can't silently skew winrate now that they're real.
         Frontend: TIMEOUT rows in the live-signals table now color/sign
         the same way WIN/LOSS already do (win-green if timeout_pnl_r
         >= 0, loss-red if negative) with the R value and exit price
         shown inline, instead of a flat neutral "TIMEOUT" label
         carrying no P&L information.
         Verified with py_compile after every edit, an actual runtime
         start (constructed two synthetic open signals — one LONG
         drifting slowly favorable, one SHORT drifting slowly adverse,
         neither ever touching its own TP/SL — confirmed both correctly
         time out at exactly bar 200 (not earlier, not the full 250-bar
         window), with exit_price a real drifted price and timeout_pnl_r
         signed correctly in each direction: positive for the LONG that
         drifted up, negative for the SHORT that drifted against it),
         pyflakes (clean), node --check on the correctly-last <script>
         block, and the Flask route/def integrity check (still 56
         routes — no new endpoints).

v0.99.100 - CRITICAL FIX, live report: "После последних правок сломались
         настройки, не применяются галочки и значения. Не приходят
         уведомления msnr... Продолжи, а еще не открываются графики по
         нажатию на сигнал." Backend checked first and found clean (a
         live test_client() round-trip against /api/settings correctly
         saved/returned msnr_max_rr and telegram_alerts_msnr; send_
         telegram()'s own "msnr" category check intact; no duplicate
         functions or object keys anywhere; py_compile/pyflakes/node
         --check all clean) — ruled out a backend cause and, given the
         user confirmed the displayed version already matched, also
         ruled out the stale-deployment theory that explained an
         earlier, similar-sounding confusion this session.
         Actually reproduced the failure by installing jsdom and
         running the REAL page (not just static analysis) — node --check
         only validates syntax, never catches a runtime TypeError.
         Found it: setInputs (the settings-checkbox DOM-mapping object)
         still had a stray telegram_alerts_ema entry pointing at
         document.getElementById('setTelegramEma') — an element removed
         from the HTML back during EMA's own settings-group removal, one
         single mapping entry missed in that pass. for (const key in
         setInputs) { setInputs[key].onchange = ... } — the very loop
         that wires up EVERY settings checkbox on page load — threw
         `TypeError: Cannot set properties of null (setting 'onchange')`
         the moment it reached this key, with no try/catch, killing ALL
         further top-level script execution for that tick: every
         setInputs key that would have been wired AFTER this one in
         object-iteration order never got its onchange handler at all,
         which is exactly "checkboxes/values don't apply" — and since
         MSNR's own telegram_alerts_msnr checkbox is a later key,
         toggling it visually never actually reached the backend either,
         explaining the missing notifications as a symptom of the SAME
         root cause, not a separate bug. ("Charts don't open" wasn't
         independently reproduced under jsdom, but sits downstream of
         the same halted-script-execution mechanism and is covered by
         the same fix.) Removed the one stray entry; reran under jsdom
         — the TypeError is gone.
         While chasing this down, two false trails worth recording so a
         future pass doesn't repeat them: (1) a naive `<div`/`</div>`
         line-count "imbalance" turned out to be regex matches INSIDE
         a CSS comment quoting old HTML as prose, and inside the
         changelog docstring's own past-tense description of an HTML
         fix — same class of false-positive as matching text in a
         Python comment, just one layer removed (a comment inside the
         real <style> block this time); (2) `src.index('</script>')`
         (search from the start) found a docstring's own mention of
         that literal string rather than the real closing tag —
         needed `rindex()` (search from the end), matching the
         discipline already used for the opening <script> tag.
         Also found, while jsdom's error trace pointed at the settings-
         wiring loop specifically: refreshEma()/openEmaChart()/
         drawEmaChart() (EMA's own frontend removal, v0.99.95) and
         openDivergenceChart()/drawDivergenceChart() (Divergence's own
         removal, v0.99.85 — much earlier this session) had each left
         their own whole rendering functions behind uncalled — genuine
         dead code, confirmed via reference-counting each function name
         (zero external callers beyond their own declaration and each
         other) before removing anything. Cleaned these up along with
         their own now-dead divModal/emaModal HTML shells and JS
         variables (currentDivRow/currentDivData/currentEmaRow/
         currentEmaData) and the window resize handler's own by-name
         references to drawDivergenceChart()/drawEmaChart() — deleting
         those two draw functions WITHOUT first removing the resize
         handler's own calls to them would have reintroduced the exact
         same class of bug (a function deleted while something else
         still references it by name) that this whole version exists to
         fix. windowParamsForInterval() (EMA-only, confirmed via
         reference count) removed too; windowAroundTime()/
         computeYRangeSimple() confirmed genuinely shared (live callers
         outside the removed functions) and left untouched.
         Verified with py_compile after every edit, pyflakes (clean),
         a full jsdom-based real page execution (not just static
         analysis) confirming zero runtime errors on load, a systematic
         getElementById audit (130 calls across the whole script, zero
         referencing a non-existent id — down from exactly 1 before this
         fix), node --check on the correctly-last <script> block, and
         the Flask route/def integrity check (still 56 routes — a pure
         frontend fix, no routes touched).

v0.99.101 - Continued module removal (4th/5th/6th of 6): Session,
         Session NY, XAU LG — frontend + settings phase, per direct
         user request ("Пока удали из настроек и вкладки, а прогон
         принудительно останови, хоть через слои кода"). Backend
         functions/routes/STATE deliberately left in place for a later
         pass (matching the established EMA precedent — settings/tabs
         first, backend cleanup separately).
         "Force-stop, even through code layers": SESSION_ENABLED/
         SESSION_NY_ENABLED/XAU_LG_ENABLED hardcoded to False directly
         at their own definition (no longer env-var-overridable) — all
         6 of their own background loops (session_loop, session_live_
         loop, session_ny_loop, session_ny_live_loop, xau_lg_backtest_
         loop, xau_lg_live_loop) already gate on these flags at the top
         of every iteration, confirmed by direct inspection. Caught a
         real gap before it shipped: hardcoding the constant alone
         wasn't enough — apply_settings() could still flip it back to
         True via a plain API POST (verified live: posting session_
         enabled=true actually re-enabled it). Removed session/session_
         ny/xau_lg entirely from apply_settings() (all if-blocks,
         global declarations), SETTINGS_KEYS, and get_settings() — the
         only way to re-enable any of the three now is editing the
         source itself, not any settings path.
         While touching this exact area, found and removed two more
         live-but-orphaned leftovers from EMA's own earlier removal
         that had slipped through every previous pass: AUTOTRADE_
         LEVERAGE_EMA (constant, never referenced by any live code) and
         two get_settings() entries (telegram_alerts_ema, autotrade_ema)
         pointing at still-defined-but-dead TELEGRAM_ALERTS_EMA/
         AUTOTRADE_ENABLED_EMA constants.
         Frontend: removed all 3 tabs, panels, reset buttons + their
         wireResetButton() calls + CSS selector, 3 settings groups in
         the modal, autotrade/leverage rows, Telegram-alert checkboxes,
         panel-visibility switching + refresh calls (both call sites),
         then — applying the exact lesson from v0.99.100's own critical
         fix — the now-dead refreshSession()/refreshSessionNy()/
         refreshXauLg() and their own helper chain (fmtSessionRow/
         wireSessionRowClicks/openSessionDetail and Session NY's
         equivalents), the openSessionChart/openSessionNyChart/
         drawSessionChart trio (openXauLgChart separately — it wraps
         the shared openVgiChart, confirmed via inspection, so removing
         it needed no resize-handler change), and the resize handler's
         own by-name reference to drawSessionChart/sessionModal/
         currentSessionData (would have reintroduced the identical
         class of bug fixed in v0.99.100 if skipped). Finished with the
         SAME getElementById-audit discipline that caught that bug
         originally: found the count at 15 dangling refs immediately
         after the dead-function removal (all inside setInputs/
         setValueInputs — the exact object that broke last time),
         worked through each remaining entry across 3 separate edits,
         and reran the audit after each one until it hit zero.
         Verified with py_compile after every single edit, pyflakes
         (clean), a live apply_settings() POST test proving session_
         enabled/etc. can no longer be re-enabled via API, a full
         getElementById audit (101 calls, zero dangling — down from
         113 before this pass began), a real jsdom page execution
         (zero runtime errors), node --check, the Flask route/def
         integrity check (56 routes — backend routes deliberately
         untouched this pass), and an AST walk for duplicate top-level
         defs (none introduced).

v0.99.102 - Manual leverage/position-size selection removed entirely,
         per a multi-turn direct user request clarified via several
         rounds of Q&A before touching any code (this is real-money
         position sizing — worth getting exactly right, not guessing):
         "выбор плеча убери для всех индикаторов, это всегда будет
         расчет по принципу стоп 2% от баланса" -> "надо чтобы размер
         позиции только можно было выбрать" -> "размер позиции может
         тоже автоматом определять, брать минимально возможный процент
         депозита но чтобы плечо позволяло ставить стоп до ликвидации,
         но было большим достаточно для стопа в 2%" -> "available +
         position_margin (без плавающего PnL, только подтверждённый
         капитал)" as the risk base. Every module now sizes identically
         and fully automatically:
         (1) get_futures_total_equity() — NEW, fetches available +
         position_margin (confirmed capital, deliberately excluding
         unrealised_pnl per the user's own explicit choice — a new
         trade's own risk shouldn't be inflated/deflated by floating,
         not-yet-realized gains/losses on OTHER open positions). This
         also fixes the original bug report: get_futures_wallet_
         balance()'s own "available" alone shrinks the moment another
         position locks margin away, corrupting risk sizing — "Если
         сделка уже открыта какая-то, то баланс становится меньше...
         а надо смотреть все равно на всю сумму денег на счету."
         (2) compute_max_safe_leverage() — NEW, finds the LARGEST
         leverage (up to the contract's own exchange leverage_max)
         whose liquidation buffer still clears this signal's own SL
         distance, by reusing compute_scalp_liquidation_move_pct()'s
         own formula via a plain integer sweep rather than inverting
         its min()/direction-dependent branches analytically (a likely
         source of a sign or edge-case bug on math this consequential).
         (3) compute_risk_based_position() — NEW, given that max safe
         leverage, derives the MINIMUM margin needed to still risk
         exactly AUTOTRADE_RISK_PCT_OF_BALANCE=2% of confirmed capital.
         Margin and leverage are inversely related for a fixed risk
         target and SL distance — using the highest SAFE leverage
         minimizes capital tied up per trade while keeping dollar risk
         exactly fixed, rather than a flat per-module leverage constant
         with no relationship to any given signal's actual SL width.
         execute_autotrade() itself: leverage/size_mode/size_value
         parameters removed from its signature entirely — computed
         internally now for every caller. compute_position_size() split
         into compute_margin_usd() + compute_contracts_from_margin()
         (the latter reused by the new risk-based path); the old
         function itself kept but no longer called by execute_
         autotrade() (a smaller future cleanup, not blocking this pass).
         All 7 real call sites (bounce/breakout, scalp, session, session
         ny, xau_lg, msnr, mirror) updated to the new 6-arg signature —
         confirmed via an AST walk that every one now passes exactly
         6 positional args. sim_execute_trade() (the separate paper-
         trading simulator) deliberately left untouched — it still
         takes its own leverage/size_mode/size_value, so the underlying
         AUTOTRADE_LEVERAGE_*/AUTOTRADE_SIZE_MODE/VALUE/SCALP_SIZE_MODE/
         VALUE constants stay defined (still feed the simulator) — they
         were removed from SETTINGS_KEYS/apply_settings()/get_settings()
         and their own UI rows only, not deleted as constants.
         Found and left alone (not part of this pass, will need its own
         separate pass): AUTOTRADE_ENABLED_MSNR has apparently never had
         a settings-modal checkbox at all — MSNR's own real autotrade
         is controlled per-symbol on its own tab instead, confirmed via
         a direct grep (no "setAutotradeMsnr" element exists anywhere) —
         a pre-existing gap, not something this pass introduced.
         Verified with py_compile after every edit (constants, the new
         functions, execute_autotrade()'s own restructuring, every call
         site, the settings pipeline, the HTML/JS removal), an actual
         runtime start throughout — compute_risk_based_position() tested
         directly confirming the SL-hit loss comes out to EXACTLY 2% of
         total_equity regardless of SL width (0.5% SL -> 77x/$519 margin,
         2.5% SL -> 23x/$348 margin, both losing exactly $200 on a
         $10,000 balance), LONG and SHORT directions both correct, a
         genuinely-unsafe SL distance correctly skipped with a clear
         reason, a full execute_autotrade() dry-run producing a
         consistent end-to-end record, and a live test_client() /api/
         settings round-trip confirming a direct POST of autotrade_
         leverage_bounce/autotrade_size_mode/scalp_size_value no longer
         changes anything and none of those keys appear in the response
         anymore — pyflakes (clean throughout), a full getElementById
         audit (93 calls, zero dangling — down from 101), a real jsdom
         page execution (zero runtime errors), node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (56 routes — a pure sizing-logic and settings-UI change,
         no routes touched), and an AST walk for duplicate top-level
         defs (none introduced).

v0.99.103 - MIRROR chart now draws the underlying support/resistance
         level itself, per direct user request ("для зеркала сделай
         отрисовку уровней, как строится сам сигнал, где зеркало
         само"). api_mirror_chart() was already storing level_price/
         level_type on every signal record (needed for the module's own
         SL-width/pattern statistics) but had never actually included
         them in its own JSON response to the frontend — added both
         fields (plus pattern) to the response for both the live-signal
         and backtest-trade lookup branches.
         Frontend: drawVgiChart() (the SHARED chart-drawing function
         Scalp/XAU LG/MSNR/FT5/MIRROR all reuse) gained one new
         conditional call to its own existing drawLevelLine() helper —
         the exact same dashed-line-with-label primitive already used
         for ENTRY/SL/TP, so the new level line is visually consistent
         by construction rather than a separate one-off drawing
         routine, and harmlessly never draws for every other chart
         type (they simply never have a level_price field to trigger
         it). Labeled by level_type: "low" (a broken support price has
         returned to from below, now acting as resistance — a SHORT
         setup) vs "high" (broken resistance now acting as support — a
         LONG setup), matching the terminology already used on the
         Зеркало tab and in the earlier explanatory diagram. Also added
         the pattern name (own RU labels, matching the tab's existing
         ones) to the chart modal's own info line.
         Verified with py_compile, an actual runtime start (a live
         test_client() round-trip against /api/mirror/chart/<symbol>
         confirming level_price/level_type/pattern all come through
         correctly), pyflakes (clean), node --check on the correctly-
         last <script> block, a real jsdom page execution (zero runtime
         errors — confirms the new conditional level-line logic doesn't
         break rendering for chart types that never pass level_price),
         and the Flask route/def integrity check (56 routes — no new
         endpoints, existing one extended).

v0.99.104 - MSNR CRITICAL FIX, live report: "часто выбивает стоп и идёт
         куда надо цена" (stop frequently gets knocked out, then price
         moves the intended direction anyway — the textbook symptom of
         a stop sitting too close to normal price noise/re-testing).
         Investigated whether this traced to the recent leverage
         redesign (v0.99.102) first, since it landed right before this
         report — confirmed it doesn't: place_tp_sl_orders() places the
         SL at exactly the signal's own sl price (rounded to tick),
         completely independent of leverage/margin, which only affect
         position SIZE. Also flagged, but deliberately NOT reverted
         without being asked: another (non-this) session's own v0.99.95
         MSNR ranking change (pure sort by compound_return_pct with a
         winrate>=45% floor, replacing the earlier winrate/sample/доход
         composite) could plausibly be promoting noisier, less stable
         symbols into live trading — a live candidate worth revisiting,
         but a genuinely separate question from the SL-width issue this
         version actually fixes.
         Root cause found by comparing MSNR's own SL formula against
         XAU LG's already-working one in this same file: MSNR's sl =
         sweep_extreme * (1 ± MSNR_SL_BUFFER_PCT=0.15%) barely widens
         the stop past the sweep's own extreme AT ALL, regardless of
         how far that sweep actually moved — a fixed, tiny % nudge on
         top of the bare extreme price, not a real buffer. XAU_LG_SL_
         BUFFER_MULT instead multiplies the RAW entry-to-extreme
         distance (an existing, real, price-action-derived risk
         measure) — a stop that scales with how far the move already
         went, not a nudge that's nearly identical regardless of the
         setup's own scale.
         Fixed by adopting XAU LG's own formula shape for MSNR: new
         MSNR_SL_BUFFER_MULT=1.3 (env-overridable), sl = entry ±
         (raw_risk * 1.3) instead of extreme * (1 ± tiny_pct), in both
         the SHORT (A-shape) and LONG (V-shape) branches of msnr_
         detect_signals(). Verified directly: on a synthetic sweep
         (entry 99.8, sweep extreme 100.6), the buffer beyond the raw
         sweep extreme grew from $0.15 (old formula) to $0.24 (new,
         ~60% wider) — total risk grew from 0.953% to 1.042% of entry.
         Deliberately NOT wired into the global risk_autotune_pass()
         SL-multiplier nudge system XAU_LG/SESSION/EMA/DIV use for
         their own — caught and corrected an overclaim in this
         constant's own first-draft comment before shipping: MSNR's
         participation in that global system was already disabled back
         in v0.99.52 in favor of its own, different tuning philosophy
         (msnr_symbol_sl_skip_min() and friends — per-symbol
         statistical significance tests, not a single global average-
         MAE nudge) — reintroducing the older global mechanism just for
         this one constant would have been inconsistent with that
         already-established design, not a genuine improvement.
         MSNR_SL_BUFFER_PCT itself left fully defined (not deleted) —
         vestigial now, nothing in signal generation reads it anymore,
         same "leave the old constant in case of future reintroduction"
         treatment already applied to MSNR_MAX_RR.
         Also confirmed msnr_detect_signals()'s own **params call sites
         (msnr_backtest_symbol, the live-scan chart-relink helper, and
         both risk-autotune-adjacent grid-search call sites) never
         build a params dict containing the old "sl_buffer_pct" key —
         a direct grep confirmed zero matches — so the parameter rename
         (sl_buffer_pct -> sl_buffer_mult) can't silently break any of
         them with an unexpected-keyword TypeError.
         Verified with py_compile after every edit, an actual runtime
         start (inspect.signature() confirming the renamed parameter;
         the exact arithmetic comparison above run directly), pyflakes
         (clean), the Flask route/def integrity check (56 routes — a
         pure signal-generation formula change, no routes/UI touched),
         and an AST walk for duplicate top-level defs (none introduced).

v0.99.105 - MSNR autotrade master switch restored, live screenshot
         report: the general "Автоторговля" settings group lists
         Bounce/Breakout/Скальпинг/Зеркало each with their own on/off
         row — MSNR conspicuously absent, and the user (reasonably)
         couldn't find any equivalent for it anywhere. Investigated
         thoroughly before touching anything (the exact symptom the
         v0.99.32 "checkbox does nothing" bug already warns about in
         this same file's own comments): AUTOTRADE_ENABLED_MSNR was
         NEVER actually deleted — still fully wired through get_
         settings()/apply_settings()/SETTINGS_KEYS since v0.99.18 — but
         v0.99.18 ALSO removed the only place that ever CHECKED it
         (msnr_scan_symbol_live()'s own firing decision), replacing it
         entirely with 6 individually-toggleable per-symbol checkboxes
         on the MSNR tab itself. So the constant was genuinely settable
         and persisted, just silently inert — exactly a decorative
         checkbox would have been if I'd simply added the missing UI
         row without checking this first.
         Fixed properly rather than papering over it: added `AUTOTRADE_
         ENABLED_MSNR and` back into msnr_scan_symbol_live()'s own
         firing condition, alongside (not replacing) the existing per-
         symbol autotrade_symbols.get(symbol) check — a genuine MASTER
         switch layered on top of the per-symbol ones, matching what
         every other module's own single on/off already does: turning
         it off now pauses every symbol's own MSNR autotrade at once,
         without having to un-toggle each one individually. Added the
         matching "↳ MSNR ⚠️" settings-modal row (with an explanatory
         sub-line making the master/per-symbol relationship explicit,
         since it's genuinely different from every sibling row) and its
         own setInputs mapping entry — this key had a stale v0.99.18
         comment explaining why it was deliberately NOT mapped, now
         corrected since the underlying reason (nothing checked the
         constant) no longer holds.
         Verified with py_compile after every edit, an actual runtime
         start (a live test_client() /api/settings POST/GET round-trip
         confirming autotrade_msnr actually persists and reads back
         correctly, not just accepted silently), pyflakes (clean), a
         full getElementById audit (94 calls, zero dangling), a real
         jsdom page execution (zero runtime errors), node --check on
         the correctly-last <script> block, the Flask route/def
         integrity check (56 routes — no new endpoints, existing
         settings pipeline extended), and an AST walk for duplicate
         top-level defs (none introduced).

v0.99.106 - get_futures_total_equity() CRITICAL FIX, live report:
         "у меня открыта уже сделка почти на весь баланс, из 80
         долларов свободно 1.7, и получается весь баланс не увидел
         индикатор" — a new trade sized as if total equity were only
         the ~$1.7 still free, not the real ~$80 (available + the
         other position's own locked margin). The user's own diagnosis
         was exactly right, worked out from the numbers alone before
         any code was even looked at.
         Root cause: the account endpoint's own "position_margin"
         field — what v0.99.102's own formula relied on for "margin
         locked in open positions" — is marked DEPRECATED in Gate's
         own official API changelog (confirmed directly against their
         docs, not assumed: "position_margin marked as deprecated"
         alongside "total field... only applicable to classic futures
         accounts"). On an account using Gate's newer unified/
         portfolio-margin structure (which Gate has been migrating
         users toward), that field can silently read 0 or stale
         regardless of how much margin is genuinely locked in a real
         open position — exactly the reported symptom.
         Fixed by switching to a source that isn't deprecated: summing
         each individual open position's OWN "margin" field via the
         already-existing get_open_positions() (GET /futures/usdt/
         positions, already used elsewhere in this file, already
         correctly filters to non-zero-size positions) instead of the
         account-level aggregate. Same available+locked-margin shape
         as before (still deliberately excludes unrealised_pnl and
         order_margin — see this function's own v0.99.102 reasoning,
         unchanged), just sourced from a field that stays accurate
         regardless of which account structure Gate has the user on.
         Verified with py_compile, an actual runtime start — mocked
         gate_signed_request() to simulate exactly the reported
         scenario (available=$1.70, the deprecated account-level
         position_margin returning $0 as it apparently did live, one
         real open position with its own margin=$78.30) and confirmed
         get_futures_total_equity() now correctly returns $80.00, not
         $1.70; a second test with multiple simultaneous positions
         (one already-closed, size=0, correctly excluded) confirmed
         the summation itself is correct, not a single-position
         coincidence — pyflakes (clean), the Flask route/def integrity
         check (56 routes — a pure balance-calculation fix, no routes/
         UI touched), and an AST walk for duplicate top-level defs
         (none introduced).

v0.99.107 - Two live reports handled in the same pass.
         (1) CRITICAL FIX — duplicate positions on the same symbol,
         seen at least in Scalp, possibly Mirror too ("увидел
         одновременно несколько позиций активных по 1 монете с
         разными а бывает и одинаковыми тейками/стопами"). Root cause:
         a genuine TOCTOU race. execute_autotrade()'s own exchange-
         position check (v0.99.53) and has_open_signal_any_module()
         are both point-in-time checks, not atomic with the order
         placement that follows — two near-simultaneous signals for
         the SAME symbol (e.g. Scalp evaluating multiple intervals for
         one coin in the same scan pass) could both see "no open
         position yet" and both place real orders before either one's
         own order became visible to the other's check.
         Fixed with a new per-symbol lock (_get_symbol_trade_lock — a
         dict of threading.Lock() keyed by symbol, not one global lock,
         so different symbols still trade fully concurrently) wrapping
         execute_autotrade()'s entire critical section (from the
         exchange-position check through order placement) — the second
         near-simultaneous call for the same symbol now blocks until
         the first has fully committed, at which point its own exchange
         check correctly finds the now-real position and skips.
         Verified with a genuine multi-threaded test: two threads
         calling execute_autotrade() for the same symbol at once, with
         a mocked place_market_order() that appends to a shared fake-
         positions list after a deliberate delay (widening the race
         window that would expose the bug without the fix) — confirmed
         exactly one real order placed (not two), one thread got
         OPENED, the other correctly got SKIPPED. Separately confirmed
         locks for different symbols are different objects (no
         accidental global serialization dragging down unrelated
         trades).
         (2) MIRROR direction auto-gate, per direct user request (a
         live example given: LONG winrate 11% vs SHORT 45% on the same
         symbol — "если какая-то сторона подходит под авто торговлю то
         в ней ещё можно брать сторону, которая лучше по винрейту, а
         меньшую не торговать"). New mirror_symbol_direction_skip(),
         same shape as the existing mirror_symbol_pattern_skip() (same
         MIRROR_SYMBOL_SKIP_MIN_SAMPLE significance bar, same breakeven
         threshold, no cascade needed — only 2 categories). Wired into
         mirror_backtest_symbol() as a 4th filter stage (raw ->
         sl_filter -> pattern_filter -> direction_filter, derived off
         whatever survived the pattern filter) and into mirror_scan_
         symbol_live()'s own firing check (a live signal whose
         direction is in the symbol's own skip_direction set doesn't
         fire, even though the symbol overall qualified for live
         trading on the strength of its other side).
         Verified directly against the user's own numbers: 18 LONG
         trades at 11% winrate + 20 SHORT at 45% (RR=3, breakeven 25%)
         — mirror_symbol_direction_skip() correctly returns {"LONG"}
         only. Confirmed a thin sample doesn't false-trigger (5 LONG
         trades with a bad winrate stayed unskipped, below the sample
         floor). Full mirror_backtest_symbol() run with patterns evenly
         mixed across both directions (isolating the direction filter
         from the pattern filter) confirmed the 4-stage checkpoint
         chain correctly shows n going 38->20 and winrate climbing
         28.9%->45.0% once LONG gets filtered out.
         Verified with py_compile after every edit, pyflakes (clean),
         the Flask route/def integrity check (56 routes — pure backend
         logic changes, no routes/UI touched), and an AST walk for
         duplicate top-level defs (none introduced).

v0.99.108 - MSNR autotrade fully automated, per direct user request:
         "монеты попавшие в топ список и винрейт больше 50 помечаются
         галочкой авто торговли, если потом такая монета вылетела из
         топа то галочку автоматом снимать" -> then, once informed the
         checkbox had actually never been auto-set at all (only manual
         clicks ever changed it): "Ручное управление можно убрать."
         Two-part change.
         (1) msnr_backtest_loop() now auto-manages STATE["msnr_
         autotrade_symbols"] each cycle: auto-ON any symbol newly
         qualifying (in the eligible top-N AND win_rate > 50%), auto-
         OFF any symbol that stops qualifying (either condition) —
         symmetric with the entry condition rather than only reacting
         to ranking changes. New STATE["msnr_autotrade_top_set"] tracks
         the top-N pool from the PREVIOUS cycle so auto-off only ever
         touches symbols that were themselves part of the auto-managed
         pool (a real design concern before part 2 below made it moot
         — at the time, msnr_manual_toggle_allowed_symbols()'s own
         "вне топ-10, на свой страх и риск" feature let a person
         manually enable a non-top-10 symbol, and a naive "not in top-N
         -> turn off" rule would have silently clobbered that deliberate
         choice). Verified directly: symbol entering top with WR=60%
         auto-turns-on; a previously-auto-managed symbol falling out of
         top correctly auto-turns-off; a manually-enabled non-top-10
         symbol stays untouched across cycles.
         (2) Per the direct follow-up, manual toggling removed entirely
         — the checkbox is now a read-only indicator (✓/—, not
         clickable), the /api/msnr/autotrade_toggle route is gone, and
         both functions that existed solely to support it (_set_msnr_
         autotrade_symbol(), msnr_manual_toggle_allowed_symbols()) are
         deleted as genuinely dead code — this session's own established
         discipline of not leaving orphaned functions behind (learned
         the hard way, repeatedly, with EMA/Divergence leftovers earlier
         this session). Also fixed a real correctness gap this
         simplification exposed: msnr_scan_symbol_live()'s own live-
         firing gate and msnr_effective_live_universe() (the scanning-
         universe builder) both used to check against the BROADER
         manual-toggle-allowed set (any valid, non-stress_test_failed
         backtest) — now that the toggle is ONLY ever set by auto-
         management, checking the broader set left a genuine gap: a
         symbol that just fell out of top-N moments ago, before the
         NEXT backtest cycle's own auto-off catches up, would still
         pass that broader check and could still fire. Both now check
         the NARROWER msnr_autotrade_eligible_symbols() (top-N) instead,
         closing that gap.
         Verified with py_compile after every edit, an actual runtime
         start (a live test_client() round-trip confirming GET /api/
         msnr/status still returns 200 while POST /api/msnr/
         autotrade_toggle now correctly 404s), pyflakes (clean), a full
         getElementById audit (94 calls, zero dangling), a real jsdom
         page execution (zero runtime errors), node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (55 routes — down from 56, exactly the one removed
         endpoint), and an AST walk for duplicate top-level defs (none
         introduced) — 305 total top-level defs, down from 308 (three
         genuinely dead functions removed).

v0.99.109 - NEW FEATURE: Scalp Martingale, per direct user request
         ("реализовать удвоение после стоплосса... классический
         мартингейл... 2%→4%→8%→16%") clarified via several rounds of
         Q&A before touching code given the real financial stakes (a
         Martingale system's exponential escalation on a losing streak
         is a mathematically well-understood risk, not a bug, and this
         account has been reported as small — worth confirming exact
         mechanics rather than guessing). Confirmed: classic doubling
         from the CURRENT level on each consecutive loss (not a flat
         2x every time), reset to base on a win, capped at SCALP_
         MARTINGALE_MAX_DOUBLINGS=3 consecutive doublings (2%→4%→8%,
         holds at 8x rather than continuing to grow) — user's own
         choice of a streak-count cap over a direct max-%-risk cap —
         and a SEPARATE multiplier per symbol (a loss on one coin
         doesn't escalate risk on an unrelated coin's next signal).
         New SCALP_MARTINGALE_ENABLED (defaults OFF — a deliberate
         opt-in, not something that should silently activate for an
         existing account) and SCALP_MARTINGALE_MAX_DOUBLINGS
         constants. New STATE["scalp_martingale"] = {symbol: {"streak",
         "multiplier"}}, new scalp_martingale_multiplier_for_symbol().
         execute_autotrade() gained an optional risk_pct_override
         param (every other module's own call site passes nothing,
         unaffected) — Scalp's own call site computes the current
         multiplier BEFORE firing and passes AUTOTRADE_RISK_PCT_OF_
         BALANCE * multiplier through to compute_risk_based_position(),
         which already accepted an override risk_pct from the v0.99.102
         redesign. update_scalp_signal_outcomes() updates the streak on
         a real WIN/LOSS — but ONLY when the closing signal's own
         autotrade_fired flag (new, set at signal creation only when
         execute_autotrade() actually reached OPENED/OPENED_TP_SL_
         FAILED) is true, so a purely informational signal (autotrade
         off, dry-run, skipped, or errored) — no real money at risk —
         never escalates risk on the NEXT real trade.
         UI: new settings row ("↳↳ Мартингейл после стопа ⚠️", with an
         explicit risk warning in its own sub-text) under Scalp's own
         autotrade row. Live signals table shows a "×N" badge next to
         a signal's own direction whenever it traded above base risk —
         the multiplier is frozen on the signal record at creation
         time (martingale_multiplier field), not a live-updating value,
         so a past signal's own badge never changes retroactively as
         later trades on other symbols resolve.
         Verified with py_compile after every edit, an actual runtime
         start throughout: a synthetic 4-consecutive-loss sequence
         confirming 1x->2x->4x->8x->(caps at 8x, doesn't reach 16x),
         then a win correctly resetting to 1x, and a different symbol
         confirmed completely unaffected; a live execute_autotrade()
         call with risk_pct_override=8.0 (4x base) confirmed the
         resulting margin came out ~4x the base-risk margin end to end;
         a live test_client() /api/settings round-trip confirming
         scalp_martingale_enabled persists and reads back correctly;
         a live /api/scalp/signals round-trip confirming martingale_
         multiplier reaches the frontend unmodified — pyflakes (clean),
         a full getElementById audit (95 calls, zero dangling), a real
         jsdom page execution (zero runtime errors), node --check on
         the correctly-last <script> block, the Flask route/def
         integrity check (55 routes — no new endpoints, existing
         settings pipeline extended), and an AST walk for duplicate
         top-level defs (none introduced).

v0.99.110 - mirror_symbol_direction_skip() changed from "skip only the
         losing side" to "always trade only the strictly better side,"
         per a conversational back-and-forth explaining the v0.99.107
         filter's own exact mechanics ("а зачем вообще торговать
         например Лонг с 25% а не только шорт с 60 по одной монете при
         хорошей выборке и там и там, просто брать хорошую сторону и
         все"). The old logic only skipped a direction that was
         outright UNPROFITABLE in isolation (below breakeven) — meaning
         a symbol with LONG at a modest-but-technically-profitable 28%
         and SHORT at a strong 60% (RR=3, breakeven 25%, both with
         sufficient sample) would trade BOTH sides, diluting risk onto
         the comparatively weak LONG edge for no real benefit given the
         much stronger SHORT alternative right there.
         New two-stage logic: (1) same absolute breakeven test as
         before, but now `<=` instead of `<` — a side sitting EXACTLY
         at breakeven is genuinely break-even, not profit, and letting
         it through was a real boundary bug, found and fixed while
         explaining the original mechanics (a direct side effect of
         this whole conversation, not something separately reported);
         (2) NEW — among whatever survives stage 1 (individually
         profitable directions), if BOTH survived, drop the weaker of
         the two. Per direct, explicit user choice ("да, всегда берём
         строго лучшую сторону, даже если разница маленькая") this
         comparison has deliberately NO minimum-gap requirement, unlike
         every other significance-bar filter in this file — even a
         1-point difference (e.g. 44% vs 46%) picks a winner. A symbol
         failing stage 1 on BOTH sides is left alone (not force-traded
         on "the less-bad loser") — that case is already handled
         separately by the overall winrate>MIRROR_LIVE_MIN_WINRATE gate
         in mirror_backtest_loop().
         Verified directly against 4 scenarios covering every branch:
         a side exactly at breakeven (25.0% @ RR=3) now correctly
         skipped, the motivating case (LONG 28%/SHORT 60%, both
         profitable, both good sample) correctly keeps only SHORT, both
         sides below breakeven (LONG 15%/SHORT 18%) correctly skips
         BOTH rather than force-trading SHORT, and a narrow gap (LONG
         44%/SHORT 46%) still picks the strictly better side per the
         user's own explicit no-minimum-gap choice. Also re-verified
         the original v0.99.107 motivating example (LONG 11%/SHORT 45%)
         and the thin-sample non-trigger case both still behave
         identically to before this change — this pass only ADDS the
         new comparative stage, doesn't alter the absolute-test
         behavior for cases where only one side has sufficient sample.
         Verified with py_compile, pyflakes (clean), the Flask route/
         def integrity check (55 routes — a pure filter-logic change,
         no routes/UI touched), and an AST walk for duplicate top-level
         defs (none introduced).

v0.99.111 - MIRROR live-eligibility minimum sample raised from 15 to
         80, live report: "у virtual n 15 всего, но она торгуется в
         топе. Хотя бы от 80 сделать." Root cause: mirror_backtest_
         loop()'s own live-eligibility gate (added v0.99.98, "Мин.
         выборка на live-гейте") reused MIRROR_SYMBOL_SKIP_MIN_SAMPLE
         (=15) as a whole-symbol floor — but that constant's own actual
         purpose is judging whether ONE bucket/pattern/direction slice
         within a symbol's data is reliable (the SL-width/pattern/
         direction filters), a genuinely different, much lower bar than
         "is this symbol's OVERALL history long enough to trust for
         live money at all." A symbol clearing barely 15 total trades
         could read as, say, 90% winrate purely from a small, lucky
         sample and still get promoted to live trading exactly like a
         genuinely-tested 80+ trade symbol.
         New dedicated MIRROR_LIVE_MIN_SAMPLE=80 (env-overridable via
         VP_MIRROR_LIVE_MIN_SAMPLE) replaces MIRROR_SYMBOL_SKIP_MIN_
         SAMPLE at this ONE call site only — the per-filter significance
         bar (SL-width/pattern/direction skip logic) stays at 15,
         unchanged, since the user's report was specifically about
         live-trading eligibility, not those other filters. Also
         exposed in api_mirror_status()'s own config dict (live_min_
         sample, alongside the existing live_min_winrate) for
         transparency.
         Verified directly against the exact reported case: a symbol at
         n=15 with a strong 90% winrate now correctly fails the gate
         (previously would have passed); n=80 exactly clears it; n=79
         (one short) still correctly fails; a genuinely well-tested
         n=150 symbol at a modest 40% winrate still correctly passes —
         confirming the fix targets sample size specifically, not
         winrate. Also confirmed the new config field reaches a live
         /api/mirror/status response.
         Verified with py_compile, pyflakes (clean), the Flask route/def
         integrity check (55 routes — a pure threshold/constant change,
         no new endpoints), and an AST walk for duplicate top-level defs
         (none introduced).

v0.99.112 - CRITICAL FIX, live report (screenshot): a real LONG
         autotrade attempt ending in bare ERROR, detail "HTTPSConnection
         Pool(host='api.gateio.ws', port=443): Read timed out. (read
         timeout=15)" — 9 such errors logged. Root cause: gate_signed_
         request() had NO retry logic at all; a single transient
         timeout anywhere in execute_autotrade()'s own multi-call flow
         (balance fetch, leverage fetch, position check, the order
         itself) aborted the whole thing straight to ERROR, potentially
         wasting a genuinely good signal — or worse, if the timeout hit
         AFTER order placement, silently abandoning a real, unprotected
         position with no TP/SL.
         Added gate_signed_request(..., retry_on_timeout=False) — an
         opt-in flag, defaulting False so every existing caller's
         behavior is unchanged. Each retry attempt regenerates the
         timestamp/signature from scratch (not resending the same
         signed payload) — Gate's own signature scheme has a timestamp
         tolerance window, and reusing one from a request that already
         waited out a full 15s timeout risked the retry itself being
         rejected as stale. Opted in ONLY genuinely read-only or
         idempotent calls: get_futures_total_equity(), get_futures_
         wallet_balance(), get_open_positions() (all read-only GETs),
         set_leverage() (idempotent — setting the same value twice has
         no side effect). get_contract_spec() uses a separate, unsigned
         public endpoint (no gate_signed_request() involved at all) —
         gained its own equivalent small retry loop directly.
         Deliberately did NOT add retry to place_market_order() itself
         — if a timeout happens AFTER Gate's server already processed
         the order but BEFORE the response reached this client, blindly
         resending would place a SECOND, duplicate order, a materially
         worse outcome than one wasted signal. Instead, execute_
         autotrade()'s own call site now catches a timeout specifically
         on that ONE call and checks the exchange directly (get_open_
         positions(), the same ground-truth query the existing
         duplicate-position guard already uses) — if the position
         genuinely did open despite the timeout, synthesizes an order
         record from the real position and continues to TP/SL
         placement (protecting what would otherwise be a real,
         unprotected position); if the position genuinely never landed,
         re-raises and reports ERROR as before, with no duplicate risk
         either way since nothing was opened.
         Verified with py_compile after every edit, an actual runtime
         start throughout: gate_signed_request() tested directly with a
         mocked requests.request() forcing 2 timeouts then a success on
         the 3rd attempt (confirmed exactly 3 attempts, 3 DIFFERENT
         timestamps — proving each retry re-signs rather than resending
         a stale signature) and, separately, confirmed retry_on_
         timeout=False (every existing caller's own unaffected default)
         still makes exactly 1 attempt before raising, identical to the
         old behavior; get_contract_spec()'s own new retry loop tested
         the same way (1 timeout then success, 2 total attempts); and —
         the highest-stakes case — a full execute_autotrade() run with
         place_market_order() mocked to always raise Timeout, tested
         against BOTH branches: the exchange confirming a real position
         despite the timeout (correctly reaches OPENED, not ERROR, with
         an order_timeout_note explaining what happened) and the
         exchange confirming NO position exists (correctly still
         reaches ERROR, exactly as before this fix) — pyflakes (clean),
         the Flask route/def integrity check (55 routes — a pure
         reliability fix, no routes/UI touched), and an AST walk for
         duplicate top-level defs (none introduced).

v0.99.113 - MIRROR_LIVE_MIN_WINRATE raised 35->40, per direct user
         request ("сделай минимальный винрейт для авто торговли 40%")
         alongside a live report/question: many symbols in the
         backtest table show n=0 (no post-filter trades at all,
         displayed as "?" and "skip SL≥0%") despite a substantial raw
         signal count, with the user's own hypothesis being "типа
         фильтрами может все режет так, что сделок не остаётся" —
         confirmed correct, not a bug, via a direct reproduction:
         for a symbol whose raw MIRROR trades cluster at a similar SL
         width with a poor overall winrate (e.g. the reported ETH_USDT
         at 358 raw -> 0 final, WR 19%, well below the RR=3 breakeven
         of 25%), mirror_symbol_sl_skip_min() alone can find that
         literally every SL-width bucket fails — meaning the SL filter
         eliminates 100% of the raw trades before the later pattern/
         direction filters ever get anything to work with. The "skip
         SL≥0%" seen for these symbols is a real, correctly-computed
         threshold (the very first, narrowest bucket already fails),
         not a formatting bug or an empty-input artifact — directly
         verified both by reproducing the exact cascade on synthetic
         data matching the reported numbers and by confirming mirror_
         symbol_sl_skip_min([]) itself returns None (not 0) on genuinely
         empty input, ruling out that alternate explanation. This is
         the intended, correct behavior of a rigorous chained filter —
         a symbol that's unprofitable across virtually every SL width
         genuinely shouldn't be live-traded via MIRROR at all, and
         total elimination (rather than forcing SOME trades through) is
         the right outcome, not something to loosen.
         Verified with py_compile, pyflakes (clean), a live test_client()
         /api/mirror/status round-trip confirming the new 40.0 value
         reaches the response's own config, the Flask route/def
         integrity check (55 routes — a pure constant change, no new
         endpoints), and an AST walk for duplicate top-level defs (none
         introduced).

v0.99.114 - MIRROR filter-blocked-signal shadow tracking, per direct
         user follow-up to v0.99.113's own explanation ("может без
         применения фильтра было лучше, а после него стало хуже") — a
         fair, pointed critique: every "this filter helps" claim so far
         rested purely on the backtest's own retrospective self-
         consistency (the filter was derived FROM, then judged AGAINST,
         the exact same historical data), exactly the kind of circular
         validation vulnerable to in-sample overfitting, especially
         with a modest per-bucket sample (MIRROR_SYMBOL_SKIP_MIN_
         SAMPLE=15) and a chained filter where each stage narrows what
         the next one judges.
         Rather than argue this abstractly, a signal the SL-width or
         direction filter blocks from firing now gets recorded (new
         STATE["mirror_filtered_signals"]) and tracked through the
         EXACT same WIN/LOSS/TIMEOUT outcome logic as a real signal —
         just never fired via execute_autotrade()/sim_execute_trade(),
         no Telegram alert. Refactored the shared tracking body out of
         update_mirror_signal_outcomes() into a new _mirror_track_
         signal_outcomes(signal_key) so both pools (real and filtered)
         run through the IDENTICAL logic, not a second, potentially-
         drifting reimplementation. New compute_mirror_filtered_signal_
         stats() (n/wins/losses/win_rate, plus a by_reason split
         between sl_width- and direction-blocked signals — a filter
         that's net harmful might only be so for one of the two, not
         both) exposed via api_mirror_status()'s own new filtered_
         signals_stats field. Persisted via save_state()/load_state()
         so this pool survives a restart. Frontend: refreshMirror()
         shows this pool right alongside the real "Живые сигналы" line
         — real forward comparison the person can watch accumulate over
         the coming weeks, not a one-time argument.
         The mechanism itself makes no claim either way about whether
         the filter is currently helping or hurting — that's exactly
         the point: it turns an unresolvable backtest-vs-backtest
         argument into something genuinely testable going forward, with
         real, out-of-sample data.
         Verified with py_compile after every edit, an actual runtime
         start (mirror_scan_symbol_live() tested directly with a
         synthetic signal deliberately built to trip the SL-width
         filter — confirmed it lands in the filtered pool with the
         correct filter_reason="sl_width" and does NOT reach the real
         signals pool; manually closed it as WIN and confirmed compute_
         mirror_filtered_signal_stats() correctly computes n=1, win_
         rate=100.0, and the right by_reason breakdown; a live test_
         client() /api/mirror/status round-trip confirming filtered_
         signals_stats reaches the response), pyflakes (clean), a full
         getElementById audit (95 calls, zero dangling), a real jsdom
         page execution (zero runtime errors), node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (55 routes — no new endpoints, existing one extended),
         and an AST walk for duplicate top-level defs (none
         introduced).

v0.99.115 - Module removal: XAU Liquidity Grab, Session, and Session NY
         backend fully deleted, per direct user request ("продолжи
         работу по удалению не нужных индикаторов и всего с ними
         связано, перепроверяй все чтобы не сломать ничего"). All
         three had their frontend (tabs, settings) removed back in
         v0.99.101 with backend deliberately left for a later pass —
         this is that pass, done across several turns given the scope.
         XAU LG: all 10 functions (detect/track/backtest/summarize/
         scan_live/update_outcomes/compute_stats/both daemon loops),
         4 API routes, its own risk_autotune_pass() block, 13 XAU_LG_*
         constants, TELEGRAM_ALERTS_XAU_LG, RISK_AUTOTUNE_XAU_LG_RR_
         BOUNDS, all STATE keys, 3 orphaned setters, all string-keyed
         dict entries (module_lists, Telegram category check, enabled
         status) — the exact bug class pyflakes can't catch, checked
         for proactively this time rather than found live after the
         fact.
         Session/Session NY: structurally harder — the two modules'
         definitions were interleaved in the file (not one clean block
         like XAU LG), so removed function-by-function/block-by-block
         rather than one contiguous deletion. All 17 core functions,
         4 daemon loops, 10 API routes, Session's own risk_autotune_
         pass() block, ~30 SESSION_*/SESSION_NY_* constants, both
         TELEGRAM_ALERTS_SESSION* constants, all STATE keys, 3 orphaned
         setters, the sessionModal HTML+CSS (confirmed via grep the JS
         side was already cleaned in v0.99.101, only markup/styles were
         left), two `if SESSION_ENABLED:` blocks still living inside
         the shared scan_loop() referencing now-deleted functions, and
         every string-keyed dict entry across SNAPSHOT_MODULE_KEYS/
         module_lists/Telegram category/autotrade enabled status.
         Found and fixed along the way, all confirmed via direct
         grep/testing rather than left to a future session:
         (1) two more EMA leftovers missed by every prior EMA removal
         pass (v0.99.96) — "ema": AUTOTRADE_ENABLED_EMA in the
         autotrade status dict, TELEGRAM_ALERTS_EMA, AUTOTRADE_
         LEVERAGE_EMA, and the #emaModalHeader/#emaCloseBtn/
         #emaChartWrap CSS rules — all genuinely dead, all removed;
         (2) session_sl_mult/session_reverse_rr had survived v0.99.101's
         own settings-removal pass despite session_invert_signals/
         session_enabled being correctly removed at the time — closed
         the gap;
         (3) CRITICAL, independently pre-existing bug (not introduced
         by this pass, but exposed and fixed while removing "session"
         from api_overview()'s response): refreshOverview() referenced
         o.divergence.enabled as its very FIRST line, before scalp or
         anything else — divergence/ema were removed well before this
         session, so this had been silently, completely broken (the
         surrounding try/catch swallowed the TypeError every single
         time) since at least whichever removal came first. The
         overview bar likely never rendered correctly for a long
         stretch. Directly reproduced with a live jsdom test: the OLD
         code throws "Cannot read properties of undefined (reading
         'enabled')" on the exact data api_overview() now actually
         returns; the NEW code (matching that real response — volume
         and scalp only) renders correctly with the same test data.
         (4) A dict string key ("xau_lg": STATE[...]) and interleaved-
         module structural gotcha both explicitly checked for
         proactively this pass, per this session's own established
         "check for these two specific bug classes on every removal"
         discipline — no new instances of either found this time.
         Comments updated to stop referencing deleted functions as if
         still callable (mirror_track_outcome, msnr_build_pivots,
         update_mirror_signal_outcomes, and one duplicated paragraph
         introduced then caught and fixed while editing msnr_build_
         pivots()'s own docstring) — historical changelog entries left
         untouched throughout, only live docstrings/comments describing
         CURRENT behavior were corrected. GLOBAL_HTTP_SEMAPHORE's own
         "14 separate ThreadPoolExecutors" comment updated to the
         directly-counted current figure (13) rather than left stale
         after removing 4 of the original loops (also updated a second,
         separate mention of the same stale count elsewhere).
         Verified with py_compile after every single edit throughout
         (dozens of edits across this multi-turn pass), pyflakes
         (clean at every step, not just the end), an actual runtime
         start repeatedly (live test_client() round-trips confirming
         every real endpoint still 200s and every removed endpoint now
         correctly 404s; save_state()/load_state() both actually
         executed successfully, not just statically checked, since
         removed STATE keys accessed via string literals are exactly
         what pyflakes cannot catch), a full getElementById audit (95
         calls, zero dangling), a real jsdom page execution (zero
         runtime errors) AND a separate, targeted jsdom test of the
         refreshOverview() fix specifically (reproducing the old bug
         first, then confirming the fix), node --check on the
         correctly-last <script> block, the Flask route/def integrity
         check (41 routes — down from 55, exactly the 14 removed
         endpoints: 4 XAU LG + 10 Session/Session NY), and an AST walk
         for duplicate top-level defs (none introduced) — 257 total
         top-level defs, down from 306.

v0.99.116 - Dead-code sweep, per direct user request ("продолжи
         очистку мусора, проверки на баги... может что-то можно
         оптимизировать значительно сократив код"). Ran a systematic
         AST-based scan across the WHOLE file (not just recently-
         removed modules) — collected every top-level function name,
         then counted its own literal occurrences anywhere in the
         source. A name appearing only once (its own `def` line) has
         zero real callers. The scan flagged 21 candidates; all but 4
         turned out to be Flask route handlers (api_status, api_scalp_
         signals, etc.) — legitimate, working code that's never
         referenced BY NAME anywhere else since Flask's own url_map
         dispatches to them via their @app.route(...) decorator, not a
         Python call site (confirmed several of these already respond
         200 via existing test_client() checks). Correctly left alone.
         The 4 genuine finds, each individually verified (not just
         trusted from the count) before removal:
         (1) A real BUG, not just cruft: msnr_detect_signals() called
         msnr_build_pivots() twice in a row with identical arguments —
         found and flagged in passing during an earlier session, fixed
         now. Confirmed the function is pure (no mutation, no external
         state) before treating the duplicate as safe to drop — a
         pure-performance fix, zero behavior change, verified directly
         with a synthetic candle series before/after.
         (2) _crossover()/_crossunder() — Pine-Script-style TA helpers,
         leftover from EMA/Divergence (both long since removed, both
         the kind of module that used crossover-based detection).
         (3) msnr_volume_bucket_stats() — its OWN docstring called it
         "display-only... purely for showing" a distribution, but
         nothing anywhere ever calls it; the actual filter logic
         (msnr_symbol_volume_skip_below()) explicitly does its own
         separate computation instead, per that function's own
         docstring.
         (4) The ENTIRE "signal snapshot" feature — save_signal_
         snapshot()/list_signal_snapshots()/replay_signal_snapshot()/
         _signal_passes_replay_filters(), SNAPSHOT_MODULE_KEYS, _
         SNAPSHOT_REPLAY_OPS, and STATE["signal_snapshots"] — a
         coherent, complete, "per user request" (per its own comment)
         capability that was apparently built but never actually wired
         to any API route or UI trigger: verified EVERY function in
         the chain individually has zero real callers, and confirmed
         its own STATE key was never even included in save_state()'s
         own persisted-keys list despite its own comment claiming it
         was — a second, independent signal this was left half-
         finished rather than actively used and just recently orphaned.
         Verified with py_compile after every removal, pyflakes (clean
         at every step), an actual runtime start (msnr_detect_signals()
         run on a synthetic candle series post-fix, producing sane
         output; save_state()/load_state() both actually executed
         successfully post-removal, not just statically checked; a
         live test_client() round-trip confirming every real endpoint
         still 200s), a real jsdom page execution (zero runtime
         errors), node --check on the correctly-last <script> block,
         the Flask route/def integrity check (41 routes unchanged —
         none of the removed code was ever route-connected), and an
         AST walk for duplicate top-level defs (none introduced) — 250
         total top-level defs, down from 257.

v0.99.117 - Dead-code sweep continued: extended the same AST-based
         methodology from v0.99.116 (count every name's own literal
         occurrences across the source) to module-level CONSTANTS and
         STATE dict keys, not just functions.
         Constants: scanned all 259 ALL_CAPS module-level assignments,
         found 3 with zero real references beyond their own definition
         line, each individually verified before removal: (1) SCALP_
         SIGNAL_COOLDOWN_SEC — the actual live dedup mechanism (checked
         directly) compares exact last-candle timestamps via _scalp_
         signal_cooldowns, not a time-window constant at all; superseded
         by a cleaner mechanism and never cleaned up; (2) AUTOTRADE_
         LEVERAGE_FT5 — confirmed FT5 has no sim_execute_trade() call
         site at all (grepped every real call site: scalp/bounce-
         breakout/msnr/mirror only), so this constant was never
         reachable by anything; (3) RISK_AUTOTUNE_SESSION_RR_BOUNDS —
         a leftover from v0.99.115's own Session removal, missed at the
         time since its only consumer (Session's own risk_autotune_
         pass() block) had already been deleted earlier in that same
         pass, making this bounds constant orphaned from that point on.
         STATE keys: parsed the actual `STATE = {...}` dict literal via
         AST (not text search, to get the real top-level key list
         precisely — 65 keys) and checked each for real STATE["key"]
         usage beyond its own initialization. Found 3: filtered_by_
         min_rr/filtered_by_adx/filtered_by_min_gap — confirmed via a
         historical comment (still describing a genuinely bygone
         incident, left untouched) that these were EMA's own panel
         counters; EMA's removal correctly deleted whatever incremented
         them, but the STATE initialization itself survived, sitting at
         a permanent 0 forever after. The sibling filtered_by_trend/
         volume/oi/staleness keys were correctly NOT flagged — still
         genuinely used by Volume Profile's own live filtering.
         Verified with py_compile after every removal, pyflakes (clean
         at every step), re-ran BOTH scans afterward confirming zero
         remaining orphaned constants and zero remaining orphaned
         top-level STATE keys, an actual runtime start (save_state()/
         load_state() both actually executed successfully; a live
         test_client() round-trip confirming every real endpoint still
         200s), a real jsdom page execution (zero runtime errors),
         node --check on the correctly-last <script> block, the Flask
         route/def integrity check (41 routes unchanged — nothing
         removed was route-connected), and an AST walk for duplicate
         top-level defs (none introduced, unchanged at 250 — this pass
         touched constants/STATE only, no functions).

v0.99.118 - Dead-code sweep, frontend side: extended the same "count
         every name's own occurrences" methodology to the CSS #id
         selector layer, checking each against both the HTML's own
         id="..." attributes and every JS getElementById() call.
         Found and removed 12 fully orphaned rules — the #divModal/
         #divCloseBtn/#divChartWrap (Divergence) and #emaModal/
         #emaCloseBtn/#emaChartWrap (EMA) modal chrome, both sets a
         complete 6-rule shape (base/.open/Header/Header h2/CloseBtn/
         ChartWrap). A historical comment elsewhere in the file (from
         whenever Divergence/EMA's own HTML shells were removed)
         already confirmed those elements were "now-dead ... HTML
         shells" — the matching CSS rules were simply the one piece
         left behind at the time.
         Corrects an inaccuracy in this file's OWN v0.99.115 changelog
         entry, which claimed "#emaModalHeader/#emaCloseBtn/
         #emaChartWrap CSS rules — all genuinely dead, all removed" —
         what that pass actually removed was a duplicate SECOND
         occurrence of those same three EMA lines (found sitting right
         above Session's own CSS block being deleted at the time); the
         original, first copy of those rules — plus the matching
         #emaModal/#emaModal.open base rules never mentioned at all —
         survived untouched until this pass. Worth remembering: a
         changelog claim of "removed" deserves the same re-verification
         as any other assumption, not just trust in what a past version
         of this same file already said about itself.
         Also swept the frontend more broadly for the OTHER bug class
         v0.99.115 found once already (a live JS reference to a field
         a now-simplified backend response no longer sends, like the
         old o.divergence.enabled crash): checked every remaining
         top-level JS function for zero-caller orphans (none — the
         frontend was already clean from the getElementById-audit
         discipline maintained throughout every module removal this
         session) and specifically re-grepped for any live code
         (not comments) still referencing xau_lg/session/session_ny/
         divergence/ema/vgi as an object property — found none; the
         only remaining textual matches are inside this same file's
         own comments describing past incidents, not executable code.
         Verified with py_compile, pyflakes (clean), node --check on
         the correctly-last <script> block, a full getElementById
         audit (95 calls, zero dangling — unchanged, confirming the
         removed CSS was never paired with a live JS reference either),
         a real jsdom page execution (zero runtime errors), and the
         Flask route/def integrity check (41 routes unchanged — a pure
         CSS change, nothing route-connected).

v0.99.119 - NEW MODULE: LSW ("Liquidity Sweep") — equal-highs/equal-
         lows liquidity-grab reversal, per direct user request ("Order
         flow, вход на выбивании чужих столпов" -> "В VP poc как
         отдельная вкладка надо добавить как новый индикатор"). >=2
         swing pivots (fractal, same left/right shape as MIRROR's own
         pivot detector) clustering within LSW_EQUAL_TOLERANCE_PCT of
         each other are treated as one resting-liquidity level. A
         signal fires when a later candle's wick pokes beyond that
         level but its CLOSE comes back inside — a genuine sweep,
         deliberately distinct from a breakout (which closes through
         and is NOT treated as a signal) — same definition used by
         every public SMC/liquidity-sweep implementation checked before
         building this (rafalsza/joshyattridge's smartmoneyconcepts
         package's own smc.liquidity() docstring: "Swept = the index of
         the candle that swept the liquidity"). Direction is the
         reversal AWAY from the swept side (sweeping equal highs ->
         SHORT, equal lows -> LONG); stop-loss sits just beyond the
         sweep candle's own wick extreme (LSW_SL_BUFFER_PCT buffer);
         take-profit is a fixed RR off that risk (LSW_RR) — same
         "mechanical pipeline needs one fixed target" reasoning as
         MIRROR_RR's own docstring.
         Deliberately PAPER-ONLY per direct, explicit user choice
         ("Сначала paper-симуляция, автоторговлю добавим потом"):
         lsw_scan_symbol_live() never calls execute_autotrade()/
         sim_execute_trade() — there is no AUTOTRADE_ENABLED_LSW
         anywhere in this app, no autotrade settings key, no Telegram
         alert wiring. Live signals are still tracked through the same
         real WIN/LOSS/TIMEOUT forward-data logic every other module
         uses (_lsw_track_signal_outcomes(), MFE/MAE included) — same
         shape as MIRROR's own filtered-signal shadow-tracking pool
         (v0.99.114), just as the ONLY pool here rather than a second
         one alongside real trades.
         Named lsw_/LSW_, NOT sweep_/SWEEP_ — sweep_sim_trades()
         already exists in this file for an unrelated purpose (settling
         PENDING paper trades from the shared sim_trades system), so
         reusing that name would have collided.
         Deliberately simpler than MIRROR for this first version — no
         SL-width/pattern/direction filter chain yet (MIRROR only grew
         that after real backtest data justified it, several versions
         in); this ships with just detection + backtest + paper-tracked
         live signals, the same scope MIRROR itself started at in
         v0.99.91. A live-eligibility gate still exists (LSW_LIVE_MIN_
         WINRATE=35%, LSW_LIVE_MIN_SAMPLE=30 closed backtest trades)
         so the live scanner only watches symbols with SOME supporting
         backtest evidence, same principle as every other module here,
         just a lower sample bar than MIRROR's (80) since the priority
         right now is gathering broad real forward data on a brand-new
         detector, not a final live-trading gate.
         Full vertical slice: constants, STATE (lsw_signals/
         lsw_backtest_results/lsw_backtest_summary/lsw_live_universe),
         settings (lsw_enabled/lsw_rr/lsw_equal_tolerance_pct — get_
         settings/apply_settings/SETTINGS_KEYS), detection (lsw_find_
         pivots/lsw_detect_signals), backtest (lsw_track_outcome/lsw_
         build_universe/lsw_backtest_symbol/lsw_summarize_backtest/
         lsw_backtest_loop), live scan (lsw_scan_symbol_live/_lsw_
         track_signal_outcomes/update_lsw_signal_outcomes/lsw_live_
         loop), stats (compute_lsw_signal_stats), 4 new API routes
         (/api/lsw/status, /api/lsw/chart/<symbol>, /api/lsw/signals,
         /api/reset/lsw), save_state()/load_state() persistence for
         lsw_signals, frontend (new "Sweep" tab, lswPanel, refreshLsw(),
         openLswChart() thin wrapper around openVgiChart() — same reuse
         judgment as openMirrorChart's own, since LSW's signal shape is
         structurally identical — resetLswBtn, settings modal group with
         an explicit "⚠️ paper-only" label so the UI itself doesn't let
         this read as a real-money module), 2 new background threads
         (lsw_backtest_loop, lsw_live_loop) started alongside every
         other module's own at the bottom of the file.
         Verified: py_compile, pyflakes clean, node --check on the
         correctly-last <script> block, a real runtime start, Flask
         route/def integrity check (45 routes, up from 41 — exactly the
         4 new LSW routes, nothing else changed), and a synthetic-candle
         unit test of lsw_detect_signals() confirming a hand-built
         equal-highs sweep (two matching swing highs, then a third
         candle wicking above both and closing back below) correctly
         fires a SHORT signal with SL above the sweep wick and TP at
         the expected RR distance — and the mirror LONG case off two
         equal lows.

v0.99.120 - LSW autotrade wired in, per direct follow-up user request
         ("надо живые сигналы сделать и авто торговлю как и везде,
         тоже с риском 2%") — v0.99.119 shipped LSW paper-only; this
         version makes lsw_scan_symbol_live() fire real trades the
         exact same way every other module does: execute_autotrade(
         "lsw", ...) when the new AUTOTRADE_ENABLED_LSW toggle is on
         (same automatic risk-based leverage/sizing every module
         already shares — 2% of confirmed equity per trade via the
         shared AUTOTRADE_RISK_PCT_OF_BALANCE, no per-module override
         needed or added), plus sim_execute_trade() for the separate
         paper-balance simulator (its own AUTOTRADE_LEVERAGE_LSW
         constant, same "deliberately kept on its own old leverage
         system" pattern every other module's sim call already uses),
         plus a Telegram alert gated on a new TELEGRAM_ALERTS_LSW flag.
         Off by default, same as every other module's own autotrade
         toggle — opt-in via Settings > Автоторговля > Sweep.
         Also added has_open_signal_any_module()'s own lsw_signals
         entry — LSW's live signals weren't in that cross-module guard
         before since paper-only signals had no real-position conflict
         to protect against; now that a real order can fire, the same
         guard MIRROR's own real-signal branch uses applies here too
         (lsw_scan_symbol_live() switched from an LSW-only "already
         open" check to the shared cross-module one).
         Also closed a small pre-existing gap while adding this rather
         than copy it forward: send_telegram()'s own category param
         checks "vp"/"hourly"/"ft5"/"msnr" against their own TELEGRAM_
         ALERTS_* flag but — found while wiring the analogous "lsw"
         check — never actually checks "mirror" against TELEGRAM_
         ALERTS_MIRROR (that flag is fully wired everywhere else —
         settings, UI checkbox — just never read here), the same class
         of dead-control bug v0.99.72's own changelog entry already
         found and fixed once for MSNR. Left MIRROR's own gap alone
         (out of scope for this change, and a working example already
         exists to fix it from later if asked) but built LSW's own
         "lsw" check correctly from the start rather than reproducing
         the same bug class a third time.
         Frontend: removed every "⚠️ paper-only" / "Paper-сигналы"
         label from the Sweep tab and settings modal (headerHtml, empty-
         state text, reset-button confirm text) since they're no longer
         accurate; added a "↳ Sweep" toggle to the Автоторговля settings
         group (with an inline note about the shared 2% risk) and a
         "↳ Алерты Sweep" toggle to the Telegram group; modeLabels (used
         by both the autotrade log table and its own summary line) now
         includes lsw: 'Sweep' in both of its two identical occurrences.
         Verified: py_compile, pyflakes clean, node --check on the
         correctly-last <script> block, a real runtime start, the Flask
         route/def integrity check (still 45 routes — this version adds
         no new routes, only wires existing ones together differently),
         and a getElementById audit confirming the 2 new settings IDs
         (setAutotradeLsw, setTelegramLsw) are each defined exactly once
         and referenced exactly once, no dangling references either way.

v0.99.121 - Two fixes + one strategy addition, both per direct user
         messages in the same session.
         FIX 1: /api/autotrade/status's own "enabled" dict never
         included "lsw" — found while investigating the report below,
         this meant Sweep's autotrade toggle state silently never
         showed up in the Автоторговля tab or the Simulator header's
         own "Режимы:" line (both read from this same endpoint).
         FIX 2 (the real cause of the report — "Все что торгуется в
         реальности должно и в симуляторе показываться и считать
         депозит, а пока я не вижу там многих сигналов"): sim_execute_
         trade() used to silently return None — recording NOTHING —
         the moment the paper balance hit zero or went negative
         (percent-of-balance sizing degenerates to a 0 margin at a
         non-positive balance, and the old code bailed before ever
         building the trade record). That meant real trades from ANY
         module could keep firing indefinitely while the simulator
         quietly stopped recording all of them, with zero error or
         indication anything had gone dark — directly contradicting
         the simulator's own stated purpose of mirroring real trading.
         Fixed: sizing now falls back to AUTOTRADE_SIM_START_BALANCE as
         the basis whenever the CURRENT balance isn't positive, so
         percent-mode sizing stays meaningful instead of collapsing to
         zero — every real trade always gets a paper trade recorded,
         and the balance itself is left free to go negative, same as a
         real wiped-out account actually would.
         STRATEGY ADDITION, per a second direct message pointing at a
         real ICT-style "Setup №1: AMD + FVG" reference note and asking
         to study it and refine LSW against it: that note's rule #1 is
         "только по тренду, дневка вверх и часовик восходящий
         моментум" (trade only WITH the higher-timeframe trend) — our
         detector already implements its rule #2/#5 (the liquidity
         sweep IS the entry trigger) but had no trend gate at all. Added
         one: lsw_htf_bias_series() computes UP/DOWN/NEUTRAL per HTF bar
         (LSW_HTF_INTERVAL=4h by default) from an EMA(LSW_HTF_EMA_
         PERIOD=50) with a small dead-zone buffer (LSW_HTF_TREND_
         BUFFER_PCT) to avoid flip-flopping right at the line;
         lsw_htf_bias_at() looks up the bias as of a given LTF signal's
         own entry_time using only HTF bars that had ALREADY closed by
         then (no lookahead — a still-forming HTF bar's close isn't
         known yet); lsw_filter_signals_by_htf_trend() drops a LONG
         (sweep of equal lows) unless HTF bias is UP/NEUTRAL, drops a
         SHORT (sweep of equal highs) unless it's DOWN/NEUTRAL, and
         drops anything with no closed HTF bar yet at all (conservative
         by design). Wired into both lsw_backtest_symbol() (fetches
         LSW_HTF_INTERVAL history over the same window, so backtest
         numbers reflect the filter exactly as live would apply it) and
         lsw_scan_symbol_live() (fetches recent HTF candles, applies the
         same filter to that bar's own signal before it's ever recorded
         or traded). Gated behind a new LSW_HTF_FILTER_ENABLED toggle
         (setLswHtfFilter checkbox, "↳ Фильтр по тренду (4ч)" in the
         Sweep settings group) — off by default, same "opt-in until the
         person has seen it work" convention as every other toggle in
         this file; the sample size to judge "did this filter actually
         help" barely exists yet for a module this new.
         The reference note's other rules — 5-minute entry confirmation
         via инверсия/BOS/поглощение (rule #3) and a structural-high
         entry cap (rule #4) — are NOT implemented yet; they need a
         second, lower timeframe wired in for confirmation and were out
         of scope for this pass. Left for a follow-up.
         Verified: py_compile, pyflakes clean, a real runtime start
         confirming both api_lsw_status()'s config.htf_filter_enabled/
         htf_interval and api_autotrade_status()'s enabled.lsw now
         appear correctly, node --check on the correctly-last <script>
         block, the Flask route/def integrity check (still 44 routes —
         no new routes, only existing ones' logic changed), a
         getElementById audit on the one new ID (setLswHtfFilter,
         defined once, referenced once), and unit tests: EMA seeding
         against a hand-computed value, bias-series correctness on
         synthetic monotonic up/down candle sequences, a no-lookahead
         check on lsw_htf_bias_at() at exactly a HTF bar's own close
         boundary, lsw_filter_signals_by_htf_trend() correctly keeping
         only the trend-aligned direction in both an uptrend and a
         downtrend and dropping a signal with no closed HTF data yet,
         and a direct sim_execute_trade() test confirming a trade now
         gets recorded (with a sane margin) even when STATE["sim_
         balance"] is set negative, whereas the pre-fix code would have
         silently returned None.

v0.99.122 - LSW's remaining two rules from the reference "AMD + FVG"
         note, per direct "Продолжи" follow-up to v0.99.121's own
         changelog entry (which had explicitly deferred these).
         Rule #4 ("торгуем не выше структурного максимума"):
         lsw_filter_signals_by_structural_cap() — a LONG only survives
         if its own entry sits BELOW the nearest significant structural
         high confirmed within LSW_STRUCTURAL_CAP_LOOKBACK bars (found
         via lsw_find_pivots() with a deliberately WIDER left/right —
         LSW_STRUCTURAL_CAP_PIVOT_LEFT/RIGHT, 10/10 — than the 3/3 used
         for equal-highs/lows grouping itself, since a "structural"
         swing is meant to be a bigger, more significant move); a SHORT
         mirrors this against the nearest structural low. A signal with
         no qualifying structural pivot in its own window is KEPT —
         nothing to cap against isn't a reason to block the trade.
         Rule #3 (5-minute entry confirmation via инверсия/BOS/
         поглощение): lsw_scan_5m_confirmation() scans LSW_ENTRY_
         CONFIRM_INTERVAL (5m) candles starting at the 1h sweep
         candle's own close, for up to LSW_ENTRY_CONFIRM_MAX_BARS (12 x
         5m = 1h) bars, for the FIRST of: BOS (a 5m close breaking the
         most recent 5m swing point in the trade's own direction),
         поглощение/absorption (a 5m candle whose rejection wick against
         the trade direction covers >= LSW_ENTRY_CONFIRM_WICK_RATIO of
         its own range, closing in the favorable part of it), or
         инверсия/inversion (a mini version of the same liquidity-sweep
         idea at 5m resolution — wicking past the last few bars' own
         extreme against the trade direction, closing back beyond it in
         the trade's favor). Whichever fires on the earliest bar wins.
         lsw_apply_entry_confirmation() then REPLACES the signal's own
         entry/sl with the confirmed values (tighter than the original
         1h-wick-based stop in every case tested) and recomputes tp at
         the same rr — or drops the signal entirely if nothing confirms
         within the window, since the reference note treats these as
         required entry triggers, not optional refinements.
         Both wired into lsw_backtest_symbol() (structural cap runs
         directly against the already-fetched 1h candles, no extra
         fetch; entry confirmation fetches LSW_ENTRY_CONFIRM_INTERVAL
         history over the same backtest window) and lsw_scan_symbol_
         live() (structural cap checked inline; entry confirmation
         fetches recent 5m candles and confirms/drops that bar's own
         signal before it's ever recorded). Filter order in both:
         HTF trend -> structural cap -> 5m confirmation — cheapest
         checks first, so the comparatively expensive 5m fetch/scan
         only runs on signals that already passed the other two.
         Known simplification, noted directly in lsw_apply_entry_
         confirmation()'s own docstring: outcome tracking still walks
         the ORIGINAL 1h candles from the sweep's own entry_idx
         afterward (lsw_track_outcome() isn't 5m-aware) rather than
         starting from the confirmed 5m entry precisely — acceptable
         since confirmation only ever happens within at most 1h of the
         sweep candle's own close, so the very next 1h bar already
         covers that window in almost every case.
         Both off by default (setLswStructuralCap, setLswEntryConfirm
         checkboxes in the Sweep settings group), same convention as
         every toggle in this file — barely any real forward data
         exists yet to judge whether either genuinely helps.
         Verified: py_compile, pyflakes clean, a real runtime start
         confirming api_lsw_status()'s new config fields (structural_
         cap_enabled, entry_confirm_enabled, entry_confirm_interval)
         all appear correctly, node --check on the correctly-last
         <script> block, the Flask route/def integrity check (still 44
         routes), a getElementById audit on the 2 new IDs (each defined
         once, referenced once), and unit tests: structural cap
         correctly keeping a LONG entry below a hand-built structural
         high and dropping one above it; lsw_scan_5m_confirmation()
         correctly detecting a hand-built BOS break and a hand-built
         absorption wick on synthetic 5m data; the full lsw_apply_
         entry_confirmation() pipeline producing a tighter SL and a
         correctly-recomputed TP at the same rr; and confirming a
         signal is correctly DROPPED (empty result) when scanned
         against flat 5m data with no confirmation pattern at all.

v0.99.123 - Optional per-direction live gating for LSW, per a direct
         user question prompted by their own screenshot of ETH_USDT's
         backtest split (L: 18.8% n=16 · S: 73.7% n=19) — asking
         whether trading only the stronger side per symbol was already
         implemented, and separately whether picking the winning side
         from the same backtest counts as overfitting.
         Answer given in-conversation (not just code): picking
         "whichever side backtested better" per symbol IS a mild form
         of overfitting at small n — by_direction naturally splits an
         already-modest sample roughly in half, so a gap like 18.8% vs
         73.7% at n=16/n=19 can easily be noise rather than a durable
         edge, unlike the HTF trend filter (v0.99.121), which has a
         causal reason for its direction bias independent of backtest
         outcome. Implemented as the more principled middle ground the
         user themselves suggested (a uniform winrate threshold applied
         per direction, not a post-hoc per-symbol pick): a symbol's
         LONG and SHORT are gated INDEPENDENTLY using the SAME LSW_
         LIVE_MIN_WINRATE threshold the overall per-symbol gate already
         uses, each requiring its own LSW_DIRECTION_MIN_SAMPLE (20,
         intentionally lower than the overall LSW_LIVE_MIN_SAMPLE=30
         since a per-direction split roughly halves the count). A
         symbol can end up LONG-only, SHORT-only, both, or (new,
         previously impossible) excluded from live trading entirely
         even though its COMBINED winrate passed the overall gate.
         Ran the exact numbers from the user's own screenshot through
         the new logic as a check: at the default 20-trade floor,
         ETH_USDT's n=16/n=19 split doesn't clear the sample bar on
         EITHER side yet — the filter would exclude ETH from live
         trading entirely (not silently trade the "winning" 73.7%
         side), which is the conservative behavior intended.
         Off by default (setLswDirectionFilter checkbox, labeled inline
         with an explicit "⚠️ мягкий подгон под прошлые данные" warning
         rather than presented as a strict improvement) — wired into
         lsw_backtest_loop() (computes STATE["lsw_live_directions"]
         per symbol only when the toggle is on) and lsw_scan_symbol_
         live() (filters that symbol's own signals down to only its
         allowed directions before picking the latest one). UI: the
         Sweep tab's backtest table now shows "(только LONG)" /
         "(только SHORT)" / "(обе стороны)" / "(ни одна сторона)" next
         to each live symbol when the filter is on, and /api/lsw/status
         exposes live_directions per symbol plus a new config.
         direction_filter_enabled field.
         Verified: py_compile, pyflakes clean, a real runtime start,
         node --check on the correctly-last <script> block, the Flask
         route/def integrity check (still 44 routes), a getElementById
         audit on the one new ID (setLswDirectionFilter, defined once,
         referenced once), and a unit test replaying the user's own
         ETH_USDT numbers (16 LONG trades/3 wins, 19 SHORT trades/14
         wins) through the actual gating logic, confirming both sides
         are correctly excluded at the default 20-trade floor, then
         confirming SHORT alone passes once its own sample is bumped
         past that floor with the same winrate.

v0.99.124 - CRITICAL FIX: a real open position could end up with a TP
         but genuinely NO stop-loss, per direct user report (screenshot:
         a real LSW LONG on CYS_USDT, autotrade_log showing status
         OPENED_TP_SL_FAILED — error 1029 AUTO_TRIGGER_PRICE_LESS_LAST,
         "Trigger.Price must < last_price" — on the SL leg specifically;
         the TP leg had succeeded).
         ROOT CAUSE: Gate's price_orders endpoint enforces trigger <
         last_price for a rule=2 order (LONG's own SL) and trigger >
         last_price for a rule=1 order (SHORT's own SL) AT THE EXACT
         MOMENT OF PLACEMENT. round_to_tick() rounds to the NEAREST
         tick — which can push a raw SL price that was correctly on the
         valid side of current price to the WRONG side by up to half a
         tick. On a coin with a wide tick size relative to price and a
         narrow stop distance (CYS_USDT, compounded by LSW's own
         deliberately tight LSW_SL_BUFFER_PCT, tighter still after 5m
         entry confirmation — see LSW_ENTRY_CONFIRM_ENABLED), that's
         enough to flip a valid SL into a rejected one.
         FIX 1: round_to_tick_directional(price, tick_size, round_up) —
         always rounds ONE direction (ceil or floor), never nearest.
         execute_autotrade() now rounds a LONG's TP up / SL down, a
         SHORT's TP down / SL up — the SL side is what actually matters
         for staying on the valid side of Gate's own constraint; the
         extra sub-tick distance this adds is a rounding artifact, not
         a real risk change, and is trivial next to the alternative (a
         real position left with no stop-loss at all). Also applied to
         move_stop_to_breakeven() — that function was passing its own
         breakeven_price completely UNROUNDED before this fix (tick was
         only ever used for decimal string FORMATTING there, never
         actually snapped to a tick multiple), the same latent bug,
         just never hit in practice yet.
         FIX 2, arguably the more important one: reconcile_positions_
         and_orders()'s own existing safety net — which alerts on a
         position with NO trigger orders at all — completely MISSED
         this exact incident, because CYS_USDT DID have an order (its
         TP), so it never counted as "unprotected" by that check's own
         definition. Added a second check: for each open position, look
         at its own trigger orders and its own direction, and flag one
         that has orders but NONE of them is actually acting as a stop-
         loss (rule=2 for a LONG, rule=1 for a SHORT). Unlike the first
         check, this doesn't just alert — find_open_signal_sl() recovers
         the position's own originally-intended SL price from whichever
         module's own OPEN signal record still has it (same signal-list
         set has_open_signal_any_module() already checks across), and a
         fresh placement is attempted immediately with the SAME
         directional-rounding fix from FIX 1. Telegram-alerts either way
         (✅ auto-healed / ⚠️ still failed, check manually), deduped the
         same way the existing unprotected-position alert already is.
         This runs on every reconcile pass — both the opportunistic one
         before each new trade AND the periodic one (RECONCILE_INTERVAL_
         SEC) — so an existing already-unprotected position (like the
         CYS_USDT one that prompted this) gets picked up and auto-healed
         on the very next cycle, not just future trades.
         Verified: py_compile, pyflakes clean (a full re-check after an
         accidental deletion of cancel_price_order() during editing was
         caught and fixed before this passed), a real runtime start, the
         Flask route/def integrity check (still 44 routes — no routes
         touched), and unit tests: round_to_tick_directional() against a
         hand-picked price/tick pair that reproduces the EXACT failure
         mode (plain round_to_tick() rounds a LONG's raw SL of 1.23455 UP
         to 1.235, which is >= a last_price of 1.2346 — Gate would reject
         that; the new directional round-down keeps it at 1.234, correctly
         below), confirming the fallback behavior with no tick_size is
         unchanged, and find_open_signal_sl() correctly recovering a
         planted OPEN LSW signal's own direction/sl and returning None
         for a symbol with no matching record.

v0.99.125 - Fixed the root cause behind one class of error-log entry,
         per direct user report (screenshot of the error log: "magnified
         profile FARTCOIN_USDT: ('Connection broken: IncompleteRead(12105
         bytes read, 78550 more expected)'...)" plus several unrelated
         "Read timed out" entries — "исправь причины ошибок").
         CONFIRMED root cause via requests' own exception hierarchy:
         "Connection broken: IncompleteRead" is requests.exceptions.
         ChunkedEncodingError's own message (a response that got cut off
         mid-stream) — and ChunkedEncodingError is a SIBLING of
         ConnectionError under RequestException, NOT a subclass of it.
         Every retry-on-network-error except clause in this file only
         ever caught (requests.exceptions.ConnectionError, requests.
         exceptions.Timeout) — meaning a ChunkedEncodingError always
         propagated on the very first occurrence with ZERO retries,
         unlike a plain dropped connection or timeout, which already got
         GET_CANDLES_RETRIES attempts. Confirmed live in the report: this
         specific error surfaced through build_profile_for_symbol()'s own
         already-graceful fallback (falls back to the same-timeframe
         approximate profile rather than failing the whole symbol), so
         it wasn't actually breaking anything that cycle — but it WAS a
         real, silent retry gap that would fail outright on any endpoint
         without such a fallback.
         Fix: a single new module-level RETRYABLE_NETWORK_EXCEPTIONS =
         (ConnectionError, Timeout, ChunkedEncodingError) tuple, and all
         6 of this file's own "except (ConnectionError, Timeout)" call
         sites — get_candles(), get_candles_range()'s own chunked-fetch
         loop, get_tickers(), the risk-limit-tiers pagination loop, the
         Telegram sender's own retry loop, and Volume's own network-error
         categorization branch — switched to catch this shared tuple
         instead of re-typing the pair by hand at each site (and missing
         ChunkedEncodingError at every single one of them, which is
         exactly what happened here). Any future call site that reuses
         this same name inherits the fix automatically instead of being
         able to reintroduce the same gap by hand-typing the pair again.
         The separate "Read timed out" entries in the same screenshot
         (NVDAX/BTR/DASH/ENA_USDT, all within about a minute) are read
         timeouts that DID already retry internally (get_candles() already
         gives every failing symbol GET_CANDLES_RETRIES=2 extra attempts,
         each with its own HTTP_TIMEOUT=15s) and still failed after
         exhausting that budget — consistent with a real, transient mobile-
         network congestion patch (the same reasoning WORKERS/GLOBAL_
         HTTP_SEMAPHORE/GLOBAL_MIN_REQUEST_INTERVAL were already tuned
         against in earlier versions), not a code gap; nothing further
         changed for that category, since it was already working as
         designed. Also confirmed the "reconcile_positions_and_orders:
         cancelled 1 orphaned trigger order(s)" entries in the same
         screenshot are NOT errors at all — they're reconcile_positions_
         and_orders()'s own normal, working-as-intended cleanup (see its
         own docstring's part (2)) logged via log_error() purely for
         visibility, which is why they show up in the same "Последние
         ошибки" list even though nothing is actually wrong.
         Verified: py_compile, pyflakes clean, a real runtime start, the
         Flask route/def integrity check (still 44 routes — no routes
         touched), and unit tests: confirmed requests.exceptions.
         ChunkedEncodingError is genuinely NOT a subclass of ConnectionError
         (the actual root cause, verified directly against the installed
         requests library, not assumed), then mocked requests.get() to
         raise ChunkedEncodingError on its first call and succeed on its
         second for both get_candles() and get_tickers(), confirming each
         now retries exactly once and returns the successful result
         instead of raising immediately — the exact behavior the pre-fix
         code was missing.
