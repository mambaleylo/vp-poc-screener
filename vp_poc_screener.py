#!/usr/bin/env python3
"""
VP-POC Screener
================
GitHub: github.com/mambaleylo/vp-poc-screener

Multi-module crypto signal screener/auto-trader (Volume Profile, Scalp,
FT5, MSNR, Mirror, LSW/Liquidity Sweep, and more) — Flask app, runs as
a local HTTP server served through a mobile browser. Data source:
Gate.io USDT-M futures public REST API; several modules can place real
orders via the Gate.io private API when their own autotrade toggle is
on (off by default everywhere).

Full version history has moved to CHANGELOG.md in this same repo
(moved out of this docstring in v0.99.122 — it had grown to ~10,470
lines). This header now only carries what stays true across versions;
check CHANGELOG.md for what changed and why.
"""

import os
import json
import time
import math
import threading
import traceback
import queue
import hmac
import hashlib
from decimal import Decimal
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# v0.99.125, per direct user report (screenshot: "magnified profile
# FARTCOIN_USDT: ('Connection broken: IncompleteRead(...)')" in the
# error log, from build_profile_for_symbol()'s own fallback path) —
# every retry-on-network-error except clause in this file only caught
# (requests.exceptions.ConnectionError, requests.exceptions.Timeout).
# CONFIRMED via requests' own exception hierarchy: ChunkedEncodingError
# — what "Connection broken: IncompleteRead" actually is, a response
# that got cut off mid-stream — is a SIBLING of ConnectionError under
# RequestException, NOT a subclass of it, so `except (ConnectionError,
# Timeout)` never catches it at all; it always propagated immediately
# with zero retries, unlike a plain dropped connection or a timeout,
# which already got GET_CANDLES_RETRIES attempts. A single shared tuple
# here (used at every one of this file's own retry-on-network-error
# call sites) closes that gap everywhere at once and keeps it closed if
# a new call site is added later using the same name rather than
# re-typing the pair by hand again.
RETRYABLE_NETWORK_EXCEPTIONS = (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                                 requests.exceptions.ChunkedEncodingError)
from flask import Flask, jsonify, request, Response

APP_VERSION = "0.99.156"

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
# v0.99.37 - CRITICAL FIX: WORKERS only ever capped concurrency WITHIN a
# single ThreadPoolExecutor — there are 13 separate ones across this app
# (scan, scalp, hourly stats, msnr backtest+live, ft5 backtest+live,
# mirror backtest+live, reconcile, risk autotune, telegram sender — was
# 14 including session/session_ny/xau_lg/vgi, all since removed),
# each running inside its OWN daemon-thread loop, with no shared budget
# between them. A live error-log screenshot showed 500 Internal Server
# Error from api.gateio.ws hitting every module at once across dozens of
# unrelated symbols, sustained for 20+ minutes straight — while a single
# ad-hoc GET to the exact same endpoint from a browser, at the same time,
# returned instantly with fresh, correct data. That rules out a genuine
# Gate.io-side outage (a real outage doesn't special-case which client
# sent the request) and points at this app's own AGGREGATE concurrent
# request volume: when several of those 14 pools happen to be mid-cycle
# at once (routine with 8+ independent background loops), total
# simultaneous connections to Gate.io can stack well past WORKERS=8 —
# plausibly 30-40+ at once — enough to trip Gate's anti-abuse layer into
# a blunt 500 instead of a polite, retryable 429. GET_CANDLES_RATE_LIMIT_
# RETRIES already retries 429 (and now 500 too, since the fix earlier
# this session) generously, but that budget assumes occasional bursts,
# not a sustained aggregate overload — retrying into the same overload
# just makes it worse.
# Fix: GLOBAL_HTTP_SEMAPHORE below caps TOTAL simultaneous Gate.io
# requests across the whole app, no matter how many of the 14 pools are
# active at once — each pool can still queue up to WORKERS threads
# locally, but only GLOBAL_MAX_CONCURRENT_REQUESTS of them actually have
# a request in flight at any moment; the rest block briefly on the
# semaphore instead of all firing at once.
GLOBAL_MAX_CONCURRENT_REQUESTS = int(os.environ.get("VP_GLOBAL_MAX_CONCURRENT_REQUESTS", 10))
GLOBAL_HTTP_SEMAPHORE = threading.Semaphore(GLOBAL_MAX_CONCURRENT_REQUESTS)

# v0.99.38 - CRITICAL FIX: per direct user report, 500s from api.gateio.ws
# STILL burst even with v0.99.37's GLOBAL_HTTP_SEMAPHORE in place and
# confirmed running. Root cause the semaphore didn't cover: it bounds how
# many requests are in flight AT ONCE, but says nothing about how FAST
# they fire back-to-back — 10 workers each immediately re-firing the
# instant their previous request completes can still sustain a high
# request RATE (potentially dozens/sec) even though concurrency never
# exceeds 10. Several of the 13 independent loops (msnr_backtest,
# ft5_backtest, mirror_backtest, etc.) having their intervals line up
# produces exactly this: a burst of rapid-fire requests, which is what a
# live error-log screenshot showed starting abruptly (a clean run of
# local /api/* calls, then a sudden run of Gate.io 500s the moment
# several backtest loops' cycles overlapped). Gate.io's anti-abuse layer
# most plausibly caps REQUEST RATE (requests/sec over a rolling window),
# not just concurrent connections — a limit the concurrency semaphore
# alone can't enforce.
# Fix: _global_rate_gate() adds a minimum spacing between the START of
# any two Gate.io requests, app-wide, on top of (not instead of) the
# existing concurrency cap — the two are complementary, not redundant:
# the semaphore bounds how many requests are open simultaneously, the
# rate gate bounds how often a new one is allowed to start regardless of
# how many are open. Together they cap both dimensions Gate's anti-abuse
# layer might be watching.
GLOBAL_MIN_REQUEST_INTERVAL = float(os.environ.get("VP_GLOBAL_MIN_REQUEST_INTERVAL", 0.12))  # seconds between successive Gate.io request STARTS, app-wide — caps sustained rate to roughly 1/this per second regardless of concurrency
_global_rate_lock = threading.Lock()
_global_last_request_started = [0.0]


def _global_rate_gate():
    """Blocks the calling thread until at least GLOBAL_MIN_REQUEST_
    INTERVAL seconds have passed since the last Gate.io request STARTED
    anywhere in the app. Deliberately holds the lock across the sleep —
    that's what makes the spacing global and strict (every caller
    queues up in true request order) rather than just an average that
    a burst could still momentarily violate."""
    with _global_rate_lock:
        now = time.time()
        wait = _global_last_request_started[0] + GLOBAL_MIN_REQUEST_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
            now = time.time()
        _global_last_request_started[0] = now
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
# v0.99.128 — network-instability alert, per direct user request
# ("Давай слать в телеграм увед при такой ошибке, когда сеть плохая и
# read time out") prompted by a real screenshot showing a sustained
# multi-hour patch of "Read timed out"/ConnectionError entries across
# many different functions (lsw_backtest, mirror_live, mirror_backtest,
# magnified profile, msnr_backtest_loop) — a genuinely different
# situation from one isolated blip (which every fetch function here
# already retries through on its own without needing an alert at all).
# This fires ONCE per sustained bad patch (NETWORK_ALERT_THRESHOLD
# network-flavored log_error() calls within NETWORK_ALERT_WINDOW_SEC),
# not per individual timeout — a single retried-through blip stays
# silent, only a real sustained patch (the kind that outlasts every
# function's own built-in retry budget) triggers this.
TELEGRAM_ALERTS_NETWORK = os.environ.get("VP_TG_ALERTS_NETWORK", "1") == "1"
NETWORK_ALERT_WINDOW_SEC = int(os.environ.get("VP_NETWORK_ALERT_WINDOW_SEC", 600))  # 10 min rolling window
NETWORK_ALERT_THRESHOLD = int(os.environ.get("VP_NETWORK_ALERT_THRESHOLD", 5))  # this many network-flavored errors inside the window before alerting
NETWORK_ALERT_COOLDOWN_SEC = int(os.environ.get("VP_NETWORK_ALERT_COOLDOWN_SEC", 1800))  # 30 min — don't re-alert more often than this even if the bad patch continues
TELEGRAM_ALERTS_HOURLY = os.environ.get("VP_TG_ALERTS_HOURLY", "1") == "1"
TELEGRAM_ALERTS_MSNR = os.environ.get("VP_TG_ALERTS_MSNR", "1") == "1"
TELEGRAM_ALERTS_FT5 = os.environ.get("VP_TG_ALERTS_FT5", "1") == "1"
HOURLY_STATS_ENABLED = os.environ.get("VP_HOURLY_STATS_ENABLED", "1") == "1"
HOURLY_STATS_INTERVAL_SEC = int(os.environ.get("VP_HOURLY_STATS_INTERVAL_SEC", 3600))



# ============================================================================
# EXPERIMENTAL: MSNR — Malaysian SNR / "Storyline" gold strategy (v0.99.0)
# ----------------------------------------------------------------------------
# Every name prefixed MSNR_/msnr_, same "findable and deletable" reasoning
# as XAU_LG. Source: the @xaubymedovyk Telegram channel + its "MSNR
# education by Medovyk" slide deck, screenshotted and forwarded by the user
# — cross-checked against the wider public "Malaysian SNR" material (this
# is an established, named retail methodology, not the channel author's own
# invention) to pin down what the slide-deck abbreviations actually mean.
# Translation from the (informal, screenshot-only) source material into a
# precise no-lookahead algorithm, as literally as the source allows:
#   - OCL (Open-Close Level): levels are built from a CLOSE-only line
#     chart, not wicks — msnr_detect_signals() pivots on `close`, never
#     high/low, for the structure timeframe.
#   - A-shape / V-shape: a confirmed pivot HIGH on that close-line is an
#     "A-shape" (origin/resistance-type OCL); a confirmed pivot LOW is a
#     "V-shape" (origin/support-type OCL) — named for the letter each
#     forms on the line chart. Only pivots whose leg from the previous
#     opposite pivot is at least MSNR_MIN_LEG_ATR x ATR count — this is
#     what the source calls an impulsive "Storyline" leg, as opposed to
#     ordinary chop, which the slides never treat as forming a real A/V.
#   - SBR / RBS (Support-Become-Resistance / Resistance-Become-Support):
#     the trade this module actually takes IS the SBR/RBS mechanism — a
#     confirmed A-shape (resistance-type) or V-shape (support-type) level
#     gets re-tested, and the entry is the rejection off it, i.e. "the
#     broken/former level now respected in the opposite role" is exactly
#     what the QM confirmation below fires on.
#   - QM (Quasimodo): the entry trigger, on a faster execution timeframe.
#     Price sweeps through the OCL level (wick beyond it) and then closes
#     back on the origin side within a short bar cluster — msnr_detect_
#     signals()'s inner loop, deliberately mirrored on detect_session_
#     manipulation()'s sweep-then-reject-cluster shape since it's the same
#     underlying pattern (liquidity grab + reversal confirmation).
#   - Storyline / target: the CURRENT opposite active OCL level (the other
#     side of the same A/V pair) is used as TP — this is what gives the
#     source's screenshots their very high R:R (10-24R examples), and is
#     structural rather than a fixed multiple: TP is wherever the paired
#     level actually is, not a fixed distance.
# Two-stage multi-timeframe cascade (MSNR_STRUCTURE_TF for the OCL/A/V
# levels, MSNR_ENTRY_TF for the QM trigger) rather than the source's full
# three/four-stage H1->M15->M5 waterfall shown in one forwarded screenshot
# — collapsed to two stages for a first, testable cut; can be extended to
# a third stage later if the two-stage version's own backtest looks worth
# refining further.
# Universe restricted to the same gold-tracking symbols as XAU_LG, per the
# channel being XAU-only.
# Status: UNVERIFIED, same as XAU_LG/FT5 were at their own introduction —
# this is a faithful translation of the source material, not a backtested-
# and-proven edge. Autotrade OFF by default (MSNR_ENABLED itself defaults
# ON, matching XAU_LG, since this module only shows signals/runs its own
# backtest unless autotrade is separately turned on).
# Constants placed here (before STATE) for the same reason as XAU_LG's —
# STATE references MSNR_SIGNAL_HISTORY at construction time.
# ============================================================================
MSNR_ENABLED = os.environ.get("VP_MSNR_ENABLED", "1") == "1"
MSNR_SYMBOLS = [s.strip() for s in os.environ.get("VP_MSNR_SYMBOLS", "XAU_USDT,XAUT_USDT,PAXG_USDT").split(",") if s.strip()]
MSNR_STRUCTURE_TF = os.environ.get("VP_MSNR_STRUCTURE_TF", "1h")  # timeframe the OCL / A-shape / V-shape "Storyline" levels are built on
MSNR_ENTRY_TF = os.environ.get("VP_MSNR_ENTRY_TF", "15m")  # v0.99.126 changed this to "1m" per the strategy author's own trade screenshot (the QM trigger is watched on M1 in the source material). v0.99.147 — reverted back to "15m", per direct user report that 1m caused a dramatic drop in backtest signal count: Gate's ~10000-candle recency floor caps 1m history to ~6.9 days (vs ~102 days at 15m), so MSNR_BACKTEST_DAYS=40 was silently giving only ~7 days of entry-TF history instead of 40, leaving most symbols with 5-7 signals instead of the expected dozens. At 15m the backtest covers the full 40 days again. Live signals are fractionally less precise (15m candle vs 1m) but the author's strategy note remains intact — a future improvement would be a separate live entry_tf, but that's a bigger change than warranted here.
MSNR_PIVOT_LEFT = int(os.environ.get("VP_MSNR_PIVOT_LEFT", 2))
MSNR_PIVOT_RIGHT = int(os.environ.get("VP_MSNR_PIVOT_RIGHT", 2))
MSNR_ATR_PERIOD = int(os.environ.get("VP_MSNR_ATR_PERIOD", 14))
MSNR_MIN_LEG_ATR = float(os.environ.get("VP_MSNR_MIN_LEG_ATR", 2.5))  # min impulsive-leg size (structure-TF ATR multiples) for a pivot to count as a real A-shape/V-shape rather than noise
MSNR_QM_ZONE_PCT = float(os.environ.get("VP_MSNR_QM_ZONE_PCT", 0.006))  # how close (as % of price) the sweep extreme must land to the OCL level to count as testing THAT level
MSNR_QM_LOOKBACK_BARS = int(os.environ.get("VP_MSNR_QM_LOOKBACK_BARS", 6))  # entry-TF bar cluster width the sweep and the close-back-inside confirmation are allowed to span, same idea as SESSION_MAX_THRUST_BARS
MSNR_VOLUME_LOOKBACK_BARS = int(os.environ.get("VP_MSNR_VOLUME_LOOKBACK_BARS", 20))  # v0.99.59, per direct user request ("второй фильтр" — the volume-confirmation candidate discussed alongside the time-of-day one, v0.99.56): how many entry-TF bars BEFORE the sweep/QM candle set that candle's own volume baseline (mean of that trailing window, excluding the signal candle itself). The QM/SNR pattern's whole premise is that a sweep-and-reclaim reflects REAL institutional order flow — a sweep on genuinely low relative volume is a plausible tell that it doesn't, same reasoning already used for the time-of-day filter. Separate constant from FT5_VOLUME_AVG_PERIOD (70) rather than reusing it — that's tuned for FT5's own strategy/timeframe, no reason to assume the same window suits MSNR's typically-shorter MSNR_ENTRY_TF.
# v0.99.141 — 2 new GLOBAL (uniform-threshold, manually toggled)
# filters, per direct user request after voicing a real concern about
# every existing MSNR filter above being auto-derived PER SYMBOL
# ("Просто под каждую монету как сейчас попахивает притянутостью,
# когда фильтр работает на всех монетах, тогда он хорош" — a filter
# that only "works" because it's individually re-tuned per coin proves
# less than one that holds up applied identically everywhere). Both
# off by default, same convention as every toggle in this file, and —
# unlike the per-symbol filters above — their own solo checkpoint is
# ALWAYS computed and appended to msnr_optimize_symbol()'s own
# filter_checkpoints chain regardless of whether the toggle is on, so
# the person can judge "what would this do" before enabling it, same
# principle Sweep's own optional filters already use.
MSNR_MIN_RR_FILTER_ENABLED = os.environ.get("VP_MSNR_MIN_RR_FILTER", "0") == "1"
MSNR_MIN_RR_FILTER = float(os.environ.get("VP_MSNR_MIN_RR_FILTER", 2.0))  # "a 1:2 minimum risk-to-reward filter is standard" — a UNIFORM floor, deliberately separate from msnr_symbol_rr_skip_min/max above (those derive a DIFFERENT per-symbol threshold from where THIS symbol's own trades statistically stop paying off, not a fixed global minimum)
MSNR_HTF_FILTER_ENABLED = os.environ.get("VP_MSNR_HTF_FILTER", "0") == "1"
MSNR_HTF_INTERVAL = os.environ.get("VP_MSNR_HTF_INTERVAL", "4h")
MSNR_HTF_EMA_PERIOD = int(os.environ.get("VP_MSNR_HTF_EMA_PERIOD", 50))
MSNR_HTF_TREND_BUFFER_PCT = float(os.environ.get("VP_MSNR_HTF_TREND_BUFFER_PCT", 0.1))
MSNR_SL_BUFFER_PCT = float(os.environ.get("VP_MSNR_SL_BUFFER_PCT", 0.0015))
MSNR_SL_BUFFER_MULT = float(os.environ.get("VP_MSNR_SL_BUFFER_MULT", 1.3))  # v0.99.104, per direct user report ("часто выбивает стоп и идёт куда надо цена"): the OLD sl_buffer_pct approach (extreme * (1 ± 0.15%)) barely widens the stop past the sweep's own extreme at all, regardless of how far that sweep actually moved — a live report of frequent premature stop-outs followed by the intended move happening anyway is the textbook symptom of a stop sitting too close to normal price noise/re-testing. Mirrors XAU_LG_SL_BUFFER_MULT's own SHAPE (see that constant's own comment): multiplies the RAW entry-to-sweep-extreme distance (already a real, price-action-derived risk measure) rather than adding a tiny fixed % on top of the bare extreme price — a stop that scales with how far the sweep itself moved, not a nudge that's nearly the same regardless. 1.3 is a starting default (30% wider than the raw sweep distance) — deliberately NOT wired into the global risk_autotune_pass() nudge system XAU_LG/SESSION/EMA/DIV use for their own SL multipliers: MSNR's own participation in that global system was disabled back in v0.99.52 in favor of its OWN, different tuning philosophy (msnr_symbol_sl_skip_min() and friends — per-symbol statistical significance tests, not a single global average-MAE nudge), and this stays consistent with that existing design rather than reintroducing the older mechanism just for this one constant. A static default, adjustable via the VP_MSNR_SL_BUFFER_MULT env var if real data suggests a different multiplier fits better.
MSNR_FALLBACK_RR = float(os.environ.get("VP_MSNR_FALLBACK_RR", 4.0))  # used only when the opposite OCL level isn't confirmed yet (Storyline has just one side so far) — a placeholder TP, not the normal path
# v0.99.126 — "add-on" (добір) second position, per the same direct
# user-forwarded trade screenshot as MSNR_ENTRY_TF's own comment above:
# "m1 QM + m30 fresh (добір)" — the source takes a SECOND position on
# the same idea when a fresh QM sweep+reject reappears on M30 against
# the SAME still-active level, sharing the primary trade's own target
# (the opposite h1 V/A-shape). This is genuinely "Две позиции по одной
# идее" (two positions on one idea) from a second forwarded post's own
# caption on a different trade, not a one-off.
# IMPORTANT — real autotrade wired in from the start, per direct user
# follow-up ("да нет, сразу делай с автоторговлей") after this app
# flagged the conflict with its own duplicate-position guard: Gate has
# no concept of two independent stacked positions on one contract in
# the same direction — a second same-direction order just MERGES into
# the existing position (blended average entry, combined size).
# execute_autotrade() gained a new allow_stack param specifically for
# this: proceeds past the duplicate-position check when the existing
# position is the SAME direction (a deliberate stack, not a
# conflicting duplicate) — see that param's own docstring. Which SL
# governs the merged position afterward (the primary's own already-
# live one, or the add-on's fresh one) had no answer in the source
# material either — per direct user decision when asked, the MORE
# CONSERVATIVE of the two (further from price) governs; see msnr_
# scan_addon_live()'s own docstring for the full mechanics (cancel-
# and-replace the primary's old SL trigger, TP left as a harmless
# duplicate at the same shared target price).
MSNR_ADDON_ENABLED = os.environ.get("VP_MSNR_ADDON_ENABLED", "0") == "1"  # off by default, same "opt-in once the person has seen it work" convention as every other toggle in this file — nothing about wiring real autotrade in changes that default
MSNR_ADDON_TF = os.environ.get("VP_MSNR_ADDON_TF", "30m")
MSNR_MAX_RR = float(os.environ.get("VP_MSNR_MAX_RR", 8.0))  # v0.99.11 — per direct user observation (SPCX: trades with rr>6 consistently hit stop, never TP) that a genuine opposite-level TP can sit SO far away the trade is structurally unlikely to ever reach it before reversing. When the real opposite level would produce rr > this cap, msnr_detect_signals() used to fall back to fallback_rr's fixed target instead. v0.99.52, per direct user question ("а проверка... таблица... что-то даёт вообще?" -> "уберём не работу"): the pooled-RR-bucket autotune this comment used to describe (risk_autotune_pass() calling _risk_autotune_msnr_max_rr() off msnr_rr_bucket_stats()) was DISABLED (commented out, not deleted) — this value stopped changing on its own. v0.99.68, per direct user request ("в оригинале... эта стратегия ловит движения с очень большим rr, даже если winrate около 20-30, у нас так не получается"): the cap ITSELF was removed from msnr_detect_signals() — it was silently substituting MSNR_FALLBACK_RR=4.0 for any genuinely-far opposite level, preventing exactly the large-RR/low-winrate trades the strategy is designed around, and keeping msnr_symbol_rr_skip_min()'s own per-symbol statistical filter blind to that entire RR range. This constant is now fully vestigial — nothing in signal generation reads it — left defined (still wired through settings/UI) only in case a future session wants to reintroduce a cap deliberately. The rr_buckets table itself still displays in the UI, informational only.
MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE = int(os.environ.get("VP_MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE", 15))  # v0.99.22 — per direct user request: MSNR_MAX_RR above is a single GLOBAL cap tuned off trades pooled across every symbol, which was a deliberate compromise (a single symbol's own sample is usually too small to bucket reliably) but leaves no way to catch a symbol whose OWN rr-vs-outcome pattern is bad even though the pooled average looks fine. This is the min closed-trade count a single symbol's OWN rr bucket (see msnr_rr_bucket_stats()) needs before msnr_symbol_rr_skip_min() trusts it enough to skip live signals in that range for that symbol specifically — see msnr_optimize_symbol()'s own "skip_rr_min" field and msnr_scan_symbol_live().
MSNR_BACKTEST_DAYS = int(os.environ.get("VP_MSNR_BACKTEST_DAYS", 40))  # v0.99.41 — was 30, raised per direct user request. Confirmed feasible against Gate's own ~10000-candle recency floor (get_candles_range()'s own docstring): at interval=15m that floor is ~102 days back, so 40 days (3840 candles) sits well inside it with room to spare — get_candles_range() already paginates in ~900-point/~9.4-day chunks regardless of the total span requested, so this just means ~5 chunks per symbol instead of ~4, not a new code path.
MSNR_SIGNAL_HISTORY = 200
MSNR_REFRESH_SEC = int(os.environ.get("VP_MSNR_REFRESH_SEC", 3600))
MSNR_SCAN_INTERVAL_SEC = int(os.environ.get("VP_MSNR_SCAN_INTERVAL_SEC", 300))
# v0.99.81, per direct user report ("термукс был жив, сигналы
# работали, но бэктест не выполнялся больше 5 часов"): investigation
# found no infinite-hang bug (every individual HTTP request/retry path
# in get_candles_range() is bounded — HTTP_TIMEOUT + a capped retry
# count either way), but also no ceiling on the CYCLE as a whole —
# worst-case arithmetic on every chunk of every symbol maxing out
# retries only reached ~1.8h, well short of the reported ~5h, so the
# actual mechanism (compounding delay under sustained bad network
# conditions, shared GLOBAL_HTTP_SEMAPHORE contention across this
# app's 14 other background loops, or something else not yet
# identified) is still genuinely unconfirmed. Per direct user choice
# ("Только диагностика... ничего не менять") this pass adds ONLY
# observability — msnr_backtest_watchdog() below — not a cycle-level
# timeout or any change to actual retry/wait behavior, so a repeat
# leaves a concrete log entry (which symbols were still in flight, how
# long the cycle had been running) instead of another silent multi-
# hour gap with nothing to diagnose from afterward.
MSNR_BACKTEST_WATCHDOG_INTERVAL_SEC = int(os.environ.get("VP_MSNR_BACKTEST_WATCHDOG_INTERVAL_SEC", 300))  # how often the watchdog checks in — 5 min, frequent enough to catch the problem developing without being noisy
MSNR_BACKTEST_WATCHDOG_THRESHOLD_SEC = int(os.environ.get("VP_MSNR_BACKTEST_WATCHDOG_THRESHOLD_SEC", 1200))  # 20 min — comfortably above the ~6-9 min this app's own logs have shown a normal full-universe cycle taking, so this doesn't fire on ordinary variance, only on a cycle that's genuinely running long
# Autotune (v0.99.5), per direct user request — same grid-search +
# confidence-bound-scoring shape as FT5's ft5_optimize_symbol()/
# ft5_ranking_score(), adapted from "% pnl" to "R multiple" since MSNR
# trades don't have a fixed stoploss %: each trade's reward is whatever
# the paired opposite OCL level happens to be, so results are compared
# in R (risk-normalized) rather than raw price % — a trade's OWN rr on
# a win, -1R on a loss (structural: the position is sized to lose
# exactly 1R at the stop by construction), TIMEOUTs excluded (no real
# outcome to score). Grid covers the 3 params most likely to move
# results: how big an impulse counts as a real A/V leg, how close price
# must get to "be testing" a level, and how many bars the QM sweep+
# reject cluster can span. Left MSNR_STRUCTURE_TF/MSNR_ENTRY_TF and
# MSNR_SL_BUFFER_PCT out of the grid — changing timeframes means
# re-fetching different candles per combo (expensive), and the SL
# buffer only nudges risk size, not the actual mechanism being tested.
MSNR_PARAM_GRID_MIN_LEG_ATR = [1.5, 2.5, 3.5]
MSNR_PARAM_GRID_QM_ZONE_PCT = [0.003, 0.006, 0.010]
MSNR_PARAM_GRID_QM_LOOKBACK = [4, 6, 9]
MSNR_MIN_BACKTEST_TRADES = int(os.environ.get("VP_MSNR_MIN_BACKTEST_TRADES", 5))  # same bar as FT5_MIN_BACKTEST_TRADES/Volume's MIN_BACKTEST_TRADES — a combo with fewer trades in the window isn't a confident pick
MSNR_RANK_PRIOR_TARGET = 1  # same role as FT5_RANK_PRIOR_TARGET — only a combo with 0 or 1 REAL observed loss gets synthetic -1R pseudo-losses blended in (guards against a small all-win sample looking falsely certain); 2+ real losses are trusted as-is
MSNR_BACKTEST_UNIVERSE_SIZE = int(os.environ.get("VP_MSNR_BACKTEST_UNIVERSE_SIZE", 70))  # v0.99.9 — per direct user request: backtest the top-N most liquid symbols too (union'd with MSNR_SYMBOLS, so gold stays included), to see whether this signal logic generalizes beyond gold — explicitly backtest-only for now, msnr_live_loop still scans only MSNR_SYMBOLS, unchanged. Lowered 30->10 in v0.99.14 when the cycle was stuck "ещё не завершился" for a long time under sustained Gate.io rate-limiting; raised back up to 70 in v0.99.16 per direct follow-up request, now that get_candles_range() ALSO retries on 429 (v0.99.15 — it previously had its own separate, unretried request loop) and the panel shows live per-symbol progress instead of a binary done/not-done, so a longer cycle is at least visibly progressing rather than looking stuck. v0.99.48 — msnr_build_backtest_universe() no longer applies this cap on top of MIN_VOL_USD (per direct user request: liquidity rank was silently gating which symbols the top-10 SCORE ranking could even consider, unrelated to signal quality) — left defined, unused by default, in case a future session wants to reintroduce a cap deliberately.
MSNR_LIVE_PROMOTE_MIN_WINRATE = float(os.environ.get("VP_MSNR_LIVE_PROMOTE_MIN_WINRATE", 50.0))  # v0.99.17 — per direct user request: a backtest-only symbol (from the wider MSNR_BACKTEST_UNIVERSE_SIZE exploration set) gets promoted into LIVE scanning once its winning combo's own closed-trade win-rate clears this bar. Union'd with MSNR_SYMBOLS (gold), never replaces it — gold stays live regardless of its own backtest numbers. v0.99.78, per direct user request ("Убери эту квалификацию... что раз просил убрать это"): the promotion rule this fed (msnr_compute_live_universe()) was retired — it now just delegates to the top-10 ranking instead. No longer read anywhere; left defined only as history/in case a future session wants a standalone promotion rule again.
MSNR_LIVE_PROMOTE_MIN_SAMPLE = int(os.environ.get("VP_MSNR_LIVE_PROMOTE_MIN_SAMPLE", 40))  # v0.99.17 — closed trades (wins+losses, NOT the raw "trades" count which also includes timeouts that say nothing about win-rate) needed before a symbol's win-rate is trusted enough to promote it to live scanning. v0.99.78 — same retirement as MSNR_LIVE_PROMOTE_MIN_WINRATE above, no longer read anywhere.
# v0.99.39 — per direct user request: the top-10 autotrade ranking
# (msnr_rank_by_winrate_sample()) now uses its OWN sample floor and its
# own sort key, deliberately separate from MSNR_LIVE_PROMOTE_MIN_SAMPLE/
# MSNR_LIVE_PROMOTE_MIN_WINRATE above (which still gate what's scanned
# live at all, unchanged) — "выборка от 35 сигналов и наибольший средний
# RR", i.e. 35 closed trades minimum, ranked by avg_rr DESC instead of
# the previous lower-confidence-bound score.
MSNR_AUTOTRADE_TOP_MIN_SAMPLE = int(os.environ.get("VP_MSNR_AUTOTRADE_TOP_MIN_SAMPLE", 35))  # closed trades (wins+losses) needed before a symbol is eligible for the top-10 autotrade ranking
# v0.99.44 - per direct user follow-up to v0.99.43's switch to a pure
# compound_return_pct sort ("только вот топ 10 стал хуже по доходу"):
# ranking purely by compound_return_pct backfired because the grid-
# search combo msnr_optimize_symbol() picks for each symbol is STILL
# chosen by `score` (the statistical lower-confidence-bound on mean R),
# never by income — so sorting the FINAL ranking by compound_return_pct
# only re-ranks each symbol's already-fixed, score-optimal combo's
# incidental $ outcome, not that symbol's actual best-achievable income
# across its 27 combos. A pure-income sort is also inherently noisy on
# its own: "va-bank" full-reinvestment compounding is extremely
# sensitive to trade ORDER/luck, not a stable measure of edge quality —
# which is exactly why `score` (msnr_ranking_score(), a lower-
# confidence-bound) existed in the first place, to guard against a
# lucky small sample. Neither metric alone is right: avg_rr/score alone
# ignore win-rate/actual $ outcome (the original v0.99.43 complaint);
# compound_return_pct alone is too noise-prone and mismatched from
# combo selection (this complaint). Fix: MSNR_TOP10_INCOME_WEIGHT blends
# both, min-max normalized across the current candidate set, weighted
# toward income per "больше веса надо для дохода" — NOT a 100% switch,
# a WEIGHTED one, matching the literal request.
MSNR_TOP10_INCOME_WEIGHT = float(os.environ.get("VP_MSNR_TOP10_INCOME_WEIGHT", 0.7))  # 0..1 — weight given to compound_return_pct in the top-10 ranking composite; the remainder (1 - this) goes to `score`. v0.99.76 — no longer read anywhere (see msnr_symbol_rank_score()'s own weights below); left defined only as history, not deleted.
# v0.99.76, per direct user follow-up to v0.99.75 ("Так для того я и
# написал 3 параметра, чтобы на выборку и доход тоже учитывало"):
# v0.99.75's plain lexicographic (winrate, raw_closed_n, доход) tuple
# checked winrate FIRST and only consulted the other two on an exact
# tie — which almost never happens with continuous values, so in
# practice it was ranking by winrate ALONE, not "all three factors."
# That wasn't what was meant: all three should genuinely pull the
# ranking — see msnr_symbol_rank_score()'s own docstring for the
# normalized-weighted-geometric-mean design this replaced it with.
# v0.99.80 — CRITICAL FIX to that same design, per direct user report
# with a live example (a symbol at 2% доход over 52 trades still
# scoring ~0.49, nearly half of the maximum possible, well into top-10
# territory): descending weights (0.5/0.3/0.2, v0.99.76-79) don't
# actually deliver "all three must be good" under a weighted GEOMETRIC
# mean — raising a normalized value x∈[0,1] to a SMALL exponent w
# COMPRESSES it toward 1 regardless of how bad x is (0.061^0.2≈0.57,
# nowhere near 0), so a low-weighted factor's badness barely drags the
# composite down. A weight in a geometric mean controls BOTH "how much
# a good value on this factor helps" AND "how much a bad value hurts"
# — they can't be tuned independently, so "доход matters least" and
# "доход must still be good" were mathematically in tension the whole
# time. Per direct user choice ("Равные веса — настоящее «all must be
# good», без приоритета") over adding a separate hard floor on доход:
# equal weights remove that tension entirely — every factor now
# punishes/rewards identically, restoring genuine "all three must be
# good" at the cost of the descending-priority ordering v0.99.76 had
# tried to express through weight alone.
MSNR_RANK_WINRATE_WEIGHT = float(os.environ.get("VP_MSNR_RANK_WINRATE_WEIGHT", 1.0 / 3))
MSNR_RANK_SAMPLE_WEIGHT = float(os.environ.get("VP_MSNR_RANK_SAMPLE_WEIGHT", 1.0 / 3))
MSNR_RANK_INCOME_WEIGHT = float(os.environ.get("VP_MSNR_RANK_INCOME_WEIGHT", 1.0 / 3))
MSNR_RANK_INCOME_WINSORIZE_PCT = float(os.environ.get("VP_MSNR_RANK_INCOME_WINSORIZE_PCT", 0.9))  # v0.99.94 — see msnr_compute_rank_bounds()'s own docstring: caps the pool-wide income normalization ceiling at this percentile so one symbol's compounding outlier can't distort every other symbol's normalized score
# v0.99.40 - CRITICAL FIX, per direct user report: "жму очистить msnr и
# заново бэктэст не запускается, час ждать что-ли". Root cause: msnr_
# backtest_loop() ends each cycle with a plain time.sleep(max(300,
# MSNR_REFRESH_SEC)) — MSNR_REFRESH_SEC defaults to 3600 (1 hour) — and
# api_reset_msnr() (the "Очистить MSNR" button) only clears STATE, it
# never touches that sleeping thread. So clicking the button mid-sleep
# genuinely does nothing but wipe the display until the hour-long timer
# happens to expire on its own — exactly the reported symptom, not a
# misunderstanding on the user's part.
# Fix: MSNR_BACKTEST_TRIGGER is a threading.Event the loop waits on
# INSTEAD of a plain sleep — .wait(timeout=...) still blocks for the
# same duration by default, but api_reset_msnr() can now call .set() to
# wake it immediately, and the loop clears the event right after so the
# next natural cycle goes back to waiting the full interval as before.
MSNR_BACKTEST_TRIGGER = threading.Event()
LSW_BACKTEST_TRIGGER = threading.Event()  # v0.99.137 — same "Очистить X doesn't wake the sleeping loop" fix as MSNR_BACKTEST_TRIGGER's own comment, applied to LSW ("Очистить Sweep"), per direct user report of the identical symptom
MSNR_AUTOTRADE_TOP_N = int(os.environ.get("VP_MSNR_AUTOTRADE_TOP_N", 10))  # v0.99.19 — how many non-gold symbols (by msnr_rank_by_winrate_sample()) get an individual autotrade toggle, on top of the always-eligible 3 gold ones. Raised 3->10 per direct follow-up request.

# ============================================================================
# EXPERIMENTAL: FT5 — port of freqtrade-strategies' Strategy005 (v0.96.0)
# ----------------------------------------------------------------------------
# Per direct user request ("сделай полную версию... фул версию") after
# researching freqtrade (github.com/freqtrade/freqtrade-strategies).
# Strategy005 (author: Gerald Lonlas) was the most-traded strategy in that
# repo's own published backtest table (180 trades) — but that backtest was
# run 2018-01-10 to 2018-01-30, a 20-day window during the post-2017-top
# crash, on whatever pairs/exchange were configured at the time. The repo's
# own README says outright: "results will heavily depend on the pairs,
# timeframe and timerange used... run your own backtests". The specific
# hyperopt-tuned parameter values (buy_rsi=26, buy_fishRsiNorma=5, etc.) are
# near-certainly overfit to that narrow, stale window — flagged to the user
# before building this, same treatment as the XAU Liquidity Grab source.
# This port keeps the STRUCTURE (which indicators, which conditions, the
# time-decaying ROI ladder) but re-derives its own parameters via a grid
# search against THIS app's own live Gate.io data (ft5_backtest_symbol()),
# the same "test on real data, don't trust the source's numbers" principle
# applied to XAU_LG. Prefixed FT5_/ft5_ throughout, same reasoning as
# XAU_LG_/xau_lg_ — easy to find and delete if it doesn't hold up.
# Deviations from the literal freqtrade source, made deliberately and
# documented rather than silently:
#   - Long-only, matching the original (short entries were never defined in
#     Strategy005 — it predates futures-style short support in freqtrade).
#   - The "close > 0.00000200" condition dropped — a stale-price sanity
#     floor from 2018-era sub-satoshi altcoins, meaningless on this app's
#     current gate.io futures universe.
#   - Sell trigger "sar-fisherRsi" compares fisher_rsi_norma (0-100 range)
#     against sell_fishRsiNorma, not the raw fisher_rsi (-1 to 1 range) the
#     original source code literally uses — that comparison in the
#     original can only ever be true in a razor-thin edge case (fisher_rsi
#     tops out at 1, sell_fishRsiNorma's own parameter range starts at 1),
#     which looks like a genuine bug in the upstream strategy (comparing
#     against the wrong variable), not a deliberate design choice. Not
#     replicated here.
# ============================================================================
FT5_ENABLED = os.environ.get("VP_FT5_ENABLED", "1") == "1"
FT5_TF = os.environ.get("VP_FT5_TF", "5m")  # matches Strategy005's own timeframe
FT5_UNIVERSE_SIZE = int(os.environ.get("VP_FT5_UNIVERSE_SIZE", 200))  # how many symbols get analyzed/optimized — wide net for finding what works
FT5_LIVE_TOP_N = int(os.environ.get("VP_FT5_LIVE_TOP_N", 10))  # how many of the analyzed symbols (ranked by the optimizer's own avg_pnl_pct) actually get scanned for live signals — per direct user request: analyze broadly, trade narrowly on the best performers only (raised 5->10 per a follow-up request)

FT5_BACKTEST_DAYS = int(os.environ.get("VP_FT5_BACKTEST_DAYS", 30))
FT5_SIGNAL_HISTORY = 200
FT5_REFRESH_SEC = int(os.environ.get("VP_FT5_REFRESH_SEC", 24 * 3600))  # daily backtest/param-search refresh, same cadence as Volume's optimizer
FT5_SCAN_INTERVAL_SEC = int(os.environ.get("VP_FT5_SCAN_INTERVAL_SEC", 300))

# MIRROR — "зеркальный уровень" (support/resistance polarity-flip)
# reversal strategy. Constants live here (not next to the module's own
# logic near the end of the file) for the same reason every other
# module's own constants do — see FT5_SIGNAL_HISTORY etc. just above:
# STATE's own construction below needs MIRROR_SIGNAL_HISTORY already
# defined, and Python evaluates top-level code strictly top-to-bottom.
MIRROR_ENABLED = os.environ.get("VP_MIRROR_ENABLED", "0") == "1"  # off by default, same reasoning as every other new module here — user opts in after seeing real backtest numbers
MIRROR_INTERVAL = os.environ.get("VP_MIRROR_INTERVAL", "1h")
MIRROR_PIVOT_LEFT = int(os.environ.get("VP_MIRROR_PIVOT_LEFT", 3))
MIRROR_PIVOT_RIGHT = int(os.environ.get("VP_MIRROR_PIVOT_RIGHT", 3))
MIRROR_LOOKBACK = int(os.environ.get("VP_MIRROR_LOOKBACK", 150))  # bars of history considered per backtest/live-scan pass
MIRROR_UNIVERSE_SIZE = int(os.environ.get("VP_MIRROR_UNIVERSE_SIZE", 60))  # capped, same reasoning as FT5's own — the per-symbol backtest cost adds up across a wide universe
MIRROR_TOUCH_TOLERANCE_PCT = float(os.environ.get("VP_MIRROR_TOUCH_TOLERANCE_PCT", 0.15))  # how close price must return to a broken level to count as "touching" it (as % of price)
MIRROR_PATTERN_TOLERANCE_PCT = float(os.environ.get("VP_MIRROR_PATTERN_TOLERANCE_PCT", 30.0))  # tweezers/rails matching-wick/body tolerance, as % of the larger of the two compared values
# v0.99.130 — per-symbol autotuning of the two tolerances above, per
# direct user question ("Может допуск касания и допуск паттерна можно
# менять?... или это уже дикая подгонка прям будет?") and follow-up
# decision to do it with real overfitting safeguards rather than a
# blind in-sample grid search. Deliberately NOT the same shape as
# mirror_symbol_sl_skip_min()/pattern_skip()/direction_skip() above —
# those already derive their own threshold straight from the SAME
# window they're then judged against (acceptable there because they're
# each a single, simple bucket-exclusion rule with a decent minimum
# sample of their own — see MIRROR_SYMBOL_SKIP_MIN_SAMPLE). A 2-
# dimensional grid search over the detector's own pattern-matching
# tolerance is a meaningfully bigger overfitting surface (more
# candidate combinations x more symbols = more chances one wins purely
# by luck on a finite sample), so this one is held to a stricter
# standard: mirror_autotune_tolerances() only ever picks a combo that
# clears its own minimum bar on an EARLIER slice of history AND, held
# out and never touched during selection, a LATER slice too (true
# walk-forward, not in-sample-only) — see that function's own
# docstring for the full split/validation mechanics. A symbol with no
# combo clearing BOTH slices keeps the plain module-wide defaults
# above, exactly as if autotuning were off for that symbol.
MIRROR_AUTOTUNE_TOLERANCE_ENABLED = os.environ.get("VP_MIRROR_AUTOTUNE_TOLERANCE", "0") == "1"
MIRROR_AUTOTUNE_TOUCH_GRID = tuple(float(x) for x in os.environ.get("VP_MIRROR_AUTOTUNE_TOUCH_GRID", "0.1,0.15,0.2,0.3").split(","))
MIRROR_AUTOTUNE_PATTERN_GRID = tuple(float(x) for x in os.environ.get("VP_MIRROR_AUTOTUNE_PATTERN_GRID", "20,30,40").split(","))
MIRROR_AUTOTUNE_TRAIN_FRACTION = float(os.environ.get("VP_MIRROR_AUTOTUNE_TRAIN_FRACTION", 0.7))  # earlier 70% of the backtest window used to pick candidates, later 30% used only to confirm — never the reverse, since the later slice is the one closer to "what live trading will actually see next"
MIRROR_AUTOTUNE_MIN_WINRATE = float(os.environ.get("VP_MIRROR_AUTOTUNE_MIN_WINRATE", 35.0))  # a combo must clear this on BOTH slices independently — deliberately below MIRROR_LIVE_MIN_WINRATE itself, since the real, stricter live gate still applies afterward on the combined result; this is just "is this combo worth using at all," not the final word
MIRROR_AUTOTUNE_MIN_TRAIN_SAMPLE = int(os.environ.get("VP_MIRROR_AUTOTUNE_MIN_TRAIN_SAMPLE", 25))
MIRROR_AUTOTUNE_MIN_TEST_SAMPLE = int(os.environ.get("VP_MIRROR_AUTOTUNE_MIN_TEST_SAMPLE", 12))
# v0.99.142 — 2 new GLOBAL (uniform-threshold, manually toggled) Mirror
# filters, per direct user request ("Давай переделаем тогда зеркало,
# придумай топ 2 фильтра и реализуем как в sweep") — same "works
# identically for every symbol" philosophy the MSNR ones (v0.99.141)
# already use, deliberately NOT another per-symbol auto-derived
# threshold like mirror_symbol_sl_skip_min/pattern_skip/direction_skip
# above. Both off by default.
MIRROR_VOLUME_FILTER_ENABLED = os.environ.get("VP_MIRROR_VOLUME_FILTER", "0") == "1"
MIRROR_VOLUME_FILTER_LOOKBACK = int(os.environ.get("VP_MIRROR_VOLUME_FILTER_LOOKBACK", 20))
MIRROR_VOLUME_FILTER_MULT = float(os.environ.get("VP_MIRROR_VOLUME_FILTER_MULT", 1.5))  # the pattern's own signal candle must show at least this many times the preceding-bars average volume — same "genuine reversal should show real participation" reasoning as LSW's own volume filter (v0.99.139)
MIRROR_HTF_FILTER_ENABLED = os.environ.get("VP_MIRROR_HTF_FILTER", "0") == "1"
MIRROR_HTF_INTERVAL = os.environ.get("VP_MIRROR_HTF_INTERVAL", "4h")
MIRROR_HTF_EMA_PERIOD = int(os.environ.get("VP_MIRROR_HTF_EMA_PERIOD", 50))
MIRROR_HTF_TREND_BUFFER_PCT = float(os.environ.get("VP_MIRROR_HTF_TREND_BUFFER_PCT", 0.1))
MIRROR_RR = float(os.environ.get("VP_MIRROR_RR", 3.0))  # fixed RR target — see mirror_detect_signals()'s own docstring for why a mechanical pipeline needs one despite the source trader's own discretionary exits
MIRROR_MAX_BARS_TO_RETURN = int(os.environ.get("VP_MIRROR_MAX_BARS_TO_RETURN", 60))  # a level broken this many bars ago without price returning to it goes stale and stops being watched
MIRROR_MAX_WAIT_BARS = int(os.environ.get("VP_MIRROR_MAX_WAIT_BARS", 200))  # v0.99.99, per direct user follow-up ("тайм аут тоже добавь"): shared by mirror_track_outcome() (backtest) and update_mirror_signal_outcomes() (live) so both sides use the SAME cutoff — was a hardcoded 200 in the backtest function only, with no live counterpart at all
MIRROR_SIGNAL_HISTORY = 300
MIRROR_BACKTEST_DAYS = int(os.environ.get("VP_MIRROR_BACKTEST_DAYS", 90))  # v0.99.98, per external code review batch 1 ("Окно бэктеста 40→90 дней"): 40 days produced too few trades per symbol (5-20) to trust winrate even with the min-sample gate above — widened to gather more evidence per symbol, same env-var-overridable pattern every other MIRROR_* constant already uses
MIRROR_REFRESH_SEC = int(os.environ.get("VP_MIRROR_REFRESH_SEC", 3600))
MIRROR_SCAN_INTERVAL_SEC = int(os.environ.get("VP_MIRROR_SCAN_INTERVAL_SEC", 300))
AUTOTRADE_ENABLED_MIRROR = os.environ.get("VP_AUTOTRADE_MIRROR", "0") == "1"
AUTOTRADE_LEVERAGE_MIRROR = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_MIRROR", 10))
TELEGRAM_ALERTS_MIRROR = os.environ.get("VP_TG_ALERTS_MIRROR", "1") == "1"
# v0.99.92, per direct user request ("придумай лучший фильтр для этого
# типа торговли... по статистике обязательно показывать до после как в
# msnr... В живых сигналах использовать только бэктестовые монеты с
# винрейтом более 35%"):
MIRROR_SYMBOL_SKIP_MIN_SAMPLE = 15  # same per-bucket significance bar MSNR's own filters use
MIRROR_LIVE_MIN_SAMPLE = int(os.environ.get("VP_MIRROR_LIVE_MIN_SAMPLE", 25))  # v0.99.111, per direct user report ("у virtual n 15 всего, но она торгуется в топе. Хотя бы от 80 сделать"): a SEPARATE, higher bar than MIRROR_SYMBOL_SKIP_MIN_SAMPLE above — that constant answers "is this one bucket/pattern/direction within a symbol's own backtest reliable enough to judge," this one answers a different question entirely: "is the symbol's OVERALL post-filter history long enough to trust for live trading at all." The two were conflated before this version (mirror_backtest_loop()'s own live-eligibility gate reused the 15-trade per-bucket bar as a whole-symbol floor too) — a symbol clearing just 15 total closed trades could read as, say, 100% winrate purely from a small, lucky sample and still get promoted to live trading exactly like a genuinely-tested 80+ trade symbol.
# v0.99.131 — lowered 80->25, per direct user request ("минималку по
# выборке убери совсем... до фильтров и так огромная выборка") and a
# follow-up compromise after this app pushed back: raw pre-filter
# sample size (~300 signals) doesn't make a small POST-filter sample
# more trustworthy — confidence comes from the final n actually being
# judged, not the size of the funnel it survived; if anything, a small
# survivor count out of a large raw pool is a bigger overfitting flag
# (the filter chain had more chances to land on a lucky-looking
# subset), not a smaller one. Asked directly whether to remove the
# floor entirely (n=1-2 could then qualify) or keep a small non-zero
# one — chose the latter (~20-30 range) specifically so a genuinely
# accidental 1-2 trade sample still can't reach live trading, while
# meaningfully loosening the previous 80-trade bar that was leaving
# every symbol shut out at once (v0.99.111's own original problem —
# n=15 mistakenly promoted — is still avoided at 25).
MIRROR_SL_PCT_BUCKETS = [(0, 1), (1, 2), (2, 4), (4, 7), (7, float("inf"))]
MIRROR_SL_PCT_BUCKET_SCHEMES = [
    MIRROR_SL_PCT_BUCKETS,
    [(0, 2), (2, 5), (5, float("inf"))],
    [(0, 3), (3, float("inf"))],
]  # finest -> coarsest cascade, same MSNR v0.99.89 lesson applied from the start here rather than shipping a fixed-only version first
MIRROR_LIVE_MIN_WINRATE = float(os.environ.get("VP_MIRROR_LIVE_MIN_WINRATE", 38.0))  # a symbol's OWN post-filter backtest winrate must clear this to be live-scanned at all — raised 35->40 (v0.99.113) per direct user request, then lowered 40->38 (v0.99.131), also per direct user request, alongside investigating (and confirming, not a bug) why many symbols show n=0 despite hundreds of raw signals: the SL-width/pattern/direction filter chain can legitimately eliminate 100% of a symbol's trades when its raw winrate is bad across virtually every SL-width bucket — the SL filter alone catches everything, leaving nothing for the later filters to work with

# LSW ("Liquidity Sweep") — equal-highs/equal-lows liquidity-grab
# reversal module. Constants live here for the same reason every other
# module's own constants do (STATE's own construction below needs
# LSW_SIGNAL_HISTORY already defined). Prefixed lsw_/LSW_ rather than
# sweep_/SWEEP_ deliberately — sweep_sim_trades() already exists in
# this file for an unrelated purpose (settling pending paper trades),
# so reusing that name would collide.
# v0.99.119 shipped this PAPER-ONLY, per direct user request at the
# time ("Сначала paper-симуляция, автоторговлю добавим потом").
# v0.99.120 wired real autotrade in (AUTOTRADE_ENABLED_LSW below), per
# direct follow-up request ("надо живые сигналы сделать и авто
# торговлю как и везде, тоже с риском 2%") — same execute_autotrade()/
# sim_execute_trade() pattern, same 2% base risk (AUTOTRADE_RISK_PCT_
# OF_BALANCE), every other module already uses. Off by default either way.
LSW_ENABLED = os.environ.get("VP_LSW_ENABLED", "0") == "1"  # off by default, same reasoning as every other new module here — user opts in after seeing real backtest numbers
LSW_INTERVAL = os.environ.get("VP_LSW_INTERVAL", "1h")
LSW_PIVOT_LEFT = int(os.environ.get("VP_LSW_PIVOT_LEFT", 3))
LSW_PIVOT_RIGHT = int(os.environ.get("VP_LSW_PIVOT_RIGHT", 3))
LSW_LOOKBACK = int(os.environ.get("VP_LSW_LOOKBACK", 150))  # bars of history considered per live-scan pass
LSW_UNIVERSE_SIZE = int(os.environ.get("VP_LSW_UNIVERSE_SIZE", 60))
LSW_EQUAL_TOLERANCE_PCT = float(os.environ.get("VP_LSW_EQUAL_TOLERANCE_PCT", 0.12))  # how close two swing highs (or two swing lows) must sit to count as the SAME resting-liquidity level, as % of price — this is what makes a level "equal highs/lows" rather than just one isolated swing
LSW_SL_BUFFER_PCT = float(os.environ.get("VP_LSW_SL_BUFFER_PCT", 0.15))  # stop placed this far BEYOND the sweep candle's own wick extreme, as % of price — a small buffer so the stop isn't sitting exactly on the exact wick tip
LSW_RR = float(os.environ.get("VP_LSW_RR", 2.5))  # fixed RR target — mechanical pipeline needs one, same reasoning as MIRROR_RR's own docstring
LSW_MAX_BARS_TO_SWEEP = int(os.environ.get("VP_LSW_MAX_BARS_TO_SWEEP", 150))  # a confirmed equal-highs/lows level not swept within this many bars goes stale and stops being watched
LSW_MAX_WAIT_BARS = int(os.environ.get("VP_LSW_MAX_WAIT_BARS", 200))  # same shared backtest/live TIMEOUT cutoff shape as MIRROR_MAX_WAIT_BARS
LSW_SIGNAL_HISTORY = 300
LSW_BACKTEST_DAYS = int(os.environ.get("VP_LSW_BACKTEST_DAYS", 90))
LSW_REFRESH_SEC = int(os.environ.get("VP_LSW_REFRESH_SEC", 3600))
LSW_SCAN_INTERVAL_SEC = int(os.environ.get("VP_LSW_SCAN_INTERVAL_SEC", 300))
LSW_LIVE_MIN_SAMPLE = int(os.environ.get("VP_LSW_LIVE_MIN_SAMPLE", 30))  # a symbol needs at least this many CLOSED backtest trades before its live signals are trusted — deliberately lower than MIRROR_LIVE_MIN_SAMPLE (80) since this is a brand-new module with far less accumulated real-world validation than MIRROR had by the time IT got autotrade wired; kept at 30 rather than raised to 80 on v0.99.120's autotrade wiring since the user didn't ask for that specific change — worth revisiting once real forward data accumulates
LSW_LIVE_MIN_WINRATE = float(os.environ.get("VP_LSW_LIVE_MIN_WINRATE", 50.0))  # raised 35->50, v0.99.138, per direct user request ("Подними порог для авто торговли 50% для монеты")
AUTOTRADE_ENABLED_LSW = os.environ.get("VP_AUTOTRADE_LSW", "0") == "1"  # v0.99.120, per direct user request ("надо живые сигналы сделать и авто торговлю как и везде, тоже с риском 2%") — off by default like every other module's own autotrade toggle, opt-in via settings
AUTOTRADE_LEVERAGE_LSW = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_LSW", 10))  # only used by sim_execute_trade()'s own separate paper-balance simulator (deliberately left on its own old leverage/size system, same as every other module) — execute_autotrade() itself computes real leverage automatically per-trade, same risk-based sizing every module shares (see execute_autotrade()'s own docstring)
TELEGRAM_ALERTS_LSW = os.environ.get("VP_TG_ALERTS_LSW", "1") == "1"
# v0.99.121 — higher-timeframe trend filter, per direct user request
# ("ещё пример того как должен торговаться sweep... сравни с нашей
# стратегией и доработай") pointing at a real ICT-style "AMD + FVG"
# setup note whose rule #1 is "только по тренду, дневка вверх и часовик
# восходящий моментум" (trade only WITH the higher-timeframe trend).
# Our detector already implements that note's rule #2/#5 (liquidity
# sweep = the entry trigger itself) — this adds the missing trend
# gate: a sweep of equal LOWS (-> LONG) only fires when the HTF trend
# is UP or NEUTRAL, a sweep of equal HIGHS (-> SHORT) only fires when
# it's DOWN or NEUTRAL — filtering out counter-trend fades, which this
# style of setup treats as materially lower-quality. Off by default,
# same "opt-in until the person has seen it work" convention as every
# other toggle in this file — the sample sizes for "did the filter
# actually help" barely exist yet for a module this new (see MIRROR's
# own v0.99.114 filtered-signal shadow-tracking precedent for why that
# question needs real data, not just intuition, before trusting it).
LSW_HTF_FILTER_ENABLED = os.environ.get("VP_LSW_HTF_FILTER", "0") == "1"
LSW_HTF_INTERVAL = os.environ.get("VP_LSW_HTF_INTERVAL", "4h")
LSW_HTF_EMA_PERIOD = int(os.environ.get("VP_LSW_HTF_EMA_PERIOD", 50))
LSW_HTF_TREND_BUFFER_PCT = float(os.environ.get("VP_LSW_HTF_TREND_BUFFER_PCT", 0.1))  # close must clear the EMA by this % to count as UP/DOWN rather than NEUTRAL — avoids flip-flopping right at the line
# v0.99.122 — the reference note's remaining two rules, per direct
# "Продолжи" follow-up to v0.99.121's own changelog entry (which had
# explicitly left these for later): rule #4 ("торгуем не выше
# структурного максимума") and rule #3 (5-minute entry confirmation
# via инверсия/BOS/поглощение). Both off by default, same convention.
LSW_STRUCTURAL_CAP_ENABLED = os.environ.get("VP_LSW_STRUCTURAL_CAP", "0") == "1"
LSW_STRUCTURAL_CAP_LOOKBACK = int(os.environ.get("VP_LSW_STRUCTURAL_CAP_LOOKBACK", 100))  # bars of LSW_INTERVAL history searched for the nearest significant structural pivot
LSW_STRUCTURAL_CAP_PIVOT_LEFT = int(os.environ.get("VP_LSW_STRUCTURAL_CAP_PIVOT_LEFT", 10))  # deliberately wider than LSW_PIVOT_LEFT/RIGHT (3/3) — a "structural" high/low is a bigger, more significant swing than the small pivots equal-highs/lows grouping uses
LSW_STRUCTURAL_CAP_PIVOT_RIGHT = int(os.environ.get("VP_LSW_STRUCTURAL_CAP_PIVOT_RIGHT", 10))
LSW_ENTRY_CONFIRM_ENABLED = os.environ.get("VP_LSW_ENTRY_CONFIRM", "0") == "1"
LSW_ENTRY_CONFIRM_INTERVAL = os.environ.get("VP_LSW_ENTRY_CONFIRM_INTERVAL", "5m")
LSW_ENTRY_CONFIRM_MAX_BARS = int(os.environ.get("VP_LSW_ENTRY_CONFIRM_MAX_BARS", 12))  # 12x5m = 1h — how long after the 1h sweep candle's own close to keep waiting for a 5m confirmation before giving up on the signal entirely
LSW_ENTRY_CONFIRM_PIVOT_LEFT = int(os.environ.get("VP_LSW_ENTRY_CONFIRM_PIVOT_LEFT", 2))
LSW_ENTRY_CONFIRM_PIVOT_RIGHT = int(os.environ.get("VP_LSW_ENTRY_CONFIRM_PIVOT_RIGHT", 2))
LSW_ENTRY_CONFIRM_WICK_RATIO = float(os.environ.get("VP_LSW_ENTRY_CONFIRM_WICK_RATIO", 0.6))  # how much of a 5m candle's own range its rejection wick + favorable close must cover to count as "поглощение" (absorption)
# v0.99.123 — per-direction live gating, per direct user question
# ("может при перевесе на бэктесте явно одной стороны... торговать
# только одно направление... или так неправильно делать и это
# подгон?"). Deliberately NOT "pick whichever side backtested better
# per symbol" — that's closer to overfitting on a small, noisy sample
# (the by_direction split roughly halves an already-small n). Instead:
# the SAME LSW_LIVE_MIN_WINRATE threshold already used for the overall
# per-symbol gate is applied to EACH direction independently, with its
# own (necessarily smaller) minimum sample — a uniform rule applied
# to every symbol/direction alike, not a per-symbol post-hoc pick.
# Off by default; when on, a symbol can end up LONG-only, SHORT-only,
# both, or excluded entirely, purely from whether each side clears the
# same bar everything else in this app already has to clear.
LSW_DIRECTION_FILTER_ENABLED = os.environ.get("VP_LSW_DIRECTION_FILTER", "0") == "1"
LSW_DIRECTION_MIN_SAMPLE = int(os.environ.get("VP_LSW_DIRECTION_MIN_SAMPLE", 20))  # smaller than LSW_LIVE_MIN_SAMPLE (30) since a per-direction split naturally has roughly half the sample of the combined count
# v0.99.139 — volume filter, per direct user request ("тогда
# структурный кэп, тренд фильтр можно убрать... давай решим какой,
# фильтр по объёму может?") replacing HTF trend/structural cap's own
# spot in the Sweep tab's solo-checkpoint table (their own toggles and
# detection code stay fully intact and usable — only their table
# columns are hidden, per the follow-up "убери из отображения в
# столбцах пока... добавим ещё один"). Real-world rationale: a genuine
# liquidity sweep (a real stop cascade getting absorbed) should show
# elevated volume on the sweep candle itself relative to recent bars —
# a low-volume wick that merely pokes past a level without real
# participation behind it is a weaker signal. Off by default, same
# convention as every other toggle here.
LSW_VOLUME_FILTER_ENABLED = os.environ.get("VP_LSW_VOLUME_FILTER", "0") == "1"
LSW_VOLUME_FILTER_LOOKBACK = int(os.environ.get("VP_LSW_VOLUME_FILTER_LOOKBACK", 20))  # bars of preceding volume averaged as the baseline
LSW_VOLUME_FILTER_MULT = float(os.environ.get("VP_LSW_VOLUME_FILTER_MULT", 1.5))  # the sweep candle's own volume must be at least this many times the preceding-bars average to count as a genuine, well-participated sweep
# v0.99.140 — 3 more optional filters, per direct user request after
# researching common liquidity-sweep confluence ideas ("Какой фильтр
# ещё придумать для sweep? Поищи в интернете мастхэвные варианты"):
# FVG (fair value gap) confirmation, a session/time-of-day filter, and
# a minimum equal-highs/lows touch count — all showed up repeatedly
# across independent sources searched, not just one blog's own opinion.
# All off by default, same convention as every toggle here.
LSW_FVG_FILTER_ENABLED = os.environ.get("VP_LSW_FVG_FILTER", "0") == "1"  # "always layer fair value gaps" / "wait for a pullback into the displacement candle's fair value gap" — repeated across multiple sources as the single most common confluence add-on for a bare liquidity sweep
LSW_SESSION_FILTER_ENABLED = os.environ.get("VP_LSW_SESSION_FILTER", "0") == "1"  # "skip sweeps in dead sessions; focus high-probability ones with volatility"
LSW_SESSION_START_HOUR_UTC = int(os.environ.get("VP_LSW_SESSION_START_HOUR_UTC", 7))  # ~European session open
LSW_SESSION_END_HOUR_UTC = int(os.environ.get("VP_LSW_SESSION_END_HOUR_UTC", 21))  # ~US session close — 07:00-21:00 UTC covers the European+US overlap, crypto's own usual higher-volume window, though this varies per symbol and is exactly why it's backtestable/toggleable rather than hardcoded
LSW_MIN_TOUCHES_ENABLED = os.environ.get("VP_LSW_MIN_TOUCHES_FILTER", "0") == "1"  # "the more touches, the higher the chance of a sweep" — the base detector already requires >=2 touches to call something an "equal highs/lows" level at all; this raises that bar further for symbols where more touches turns out to matter
LSW_MIN_TOUCHES = int(os.environ.get("VP_LSW_MIN_TOUCHES", 3))
# v0.99.149 — candle structure filter, per direct user request
# ("давай структуру свечи сделаем" after a discussion of which filters
# might genuinely help Sweep): a real stop-cascade / liquidity sweep
# should show a LARGE wick relative to a SMALL body on the sweep
# candle — a big wick means price was sharply rejected back inside the
# level, a big body means price actually closed far from the open
# (more of a trend/impulse move, not a rejection). Both the wick ratio
# and a minimum absolute wick size (relative to candle total range)
# are checked to avoid passing microscopic wicks that technically
# qualify by ratio but have no real structure. Off by default.
LSW_CANDLE_STRUCTURE_FILTER_ENABLED = os.environ.get("VP_LSW_CANDLE_STRUCTURE_FILTER", "0") == "1"
LSW_CANDLE_WICK_BODY_RATIO = float(os.environ.get("VP_LSW_CANDLE_WICK_BODY_RATIO", 2.0))  # sweep candle's directional wick must be at least this many times the body size
LSW_CANDLE_WICK_RANGE_MIN_PCT = float(os.environ.get("VP_LSW_CANDLE_WICK_RANGE_MIN_PCT", 0.3))  # the directional wick must cover at least this fraction of the candle's total high-low range (guards against ratio passing on near-doji candles with no real structure at all)
FT5_MIN_BACKTEST_TRADES = int(os.environ.get("VP_FT5_MIN_BACKTEST_TRADES", 5))  # a combo with fewer trades than this in the backtest window isn't a confident pick — same bar Volume's optimizer uses (MIN_BACKTEST_TRADES)
# v0.99.143 — 2 new GLOBAL (uniform-threshold) FT5 filters, per direct
# user request ("Тоже самое для msnr и ft5" — same architecture as
# MSNR/Mirror's own v0.99.141/142 pairs). FT5's own entry trigger
# already has a volume-spike REQUIREMENT baked directly into it
# (buy_volume_avg/buy_volume_mult, see ft5_run_backtest()'s own entry
# condition) — adding a separate volume filter here would be pure
# redundancy, so these are two DIFFERENT, genuinely new checks instead:
# an HTF trend filter (same shared lsw_htf_bias_at()/lsw_htf_bias_
# series() this app's other 3 modules already reuse) and a session/
# time-of-day filter (reusing lsw_filter_signals_by_session() directly
# — FT5's own trade dicts already use the same "entry_time" field name
# that function expects, no adapter needed). "1:2 minimum RR", the
# other MSNR/Mirror filter, doesn't map onto FT5 at all — it exits via
# a % stoploss + ROI ladder, not a fixed R-multiple target, so there's
# no "rr" field on an FT5 trade to filter by.
FT5_HTF_FILTER_ENABLED = os.environ.get("VP_FT5_HTF_FILTER", "0") == "1"
FT5_HTF_INTERVAL = os.environ.get("VP_FT5_HTF_INTERVAL", "4h")
FT5_HTF_EMA_PERIOD = int(os.environ.get("VP_FT5_HTF_EMA_PERIOD", 50))
FT5_HTF_TREND_BUFFER_PCT = float(os.environ.get("VP_FT5_HTF_TREND_BUFFER_PCT", 0.1))
FT5_SESSION_FILTER_ENABLED = os.environ.get("VP_FT5_SESSION_FILTER", "0") == "1"
FT5_SESSION_START_HOUR_UTC = int(os.environ.get("VP_FT5_SESSION_START_HOUR_UTC", 7))
FT5_SESSION_END_HOUR_UTC = int(os.environ.get("VP_FT5_SESSION_END_HOUR_UTC", 21))
FT5_RANK_PRIOR_TARGET = int(os.environ.get("VP_FT5_RANK_PRIOR_TARGET", 1))  # v0.98.8 — ft5_ranking_score() blends in max(0, TARGET - losses_count) pseudo-trades at the known -FT5_STOPLOSS_PCT level, so a small loss-free sample can't look artificially low-risk just because it hasn't hit its (structurally always-possible) stop yet. Tapered by ACTUAL real losses (not a flat count on every combo) — a flat prior tested worse, disproportionately hurting smaller-but-still-real samples. See ft5_ranking_score()'s own docstring for the full reasoning, including why TARGET=1 specifically. Replaces FT5_RANK_Z (v0.98.7), which is no longer referenced — the confidence multiplier is now t_critical(n-1), not a fixed Z.

# Fixed structural parameters (not grid-searched — kept at the original's
# own defaults, since re-deriving every one of Strategy005's 8 hyperopt
# dimensions would be its own combinatorial explosion; the grid search
# below focuses on the 3 parameters most likely to matter for entry
# selectivity, same "modest grid over the highest-impact dimensions"
# philosophy PARAM_GRID_RR/PARAM_GRID_LOOKBACK already use for Volume).
FT5_VOLUME_AVG_PERIOD = int(os.environ.get("VP_FT5_VOLUME_AVG_PERIOD", 70))
FT5_VOLUME_SPIKE_MULT = float(os.environ.get("VP_FT5_VOLUME_SPIKE_MULT", 4.0))
FT5_SMA_PERIOD = int(os.environ.get("VP_FT5_SMA_PERIOD", 40))
FT5_STOCH_K = int(os.environ.get("VP_FT5_STOCH_K", 5))
FT5_STOCH_D = int(os.environ.get("VP_FT5_STOCH_D", 3))
FT5_SELL_MINUS_DI = float(os.environ.get("VP_FT5_SELL_MINUS_DI", 4.0))
FT5_SELL_FISHER = float(os.environ.get("VP_FT5_SELL_FISHER", 30.0))  # compared against fisher_rsi_norma (0-100), see header comment on the corrected variable
FT5_STOPLOSS_PCT = float(os.environ.get("VP_FT5_STOPLOSS_PCT", 0.10))  # matches Strategy005's fixed -10% stoploss
FT5_INVERT_SIGNALS = os.environ.get("VP_FT5_INVERT_SIGNALS", "0") == "1"  # v0.98.10 — per direct user request for a reverse mode "по аналогии с другими индикаторами". Mirrors stoploss/ROI-ladder exactly (both pure %-of-entry rules); deliberately does NOT mirror the sell-signal exit (RSI/MACD/MinusDI/SAR) — see ft5_run_backtest()'s own docstring for why that can't be safely done with a mechanical sign flip.
FT5_ROI_LADDER = [(1440, 0.01), (80, 0.02), (40, 0.03), (20, 0.04), (0, 0.05)]  # (minutes_in_trade_at_least, min_profit_pct_required) — first entry (by descending minutes) whose time threshold is cleared applies; matches Strategy005's minimal_roi table exactly

# Grid-searched per symbol (FT5_PARAM_GRID_* + FT5_SYMBOL_OVERRIDES), same
# EV-based selection this file already uses for Volume (v0.95.6) — buy_rsi/
# buy_fisher/sell_rsi were the 3 parameters freqtrade's own hyperopt run
# actually varied the most across that stale 2018 backtest, so they're the
# most plausible candidates for "matters enough to re-search," not an
# arbitrary subset.
FT5_PARAM_GRID_BUY_RSI = [20, 26, 32, 40]
FT5_PARAM_GRID_BUY_FISHER = [5, 15, 30]
FT5_PARAM_GRID_SELL_RSI = [65, 74, 82]


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
AUTOTRADE_ENABLED_SCALP = os.environ.get("VP_AUTOTRADE_SCALP", "0") == "1"
AUTOTRADE_SIZE_MODE = os.environ.get("VP_AUTOTRADE_SIZE_MODE", "percent")  # "percent" or "fixed" — the single size value below is interpreted according to this
AUTOTRADE_SIZE_VALUE = float(os.environ.get("VP_AUTOTRADE_SIZE_VALUE", 2.0))  # percent: % of futures wallet balance; fixed: raw USD margin, leverage-independent either way
AUTOTRADE_RISK_PCT_OF_BALANCE = float(os.environ.get("VP_AUTOTRADE_RISK_PCT", 5.0))  # v0.99.102, per direct user request ("надо чтобы размер позиции только можно было выбрать"): % of TOTAL account equity risked per trade if SL hits — drives the now-auto-computed leverage, replacing every module's own fixed leverage constant. The user picks position SIZE (margin, via AUTOTRADE_SIZE_MODE/VALUE above, unchanged); leverage is derived per-trade from this risk target, this signal's own SL distance, and the chosen margin — no longer a manual choice at all. v0.99.145 — default raised 2.0->5.0 and made settings-editable, per direct user request ("Риск на сделку сделай 5% с выбором в настройках")
AUTOTRADE_EMERGENCY_SL_BUFFER_PCT = float(os.environ.get("VP_AUTOTRADE_EMERGENCY_SL_BUFFER_PCT", 0.3))  # v0.99.146, per direct user report (a signal fired after price had already moved past its own sl, opened anyway, the stop then failed to place, leaving a real position with nothing but liquidation as its actual stop) — when the SL leg of place_tp_sl_orders() fails on an already-open real position, ONE emergency retry is attempted at this % away from a freshly-fetched current price (not the original, now-invalid sl), per the user's own direct choice ("выставить маленький стоп если да" — a small protective stop, not an immediate market close)
SCALP_MARTINGALE_ENABLED = os.environ.get("VP_SCALP_MARTINGALE_ENABLED", "0") == "1"  # v0.99.109, per direct user request ("удвоение после стоплосса... классический мартингейл"): defaults OFF — a deliberate opt-in given the real, well-understood risk of exponentially escalating position size on a losing streak (a mathematically inevitable property of Martingale-style sizing, not a bug), not something that should silently activate for an existing account. See scalp_martingale_multiplier_for_symbol()'s own docstring for the full mechanics.
SCALP_MARTINGALE_MAX_DOUBLINGS = int(os.environ.get("VP_SCALP_MARTINGALE_MAX_DOUBLINGS", 3))  # v0.99.109 — the safety cap: after this many consecutive losses on a symbol, the risk multiplier (2^streak) stops growing and holds at 2^this value — per direct user choice of a count-based cap over a direct max-%-risk cap. Default 3 -> caps at 2^3=8x base risk (16% of balance at the default 2% base), a starting value, adjustable via the env var.
# Scalp gets its OWN size config, separate from the shared one above — per
# direct user request, by analogy with how leverage is already per-mode for
# bounce/breakout/divergence/ema/session. Defaults mirror AUTOTRADE_SIZE_MODE/
# VALUE at import time so an existing setup's scalp sizing doesn't silently
# change until the user actually customizes it via settings.
SCALP_SIZE_MODE = os.environ.get("VP_SCALP_SIZE_MODE", AUTOTRADE_SIZE_MODE)
SCALP_SIZE_VALUE = float(os.environ.get("VP_SCALP_SIZE_VALUE", AUTOTRADE_SIZE_VALUE))
AUTOTRADE_LEVERAGE_BOUNCE = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_BOUNCE", 10))
AUTOTRADE_LEVERAGE_BREAKOUT = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_BREAKOUT", 10))
AUTOTRADE_ENABLED_MSNR = os.environ.get("VP_AUTOTRADE_MSNR", "0") == "1"  # off by default — same "unverified source" treatment as XAU_LG/FT5
AUTOTRADE_LEVERAGE_MSNR = int(os.environ.get("VP_AUTOTRADE_LEVERAGE_MSNR", 10))
MSNR_COMPOUND_START_BALANCE = float(os.environ.get("VP_MSNR_COMPOUND_START_BALANCE", 40.0))  # v0.99.24 — per direct user request: $ margin the backtest's compounding simulation starts with on the first closed trade. Leverage for this simulation deliberately reuses AUTOTRADE_LEVERAGE_MSNR above (not a separate constant) so the simulated compounding always matches whatever leverage this symbol would actually be traded at live — see msnr_compound_return().
MSNR_LIVE_BALANCE_MAX = float(os.environ.get("VP_MSNR_LIVE_BALANCE_MAX", 500.0))  # v0.99.33 — per direct user request: hard ceiling on the REAL per-symbol compounding margin (see msnr_live_balance_for_symbol()) — a symbol's live-trading balance still starts at MSNR_COMPOUND_START_BALANCE and reinvests its own result every closed trade exactly like the backtest simulation, but never sizes a real order above this cap regardless of how far the compounding would otherwise have grown it.
MSNR_TARGET_STOP_LOSS_PCT = float(os.environ.get("VP_MSNR_TARGET_STOP_LOSS_PCT", 10.0))  # v0.99.46 — per direct user request, after a live SKHYNIX_USDT example: at the flat AUTOTRADE_LEVERAGE_MSNR (10x) on a tight sub-1%-wide stop, hitting SL barely dents the account (well under this %), wasting most of the position's real risk budget on a trade that can't move the needle either way. This is the target fraction of margin a stop-out should cost — msnr_leverage_for_stop() scales leverage UP (never down) from AUTOTRADE_LEVERAGE_MSNR for a signal whose own stop is narrower than what this target implies, capped by the contract's own exchange leverage_max and by the liquidation-safety margin.
AUTOTRADE_ENABLED_FT5 = os.environ.get("VP_AUTOTRADE_FT5", "0") == "1"  # off by default — same reasoning as XAU_LG: unverified source, and the freqtrade backtest table this was ported from is a near-certain overfitting example (20-day 2018 window)
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
SETTINGS_KEYS = ("volume_profile_enabled", "bounce_enabled", "breakout_enabled",
                  "scalp_enabled", "scalp_signals_enabled", "ft5_enabled", "ft5_invert_signals", "ft5_htf_filter_enabled", "ft5_session_filter_enabled", "msnr_enabled", "msnr_addon_enabled", "msnr_min_rr_filter_enabled", "msnr_htf_filter_enabled", "mirror_enabled", "mirror_autotune_tolerance_enabled", "mirror_volume_filter_enabled", "mirror_htf_filter_enabled", "lsw_enabled", "lsw_htf_filter_enabled", "lsw_structural_cap_enabled", "lsw_volume_filter_enabled", "lsw_fvg_filter_enabled", "lsw_session_filter_enabled", "lsw_min_touches_enabled", "lsw_candle_structure_filter_enabled", "lsw_entry_confirm_enabled", "lsw_direction_filter_enabled", "hourly_stats_enabled", "telegram_enabled",
                  "telegram_alerts_vp", "telegram_alerts_hourly", "telegram_alerts_ft5", "telegram_alerts_msnr", "telegram_alerts_mirror", "telegram_alerts_lsw", "telegram_alerts_network",
                  "autotrade_dry_run", "autotrade_bounce", "autotrade_breakout", "autotrade_scalp", "scalp_martingale_enabled", "autotrade_ft5", "autotrade_msnr", "autotrade_mirror", "autotrade_lsw",
                  "autotrade_risk_pct",
                  "mirror_rr", "mirror_touch_tolerance_pct", "mirror_pattern_tolerance_pct",
                  "lsw_rr", "lsw_equal_tolerance_pct",
                  # v0.93.0 — moved into the settings system specifically so
                  # auto_tune_pass() can persist adjustments to these via the
                  # same save_settings() path everything else already uses,
                  # rather than inventing a second, separate persistence
                  # mechanism just for auto-tuned values. Also fixes a real
                  # (if minor) pre-existing gap: before this, these three were
                  # plain module constants with NO persistence at all, so any
                  # manual env-var override would silently revert on restart
                  # too — now they follow the same rules as other autotune targets.
                  "scalp_min_rr", "scalp_sl_buffer_mult", "msnr_max_rr")


def get_settings():
    return {
        "volume_profile_enabled": VOLUME_PROFILE_ENABLED,
        "bounce_enabled": BOUNCE_ENABLED,
        "breakout_enabled": BREAKOUT_ENABLED,
        "scalp_enabled": SCALP_ENABLED,
        "scalp_signals_enabled": SCALP_SIGNALS_ENABLED,
        "ft5_enabled": FT5_ENABLED,
        "ft5_invert_signals": FT5_INVERT_SIGNALS,
        "ft5_htf_filter_enabled": FT5_HTF_FILTER_ENABLED,
        "ft5_session_filter_enabled": FT5_SESSION_FILTER_ENABLED,
        "mirror_enabled": MIRROR_ENABLED,
        "mirror_rr": MIRROR_RR,
        "mirror_touch_tolerance_pct": MIRROR_TOUCH_TOLERANCE_PCT,
        "mirror_pattern_tolerance_pct": MIRROR_PATTERN_TOLERANCE_PCT,
        "mirror_autotune_tolerance_enabled": MIRROR_AUTOTUNE_TOLERANCE_ENABLED,
        "mirror_volume_filter_enabled": MIRROR_VOLUME_FILTER_ENABLED,
        "mirror_htf_filter_enabled": MIRROR_HTF_FILTER_ENABLED,
        "lsw_enabled": LSW_ENABLED,
        "lsw_rr": LSW_RR,
        "lsw_equal_tolerance_pct": LSW_EQUAL_TOLERANCE_PCT,
        "lsw_htf_filter_enabled": LSW_HTF_FILTER_ENABLED,
        "lsw_structural_cap_enabled": LSW_STRUCTURAL_CAP_ENABLED,
        "lsw_volume_filter_enabled": LSW_VOLUME_FILTER_ENABLED,
        "lsw_fvg_filter_enabled": LSW_FVG_FILTER_ENABLED,
        "lsw_session_filter_enabled": LSW_SESSION_FILTER_ENABLED,
        "lsw_min_touches_enabled": LSW_MIN_TOUCHES_ENABLED,
        "lsw_candle_structure_filter_enabled": LSW_CANDLE_STRUCTURE_FILTER_ENABLED,
        "lsw_entry_confirm_enabled": LSW_ENTRY_CONFIRM_ENABLED,
        "lsw_direction_filter_enabled": LSW_DIRECTION_FILTER_ENABLED,
        "msnr_max_rr": MSNR_MAX_RR,
        "msnr_enabled": MSNR_ENABLED,
        "msnr_addon_enabled": MSNR_ADDON_ENABLED,
        "msnr_min_rr_filter_enabled": MSNR_MIN_RR_FILTER_ENABLED,
        "msnr_htf_filter_enabled": MSNR_HTF_FILTER_ENABLED,
        "hourly_stats_enabled": HOURLY_STATS_ENABLED,
        "telegram_enabled": TELEGRAM_ENABLED,
        "telegram_alerts_vp": TELEGRAM_ALERTS_VP,
        "telegram_alerts_hourly": TELEGRAM_ALERTS_HOURLY,
        "telegram_alerts_ft5": TELEGRAM_ALERTS_FT5,
        "telegram_alerts_msnr": TELEGRAM_ALERTS_MSNR,
        "telegram_alerts_mirror": TELEGRAM_ALERTS_MIRROR,
        "telegram_alerts_lsw": TELEGRAM_ALERTS_LSW,
        "telegram_alerts_network": TELEGRAM_ALERTS_NETWORK,
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "autotrade_dry_run": AUTOTRADE_DRY_RUN,
        "autotrade_risk_pct": AUTOTRADE_RISK_PCT_OF_BALANCE,
        "autotrade_bounce": AUTOTRADE_ENABLED_BOUNCE,
        "autotrade_breakout": AUTOTRADE_ENABLED_BREAKOUT,
        "autotrade_scalp": AUTOTRADE_ENABLED_SCALP,
        "scalp_martingale_enabled": SCALP_MARTINGALE_ENABLED,
        "autotrade_ft5": AUTOTRADE_ENABLED_FT5,
        "autotrade_msnr": AUTOTRADE_ENABLED_MSNR,
        "autotrade_mirror": AUTOTRADE_ENABLED_MIRROR,
        "autotrade_lsw": AUTOTRADE_ENABLED_LSW,
        "scalp_min_rr": SCALP_MIN_RR,
        "scalp_sl_buffer_mult": SCALP_SL_BUFFER_MULT,
    }



def apply_settings(updates):
    """Mutates the module-level flags directly — every place that checks
    them (scan_loop, scan_symbol, send_telegram, ...) reads the name at
    call time, not at import time, so this takes effect on the very next
    scan cycle / next alert, no restart needed."""
    global VOLUME_PROFILE_ENABLED, BOUNCE_ENABLED, BREAKOUT_ENABLED, SCALP_ENABLED, SCALP_SIGNALS_ENABLED, FT5_ENABLED, FT5_INVERT_SIGNALS, FT5_HTF_FILTER_ENABLED, FT5_SESSION_FILTER_ENABLED, MSNR_ENABLED, MSNR_MAX_RR, MSNR_ADDON_ENABLED, MSNR_MIN_RR_FILTER_ENABLED, MSNR_HTF_FILTER_ENABLED, HOURLY_STATS_ENABLED
    global MIRROR_ENABLED, MIRROR_RR, MIRROR_TOUCH_TOLERANCE_PCT, MIRROR_PATTERN_TOLERANCE_PCT, MIRROR_AUTOTUNE_TOLERANCE_ENABLED
    global MIRROR_VOLUME_FILTER_ENABLED, MIRROR_HTF_FILTER_ENABLED
    global LSW_ENABLED, LSW_RR, LSW_EQUAL_TOLERANCE_PCT, LSW_HTF_FILTER_ENABLED
    global LSW_STRUCTURAL_CAP_ENABLED, LSW_ENTRY_CONFIRM_ENABLED, LSW_DIRECTION_FILTER_ENABLED, LSW_VOLUME_FILTER_ENABLED
    global LSW_FVG_FILTER_ENABLED, LSW_SESSION_FILTER_ENABLED, LSW_MIN_TOUCHES_ENABLED, LSW_CANDLE_STRUCTURE_FILTER_ENABLED
    global TELEGRAM_ENABLED, TELEGRAM_ALERTS_VP, TELEGRAM_ALERTS_HOURLY
    global TELEGRAM_ALERTS_FT5, TELEGRAM_ALERTS_MSNR, TELEGRAM_ALERTS_MIRROR, TELEGRAM_ALERTS_LSW, TELEGRAM_ALERTS_NETWORK
    global AUTOTRADE_DRY_RUN, AUTOTRADE_ENABLED_BOUNCE, AUTOTRADE_ENABLED_BREAKOUT, AUTOTRADE_ENABLED_SCALP, AUTOTRADE_ENABLED_FT5, AUTOTRADE_ENABLED_MSNR, AUTOTRADE_ENABLED_MIRROR, AUTOTRADE_ENABLED_LSW, SCALP_MARTINGALE_ENABLED, AUTOTRADE_RISK_PCT_OF_BALANCE
    global SCALP_MIN_RR, SCALP_SL_BUFFER_MULT
    if "volume_profile_enabled" in updates:
        VOLUME_PROFILE_ENABLED = bool(updates["volume_profile_enabled"])
    if "bounce_enabled" in updates:
        BOUNCE_ENABLED = bool(updates["bounce_enabled"])
    if "breakout_enabled" in updates:
        BREAKOUT_ENABLED = bool(updates["breakout_enabled"])
    if "scalp_enabled" in updates:
        SCALP_ENABLED = bool(updates["scalp_enabled"])
    if "scalp_signals_enabled" in updates:
        SCALP_SIGNALS_ENABLED = bool(updates["scalp_signals_enabled"])
    if "ft5_enabled" in updates:
        FT5_ENABLED = bool(updates["ft5_enabled"])
    if "ft5_invert_signals" in updates:
        FT5_INVERT_SIGNALS = bool(updates["ft5_invert_signals"])
    if "ft5_htf_filter_enabled" in updates:
        FT5_HTF_FILTER_ENABLED = bool(updates["ft5_htf_filter_enabled"])
    if "ft5_session_filter_enabled" in updates:
        FT5_SESSION_FILTER_ENABLED = bool(updates["ft5_session_filter_enabled"])
    if "mirror_enabled" in updates:
        MIRROR_ENABLED = bool(updates["mirror_enabled"])
    if "mirror_rr" in updates:
        try:
            v = float(updates["mirror_rr"])
            if v > 0:
                MIRROR_RR = v
        except (TypeError, ValueError):
            pass
    if "mirror_touch_tolerance_pct" in updates:
        try:
            v = float(updates["mirror_touch_tolerance_pct"])
            if v >= 0:
                MIRROR_TOUCH_TOLERANCE_PCT = v
        except (TypeError, ValueError):
            pass
    if "mirror_pattern_tolerance_pct" in updates:
        try:
            v = float(updates["mirror_pattern_tolerance_pct"])
            if v >= 0:
                MIRROR_PATTERN_TOLERANCE_PCT = v
        except (TypeError, ValueError):
            pass
    if "mirror_autotune_tolerance_enabled" in updates:
        MIRROR_AUTOTUNE_TOLERANCE_ENABLED = bool(updates["mirror_autotune_tolerance_enabled"])
    if "mirror_volume_filter_enabled" in updates:
        MIRROR_VOLUME_FILTER_ENABLED = bool(updates["mirror_volume_filter_enabled"])
    if "mirror_htf_filter_enabled" in updates:
        MIRROR_HTF_FILTER_ENABLED = bool(updates["mirror_htf_filter_enabled"])
    if "lsw_enabled" in updates:
        LSW_ENABLED = bool(updates["lsw_enabled"])
    if "lsw_rr" in updates:
        try:
            v = float(updates["lsw_rr"])
            if v > 0:
                LSW_RR = v
        except (TypeError, ValueError):
            pass
    if "lsw_equal_tolerance_pct" in updates:
        try:
            v = float(updates["lsw_equal_tolerance_pct"])
            if v >= 0:
                LSW_EQUAL_TOLERANCE_PCT = v
        except (TypeError, ValueError):
            pass
    if "lsw_htf_filter_enabled" in updates:
        LSW_HTF_FILTER_ENABLED = bool(updates["lsw_htf_filter_enabled"])
    if "lsw_structural_cap_enabled" in updates:
        LSW_STRUCTURAL_CAP_ENABLED = bool(updates["lsw_structural_cap_enabled"])
    if "lsw_volume_filter_enabled" in updates:
        LSW_VOLUME_FILTER_ENABLED = bool(updates["lsw_volume_filter_enabled"])
    if "lsw_fvg_filter_enabled" in updates:
        LSW_FVG_FILTER_ENABLED = bool(updates["lsw_fvg_filter_enabled"])
    if "lsw_session_filter_enabled" in updates:
        LSW_SESSION_FILTER_ENABLED = bool(updates["lsw_session_filter_enabled"])
    if "lsw_min_touches_enabled" in updates:
        LSW_MIN_TOUCHES_ENABLED = bool(updates["lsw_min_touches_enabled"])
    if "lsw_candle_structure_filter_enabled" in updates:
        LSW_CANDLE_STRUCTURE_FILTER_ENABLED = bool(updates["lsw_candle_structure_filter_enabled"])
    if "lsw_entry_confirm_enabled" in updates:
        LSW_ENTRY_CONFIRM_ENABLED = bool(updates["lsw_entry_confirm_enabled"])
    if "lsw_direction_filter_enabled" in updates:
        LSW_DIRECTION_FILTER_ENABLED = bool(updates["lsw_direction_filter_enabled"])
    if "msnr_enabled" in updates:
        MSNR_ENABLED = bool(updates["msnr_enabled"])
    if "msnr_addon_enabled" in updates:
        MSNR_ADDON_ENABLED = bool(updates["msnr_addon_enabled"])
    if "msnr_min_rr_filter_enabled" in updates:
        MSNR_MIN_RR_FILTER_ENABLED = bool(updates["msnr_min_rr_filter_enabled"])
    if "msnr_htf_filter_enabled" in updates:
        MSNR_HTF_FILTER_ENABLED = bool(updates["msnr_htf_filter_enabled"])
    if "msnr_max_rr" in updates:
        try:
            v = float(updates["msnr_max_rr"])
            if v > 0:
                MSNR_MAX_RR = v
        except (TypeError, ValueError):
            pass
    if "hourly_stats_enabled" in updates:
        HOURLY_STATS_ENABLED = bool(updates["hourly_stats_enabled"])
    if "telegram_enabled" in updates:
        TELEGRAM_ENABLED = bool(updates["telegram_enabled"])
    if "telegram_alerts_vp" in updates:
        TELEGRAM_ALERTS_VP = bool(updates["telegram_alerts_vp"])
    if "telegram_alerts_ft5" in updates:
        TELEGRAM_ALERTS_FT5 = bool(updates["telegram_alerts_ft5"])
    if "telegram_alerts_msnr" in updates:
        TELEGRAM_ALERTS_MSNR = bool(updates["telegram_alerts_msnr"])
    if "telegram_alerts_mirror" in updates:
        TELEGRAM_ALERTS_MIRROR = bool(updates["telegram_alerts_mirror"])
    if "telegram_alerts_lsw" in updates:
        TELEGRAM_ALERTS_LSW = bool(updates["telegram_alerts_lsw"])
    if "telegram_alerts_network" in updates:
        TELEGRAM_ALERTS_NETWORK = bool(updates["telegram_alerts_network"])
    if "autotrade_dry_run" in updates:
        AUTOTRADE_DRY_RUN = bool(updates["autotrade_dry_run"])
    if "autotrade_risk_pct" in updates:
        try:
            v = float(updates["autotrade_risk_pct"])
            if v > 0:
                AUTOTRADE_RISK_PCT_OF_BALANCE = v
        except (TypeError, ValueError):
            pass
    if "autotrade_bounce" in updates:
        AUTOTRADE_ENABLED_BOUNCE = bool(updates["autotrade_bounce"])
    if "autotrade_breakout" in updates:
        AUTOTRADE_ENABLED_BREAKOUT = bool(updates["autotrade_breakout"])
    if "autotrade_scalp" in updates:
        AUTOTRADE_ENABLED_SCALP = bool(updates["autotrade_scalp"])
    if "scalp_martingale_enabled" in updates:
        SCALP_MARTINGALE_ENABLED = bool(updates["scalp_martingale_enabled"])
    if "autotrade_ft5" in updates:
        AUTOTRADE_ENABLED_FT5 = bool(updates["autotrade_ft5"])
    if "autotrade_msnr" in updates:
        AUTOTRADE_ENABLED_MSNR = bool(updates["autotrade_msnr"])
    if "autotrade_mirror" in updates:
        AUTOTRADE_ENABLED_MIRROR = bool(updates["autotrade_mirror"])
    if "autotrade_lsw" in updates:
        AUTOTRADE_ENABLED_LSW = bool(updates["autotrade_lsw"])
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


def gate_signed_request(method, url_path, query_string="", body=None, timeout=HTTP_TIMEOUT, retry_on_timeout=False):
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
    full_url_path = "/api/v4" + url_path
    url = f"{GATE_BASE_HOST}{full_url_path}"
    if query_string:
        url += f"?{query_string}"
    # v0.99.112, per direct user report (screenshot: "HTTPSConnectionPool
    # (host='api.gateio.ws', port=443): Read timed out. (read timeout=15)"
    # during a real LONG autotrade attempt, 9 such errors in the log) —
    # this function previously had NO retry at all; a single transient
    # timeout anywhere in execute_autotrade()'s own multi-call flow
    # aborted the whole thing straight to a bare ERROR, wasting a
    # genuinely good signal. retry_on_timeout defaults to False (keeps
    # every existing caller's behavior unchanged) — only READ-ONLY or
    # genuinely IDEMPOTENT calls should ever opt into it. Deliberately
    # NOT applied to order placement: if a timeout happens AFTER Gate's
    # server already processed the order but BEFORE the response
    # reached this client, blindly resending would place a SECOND,
    # duplicate order — a much worse outcome than one wasted signal.
    # Each retry attempt regenerates the timestamp/signature from
    # scratch (not just resending the same signed payload) — Gate's own
    # signature scheme has a timestamp tolerance window, and reusing a
    # timestamp from a request that already waited out a full timeout
    # once risks the retry itself being rejected as stale.
    attempts = 3 if retry_on_timeout else 1
    last_timeout_error = None
    for attempt in range(attempts):
        ts = str(time.time())
        sign_string = f"{method}\n{full_url_path}\n{query_string}\n{hashed_payload}\n{ts}"
        sign = hmac.new(GATE_API_SECRET.encode("utf-8"), sign_string.encode("utf-8"), hashlib.sha512).hexdigest()
        headers = {
            "KEY": GATE_API_KEY, "Timestamp": ts, "SIGN": sign,
            "Accept": "application/json", "Content-Type": "application/json",
        }
        try:
            r = requests.request(method, url, headers=headers, data=payload_str if body is not None else None, timeout=timeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_timeout_error = e
            if attempt < attempts - 1:
                time.sleep(1)
                continue
            raise
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
    raise last_timeout_error


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
    "last_scan_started": None,
    "last_scan_finished": None,
    "last_scan_duration": None,
    "errors": deque(maxlen=30),
    # Скальпинг — pure stats, not a signal source: universe + per-symbol
    # excursion data + the computed recommendation for each, refreshed on
    # its own slow SCALP_REFRESH_SEC cadence, separate from the main loop.
    "scalp_universe": [],
    "scalp_universe_scores": {},
    "scalp_mmr_map": {},
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
    "scalp_martingale": {},  # v0.99.109 — {symbol: {"streak": int, "multiplier": float}}. Missing symbol = never lost yet (streak 0, multiplier 1.0, base risk). See scalp_martingale_multiplier_for_symbol()'s own docstring for the full mechanics.
    # EXPERIMENTAL MSNR (Malaysian SNR / Storyline gold strategy, v0.99.0) —
    # see that module's own header comment. All keys prefixed msnr_.
    "msnr_signals": deque(maxlen=MSNR_SIGNAL_HISTORY),
    "msnr_backtest_results": {},
    "msnr_backtest_results_raw": {},  # v0.99.23 — same shape, UNFILTERED by any symbol's skip_rr_min; see msnr_optimize_symbol()'s own docstring for why the pooled autotune/display needs this separate copy
    "msnr_backtest_summary": {},
    "msnr_last_backtest_finished": None,
    "msnr_last_backtest_duration": None,
    "msnr_symbol_overrides": {},  # symbol -> {min_leg_atr, qm_zone_pct, qm_lookback_bars, trades, wins, losses, timeouts, winrate, avg_rr, expectancy_r, score, optimized_at, raw_closed_n, skip_rr_min, rr_filtered_count, skip_sl_pct_min, sl_filtered_count, skip_hours, hours_filtered_count, skip_volume_below, volume_filtered_count, effective_leverage, leverage_ceiling, optimal_leverage, liquidation_filtered_count, compound_final_balance, compound_return_pct, compound_blown_at, stress_test_failed}
    "msnr_backtest_universe": [],  # v0.99.9 — MSNR_SYMBOLS union'd with the top-liquid backtest-only exploration set, see msnr_build_backtest_universe()
    "msnr_live_universe": [],  # v0.99.17 — MSNR_SYMBOLS union'd with any backtest-qualifying symbol (win-rate/sample threshold), see msnr_compute_live_universe(); msnr_live_loop() scans THIS, not the static MSNR_SYMBOLS constant directly, so it stays empty (falls back to MSNR_SYMBOLS at the call site) until the first backtest cycle populates it
    "msnr_autotrade_symbols": {},  # v0.99.18 — per-symbol autotrade toggle, {symbol: bool}. Originally per direct user request for individually-toggleable fields, manually clickable. v0.99.108, per direct user request ("Ручное управление можно убрать"): now FULLY AUTOMATIC — msnr_backtest_loop() sets this True for a symbol currently in the top MSNR_AUTOTRADE_TOP_N AND win_rate > 50%, False the moment either condition stops holding (scoped to the auto-managed pool via msnr_autotrade_top_set below, see that key's own comment). A symbol missing from this dict is treated as off (same "off unless explicitly on" default every other autotrade toggle in this app already uses). See msnr_autotrade_eligible_symbols() for the top-N set and msnr_backtest_loop()'s own comment for the full auto-on/auto-off logic.
    "msnr_autotrade_top_set": [],  # v0.99.108 — the top-N eligible set (msnr_autotrade_eligible_symbols()) as of the LAST backtest cycle, used to scope msnr_backtest_loop()'s own auto-on/auto-off toggle management to symbols that were actually part of the auto-managed pool. See msnr_backtest_loop()'s own comment for the full reasoning.
    "msnr_live_balance": {},  # v0.99.33 — symbol -> current REAL compounding margin in USD for that symbol's live autotrade sizing. Missing = never traded yet, defaults to MSNR_COMPOUND_START_BALANCE ($40) on the first fire — see msnr_live_balance_for_symbol(). Updated by update_msnr_signal_outcomes() off each autotrade-fired signal's own WIN/LOSS result, same price-move-%-times-leverage math msnr_compound_trail() already uses for the backtest simulation, capped at MSNR_LIVE_BALANCE_MAX. In-memory only, same as every other STATE dict here — resets to empty (so every symbol restarts at $40) on app restart, which is the correct "start with 40" behavior, not a gap to fix.
    "msnr_backtest_total": 0,  # v0.99.15 — progress tracking for the CURRENT (or most recent) backtest cycle, per direct user request for visibility during a long-running cycle
    "msnr_backtest_done": 0,
    "msnr_backtest_in_flight": [],  # symbols currently being fetched/optimized right now, not yet resolved
    "msnr_backtest_running": False,
    "msnr_backtest_started_at": None,
    # EXPERIMENTAL FT5 (port of freqtrade's Strategy005, v0.96.0) — see
    # that module's own header comment. All keys prefixed ft5_.
    "ft5_universe": [],
    "ft5_live_universe": [],  # top FT5_LIVE_TOP_N of ft5_universe by avg_pnl_pct, computed after each backtest pass — only these get live-scanned
    "ft5_symbol_overrides": {},  # symbol -> {buy_rsi, buy_fisher, sell_rsi, trades, winrate, avg_pnl_pct, optimized_at}
    "ft5_symbols_done": 0,
    "ft5_last_backtest_finished": None,
    "ft5_last_backtest_duration": None,
    "ft5_signals": deque(maxlen=FT5_SIGNAL_HISTORY),
    # MIRROR — "зеркальный уровень" reversal strategy, see that module's
    # own header comment. All keys prefixed mirror_.
    "mirror_backtest_results": {},
    "mirror_backtest_summary": {},
    "mirror_symbol_overrides": {},  # symbol -> {skip_sl_pct_min, checkpoints}, see mirror_backtest_symbol()
    "mirror_live_universe": [],  # symbols whose post-filter backtest winrate cleared MIRROR_LIVE_MIN_WINRATE, see mirror_backtest_loop()
    "mirror_tuned_tolerances": {},  # v0.99.130 — symbol -> {"touch_tolerance_pct","pattern_tolerance_pct","train_winrate","train_n","test_winrate","test_n"} for symbols where mirror_autotune_tolerances() found a validated combo; absent symbols use the plain module-wide defaults
    "mirror_last_backtest_finished": None,
    "mirror_last_backtest_duration": None,
    "mirror_signals": deque(maxlen=MIRROR_SIGNAL_HISTORY),
    "mirror_filtered_signals": deque(maxlen=MIRROR_SIGNAL_HISTORY),  # v0.99.114, per direct user question ("может без применения фильтра было лучше, а после него стало хуже"): signals the SL-width/direction filters would have blocked from firing, tracked through the exact same outcome logic (WIN/LOSS/TIMEOUT) as real live signals, but never actually traded — the only honest way to answer "does this filter actually help" with real forward data instead of assuming the backtest's own retrospective self-consistency proves it. See mirror_scan_symbol_live()'s own comment for the full reasoning.
    # LSW ("Liquidity Sweep") — equal-highs/equal-lows liquidity-grab
    # reversal module. All keys prefixed lsw_. Shipped paper-only in
    # v0.99.119; v0.99.120 wired real autotrade in (see LSW_ENABLED's
    # own comment).
    "lsw_signals": deque(maxlen=LSW_SIGNAL_HISTORY),
    "lsw_backtest_results": {},
    "lsw_backtest_summary": {},
    "lsw_filter_checkpoints": {},  # v0.99.136 — symbol -> {"raw","htf_filter","structural_cap","entry_confirm"}, each filter's own SOLO before/after (not chained), so a toggle's own contribution is visible before deciding whether to enable it
    "lsw_backtest_total": 0,  # v0.99.137 — same progress-tracking fields as MSNR's own (msnr_backtest_total/done/in_flight/running/started_at), per direct user request for the same visibility during a long-running LSW cycle
    "lsw_backtest_done": 0,
    "lsw_backtest_in_flight": [],
    "lsw_backtest_running": False,
    "lsw_backtest_started_at": None,
    "lsw_live_universe": [],
    "lsw_live_directions": {},  # symbol -> list of directions allowed to fire live, e.g. ["LONG"] — only populated/consulted when LSW_DIRECTION_FILTER_ENABLED
    "lsw_last_backtest_finished": None,
    "lsw_last_backtest_duration": None,
    "autotrade_log": deque(maxlen=AUTOTRADE_TRADE_HISTORY),  # every attempted auto-trade, dry-run or real, with its outcome
    "sim_balance": AUTOTRADE_SIM_START_BALANCE,
    "sim_trades": deque(maxlen=AUTOTRADE_SIM_TRADE_HISTORY),  # pending + settled paper trades
}
_cooldowns = {}  # (symbol, zone_key) -> last_alert_ts
_cooldowns_lock = threading.Lock()
_scalp_signal_cooldowns = {}  # (symbol, interval) -> last_signal_ts
_scalp_signal_cooldowns_lock = threading.Lock()


def has_open_signal(symbol):
    """True if this symbol already has an unresolved (OPEN) signal —
    simplest fix for the "repeat signal on the same level every scan"
    problem: don't stack a second signal on a symbol that already has one
    running, regardless of which exact zone/direction produced it."""
    with state_lock:
        return any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in STATE["signals"])


_symbol_trade_locks = {}
_symbol_trade_locks_meta_lock = threading.Lock()


def _get_symbol_trade_lock(symbol):
    """v0.99.107, per direct user report ("увидел одновременно несколько
    позиций активных по 1 монете с разными а бывает и одинаковыми
    тейками/стопами" — seen at least in Scalp, possibly Mirror too):
    a per-symbol lock serializing execute_autotrade() calls for the
    SAME symbol across every module. Closes a genuine TOCTOU race
    execute_autotrade()'s own exchange-position check (v0.99.53) and
    has_open_signal_any_module() above couldn't catch on their own:
    both are simple point-in-time checks, not atomic with the order
    placement that follows — if two near-simultaneous signals for the
    SAME symbol (e.g. Scalp evaluating multiple intervals for one coin
    in the same scan pass) both reach execute_autotrade() close enough
    together, BOTH can see "no open position yet" and BOTH place real
    orders before either one's own order becomes visible to the other's
    check — exactly the reported duplicate-position, sometimes-
    identical-TP/SL symptom. A dict of per-symbol locks (not one global
    lock across all trading) so trades on DIFFERENT symbols still run
    fully concurrently — only same-symbol calls actually serialize,
    the second one blocking until the first has fully committed (order
    placed, now visible on the exchange) or decided to skip."""
    with _symbol_trade_locks_meta_lock:
        if symbol not in _symbol_trade_locks:
            _symbol_trade_locks[symbol] = threading.Lock()
        return _symbol_trade_locks[symbol]


def has_open_signal_any_module(symbol, exclude=None):
    """True if ANY module already has an OPEN signal on this symbol.
    Each module previously only checked its OWN signal list before
    firing — real gap found live, back when EMA and Divergence (both
    since removed) still existed: EMA opened MMT_USDT SHORT, and 43
    minutes later Breakout opened MMT_USDT LONG, completely
    independently, each placing its own market order + TP + SL.
    Multiplied across several modules all watching the same universe, a
    single popular/volatile symbol accumulates a pile of orders from
    different sources with no coordination between them (the reported
    case: 13 open orders on one symbol on Gate, nothing in any single
    module's own log looking obviously wrong, because no module's log
    ever saw the whole picture).
    Called in ADDITION to each module's existing own-list check, not
    instead of it — this only adds a cross-module veto, it doesn't
    change any module's internal per-symbol/interval dedup logic.
    exclude: the caller's own STATE key name (e.g. "scalp_signals"),
    skipped so a module never vetoes its own already-pending signal —
    every current caller passes its own list name for exactly this
    reason, purely for clarity (their own already-called check already
    makes it a no-op in practice)."""
    lists = {
        "signals": STATE["signals"],
        "scalp_signals": STATE["scalp_signals"],
        "ft5_signals": STATE["ft5_signals"],
        "msnr_signals": STATE["msnr_signals"],
        "mirror_signals": STATE["mirror_signals"],
        "lsw_signals": STATE["lsw_signals"],  # v0.99.120 — added when LSW got real autotrade wired in; before that LSW was paper-only so its own open signals had no real-position conflict to guard against
    }
    with state_lock:
        for name, lst in lists.items():
            if name == exclude:
                continue
            if any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in lst):
                return True
    return False


def compute_rsi(closes, period=14):
    """v0.99.85 — RESTORED after being deleted along with Divergence's
    own detect_divergence()/find_pivots(): this specific function is
    NOT divergence-only. FT5's own run_ft5_backtest() calls it directly
    as part of its own indicator stack (alongside compute_fisher_rsi/
    compute_macd/compute_adx/compute_stoch_fast/compute_sma/compute_sar)
    — genuinely shared infrastructure the same way openVgiChart() turned
    out to be for Scalp/XAU LG during the VGI removal. find_pivots()/
    simulate_pivot_stability() (the OTHER two functions removed in this
    same original block) really were divergence-only — confirmed via a
    fresh grep before restoring only this one, not blindly reverting
    the whole deletion.
    `period` default changed from DIV_RSI_PERIOD (now a deleted
    constant) to a literal 14 (DIV_RSI_PERIOD's own former default
    value) — FT5's own call site never passed period explicitly either
    way, so this default was always what actually got used there.
    Standard Wilder RSI."""
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


# ----------------------------------------------------------------------------
# Extra indicator helpers for FT5 (v0.96.0) — SMA, MACD, Stochastic Fast,
# Fisher-transformed RSI, Parabolic SAR. Pure Python over this app's own
# candle-dict lists, matching every other indicator here — no pandas/talib
# dependency (this whole app deliberately avoids that stack), unlike the
# freqtrade source these are ported from, which uses talib.abstract
# throughout. Kept as generic, reusable helpers (not FT5-prefixed) since
# none of them are specific to that one module — same principle already
# applied to compute_rsi/compute_ema/compute_adx being shared infrastructure.
# ----------------------------------------------------------------------------
def compute_sma(values, period):
    n = len(values)
    sma = [None] * n
    for i in range(period - 1, n):
        window = values[i - period + 1:i + 1]
        if any(v is None for v in window):
            continue
        sma[i] = sum(window) / period
    return sma


def compute_macd(closes, fast=12, slow=26, signal=9):
    """Standard MACD: macd_line = EMA(fast) - EMA(slow), signal_line =
    EMA(macd_line, signal). compute_ema() seeds from index 0 with no
    None warm-up (Pine-style, same as the EMA 7/14/28 module already
    uses), so macd_line has no None gaps either — only genuinely
    meaningless very-early values, same caveat as EMA7/14/28 have."""
    ema_fast = compute_ema(closes, fast)
    ema_slow = compute_ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = compute_ema(macd_line, signal)
    return macd_line, signal_line


def compute_stoch_fast(candles, k_period=5, d_period=3):
    """%K = 100*(close-lowest_low)/(highest_high-lowest_low) over
    k_period bars; %D = SMA(%K, d_period) — matches TA-Lib's STOCHF
    defaults (fastk_period=5, fastd_period=3, fastd_matype=SMA)."""
    n = len(candles)
    fastk = [None] * n
    for i in range(k_period - 1, n):
        window = candles[i - k_period + 1:i + 1]
        hh = max(c["high"] for c in window)
        ll = min(c["low"] for c in window)
        rng = hh - ll
        fastk[i] = 100 * (candles[i]["close"] - ll) / rng if rng > 0 else 0.0
    fastd = compute_sma(fastk, d_period)
    return fastk, fastd


def compute_fisher_rsi(rsi_series):
    """Inverse Fisher transform of RSI — sharpens RSI's extremes into a
    [-1, 1] range (fisher) and a normalized [0, 100] range (fisher_
    norma), same transform Strategy005 uses: rsi_scaled = 0.1*(rsi-50),
    fisher = (e^(2x)-1)/(e^(2x)+1), fisher_norma = 50*(fisher+1)."""
    n = len(rsi_series)
    fisher = [None] * n
    fisher_norma = [None] * n
    for i, r in enumerate(rsi_series):
        if r is None:
            continue
        x = 0.1 * (r - 50)
        f = (math.exp(2 * x) - 1) / (math.exp(2 * x) + 1)
        fisher[i] = f
        fisher_norma[i] = 50 * (f + 1)
    return fisher, fisher_norma


def compute_sar(candles, af_start=0.02, af_increment=0.02, af_max=0.2):
    """Wilder's Parabolic SAR — standard iterative algorithm, no
    external TA library (same reasoning as this whole section's header
    comment). Trend flips when price crosses the current SAR; AF
    (acceleration factor) grows each time a new extreme point forms in
    the current trend's direction, capped at af_max, and resets to
    af_start on every flip."""
    n = len(candles)
    sar = [None] * n
    if n < 2:
        return sar
    uptrend = candles[1]["close"] >= candles[0]["close"]
    if uptrend:
        cur_sar = candles[0]["low"]
        ep = candles[1]["high"]
    else:
        cur_sar = candles[0]["high"]
        ep = candles[1]["low"]
    af = af_start
    sar[1] = cur_sar
    for i in range(2, n):
        prev_sar = cur_sar
        cur_sar = prev_sar + af * (ep - prev_sar)
        if uptrend:
            cur_sar = min(cur_sar, candles[i - 1]["low"], candles[i - 2]["low"])
            if candles[i]["low"] < cur_sar:
                uptrend = False
                cur_sar = ep
                ep = candles[i]["low"]
                af = af_start
            elif candles[i]["high"] > ep:
                ep = candles[i]["high"]
                af = min(af + af_increment, af_max)
        else:
            cur_sar = max(cur_sar, candles[i - 1]["high"], candles[i - 2]["high"])
            if candles[i]["high"] > cur_sar:
                uptrend = True
                cur_sar = ep
                ep = candles[i]["high"]
                af = af_start
            elif candles[i]["low"] < ep:
                ep = candles[i]["low"]
                af = min(af + af_increment, af_max)
        sar[i] = cur_sar
    return sar




_T_CRITICAL_TABLE = [  # (df, t-value at ~84.13% one-sided confidence, i.e. Phi(1.0) — chosen so this smoothly converges to the old fixed Z=1.0 at large df) — computed once via scipy.stats.t.ppf and hardcoded as plain numbers rather than adding scipy as an app dependency (same reasoning as avoiding numpy for VGI — this needs to run on a phone via Termux)
    (1, 1.8373), (2, 1.3213), (3, 1.1969), (4, 1.1416), (5, 1.1105),
    (6, 1.0906), (7, 1.0767), (8, 1.0665), (9, 1.0587), (10, 1.0526),
    (12, 1.0434), (15, 1.0345), (20, 1.0256), (25, 1.0204), (30, 1.0169),
    (40, 1.0127), (60, 1.0084), (100, 1.0050),
]
_T_CRITICAL_MAX_DF = _T_CRITICAL_TABLE[-1][0]
_T_CRITICAL_INF = 1.0  # Phi^-1(0.8413) — the Normal-distribution limit as df -> infinity


def t_critical(df):
    """Linear-interpolated one-sided ~84% t-critical value for df degrees
    of freedom — see _T_CRITICAL_TABLE's own comment for why this is a
    hardcoded table instead of scipy.stats.t.ppf(). v0.98.8: added
    because a fixed Z (however statistically reasonable-looking) can't
    tell the difference between "n=5, genuinely low variance" and "n=5,
    simply hasn't had the chance to show a loss yet" — a small sample's
    OBSERVED variance is itself an unreliable estimate of the TRUE
    variance, and a fixed Z doesn't account for that extra layer of
    uncertainty the way a t-distribution's fatter tails at low df do.
    Diagnosed from a direct, concrete counterexample: DEXE_USDT (n=5,
    5W/0L, avg +2.957%) outranked 龙虾_USDT (n=24, 22W/2L, avg +1.084%)
    under the fixed-Z formula — an all-win 5-trade sample looked "low
    variance" simply because it hadn't lost yet, not because it was
    actually more reliable than a 24-trade sample with real (if small)
    downside experience. t_critical(4) ≈ 1.14 vs the old fixed 1.0
    isn't a huge jump on its own, but the effect compounds: the SAME
    all-win-so-far sample also has an artificially small observed std,
    so the two errors were stacking in the same direction — the wider
    critical value directly counteracts that."""
    if df <= 0:
        return _T_CRITICAL_TABLE[0][1]
    if df >= _T_CRITICAL_MAX_DF:
        return _T_CRITICAL_INF
    for i in range(len(_T_CRITICAL_TABLE) - 1):
        df_lo, t_lo = _T_CRITICAL_TABLE[i]
        df_hi, t_hi = _T_CRITICAL_TABLE[i + 1]
        if df_lo <= df <= df_hi:
            frac = (df - df_lo) / (df_hi - df_lo)
            return t_lo + frac * (t_hi - t_lo)
    return _T_CRITICAL_INF


def _ft5_filter_checkpoint(trades):
    """v0.99.143 — same {n, winrate, avg_pnl_pct} snapshot shape as
    _mirror_checkpoint()/_msnr_filter_checkpoint(), adapted to FT5's own
    metric: FT5 has no fixed-R target (it exits via a % stoploss + ROI
    ladder, not a single R-multiple TP), so "income" here is the plain
    average pnl_pct across trades rather than an R-expectancy or a
    compounded %."""
    if not trades:
        return {"n": 0, "winrate": None, "avg_pnl_pct": None}
    wins = sum(1 for t in trades if t.get("result") == "WIN")
    pnls = [t["pnl_pct"] for t in trades if t.get("pnl_pct") is not None]
    return {
        "n": len(trades),
        "winrate": round(wins / len(trades) * 100, 1),
        "avg_pnl_pct": round(sum(pnls) / len(pnls), 3) if pnls else None,
    }


def ft5_filter_by_htf_trend(trades, bias_series, htf_interval_sec):
    """v0.99.143 — same higher-timeframe trend concept as LSW's
    (v0.99.121), MSNR's (v0.99.141), and Mirror's (v0.99.142) own
    versions, reusing the shared lsw_htf_bias_at() lookup. Reads
    "entry_time" (FT5's own trade dicts use that field name, not
    "time") and "direction"."""
    kept = []
    for t in trades:
        bias = lsw_htf_bias_at(bias_series, t["entry_time"], htf_interval_sec)
        if bias is None:
            continue
        if t["direction"] == "LONG" and bias == "DOWN":
            continue
        if t["direction"] == "SHORT" and bias == "UP":
            continue
        kept.append(t)
    return kept


def ft5_ranking_score(pnls, losses_count, z=None):
    """Ranking score for FT5 combos/symbols — replaces raw avg_pnl_pct as
    the selection criterion wherever FT5 picks a "best" option (best
    param combo per symbol, best symbols for the live-scan pool).
    v0.98.7: switched from a sample-size-only shrinkage (avg_pnl_pct *
    n/(n+K)) to a proper lower-confidence-bound on the mean: score =
    mean - Z * stderr, stderr = sample_std / sqrt(n). Per direct user
    report with a concrete counterexample: the old formula let a combo
    with MORE losses (UB_USDT: 21W/7L, avg +1.353%) outrank one with
    FEWER losses and a HIGHER average (AKE_USDT: 13W/2L, avg +1.488%),
    purely because UB_USDT's larger n gave it a smaller size-based
    discount. A lower-confidence-bound fixes this naturally: frequent
    large losses mixed with modest wins directly inflate variance,
    which inflates stderr, which lowers the score.
    v0.98.8: two more direct counterexamples, fixed in sequence rather
    than guessed at once — each verified behaviorally before moving to
    the next, and the combination re-verified against BOTH original
    cases at the end, since a naive second fix reintroduced the first.
    (1) DEXE_USDT (n=5, 5W/0L, avg +2.957%) outranked 龙虾_USDT (n=24,
    22W/2L, avg +1.084%) — a small sample's OBSERVED variance can look
    deceptively tiny simply because it hasn't happened to hit a loss
    yet. Fixed with t_critical(n-1), a proper Student's-t critical
    value instead of a fixed Z — see t_critical()'s own docstring.
    (2) t_critical alone wasn't quite enough for the all-win DEXE case
    (no reasonable fixed multiplier closes the gap when observed
    variance is near-zero) — added a Bayesian prior: since FT5's
    stoploss is a FIXED, KNOWN quantity (not something to estimate from
    data — every trade structurally CAN reach -FT5_STOPLOSS_PCT*100),
    max(0, FT5_RANK_PRIOR_TARGET - losses_count) pseudo-trades at that
    loss level are blended in before computing mean/variance. Tapering
    by ACTUAL losses_count (not a flat count added to every combo
    regardless) was essential, found by testing: a flat +3 prior fixed
    DEXE but flipped UB/AKE back the wrong way, since 3 fixed pseudo-
    losses land disproportionately harder on AKE's smaller real sample
    (2 real losses) than on UB's larger one (7 real losses already
    telling an honest, undiluted story). FT5_RANK_PRIOR_TARGET=1 means
    only a combo with ZERO or ONE real observed loss gets any prior
    adjustment at all; two or more real losses are trusted as-is.
    Reduces to the raw mean as n grows, variance shrinks, and/or real
    losses accumulate — same convergence property every version had.
    z, if given, overrides the automatic t_critical lookup entirely
    (mainly for testing) — resolved at call time either way, not frozen
    as a signature default, avoiding the exact v0.95.7-class stale-
    default bug this session already found and fixed elsewhere."""
    n = len(pnls) if pnls else 0
    if n == 0:
        return -999
    prior_n = max(0, FT5_RANK_PRIOR_TARGET - losses_count)
    prior_pnls = pnls + [-FT5_STOPLOSS_PCT * 100] * prior_n
    pn = len(prior_pnls)
    mean = sum(prior_pnls) / pn
    if pn < 2:
        return mean
    zz = z if z is not None else t_critical(pn - 1)
    var = sum((p - mean) ** 2 for p in prior_pnls) / (pn - 1)
    stderr = math.sqrt(var) / math.sqrt(pn)
    return mean - zz * stderr


def ft5_run_backtest(candles, buy_rsi=26, buy_fisher=5, sell_rsi=74,
                      buy_fastd_min=1, buy_volume_avg=FT5_VOLUME_AVG_PERIOD,
                      buy_volume_mult=FT5_VOLUME_SPIKE_MULT, sma_period=FT5_SMA_PERIOD,
                      sell_minus_di=FT5_SELL_MINUS_DI, sell_fisher=FT5_SELL_FISHER,
                      stoploss_pct=FT5_STOPLOSS_PCT, roi_ladder=None, invert=None):
    """Core FT5 walk-forward simulator — computes every indicator ONCE
    over the whole candle list, then walks forward bar by bar with no
    lookahead: an entry at bar i only ever uses indicator values through
    bar i, and once in a (simulated) position, checks exits in the same
    priority order Strategy005 itself effectively has (stoploss first,
    then the ROI ladder, then the sell-signal conditions) using only
    that bar's own high/low/close. Used identically for grid-search
    backtesting (feed the whole history, try many param combos) and for
    turning a symbol's LATEST bar into a live signal (feed recent
    history, check whether a position would have just opened/closed on
    the last bar) — same "one function serves both" principle as every
    other detector in this app.
    Long-only by default, matching Strategy005's own design (see this
    module's header comment for the full list of deliberate deviations
    from the literal freqtrade source).
    v0.98.10: invert, per direct user request for reverse mode "по
    аналогии с другими индикаторами" (defaults to the live FT5_INVERT_
    SIGNALS global if not given — resolved at call time, not frozen as
    a signature default, since that constant IS settings-mutable,
    avoiding the exact v0.95.7-class stale-default bug this session
    already found and fixed elsewhere). When on, the SAME entry trigger
    fires but opens a SHORT instead of a LONG, with stoploss and the
    ROI ladder both mirrored (both are pure %-of-entry rules, safe to
    reflect exactly). The sell-signal exit (RSI cross + MACD + MinusDI,
    or SAR flip + Fisher) is deliberately NOT mirrored and simply
    doesn't fire for inverted trades — it's tuned to detect bullish
    exhaustion for exiting a LONG, and MinusDI/SAR/Fisher don't mirror
    to their bearish-exhaustion equivalents by simply flipping a
    comparison operator (unlike PlusDI/MinusDI, which ARE genuine
    mirrors of each other, this indicator SET as a whole measures
    direction-specific things that would need their own redesign, not
    a mechanical sign flip, to detect the opposite exhaustion honestly).
    Inverted trades exit only via stoploss or the ROI ladder — simpler
    than the LONG side, same "own, simplified exit rather than reusing
    original complexity" pattern this app's other invert modes already
    use (see EMA_INVERT_SIGNALS/SESSION_INVERT_SIGNALS's own comments).
    Returns (trades, open_position): trades is a list of CLOSED trades
    ({entry_time, exit_time, entry, exit, pnl_pct, result, exit_reason});
    open_position is None, or {entry, entry_time} if a position was
    still open when the candle list ran out — the live scanner uses
    this to detect a position that just opened on the very last bar."""
    roi_ladder = roi_ladder or FT5_ROI_LADDER
    inv = invert if invert is not None else FT5_INVERT_SIGNALS
    n = len(candles)
    warmup = max(sma_period, buy_volume_avg) + 30
    if n < warmup + 20:
        return [], None
    closes = [c["close"] for c in candles]
    volumes = [c["volume"] for c in candles]
    rsi = compute_rsi(closes)
    fisher, fisher_norma = compute_fisher_rsi(rsi)
    macd_line, macd_signal = compute_macd(closes)
    _, minus_di, _ = compute_adx(candles)
    fastk, fastd = compute_stoch_fast(candles, FT5_STOCH_K, FT5_STOCH_D)
    sma = compute_sma(closes, sma_period)
    vol_avg = compute_sma(volumes, buy_volume_avg)
    sar = compute_sar(candles)

    trades = []
    position = None
    for i in range(warmup, n):
        c = candles[i]
        if position is None:
            if (vol_avg[i] is not None and volumes[i] > vol_avg[i] * buy_volume_mult and
                    sma[i] is not None and c["close"] < sma[i] and
                    fastd[i] is not None and fastk[i] is not None and fastd[i] > fastk[i] and
                    rsi[i] is not None and rsi[i] > buy_rsi and
                    fastd[i] > buy_fastd_min and
                    fisher_norma[i] is not None and fisher_norma[i] < buy_fisher):
                position = {"entry": c["close"], "entry_time": c["time"], "direction": "SHORT" if inv else "LONG",
                            "mfe_r": 0.0, "mae_r": 0.0}
            continue

        entry = position["entry"]
        minutes_in_trade = (c["time"] - position["entry_time"]) / 60
        r_unit = entry * stoploss_pct
        if position["direction"] == "LONG":
            fav_r, adv_r = (c["high"] - entry) / r_unit, (entry - c["low"]) / r_unit
        else:
            fav_r, adv_r = (entry - c["low"]) / r_unit, (c["high"] - entry) / r_unit
        position["mfe_r"] = max(position["mfe_r"], fav_r)
        position["mae_r"] = max(position["mae_r"], adv_r)

        if inv:
            sl_price = entry * (1 + stoploss_pct)
            if c["high"] >= sl_price:
                trades.append({**position, "exit_time": c["time"],
                                "exit": sl_price, "pnl_pct": round(-stoploss_pct * 100, 3),
                                "result": "LOSS", "exit_reason": "stoploss"})
                position = None
                continue

            roi_threshold = None
            for min_minutes, min_pct in roi_ladder:
                if minutes_in_trade >= min_minutes:
                    roi_threshold = min_pct
                    break
            if roi_threshold is not None:
                roi_price = entry * (1 - roi_threshold)
                if c["low"] <= roi_price:
                    trades.append({**position, "exit_time": c["time"],
                                    "exit": roi_price, "pnl_pct": round(roi_threshold * 100, 3),
                                    "result": "WIN", "exit_reason": "roi"})
                    position = None
            continue

        sl_price = entry * (1 - stoploss_pct)
        if c["low"] <= sl_price:
            trades.append({**position, "exit_time": c["time"],
                            "exit": sl_price, "pnl_pct": round(-stoploss_pct * 100, 3),
                            "result": "LOSS", "exit_reason": "stoploss"})
            position = None
            continue

        roi_threshold = None
        for min_minutes, min_pct in roi_ladder:
            if minutes_in_trade >= min_minutes:
                roi_threshold = min_pct
                break
        if roi_threshold is not None:
            roi_price = entry * (1 + roi_threshold)
            if c["high"] >= roi_price:
                trades.append({**position, "exit_time": c["time"],
                                "exit": roi_price, "pnl_pct": round(roi_threshold * 100, 3),
                                "result": "WIN", "exit_reason": "roi"})
                position = None
                continue

        sell_signal = False
        if (rsi[i - 1] is not None and rsi[i] is not None and rsi[i - 1] <= sell_rsi < rsi[i] and
                macd_line[i] < 0 and minus_di[i] is not None and minus_di[i] > sell_minus_di):
            sell_signal = True
        # NOTE: compares fisher_rsi_norma (0-100 scale), not the raw
        # fisher_rsi (-1..1 scale) the literal freqtrade source uses for
        # this specific condition — see this module's header comment on
        # why that's treated as a source bug, not replicated here.
        if not sell_signal and (sar[i] is not None and sar[i] > c["close"] and
                                 fisher_norma[i] is not None and fisher_norma[i] > sell_fisher):
            sell_signal = True
        if sell_signal:
            pnl_pct = (c["close"] - entry) / entry
            trades.append({**position, "exit_time": c["time"],
                            "exit": c["close"], "pnl_pct": round(pnl_pct * 100, 3),
                            "result": "WIN" if pnl_pct > 0 else "LOSS", "exit_reason": "signal"})
            position = None
    return trades, position


def ft5_optimize_symbol(symbol):
    """Grid search over (buy_rsi, buy_fisher, sell_rsi) — FT5_PARAM_GRID_
    BUY_RSI x FT5_PARAM_GRID_BUY_FISHER x FT5_PARAM_GRID_SELL_RSI, 36
    combos. Selects by ft5_ranking_score() — a lower-confidence-bound
    on the mean (mean - Z*stderr, v0.98.7) rather than raw avg_pnl_pct.
    Originally just shrunk by sample size (v0.98.3, fixing a small-
    lucky-sample-outranks-a-frequent-setup issue), then rebuilt as a
    proper confidence bound after a direct counterexample showed the
    size-only version let a combo with MORE losses outrank one with
    FEWER losses and a higher average, since it only rewarded n and
    never separately weighed how much of that n was losses — see
    ft5_ranking_score()'s own docstring for the full reasoning.
    Mirrors optimize_symbol()'s own shape (grid search, min-trades bar,
    best-effort fallback) for consistency with the rest of this app."""
    now = time.time()
    candles = get_candles_range(symbol, FT5_TF, now - FT5_BACKTEST_DAYS * 86400, now)
    if len(candles) < 300:
        return {"error": "not enough history"}
    best = None
    best_score = None
    best_trades = []
    tried = []
    for buy_rsi in FT5_PARAM_GRID_BUY_RSI:
        for buy_fisher in FT5_PARAM_GRID_BUY_FISHER:
            for sell_rsi in FT5_PARAM_GRID_SELL_RSI:
                trades, _ = ft5_run_backtest(candles, buy_rsi=buy_rsi, buy_fisher=buy_fisher, sell_rsi=sell_rsi)
                tried.append(len(trades))
                if len(trades) < FT5_MIN_BACKTEST_TRADES:
                    continue
                pnls = [t["pnl_pct"] for t in trades]
                avg_pnl = sum(pnls) / len(pnls)
                wins = sum(1 for t in trades if t["result"] == "WIN")
                losses = len(trades) - wins
                score = ft5_ranking_score(pnls, losses)
                if best is None or score > best_score:
                    best = {
                        "buy_rsi": buy_rsi, "buy_fisher": buy_fisher, "sell_rsi": sell_rsi,
                        "trades": len(trades), "wins": wins, "losses": len(trades) - wins,
                        "winrate": round(wins / len(trades) * 100, 1),
                        "avg_pnl_pct": round(avg_pnl, 3), "score": round(score, 4),
                        "optimized_at": now, "candles_used": len(candles),
                    }
                    best_score = score
                    # v0.99.143 — keeps the winning combo's own raw trade
                    # list around for the new filter-checkpoint chain
                    # below, instead of re-running ft5_run_backtest() a
                    # second time just to get it back.
                    best_trades = trades
    if best is None:
        best = {
            "buy_rsi": FT5_PARAM_GRID_BUY_RSI[len(FT5_PARAM_GRID_BUY_RSI) // 2],
            "buy_fisher": FT5_PARAM_GRID_BUY_FISHER[len(FT5_PARAM_GRID_BUY_FISHER) // 2],
            "sell_rsi": FT5_PARAM_GRID_SELL_RSI[len(FT5_PARAM_GRID_SELL_RSI) // 2],
            "trades": 0, "wins": 0, "losses": 0, "winrate": None, "avg_pnl_pct": None, "score": None,
            "optimized_at": now, "candles_used": len(candles),
            "note": f"insufficient trades across all 36 combos tried (max {max(tried) if tried else 0}, need {FT5_MIN_BACKTEST_TRADES}); using middle-of-grid defaults",
        }
    # v0.99.143 — 2 new GLOBAL (uniform-threshold) optional filters,
    # same "always compute a solo preview even while off, only actually
    # narrow when the toggle is genuinely on" principle as MSNR/Mirror's
    # own pairs (v0.99.141/142) — see FT5_HTF_FILTER_ENABLED's own
    # comment for why these two (not volume, already baked into the
    # entry trigger itself; not min-RR, FT5 has no rr field at all).
    checkpoints = [{"stage": "raw", **_ft5_filter_checkpoint(best_trades)}]
    htf_candles = None
    try:
        htf_interval_sec = INTERVAL_SECONDS.get(FT5_HTF_INTERVAL, 14400)
        htf_fetch_start = now - FT5_BACKTEST_DAYS * 86400 - FT5_HTF_EMA_PERIOD * htf_interval_sec
        htf_candles = get_candles_range(symbol, FT5_HTF_INTERVAL, htf_fetch_start, now)
    except Exception as e:
        log_error(f"ft5_optimize_symbol {symbol}: HTF fetch for trend filter failed: {e}")
    if htf_candles and len(htf_candles) >= FT5_HTF_EMA_PERIOD:
        bias_series = lsw_htf_bias_series(htf_candles, period=FT5_HTF_EMA_PERIOD, buffer_pct=FT5_HTF_TREND_BUFFER_PCT)
        htf_candidates = ft5_filter_by_htf_trend(best_trades, bias_series, htf_interval_sec)
    else:
        htf_candidates = best_trades  # not enough HTF history to judge — informational preview only
    working_trades = best_trades
    if FT5_HTF_FILTER_ENABLED:
        working_trades = htf_candidates if (htf_candles and len(htf_candles) >= FT5_HTF_EMA_PERIOD) else []
        checkpoints.append({"stage": "htf_trend", **_ft5_filter_checkpoint(working_trades)})
    else:
        checkpoints.append({"stage": "htf_trend", **_ft5_filter_checkpoint(htf_candidates)})
    session_candidates = lsw_filter_signals_by_session(working_trades, FT5_SESSION_START_HOUR_UTC, FT5_SESSION_END_HOUR_UTC)
    if FT5_SESSION_FILTER_ENABLED:
        working_trades = session_candidates
        checkpoints.append({"stage": "session", **_ft5_filter_checkpoint(working_trades)})
    else:
        checkpoints.append({"stage": "session", **_ft5_filter_checkpoint(session_candidates)})
    best["filter_checkpoints"] = checkpoints
    if working_trades is not best_trades:
        w_wins = sum(1 for t in working_trades if t["result"] == "WIN")
        w_pnls = [t["pnl_pct"] for t in working_trades]
        best["trades"] = len(working_trades)
        best["wins"] = w_wins
        best["losses"] = len(working_trades) - w_wins
        best["winrate"] = round(w_wins / len(working_trades) * 100, 1) if working_trades else None
        best["avg_pnl_pct"] = round(sum(w_pnls) / len(w_pnls), 3) if w_pnls else None
    return best


def ft5_build_universe():
    """Liquid-symbol pool, same top-by-24h-volume source and shape as
    build_session_universe() — capped to FT5_UNIVERSE_SIZE since the
    36-combo grid search per symbol is the expensive part here."""
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
    return [s[0] for s in ranked[:FT5_UNIVERSE_SIZE]]


_ft5_signal_cooldowns = {}  # symbol -> last-signaled entry_time
_ft5_signal_cooldowns_lock = threading.Lock()
FT5_MAX_HOLD_SEC = 7 * 24 * 3600  # safety-net TIMEOUT if somehow neither the ROI ladder, sell-signal, nor stoploss ever resolves a position — shouldn't happen given the ROI ladder guarantees an eventual exit condition, but every other module in this app has a hold-time backstop, so this one does too


def ft5_scan_symbol_live(symbol):
    """Live counterpart to ft5_optimize_symbol()/ft5_run_backtest() —
    fetches recent history, runs the walk-forward detector with this
    symbol's own optimized (buy_rsi, buy_fisher, sell_rsi) from
    FT5_SYMBOL_OVERRIDES (falling back to the middle of each grid if
    not optimized yet), and fires only if a position just opened on the
    LAST candle.
    Deliberately does NOT call execute_autotrade() or sim_execute_trade()
    — unlike every other module here, FT5's real exit logic (stoploss OR
    a time-decaying ROI ladder OR either of two sell-signal conditions)
    isn't a fixed (SL, TP) price pair; execute_autotrade/sim_execute_
    trade are both built around exactly that shape. Approximating it
    with a single static TP (e.g. the largest ROI rung) would silently
    misrepresent FT5's actual exit behavior to real money or the paper
    simulator — faithfully trading FT5 would need active position
    management (a loop that sends a real close-order the moment ROI-
    ladder/signal/stoploss conditions are met), which hasn't been
    built. AUTOTRADE_ENABLED_FT5 exists in settings for future use but
    is a no-op here for now; ft5_signals are informational only,
    tracked with their own pnl_pct via update_ft5_signal_outcomes()."""
    if not FT5_ENABLED:
        return
    try:
        with state_lock:
            override = STATE["ft5_symbol_overrides"].get(symbol) or {}
        buy_rsi = override.get("buy_rsi", FT5_PARAM_GRID_BUY_RSI[len(FT5_PARAM_GRID_BUY_RSI) // 2])
        buy_fisher = override.get("buy_fisher", FT5_PARAM_GRID_BUY_FISHER[len(FT5_PARAM_GRID_BUY_FISHER) // 2])
        sell_rsi = override.get("sell_rsi", FT5_PARAM_GRID_SELL_RSI[len(FT5_PARAM_GRID_SELL_RSI) // 2])
        interval_sec = INTERVAL_SECONDS.get(FT5_TF, 300)
        now = time.time()
        lookback_bars = max(FT5_SMA_PERIOD, FT5_VOLUME_AVG_PERIOD) + 100
        candles = get_candles(symbol, interval=FT5_TF, limit=lookback_bars)
        candles = [c for c in candles if c["time"] + interval_sec <= now]  # drop still-forming candle, same reasoning as every other live scanner here
        if len(candles) < lookback_bars - 20:
            return
        _, open_position = ft5_run_backtest(candles, buy_rsi=buy_rsi, buy_fisher=buy_fisher, sell_rsi=sell_rsi)
        if open_position is None or open_position["entry_time"] != candles[-1]["time"]:
            return  # nothing open, or it opened on an earlier bar — already handled or stale
        with _ft5_signal_cooldowns_lock:
            if _ft5_signal_cooldowns.get(symbol) == open_position["entry_time"]:
                return
            _ft5_signal_cooldowns[symbol] = open_position["entry_time"]
        # v0.99.144 — same own-list persisted-state check added to
        # every other module (MSNR/Mirror/LSW) for the identical
        # restart-survives-but-cooldown-doesn't bug — see any of those
        # own comments for the full mechanics. FT5 never fires a real
        # order, so this only prevents duplicate PAPER/informational
        # signal rows, not a real financial risk, but the same gap
        # exists here for the same reason.
        with state_lock:
            if any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in STATE["ft5_signals"]):
                return
        if has_open_signal_any_module(symbol, exclude="ft5_signals"):
            return
        entry = open_position["entry"]
        record = {
            "symbol": symbol, "direction": open_position["direction"], "entry": entry,
            "entry_time": open_position["entry_time"],
            "buy_rsi": buy_rsi, "buy_fisher": buy_fisher, "sell_rsi": sell_rsi,
            "detected_at": now, "status": "OPEN", "result": None,
            "exit_price": None, "exit_time": None, "exit_reason": None,
            "pnl_pct": None, "app_version": APP_VERSION,
            "mfe_r": open_position.get("mfe_r", 0.0), "mae_r": open_position.get("mae_r", 0.0),
            "mfe_r_at_close": None, "mae_r_at_close": None,
        }
        with state_lock:
            STATE["ft5_signals"].appendleft(record)
        arrow = "\u2b06\ufe0f LONG" if open_position["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        send_telegram(
            f"{arrow} {symbol} (FT5 \u2014 Strategy005, \u042d\u041a\u0421\u041f\u0415\u0420\u0418\u041c\u0415\u041d\u0422\u0410\u041b\u042c\u041d\u041e, \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u043e\u043d\u043d\u043e)\n"
            f"entry: {entry:.6g}\n"
            f"buy_rsi={buy_rsi} buy_fisher={buy_fisher} sell_rsi={sell_rsi}",
            category="ft5",
        )
    except Exception as e:
        log_error(f"ft5_live {symbol}: {e}")


def update_ft5_signal_outcomes():
    """For each OPEN ft5_signal, re-runs ft5_run_backtest on an extended
    window (from a bit before the signal's own entry_time through now)
    using that signal's own recorded params — deterministic and
    no-lookahead, so it reproduces the exact same entry at the exact
    same bar, then naturally continues through the newer candles to
    check whether stoploss/ROI/sell-signal has since triggered. Reuses
    the walk-forward detector rather than building a separate
    resume-from-open-position code path.
    v0.96.2: also sends a Telegram close alert for each signal that
    just transitioned OPEN -> CLOSED this pass, per direct user
    request — collected during the lock-held update and sent AFTER
    state_lock is released, so a slow/retrying network call never
    holds up other threads waiting on the lock (same reasoning behind
    every other network call in this app happening outside a lock)."""
    now = time.time()
    with state_lock:
        open_signals = [s for s in STATE["ft5_signals"] if s["status"] == "OPEN"]
    interval_sec = INTERVAL_SECONDS.get(FT5_TF, 300)
    warmup_bars = max(FT5_SMA_PERIOD, FT5_VOLUME_AVG_PERIOD) + 100
    just_closed = []
    for sig in open_signals:
        try:
            fetch_start = sig["entry_time"] - warmup_bars * interval_sec
            candles = get_candles_range(sig["symbol"], FT5_TF, fetch_start, now)
            candles = [c for c in candles if c["time"] + interval_sec <= now]
            if not candles:
                continue
            trades, open_position = ft5_run_backtest(
                candles, buy_rsi=sig["buy_rsi"], buy_fisher=sig["buy_fisher"], sell_rsi=sig["sell_rsi"])
            matched = next((t for t in trades if t["entry_time"] == sig["entry_time"]), None)
            timed_out = (now - sig["detected_at"]) > FT5_MAX_HOLD_SEC
            with state_lock:
                if not matched and open_position and open_position["entry_time"] == sig["entry_time"]:
                    sig["mfe_r"] = round(open_position.get("mfe_r", sig.get("mfe_r", 0.0)), 3)
                    sig["mae_r"] = round(open_position.get("mae_r", sig.get("mae_r", 0.0)), 3)
                if matched:
                    sig["status"] = "CLOSED"
                    sig["result"] = matched["result"]
                    sig["exit_price"] = matched["exit"]
                    sig["exit_time"] = matched["exit_time"]
                    sig["exit_reason"] = matched["exit_reason"]
                    sig["pnl_pct"] = matched["pnl_pct"]
                    # Realized R-multiple: pnl_pct relative to the fixed
                    # stoploss risk (FT5_STOPLOSS_PCT), matching the
                    # "RR" meaning every other module here uses (return
                    # relative to what was actually risked) even though
                    # FT5 has no single fixed reward target the way a
                    # fixed-TP module does — see this module's own header
                    # comment on why a static TP isn't a faithful concept
                    # for this strategy's ROI-ladder/signal exit shape.
                    sig["rr"] = round(matched["pnl_pct"] / (FT5_STOPLOSS_PCT * 100), 3)
                    sig["mfe_r"] = round(matched.get("mfe_r", 0.0), 3)
                    sig["mae_r"] = round(matched.get("mae_r", 0.0), 3)
                    sig["mfe_r_at_close"] = sig["mfe_r"]
                    sig["mae_r_at_close"] = sig["mae_r"]
                    just_closed.append(dict(sig))
                elif timed_out:
                    sig["status"] = "CLOSED"
                    sig["result"] = "TIMEOUT"
                    sig["exit_price"] = candles[-1]["close"] if candles else None
                    sig["exit_time"] = candles[-1]["time"] if candles else None
                    sig["exit_reason"] = "max_hold_timeout"
                    if sig["exit_price"]:
                        sig["pnl_pct"] = round((sig["exit_price"] - sig["entry"]) / sig["entry"] * 100, 3)
                        sig["rr"] = round(sig["pnl_pct"] / (FT5_STOPLOSS_PCT * 100), 3)
                    sig["mfe_r_at_close"] = sig.get("mfe_r", 0.0)
                    sig["mae_r_at_close"] = sig.get("mae_r", 0.0)
                    just_closed.append(dict(sig))
        except Exception as e:
            log_error(f"ft5_outcome {sig['symbol']}: {e}")

    for sig in just_closed:
        try:
            result = sig.get("result")
            icon = "\u2705" if result == "WIN" else ("\u274c" if result == "LOSS" else "\u23f1\ufe0f")
            pnl = sig.get("pnl_pct")
            pnl_txt = f"{'+' if pnl and pnl > 0 else ''}{pnl}%" if pnl is not None else "?"
            rr = sig.get("rr")
            rr_txt = f" \u00b7 RR {'+' if rr and rr > 0 else ''}{rr}" if rr is not None else ""
            send_telegram(
                f"{icon} {result} {sig['symbol']} (FT5 \u2014 \u042d\u041a\u0421\u041f\u0415\u0420\u0418\u041c\u0415\u041d\u0422\u0410\u041b\u042c\u041d\u041e, \u0438\u043d\u0444\u043e\u0440\u043c\u0430\u0446\u0438\u043e\u043d\u043d\u043e)\n"
                f"\u0432\u044b\u0445\u043e\u0434: {sig.get('exit_reason')} \u0432 {sig.get('exit_price')}\n"
                f"P&L: {pnl_txt}{rr_txt}",
                category="ft5",
            )
        except Exception as e:
            log_error(f"ft5_close_alert {sig.get('symbol')}: {e}")


def compute_ft5_signal_stats():
    with state_lock:
        signals = list(STATE["ft5_signals"])
    closed = [s for s in signals if s["status"] == "CLOSED" and s["result"] in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = sum(1 for s in closed if s["result"] == "LOSS")
    timeouts = sum(1 for s in signals if s.get("result") == "TIMEOUT")
    open_n = sum(1 for s in signals if s["status"] == "OPEN")
    total_closed = len(closed)
    winrate = round(wins / total_closed * 100, 1) if total_closed else None
    pnls = [s["pnl_pct"] for s in closed if s.get("pnl_pct") is not None]
    avg_pnl = round(sum(pnls) / len(pnls), 3) if pnls else None
    rrs = sorted(s["rr"] for s in closed if s.get("rr") is not None)
    rr_avg = round(sum(rrs) / len(rrs), 3) if rrs else None
    rr_median = round(rrs[len(rrs) // 2], 3) if rrs else None

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

    win_set = [s for s in closed if s["result"] == "WIN"]
    loss_set = [s for s in closed if s["result"] == "LOSS"]
    return {"total": len(signals), "wins": wins, "losses": losses, "timeouts": timeouts,
            "open": open_n, "winrate": winrate, "avg_pnl_pct": avg_pnl,
            "rr_avg": rr_avg, "rr_median": rr_median,
            "mfe_r_wins_at_close": agg("mfe_r_at_close", win_set), "mae_r_wins_at_close": agg("mae_r_at_close", win_set),
            "mfe_r_losses_at_close": agg("mfe_r_at_close", loss_set), "mae_r_losses_at_close": agg("mae_r_at_close", loss_set)}






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


_NETWORK_ERROR_MARKERS = ("Read timed out", "ConnectionError", "Connection broken",
                           "Failed to establish a new connection", "Max retries exceeded",
                           "Connection aborted", "Connection reset")
_network_error_timestamps = []  # sliding window of recent network-flavored log_error() calls
_network_error_lock = threading.Lock()
_network_alert_last_sent = 0.0

# v0.99.129 — Russian prefix for the error log, per direct user request
# ("код ошибки оставим... писать на русском, чтобы мне сразу понятно
# было"): rewriting every one of this file's own ~100+ log_error()
# call sites by hand to speak Russian natively would be a huge, error-
# prone undertaking for something this file already has a working
# pattern for (see the network-alert marker matching just above) —
# instead, log_error() itself now recognizes the common, recurring
# SHAPES of error this app actually produces and prepends a short
# Russian explanation, WITHOUT touching or translating the original
# technical text itself (exception class, exchange error code/label,
# stack detail) — "код ошибки оставим" means exactly that: the
# original stays intact and searchable, only a plain-language label
# gets added in front of it. Order matters — first matching entry
# wins, so more specific patterns (an exchange's own named error code)
# are listed before generic ones (a bare HTTP status) that could also
# appear inside a more specific message.
_ERROR_TRANSLATIONS = (
    (("AUTO_TRIGGER_PRICE_LESS_LAST", "AUTO_TRIGGER"), "📉 Биржа отклонила цену стоп/тейк-триггера: "),
    (("INSUFFICIENT_AVAILABLE", "insufficient", "not enough balance", "not enough margin"), "💰 Недостаточно средств на бирже: "),
    (("invalid signature", "INVALID_KEY", "auth failed", "Unauthorized", "401 Client Error"), "🔑 Проблема с API-ключом: "),
    (("Too Many Requests", "RATE_LIMIT", "429 Client Error"), "⏳ Биржа ограничила частоту запросов: "),
    (_NETWORK_ERROR_MARKERS, "🌐 Проблема с сетью (соединение/таймаут): "),
    (("403 Client Error",), "🔒 Нет доступа к бирже (403) — возможно, гео- или сетевое ограничение: "),
    (("500 Server Error", "502 ", "503 ", "504 ", "Bad Gateway", "Service Unavailable"), "🛠 Сбой на стороне биржи: "),
    (("JSONDecodeError", "Expecting value"), "📄 Биржа вернула некорректный (не JSON) ответ: "),
    (("KeyError",), "🔑 В ответе биржи не хватает ожидаемого поля: "),
)


def _russian_error_prefix(text):
    for markers, prefix in _ERROR_TRANSLATIONS:
        if any(marker in text for marker in markers):
            return prefix
    return ""  # no recognized pattern — left as-is rather than guessing a misleading translation


def log_error(msg):
    text = str(msg)[:500]
    text = _russian_error_prefix(text) + text
    print("[ERR]", text)
    with state_lock:
        STATE["errors"].append({"t": time.time(), "msg": text[:550]})
    if any(marker in text for marker in _NETWORK_ERROR_MARKERS):
        now = time.time()
        with _network_error_lock:
            _network_error_timestamps.append(now)
            cutoff = now - NETWORK_ALERT_WINDOW_SEC
            while _network_error_timestamps and _network_error_timestamps[0] < cutoff:
                _network_error_timestamps.pop(0)
            count = len(_network_error_timestamps)
            global _network_alert_last_sent
            should_alert = (count >= NETWORK_ALERT_THRESHOLD
                             and now - _network_alert_last_sent >= NETWORK_ALERT_COOLDOWN_SEC)
            if should_alert:
                _network_alert_last_sent = now
        if should_alert:
            window_min = NETWORK_ALERT_WINDOW_SEC // 60
            send_telegram(
                f"⚠️ Сеть нестабильна: {count} сетевых ошибок (Read timed out / ConnectionError) "
                f"за последние {window_min} мин. Сбор данных и бэктесты могут отставать — "
                f"открытые позиции и стопы это не затрагивает.",
                category="network",
            )


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
GET_CANDLES_RATE_LIMIT_RETRIES = int(os.environ.get("VP_GET_CANDLES_RATE_LIMIT_RETRIES", 3))  # v0.99.8 — separate, more generous retry budget specifically for HTTP 429 (Too Many Requests). Confirmed live via an error-log screenshot: many DIFFERENT modules (Volume, Session NY, MSNR) all hit 429 on the SAME symbol (XAU_USDT) within the same minute, consistent with this app's overall concurrent request volume across modules occasionally exceeding Gate.io's rate limit, not a per-symbol problem. A 429 is fundamentally different from a generic 4xx (404/400 are real, final answers unlikely to change) — it's the one status code specifically designed to mean "back off and retry," so treating it the same as "don't retry 4xx/5xx" (the general rule, still correct for every OTHER 4xx/5xx) was the actual bug.
GET_CANDLES_RATE_LIMIT_DELAY = float(os.environ.get("VP_GET_CANDLES_RATE_LIMIT_DELAY", 4.0))  # base seconds between 429 retries — deliberately longer than GET_CANDLES_RETRY_DELAY's 1.5s, since a rate-limit window needs more time to clear than a transient connection blip; doubles per attempt (4s, 8s, 16s) unless Gate.io's own Retry-After header says otherwise


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
    v0.99.8: HTTP 429 (Too Many Requests) now gets its OWN retry budget
    (GET_CANDLES_RATE_LIMIT_RETRIES, longer exponential backoff via
    GET_CANDLES_RATE_LIMIT_DELAY, honoring Gate.io's own Retry-After
    header when present) instead of failing immediately — found from a
    live error-log screenshot showing 429s hitting the SAME symbol
    (XAU_USDT) across three UNRELATED modules (Volume's fetch_candles_
    concurrent, Session NY's process_one, MSNR's own backtest) within
    the same minute, which pointed at this app's overall concurrent
    request volume across modules occasionally exceeding Gate.io's rate
    limit — not a per-symbol or per-module problem, and specifically
    NOT the "don't retry 4xx/5xx" logic below being wrong in general:
    429 is the one status code explicitly designed to mean "back off
    and retry," fundamentally different from a genuine 404/400 (a real,
    final answer unlikely to change). Every OTHER 4xx/5xx status still
    gets zero retries, unchanged."""
    conn_attempt = 0
    rate_limit_attempt = 0
    while True:
        try:
            # v0.99.37/38 — see GLOBAL_HTTP_SEMAPHORE/_global_rate_gate()
            # docstrings above: caps both TOTAL concurrent Gate.io
            # requests and how fast new ones may start, across all 14 of
            # this app's independent thread pools, not just this one.
            with GLOBAL_HTTP_SEMAPHORE:
                _global_rate_gate()
                r = requests.get(
                    f"{GATE_BASE}/futures/usdt/candlesticks",
                    params={"contract": symbol, "interval": interval, "limit": limit},
                    timeout=HTTP_TIMEOUT,
                )
            if r.status_code == 429 and rate_limit_attempt < GET_CANDLES_RATE_LIMIT_RETRIES:
                retry_after = r.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else GET_CANDLES_RATE_LIMIT_DELAY * (2 ** rate_limit_attempt)
                except ValueError:
                    delay = GET_CANDLES_RATE_LIMIT_DELAY * (2 ** rate_limit_attempt)
                rate_limit_attempt += 1
                time.sleep(delay)
                continue
            # v0.99.36 - a live error-log screenshot showed 500 Internal
            # Server Error from api.gateio.ws hitting every module at once
            # (session, session_ny, msnr, ft5, vgi, xau_lg) across
            # unrelated symbols within the same second, right after
            # startup — a genuine transient blip on Gate's side, not a
            # per-request problem. Every OTHER 4xx/5xx still gets zero
            # retries (a real 400/404 won't change on retry), but 5xx
            # specifically means "something broke on the server", which
            # 429 already gets a retry budget for — this closes the same
            # gap for 500-599 in general, reusing the same rate-limit
            # budget/backoff rather than adding a third counter.
            if 500 <= r.status_code < 600 and rate_limit_attempt < GET_CANDLES_RATE_LIMIT_RETRIES:
                rate_limit_attempt += 1
                time.sleep(GET_CANDLES_RATE_LIMIT_DELAY * (2 ** rate_limit_attempt))
                continue
            r.raise_for_status()
            # Gate.io returns oldest->newest already; fields: t,v,c,h,l,o,sum (varies by version)
            return _parse_candles(r.json())
        except RETRYABLE_NETWORK_EXCEPTIONS:
            if conn_attempt < GET_CANDLES_RETRIES:
                conn_attempt += 1
                time.sleep(GET_CANDLES_RETRY_DELAY)
                continue
            raise


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
        rate_limit_attempt = 0
        while True:
            chunk_span = interval_sec * chunk_points
            chunk_end = min(cur + chunk_span, end_ts)
            try:
                # v0.99.37/38 — same GLOBAL_HTTP_SEMAPHORE/_global_rate_
                # gate() as get_candles(), see their docstrings: this
                # function's own chunked-fetch loop is a separate code
                # path that was missing the same global concurrency+rate
                # caps.
                with GLOBAL_HTTP_SEMAPHORE:
                    _global_rate_gate()
                    r = requests.get(
                        f"{GATE_BASE}/futures/usdt/candlesticks",
                        params={"contract": symbol, "interval": interval, "from": cur, "to": chunk_end},
                        timeout=HTTP_TIMEOUT,
                    )
                # v0.99.15 — same 429-retry gap get_candles() already had
                # fixed in v0.99.8, missed here: this function has its OWN
                # separate request loop, so that fix never covered it.
                # Found while investigating a direct report of MSNR's
                # backtest taking far longer than before — a multi-chunk
                # range fetch (this function, used for MSNR's structure/
                # entry candles, session's multi-week backtests, and the
                # "magnified profile" data) previously failed a WHOLE
                # symbol's fetch on the very first 429 hit on ANY chunk,
                # with zero retry, unlike get_candles()'s own single-shot
                # fetches which already retry generously. Checked before
                # applying: doesn't explain a multi-minute HANG on its own
                # (an unretried 429 fails FAST, not slow) — but it's a
                # real, separate gap worth closing regardless, and
                # combined with genuinely heavy concurrent rate-limit
                # pressure across many modules at once, still meaningfully
                # increases how often a symbol's fetch fails outright.
                if r.status_code == 429 and rate_limit_attempt < GET_CANDLES_RATE_LIMIT_RETRIES:
                    retry_after = r.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else GET_CANDLES_RATE_LIMIT_DELAY * (2 ** rate_limit_attempt)
                    except ValueError:
                        delay = GET_CANDLES_RATE_LIMIT_DELAY * (2 ** rate_limit_attempt)
                    rate_limit_attempt += 1
                    time.sleep(delay)
                    continue
                # v0.99.36 — same reasoning as get_candles()'s own 5xx
                # retry added alongside this one: a live error-log
                # screenshot showed 500s from api.gateio.ws hitting this
                # function too (msnr/vgi/xau_lg backtests), simultaneous
                # with plain get_candles() 500s elsewhere in the same
                # cycle — a transient server-side blip, not a per-chunk
                # problem, so it gets the same bounded retry budget.
                if 500 <= r.status_code < 600 and rate_limit_attempt < GET_CANDLES_RATE_LIMIT_RETRIES:
                    rate_limit_attempt += 1
                    time.sleep(GET_CANDLES_RATE_LIMIT_DELAY * (2 ** rate_limit_attempt))
                    continue
                r.raise_for_status()
                break
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 400 and chunk_points > 50:
                    chunk_points = chunk_points // 2  # server rejected this size — shrink, and keep it shrunk for later chunks too
                    continue
                raise
            except RETRYABLE_NETWORK_EXCEPTIONS:
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
    losing the whole cycle, this retry means usually not needing to.
    v0.99.21: also retries on HTTP 429 now (GET_CANDLES_RATE_LIMIT_
    RETRIES/DELAY, honoring Retry-After — same mechanism and constants
    as get_candles()'s own v0.99.8 fix, reused rather than duplicated
    with its own tuning). This function was somehow never given that
    fix when get_candles() got it — confirmed as a real, direct cause of
    a live-reported problem, not just theorized: msnr_build_backtest_
    universe() calls this BEFORE msnr_backtest_loop() ever sets
    STATE["msnr_backtest_running"]=True, so an un-retried 429 here means
    the whole cycle fails before the progress bar (v0.99.15) has any
    chance to show anything at all — worse than the "stuck, no detail"
    problem that progress bar was built to fix, since now there's no
    visible indication a cycle is even being attempted, let alone
    failing. Direct user report: "версия обновилась, но минут 20 ничего
    не происходит, шкалы загрузки нет" — exactly the symptom of this
    exact gap, especially given this session's confirmed sustained
    Gate.io rate-limit pressure across many other endpoints."""
    conn_attempt = 0
    rate_limit_attempt = 0
    while True:
        try:
            # v0.99.38 — same global concurrency+rate caps as get_candles()/
            # get_candles_range() (see GLOBAL_HTTP_SEMAPHORE/_global_rate_
            # gate() docstrings): this function was hitting Gate.io
            # uncapped, same gap as those two had before v0.99.37/38.
            with GLOBAL_HTTP_SEMAPHORE:
                _global_rate_gate()
                r = requests.get(f"{GATE_BASE}/futures/usdt/tickers", timeout=HTTP_TIMEOUT)
            if r.status_code == 429 and rate_limit_attempt < GET_CANDLES_RATE_LIMIT_RETRIES:
                retry_after = r.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else GET_CANDLES_RATE_LIMIT_DELAY * (2 ** rate_limit_attempt)
                except ValueError:
                    delay = GET_CANDLES_RATE_LIMIT_DELAY * (2 ** rate_limit_attempt)
                rate_limit_attempt += 1
                time.sleep(delay)
                continue
            if 500 <= r.status_code < 600 and rate_limit_attempt < GET_CANDLES_RATE_LIMIT_RETRIES:
                rate_limit_attempt += 1
                time.sleep(GET_CANDLES_RATE_LIMIT_DELAY * (2 ** rate_limit_attempt))
                continue
            r.raise_for_status()
            return r.json()
        except RETRYABLE_NETWORK_EXCEPTIONS:
            if conn_attempt < GET_CANDLES_RETRIES:
                conn_attempt += 1
                time.sleep(GET_CANDLES_RETRY_DELAY)
                continue
            raise


def get_last_price(symbol):
    """v0.99.146 — a genuinely FRESH single-symbol quote, deliberately
    NOT get_contract_spec()'s own cached response (up to CONTRACT_SPEC_
    CACHE_TTL_SEC=3600s stale) and NOT a candle close (up to one whole
    candle-interval stale) — used right before opening a real trade to
    catch a signal that's gone stale since detection, and again as the
    basis for an emergency stop if the original one turns out to
    already be invalid. Public, unsigned GET (Gate's own tickers
    endpoint supports filtering to one contract via the query param),
    read-only so safe to retry on the same network exceptions every
    other public endpoint here retries on."""
    for attempt in range(3):
        try:
            with GLOBAL_HTTP_SEMAPHORE:
                _global_rate_gate()
                r = requests.get(f"{GATE_BASE}/futures/usdt/tickers", params={"contract": symbol}, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            if data:
                return float(data[0]["last"])
            return None
        except RETRYABLE_NETWORK_EXCEPTIONS:
            if attempt < 2:
                time.sleep(GET_CANDLES_RETRY_DELAY)
                continue
            raise
    return None


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
    # v0.99.112 — this is a public, unsigned endpoint (no gate_signed_
    # request(), no timestamp/signature to regenerate), so a plain
    # retry-on-timeout loop is enough — read-only, safe to retry.
    last_timeout_error = None
    data = None
    for attempt in range(3):
        try:
            r = requests.get(f"{GATE_BASE}/futures/usdt/contracts/{symbol}", timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_timeout_error = e
            if attempt < 2:
                time.sleep(1)
    if data is None:
        raise last_timeout_error
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


def round_to_tick_directional(price, tick_size, round_up):
    """Same tick-snapping as round_to_tick(), but ALWAYS rounds in one
    direction instead of to the nearest tick — round_up=True always
    rounds UP (ceil), round_up=False always rounds DOWN (floor).
    v0.99.124, per direct user report (screenshot: a real LSW LONG
    trade on CYS_USDT opened fine but its own SL leg came back
    OPENED_TP_SL_FAILED — error 1029 AUTO_TRIGGER_PRICE_LESS_LAST,
    "Trigger.Price must < last_price" — leaving the position with a TP
    but genuinely NO stop-loss at all): Gate's price_orders endpoint
    enforces trigger < last_price for a rule=2 order and trigger >
    last_price for a rule=1 order AT THE EXACT MOMENT OF PLACEMENT.
    Plain round-to-nearest (round_to_tick()) can push a price that was
    correctly on the valid side of current price to the WRONG side by
    up to half a tick — and on a coin with a wide tick size relative to
    price and a tight stop distance (CYS_USDT, plus LSW's own
    deliberately narrow LSW_SL_BUFFER_PCT, especially after 5m entry
    confirmation tightens it further — see LSW_ENTRY_CONFIRM_ENABLED's
    own docstring), that's enough to flip a valid SL into a rejected
    one. Rounding a LONG's SL DOWN (away from current price) and a
    SHORT's SL UP (same direction) keeps the trigger unambiguously on
    the valid side of last_price no matter how close the raw value
    sat to a tick boundary — the tiny (at most one tick) extra distance
    this adds to the stop is a rounding error, not a real risk change,
    and is a trivial cost next to the alternative (a real position left
    with no stop-loss at all, which is what actually happened here).
    Falls back to the raw price unchanged if tick_size is missing/zero,
    same as round_to_tick()."""
    if not tick_size or tick_size <= 0:
        return price
    n = price / tick_size
    n = math.ceil(n) if round_up else math.floor(n)
    return round(n * tick_size, 12)


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
    position setting. Takes `leverage` as a query-string value.
    v0.99.112 — retry_on_timeout=True: setting leverage to the same
    value repeatedly is idempotent (no side-effect risk from a retry,
    unlike order placement), safe to opt into gate_signed_request()'s
    own new retry mechanism."""
    return gate_signed_request(
        "POST", f"/futures/usdt/positions/{symbol}/leverage",
        query_string=f"leverage={leverage}", retry_on_timeout=True,
    )


def compute_margin_usd(size_mode, size_value, wallet_balance=None):
    """Extracted from compute_position_size() (v0.99.102) so the same
    margin-sizing logic is reusable by both that function AND the new
    risk-based leverage derivation in execute_autotrade() — under the
    new model, margin has to be known FIRST (leverage is now DERIVED
    from margin + this signal's own SL distance + the risk target, not
    chosen independently as a fixed constant anymore). Uses AVAILABLE
    balance (not total equity) deliberately — this is an affordability
    check, and you can't allocate margin the account doesn't actually
    have free right now, regardless of what's tied up in other open
    positions. Returns (margin_usd, skip_reason) — skip_reason is None
    on success."""
    if size_mode == "percent":
        if wallet_balance is None:
            return 0, "wallet balance unavailable for percent-based sizing"
        margin_usd = wallet_balance * (size_value / 100.0)
    else:
        margin_usd = size_value
    if margin_usd <= 0:
        return 0, f"computed margin is {margin_usd} — check sizing config/wallet balance"
    # Fixed mode has no built-in relationship to the account balance, so it
    # never naturally scales down — with several positions already open
    # consuming margin, a flat $X request can easily exceed what's actually
    # free, and every attempt fails the same way (INSUFFICIENT_AVAILABLE)
    # until something closes. Check against real availability regardless of
    # mode rather than letting Gate reject it after the fact every time.
    if wallet_balance is not None and margin_usd > wallet_balance * 0.98:
        return 0, (f"computed margin ${margin_usd:.2f} exceeds available balance "
                    f"${wallet_balance:.2f} (with a 2% safety margin) — skipping rather than sending a doomed order")
    return margin_usd, None


def compute_max_safe_leverage(direction, sl_distance_pct, mmr_pct, leverage_cap,
                               safety_margin=None, taker_fee_pct=SCALP_TAKER_FEE_PCT):
    """v0.99.102, per direct user follow-up ("размер позиции может тоже
    автоматом определять, брать минимально возможный процент депозита
    но чтобы плечо позволяло ставить стоп до ликвидации"): finds the
    LARGEST leverage (up to leverage_cap, the contract's own exchange-
    side leverage_max) whose own liquidation buffer still clears
    sl_distance_pct * safety_margin — reusing compute_scalp_
    liquidation_move_pct()'s own formula so this stays consistent with
    the existing liquidation-safety check in execute_autotrade() by
    construction, rather than risking a subtly different reimplemen-
    tation of the same math. That function's own buffer is
    monotonically decreasing in leverage (higher leverage always
    brings liquidation closer, never further), so a plain integer
    sweep from leverage_cap down to 1 finds the answer directly — no
    inversion of the underlying formula's own min()/direction-
    dependent branches needed, which would be a likely source of a
    sign or edge-case bug on math this consequential.
    Returns None if even leverage=1 isn't safe for this SL distance
    (pathological — an extremely wide SL combined with unusually high
    MMR — but the caller must treat it as "skip this trade", not
    silently fall back to something unsafe)."""
    safety_margin = SCALP_SAFETY_MARGIN if safety_margin is None else safety_margin
    if sl_distance_pct is None or sl_distance_pct <= 0:
        return None
    required = sl_distance_pct * safety_margin
    lev_cap = int(leverage_cap) if leverage_cap else 125
    for lev in range(max(lev_cap, 1), 0, -1):
        buf = compute_scalp_liquidation_move_pct(direction, lev, mmr_pct, taker_fee_pct)
        if buf is not None and buf >= required:
            return lev
    return None


def compute_risk_based_position(direction, entry, sl, leverage_cap, mmr_pct, total_equity, risk_pct=None):
    """v0.99.102 — the new, fully-automatic replacement for both manual
    leverage AND manual position-size selection, per direct user
    confirmation ("максимально безопасное плечо → минимальный margin
    под 2% риска, всё автоматически"): finds this signal's own maximum
    SAFE leverage (compute_max_safe_leverage() above), then derives the
    MINIMUM margin needed to still risk exactly risk_pct% of total_
    equity at that leverage.
        risk_amount = total_equity * risk_pct/100
        loss_at_sl  = margin_usd * leverage * sl_distance_pct/100
        => margin_usd = risk_amount / (leverage * sl_distance_pct/100)
    margin and leverage are inversely related for a fixed risk target
    and SL distance — using the highest SAFE leverage available (not
    an arbitrary lower one) minimizes how much capital gets tied up in
    any single trade while keeping the dollar risk exactly fixed,
    rather than the old model where leverage was a flat per-module
    constant with no relationship to the actual SL width of a given
    signal at all.
    Returns (margin_usd, leverage, skip_reason) — skip_reason is None
    on success, otherwise a human-readable string with margin_usd=0,
    leverage=0, matching compute_position_size()'s own convention."""
    risk_pct = AUTOTRADE_RISK_PCT_OF_BALANCE if risk_pct is None else risk_pct
    if not entry or entry <= 0:
        return 0, 0, "некорректная цена входа"
    sl_distance_pct = abs(entry - sl) / entry * 100
    if sl_distance_pct <= 0:
        return 0, 0, "некорректное расстояние до стопа (ноль или отрицательное)"
    leverage = compute_max_safe_leverage(direction, sl_distance_pct, mmr_pct, leverage_cap)
    if leverage is None:
        return 0, 0, (f"даже плечо 1x не удерживает стоп ({sl_distance_pct:.3f}%) "
                       f"в безопасной зоне от ликвидации — сделка пропущена")
    if not total_equity or total_equity <= 0:
        return 0, 0, "не удалось получить баланс счёта для расчёта размера позиции"
    risk_amount = total_equity * risk_pct / 100.0
    margin_usd = risk_amount / (leverage * sl_distance_pct / 100.0)
    return margin_usd, leverage, None


def compute_contracts_from_margin(symbol, entry_price, margin_usd, leverage):
    """Extracted from compute_position_size() (v0.99.102) — the shared
    "given a margin amount and leverage, how many contracts" logic
    (lot-size snapping, the near-minimum-lot oversizing guard), reused
    by both compute_position_size() (legacy size_mode/value path,
    kept for now but no longer called by execute_autotrade()) and the
    new risk-based automatic sizing in execute_autotrade() — margin
    and leverage are computed together there (compute_risk_based_
    position()) before this shared "turn it into contracts" step runs.

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
    if margin_usd is None or margin_usd <= 0 or not leverage or leverage <= 0:
        return 0, 0, 0, f"некорректная маржа ({margin_usd}) или плечо ({leverage})"
    notional_usd = margin_usd * leverage
    multiplier = spec["quanto_multiplier"]
    if multiplier <= 0 or entry_price <= 0:
        return 0, 0, 0, f"некорректная спецификация контракта (multiplier={multiplier}) или цена ({entry_price}) для {symbol}"
    min_size = spec["order_size_min"] or 1
    raw_contracts = notional_usd / (multiplier * entry_price)
    if raw_contracts < min_size:
        min_size_notional = min_size * multiplier * entry_price
        if min_size_notional > notional_usd * 1.5:
            return 0, 0, 0, (f"минимальный лот {symbol} ({min_size} контр. = "
                              f"${min_size_notional:.2f}) более чем в 1.5x превышает "
                              f"расчётный ${notional_usd:.2f} — пропущено, чтобы не завышать риск")
        contracts = min_size  # gap is small enough to accept rounding up to the minimum lot
    else:
        contracts = math.floor(raw_contracts / min_size) * min_size
    actual_notional = contracts * multiplier * entry_price
    return contracts, actual_notional, actual_notional / leverage, None


def compute_position_size(symbol, entry_price, size_mode, size_value, leverage, wallet_balance=None):
    """Turns the configured sizing (percent-of-wallet or flat $ margin) into
    a contract count. margin * leverage = notional; notional / (quanto_
    multiplier * price) = raw contract count, then snapped to the
    contract's own lot step (order_size_min).

    Legacy path (v0.99.102) — no longer called by execute_autotrade(),
    which now uses compute_risk_based_position() + compute_contracts_
    from_margin() directly. Kept defined (not yet deleted) purely as a
    smaller, later cleanup step, matching this session's own established
    "don't necessarily delete everything in one sweep" discipline.

    Returns (contracts, notional_usd, margin_usd, skip_reason). skip_reason
    is None on success, otherwise a human-readable string and contracts=0."""
    margin_usd, skip_reason = compute_margin_usd(size_mode, size_value, wallet_balance)
    if skip_reason:
        return 0, 0, 0, skip_reason
    return compute_contracts_from_margin(symbol, entry_price, margin_usd, leverage)


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
    # v0.99.124 — this call previously passed the raw, un-tick-rounded
    # breakeven_price straight through (place_close_trigger_order()'s
    # own `tick` param only controls decimal FORMATTING there, not
    # snapping to a tick multiple at all) — the exact same failure
    # mode as execute_autotrade()'s own SL placement (see round_to_
    # tick_directional()'s own docstring), just never actually hit
    # before now since a breakeven move is rarer than a fresh open.
    breakeven_price = round_to_tick_directional(breakeven_price, tick, round_up=(direction == "SHORT"))
    try:
        new_sl = place_close_trigger_order(symbol, direction, breakeven_price, sl_rule, tick)
    except Exception as e:
        log_error(f"move_stop_to_breakeven {symbol}: old SL cancelled but new breakeven SL failed to place ({e}) — position may be UNPROTECTED, check manually")
        return None
    return new_sl.get("id") if isinstance(new_sl, dict) else None


def get_futures_wallet_balance():
    """GET /futures/usdt/accounts — returns the USDT futures wallet's
    available balance, used for percent-of-deposit position sizing
    AND for the "can we actually afford this margin" affordability
    check — both genuinely need the FREE/available figure, not total
    equity (you can't allocate margin the account doesn't actually
    have free right now, regardless of what's tied up in other open
    positions).
    v0.99.112 — retry_on_timeout=True: a read-only GET, safe to retry
    (no side effects), opts into gate_signed_request()'s own new retry
    mechanism to survive a transient timeout without wasting an
    otherwise-good signal upstream in execute_autotrade()."""
    data = gate_signed_request("GET", "/futures/usdt/accounts", retry_on_timeout=True)
    return float(data.get("available", 0) or 0)


def get_futures_total_equity():
    """GET /futures/usdt/accounts + /futures/usdt/positions — CONFIRMED
    (realized-basis) account capital, used specifically for risk-based
    leverage/margin sizing in execute_autotrade(). Deliberately NOT the
    same figure as get_futures_wallet_balance()'s own "available" —
    that shrinks the moment another position locks margin away, which
    is exactly the bug the user reported: "Если сделка уже открыта
    какая-то, то баланс становится меньше, из-за этого некорректно
    может определяться плечо... а надо смотреть все равно на всю сумму
    денег на счету."
    v0.99.102 — computed as available + position_margin (free capital
    PLUS whatever's currently locked as margin in open positions), per
    direct user follow-up choosing this over total+unrealised_pnl:
    "available + position_margin (без плавающего PnL, только
    подтверждённый капитал)" — deliberately EXCLUDES unrealised_pnl
    (floating, not-yet-realized gains/losses on open positions), so a
    NEW trade's own risk sizing isn't inflated or deflated by paper
    profit/loss on trades that haven't closed yet. order_margin
    (margin reserved for pending, not-yet-filled orders) is
    deliberately left out too — that capital isn't "in a position"
    yet, and this app's own autotrade flow doesn't leave working
    limit orders sitting around (market entries, price-triggered
    TP/SL) that would tie up order_margin for any meaningful stretch.
    v0.99.106 — CRITICAL FIX, live report: a $80 account with one open
    position (using most of the margin) showed a new trade sized as if
    total equity were only the ~$1.7 still free, not ~$80. Root cause:
    the account endpoint's own "position_margin" field is marked
    DEPRECATED in Gate's own official API changelog (confirmed via
    their own docs: "position_margin marked as deprecated" alongside
    "total field... only applicable to classic futures accounts") —
    on an account using Gate's newer unified/portfolio-margin structure
    (which Gate has been migrating users to), that field can silently
    read 0 or stale regardless of real open-position margin. Switched
    to summing each open position's OWN "margin" field via get_open_
    positions() (GET /futures/usdt/positions) instead — a per-position
    figure, not a deprecated account-level aggregate, so it stays
    correct across both classic and newer account structures.
    v0.99.112 — retry_on_timeout=True: a read-only GET, safe to retry
    (no side effects), opts into gate_signed_request()'s own new retry
    mechanism to survive a transient timeout without wasting an
    otherwise-good signal upstream in execute_autotrade()."""
    data = gate_signed_request("GET", "/futures/usdt/accounts", retry_on_timeout=True)
    available = float(data.get("available", 0) or 0)
    position_margin = sum(float(p.get("margin", 0) or 0) for p in get_open_positions())
    return available + position_margin


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
    size (Gate returns every contract ever touched, most with size=0).
    v0.99.112 — retry_on_timeout=True: read-only, safe to retry."""
    data = gate_signed_request("GET", "/futures/usdt/positions", retry_on_timeout=True)
    return [p for p in data if float(p.get("size", 0) or 0) != 0]


def get_open_price_orders():
    """GET /futures/usdt/price_orders?status=open — every still-pending
    price-triggered (TP/SL) order."""
    return gate_signed_request("GET", "/futures/usdt/price_orders", query_string="status=open")


_unprotected_alerted = set()  # contracts already flagged — avoids re-alerting on every single new trade while the same position stays unprotected
_missing_sl_alerted = set()  # v0.99.124 — same dedup, for the separate "has orders but none of them is a stop-loss" case


def cancel_price_order(order_id):
    """DELETE /futures/usdt/price_orders/{order_id} — cancels one still-
    pending trigger order."""
    return gate_signed_request("DELETE", f"/futures/usdt/price_orders/{order_id}")


def find_open_signal_sl(symbol):
    """Searches every module's own OPEN-signal list (same set has_open_
    signal_any_module() already checks) for one on this symbol, and
    returns (direction, sl, detected_at) from whichever it finds first
    — used by reconcile_positions_and_orders() to recover a stop-loss
    price for an open position whose own SL placement failed at open
    time, so it can be automatically retried rather than just alerted
    about; detected_at feeds that same function's own grace-period
    check (see RECONCILE_GRACE_SEC's own comment). None if no module
    has a matching OPEN record (shouldn't normally happen for a real
    open position, but the caller treats that as "nothing to retry
    with" rather than assuming one)."""
    lists = {
        "signals": STATE["signals"], "scalp_signals": STATE["scalp_signals"],
        "ft5_signals": STATE["ft5_signals"], "msnr_signals": STATE["msnr_signals"],
        "mirror_signals": STATE["mirror_signals"], "lsw_signals": STATE["lsw_signals"],
    }
    with state_lock:
        for lst in lists.values():
            for s in lst:
                if s.get("symbol") == symbol and s.get("status") == "OPEN" and s.get("sl") is not None:
                    return s.get("direction"), s.get("sl"), s.get("detected_at")
    return None


def _newest_open_signal_detected_at(symbol):
    """Same module-list scan as find_open_signal_sl(), but returns just
    the MOST RECENT detected_at across every OPEN signal on this symbol
    (regardless of whether it has an sl recorded) — used by reconcile_
    positions_and_orders() to tell a genuinely-missing TP/SL apart from
    one that simply hasn't landed on Gate's own side yet (see
    RECONCILE_GRACE_SEC's own comment). None if no OPEN signal at all."""
    lists = (STATE["signals"], STATE["scalp_signals"], STATE["ft5_signals"],
             STATE["msnr_signals"], STATE["mirror_signals"], STATE["lsw_signals"])
    newest = None
    with state_lock:
        for lst in lists:
            for s in lst:
                if s.get("symbol") == symbol and s.get("status") == "OPEN":
                    dt = s.get("detected_at")
                    if dt is not None and (newest is None or dt > newest):
                        newest = dt
    return newest


RECONCILE_GRACE_SEC = int(os.environ.get("VP_RECONCILE_GRACE_SEC", 15))  # v0.99.135, per direct user report (screenshot: an auto-heal "восстановлен отсутствовавший стоп-лосс" alert fired on a position whose REAL SL had actually already been placed by execute_autotrade — just hadn't propagated into Gate's own GET /price_orders response yet — leaving TWO live SL orders on one position): execute_autotrade() places the market order, THEN the TP/SL trigger orders, as separate sequential API calls, and reconcile_positions_and_orders() can run (opportunistically, right before the NEXT trade) within that same window before Gate's own read-side reflects the write that already happened. A contract with an OPEN signal detected less than this many seconds ago is given a pass on BOTH checks below (no orders at all, missing SL specifically) for this cycle — genuinely missing protection surfaces on the VERY NEXT reconcile pass regardless, so nothing real goes unprotected for longer than one extra cycle, but a same-second placement race no longer gets treated as a real gap.


def reconcile_positions_and_orders():
    """One combined pass over live positions + live trigger orders,
    fetched once and reused for both checks (rather than two separate
    functions each re-fetching the same data):
    (1) positions with NO attached trigger order at all — alerted via
        Telegram, deduped so the same still-unprotected contract doesn't
        re-alert on every subsequent trade.
    (1b) v0.99.124, per direct user report (screenshot: a real LSW LONG
        on CYS_USDT had its SL leg rejected by Gate at open time —
        AUTO_TRIGGER_PRICE_LESS_LAST, see round_to_tick_directional()'s
        own docstring for the root cause — leaving a position with a TP
        but genuinely no stop-loss): check (1) alone MISSED this case
        entirely, because it only asks "does this contract have ANY
        trigger order," and CYS_USDT did (its TP). This second check
        looks at each contract's OWN trigger orders and its OWN position
        direction (LONG needs a rule=2 order, SHORT needs rule=1) and
        flags a contract that has orders but none of them is actually a
        stop-loss. Unlike (1), this doesn't just alert — it tries to
        AUTO-HEAL: find_open_signal_sl() recovers the original SL price
        from whichever module's own signal record still has it, and a
        fresh placement is attempted with the SAME directional-rounding
        fix that caused the original failure to (hopefully) not recur.
        Success or failure either way is Telegram-alerted, deduped the
        same way as (1) so a still-failing retry doesn't spam.
    v0.99.135, per direct user report (a "восстановлен отсутствовавший
        стоп-лосс" alert fired and left TWO live SL orders on one
        position): both (1) and (1b) now give a contract a pass for
        RECONCILE_GRACE_SEC seconds after its own OPEN signal was first
        detected — execute_autotrade() places TP/SL as separate calls
        right after the market order, and this function can run (the
        opportunistic call happens right before the NEXT trade) inside
        that same narrow window, before Gate's own GET /price_orders
        reflects a placement that already genuinely succeeded. See that
        constant's own comment for the full mechanics.
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
    # v0.99.135 — grace period: a contract whose own OPEN signal was
    # detected within the last RECONCILE_GRACE_SEC seconds gets a pass
    # here even with zero trigger orders yet — execute_autotrade()
    # places TP/SL as separate calls right after the market order, and
    # this check can otherwise run in that same narrow window before
    # they land. See RECONCILE_GRACE_SEC's own comment for the full
    # incident and the "surfaces next cycle regardless" reasoning.
    now = time.time()
    unprotected = [c for c in unprotected
                   if (_newest_open_signal_detected_at(c) or 0) < now - RECONCILE_GRACE_SEC]
    with _scalp_signal_cooldowns_lock:  # reusing an existing lock for this tiny bit of shared state rather than adding a new one
        new_ones = [c for c in unprotected if c not in _unprotected_alerted]
        _unprotected_alerted.intersection_update(unprotected)
        _unprotected_alerted.update(unprotected)
    if new_ones:
        send_telegram(
            f"⚠️ Незащищённые позиции без TP/SL: {', '.join(new_ones)} — проверь вручную на бирже",
            category=None,
        )

    # (1b) — has orders, but none of them is actually a stop-loss for this position's own direction
    triggers_by_contract = {}
    for t in triggers:
        c = t.get("initial", {}).get("contract")
        if c:
            triggers_by_contract.setdefault(c, []).append(t)
    missing_sl_healed = []
    missing_sl_still_failed = []
    for p in positions:
        contract = p.get("contract")
        if not contract or contract in unprotected:
            continue  # already covered by the "no orders at all" case above
        size = float(p.get("size", 0) or 0)
        direction = "LONG" if size > 0 else "SHORT"
        expected_sl_rule = 2 if direction == "LONG" else 1
        contract_triggers = triggers_by_contract.get(contract, [])
        has_sl = any((t.get("trigger", {}) or {}).get("rule") == expected_sl_rule for t in contract_triggers)
        if has_sl:
            continue
        if (_newest_open_signal_detected_at(contract) or 0) >= now - RECONCILE_GRACE_SEC:
            continue  # too soon to tell — its own SL may simply not have landed on Gate's side yet, see RECONCILE_GRACE_SEC's own comment
        found = find_open_signal_sl(contract)
        if not found:
            if contract not in _missing_sl_alerted:
                _missing_sl_alerted.add(contract)
                send_telegram(
                    f"⚠️ {contract}: есть ордер(а), но среди них нет стоп-лосса, и не нашлось "
                    f"записи сигнала, чтобы восстановить его автоматически — проверь вручную на бирже",
                    category=None,
                )
            missing_sl_still_failed.append(contract)
            continue
        sig_direction, sig_sl, _sig_detected_at = found
        try:
            tick = get_contract_spec(contract).get("order_price_round")
        except Exception:
            tick = None
        sl_rounded = round_to_tick_directional(sig_sl, tick, round_up=(sig_direction == "SHORT"))
        try:
            place_close_trigger_order(contract, sig_direction, sl_rounded, expected_sl_rule, tick)
            missing_sl_healed.append(contract)
            _missing_sl_alerted.discard(contract)
            send_telegram(f"✅ {contract}: автоматически восстановлен отсутствовавший стоп-лосс @ {sl_rounded}", category=None)
        except Exception as e:
            log_error(f"reconcile_positions_and_orders: {contract} missing SL, auto-heal retry failed: {e}")
            if contract not in _missing_sl_alerted:
                _missing_sl_alerted.add(contract)
                send_telegram(
                    f"⚠️ {contract}: стоп-лосс отсутствует, автовосстановление тоже не удалось ({e}) — проверь вручную на бирже",
                    category=None,
                )
            missing_sl_still_failed.append(contract)
    if missing_sl_healed:
        log_error(f"reconcile_positions_and_orders: auto-healed missing SL for {len(missing_sl_healed)} contract(s): {missing_sl_healed}")

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


def execute_autotrade(mode, symbol, direction, entry, sl, tp, extra=None, risk_pct_override=None, allow_stack=False):
    """The single entry point every signal source calls to (maybe) fire a
    real trade. `mode` is a short label (e.g. "bounce", "msnr", "scalp")
    used for the auto-trade-enabled toggle lookup and the log. `extra` is
    any signal-specific context worth keeping in the log (reason, interval,
    etc.) — purely informational, not used for trading logic.

    v0.99.102, per direct user request ("надо чтобы размер позиции
    только можно было выбрать" -> then "размер позиции может тоже
    автоматом определять... максимально безопасное плечо -> минимальный
    margin под 2% риска"): leverage and position size are no longer
    caller-supplied at all — both are computed HERE, automatically, for
    EVERY module, via compute_risk_based_position(): the maximum SAFE
    leverage for this specific signal's own SL distance (bounded by
    both the contract's own exchange-side leverage_max and the
    liquidation-safety buffer), then the minimum margin needed to still
    risk exactly AUTOTRADE_RISK_PCT_OF_BALANCE% of confirmed account
    capital (get_futures_total_equity()) at that leverage. This
    entirely replaces the old per-module fixed leverage constants AND
    the shared/scalp-specific AUTOTRADE_SIZE_MODE/VALUE and SCALP_
    SIZE_MODE/VALUE sizing mechanisms — every module now sizes
    identically, driven only by its own SL width, with no manual
    leverage or size choice left anywhere.

    risk_pct_override, v0.99.109: when given, replaces AUTOTRADE_RISK_
    PCT_OF_BALANCE for THIS call only — used by Scalp's own Martingale
    feature (scalp_martingale_multiplier_for_symbol()) to risk a
    multiple of the base % after a losing streak on that symbol,
    resetting to base on a win. None (the default) for every other
    module's own call site — unaffected, still risks the plain base %.

    allow_stack, v0.99.126: when True, the exchange-side duplicate-
    position guard below permits this order through even though the
    symbol already has an open position, PROVIDED that existing
    position is in the SAME direction as this call's own `direction`
    (a deliberate stack, not a conflicting duplicate) — used ONLY by
    MSNR's own add-on ("добір") second position, per direct user
    request ("да нет, сразу делай с автоторговлей"). An OPPOSITE-
    direction existing position still blocks regardless of allow_
    stack — that's a genuine conflict this guard exists to catch, not
    something any caller should be able to wave through. False (the
    default) for every other call site — completely unaffected.

    Always writes exactly one entry to STATE["autotrade_log"], whether it
    trades, skips, or dry-runs, so the log is a complete record of every
    signal that was even considered, not just the ones that fired."""
    record = {
        "time": time.time(), "mode": mode, "symbol": symbol, "direction": direction,
        "entry": entry, "sl": sl, "tp": tp, "leverage": None,
        "dry_run": AUTOTRADE_DRY_RUN, "extra": extra or {},
        "status": None, "detail": None, "contracts": None, "order_id": None,
    }
    lock = _get_symbol_trade_lock(symbol)
    with lock:
        try:
            # total_equity drives the RISK TARGET (2% of confirmed capital,
            # deliberately NOT shrunk by other open positions' locked
            # margin — see get_futures_total_equity()'s own docstring for
            # the full reasoning). wallet_balance (available) is fetched
            # separately, further below, purely as an AFFORDABILITY check
            # once the risk math has already decided on a margin amount —
            # you can't allocate margin the account doesn't actually have
            # free right now, regardless of what total_equity says.
            total_equity = None
            if not AUTOTRADE_DRY_RUN:
                total_equity = get_futures_total_equity()
            else:
                # dry-run still needs a balance figure to show a realistic
                # size/leverage in the log, but shouldn't require live
                # credentials just to preview.
                if GATE_API_KEY and GATE_API_SECRET:
                    try:
                        total_equity = get_futures_total_equity()
                    except Exception:
                        total_equity = 1000.0
                        record["extra"]["balance_note"] = "fetch failed, used nominal $1000 for dry-run estimate"
                else:
                    total_equity = 1000.0
                    record["extra"]["balance_note"] = "no credentials configured, used nominal $1000 for dry-run estimate"

            try:
                leverage_cap = get_contract_spec(symbol).get("leverage_max") or 125
            except Exception as e:
                leverage_cap = 125
                log_error(f"execute_autotrade {symbol}: couldn't fetch leverage_max ({e}), using {leverage_cap}x as a conservative cap")

            # mmr_pct comes from the same STATE["scalp_mmr_map"] the scalp
            # module already refreshes every SCALP_REFRESH_SEC — MMR is a
            # property of the Gate contract itself, not of which module is
            # trading it, so reusing that cache instead of a fresh fetch is
            # correct, not a shortcut. Falls back to SCALP_DEFAULT_MMR_PCT
            # (a deliberately conservative default) for a symbol the scalp
            # universe hasn't covered yet.
            with state_lock:
                mmr_map = STATE.get("scalp_mmr_map", {})
            mmr_pct = mmr_map.get(symbol, SCALP_DEFAULT_MMR_PCT)

            margin, leverage, skip_reason = compute_risk_based_position(
                direction, entry, sl, leverage_cap, mmr_pct, total_equity, risk_pct=risk_pct_override)
            record["leverage"] = leverage
            record["risk_pct"] = round(risk_pct_override if risk_pct_override is not None else AUTOTRADE_RISK_PCT_OF_BALANCE, 4)

            if skip_reason:
                record["status"] = "SKIPPED"
                record["detail"] = skip_reason
                with state_lock:
                    STATE["autotrade_log"].appendleft(record)
                return record

            # Affordability check — the derived margin, however "minimal"
            # by the risk math above, still has to fit inside what's
            # actually FREE right now (not locked in other open positions).
            # total_equity deliberately doesn't shrink from other open
            # positions (the whole point of this redesign), but real order
            # placement obviously still needs real free margin to draw
            # from — this is the same "computed margin exceeds available
            # balance" guard the old sizing path always had, just moved
            # here since margin is no longer computed inside compute_
            # position_size() for this call path.
            wallet_balance = None
            if not AUTOTRADE_DRY_RUN:
                wallet_balance = get_futures_wallet_balance()
            elif GATE_API_KEY and GATE_API_SECRET:
                try:
                    wallet_balance = get_futures_wallet_balance()
                except Exception:
                    pass
            if wallet_balance is not None and margin > wallet_balance * 0.98:
                record["status"] = "SKIPPED"
                record["detail"] = (f"маржа ${margin:.2f} превышает доступный баланс "
                                     f"${wallet_balance:.2f} (с запасом 2%) — сделка пропущена")
                with state_lock:
                    STATE["autotrade_log"].appendleft(record)
                return record

            contracts, notional, actual_margin, skip_reason = compute_contracts_from_margin(symbol, entry, margin, leverage)
            record["contracts"] = contracts
            record["notional_usd"] = round(notional, 2) if notional else notional
            record["margin_usd"] = round(actual_margin, 2) if actual_margin else actual_margin

            if skip_reason:
                record["status"] = "SKIPPED"
                record["detail"] = skip_reason
                with state_lock:
                    STATE["autotrade_log"].appendleft(record)
                return record

            if AUTOTRADE_DRY_RUN:
                record["status"] = "DRY_RUN"
                record["detail"] = f"dry-run: открыл бы {direction} {contracts} контр. по {leverage}x плеча, TP {tp} / SL {sl}"
                with state_lock:
                    STATE["autotrade_log"].appendleft(record)
                return record

            # v0.99.53, per direct user question ("а проверка на уже
            # открытую сделку на бирже есть?"): until now, every duplicate-
            # position guard in this app (has_open_signal_any_module(), and
            # MSNR's own v0.99.50 fix) only checked this app's OWN internal
            # STATE — never the actual exchange. If STATE ever drifts from
            # reality (a position closed on Gate before this app's own
            # outcome-tracking loop caught up, a manual close via the Gate
            # app itself, STATE getting reset/corrupted while a real
            # position stayed open, two app instances sharing one Gate
            # account, etc.) every one of those STATE-only checks would
            # wave a genuinely duplicate order straight through with no way
            # to catch it. This queries the exchange directly, right before
            # placing a new order — the actual ground truth, not this app's
            # belief about it. Placed AFTER the DRY_RUN branch above (a
            # dry-run never touches the real account, nothing to check
            # against) and BEFORE reconcile_positions_and_orders() below
            # (no reason to run that cleanup pass first if this is about to
            # skip anyway). Same fail-open defensive shape as the
            # liquidation-safety check above it: if the exchange query
            # itself fails, log it and proceed rather than blocking every
            # future trade on one flaky API call — this check is additive
            # insurance on top of the existing STATE-based guards, not
            # their replacement, so losing it for one cycle isn't fatal the
            # way losing the STATE-based checks entirely would be.
            try:
                existing_positions = get_open_positions()
                conflicting = next((p for p in existing_positions if p.get("contract") == symbol), None)
                if conflicting:
                    existing_direction = "LONG" if float(conflicting.get("size", 0) or 0) > 0 else "SHORT"
                    if not (allow_stack and existing_direction == direction):
                        record["status"] = "SKIPPED"
                        record["detail"] = f"{symbol} уже есть открытая позиция на бирже — дубль пропущен"
                        with state_lock:
                            STATE["autotrade_log"].appendleft(record)
                        return record
                    # v0.99.126 — deliberate same-direction stack (MSNR
                    # add-on), not a conflicting duplicate. Gate merges a
                    # second same-direction market order into the existing
                    # position (blended average entry, combined size) —
                    # there's no such thing as two independent stacked
                    # positions on one contract, so this proceeds to place
                    # a real order that adds to what's already open rather
                    # than opening a second, separately-tracked position.
                    record["extra"]["stacked_onto_existing"] = True
                    log_error(f"execute_autotrade {symbol}: stacking {direction} onto existing {existing_direction} position (allow_stack=True, mode={mode})")
            except Exception as e:
                log_error(f"execute_autotrade {symbol}: exchange position check failed ({e}), proceeding without it — this is exactly the kind of STATE/exchange desync this check exists to catch, so treat any recurrence as worth investigating")

            # v0.99.146 — BUG FOUND (per direct user report: a signal
            # fired, price had already moved past its own sl by the
            # time this function ran, the trade opened anyway, and the
            # sl leg then failed to place — leaving a real position
            # with nothing but liquidation as its actual stop). A
            # signal's own sl is decided at DETECTION time, from candle
            # data that can be seconds to minutes old by the time this
            # function actually executes (network delay, scan queue,
            # retry backoff). Checked here, right before the market
            # order, using a genuinely FRESH single-symbol quote
            # (get_last_price() — NOT get_contract_spec()'s own cached
            # response, up to CONTRACT_SPEC_CACHE_TTL_SEC=3600s stale,
            # and NOT a candle close, up to one whole candle-interval
            # stale). Per the user's own direct choice ("если цена ушла
            # за стоп то не открывать") — this is the FIRST line of
            # defense; the emergency-stop fallback further below covers
            # the much narrower race where price crosses the sl in the
            # brief window AFTER this check but before the market order
            # actually fills.
            try:
                current_price = get_last_price(symbol)
            except Exception as e:
                current_price = None
                log_error(f"execute_autotrade {symbol}: couldn't fetch a fresh price for the pre-open stale-signal check ({e}) — proceeding without it")
            if current_price is not None:
                price_already_past_sl = ((direction == "LONG" and current_price <= sl)
                                          or (direction == "SHORT" and current_price >= sl))
                if price_already_past_sl:
                    record["status"] = "SKIPPED"
                    record["detail"] = (f"цена ({current_price}) уже за стопом ({sl}) к моменту открытия — "
                                         f"сделка не открыта")
                    send_telegram(
                        f"⚠️ {symbol} ({mode}): сигнал устарел — цена ({current_price}) уже прошла "
                        f"уровень стопа ({sl}) ещё до открытия. Сделка НЕ открыта.",
                        category=None,
                    )
                    with state_lock:
                        STATE["autotrade_log"].appendleft(record)
                    return record

            try:
                reconcile_positions_and_orders()
            except Exception as e:
                log_error(f"execute_autotrade {symbol}: reconcile before open failed: {e}")

            set_leverage(symbol, leverage)
            # v0.99.112, per direct user report (screenshot: a real LONG
            # autotrade attempt ending in bare ERROR with "Read timed
            # out" — 9 such errors logged): place_market_order() itself
            # deliberately does NOT retry on timeout (see gate_signed_
            # request()'s own docstring for why — a retry after a
            # timeout that actually succeeded server-side would place a
            # SECOND, duplicate order). But a bare timeout here still
            # left real ambiguity: did the order land or not? Rather
            # than assume failure and silently waste what might have
            # been a genuinely opened, unprotected position, check the
            # exchange directly — the same ground-truth query the
            # duplicate-position guard above already uses.
            try:
                order = place_market_order(symbol, direction, contracts)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                positions_after = get_open_positions()
                matched = next((p for p in positions_after if p.get("contract") == symbol), None)
                if matched:
                    # It DID land — the timeout was purely on the response,
                    # not the order itself. Synthesize an order record from
                    # the real position so the rest of this flow (TP/SL
                    # placement) proceeds normally instead of leaving a
                    # real, unprotected position with no stop-loss.
                    order = {"id": None, "fill_price": matched.get("entry_price")}
                    record["extra"]["order_timeout_note"] = (
                        f"place_market_order() itself timed out ({e}), but the exchange confirms "
                        f"the position DID open — continuing to TP/SL placement rather than "
                        f"abandoning an unprotected real position")
                    log_error(f"execute_autotrade {symbol}: order placement timed out but position confirmed open on exchange — continuing")
                else:
                    # Genuinely never landed — safe to treat as a real failure,
                    # nothing was opened, no risk of a phantom duplicate.
                    raise
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
            # v0.99.124 — directional rounding, not round_to_tick()'s
            # round-to-nearest: see round_to_tick_directional()'s own
            # docstring for why nearest-rounding can flip a valid SL
            # trigger to the wrong side of last_price and get it
            # rejected by Gate, leaving a real position unprotected.
            tp_rounded = round_to_tick_directional(tp, tick, round_up=(direction == "LONG"))
            sl_rounded = round_to_tick_directional(sl, tick, round_up=(direction == "SHORT"))
            record["tp_rounded"] = tp_rounded
            record["sl_rounded"] = sl_rounded
            tp_order, sl_order, tp_sl_errors = place_tp_sl_orders(symbol, direction, tp_rounded, sl_rounded, tick=tick)
            record["tick"] = tick
            record["tp_order_id"] = tp_order.get("id") if isinstance(tp_order, dict) else None
            record["sl_order_id"] = sl_order.get("id") if isinstance(sl_order, dict) else None
            sl_failed = any(which == "sl" for which, _msg in tp_sl_errors)
            if sl_failed:
                # v0.99.146 — safety net for the narrow race between the
                # pre-open price check above and the market order
                # actually filling: if price crossed sl in that window,
                # the ORIGINAL sl is now invalid and re-trying it (what
                # reconcile_positions_and_orders()'s own v0.99.124 auto-
                # heal would otherwise do on its next cycle) would just
                # fail again for the same reason. Per the user's own
                # direct choice ("выставить маленький стоп если да" — a
                # small protective stop, not an immediate market close):
                # ONE emergency attempt at AUTOTRADE_EMERGENCY_SL_
                # BUFFER_PCT away from a freshly-fetched current price,
                # so the position gets SOME real stop rather than riding
                # to liquidation unprotected.
                try:
                    emergency_price = get_last_price(symbol)
                except Exception as e:
                    emergency_price = None
                    log_error(f"execute_autotrade {symbol}: emergency-SL price fetch failed ({e})")
                emergency_sl_placed = False
                if emergency_price is not None:
                    if direction == "LONG":
                        emergency_sl = emergency_price * (1 - AUTOTRADE_EMERGENCY_SL_BUFFER_PCT / 100)
                    else:
                        emergency_sl = emergency_price * (1 + AUTOTRADE_EMERGENCY_SL_BUFFER_PCT / 100)
                    emergency_sl = round_to_tick_directional(emergency_sl, tick, round_up=(direction == "SHORT"))
                    sl_rule = 2 if direction == "LONG" else 1
                    try:
                        emergency_sl_order = place_close_trigger_order(symbol, direction, emergency_sl, sl_rule, tick)
                        record["sl_order_id"] = emergency_sl_order.get("id") if isinstance(emergency_sl_order, dict) else None
                        record["emergency_sl"] = emergency_sl
                        tp_sl_errors = [pair for pair in tp_sl_errors if pair[0] != "sl"]
                        emergency_sl_placed = True
                        send_telegram(
                            f"⚠️ {symbol} ({mode}): цена ушла за расчётный стоп в момент открытия — "
                            f"выставлен АВАРИЙНЫЙ минимальный стоп у {emergency_sl}. Риск по сделке может "
                            f"быть выше обычного {AUTOTRADE_RISK_PCT_OF_BALANCE}% — стоит проверить вручную.",
                            category=None,
                        )
                    except Exception as e:
                        log_error(f"execute_autotrade {symbol}: emergency SL placement ALSO failed ({e}) — position genuinely unprotected")
                if not emergency_sl_placed:
                    send_telegram(
                        f"🔴 {symbol} ({mode}): КРИТИЧНО — позиция открыта, обычный стоп не встал, "
                        f"аварийный стоп ТОЖЕ не встал. Единственная защита сейчас — ликвидация. "
                        f"Проверь вручную немедленно.",
                        category=None,
                    )
            if tp_sl_errors:
                record["status"] = "OPENED_TP_SL_FAILED"
                record["detail"] = f"позиция открыта, но TP/SL не выставились: {tp_sl_errors} — проверьте вручную"
            else:
                record["status"] = "OPENED"
                record["detail"] = f"открыта {direction} {contracts} контр. по {leverage}x плеча"
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
    so no separate lookup is needed, just checking the same dict again.
    v0.99.121, per direct user request ("Все что торгуется в реальности
    должно и в симуляторе показываться и считать депозит") — this used
    to silently stop recording ANY new trade, from ANY module, the
    moment the paper balance hit zero or went negative (percent-of-
    balance sizing degenerates to 0 margin at a non-positive balance,
    and the old code returned None before ever building the trade
    record). That meant a real trade could keep firing for months while
    the simulator quietly went dark on all of them, with no error or
    indication anything had stopped. Sizing now falls back to
    AUTOTRADE_SIM_START_BALANCE as the basis whenever the CURRENT
    balance isn't positive, so percent-mode sizing stays meaningful
    instead of collapsing to zero — every real trade always gets a
    paper trade recorded, and the balance itself is left free to go
    negative, same as a real account that got wiped out actually would."""
    size_mode = AUTOTRADE_SIZE_MODE if size_mode is None else size_mode
    size_value = AUTOTRADE_SIZE_VALUE if size_value is None else size_value
    with state_lock:
        balance = STATE["sim_balance"]
    sizing_basis = balance if balance > 0 else AUTOTRADE_SIM_START_BALANCE
    if size_mode == "percent":
        margin = sizing_basis * (size_value / 100.0)
    else:
        margin = size_value
    margin = max(margin, 0.01)  # never a zero/negative-size trade — that would be invisible in all practical terms
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
                except RETRYABLE_NETWORK_EXCEPTIONS:
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

        # v0.99.109, per direct user request ("удвоение после
        # стоплосса... классический мартингейл"): the multiplier this
        # SPECIFIC signal actually traded at, frozen here at creation
        # time — a live-updating value would make past signals'
        # displayed multiplier confusingly change as later trades
        # resolve. 1.0 (no change) whenever the feature is off.
        martingale_multiplier = scalp_martingale_multiplier_for_symbol(symbol)
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
            "martingale_multiplier": martingale_multiplier, "autotrade_fired": False,
        }
        with state_lock:
            STATE["scalp_signals"].appendleft(record)
        if AUTOTRADE_ENABLED_SCALP:
            autotrade_result = execute_autotrade("scalp", symbol, direction, entry, sl_price, target_price,
                               extra={"interval": interval, "score": rec["score"]},
                               risk_pct_override=AUTOTRADE_RISK_PCT_OF_BALANCE * martingale_multiplier)
            # v0.99.109 — only a GENUINELY fired real order (not a dry-
            # run preview, a skip, or an error) counts toward the
            # martingale streak in update_scalp_signal_outcomes() below
            # — a signal with no real money at risk shouldn't escalate
            # risk on the NEXT real trade.
            if autotrade_result and autotrade_result.get("status") in ("OPENED", "OPENED_TP_SL_FAILED"):
                with state_lock:
                    record["autotrade_fired"] = True
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


def scalp_martingale_multiplier_for_symbol(symbol):
    """v0.99.109, per direct user request ("удвоение после стоплосса...
    классический мартингейл... если снова стоп, то опять удваивает"):
    the CURRENT risk multiplier for this symbol's NEXT Scalp trade,
    derived from that symbol's own current consecutive-loss streak
    (STATE["scalp_martingale"]) — classic Martingale: 1x base after a
    win or no history, 2x after 1 loss, 4x after 2, 8x after 3, doubling
    again each additional consecutive loss up to SCALP_MARTINGALE_
    MAX_DOUBLINGS, after which it holds at 2^that cap rather than
    continuing to grow (the safety cap, per direct user choice of a
    streak-count cap over a direct max-%-risk cap).
    Deliberately per-SYMBOL, not one shared multiplier across all of
    Scalp — per direct user choice: "отдельный множитель на каждую
    монету (удваивается только следующая сделка по той же монете)" —
    a loss on one coin shouldn't escalate risk on a completely
    unrelated coin's next signal.
    Returns 1.0 (base, no change) if SCALP_MARTINGALE_ENABLED is off —
    every caller can unconditionally multiply by this function's return
    value without its own separate enabled-check."""
    if not SCALP_MARTINGALE_ENABLED:
        return 1.0
    with state_lock:
        mg = STATE["scalp_martingale"].get(symbol)
    if not mg:
        return 1.0
    return float(mg.get("multiplier", 1.0))


def update_scalp_signal_outcomes():
    now = time.time()
    with state_lock:
        open_signals = [s for s in STATE["scalp_signals"] if s["status"] == "OPEN"]
    all_candles = fetch_candles_concurrent([(s["symbol"], s["interval"], 200) for s in open_signals])
    for sig, candles in zip(open_signals, all_candles):
        try:
            if candles is None:
                continue
            scalp_interval_sec = INTERVAL_SECONDS.get(sig["interval"], 300)
            candles = [c for c in candles if c["time"] + scalp_interval_sec <= now]  # v0.98.8: drop still-forming candle
            future = [c for c in candles if c["time"] > sig["time"]]
            entry = sig["entry"]
            direction = sig["direction"]
            mfe_price = sig.get("mfe_price", entry)
            mae_price = sig.get("mae_price", entry)
            result = None
            exit_price = None
            exit_time = None
            sl_price = sig.get("sl_price")  # older signals created before SL existed won't have this — falls back to WIN/TIMEOUT only, same as before
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
                    # v0.99.109, per direct user request ("удвоение
                    # после стоплосса... классический мартингейл"):
                    # only a genuinely-fired real trade (see the
                    # autotrade_fired flag set at signal creation)
                    # updates the streak — a purely informational
                    # signal (autotrade off, dry-run, or the order got
                    # skipped/errored) never had real money at risk, so
                    # its own WIN/LOSS shouldn't escalate risk on the
                    # NEXT real trade. result == "WIN" resets to base;
                    # result == "LOSS" advances the streak (capped at
                    # SCALP_MARTINGALE_MAX_DOUBLINGS) and doubles the
                    # multiplier again from wherever it currently sits.
                    if SCALP_MARTINGALE_ENABLED and sig.get("autotrade_fired") and result in ("WIN", "LOSS"):
                        mg = STATE["scalp_martingale"].setdefault(sig["symbol"], {"streak": 0, "multiplier": 1.0})
                        if result == "LOSS":
                            if mg["streak"] < SCALP_MARTINGALE_MAX_DOUBLINGS:
                                mg["streak"] += 1
                            mg["multiplier"] = 2.0 ** mg["streak"]
                        else:
                            mg["streak"] = 0
                            mg["multiplier"] = 1.0
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


_save_state_file_lock = threading.Lock()  # v0.99.90 — see save_state()'s own docstring for the race this fixes


def save_state():
    """v0.99.90, per a live error report (3 identical "save_state:
    [Errno 2] No such file or directory: '....json.tmp' -> '....json'"
    lines within the same minute): the tmp-write-then-os.replace() pair
    below is a standard atomic-save pattern, but it used to run OUTSIDE
    any lock — only the `data = {...}` snapshot itself was protected by
    state_lock, briefly, above. save_state() is called from ~26
    different places across this app's many independent background
    loops (backtest cycles, live scans, sim-trade sweeps, settings
    changes, etc.), all sharing the exact same tmp_path (no per-call
    unique suffix) — if two callers' save_state() calls overlapped even
    slightly, the SECOND caller's os.replace() would find the tmp file
    already consumed by the FIRST caller's own replace (which atomically
    renames tmp_path away, so it no longer exists under that name),
    throwing exactly the reported ENOENT. Fixed by serializing the
    write+replace pair itself behind a DEDICATED lock (_save_state_
    file_lock, not the broader state_lock) — dedicated specifically so
    a slow disk write never blocks unrelated state-reading/mutating
    code the way reusing state_lock for the I/O itself would; the data
    snapshot above still only needs state_lock briefly, same as before."""
    try:
        with state_lock:
            sim_trades_out = [
                {k: v for k, v in t.items() if k != "_signal_ref"}
                for t in STATE["sim_trades"]
            ]
            data = {
                "overrides": SYMBOL_OVERRIDES,
                "signals": list(STATE["signals"]),
                "scalp_signals": list(STATE["scalp_signals"]),
                "msnr_signals": list(STATE["msnr_signals"]),
                "msnr_symbol_overrides": STATE["msnr_symbol_overrides"],
                "msnr_autotrade_symbols": STATE["msnr_autotrade_symbols"],
                "msnr_autotrade_top_set": STATE["msnr_autotrade_top_set"],
                "ft5_signals": list(STATE["ft5_signals"]),
                "ft5_symbol_overrides": STATE["ft5_symbol_overrides"],
                "mirror_signals": list(STATE["mirror_signals"]),
                "mirror_filtered_signals": list(STATE["mirror_filtered_signals"]),
                "mirror_symbol_overrides": STATE["mirror_symbol_overrides"],
                "mirror_live_universe": STATE["mirror_live_universe"],
                "lsw_signals": list(STATE["lsw_signals"]),
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
        with _save_state_file_lock:
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
        "scalp": STATE["scalp_signals"],
        "msnr": STATE["msnr_signals"],
        "mirror": STATE["mirror_signals"],
        # v0.99.133 — BUG FOUND (per direct user report, "остальные
        # сделки тоже далеко не все попадают в симулятор"): this dict
        # was never updated when LSW got real autotrade wired in
        # (v0.99.120) — every PENDING (still-open) LSW sim trade alive
        # at the moment of a server restart hit `candidates = module_
        # lists.get("lsw")` -> None -> instant "no match" -> silently
        # DROPPED from restored_trades in load_state() below, forever.
        # A real LSW position stayed open on the exchange the whole
        # time; only its paper counterpart vanished. Given how often
        # this app gets restarted during active development, this was
        # a systematic, ongoing loss, not a rare edge case — matches
        # "далеко не все" far better than the add-on gap alone (that
        # one, v0.99.132, only affected the add-on's own OWN entries;
        # this one silently erases ANY still-open LSW trade on every
        # single restart, regardless of module). "ft5" added too for
        # the same completeness, even though FT5 currently never fires
        # real orders at all (see AUTOTRADE_ENABLED_FT5's own comment)
        # — costs nothing now and closes the same gap in advance if
        # that ever changes.
        "lsw": STATE["lsw_signals"], "ft5": STATE["ft5_signals"],
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


def _backfill_mfe_mae(signal_list):
    """Fills in mfe_r/mae_r/mfe_price/mae_price/mfe_r_at_close/mae_r_at_
    close with safe defaults on any signal loaded from persisted state
    that predates these fields — v0.98.11: several outcome-tracking
    functions (FT5, Session, Divergence, EMA, Volume, VGI) access
    sig["mfe_r"]/sig["mae_r"] directly (not via .get()), which is fine
    for signals created AFTER MFE/MAE tracking was added to that
    module, but raises KeyError for older persisted signals that
    predate it — confirmed live via a direct error-log screenshot
    showing exactly this (session_outcome/vgi_outcome: 'mfe_r').
    Patching every individual access site was considered and rejected:
    ~30 occurrences across 6 functions, each edit risking the exact
    line-dropping mistake this session has already made several times
    when touching multi-line blocks — one centralized backfill at the
    single point signals get loaded from disk is safer and covers
    every current and future direct-access site at once, without
    needing to know where they all are."""
    for sig in signal_list:
        sig.setdefault("mfe_r", 0.0)
        sig.setdefault("mae_r", 0.0)
        sig.setdefault("mfe_price", None)
        sig.setdefault("mae_price", None)
        sig.setdefault("mfe_r_at_close", None)
        sig.setdefault("mae_r_at_close", None)
    return signal_list


def load_state():
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        SYMBOL_OVERRIDES.update(data.get("overrides", {}))
        signals = data.get("signals", [])
        scalp_signals = data.get("scalp_signals", [])
        msnr_signals = data.get("msnr_signals", [])
        msnr_symbol_overrides = data.get("msnr_symbol_overrides", {})
        msnr_autotrade_symbols = data.get("msnr_autotrade_symbols", {})
        msnr_autotrade_top_set = data.get("msnr_autotrade_top_set", [])
        ft5_signals = data.get("ft5_signals", [])
        ft5_symbol_overrides = data.get("ft5_symbol_overrides", {})
        mirror_signals = data.get("mirror_signals", [])
        mirror_filtered_signals = data.get("mirror_filtered_signals", [])
        mirror_symbol_overrides = data.get("mirror_symbol_overrides", {})
        mirror_live_universe = data.get("mirror_live_universe", [])
        lsw_signals = data.get("lsw_signals", [])
        autotrade_log = data.get("autotrade_log", [])
        sim_trades = data.get("sim_trades", [])
        risk_autotune_log = data.get("risk_autotune_log", [])
        risk_autotune_last_change = data.get("risk_autotune_last_change", {})
        with state_lock:
            STATE["signals"] = deque(_backfill_mfe_mae(signals), maxlen=SIGNAL_HISTORY)
            STATE["scalp_signals"] = deque(scalp_signals, maxlen=SCALP_SIGNAL_HISTORY)
            STATE["msnr_signals"] = deque(msnr_signals, maxlen=MSNR_SIGNAL_HISTORY)
            STATE["msnr_symbol_overrides"] = msnr_symbol_overrides
            STATE["msnr_autotrade_symbols"] = msnr_autotrade_symbols
            STATE["msnr_autotrade_top_set"] = msnr_autotrade_top_set
            STATE["ft5_signals"] = deque(_backfill_mfe_mae(ft5_signals), maxlen=FT5_SIGNAL_HISTORY)
            STATE["ft5_symbol_overrides"] = ft5_symbol_overrides
            STATE["mirror_signals"] = deque(_backfill_mfe_mae(mirror_signals), maxlen=MIRROR_SIGNAL_HISTORY)
            STATE["mirror_filtered_signals"] = deque(_backfill_mfe_mae(mirror_filtered_signals), maxlen=MIRROR_SIGNAL_HISTORY)
            STATE["mirror_symbol_overrides"] = mirror_symbol_overrides
            STATE["mirror_live_universe"] = mirror_live_universe
            STATE["lsw_signals"] = deque(_backfill_mfe_mae(lsw_signals), maxlen=LSW_SIGNAL_HISTORY)
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
        print(f"Loaded persisted state: {len(SYMBOL_OVERRIDES)} overrides, {len(signals)} signals, {len(scalp_signals)} scalp signals, {len(autotrade_log)} autotrade log entries, {len(restored_trades)} sim trades ({dropped_pending} pending trades couldn't be re-linked and were dropped)")
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
    if category == "hourly" and not TELEGRAM_ALERTS_HOURLY:
        return
    if category == "ft5" and not TELEGRAM_ALERTS_FT5:
        return
    # v0.99.72 — BUG FOUND, per direct user report ("монета не пришла в
    # уведомление телеграм... как оказалось галочки на монете нет"):
    # investigating that report found a SEPARATE, real bug — TELEGRAM_
    # ALERTS_MSNR is properly defined (env default, get_settings()/
    # apply_settings() wiring, a real "Алерты MSNR" checkbox in the UI)
    # but was never actually CHECKED here, unlike every other module's
    # own category. The setting was a dead control: toggling "Алерты
    # MSNR" off in settings had zero effect on whether MSNR messages
    # actually sent — this direction doesn't explain a MISSING
    # notification (a missing check means messages are never blocked,
    # not more likely to be), but it's a real correctness gap found
    # along the way and worth closing regardless. The actual reported
    # symptom's more likely explanation is separate — see msnr_scan_
    # symbol_live()'s own send_telegram() call site, which already
    # documents that it's unconditional and NOT gated by the per-
    # symbol autotrade checkbox — and _telegram_send_queue's own
    # in-memory (not persisted) nature, which can silently lose an
    # already-queued message if the process restarts before the
    # background worker drains it — the same class of background-
    # process-kill issue this app's own MSNR staleness warning already
    # flags separately.
    if category == "msnr" and not TELEGRAM_ALERTS_MSNR:
        return
    if category == "lsw" and not TELEGRAM_ALERTS_LSW:
        return
    if category == "network" and not TELEGRAM_ALERTS_NETWORK:
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
            except RETRYABLE_NETWORK_EXCEPTIONS as e:
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
                # v0.99.67 — BUG FOUND, per direct user report with
                # screenshots ("возле сделок я не вижу rr, я не вижу
                # средний rr по всем сделкам, я вижу просто в тексте
                # rr2"): `rr` above is THIS symbol's own tuned value
                # (bounce_rr/breakout_rr, from optimize_symbol()'s own
                # per-symbol grid search over PARAM_GRID_RR — genuinely
                # varies symbol to symbol, unlike the flat header text
                # that was showing) — it was used to compute sl/tp right
                # above, then silently discarded: never stored on the
                # record itself. Every OTHER RR-bearing module (VGI,
                # Scalp, EMA/DIV's own reverse mode, XAU LG since
                # v0.99.66) stores its own per-trade rr; Volume/bounce/
                # breakout was the one place that got skipped. Now
                # stored so the signals table can show it per-trade and
                # a real avg/median can be computed from actual trades,
                # not just echo whatever the global RR/RR_BREAKOUT
                # constant happens to be right now.
                record = {
                    "symbol": symbol,
                    "direction": sig["direction"],
                    "reason": sig["reason"],
                    "price": sig["price"],
                    "entry": sig["price"],
                    "sl": sl,
                    "tp": tp,
                    "risk": risk,
                    "rr": rr,
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
                                       extra={"reason": sig["reason"]})
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
    except RETRYABLE_NETWORK_EXCEPTIONS as e:
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
    vp_interval_sec = INTERVAL_SECONDS.get(INTERVAL, 3600)
    for sig, candles in zip(active, all_candles):
        try:
            if candles is None:
                continue
            candles = [c for c in candles if c["time"] + vp_interval_sec <= now]  # v0.98.8: drop still-forming candle
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

            # Timeout removed per direct request — see the same removal in
            # update_divergence_outcomes()'s comment for the full reasoning
            # (applied consistently across every module).
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

    # v0.99.67, per direct user report ("возле сделок я не вижу rr, я
    # не вижу средний rr по всем сделкам, я вижу просто в тексте rr2"):
    # bounce/breakout RR is auto-tuned per SYMBOL (optimize_symbol()'s
    # own grid search over PARAM_GRID_RR) and genuinely varies trade to
    # trade — the header was showing one flat global RR/RR_BREAKOUT
    # constant instead of anything real. Now aggregates the actual
    # per-trade "rr" field (only just started being stored on the
    # record itself — see the record-construction fix in scan_symbol())
    # into avg/median/p25/p75, same shape EMA/DIV's own rr_all already
    # uses. Trades closed before this fix won't have "rr" set — they're
    # silently excluded (not shown as 0), same "don't fabricate history
    # that wasn't recorded" stance every other agg() helper in this
    # file already takes for a newly-added field.
    def _agg_rr(subset):
        vals = [s["rr"] for s in subset if s.get("rr") is not None]
        if not vals:
            return None
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        return {"avg": round(sum(vals) / n, 3), "median": round(vals_sorted[n // 2], 3),
                "p25": round(vals_sorted[int(n * 0.25)], 3),
                "p75": round(vals_sorted[min(int(n * 0.75), n - 1)], 3), "n": n}

    by_reason = {}
    for reason in ("bounce", "breakout"):
        rc = [s for s in closed if s.get("reason") == reason]
        rw = sum(1 for s in rc if s["result"] == "WIN")
        rl = sum(1 for s in rc if s["result"] == "LOSS")
        rt = rw + rl
        by_reason[reason] = {"wins": rw, "losses": rl, "total": rt, "winrate": round(rw / rt * 100, 1) if rt else None,
                              "rr": _agg_rr(rc)}

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
        "rr_all": _agg_rr(closed),
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
                if SCALP_SIGNALS_ENABLED:
                    with state_lock:
                        scalp_recs_snapshot = dict(STATE["scalp_recommendations"])
                    top_recs = sorted(
                        [(sym, rec) for sym, rec in scalp_recs_snapshot.items() if rec],
                        key=lambda x: -x[1]["score"]
                    )[:SCALP_SIGNAL_TOP_N]
                    futs += [ex.submit(scan_symbol_scalp_signal, sym, rec) for sym, rec in top_recs]
                for _ in as_completed(futs):
                    pass
            if VOLUME_PROFILE_ENABLED:
                update_signal_outcomes()
                auto_tune_cycle(universe)
            if SCALP_SIGNALS_ENABLED:
                update_scalp_signal_outcomes()
            sweep_sim_trades()
            save_state()
            t1 = time.time()
            with state_lock:
                STATE["last_scan_finished"] = t1
                STATE["last_scan_duration"] = round(t1 - t0, 1)
        except Exception as e:
            log_error(f"scan_loop: {e}\n{traceback.format_exc()}")
        time.sleep(max(5, SCAN_INTERVAL_SEC))


def build_hourly_stats_report():
    vp_s = compute_signal_stats()
    scalp_s = compute_scalp_signal_stats()

    def wr(x):
        return f"{x}%" if x is not None else "-"

    br = vp_s.get("by_reason", {}) or {}
    bounce = br.get("bounce", {}) or {}
    breakout = br.get("breakout", {}) or {}
    vp_line = (f"<b>Volume</b>: {wr(vp_s['winrate'])} ({vp_s['wins']}W/{vp_s['losses']}L) · "
               f"открытых {vp_s['open']} · bounce {wr(bounce.get('winrate'))}/breakout {wr(breakout.get('winrate'))}")

    scalp_line = (f"<b>Скальпинг</b>: {wr(scalp_s['win_rate'])} ({scalp_s['wins']}W/{scalp_s['losses']}L/{scalp_s['timeouts']}TIMEOUT) · "
                  f"открытых {scalp_s['open']}") if SCALP_SIGNALS_ENABLED else None

    lines = [f"📊 Часовая статистика (v{APP_VERSION})", vp_line]
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
# EMA_SL_ATR_MULT, DIV_SL_ATR_MULT, SCALP_SL_BUFFER_MULT, SESSION_SL_MULT
# (stop width), SESSION_REVERSE_RR/EMA_TP_PCT/DIV_TP_PCT (target extension),
# and DIV_INVERT_SIGNALS/EMA_INVERT_SIGNALS/SESSION_INVERT_SIGNALS (direction).
# Per direct user request for FULL automation including reverse — the
# safeguards below (min sample sizes, bounded step sizes, cooldowns) aren't
# a hedge against that choice, just how "automatic" avoids being self-
# destructive on noisy data: a fixed formula chasing every small sample
# would thrash a parameter back and forth on noise alone.
# v0.98.4: Session gained MFE/MAE tracking (update_session_signal_outcomes())
# specifically so SESSION_SL_MULT and SESSION_REVERSE_RR (previously a
# hardcoded "2", never tunable at all) could join the other modules' full
# overshoot/target-extend treatment instead of only ever being changed by
# hand — this used to be a known, permanent gap; it isn't anymore.
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

RISK_AUTOTUNE_MSNR_MAX_RR_BOUNDS = (5.5, 15.0)  # v0.99.11 — lower bound deliberately kept above MSNR_FALLBACK_RR (4.0): caught via behavioral testing that a cap set BELOW fallback_rr is self-defeating (the fallback trade it falls through to would itself exceed the "cap" it was supposed to enforce). Upper bound just gives room to relax the cap if the data doesn't actually support tightening it.


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


def _risk_autotune_msnr_max_rr(pooled_trades, current_max_rr, setter):
    """MSNR-specific rule: per direct user observation (SPCX — trades
    with rr>6 consistently hit stop) that a genuine opposite-level TP
    can sit so far away the trade structurally rarely reaches it before
    reversing. Uses msnr_rr_bucket_stats() (pooled across ALL symbols'
    backtest trades — a single symbol's own sample is usually too small
    to bucket reliably) to find the LOWEST RR bucket that's actually
    failing its own breakeven, then steps MSNR_MAX_RR toward that
    bucket's lower edge — not straight to it, same bounded-step
    philosophy as every other nudge here, so one noisy pass can't swing
    the cap wildly.
    "Failing" means: enough closed trades in that bucket (>= RISK_
    AUTOTUNE_MIN_SAMPLE) AND its own win-rate sits below the breakeven
    win-rate for that bucket's own ACTUAL average realized rr (not the
    bucket's lower boundary — caught via behavioral testing that using
    the lower edge breaks down for the first bucket, whose lo=0 implies
    a nonsensical 100% breakeven requirement and made the rule fire
    almost unconditionally on realistic data).
    If no bucket is clearly failing, leaves the cap alone — this rule
    only ever tightens the cap off solid evidence, it doesn't guess at
    loosening it back up (unlike the tp_extend-style rules elsewhere,
    which nudge in both directions off MFE data): a cap that's too
    tight just costs some upside on trades that would have won anyway,
    a cap that's too loose keeps letting the reported problem through —
    the two mistakes aren't symmetric, so this stays one-directional
    on purpose."""
    if not RISK_AUTOTUNE_ENABLED:
        return
    if not _risk_autotune_cooldown_ok("msnr_max_rr", RISK_AUTOTUNE_COOLDOWN_SEC):
        return
    buckets = msnr_rr_bucket_stats(pooled_trades)
    failing_edges = []
    for b in buckets:
        if b["n"] < RISK_AUTOTUNE_MIN_SAMPLE or b["winrate"] is None or not b["avg_rr"]:
            continue
        breakeven = 100.0 / (1.0 + b["avg_rr"])
        if b["winrate"] < breakeven:
            failing_edges.append(b["lo"])
    if not failing_edges:
        return
    target = min(failing_edges)
    lo, hi = RISK_AUTOTUNE_MSNR_MAX_RR_BOUNDS
    if current_max_rr <= target:
        return  # already at or below the failing edge, nothing to tighten
    step = min(RISK_AUTOTUNE_TP_STEP_RATIO * current_max_rr, current_max_rr - target)
    new_value = round(max(lo, min(hi, current_max_rr - step)), 2)
    if new_value == current_max_rr:
        return
    setter(new_value)
    _risk_autotune_mark("msnr_max_rr")
    _risk_autotune_log("msnr", "msnr_max_rr", current_max_rr, new_value,
                        f"failing bucket edge={target} (winrate below breakeven, n>={RISK_AUTOTUNE_MIN_SAMPLE})",
                        sum(b["n"] for b in buckets))


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


def _risk_autotune_tp_extend(module, param_key, current_tp_pct, win_mfe_r, current_rr, sample_n, setter, bounds=None):
    """Nudges a fixed TP_PCT (EMA_TP_PCT / DIV_TP_PCT) — or, since v0.98.4,
    a directly RR-expressed target like Session's SESSION_REVERSE_RR —
    toward matching the R-multiple winning trades actually reach before
    closing (win_mfe_r — pass mfe_r_wins_at_close specifically, NOT the
    full-24h-window MFE, since that includes post-close movement that
    isn't tradeable under the current exit logic and the app's own UI
    already labels it "не для оценки конкретной сделки"). If wins
    consistently run well past the R-multiple the current target sits
    at (current_rr — pass rr_all's median or avg, or the target's own
    current value for a module like Session where the target IS
    directly an RR with no separate %-of-price translation needed), the
    target is cutting profit short: extend it. If wins rarely get
    anywhere near it, the target may be unrealistic: trim it. Mirrors
    _risk_autotune_sl_mult()'s two-directional nudge, just for the
    reward side instead of the risk side.
    Since SL is ATR-based (varies per trade) while TP_PCT is one fixed %
    for everyone, R and TP_PCT move proportionally — scaling TP_PCT by
    (win_mfe_r / current_rr) is the direct translation, bounded to a
    max step per pass same as every other nudge here.
    bounds defaults to RISK_AUTOTUNE_TP_PCT_BOUNDS (the existing EMA/
    DIV %-of-price range) if not given — Session passes its own RR-scale
    bounds instead, since a valid RR range (e.g. 0.5-5) and a valid
    %-of-price range (0.3%-5%) share nothing but both happening to be
    "some positive number.\""""
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
    lo, hi = bounds if bounds is not None else RISK_AUTOTUNE_TP_PCT_BOUNDS
    new_value = round(min(hi, max(lo, current_tp_pct * ratio)), 5)
    if new_value == current_tp_pct:
        return
    setter(new_value)
    _risk_autotune_mark(param_key)
    _risk_autotune_log(module, param_key, current_tp_pct, new_value,
                        f"win_mfe_r={win_mfe_r:.3f} current_rr={current_rr:.3f} ratio={ratio:.3f}", sample_n)


# --- setters: each applies the change AND persists it via save_settings(),
# same pattern the settings API endpoint itself already uses ---

def _set_scalp_min_rr(v):
    global SCALP_MIN_RR
    SCALP_MIN_RR = v
    save_settings()


def _set_scalp_sl_buffer_mult(v):
    global SCALP_SL_BUFFER_MULT
    SCALP_SL_BUFFER_MULT = v
    save_settings()


def _set_ft5_invert(v):
    global FT5_INVERT_SIGNALS
    FT5_INVERT_SIGNALS = v
    save_settings()


def _set_msnr_max_rr(v):
    global MSNR_MAX_RR
    MSNR_MAX_RR = v
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


def risk_autotune_pass():
    """One tuning pass across all four modules. Each module's checks are
    wrapped separately so one module's bad data doesn't block the rest."""
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
        # v0.98.10: per the same direct user request as VGI's block above.
        # FT5 already has its own daily grid-search auto-optimizer
        # (ft5_optimize_symbol()), which is arguably a MORE thorough form
        # of parameter tuning than this pass's usual overshoot-nudge
        # style — so the only genuinely NEW lever here is the reverse
        # flag itself, using the MFE/MAE data FT5 gained this round.
        # Deliberately does NOT tune FT5_STOPLOSS_PCT: FT5's own "RR"
        # meaning is DEFINED relative to it (rr = pnl_pct/(stoploss_pct*
        # 100), see update_ft5_signal_outcomes()'s own comment) — nudging
        # the stoploss itself would retroactively change what every
        # already-recorded trade's RR even means, and would also need
        # coordinating with the grid-search optimizer's own use of it
        # (FT5_RANK_PRIOR_TARGET's pseudo-loss level). Left alone rather
        # than risking a comparably subtle new inconsistency.
        s = compute_ft5_signal_stats()
        winrate = s.get("winrate")
        closed_n = (s.get("wins", 0) or 0) + (s.get("losses", 0) or 0)
        loss_mae = s.get("mae_r_losses_at_close")
        rr_ref = s.get("rr_median")
        if winrate is not None and closed_n and rr_ref:
            _risk_autotune_reverse("ft5", "ft5_invert_signals", FT5_INVERT_SIGNALS, winrate, rr_ref, closed_n, _set_ft5_invert,
                                    avg_loss_mae_r=loss_mae["avg"] if loss_mae else None)
    except Exception as e:
        log_error(f"risk_autotune ft5: {e}")

    try:
        # v0.99.52, per direct user request ("уберём не работу, оставим
        # для вида, мне кажется без неё будет лучше"): disabled — kept
        # commented rather than deleted in case a future session wants
        # it back. Root reasoning from the conversation that led here:
        # this pools trades across ALL ~180 backtested symbols into one
        # global RR-bucket table, but a bucket's pooled n (e.g. n=156
        # for the 7-10R bucket) divided across that many symbols is
        # under one trade per symbol on average — not a real per-symbol
        # sample, just noise that happens to average out smoothly at
        # the pooled level. Adjusting a single GLOBAL MSNR_MAX_RR off
        # that pooled-but-per-symbol-thin evidence risks exactly the
        # "looks fine in aggregate, wrong for the one symbol it's
        # actually capping" failure mode this whole session's per-
        # symbol filters (skip_rr_min, skip_sl_pct_min, Kelly leverage,
        # stress_test_failed) were built specifically to avoid at the
        # per-symbol level — this global knob was the one place that
        # reasoning was never applied.
        # The rr_buckets table itself stays fully displayed in the UI
        # (api_msnr_status() computes it independently of this call,
        # straight from msnr_backtest_results_raw) — informational only
        # now, doesn't feed back into MSNR_MAX_RR or anything else.
        # v0.99.11: per direct user request to tune MSNR_MAX_RR off
        # statistics rather than a one-off manual observation — see
        # _risk_autotune_msnr_max_rr()'s own docstring for the full
        # reasoning. Pools trades across every symbol's own backtest
        # results (msnr_backtest_results_raw is keyed by symbol) rather
        # than tuning per-symbol, since MSNR_MAX_RR is a single global
        # cap, not a per-symbol optimized param like min_leg_atr/
        # qm_zone_pct. v0.99.23: switched from msnr_backtest_results to
        # the _raw variant — the former now has each symbol's own skip_
        # rr_min-failing trades already filtered out (per direct user
        # request, see msnr_optimize_symbol()), which would quietly
        # starve THIS pooled rule of exactly the evidence it exists to
        # catch if left pointed at the filtered copy.
        # with state_lock:
        #     all_results = list(STATE["msnr_backtest_results_raw"].values())
        # pooled_trades = [t for sym_trades in all_results for t in sym_trades]
        # if pooled_trades:
        #     _risk_autotune_msnr_max_rr(pooled_trades, MSNR_MAX_RR, _set_msnr_max_rr)
        pass
    except Exception as e:
        log_error(f"risk_autotune msnr: {e}")


def risk_autotune_loop():
    while True:
        try:
            if RISK_AUTOTUNE_ENABLED:
                risk_autotune_pass()
        except Exception as e:
            log_error(f"risk_autotune_loop: {e}")
        time.sleep(max(300, RISK_AUTOTUNE_INTERVAL_SEC))


# ============================================================================


# ============================================================================
# EXPERIMENTAL: MSNR — Malaysian SNR / "Storyline" gold strategy — functions
# (constants are up top, see that block's own header comment for the full
# OCL/A-shape/V-shape/SBR/RBS/QM translation from the source material)
# ============================================================================
def msnr_build_pivots(structure_candles, pivot_left=MSNR_PIVOT_LEFT, pivot_right=MSNR_PIVOT_RIGHT,
                       min_leg_atr=MSNR_MIN_LEG_ATR, atr_period=MSNR_ATR_PERIOD):
    """Single walk-forward pass over structure_candles (MSNR_STRUCTURE_TF,
    oldest first) building confirmed OCL pivots off the CLOSE line — never
    high/low, per the source's "Open-Close Level" definition. A close-pivot
    at bar j only becomes confirmed once bar j+pivot_right has been seen
    (same no-lookahead confirmation delay every other pivot-based
    detector in this file uses). Alternates strictly A/V (a new A-shape can't follow
    another A-shape — the intervening V is what makes it a genuine
    impulsive leg) and only keeps a pivot whose distance from the
    previous opposite pivot is >= min_leg_atr x ATR(atr_period) at that
    point, i.e. a real "Storyline" leg, not chop.
    v0.99.42 - CRITICAL FIX (lookahead): confirm_time used to be
    structure_candles[confirm_idx]["time"] — the PIVOT BAR'S OWN
    timestamp — even though the pivot isn't actually confirmed until
    pivot_right MORE structure bars have printed (that's the entire
    point of pivot_right: you can't know bar confirm_idx was a local
    extreme until you've seen what came after it). msnr_detect_signals()
    activates a pivot the moment entry_candles' walk reaches confirm_
    time, so the old value let it treat a level as tradeable up to
    pivot_right x MSNR_STRUCTURE_TF early (2h at the current 1h/
    pivot_right=2 defaults) — both in backtesting (inflating win-rate/
    avg-RR on trades that used information not really available yet)
    and in live scanning (msnr_scan_symbol_live() runs this exact same
    function), a real lookahead bug this function's own docstring
    claimed not to have. Fixed to the close time
    of the actual confirming bar: structure_candles[confirm_idx +
    pivot_right]["time"] + <structure interval seconds> — matches the
    exact "has this bar closed yet" convention msnr_scan_symbol_live()
    itself already uses one function over (`c["time"] + s_interval_sec
    <= now`).
    Returns a list of {"type": "A"|"V", "price": close, "confirm_time": ts},
    oldest first."""
    n = len(structure_candles)
    if n < atr_period + pivot_left + pivot_right + 2:
        return []
    closes = [c["close"] for c in structure_candles]
    tr = _true_range_series(structure_candles)
    atr = _atr_series(tr, atr_period)
    structure_interval_sec = INTERVAL_SECONDS.get(MSNR_STRUCTURE_TF, 3600)
    pivots = []
    last_price = None
    last_type = None
    for confirm_idx in range(pivot_left, n - pivot_right):
        cc_close = closes[confirm_idx]
        atr_here = atr[confirm_idx] if confirm_idx < len(atr) and atr[confirm_idx] else None
        if not atr_here:
            continue
        is_high = (all(cc_close >= closes[confirm_idx - j] for j in range(1, pivot_left + 1)) and
                   all(cc_close >= closes[confirm_idx + j] for j in range(1, pivot_right + 1)))
        is_low = (all(cc_close <= closes[confirm_idx - j] for j in range(1, pivot_left + 1)) and
                  all(cc_close <= closes[confirm_idx + j] for j in range(1, pivot_right + 1)))
        # v0.99.42 — see the docstring above: this is the actual moment
        # the pivot becomes knowable, not the pivot bar's own time.
        confirm_time = structure_candles[confirm_idx + pivot_right]["time"] + structure_interval_sec
        if is_high and last_type != "A":
            leg = abs(cc_close - last_price) if last_price is not None else None
            if leg is None or leg >= min_leg_atr * atr_here:
                pivots.append({"type": "A", "price": cc_close, "confirm_time": confirm_time})
                last_price, last_type = cc_close, "A"
        elif is_low and last_type != "V":
            leg = abs(cc_close - last_price) if last_price is not None else None
            if leg is None or leg >= min_leg_atr * atr_here:
                pivots.append({"type": "V", "price": cc_close, "confirm_time": confirm_time})
                last_price, last_type = cc_close, "V"
    return pivots


def msnr_detect_signals(structure_candles, entry_candles, pivot_left=MSNR_PIVOT_LEFT, pivot_right=MSNR_PIVOT_RIGHT,
                         min_leg_atr=MSNR_MIN_LEG_ATR, atr_period=MSNR_ATR_PERIOD,
                         qm_zone_pct=MSNR_QM_ZONE_PCT, qm_lookback=MSNR_QM_LOOKBACK_BARS,
                         sl_buffer_mult=MSNR_SL_BUFFER_MULT, fallback_rr=MSNR_FALLBACK_RR):
    """Combined walk-forward pass, no lookahead — mirrors detect_session_
    manipulation() in spirit. Builds confirmed A-
    shape/V-shape OCL pivots off structure_candles as it goes (via
    msnr_build_pivots(), pre-computed since it doesn't depend on
    entry_candles at all), then walks entry_candles watching for a QM
    (sweep through the currently-active A or V level, then close back on
    the origin side within qm_lookback bars) — the SBR/RBS entry the
    source actually trades. TP is the OTHER active level of the pair
    (the "Storyline" target) ONLY if that level is still genuinely ahead
    of price (on the correct side of entry) — a pivot confirmed long ago
    can end up anywhere relative to current price by the time a much-
    later signal fires, and using it regardless of side produced invalid
    trades (TP below SL on a LONG — found via direct user chart review
    of a backtest trade, see v0.99.4). Falls back to a fixed RR
    (fallback_rr) whenever the paired level isn't confirmed yet OR isn't
    on the correct side of entry.
    v0.99.11 added, v0.99.68 REMOVED: a cap (MSNR_MAX_RR) that ALSO
    fell back to fallback_rr whenever the paired level was valid but
    would produce rr > max_rr. Per direct user request ("в оригинале
    по задумке автора эта стратегия msnr ловит движения с очень
    большим rr, даже если winrate около 20-30, у нас так не
    получается"): that cap was silently substituting a much smaller
    MSNR_FALLBACK_RR=4.0 target for ANY genuinely-far opposite level,
    directly preventing the large-RR/low-winrate trades this strategy
    was designed around — and keeping msnr_symbol_rr_skip_min()'s own
    per-symbol statistical test (exactly the right tool for "is this
    RR bucket actually profitable for THIS symbol despite a low
    win-rate") blind to that entire RR range, since it never saw a
    trade's true RR once this had already substituted a capped one.
    Trusting that per-symbol filter fully now instead of a blanket
    global ceiling that couldn't tell a genuinely unreachable target
    from a genuinely rare-but-profitable one.
    A level only fires once per "reign" (consumed on signal) — replaced by the next
    confirmed pivot of that type resets it.
    Returns (signals, pivots). signals: list of dicts with index (into
    entry_candles), time, direction, entry, sl, tp, level, level_type."""
    pivots = msnr_build_pivots(structure_candles, pivot_left, pivot_right, min_leg_atr, atr_period)
    signals = []
    if not entry_candles:
        return signals, pivots
    pi = 0
    active_a = None
    active_v = None
    a_fired = False
    v_fired = False
    n_p = len(pivots)
    for i, c in enumerate(entry_candles):
        while pi < n_p and pivots[pi]["confirm_time"] <= c["time"]:
            piv = pivots[pi]
            if piv["type"] == "A":
                if active_a is None or piv["price"] != active_a["price"]:
                    active_a = piv
                    a_fired = False
            else:
                if active_v is None or piv["price"] != active_v["price"]:
                    active_v = piv
                    v_fired = False
            pi += 1

        cluster = entry_candles[max(0, i - qm_lookback + 1): i + 1]
        # v0.99.59, per direct user request ("второй фильтр" — volume
        # confirmation on the sweep, discussed as the more-in-the-
        # pattern-itself alternative to the time-of-day filter):
        # this candle's own volume relative to the MEAN volume of the
        # MSNR_VOLUME_LOOKBACK_BARS bars immediately before it
        # (deliberately excluding c itself — including it would let a
        # single huge-volume sweep partially inflate its own baseline).
        # Computed unconditionally here (once per bar, not duplicated
        # in the A-shape/V-shape blocks below) since it only depends on
        # i/c, not on direction — attached to whichever signal (if any)
        # actually fires on this candle. None near the very start of
        # the series where there's no lookback window yet, or if that
        # window's own volumes happen to sum to zero (matches msnr_
        # symbol_volume_skip_below()'s own "can't judge, don't touch
        # the trade" stance for a None ratio).
        vol_window = entry_candles[max(0, i - MSNR_VOLUME_LOOKBACK_BARS):i]
        vol_avg = (sum(cc["volume"] for cc in vol_window) / len(vol_window)) if vol_window else None
        volume_ratio = round(c["volume"] / vol_avg, 3) if vol_avg and vol_avg > 0 else None

        if active_a is not None and not a_fired:
            level = active_a["price"]
            swept = [cc["high"] for cc in cluster if cc["high"] > level]
            if swept and c["close"] < level:
                sweep_extreme = max(swept)
                if level > 0 and (sweep_extreme - level) / level <= qm_zone_pct:
                    entry = c["close"]
                    # v0.99.104 — see MSNR_SL_BUFFER_MULT's own comment for
                    # the full "why" (frequent premature stop-outs, the old
                    # extreme*(1±tiny_pct) formula barely widened the stop
                    # past the sweep's own extreme at all). raw_risk is the
                    # sweep's OWN natural entry-to-extreme distance; the
                    # actual risk/SL scales with how far that sweep already
                    # moved, same "multiply the real risk distance" design
                    # XAU_LG_SL_BUFFER_MULT already uses.
                    raw_risk = sweep_extreme - entry
                    risk = raw_risk * sl_buffer_mult
                    sl = entry + risk
                    if risk > 0:
                        # TP is the paired V-shape ONLY if it's actually still
                        # ahead of price (below entry, for a SHORT) — a
                        # V-shape confirmed long ago can sit anywhere price
                        # has been since, including above the current entry
                        # once a later uptrend leg passed it. Using a stale
                        # level on the wrong side of entry produced nonsense
                        # trades (TP below SL on a LONG, found via direct
                        # user screenshot review of a backtest trade) — a
                        # target that isn't a genuine unmet objective isn't
                        # a valid Storyline pair, so fall back to fixed RR
                        # instead.
                        # v0.99.68 — REMOVED the "AND doesn't imply an rr
                        # past the cap" half of this check, per direct user
                        # request: "в оригинале по задумке автора эта
                        # стратегия msnr ловит движения с очень большим rr,
                        # даже если winrate около 20-30, у нас так не
                        # получается." MSNR_MAX_RR (rr_cap above) used to
                        # silently swap ANY genuinely-far opposite level for
                        # a much smaller MSNR_FALLBACK_RR=4.0 fixed target —
                        # directly preventing the strategy from ever taking
                        # the large-RR/low-winrate trades it was designed
                        # around, and — worse — keeping msnr_symbol_rr_
                        # skip_min()'s own per-symbol statistical test (which
                        # is exactly the right tool for "is this RR bucket
                        # actually profitable for THIS symbol despite a low
                        # win-rate") blind to that entire RR range, since it
                        # never saw a trade's true RR once this had already
                        # substituted a capped one. Full trust now placed in
                        # that per-symbol statistical filter instead of a
                        # blanket global ceiling — msnr_symbol_rr_skip_min()
                        # will correctly reject a high-RR bucket for a
                        # symbol where it's actually failing breakeven, and
                        # correctly allow it through for one where it isn't,
                        # which a fixed cap can never distinguish. rr_cap/
                        # MSNR_MAX_RR itself is left fully defined (still
                        # wired through settings/UI) in case a future
                        # session wants to reintroduce a cap deliberately —
                        # nothing in signal generation reads it anymore.
                        opp = active_v["price"] if active_v is not None else None
                        opp_valid = opp is not None and opp < entry
                        tp = opp if opp_valid else entry - risk * fallback_rr
                        signals.append({
                            "index": i, "time": c["time"], "direction": "SHORT",
                            "entry": entry, "sl": sl, "tp": tp,
                            "level": level, "level_type": "A",
                            "opposite_level": opp if opp_valid else None,
                            "volume_ratio": volume_ratio,
                        })
                        a_fired = True

        if active_v is not None and not v_fired:
            level = active_v["price"]
            swept = [cc["low"] for cc in cluster if cc["low"] < level]
            if swept and c["close"] > level:
                sweep_extreme = min(swept)
                if level > 0 and (level - sweep_extreme) / level <= qm_zone_pct:
                    entry = c["close"]
                    # v0.99.104 — mirrors the SHORT branch above, see its
                    # own comment for the full reasoning.
                    raw_risk = entry - sweep_extreme
                    risk = raw_risk * sl_buffer_mult
                    sl = entry - risk
                    if risk > 0:
                        # v0.99.68 — same removal as the SHORT branch above
                        # (see its own comment for the full reasoning): no
                        # longer checks implied RR against rr_cap, only that
                        # the paired A-shape is still a genuine unmet target
                        # ahead of price.
                        opp = active_a["price"] if active_a is not None else None
                        opp_valid = opp is not None and opp > entry
                        tp = opp if opp_valid else entry + risk * fallback_rr
                        signals.append({
                            "index": i, "time": c["time"], "direction": "LONG",
                            "entry": entry, "sl": sl, "tp": tp,
                            "level": level, "level_type": "V",
                            "opposite_level": opp if opp_valid else None,
                            "volume_ratio": volume_ratio,
                        })
                        v_fired = True

    signals.sort(key=lambda s: s["index"])
    return signals, pivots


def msnr_track_outcome(entry_candles, sig, max_wait_bars=300):
    """Walks forward from sig['index']+1 looking for TP/SL touch — SL
    checked first on any bar covering both, same conservative convention
    as track_session_outcome()."""
    n = len(entry_candles)
    for k in range(sig["index"] + 1, min(n, sig["index"] + 1 + max_wait_bars)):
        c = entry_candles[k]
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


def msnr_detect_addon_signals(addon_candles, primary_signals, qm_zone_pct=MSNR_QM_ZONE_PCT,
                               qm_lookback=MSNR_QM_LOOKBACK_BARS, sl_buffer_mult=MSNR_SL_BUFFER_MULT):
    """v0.99.126 — the "добір" (add-on) second position, per direct
    user-forwarded trade screenshot from the strategy's own author (see
    MSNR_ADDON_ENABLED's own comment for the full context and the
    DETECTION/BACKTEST-ONLY caveat).
    For each already-fired primary signal (from msnr_detect_signals(),
    on MSNR_ENTRY_TF), scans addon_candles (coarser, MSNR_ADDON_TF) for
    the FIRST fresh QM sweep+reject against the SAME level, occurring
    strictly AFTER the primary signal's own time — same sweep-then-
    close-back-inside logic as the primary detector's own A-shape/
    V-shape branches, just replayed on the add-on timeframe and
    restricted to one level instead of walking a live pivot stream.
    Shares the primary signal's own tp (same Storyline target, per the
    source's own "> Target h1 V-shape" for both positions) — only
    entry/sl differ, from wherever the add-on's own fresh sweep
    occurred. At most ONE add-on per primary signal (first fresh M30
    QM found after it) — the source's own examples show exactly two
    positions per idea, not an unbounded add-on chain.
    Returns a list of signal dicts in the SAME shape msnr_detect_
    signals() itself returns, plus "is_addon": True and "primary_time"
    linking back to the primary signal it's attached to."""
    addon_signals = []
    for psig in primary_signals:
        level = psig["level"]
        level_type = psig["level_type"]
        direction = psig["direction"]
        after_time = psig["time"]
        for i, c in enumerate(addon_candles):
            if c["time"] <= after_time:
                continue
            cluster = addon_candles[max(0, i - qm_lookback + 1): i + 1]
            if level_type == "A":  # SHORT add-on, mirrors msnr_detect_signals()'s own A-shape branch
                swept = [cc["high"] for cc in cluster if cc["high"] > level]
                if not (swept and c["close"] < level):
                    continue
                sweep_extreme = max(swept)
                if not (level > 0 and (sweep_extreme - level) / level <= qm_zone_pct):
                    continue
                entry = c["close"]
                risk = (sweep_extreme - entry) * sl_buffer_mult
                sl = entry + risk
            else:  # LONG add-on, mirrors the V-shape branch
                swept = [cc["low"] for cc in cluster if cc["low"] < level]
                if not (swept and c["close"] > level):
                    continue
                sweep_extreme = min(swept)
                if not (level > 0 and (level - sweep_extreme) / level <= qm_zone_pct):
                    continue
                entry = c["close"]
                risk = (entry - sweep_extreme) * sl_buffer_mult
                sl = entry - risk
            if risk <= 0:
                continue
            addon_signals.append({
                "index": i, "time": c["time"], "direction": direction,
                "entry": entry, "sl": sl, "tp": psig["tp"],
                "level": level, "level_type": level_type,
                "opposite_level": psig.get("opposite_level"),
                "is_addon": True, "primary_time": after_time,
            })
            break  # one add-on per primary signal, first fresh M30 QM found
    return addon_signals


def msnr_run_backtest(structure_candles, entry_candles, **params):
    """Runs msnr_detect_signals(**params) + msnr_track_outcome() over the
    result and returns the full per-trade list (time/direction/entry/sl/
    tp/level/rr/result). The shared core behind both a plain single-
    params backtest and msnr_optimize_symbol()'s grid search — params
    are whichever of msnr_detect_signals()'s own kwargs (min_leg_atr,
    qm_zone_pct, qm_lookback, ...) the caller wants to override; anything
    not given keeps msnr_detect_signals()'s own module-default."""
    sigs, _pivots = msnr_detect_signals(structure_candles, entry_candles, **params)
    results = []
    for sig in sigs:
        result, exit_time = msnr_track_outcome(entry_candles, sig)
        risk = abs(sig["entry"] - sig["sl"])
        reward = abs(sig["tp"] - sig["entry"])
        rr = round(reward / risk, 2) if risk > 0 else None
        results.append({
            "time": sig["time"], "direction": sig["direction"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
            "level": sig["level"], "level_type": sig["level_type"],
            "opposite_level": sig.get("opposite_level"),
            "result": result, "exit_time": exit_time, "rr": rr,
            "volume_ratio": sig.get("volume_ratio"),
        })
    return results


def msnr_backtest_symbol(symbol, days=MSNR_BACKTEST_DAYS, **params):
    """Fetches MSNR_BACKTEST_DAYS of both MSNR_STRUCTURE_TF and MSNR_
    ENTRY_TF history and runs msnr_run_backtest() over the whole window.
    Structure candles are fetched with extra lookback (structure TF is
    coarser, so this stays cheap) so the earliest entry-TF bars already
    have a real A/V pair to test against. Accepts the same param
    overrides as msnr_detect_signals — used both for a plain module-
    defaults backtest and, via msnr_optimize_symbol(), a specific
    symbol's autotuned params. Deliberately left untouched by the
    v0.99.126 add-on feature (see msnr_addon_backtest_symbol() instead)
    — this stays the primary-only path msnr_optimize_symbol()'s own
    grid search depends on."""
    now = time.time()
    structure_start = now - (days + 20) * 86400
    structure_candles = get_candles_range(symbol, MSNR_STRUCTURE_TF, structure_start, now)
    entry_start = now - days * 86400
    entry_candles = get_candles_range(symbol, MSNR_ENTRY_TF, entry_start, now)
    if len(structure_candles) < MSNR_ATR_PERIOD + 10 or len(entry_candles) < 10:
        return []
    return msnr_run_backtest(structure_candles, entry_candles, **params)


def msnr_addon_backtest_symbol(symbol, days=MSNR_BACKTEST_DAYS):
    """v0.99.126 — separate from msnr_backtest_symbol() deliberately
    (see that function's own docstring): fetches structure/entry/add-on
    (MSNR_STRUCTURE_TF/MSNR_ENTRY_TF/MSNR_ADDON_TF) history over the
    same window, runs msnr_detect_signals() for the primary trades, then
    msnr_detect_addon_signals() for the add-on ("добір") second position
    on each — tracking each pool's outcome on its OWN candle series
    (primary on entry_candles, add-on on addon_candles, since an add-on
    signal's own "index" refers into addon_candles). Returns (primary_
    results, addon_results), same per-trade dict shape as msnr_run_
    backtest()'s own results, each with "is_addon" already set."""
    now = time.time()
    structure_start = now - (days + 20) * 86400
    structure_candles = get_candles_range(symbol, MSNR_STRUCTURE_TF, structure_start, now)
    entry_start = now - days * 86400
    entry_candles = get_candles_range(symbol, MSNR_ENTRY_TF, entry_start, now)
    addon_candles = get_candles_range(symbol, MSNR_ADDON_TF, entry_start, now)
    if len(structure_candles) < MSNR_ATR_PERIOD + 10 or len(entry_candles) < 10:
        return [], []
    sigs, _pivots = msnr_detect_signals(structure_candles, entry_candles)
    primary_results = []
    for sig in sigs:
        result, exit_time = msnr_track_outcome(entry_candles, sig)
        risk = abs(sig["entry"] - sig["sl"])
        reward = abs(sig["tp"] - sig["entry"])
        rr = round(reward / risk, 2) if risk > 0 else None
        primary_results.append({
            "time": sig["time"], "direction": sig["direction"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
            "level": sig["level"], "level_type": sig["level_type"],
            "opposite_level": sig.get("opposite_level"),
            "result": result, "exit_time": exit_time, "rr": rr,
            "is_addon": False,
        })
    addon_results = []
    if MSNR_ADDON_ENABLED and addon_candles and sigs:
        addon_sigs = msnr_detect_addon_signals(addon_candles, sigs)
        for asig in addon_sigs:
            result, exit_time = msnr_track_outcome(addon_candles, asig)
            risk = abs(asig["entry"] - asig["sl"])
            reward = abs(asig["tp"] - asig["entry"])
            rr = round(reward / risk, 2) if risk > 0 else None
            addon_results.append({
                "time": asig["time"], "direction": asig["direction"],
                "entry": asig["entry"], "sl": asig["sl"], "tp": asig["tp"],
                "level": asig["level"], "level_type": asig["level_type"],
                "opposite_level": asig.get("opposite_level"),
                "result": result, "exit_time": exit_time, "rr": rr,
                "is_addon": True, "primary_time": asig["primary_time"],
            })
    return primary_results, addon_results


def msnr_ranking_score(r_values, losses_count, z=None):
    """Lower-confidence-bound on mean R — same technique and reasoning as
    ft5_ranking_score() (see that function's own docstring for the full
    multi-iteration story of why raw mean/avg_pnl isn't enough), adapted
    from "% pnl" to "R multiple": score = mean - t_critical * stderr,
    with max(0, MSNR_RANK_PRIOR_TARGET - losses_count) synthetic -1R
    pseudo-losses blended in first. MSNR's structural loss is already
    exactly -1R by construction (the stop defines what 1R even means),
    so — unlike FT5, which needed a lookup at its fixed stoploss_pct —
    the prior needs no external lookup at all. Guards a small all-win
    combo (a handful of lucky signals, zero real losses YET) from
    outranking a larger, steadier one purely because it hasn't happened
    to lose yet; 2+ real losses are trusted as-is."""
    n = len(r_values) if r_values else 0
    if n == 0:
        return -999
    prior_n = max(0, MSNR_RANK_PRIOR_TARGET - losses_count)
    prior_r = r_values + [-1.0] * prior_n
    pn = len(prior_r)
    mean = sum(prior_r) / pn
    if pn < 2:
        return mean
    zz = z if z is not None else t_critical(pn - 1)
    var = sum((r - mean) ** 2 for r in prior_r) / (pn - 1)
    stderr = math.sqrt(var) / math.sqrt(pn)
    return mean - zz * stderr


def _msnr_filter_checkpoint(trades, symbol, leverage_ceiling):
    """v0.99.86, per direct user request ("хочу видеть не только сделок
    до и после фильтров, а так же винрейт и доход до и после, чтобы
    понимать эффективность фильтров"): a reusable snapshot of {n,
    winrate, income} for a given trade list, taken at each filter
    checkpoint in msnr_optimize_symbol() below. Before this, the only
    per-filter visibility was a trade COUNT delta (rr_filtered_count
    etc) — no way to tell whether a filter that removed, say, 8 trades
    actually IMPROVED the remaining set's winrate/income or just
    shrank the sample for no real gain.
    Income is computed the same honest way the final display number is
    — a FRESH msnr_optimal_leverage_for_symbol() search against THIS
    checkpoint's own trade list, not the symbol's final leverage reused
    across every checkpoint. Reusing one fixed leverage would silently
    conflate "did this filter change the edge" with "does the FINAL
    leverage happen to suit this intermediate set" — using each
    checkpoint's own best leverage answers the question actually being
    asked: "if you traded exactly this set, on its own merits, what
    would it look like."
    Returns {"n": int, "winrate": float|None, "income_pct": float|None}
    — None values propagate the same "not enough evidence" meaning
    msnr_compound_return()/msnr_summarize_backtest() already use, not
    a silent 0."""
    closed = [t for t in trades if t.get("result") in ("WIN", "LOSS")]
    if not closed:
        return {"n": 0, "winrate": None, "income_pct": None}
    summary = msnr_summarize_backtest(trades)
    lev = msnr_optimal_leverage_for_symbol(trades, leverage_ceiling, symbol=symbol)
    compound = msnr_compound_return(trades, leverage=lev)
    return {
        "n": len(closed),
        "winrate": summary["win_rate"],
        "income_pct": compound["return_pct"] if compound else None,
    }


def msnr_filter_by_min_rr(trades, min_rr=None):
    """v0.99.141 — "a 1:2 minimum risk-to-reward filter is standard"
    (repeated across independent sources researched for Sweep's own
    filters, applies just as well here): a UNIFORM floor applied the
    SAME way to every symbol, deliberately separate from msnr_symbol_
    rr_skip_min/max above (those derive a per-symbol threshold from
    where THIS symbol's own trades statistically stop paying off — a
    different question from "is a 1:2 floor a good idea everywhere").
    A trade with no computed rr (shouldn't normally happen) is kept —
    nothing to judge isn't a reason to drop it."""
    min_rr = min_rr if min_rr is not None else MSNR_MIN_RR_FILTER
    return [t for t in trades if t.get("rr") is None or t["rr"] >= min_rr]


def msnr_filter_by_htf_trend(trades, bias_series, htf_interval_sec):
    """v0.99.141 — same higher-timeframe trend concept as LSW's own
    lsw_filter_signals_by_htf_trend() (v0.99.121), reused here via the
    shared lsw_htf_bias_at() lookup rather than duplicating that logic:
    a LONG only survives if the HTF bias at its own entry time is UP or
    NEUTRAL, a SHORT only survives if it's DOWN or NEUTRAL. A trade
    whose own HTF bar hadn't closed yet (bias is None) is dropped too —
    conservative, matching LSW's own version. Reads "time" (not
    "entry_time" — MSNR's own trade dicts use a different key than
    LSW's signal dicts) and "direction", both already present on every
    MSNR trade dict."""
    kept = []
    for t in trades:
        bias = lsw_htf_bias_at(bias_series, t["time"], htf_interval_sec)
        if bias is None:
            continue
        if t["direction"] == "LONG" and bias == "DOWN":
            continue
        if t["direction"] == "SHORT" and bias == "UP":
            continue
        kept.append(t)
    return kept


def _msnr_recompute_summary_score(best, best_results):
    """v0.99.26 — shared recompute step reused by every post-hoc filter
    in msnr_optimize_symbol() (skip_rr_min, liquidation, skip_sl_pct_
    min): keeps trades/wins/losses/timeouts/winrate/avg_rr/median_rr/
    expectancy_r and score in sync with whatever subset of best_results
    survived filtering, in ONE place instead of near-identical copies
    at each filter step that could quietly drift apart over time."""
    filtered_summary = msnr_summarize_backtest(best_results)
    best["trades"] = filtered_summary["n"]
    best["wins"] = filtered_summary["wins"]
    best["losses"] = filtered_summary["losses"]
    best["timeouts"] = filtered_summary["timeouts"]
    best["winrate"] = filtered_summary["win_rate"]
    best["avg_rr"] = filtered_summary["avg_rr"]
    best["median_rr"] = filtered_summary["median_rr"]
    best["expectancy_r"] = filtered_summary["expectancy_r"]
    r_values = [t["rr"] for t in best_results if t["result"] == "WIN" and t["rr"] is not None]
    r_values += [-1.0] * filtered_summary["losses"]
    best["score"] = round(msnr_ranking_score(r_values, filtered_summary["losses"]), 4) if r_values else None


def msnr_optimize_symbol(symbol, days=MSNR_BACKTEST_DAYS):
    """Grid search over (min_leg_atr, qm_zone_pct, qm_lookback) —
    MSNR_PARAM_GRID_MIN_LEG_ATR x MSNR_PARAM_GRID_QM_ZONE_PCT x
    MSNR_PARAM_GRID_QM_LOOKBACK, 27 combos. Candles fetched ONCE per
    symbol; msnr_run_backtest() is pure CPU per combo (no network calls
    inside the grid loop), same cost shape as ft5_optimize_symbol()'s
    36-combo search. Selected by msnr_ranking_score() rather than raw
    win-rate or avg_rr, for the same reason FT5 needed it: a lucky small
    sample, or wins/losses landing unevenly across RR, shouldn't
    outrank a larger steadier combo just because its raw average looks
    higher. Falls back to the middle of the grid (~module defaults) if
    no combo clears MSNR_MIN_BACKTEST_TRADES closed trades.
    Returns (override_dict, trades_list, raw_trades_list) — trades_list
    is the winning combo's backtest with skip_rr_min-failing (v0.99.23),
    beyond-liquidation (v0.99.26), and skip_sl_pct_min-failing (v0.99.26)
    trades already filtered out, in that order (see below); raw_trades_
    list is the SAME winning combo's backtest UNFILTERED, kept
    separately for the global pooled-across-symbols MSNR_MAX_RR autotune
    and the /api/msnr/status rr_buckets display — those deliberately
    need the full picture (including whatever this symbol's own filters
    just removed) since they're a different mechanism judging RR
    badness pooled across the WHOLE universe, not this symbol alone;
    filtering per-symbol first would quietly starve that pooled
    evidence."""
    now = time.time()
    structure_start = now - (days + 20) * 86400
    structure_candles = get_candles_range(symbol, MSNR_STRUCTURE_TF, structure_start, now)
    entry_start = now - days * 86400
    entry_candles = get_candles_range(symbol, MSNR_ENTRY_TF, entry_start, now)
    if len(structure_candles) < MSNR_ATR_PERIOD + 10 or len(entry_candles) < 10:
        # v0.99.97, live crash report ("not enough values to unpack
        # (expected 3, got 2)"), repeated for MRNA_USDT specifically:
        # this early-exit path (insufficient candle history to even
        # attempt the grid search — e.g. a newly-listed contract with
        # too little historical data yet) had drifted out of sync with
        # this function's own documented 3-tuple contract (override,
        # trades_list, raw_trades_list), returning only 2 values. The
        # sole caller, msnr_backtest_symbol(), always unpacks assuming
        # 3 — a symbol landing here crashed that unpacking on every
        # single backtest cycle, not a transient issue. Fixed to match
        # the documented contract: both trade lists are empty (there's
        # no backtest to report), not just the override.
        return {"error": "not enough history"}, [], []
    best = None
    best_score = None
    best_results = []
    tried = []
    for min_leg_atr in MSNR_PARAM_GRID_MIN_LEG_ATR:
        for qm_zone_pct in MSNR_PARAM_GRID_QM_ZONE_PCT:
            for qm_lookback in MSNR_PARAM_GRID_QM_LOOKBACK:
                results = msnr_run_backtest(structure_candles, entry_candles,
                                             min_leg_atr=min_leg_atr, qm_zone_pct=qm_zone_pct,
                                             qm_lookback=qm_lookback)
                tried.append(len(results))
                closed = [r for r in results if r["result"] in ("WIN", "LOSS")]
                if len(closed) < MSNR_MIN_BACKTEST_TRADES:
                    continue
                wins = sum(1 for r in closed if r["result"] == "WIN")
                losses_count = len(closed) - wins
                r_values = [r["rr"] for r in closed if r["result"] == "WIN" and r["rr"] is not None]
                r_values += [-1.0] * losses_count
                score = msnr_ranking_score(r_values, losses_count)
                if best is None or score > best_score:
                    summary = msnr_summarize_backtest(results)
                    best = {
                        "min_leg_atr": min_leg_atr, "qm_zone_pct": qm_zone_pct, "qm_lookback_bars": qm_lookback,
                        "trades": len(results), "wins": wins, "losses": losses_count,
                        "timeouts": len(results) - len(closed),
                        "winrate": summary["win_rate"], "avg_rr": summary["avg_rr"],
                        "median_rr": summary["median_rr"], "expectancy_r": summary["expectancy_r"],
                        "score": round(score, 4), "optimized_at": now, "candles_used": len(entry_candles),
                    }
                    best_score = score
                    best_results = results
    if best is None:
        mid_atr = MSNR_PARAM_GRID_MIN_LEG_ATR[len(MSNR_PARAM_GRID_MIN_LEG_ATR) // 2]
        mid_zone = MSNR_PARAM_GRID_QM_ZONE_PCT[len(MSNR_PARAM_GRID_QM_ZONE_PCT) // 2]
        mid_lookback = MSNR_PARAM_GRID_QM_LOOKBACK[len(MSNR_PARAM_GRID_QM_LOOKBACK) // 2]
        best_results = msnr_run_backtest(structure_candles, entry_candles,
                                          min_leg_atr=mid_atr, qm_zone_pct=mid_zone, qm_lookback=mid_lookback)
        raw_results = best_results
        combos = len(MSNR_PARAM_GRID_MIN_LEG_ATR) * len(MSNR_PARAM_GRID_QM_ZONE_PCT) * len(MSNR_PARAM_GRID_QM_LOOKBACK)
        leverage_ceiling = msnr_symbol_contract_max_leverage(symbol)
        best = {
            "min_leg_atr": mid_atr, "qm_zone_pct": mid_zone, "qm_lookback_bars": mid_lookback,
            "trades": len(best_results), "wins": 0, "losses": 0, "timeouts": 0,
            "winrate": None, "avg_rr": None, "median_rr": None, "expectancy_r": None, "score": None,
            "optimized_at": now, "candles_used": len(entry_candles), "skip_rr_min": None,
            "skip_rr_max": None,
            "skip_sl_pct_min": None, "liquidation_filtered_count": 0, "skip_hours": [],
            "raw_closed_n": 0, "rr_filtered_count": 0, "sl_filtered_count": 0, "hours_filtered_count": 0,
            "skip_volume_below": None, "volume_filtered_count": 0,
            "filter_checkpoints": [],
            "effective_leverage": msnr_symbol_effective_leverage(symbol),
            "leverage_ceiling": leverage_ceiling,
            "optimal_leverage": msnr_optimal_leverage_for_symbol(best_results, leverage_ceiling, symbol=symbol),
            "note": f"insufficient closed trades across all {combos} combos tried "
                    f"(max {max(tried) if tried else 0}, need {MSNR_MIN_BACKTEST_TRADES}); "
                    f"using middle-of-grid defaults",
        }
    else:
        # v0.99.86, per direct user request ("много слабых результатов
        # в msnr, по 50 сделок а доход околонулевой... отсечение
        # всегда убыточного диапазона RR, как снизу так и сверху...
        # хочу видеть винрейт и доход до и после [каждого фильтра]"):
        # leverage_ceiling/effective_leverage moved up here (used to sit
        # right before the liquidation filter) — every checkpoint below
        # needs leverage_ceiling for its own Kelly search, not just the
        # liquidation filter.
        best["effective_leverage"] = msnr_symbol_effective_leverage(symbol)
        best["leverage_ceiling"] = msnr_symbol_contract_max_leverage(symbol)
        # v0.99.57, per direct user follow-up ("теперь количество сделок
        # снизится и монеты могут перестать проходить по выборке"):
        # captured HERE, before any filter below runs — this symbol's
        # true closed-trade sample size, independent of how many later
        # get excluded by any filter. msnr_rank_by_winrate_sample()/
        # msnr_compute_live_universe() gate eligibility on THIS field,
        # not wins+losses — a symbol shouldn't lose its shot at ranking
        # just because filters progressively shrink the DISPLAYED
        # win/loss count.
        best["raw_closed_n"] = best["wins"] + best["losses"]
        raw_results = best_results
        # v0.99.86 — the checkpoint chain: one snapshot per stage
        # transition (not two per filter) — each filter's "before" is
        # exactly the PREVIOUS filter's "after," so this only costs
        # ONE fresh leverage-search+compound-sim per filter, not two.
        # "raw" is the baseline BEFORE any per-symbol filter has run
        # (the winning grid combo's own unfiltered trade list).
        checkpoints = [{"stage": "raw", **_msnr_filter_checkpoint(best_results, symbol, best["leverage_ceiling"])}]
        # v0.99.22/v0.99.79/v0.99.86: derive this symbol's own RR range
        # off the winning combo's own trades (not re-run per grid combo
        # — needlessly expensive, and the winning combo's own trades
        # are what's actually traded). v0.99.79 had disabled the old
        # ONE-SIDED version entirely ("Skip RR>3, давай подобную
        # проверку тоже уберем, пока важно все RR торговать") — this
        # re-enables filtering, but as msnr_symbol_rr_range()'s
        # genuinely TWO-SIDED (floor AND ceiling) replacement, not a
        # plain revert to the old rule; see that function's own
        # docstring for why a one-sided cutoff couldn't catch the
        # reported pattern (large, trustworthy samples with a middling
        # winrate but near-zero income — a bad low-RR region dragging
        # the average down just as much as a bad high-RR one).
        # Deliberately computed off the FULL unfiltered sample before
        # any filtering — filtering first would shrink the very bucket
        # evidence the range is judged from.
        before_rr = len(best_results)
        rr_floor, rr_ceiling = msnr_symbol_rr_range(best_results)
        best["skip_rr_min"] = rr_ceiling
        best["skip_rr_max"] = rr_floor  # v0.99.86 — new field, the floor side; kept named "_max" for symmetry with "_min" meaning "everything past this edge, going the other direction, is skipped"
        if rr_ceiling is not None or rr_floor is not None:
            best_results = [t for t in best_results if t["rr"] is None
                             or ((rr_ceiling is None or t["rr"] < rr_ceiling)
                                 and (rr_floor is None or t["rr"] >= rr_floor))]
            _msnr_recompute_summary_score(best, best_results)
        best["rr_filtered_count"] = before_rr - len(best_results)
        checkpoints.append({"stage": "rr_range", **_msnr_filter_checkpoint(best_results, symbol, best["leverage_ceiling"])})
        # v0.99.26, per direct user request ("иногда стоп будет за
        # ликвидацией и просто избегать этого"): deterministic filter,
        # not statistical — a trade whose own SL sits past this
        # symbol's effective-leverage liquidation buffer gets dropped
        # unconditionally, sample size doesn't matter here since it's
        # Gate's own margin math, not a pattern being inferred from
        # history. Applied AFTER the RR-range filter (on whatever
        # survived it) and BEFORE the SL-width statistical filter below
        # — the SL-width bucket stats should reflect only trades that
        # could have actually played out as scored, not ones that were
        # never mechanically reachable in the first place.
        before_liq = len(best_results)
        best_results = [t for t in best_results
                         if not msnr_trade_beyond_liquidation(symbol, t["direction"], t["entry"], t["sl"],
                                                               leverage=best["effective_leverage"])]
        best["liquidation_filtered_count"] = before_liq - len(best_results)
        if best["liquidation_filtered_count"]:
            _msnr_recompute_summary_score(best, best_results)
        checkpoints.append({"stage": "liquidation", **_msnr_filter_checkpoint(best_results, symbol, best["leverage_ceiling"])})
        # v0.99.26, per direct user request ("фильтр по ширине стопа"):
        # SL-width counterpart to the RR-range block above — same
        # ordering reasoning (derive the floor off the full surviving
        # sample first, THEN filter), same "skip entirely" behavior.
        before_sl = len(best_results)
        best["skip_sl_pct_min"] = msnr_symbol_sl_skip_min(best_results)
        if best["skip_sl_pct_min"] is not None:
            skip_sl = best["skip_sl_pct_min"]
            best_results = [t for t in best_results
                             if not t.get("entry") or t["entry"] <= 0 or t.get("sl") is None
                             or abs(t["entry"] - t["sl"]) / t["entry"] * 100 < skip_sl]
            _msnr_recompute_summary_score(best, best_results)
        best["sl_filtered_count"] = before_sl - len(best_results)
        checkpoints.append({"stage": "sl_pct", **_msnr_filter_checkpoint(best_results, symbol, best["leverage_ceiling"])})
        # v0.99.56, per direct user request ("какой фильтр сигналов был
        # бы самым эффективным для внедрения" -> time-of-day): same
        # ordering reasoning as every filter above — derive the
        # bad-hours SET off the full surviving sample first, THEN
        # filter, so msnr_symbol_skip_hours()'s own sample-size gate
        # judges against undiminished evidence. Unlike the RR/SL
        # filters above (a threshold), this drops a SET of specific UTC
        # hours — see that function's own docstring for why hour-of-day
        # has no natural "past this point" ordering.
        before_hours = len(best_results)
        best["skip_hours"] = msnr_symbol_skip_hours(best_results)
        if best["skip_hours"]:
            skip_hour_set = set(best["skip_hours"])
            best_results = [t for t in best_results
                             if t.get("time") is None or time.gmtime(t["time"])[3] not in skip_hour_set]
            _msnr_recompute_summary_score(best, best_results)
        best["hours_filtered_count"] = before_hours - len(best_results)
        checkpoints.append({"stage": "hours", **_msnr_filter_checkpoint(best_results, symbol, best["leverage_ceiling"])})
        # v0.99.59, per direct user request ("второй фильтр... про n
        # как в первом не забудь" — volume confirmation on the sweep):
        # same ordering reasoning as every filter above — derive the
        # floor off the full surviving sample first, THEN filter. See
        # msnr_symbol_volume_skip_below()'s own docstring for why this
        # skips BELOW a ceiling (opposite direction from the RR-range
        # floor/skip_sl_pct_min, which skip ABOVE a floor).
        before_volume = len(best_results)
        best["skip_volume_below"] = msnr_symbol_volume_skip_below(best_results)
        if best["skip_volume_below"] is not None:
            skip_vol = best["skip_volume_below"]
            best_results = [t for t in best_results
                             if t.get("volume_ratio") is None or t["volume_ratio"] >= skip_vol]
            _msnr_recompute_summary_score(best, best_results)
        best["volume_filtered_count"] = before_volume - len(best_results)
        checkpoints.append({"stage": "volume", **_msnr_filter_checkpoint(best_results, symbol, best["leverage_ceiling"])})
        # v0.99.141 — 2 new GLOBAL (not per-symbol-tuned, unlike every
        # filter above) optional stages. Their own solo checkpoint is
        # ALWAYS computed and appended (what this filter would do if
        # applied on top of everything above), even while its own
        # toggle is off — see MSNR_MIN_RR_FILTER_ENABLED's own comment
        # for the full reasoning — but best_results is only actually
        # narrowed when the toggle is genuinely on.
        min_rr_candidates = msnr_filter_by_min_rr(best_results)
        if MSNR_MIN_RR_FILTER_ENABLED:
            before_min_rr = len(best_results)
            best_results = min_rr_candidates
            best["min_rr_filtered_count"] = before_min_rr - len(best_results)
            _msnr_recompute_summary_score(best, best_results)
            checkpoints.append({"stage": "min_rr", **_msnr_filter_checkpoint(best_results, symbol, best["leverage_ceiling"])})
        else:
            checkpoints.append({"stage": "min_rr", **_msnr_filter_checkpoint(min_rr_candidates, symbol, best["leverage_ceiling"])})
        htf_candles = None
        try:
            htf_interval_sec = INTERVAL_SECONDS.get(MSNR_HTF_INTERVAL, 14400)
            htf_fetch_start = now - (days + 20) * 86400
            htf_candles = get_candles_range(symbol, MSNR_HTF_INTERVAL, htf_fetch_start, now)
        except Exception as e:
            log_error(f"msnr_optimize_symbol {symbol}: HTF fetch for trend filter failed: {e}")
        if htf_candles and len(htf_candles) >= MSNR_HTF_EMA_PERIOD:
            bias_series = lsw_htf_bias_series(htf_candles, period=MSNR_HTF_EMA_PERIOD, buffer_pct=MSNR_HTF_TREND_BUFFER_PCT)
            htf_candidates = msnr_filter_by_htf_trend(best_results, bias_series, htf_interval_sec)
        else:
            htf_candidates = best_results  # not enough HTF history to judge — same "nothing to judge, keep" convention as LSW's own version, just non-conservative here since this is only a solo/optional preview when not enough data exists
        if MSNR_HTF_FILTER_ENABLED:
            before_htf = len(best_results)
            best_results = htf_candidates if (htf_candles and len(htf_candles) >= MSNR_HTF_EMA_PERIOD) else []
            best["htf_filtered_count"] = before_htf - len(best_results)
            _msnr_recompute_summary_score(best, best_results)
            checkpoints.append({"stage": "htf_trend", **_msnr_filter_checkpoint(best_results, symbol, best["leverage_ceiling"])})
        else:
            checkpoints.append({"stage": "htf_trend", **_msnr_filter_checkpoint(htf_candidates, symbol, best["leverage_ceiling"])})
        # v0.99.86 — the full chain, one entry per stage transition;
        # api_msnr_status() surfaces this so the UI can show, per
        # filter, exactly what its own before->after did to n/winrate/
        # income — not just a trade count delta, per the direct request
        # ("чтобы понимать эффективность фильтров и менять их на другие
        # своевременно"). Each entry's own "stage" names WHICH filter
        # produced it (i.e. checkpoints[i] is the state AFTER stage
        # checkpoints[i]["stage"] ran, checkpoints[i-1] is its "before").
        best["filter_checkpoints"] = checkpoints
    # v0.99.47, per direct user follow-up to v0.99.46 ("чёт лучше не
    # стало, будто даже хуже" -> Kelly/optimal-f search instead of a
    # fixed stop-width target): ONE flat leverage for this symbol,
    # chosen to maximize long-run compounded growth against its OWN
    # (already-filtered) trade history — see msnr_optimal_leverage_
    # for_symbol()'s own docstring for the full reasoning. Computed
    # against best_results AFTER every filter above (skip_rr_min,
    # liquidation, skip_sl_pct_min) — the same final trade set the
    # compound simulation right below already uses, not the raw
    # unfiltered history.
    best["optimal_leverage"] = msnr_optimal_leverage_for_symbol(best_results, best.get("leverage_ceiling"), symbol=symbol)
    # v0.99.24, per direct user request: a $ compounding simulation
    # (start MSNR_COMPOUND_START_BALANCE, reinvest the whole balance
    # every trade) over best_results — the FILTERED list (skip_rr_min +
    # v0.99.26's liquidation/skip_sl_pct_min filters), matching what
    # this symbol would actually be traded as, same reasoning as the
    # R-multiple stats above using the filtered set rather than
    # raw_results. v0.99.47: leverage is this symbol's own Kelly-optimal
    # value (just computed above) — flat for the whole simulation, not
    # varied per-trade by stop width (v0.99.46, reverted — see msnr_
    # compound_trail()'s own docstring for why).
    compound = msnr_compound_return(best_results, leverage=best["optimal_leverage"])
    best["compound_final_balance"] = compound["final_balance"] if compound else None
    best["compound_return_pct"] = compound["return_pct"] if compound else None
    best["compound_blown_at"] = compound["blown_at_trade"] if compound else None
    # v0.99.27, per direct user request ("просто не попадает в топ"):
    # a hard gate, not a score penalty — a symbol whose own $ compound
    # simulation lost money (return_pct <= 0, which trivially includes
    # a full blow-up to 0) is unfit for ranking/autotrade regardless of
    # how good its R-multiple score looks; msnr_rank_by_winrate_sample()
    # excludes it outright and api_msnr_status()'s sort sinks it below
    # every symbol that passed, so it structurally can't land near the
    # top of the table the user actually looks at. None (not False) when
    # there's no compound result to judge at all (e.g. zero closed
    # trades survived filtering) — "no evidence either way" shouldn't
    # silently read as "passed."
    best["stress_test_failed"] = (best["compound_return_pct"] is not None
                                   and best["compound_return_pct"] <= 0)
    return best, best_results, raw_results


def msnr_summarize_backtest(results):
    total = len(results)
    if not total:
        return {"n": 0, "win_rate": None, "wins": 0, "losses": 0, "timeouts": 0,
                "avg_rr": None, "median_rr": None, "expectancy_r": None}
    wins = sum(1 for r in results if r["result"] == "WIN")
    losses = sum(1 for r in results if r["result"] == "LOSS")
    timeouts = sum(1 for r in results if r["result"] == "TIMEOUT")
    closed = wins + losses
    win_rate = round(wins / closed * 100, 1) if closed else None
    rrs = [r["rr"] for r in results if r["rr"] is not None]
    avg_rr = round(sum(rrs) / len(rrs), 2) if rrs else None
    if rrs:
        srr = sorted(rrs)
        mid = len(srr) // 2
        median_rr = round(srr[mid] if len(srr) % 2 else (srr[mid - 1] + srr[mid]) / 2, 2)
    else:
        median_rr = None
    # Expectancy in R, using each closed trade's OWN rr (not just avg_rr) —
    # win contributes +its own rr, loss contributes -1, timeout excluded
    # (no real outcome to score). This is what actually tells you whether
    # the ~50% win-rate is sound: with real 10R+ targets, even a coin-flip
    # win-rate should show strongly positive expectancy.
    r_values = [r["rr"] for r in results if r["result"] == "WIN" and r["rr"] is not None]
    r_values += [-1.0 for r in results if r["result"] == "LOSS"]
    expectancy_r = round(sum(r_values) / len(r_values), 2) if r_values else None
    return {"n": total, "win_rate": win_rate, "wins": wins, "losses": losses, "timeouts": timeouts,
            "avg_rr": avg_rr, "median_rr": median_rr, "expectancy_r": expectancy_r}


MSNR_RR_BUCKETS = [(0, 3), (3, 5), (5, 7), (7, 10), (10, float("inf"))]  # v0.99.11 — bucket boundaries for msnr_rr_bucket_stats(); chosen so the user's own reported breakpoint (rr>6 consistently failing) falls cleanly inside the 5-7 bucket, not split across two


def msnr_rr_bucket_stats(trades, bucket_scheme=None):
    """Buckets CLOSED trades (WIN/LOSS only — TIMEOUT has no real outcome
    to bucket by) by their OWN realized rr into MSNR_RR_BUCKETS, computing
    win-rate per bucket. Per direct user observation: pooled stats (avg/
    median RR, one overall win-rate) can't reveal a pattern like "rr>6
    trades consistently hit stop, rr<6 trades win normally" — that only
    becomes visible once trades are actually split by their own RR rather
    than averaged together. Feeds both the panel's own display (so the
    pattern the user described becomes directly visible, not just
    assumed from one example) and _risk_autotune_msnr_max_rr() below.
    v0.99.12: returned dicts deliberately do NOT include a raw "hi" key
    (only "lo") — CRITICAL FIX: MSNR_RR_BUCKETS' last bucket's hi is
    float("inf"), and jsonify() happily serializes that as the literal
    token `Infinity`, which is NOT valid JSON (RFC 8259 only allows
    finite numbers) — the browser's JSON.parse() then throws a
    SyntaxError on it, confirmed directly (`node -e "JSON.parse(...)"`)
    to reproduce the exact failure. Since refreshMsnr()'s very first
    line awaits response.json() with no try/catch around it, that parse
    failure meant the WHOLE function threw before panel.innerHTML was
    ever set — explaining the reported "black screen" (empty MSNR tab,
    every other tab fine) precisely. "hi" was never actually consumed
    anywhere (the label string already encodes both boundaries as text,
    and _risk_autotune_msnr_max_rr() only ever reads "lo") — dropping it
    entirely is safer than sanitizing inf->None at the jsonify boundary,
    since it removes the whole class of "some other future numeric
    field might also carry inf into a JSON response" risk, not just
    this one instance of it.
    v0.99.89 — accepts an optional `bucket_scheme` (a list of (lo, hi)
    tuples, same shape as MSNR_RR_BUCKETS) to support msnr_symbol_rr_
    range()'s own granularity cascade (see that function's docstring —
    found via a direct user report, "на некоторых монетах фильтры
    никакие не применены," after v0.99.86 shipped this filter with a
    FIXED 5-bucket scheme and no fallback, unlike the hour/volume
    filters which already had one since v0.99.60). Defaults to the
    canonical MSNR_RR_BUCKETS when omitted, preserving the EXACT
    existing behavior for the pooled/display table below, which always
    wants the fixed 5-bucket scheme regardless of whatever granularity
    a per-symbol filter cascade happens to be trying."""
    scheme = bucket_scheme if bucket_scheme is not None else MSNR_RR_BUCKETS
    buckets = []
    for lo, hi in scheme:
        subset = [t for t in trades if t.get("result") in ("WIN", "LOSS") and t.get("rr") is not None and lo <= t["rr"] < hi]
        label = f"{lo}-{hi}" if hi != float("inf") else f"{lo}+"
        if not subset:
            buckets.append({"range": label, "lo": lo, "n": 0, "wins": 0, "losses": 0, "winrate": None, "avg_rr": None})
            continue
        wins = sum(1 for t in subset if t["result"] == "WIN")
        n = len(subset)
        avg_rr = round(sum(t["rr"] for t in subset) / n, 2)
        buckets.append({"range": label, "lo": lo, "n": n, "wins": wins,
                         "losses": n - wins, "winrate": round(wins / n * 100, 1), "avg_rr": avg_rr})
    return buckets


MSNR_RR_BUCKET_SCHEMES = [
    MSNR_RR_BUCKETS,  # finest — v0.99.11's original 5-bucket split
    [(0, 5), (5, 10), (10, float("inf"))],  # medium — 3 buckets
    [(0, 7), (7, float("inf"))],  # coarsest — 2 buckets
]  # v0.99.89, per direct user report ("на некоторых монетах фильтры никакие не применены") after v0.99.86 shipped msnr_symbol_rr_range() with ONLY the fixed 5-bucket scheme and no fallback — a modest total sample (e.g. the ~50-trade symbols the earlier report itself described) splits into ~10/bucket on average across 5 buckets, already below MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE=15 even before accounting for any real unevenness, so NONE of the 5 buckets could ever reach significance and the filter silently found nothing for those symbols. Mirrors the exact cascade shape msnr_symbol_skip_hours()/msnr_symbol_volume_skip_below() already use (MSNR_HOUR_GROUP_WIDTHS/MSNR_VOLUME_QUANTILE_GROUPS, both v0.99.60) — finest tried first, progressively coarser as fallback, first scheme that finds ANYTHING significant wins.


def msnr_symbol_rr_range(trades):
    """v0.99.86, per direct user request ("отсечение всегда убыточного
    диапазона RR, как снизу так и сверху... много слабых результатов в
    msnr, по 50 сделок а доход околонулевой, при этом винрейт от 30 до
    50"): TWO-SIDED replacement for msnr_symbol_rr_skip_min() above
    (v0.99.79 disabled that one-sided rule entirely, per an earlier
    direct request to trade every RR range while more data accumulated
    — this reintroduces filtering in a genuinely different, symmetric
    shape, not a plain revert). The live pattern that prompted this —
    a large, trustworthy sample (~50 trades) with a middling winrate
    but near-zero compounded income — is exactly what a ONE-SIDED high-
    RR cutoff can't catch: if the symbol's edge is concentrated in the
    MIDDLE of its own RR distribution while BOTH extremes (very low RR
    AND very high RR) drag the average down, cutting only the top
    leaves the bad low end untouched.
    Uses the SAME bucket-and-breakeven test every other MSNR filter
    already uses (msnr_rr_bucket_stats(), MSNR_SYMBOL_RR_SKIP_MIN_
    SAMPLE) — nothing new statistically, just applied from both ends:
    - ceiling: the lowest bucket edge among sufficiently-sampled
      buckets failing their own breakeven (unchanged from the old
      one-sided rule) — a live signal at or above this RR is skipped.
    - floor: scans buckets from RR=0 upward and finds the upper edge of
      the longest CONTIGUOUS run of failing buckets starting at the
      very bottom — a live signal below this RR is skipped. A single
      bad low-RR bucket sets the floor to its own upper edge; several
      consecutive bad low-RR buckets extend it further up. Buckets
      past the first PASSING (or insufficiently-sampled) one don't
      extend the floor, even if a later bucket also happens to fail —
      the floor means "everything below here is bad," which a gap of
      good buckets in between would contradict.
    v0.99.89 — cascades MSNR_RR_BUCKET_SCHEMES from finest to coarsest
    (see that constant's own comment for the full reasoning): tries the
    canonical 5-bucket scheme first; if NEITHER a floor nor a ceiling
    is found there, retries against a coarser 3-bucket, then 2-bucket
    scheme, stopping at the first scheme that finds ANYTHING — a symbol
    whose fine-grained buckets never individually reach the sample bar
    still gets a shot at a coarser, still-statistically-legitimate
    split instead of silently passing every trade through unfiltered.
    Either side can independently be None (no statistically significant
    unprofitable region found there, even at the coarsest tried scheme)
    — a symbol can end up with only a ceiling, only a floor, both, or
    neither, same "don't invent evidence from a thin sample" stance as
    the rule this replaces.
    Returns (floor, ceiling) — floor is the bucket's own upper edge
    (never returns float("inf") — an open-ended top bucket can only
    ever extend a ceiling-seeking search, not a floor-seeking one,
    since a floor search stops at the first non-failing bucket long
    before reaching it in any realistic RR distribution)."""
    def _failing(b):
        return (b["n"] >= MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE and b["winrate"] is not None
                and b["avg_rr"] and b["winrate"] < 100.0 / (1.0 + b["avg_rr"]))

    for scheme in MSNR_RR_BUCKET_SCHEMES:
        buckets = msnr_rr_bucket_stats(trades, bucket_scheme=scheme)

        # v0.99.86 fix, caught by a synthetic test with BOTH ends failing
        # before shipping: floor is computed FIRST, and ceiling's own
        # search only considers buckets AFTER the floor's own contiguous
        # run — not the whole bucket list. Without this split, a failing
        # low-RR bucket (lo=0) would itself show up as the "lowest
        # failing edge" and get mistaken for the ceiling too, producing
        # a nonsensical ceiling=0 that would skip literally everything
        # instead of two genuinely separate bad regions at opposite ends.
        floor = None
        floor_bucket_count = 0
        for lo, hi in scheme:
            b = next(bb for bb in buckets if bb["lo"] == lo)
            if _failing(b):
                floor = hi
                floor_bucket_count += 1
            else:
                break

        failing_edges = [b["lo"] for i, b in enumerate(buckets) if i >= floor_bucket_count and _failing(b)]
        ceiling = min(failing_edges) if failing_edges else None

        # a floor at or above the ceiling would leave nothing tradable at
        # all — shouldn't arise given ceiling only searches buckets past
        # the floor's own run, but guarded explicitly rather than
        # trusting bucket ordering to hold forever.
        if floor is not None and ceiling is not None and floor >= ceiling:
            floor = None

        if floor is not None or ceiling is not None:
            return floor, ceiling
    return None, None


def msnr_symbol_rr_skip_min(trades):
    """v0.99.22, per direct user request: a per-SYMBOL counterpart to
    _risk_autotune_msnr_max_rr()'s pooled-across-all-symbols cap.
    Bucket THIS symbol's own closed backtest trades by rr (same
    msnr_rr_bucket_stats() the pooled rule uses), and find the lowest
    bucket that both (a) has enough of this symbol's own trades to
    trust (>= MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE — deliberately a higher
    single-symbol bar than the pooled rule's RISK_AUTOTUNE_MIN_SAMPLE,
    since this is judging one symbol off its own sample rather than
    the whole universe) and (b) is failing its own breakeven at its
    own actual average realized rr (not the bucket's lower edge —
    same fix as the pooled rule, since lo=0 on the first bucket implies
    a nonsensical 100% breakeven requirement).
    Returns that bucket's lower edge — this symbol's live scanner skips
    any new signal whose own rr lands at or above it — or None if no
    bucket for this symbol clears the sample bar, in which case the
    symbol trades normally (falls through to the global MSNR_MAX_RR
    cap same as before). Deliberately one-directional like the pooled
    rule: this only ever adds a skip floor off solid per-symbol
    evidence, it never widens one back out on its own."""
    buckets = msnr_rr_bucket_stats(trades)
    failing_edges = [b["lo"] for b in buckets
                      if b["n"] >= MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE and b["winrate"] is not None and b["avg_rr"]
                      and b["winrate"] < 100.0 / (1.0 + b["avg_rr"])]
    return min(failing_edges) if failing_edges else None


MSNR_SL_PCT_BUCKETS = [(0, 2), (2, 4), (4, 6), (6, 10), (10, float("inf"))]  # v0.99.26 — % SL-distance buckets for msnr_sl_bucket_stats(), same shape as MSNR_RR_BUCKETS but keyed on stop width instead of RR


def msnr_sl_bucket_stats(trades, bucket_scheme=None):
    """v0.99.26, per direct user request: SL-width counterpart to msnr_
    rr_bucket_stats() — buckets CLOSED trades (WIN/LOSS only) by their
    OWN SL distance as a % of entry price (not by rr) into MSNR_SL_PCT_
    BUCKETS, computing win-rate AND avg_rr per bucket (avg_rr is needed
    here too, same as the RR-bucket version, to judge each bucket
    against its own breakeven). A wide stop matters independently of
    RR: a single very-wide-stop loss can wipe a fixed-leverage
    compounding account outright (see msnr_compound_return()) even
    when that trade's RR looked perfectly ordinary — RR alone (reward
    relative to risk) says nothing about how big the risk itself was
    in absolute % terms.
    Same "hi" key omitted (only "lo") for the same JSON-Infinity reason
    msnr_rr_bucket_stats() already documented — the last bucket's hi is
    float("inf") and would break jsonify().
    v0.99.89 — accepts an optional `bucket_scheme`, same reasoning and
    same shape as msnr_rr_bucket_stats()'s own addition: supports msnr_
    symbol_sl_skip_min()'s own granularity cascade (MSNR_SL_PCT_BUCKET_
    SCHEMES) without disturbing the fixed MSNR_SL_PCT_BUCKETS default
    any other caller relies on."""
    scheme = bucket_scheme if bucket_scheme is not None else MSNR_SL_PCT_BUCKETS
    buckets = []
    for lo, hi in scheme:
        subset = []
        for t in trades:
            if t.get("result") not in ("WIN", "LOSS"):
                continue
            entry = t.get("entry")
            sl = t.get("sl")
            if not entry or entry <= 0 or sl is None:
                continue
            sl_pct = abs(entry - sl) / entry * 100
            if lo <= sl_pct < hi:
                subset.append(t)
        label = f"{lo}-{hi}" if hi != float("inf") else f"{lo}+"
        if not subset:
            buckets.append({"range": label, "lo": lo, "n": 0, "wins": 0, "losses": 0, "winrate": None, "avg_rr": None})
            continue
        wins = sum(1 for t in subset if t["result"] == "WIN")
        n = len(subset)
        rrs = [t["rr"] for t in subset if t.get("rr") is not None]
        avg_rr = round(sum(rrs) / len(rrs), 2) if rrs else None
        buckets.append({"range": label, "lo": lo, "n": n, "wins": wins,
                         "losses": n - wins, "winrate": round(wins / n * 100, 1), "avg_rr": avg_rr})
    return buckets


MSNR_SL_PCT_BUCKET_SCHEMES = [
    MSNR_SL_PCT_BUCKETS,  # finest — v0.99.26's original 5-bucket split
    [(0, 4), (4, 10), (10, float("inf"))],  # medium — 3 buckets
    [(0, 6), (6, float("inf"))],  # coarsest — 2 buckets
]  # v0.99.89 — same cascade reasoning/shape as MSNR_RR_BUCKET_SCHEMES above, applied to SL-width instead of RR (found via the same direct user report, "на некоторых монетах фильтры никакие не применены" — this filter had the identical fixed-scheme-no-fallback gap).


def msnr_symbol_sl_skip_min(trades):
    """v0.99.26, per direct user request ("фильтр по ширине стопа"):
    SL-width counterpart to msnr_symbol_rr_skip_min() — same shape,
    same sample bar (MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE — no reason for a
    separate one, it's the same "trust this symbol's own bucket"
    question either way), same one-directional-only stance, but
    bucketed by msnr_sl_bucket_stats() instead of msnr_rr_bucket_
    stats(). Returns this symbol's own SL% floor — live signals whose
    OWN SL distance lands at or above it get skipped for this symbol —
    or None if no bucket clears the sample bar at ANY tried granularity.
    Deliberately separate from msnr_symbol_rr_skip_min(): a symbol can
    have a fine RR distribution (good reward-to-risk ratios) while
    still routinely getting stopped out on unusually WIDE stops in
    absolute % terms — RR alone doesn't capture that, only the SL's
    own size does.
    v0.99.89 — cascades MSNR_SL_PCT_BUCKET_SCHEMES from finest to
    coarsest, identical reasoning/shape to msnr_symbol_rr_range()'s own
    cascade addition — a modest total sample can leave every one of the
    fine scheme's 5 buckets under MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE even
    when the symbol's overall trade count looks substantial."""
    for scheme in MSNR_SL_PCT_BUCKET_SCHEMES:
        buckets = msnr_sl_bucket_stats(trades, bucket_scheme=scheme)
        failing_edges = [b["lo"] for b in buckets
                          if b["n"] >= MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE and b["winrate"] is not None and b["avg_rr"]
                          and b["winrate"] < 100.0 / (1.0 + b["avg_rr"])]
        if failing_edges:
            return min(failing_edges)
    return None


MSNR_HOUR_GROUP_WIDTHS = [1, 2, 3]  # v0.99.60, per direct user request ("оба варианта вместе" — granularity/threshold search paired with the volume filter's quantile adaptation): candidate UTC-hour group widths for msnr_hour_bucket_stats(), tried FINEST first (single-hour resolution, the original v0.99.56 behavior) then progressively wider — a symbol whose per-hour sample never clears MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE still gets a shot at a coarser, still-legitimate 2h or 3h grouping instead of the filter finding nothing at all purely from thin per-hour data.


def msnr_hour_bucket_stats(trades, group_width=1):
    """v0.99.56, per direct user request ("какой фильтр сигналов был бы
    самым эффективным"): time-of-day counterpart to msnr_rr_bucket_
    stats()/msnr_sl_bucket_stats() — buckets CLOSED trades (WIN/LOSS
    only) by the UTC hour (0-23) of their OWN entry candle's time,
    computing win-rate AND avg_rr per hour (avg_rr needed for the same
    per-bucket-breakeven judgment the RR/SL bucket versions already
    use). The whole QM/SNR pattern is a bet that a sweep-and-reclaim
    reflects REAL institutional order flow, not noise — and that's
    exactly the kind of thing that varies by session: London/NY open
    genuinely has that flow behind it, thin overnight hours often
    don't, and this app's own separate "Сессия" module already trades
    that same premise directly. Symmetric with the RR/SL bucket
    functions in every other way, including which hours a given
    symbol tends to actually trade in at all being visible via which
    buckets even have a nonzero n.
    UTC via time.gmtime() (stdlib, already imported) — deliberately
    NOT the app's own Moscow-fixed-offset convention the Session
    module uses (that offset exists specifically to avoid a system
    tzdata dependency for one fixed daily reference point, 10:00 MSK;
    this needs the actual UTC hour of arbitrary historical timestamps
    across 24 buckets, which time.gmtime() gives directly with no
    timezone-database dependency either).
    v0.99.60: `group_width` groups consecutive UTC hours together
    (e.g. width=3 -> 0-2, 3-5, 6-8, ...) instead of always a single
    hour per bucket — msnr_symbol_skip_hours() searches MSNR_HOUR_
    GROUP_WIDTHS from finest to coarsest, using this parameter, so a
    symbol whose per-HOUR sample is too thin to ever clear the
    significance bar still gets evaluated at a coarser, still-
    legitimate resolution instead of the filter simply finding
    nothing. Each returned dict's "hours" field lists every individual
    UTC hour that group covers, so a caller can expand a flagged group
    back into the specific hours it represents."""
    n_groups = -(-24 // group_width)  # ceiling division — width=1 -> 24 groups, width=3 -> 8 groups
    buckets_by_group = {g: [] for g in range(n_groups)}
    for t in trades:
        if t.get("result") not in ("WIN", "LOSS"):
            continue
        if t.get("time") is None:
            continue
        hour = time.gmtime(t["time"])[3]
        buckets_by_group[hour // group_width].append(t)
    result = []
    for g in range(n_groups):
        lo_hour = g * group_width
        hours = list(range(lo_hour, min(24, lo_hour + group_width)))
        subset = buckets_by_group[g]
        if not subset:
            result.append({"hours": hours, "n": 0, "wins": 0, "losses": 0, "winrate": None, "avg_rr": None})
            continue
        wins = sum(1 for t in subset if t["result"] == "WIN")
        n = len(subset)
        rrs = [t["rr"] for t in subset if t.get("rr") is not None]
        avg_rr = round(sum(rrs) / len(rrs), 2) if rrs else None
        result.append({"hours": hours, "n": n, "wins": wins, "losses": n - wins,
                        "winrate": round(wins / n * 100, 1), "avg_rr": avg_rr})
    return result


def msnr_symbol_skip_hours(trades):
    """v0.99.56, per direct user request: hour-of-day counterpart to
    msnr_symbol_rr_skip_min()/msnr_symbol_sl_skip_min() — same sample
    bar (MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE), same per-bucket-breakeven
    test, but returns a SET of specific bad hours rather than a single
    threshold: unlike RR/SL width, hour-of-day has no natural ordering
    where "everything past this point is bad" makes sense — a symbol
    could easily be fine at both 2:00 and 22:00 UTC but bad specifically
    at 14:00, and a single cutoff value couldn't express that shape.
    v0.99.60, per direct user follow-up ("добавить вариативность...
    оба варианта вместе"): searches MSNR_HOUR_GROUP_WIDTHS from finest
    (single-hour) to coarsest — the first width that finds ANY group
    clearing both the significance test and the sample bar wins; a
    thin trade history simply never reaches the finer widths' own per-
    group sample requirement, so it falls through to a coarser, still-
    legitimate grouping instead of finding nothing. When a WIDER group
    is flagged, every individual UTC hour it covers gets skipped —
    less precise than single-hour resolution, but still statistically
    supported, which single-hour buckets on a thin history wouldn't be.
    Returns a sorted list of UTC hours (0-23) where this symbol's own
    trade history shows a statistically-trustworthy losing pattern —
    live signals whose entry candle falls in one of these hours get
    skipped for this symbol. Empty list if nothing at any tried
    granularity clears the sample bar (the overwhelmingly common case
    for any symbol without a very long or very lopsided-by-hour trading
    history)."""
    for width in MSNR_HOUR_GROUP_WIDTHS:
        buckets = msnr_hour_bucket_stats(trades, group_width=width)
        bad_groups = [b for b in buckets
                      if b["n"] >= MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE and b["winrate"] is not None and b["avg_rr"]
                      and b["winrate"] < 100.0 / (1.0 + b["avg_rr"])]
        if bad_groups:
            bad_hours = set()
            for b in bad_groups:
                bad_hours.update(b["hours"])
            return sorted(bad_hours)
    return []


MSNR_VOLUME_QUANTILE_GROUPS = [5, 4, 3]  # v0.99.60, per direct user request ("оба варианта вместе" — quantile-adaptive bucketing AND granularity/threshold search, applied together): candidate group counts for msnr_volume_quantile_buckets(), tried FINEST first (5 roughly-equal groups) then progressively coarser as a fallback — finer groups are more precise but need more of this symbol's own trades to individually clear MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE; a symbol with a thinner trade history still gets a shot at a coarser, still-significant split instead of the filter just giving up.


def msnr_volume_quantile_buckets(trades, k):
    """v0.99.60, per direct user follow-up to v0.99.59 ("может в первый
    фильтр и во второй добавить некую вариативность... авто перебор
    параметров фильтра для лучшего результата?"): REPLACES the old
    fixed MSNR_VOLUME_RATIO_BUCKETS (0-0.5/0.5-0.8/0.8-1.2/1.2-2/2+)
    with QUANTILE buckets computed fresh from THIS symbol's own
    volume_ratio distribution — splits its CLOSED trades (with a known
    volume_ratio) into k roughly-equal-SIZED groups by sorted value,
    rather than assuming one universal set of absolute cutoffs fits
    every symbol's typical volume behavior. A generally choppy/spiky
    symbol and a generally calm one don't share a "normal" volume_ratio
    range — fixed absolute buckets would leave one of them with nearly
    all its trades crammed into a single bucket (useless — no
    resolution) while the other's trades scatter thinly across all
    five (useless — no bucket ever reaches significant sample size).
    Quantile splitting sidesteps that entirely: every bucket gets
    n/k trades by construction, regardless of the symbol's own
    distribution shape.
    IMPORTANT — this is explicitly NOT "search for whichever k gives
    the best-looking result": every candidate k still goes through the
    exact same breakeven-at-sufficient-sample test msnr_symbol_volume_
    skip_below() already used before this change (see that function's
    own docstring) — this only varies HOW the trades get grouped, not
    whether a group has to prove itself significant to matter. Reusing
    a threshold-hunting search without that same significance gate
    would just be curve-fitting the filter itself to this backtest's
    own noise, exactly the overfitting failure mode already found and
    fixed elsewhere this session (the liquid-universe cap, the pooled
    RR-bucket autotune) — the whole point of asking for "оба варианта
    вместе" was adding flexibility WITHOUT reopening that door.
    Returns a list of k (or fewer, if there aren't enough closed trades
    with a volume_ratio to fill k groups) dicts: {"n", "wins", "losses",
    "winrate", "avg_rr", "hi"} — "hi" is that group's own maximum
    volume_ratio (the boundary msnr_symbol_volume_skip_below() treats
    as a candidate ceiling), in ascending group order."""
    closed = [t for t in trades if t.get("result") in ("WIN", "LOSS") and t.get("volume_ratio") is not None]
    if len(closed) < k:
        return []
    closed.sort(key=lambda t: t["volume_ratio"])
    n = len(closed)
    buckets = []
    for i in range(k):
        lo_idx = i * n // k
        hi_idx = (i + 1) * n // k
        subset = closed[lo_idx:hi_idx]
        if not subset:
            continue
        wins = sum(1 for t in subset if t["result"] == "WIN")
        cnt = len(subset)
        rrs = [t["rr"] for t in subset if t.get("rr") is not None]
        avg_rr = round(sum(rrs) / len(rrs), 2) if rrs else None
        buckets.append({"n": cnt, "wins": wins, "losses": cnt - wins,
                         "winrate": round(wins / cnt * 100, 1), "avg_rr": avg_rr,
                         "hi": subset[-1]["volume_ratio"]})
    return buckets


def msnr_symbol_volume_skip_below(trades):
    """v0.99.59/v0.99.60, per direct user request ("второй фильтр... про
    n как в первом не забудь" then "добавить вариативность... оба
    варианта вместе"): volume-ratio counterpart to msnr_symbol_rr_
    skip_min()/msnr_symbol_sl_skip_min(), same sample bar (MSNR_
    SYMBOL_RR_SKIP_MIN_SAMPLE) and per-bucket-breakeven test — but
    skips BELOW a ceiling instead of above a floor, the OPPOSITE
    direction from the RR/SL filters (their hypothesis: metric too
    HIGH is unreliable; this one's: volume too LOW is).
    v0.99.60: searches MSNR_VOLUME_QUANTILE_GROUPS from finest to
    coarsest (msnr_volume_quantile_buckets()) — the first k that finds
    ANY group clearing both the significance test and the sample bar
    wins; a thin trade history simply never reaches the finer k values'
    own per-group sample requirement, so it falls through to a coarser,
    still-legitimate split rather than finding nothing at all. The
    LAST (highest-volume) group of whichever k is used is always
    excluded from the search — taking its own "hi" as a "skip below"
    ceiling would, in the pathological case where it still fails,
    mean skipping literally everything, never the intended outcome.
    Returns this symbol's own volume-ratio floor — a live signal whose
    OWN volume_ratio lands BELOW it gets skipped for this symbol — or
    None if nothing at any tried granularity clears the sample bar, or
    the symbol's trades don't carry volume_ratio at all (e.g. an
    override computed before that field existed)."""
    for k in MSNR_VOLUME_QUANTILE_GROUPS:
        buckets = msnr_volume_quantile_buckets(trades, k)
        candidate_buckets = buckets[:-1] if len(buckets) > 1 else []
        failing_edges = [b["hi"] for b in candidate_buckets
                          if b["n"] >= MSNR_SYMBOL_RR_SKIP_MIN_SAMPLE and b["winrate"] is not None and b["avg_rr"]
                          and b["winrate"] < 100.0 / (1.0 + b["avg_rr"])]
        if failing_edges:
            return max(failing_edges)
    return None


def msnr_symbol_effective_leverage(symbol):
    """v0.99.26, per direct user request ("узнавать максимальное плечо
    на бирже"): AUTOTRADE_LEVERAGE_MSNR clamped to THIS contract's own
    exchange-enforced leverage_max — exactly the same clamp execute_
    autotrade() already applies right before sending a real order (see
    its own leverage_max handling), reused here so the backtest/live-
    gate liquidation math and the compounding simulation both reflect
    the leverage a real order would actually get, not the configured
    setting regardless of what Gate.io allows on this specific
    contract (altcoins often carry a much lower cap than majors)."""
    try:
        contract_max_lev = get_contract_spec(symbol).get("leverage_max")
    except Exception as e:
        log_error(f"msnr_symbol_effective_leverage {symbol}: {e}")
        contract_max_lev = None
    if contract_max_lev and contract_max_lev < AUTOTRADE_LEVERAGE_MSNR:
        return contract_max_lev
    return AUTOTRADE_LEVERAGE_MSNR


def msnr_symbol_contract_max_leverage(symbol):
    """v0.99.46 — the RAW exchange-enforced leverage_max for this
    contract (get_contract_spec()), with NO clamp to AUTOTRADE_
    LEVERAGE_MSNR — unlike msnr_symbol_effective_leverage() above
    (which picks min(configured, contract_max) for the flat-leverage
    case), this is the CEILING msnr_leverage_for_stop() is allowed to
    scale UP TOWARD for an unusually tight-stop signal; msnr_symbol_
    effective_leverage()'s own min-clamp would silently cap every
    symbol at the configured default and defeat the entire point of
    scaling up in the first place.
    Falls back to AUTOTRADE_LEVERAGE_MSNR itself (i.e. no headroom to
    scale up beyond the configured default) if the contract spec can't
    be fetched — same "degrade to the conservative default" stance
    msnr_symbol_effective_leverage() already takes on the same
    failure."""
    try:
        contract_max_lev = get_contract_spec(symbol).get("leverage_max")
    except Exception as e:
        log_error(f"msnr_symbol_contract_max_leverage {symbol}: {e}")
        contract_max_lev = None
    return contract_max_lev if contract_max_lev else AUTOTRADE_LEVERAGE_MSNR


def msnr_optimal_leverage_for_symbol(trades, ceiling_leverage=None, symbol=None):
    """v0.99.47, per direct user follow-up to v0.99.46 ("чёт лучше не
    стало, будто даже хуже" -> "давай для каждой монеты в рамках
    автотюнинга автоматически выбирать оптимальное плечо для
    долгосрочного роста"): REPLACES v0.99.46's msnr_leverage_for_stop()
    — that heuristic hit its own "lose ~10% of margin on a stop-out"
    target correctly, but a fixed target loss % scales leverage up
    SYMMETRICALLY, amplifying the WIN side by the exact same factor as
    the loss side. Under full-reinvestment compounding, higher
    variance can REDUCE long-run geometric growth even at an unchanged
    (or better) arithmetic edge — the same Kelly-criterion "over-
    betting past optimal hurts compounded growth" point already raised
    earlier this session about the sizing model in general. A target-%
    heuristic has no way to know it's on the wrong side of that curve
    for a given symbol; only actually testing against that symbol's
    own trade history can tell.
    Finds the single leverage L, applied FLAT to every trade in this
    symbol's own history (not varied per-trade by stop width, unlike
    the function this replaces), that MAXIMIZES E[log(1 + pnl_frac(L))]
    over the symbol's own closed (WIN/LOSS) trades — the textbook
    "optimal f" / Kelly-criterion objective for choosing bet size under
    repeated, reinvested exposure: maximizing expected log-growth is
    exactly what maximizes long-run COMPOUNDED wealth (a mathematical
    consequence of the strong law of large numbers applied to a
    sequence of multiplicative i.i.d.-ish returns, not a heuristic
    itself). A single trade's own probability of WIN vs LOSS isn't
    knowable in advance beyond what the symbol's pooled historical
    distribution already implies, so — same reasoning "optimal f"
    (Ralph Vince) already uses — this optimizes ONE leverage against
    the whole historical distribution and applies it uniformly to
    every future trade on this symbol, rather than trying to vary it
    signal-by-signal off a single visible feature (stop width) the way
    the replaced heuristic did.
    Any candidate leverage where even ONE historical trade's own
    pnl_frac(L) <= -1 (would have wiped the account, isolated-margin
    nominal loss) scores negative infinity for that candidate outright
    — ruin is absorbing; no amount of upside on other trades
    compensates for a leverage that has already blown the account once
    in its own visible history.
    v0.99.70 — CRITICAL FIX, per direct user question ("получается на
    бэктесте плечо выходящее за рамки ликвидации?"): the nominal-loss
    ruin check above is NOT the tightest constraint. Gate's own
    maintenance-margin liquidation price is ALWAYS at or before the
    naive 100%-of-margin point (compute_scalp_liquidation_move_pct()'s
    own docstring: "a non-negative MMR+fee can only ever SHRINK this
    buffer... never enlarge it"), so a candidate leverage could pass
    the nominal check above while still meaning some historical LOSS
    trade's own SL sits PAST where the exchange would have actually
    force-liquidated the position first — the exact same "trade beyond
    liquidation" condition msnr_trade_beyond_liquidation() already
    guards live signals against, but this search was never checking it
    against its OWN candidate leverages. When `symbol` is given, each
    LOSS trade's own SL distance is now ALSO checked against that
    symbol's real liquidation buffer (compute_scalp_liquidation_move_
    pct(), same STATE["scalp_mmr_map"]/SCALP_DEFAULT_MMR_PCT/SCALP_
    SAFETY_MARGIN this app's other liquidation checks already use) at
    each candidate leverage — a leverage that would have breached it
    scores -inf too, same absorbing-ruin treatment as the nominal
    check. Without a symbol (backward-compatible default), this check
    is skipped — same "can't evaluate, don't penalize" stance the rest
    of this codebase takes for missing data, not a silent widening of
    what counts as safe.
    Searched as a plain grid from AUTOTRADE_LEVERAGE_MSNR up to
    ceiling_leverage in 0.5x steps rather than a smarter optimizer
    (gradient ascent / golden-section search): this objective is
    well-behaved (concave) for realistic win-rate/RR distributions,
    but a grid is simpler to verify correct, and cheap enough at this
    scale (well under a few hundred candidates even against a very
    high exchange leverage cap) that a fancier search isn't worth the
    risk of a subtler bug for the compute it would save.
    Floored at AUTOTRADE_LEVERAGE_MSNR — never recommends LESS than
    the configured default; a symbol whose own history says even the
    default is already past Kelly-optimal is a stress_test_failed/
    skip_sl_pct_min candidate handled elsewhere, not something this
    function should try to further de-risk by going below the floor.
    v0.99.71 — CRITICAL FIX, found on a direct user request for a full
    professional-trader-style audit of every indicator: this objective
    was computing pnl_frac with NO taker-fee deduction at all, despite
    AUTOTRADE_SIM_FEE_PCT already existing in this codebase for exactly
    this purpose elsewhere. Round-trip fee cost, as a fraction of
    MARGIN (not notional), is `2 * AUTOTRADE_SIM_FEE_PCT * leverage` —
    it scales linearly WITH leverage, because notional = margin *
    leverage and both entry and exit each pay a taker fee on that
    notional. A fee-blind Kelly search finds the leverage optimal in a
    zero-fee world, which is a strict OVERESTIMATE of the true fee-
    inclusive optimum — as leverage grows, fee drag grows right along
    with it, pulling the real optimum lower than what this function
    used to report. Now subtracted from every trade's pnl_frac
    (charged regardless of WIN or LOSS — the exchange collects it
    either way), same ruin/liquidation treatment applying on top of
    the fee-adjusted figure.
    Returns AUTOTRADE_LEVERAGE_MSNR if there are no valid closed trades
    to optimize against at all."""
    ceiling = ceiling_leverage if ceiling_leverage else AUTOTRADE_LEVERAGE_MSNR
    mmr_pct = None
    if symbol is not None:
        with state_lock:
            mmr_map = STATE.get("scalp_mmr_map", {})
        mmr_pct = mmr_map.get(symbol, SCALP_DEFAULT_MMR_PCT)
    moves = []
    for t in trades:
        if t.get("result") not in ("WIN", "LOSS"):
            continue
        entry = t.get("entry")
        sl = t.get("sl")
        tp = t.get("tp")
        if not entry or entry <= 0 or sl is None or tp is None:
            continue
        if t["result"] == "WIN":
            moves.append((1, abs(tp - entry) / entry, None))
        else:
            moves.append((-1, abs(entry - sl) / entry, t.get("direction")))
    if not moves:
        return AUTOTRADE_LEVERAGE_MSNR

    def _log_growth(lev):
        total = 0.0
        fee_frac = 2 * AUTOTRADE_SIM_FEE_PCT * lev
        for sign, move_pct, direction in moves:
            if sign == -1 and mmr_pct is not None and direction:
                liq_buffer_pct = compute_scalp_liquidation_move_pct(direction, lev, mmr_pct)
                if liq_buffer_pct is not None and move_pct * 100 * SCALP_SAFETY_MARGIN > liq_buffer_pct:
                    return float("-inf")
            pnl_frac = sign * move_pct * lev - fee_frac
            if pnl_frac <= -1.0:
                return float("-inf")
            total += math.log(1 + pnl_frac)
        return total / len(moves)

    best_lev = AUTOTRADE_LEVERAGE_MSNR
    best_score = _log_growth(best_lev)
    lev = AUTOTRADE_LEVERAGE_MSNR + 0.5
    while lev <= ceiling:
        score = _log_growth(lev)
        if score > best_score:
            best_score = score
            best_lev = lev
        lev += 0.5
    return round(best_lev, 1)


def msnr_live_balance_for_symbol(symbol):
    """v0.99.33, per direct user request: "40 долларов для первой
    сделки, размер второй сделки зависит от исхода первой, по сути как
    на бэктесте... начинать с 40" — the REAL per-symbol compounding
    margin used to size actual live autotrade orders, mirroring msnr_
    compound_trail()'s backtest math exactly, but tracked against real
    outcomes (update_msnr_signal_outcomes()) instead of historical
    ones. A symbol with no stored balance yet (STATE["msnr_live_
    balance"] missing that key) has never had an autotrade-fired live
    trade — starts at MSNR_COMPOUND_START_BALANCE, same $40 the
    backtest simulation starts at. Always clamped to [0, MSNR_LIVE_
    BALANCE_MAX] on read as well as on write (defensive: covers the
    cap being lowered via settings after a balance already grew past
    the new, smaller ceiling)."""
    with state_lock:
        balance = STATE["msnr_live_balance"].get(symbol)
    if balance is None:
        balance = MSNR_COMPOUND_START_BALANCE
    return max(0.0, min(balance, MSNR_LIVE_BALANCE_MAX))


def msnr_update_live_balance(symbol, result, entry, sl, tp, leverage):
    """v0.99.33 — updates this symbol's REAL live compounding balance
    (see msnr_live_balance_for_symbol()) after an autotrade-fired
    signal actually closes WIN or LOSS. Deliberately the EXACT same
    per-trade P&L formula msnr_compound_trail() uses for the backtest
    simulation (price move % from entry/sl/tp, scaled by `leverage`,
    isolated-margin floor at -100% for a single loss) — this is
    supposed to be the live counterpart of that same math, not a
    parallel implementation that could quietly drift from it. Result
    is additionally capped at MSNR_LIVE_BALANCE_MAX (the hard $ ceiling
    the backtest simulation doesn't have, since compounding an actual
    account isn't supposed to run away unbounded) and floored at 0 (a
    wiped symbol simply prices future orders at $0 margin, which
    compute_position_size() already skips rather than sending a doomed
    order — same passive-stop behavior the backtest's own blown-to-
    zero trail already has, no separate "disable autotrade" step
    needed).
    Called only for WIN/LOSS — a TIMEOUT or still-OPEN signal has no
    realized P&L to compound with, exactly like msnr_compound_trail()
    already treats a TIMEOUT trade."""
    if not entry or entry <= 0 or sl is None or tp is None:
        return  # malformed signal — leave the balance untouched rather than guess
    if result == "WIN":
        move_pct = abs(tp - entry) / entry
        pnl_frac = move_pct * leverage
    elif result == "LOSS":
        move_pct = abs(entry - sl) / entry
        pnl_frac = -move_pct * leverage
    else:
        return
    pnl_frac = max(pnl_frac, -1.0)
    with state_lock:
        current = STATE["msnr_live_balance"].get(symbol)
        if current is None:
            current = MSNR_COMPOUND_START_BALANCE
        new_balance = max(0.0, min(current * (1 + pnl_frac), MSNR_LIVE_BALANCE_MAX))
        STATE["msnr_live_balance"][symbol] = round(new_balance, 2)


def msnr_trade_beyond_liquidation(symbol, direction, entry, sl, leverage=None):
    """v0.99.26, per direct user request ("иногда стоп будет за
    ликвидацией и просто избегать этого"): True if this trade's own SL
    sits past (or too close to) where Gate.io would force-liquidate
    the position first, at this symbol's effective leverage. A wide
    enough stop combined with this contract's own leverage cap and
    maintenance margin rate means the exchange liquidates the position
    — at a worse price, eating extra maintenance-margin/fees — before
    price ever reaches the SL msnr_detect_signals() computed. This
    app's backtest only tracks SL/TP price touches, not margin math, so
    it can't price this in after the fact; has to be filtered before.
    This is the EXACT same check execute_autotrade() already runs
    (v0.70.0) right before a real order — same compute_scalp_
    liquidation_move_pct() formula (Gate's own isolated-margin
    liquidation math — not scalp-specific despite the name, just first
    written for that module), same STATE["scalp_mmr_map"] source
    ("MMR is a property of the Gate contract itself, not of which
    module is trading it" — that function's own reasoning, reused
    verbatim here) with the same SCALP_DEFAULT_MMR_PCT fallback, and
    the same SCALP_SAFETY_MARGIN buffer factor — deliberately not a
    separate/looser threshold, so a trade this function lets through
    is one execute_autotrade() would also actually place.
    Applied here PROACTIVELY (before a backtest trade counts toward a
    symbol's stats, or before a live signal fires) rather than only
    reactively at order time, so the backtest/ranking never credits a
    symbol with a "WIN" or "LOSS" outcome msnr_track_outcome() computed
    off a pure price-touch that a real order would never have survived
    to see.
    entry<=0 or a missing SL returns False (can't evaluate — same
    "skip without penalizing" stance used for other malformed-record
    cases) rather than blocking on incomplete data."""
    if not entry or entry <= 0 or sl is None:
        return False
    leverage = leverage if leverage is not None else msnr_symbol_effective_leverage(symbol)
    with state_lock:
        mmr_map = STATE.get("scalp_mmr_map", {})
    mmr_pct = mmr_map.get(symbol, SCALP_DEFAULT_MMR_PCT)
    liq_buffer_pct = compute_scalp_liquidation_move_pct(direction, leverage, mmr_pct)
    if liq_buffer_pct is None:
        return False
    sl_distance_pct = abs(entry - sl) / entry * 100
    return liq_buffer_pct < sl_distance_pct * SCALP_SAFETY_MARGIN


_msnr_signal_cooldowns = {}  # symbol -> last signaled entry-candle time
_msnr_signal_cooldowns_lock = threading.Lock()
_msnr_addon_cooldowns = {}  # v0.99.126 — symbol -> last add-on signaled candle time, same dedup shape


def msnr_symbol_params(symbol):
    """This symbol's autotuned (min_leg_atr, qm_zone_pct, qm_lookback)
    from STATE["msnr_symbol_overrides"], falling back to the module
    defaults for any not yet optimized (or for a symbol whose optimize
    run errored, e.g. not enough history yet) — same fallback shape as
    ft5_scan_symbol_live()'s override.get(..., grid-middle) pattern.
    Used by BOTH the live scanner and the chart endpoint, so a chart
    always reflects the exact params that actually produced whatever
    signal it's showing."""
    with state_lock:
        override = STATE["msnr_symbol_overrides"].get(symbol) or {}
    return {
        "min_leg_atr": override.get("min_leg_atr", MSNR_MIN_LEG_ATR),
        "qm_zone_pct": override.get("qm_zone_pct", MSNR_QM_ZONE_PCT),
        "qm_lookback": override.get("qm_lookback_bars", MSNR_QM_LOOKBACK_BARS),
    }


def msnr_symbol_skip_rr_min(symbol):
    """v0.99.22 — this symbol's own live-signal RR-skip floor (see
    msnr_symbol_rr_skip_min()), kept as a SEPARATE lookup from msnr_
    symbol_params() rather than folded into that dict: msnr_symbol_
    params()'s return value gets spread as **params straight into msnr_
    detect_signals() at three call sites, whose signature has no skip_
    rr_min kwarg — adding it there would throw a TypeError at every one
    of those call sites, not just the live scanner that actually needs
    it."""
    with state_lock:
        override = STATE["msnr_symbol_overrides"].get(symbol) or {}
    return override.get("skip_rr_min")


def msnr_symbol_skip_rr_max(symbol):
    """v0.99.86 — the FLOOR counterpart to msnr_symbol_skip_rr_min()
    above, added alongside msnr_symbol_rr_range()'s own two-sided
    redesign. Named "_max" (not "_min", despite being a floor) for
    symmetry with the existing "_min" naming: both mean "skip signals
    past THIS edge, in the direction away from the tradeable middle" —
    skip_rr_min is the ceiling (skip rr >= this), skip_rr_max is the
    floor (skip rr < this)."""
    with state_lock:
        override = STATE["msnr_symbol_overrides"].get(symbol) or {}
    return override.get("skip_rr_max")


def msnr_symbol_skip_sl_min(symbol):
    """v0.99.26 — SL-width counterpart to msnr_symbol_skip_rr_min(),
    same reasoning for being a separate lookup (msnr_symbol_params()'s
    return value gets spread as **params into msnr_detect_signals(),
    which has no skip_sl_pct_min kwarg either)."""
    with state_lock:
        override = STATE["msnr_symbol_overrides"].get(symbol) or {}
    return override.get("skip_sl_pct_min")


def msnr_symbol_skip_hours_live(symbol):
    """v0.99.56 — hour-of-day counterpart to msnr_symbol_skip_rr_min()/
    msnr_symbol_skip_sl_min(), same separate-lookup reasoning. Returns
    this symbol's own set of statistically-bad UTC hours (msnr_symbol_
    skip_hours()) as a plain list — empty (not None) when no hour has
    been flagged, so callers can use it directly as `hour in skip_
    hours` without a None-check first."""
    with state_lock:
        override = STATE["msnr_symbol_overrides"].get(symbol) or {}
    return override.get("skip_hours") or []


def msnr_symbol_skip_volume_below(symbol):
    """v0.99.59 — volume-ratio counterpart to msnr_symbol_skip_rr_min()/
    msnr_symbol_skip_sl_min()/msnr_symbol_skip_hours_live(), same
    separate-lookup reasoning (msnr_symbol_params()'s return value gets
    spread as **params into msnr_detect_signals(), which has no
    skip_volume_below kwarg either). Returns this symbol's own volume-
    ratio floor (msnr_symbol_volume_skip_below()) — a live signal whose
    OWN volume_ratio lands below it gets skipped for this symbol — or
    None when no low-volume bucket has been flagged."""
    with state_lock:
        override = STATE["msnr_symbol_overrides"].get(symbol) or {}
    return override.get("skip_volume_below")


def msnr_symbol_optimal_leverage(symbol):
    """v0.99.47 — this symbol's own Kelly-optimal leverage (msnr_
    optimal_leverage_for_symbol(), computed once per backtest cycle in
    msnr_optimize_symbol() against this symbol's own filtered trade
    history), looked up for live signal firing. Same separate-lookup
    reasoning msnr_symbol_skip_rr_min()/msnr_symbol_skip_sl_min()
    already documented — this isn't threaded through msnr_symbol_
    params() either. Falls back to AUTOTRADE_LEVERAGE_MSNR if this
    symbol has no override yet (e.g. its very first backtest cycle
    hasn't completed)."""
    with state_lock:
        override = STATE["msnr_symbol_overrides"].get(symbol) or {}
    optimal = override.get("optimal_leverage")
    return optimal if optimal is not None else AUTOTRADE_LEVERAGE_MSNR


def msnr_compound_trail(trades, start_balance=None, leverage=None):
    """v0.99.25, per direct user follow-up to msnr_compound_return():
    the SAME walk, but returns one entry per actually-compounded CLOSED
    trade instead of collapsing straight to a final number — so the
    compounding math can be checked trade-by-trade (used to annotate
    /api/msnr/backtest/<symbol>'s expanded per-trade UI) rather than
    just trusted as a single end figure. msnr_compound_return() below
    is now a thin reduction over this same trail, so the per-trade
    display and the summary "доход" figure can never silently disagree
    about the underlying math — one calculation, two views of it.
    v0.99.46 briefly varied leverage PER TRADE off that trade's own
    stop width — reverted in v0.99.47, per direct user follow-up
    ("чёт лучше не стало, будто даже хуже"): that scaled the WIN side
    up by the exact same factor as the loss side on every tight-stop
    trade, and under full-reinvestment compounding, the resulting
    higher variance reduced long-run geometric growth for some symbols
    even though each individual trade's own edge hadn't changed — see
    msnr_optimal_leverage_for_symbol()'s own docstring for the
    Kelly-criterion reasoning. Back to ONE flat `leverage` for the
    whole walk, same as before v0.99.46 — callers now pass the
    symbol's own Kelly-optimal value (msnr_optimal_leverage_for_
    symbol()) instead of a stop-width-derived one. Resolves to
    AUTOTRADE_LEVERAGE_MSNR when not given, same default this
    parameter always had.
    TIMEOUT trades and malformed records (missing/invalid entry/sl/tp)
    are skipped entirely — absent from the trail, not shown at some
    placeholder balance — same skip conditions msnr_compound_return()
    already documented. Stops (trail simply ends) once a trade drives
    the balance to 0; a trade that would come after that in time never
    actually happened for this account, so it isn't in the trail.
    Returns a list of dicts in chronological order: {"time",
    "direction", "result", "leverage", "pnl_pct", "balance_before",
    "balance_after"} — direction included alongside time so callers
    matching trail rows back to trade records (e.g. api_msnr_backtest_
    trades()) have a collision-safe key: an A-shape and V-shape level
    can structurally resolve on the exact same entry candle, and time
    alone wouldn't disambiguate that pair. `leverage` echoes the flat
    value used for the whole trail (kept per-row, not just once, so
    the UI's existing per-trade rendering doesn't need special-casing
    for "one value vs per-trade" between backtest and live views).
    v0.99.71 — CRITICAL FIX, found on a direct user request for a full
    professional-trader-style audit of every indicator: pnl_frac had NO
    taker-fee deduction at all, despite AUTOTRADE_SIM_FEE_PCT already
    existing in this codebase for exactly this purpose. Round-trip fee,
    as a fraction of MARGIN, is `2 * AUTOTRADE_SIM_FEE_PCT * leverage`
    — scales linearly with leverage since fees are charged on notional
    (margin * leverage), both entry and exit. At leverage=30x and the
    0.05%/side default, that's already 3% of margin gone to fees alone
    on EVERY trade, win or lose — compounding multiplicatively across a
    trail the same way returns do. The displayed "доход $40→$Y" figure
    was systematically overstated by ignoring this. Now subtracted from
    every trade's pnl_frac (same as msnr_optimal_leverage_for_symbol()'s
    own matching fix — see that function's docstring), charged
    regardless of WIN or LOSS, same isolated-margin floor applying on
    top of the fee-adjusted figure."""
    start_balance = start_balance if start_balance is not None else MSNR_COMPOUND_START_BALANCE
    leverage = leverage if leverage is not None else AUTOTRADE_LEVERAGE_MSNR
    fee_frac = 2 * AUTOTRADE_SIM_FEE_PCT * leverage
    closed = [t for t in trades if t.get("result") in ("WIN", "LOSS")]
    trail = []
    balance = start_balance
    for t in closed:
        if balance <= 0:
            break
        entry = t.get("entry")
        sl = t.get("sl")
        tp = t.get("tp")
        if not entry or entry <= 0 or sl is None or tp is None:
            continue  # malformed trade record — skip without touching the running balance
        if t["result"] == "WIN":
            move_pct = abs(tp - entry) / entry
            pnl_frac = move_pct * leverage - fee_frac
        else:
            move_pct = abs(entry - sl) / entry
            pnl_frac = -move_pct * leverage - fee_frac
        pnl_frac = max(pnl_frac, -1.0)  # isolated-margin floor — can't lose more than the margin risked
        balance_before = balance
        balance = balance * (1 + pnl_frac)
        if balance <= 0:
            balance = 0.0
        trail.append({
            "time": t["time"], "direction": t.get("direction"), "result": t["result"],
            "leverage": round(leverage, 1),
            "pnl_pct": round(pnl_frac * 100, 1),
            "balance_before": round(balance_before, 2),
            "balance_after": round(balance, 2),
        })
    return trail


def msnr_compound_return(trades, start_balance=None, leverage=None):
    """Per direct user request: a compounding $ P&L simulation over one
    symbol's backtest — deliberately separate from msnr_summarize_
    backtest()'s R-multiple stats, which measure the STRATEGY's edge
    independent of position sizing. This measures what actually
    happens to a real account: start with start_balance USD margin
    (default MSNR_COMPOUND_START_BALANCE) on the FIRST closed (WIN/
    LOSS) trade in chronological order, then reinvests the ENTIRE
    resulting balance into the next closed trade, and so on through
    every closed trade in the list passed in — literally "va-bank" the
    whole account every single trade, per the user's own description.
    v0.99.47: `leverage` is a single flat value again (msnr_optimal_
    leverage_for_symbol()'s own Kelly-optimal choice for this symbol,
    typically) — see msnr_compound_trail()'s own docstring for why
    v0.99.46's per-trade stop-width variant was reverted.
    v0.99.25: a thin reduction over msnr_compound_trail() (see its own
    docstring for the full per-trade mechanics — TIMEOUT handling, the
    isolated-margin loss floor, why entry/sl/tp drive the math instead
    of the stored rr field) rather than its own separate walk, so this
    summary and the per-trade trail can never drift apart.
    Returns {"final_balance", "return_pct", "trades_compounded",
    "blown_at_trade"} (blown_at_trade is the 1-based position WITHIN
    the trail — i.e. among trades actually compounded, not raw
    position in the input list, since a malformed trade is skipped
    without consuming a slot), or None if there are no closed trades
    to compound over at all."""
    start_balance = start_balance if start_balance is not None else MSNR_COMPOUND_START_BALANCE
    closed = [t for t in trades if t.get("result") in ("WIN", "LOSS")]
    if not closed:
        return None
    trail = msnr_compound_trail(trades, start_balance, leverage)
    if not trail:
        return {"final_balance": round(start_balance, 2), "return_pct": 0.0,
                "trades_compounded": 0, "blown_at_trade": None}
    final_balance = trail[-1]["balance_after"]
    blown_at = len(trail) if final_balance <= 0 else None
    return {
        "final_balance": final_balance,
        "return_pct": round((final_balance / start_balance - 1) * 100, 1) if start_balance else None,
        "trades_compounded": len(trail),
        "blown_at_trade": blown_at,
    }


def msnr_scan_symbol_live(symbol):
    """Live counterpart to msnr_backtest_symbol() — fetches recent
    structure + entry history, runs the SAME detector (with this
    symbol's autotuned params, see msnr_symbol_params()), and fires only
    if the LAST entry candle produced a brand-new signal not already
    seen for this symbol."""
    if not MSNR_ENABLED:
        return
    try:
        params = msnr_symbol_params(symbol)
        structure_candles = get_candles(symbol, interval=MSNR_STRUCTURE_TF, limit=MSNR_ATR_PERIOD + 250)
        entry_candles = get_candles(symbol, interval=MSNR_ENTRY_TF, limit=params["qm_lookback"] + 200)
        now = time.time()
        s_interval_sec = INTERVAL_SECONDS.get(MSNR_STRUCTURE_TF, 3600)
        e_interval_sec = INTERVAL_SECONDS.get(MSNR_ENTRY_TF, 900)
        structure_candles = [c for c in structure_candles if c["time"] + s_interval_sec <= now]
        entry_candles = [c for c in entry_candles if c["time"] + e_interval_sec <= now]
        if len(structure_candles) < MSNR_ATR_PERIOD + 10 or len(entry_candles) < 10:
            return
        sigs, _pivots = msnr_detect_signals(structure_candles, entry_candles, **params)
        if not sigs:
            return
        sig = sigs[-1]
        if sig["index"] != len(entry_candles) - 1:
            return  # most recent signal isn't off the latest closed entry-TF candle — stale
        # v0.99.22, per direct user request: skip firing if THIS symbol's
        # own backtest showed its rr bucket at-or-above skip_rr_min
        # failing breakeven — see msnr_symbol_rr_skip_min(). Computed
        # from entry/sl/tp directly (same formula msnr_run_backtest()
        # uses), not stored on sig, since msnr_detect_signals() itself
        # doesn't compute rr.
        # v0.99.79 disabled this entirely, per direct user request
        # ("Skip RR>3, давай подобную проверку тоже уберем, пока важно
        # все RR торговать"). v0.99.86 RE-ENABLES it, per a direct
        # follow-up request after live data showed the cost of no RR
        # filtering at all ("много слабых результатов в msnr, по 50
        # сделок а доход околонулевой") — but as msnr_symbol_rr_range()'s
        # two-sided replacement, checking BOTH a ceiling (skip_rr_min,
        # unchanged meaning) AND a floor (skip_rr_max, new) rather than
        # just reverting to the old one-sided rule.
        skip_rr_min = msnr_symbol_skip_rr_min(symbol)
        skip_rr_max = msnr_symbol_skip_rr_max(symbol)
        if skip_rr_min is not None or skip_rr_max is not None:
            risk = abs(sig["entry"] - sig["sl"])
            reward = abs(sig["tp"] - sig["entry"])
            sig_rr = reward / risk if risk > 0 else None
            if sig_rr is not None:
                if skip_rr_min is not None and sig_rr >= skip_rr_min:
                    return  # this symbol's own history says rr this high fails here — skip, don't fire
                if skip_rr_max is not None and sig_rr < skip_rr_max:
                    return  # this symbol's own history says rr this low ALSO fails here — skip, don't fire
        # v0.99.47, per direct user follow-up to v0.99.46 ("чёт лучше
        # не стало, будто даже хуже" -> Kelly/optimal-f search instead
        # of a fixed stop-width target): this signal uses THIS symbol's
        # own Kelly-optimal leverage (msnr_symbol_optimal_leverage(),
        # computed once per backtest cycle against the symbol's whole
        # trade history — msnr_optimal_leverage_for_symbol()'s own
        # docstring has the full reasoning) — a single flat value per
        # symbol, not derived from this one signal's own stop width the
        # way v0.99.46 did. Computed BEFORE the liquidation check below
        # so that check evaluates the leverage this trade will ACTUALLY
        # use.
        dyn_leverage = msnr_symbol_optimal_leverage(symbol)
        # v0.99.26, per direct user request ("иногда стоп будет за
        # ликвидацией и просто избегать этого"): deterministic check —
        # if this signal's own SL sits past where Gate.io would force-
        # liquidate the position at the leverage this trade would
        # actually use, skip firing regardless of any statistics. Same
        # check the backtest filter (msnr_optimize_symbol()) and
        # execute_autotrade()'s own v0.70.0 order-time gate both use —
        # a signal that fails here would also get SKIPPED at order time
        # anyway, this just avoids ever showing it as a live signal in
        # the first place.
        # v0.99.46: walks dyn_leverage DOWN in 0.5x steps (never below
        # AUTOTRADE_LEVERAGE_MSNR) until the liquidation-safety margin
        # clears, since the symbol's own optimal leverage has no
        # awareness of THIS signal's live MMR at firing time — only
        # after exhausting that headroom does a still-failing check
        # mean skip the signal entirely.
        while dyn_leverage > AUTOTRADE_LEVERAGE_MSNR and msnr_trade_beyond_liquidation(
                symbol, sig["direction"], sig["entry"], sig["sl"], leverage=dyn_leverage):
            dyn_leverage = max(AUTOTRADE_LEVERAGE_MSNR, dyn_leverage - 0.5)
        if msnr_trade_beyond_liquidation(symbol, sig["direction"], sig["entry"], sig["sl"], leverage=dyn_leverage):
            return
        # v0.99.26, per direct user request ("фильтр по ширине стопа"):
        # SL-width counterpart to the skip_rr_min check above — see
        # msnr_symbol_sl_skip_min().
        skip_sl_min = msnr_symbol_skip_sl_min(symbol)
        if skip_sl_min is not None and sig["entry"]:
            sig_sl_pct = abs(sig["entry"] - sig["sl"]) / sig["entry"] * 100
            if sig_sl_pct >= skip_sl_min:
                return  # this symbol's own history says a stop this wide fails here — skip, don't fire
        # v0.99.56, per direct user request ("какой фильтр сигналов был
        # бы самым эффективным для внедрения" -> time-of-day): hour-of-
        # day counterpart to the RR/SL-width checks above — see msnr_
        # symbol_skip_hours()'s own docstring for why this is a SET of
        # specific hours rather than a single threshold.
        skip_hours = msnr_symbol_skip_hours_live(symbol)
        if skip_hours and time.gmtime(sig["time"])[3] in skip_hours:
            return  # this symbol's own history says this UTC hour fails here — skip, don't fire
        # v0.99.59, per direct user request ("второй фильтр... про n
        # как в первом не забудь" — volume confirmation on the sweep):
        # LOW relative volume counterpart to the checks above — see
        # msnr_symbol_volume_skip_below()'s own docstring for why this
        # skips BELOW a ceiling rather than above a floor (opposite
        # direction from skip_rr_min/skip_sl_pct_min). sig.get(
        # "volume_ratio") can genuinely be None (no lookback window yet
        # near the very start of fetched history, or a zero-volume
        # baseline) — a None ratio means "can't judge this signal on
        # volume," not "reject it," so this only skips when there's an
        # actual number to compare.
        skip_volume_below = msnr_symbol_skip_volume_below(symbol)
        if skip_volume_below is not None and sig.get("volume_ratio") is not None:
            if sig["volume_ratio"] < skip_volume_below:
                return  # this symbol's own history says a sweep this quiet fails here — skip, don't fire
        with _msnr_signal_cooldowns_lock:
            if _msnr_signal_cooldowns.get(symbol) == sig["time"]:
                return
            _msnr_signal_cooldowns[symbol] = sig["time"]
        # v0.99.50 — BUG FOUND ON LIVE REPORT ("почему-то 2 раза одна и
        # та же сделка в живых"): the cooldown check right above is
        # this function's ONLY internal dedup against re-firing the
        # exact same signal, and it's a plain in-memory dict — NOT part
        # of STATE, never written by save_state()/restored by load_
        # state(). A process restart (this app has a documented history
        # of those, from Gate.io rate-limit pressure to Android killing
        # the background Termux process during idle screen-off time —
        # see the earlier watchdog discussion) wipes it back to empty,
        # while STATE["msnr_signals"] itself (the actual persisted
        # record of what already fired) survives the restart intact.
        # If the same active V-shape/A-shape level is still the most
        # recent qualifying signal after restart (nothing about the
        # market needed to change for that — msnr_detect_signals() has
        # no memory between calls, v_fired/a_fired are local variables
        # reset every single call), the freshly-empty cooldown dict has
        # no record of having already fired it, and it fires again —
        # a second, genuinely duplicate OPEN record for a symbol that
        # already has one, exactly the two identical TIA_USDT rows
        # reported live. has_open_signal_any_module() above doesn't
        # catch this either: it deliberately EXCLUDES msnr_signals from
        # its own check (see that function's own docstring — each
        # module is expected to check its OWN list itself, this is only
        # the cross-module veto), and MSNR never had that self-check at
        # all until now. Checking STATE directly (persisted, survives
        # restart) instead of only the fragile in-memory cooldown closes
        # the gap regardless of WHY the time-based cooldown alone
        # failed to catch it.
        with state_lock:
            if any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in STATE["msnr_signals"]):
                return
        if has_open_signal_any_module(symbol, exclude="msnr_signals"):
            return
        record = {
            "symbol": symbol, "direction": sig["direction"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
            "level": sig["level"], "level_type": sig["level_type"],
            "opposite_level": sig["opposite_level"], "time": sig["time"],
            "detected_at": time.time(), "status": "OPEN", "result": None,
            "exit_price": None, "exit_time": None, "app_version": APP_VERSION,
            # v0.99.33 — see msnr_live_balance_for_symbol()'s own docstring.
            # autotrade_fired/leverage_used are what msnr_update_live_
            # balance() (called from update_msnr_signal_outcomes() once
            # this signal closes WIN/LOSS) needs to know whether/how to
            # update this symbol's real compounding balance — a signal
            # nobody actually traded (autotrade off, or not eligible)
            # has no real P&L to compound with, so it must NOT move the
            # balance just because the price happened to hit TP/SL.
            "autotrade_fired": False, "live_size_usd": None, "leverage_used": None,
            # v0.99.126 — sl_order_id needed so msnr_scan_addon_live()
            # can cancel THIS order once an add-on stacks onto the same
            # position and a new combined SL is placed (see that
            # function's own docstring). addon_fired stops a second
            # add-on ever firing on top of the first — the source's own
            # examples show exactly two positions per idea, not a chain.
            "sl_order_id": None, "addon_fired": False,
        }
        with state_lock:
            STATE["msnr_signals"].appendleft(record)
            autotrade_symbols = dict(STATE["msnr_autotrade_symbols"])
            overrides_snapshot = dict(STATE["msnr_symbol_overrides"])
        # v0.99.18: replaced the old single AUTOTRADE_ENABLED_MSNR gate
        # with a per-symbol toggle, per direct user request for exactly
        # 6 individually-toggleable fields (3 gold + current top 3 non-
        # gold by msnr_rank_by_winrate_sample()). Re-checks CURRENT
        # eligibility here, not just the saved toggle — a symbol that
        # was toggled on while eligible, then later fell out of the
        # top-N (or its backtest started erroring, or it flipped to
        # stress_test_failed), should NOT keep autotrading just because
        # its old toggle value is still True — this is the safety net
        # for the GAP between backtest cycles: msnr_backtest_loop()'s
        # own auto-off logic (v0.99.108) only runs once per cycle, so a
        # symbol that just fell out of top-N moments ago could still
        # have a stale True toggle sitting in STATE until the next
        # cycle catches up and flips it off.
        # v0.99.108, per direct user request ("Ручное управление можно
        # убрать"): now checks against the NARROWER msnr_autotrade_
        # eligible_symbols() (top-N by score) — the broader msnr_
        # manual_toggle_allowed_symbols() (any valid, non-stress_test_
        # failed backtest) existed specifically to let a manually-
        # toggled non-top-10 symbol fire; with manual toggling removed
        # entirely (the toggle is now ONLY ever set by auto-management,
        # which only ever turns it on for genuine top-N members), using
        # the broader set here would leave exactly the gap the user
        # asked to close: a symbol that fell out of top-N between
        # backtest cycles would still pass this broader check and could
        # still fire.
        if AUTOTRADE_ENABLED_MSNR and autotrade_symbols.get(symbol) and symbol in msnr_autotrade_eligible_symbols(overrides_snapshot):
            # v0.99.33, per direct user request: real order sizing now
            # compounds off THIS symbol's own live trade history — $40
            # on the very first autotrade-fired trade, then the whole
            # resulting balance (same math as the backtest simulation,
            # msnr_compound_trail()) on every trade after, hard-capped
            # at MSNR_LIVE_BALANCE_MAX — instead of the shared AUTOTRADE_
            # SIZE_MODE/VALUE every other mode uses.
            # v0.99.47: leverage is dyn_leverage — this symbol's own
            # Kelly-optimal value (msnr_symbol_optimal_leverage()),
            # resolved BEFORE this block and walked back down against
            # the liquidation-safety check (see that check's own
            # comment above), not the old v0.99.46 stop-width-derived
            # value. Reusing the SAME already-checked value here
            # (rather than re-deriving it) guarantees the leverage this
            # order actually places at is the exact one the liquidation
            # check above already verified is safe.
            live_leverage = dyn_leverage
            live_size = msnr_live_balance_for_symbol(symbol)
            # v0.99.45 — BUG FOUND ON AUDIT (per direct user request to
            # review recent MSNR changes for bugs): execute_autotrade()'s
            # return value was being discarded here, and record[
            # "autotrade_fired"] was set to True unconditionally right
            # after the call — regardless of whether a real order
            # actually opened. execute_autotrade() can legitimately
            # return without opening anything: status "SKIPPED" (its own
            # order-time liquidation-safety re-check, or compute_
            # position_size() rejecting the size/margin), "ERROR" (a
            # network/API failure), or "DRY_RUN" (AUTOTRADE_DRY_RUN mode
            # — no real capital moved at all). With the old code, any of
            # those still set autotrade_fired=True, and once this signal
            # later resolved WIN/LOSS, msnr_update_live_balance() would
            # have compounded real P&L math onto this symbol's tracked
            # live balance for a trade that was NEVER ACTUALLY PLACED —
            # silently corrupting the exact number the NEXT real order's
            # size_value comes from. Only "OPENED" and "OPENED_TP_SL_
            # FAILED" (the position itself DID open, even if the TP/SL
            # orders had trouble — the risk is real either way) now
            # count as fired.
            autotrade_result = execute_autotrade("msnr", symbol, sig["direction"], sig["entry"], sig["sl"],
                                                  sig["tp"])
            order_opened = autotrade_result.get("status") in ("OPENED", "OPENED_TP_SL_FAILED")
            # v0.99.134 — same cooldown-release-on-ERROR fix as LSW's own
            # (see that module's own call site comment for the full
            # incident): a bare network ERROR shouldn't permanently burn
            # this signal's one-and-only chance to fire.
            if autotrade_result.get("status") == "ERROR":
                with _msnr_signal_cooldowns_lock:
                    if _msnr_signal_cooldowns.get(symbol) == sig["time"]:
                        del _msnr_signal_cooldowns[symbol]
            # v0.99.34, per direct user follow-up ("как добавить сигналы
            # по msnr в симулятор"): sim_execute_trade() already gets
            # called for every autotrade-fired MSNR signal (same design
            # every other module uses — the paper simulator mirrors
            # real autotrade, not a shadow-mode for every signal
            # unconditionally, confirmed intentional back in v0.99.7),
            # but this call was missed when v0.99.33 wired the new per-
            # symbol live-balance sizing into the REAL order above —
            # left defaulting to the shared AUTOTRADE_SIZE_MODE/VALUE,
            # meaning the paper simulator would silently disagree with
            # what the real order actually risked. Passing the same
            # size_mode="fixed"/size_value=live_size here closes that gap.
            # v0.99.45 — now gated on order_opened, same reasoning as
            # autotrade_fired below: a real order that got SKIPPED/
            # ERRORed shouldn't leave a paper trade behind pretending it
            # went through either, for the same "mirrors what actually
            # happened" reason the simulator exists in the first place.
            if order_opened:
                sim_execute_trade("msnr", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"],
                                   live_leverage, record, size_mode="fixed", size_value=live_size)
                record["autotrade_fired"] = True
                record["live_size_usd"] = live_size
                record["leverage_used"] = live_leverage
                record["sl_order_id"] = autotrade_result.get("sl_order_id")
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        level_txt = "A-shape (resist)" if sig["level_type"] == "A" else "V-shape (support)"
        # v0.99.74, per direct user request ("мне не нужны уведомления
        # в тг по монетам, которые не в автоторговле"): notification now
        # ONLY fires when a real order actually opened — record[
        # "autotrade_fired"] is set True (alongside leverage_used/
        # live_size_usd) only inside the order_opened branch above, so
        # checking it here is the exact same condition, not a separate
        # approximation. Before this, v0.99.55 had every detected
        # signal notify regardless of whether real money was ever at
        # risk, with a "плечо (реком.)" fallback label specifically for
        # the not-autotraded case — that fallback (and the whole
        # notification) is now skipped entirely for those signals
        # instead of sent with a qualifier. The signal itself is still
        # logged and tracked toward WIN/LOSS either way (record[
        # "status"]="OPEN" above runs unconditionally, same as always —
        # see v0.99.73's own "OPEN (сигнал)" UI label for that exact
        # tracked-but-not-traded distinction) — only the Telegram
        # message is now conditional, not the underlying statistics.
        if record.get("autotrade_fired"):
            leverage_txt = f"плечо: {record['leverage_used']}x"
            send_telegram(
                f"{arrow} {symbol} (MSNR QM off {level_txt})\n"
                f"entry: {sig['entry']:.6g}\n"
                f"SL: {sig['sl']:.6g}  TP: {sig['tp']:.6g}\n"
                f"{leverage_txt}",
                category="msnr",
            )
    except Exception as e:
        log_error(f"msnr_live {symbol}: {e}")


def msnr_scan_addon_live(symbol):
    """v0.99.126 — the "добір" (add-on) second position, per direct
    user-forwarded trade screenshot and direct follow-up request ("да
    нет, сразу делай с автоторговлей"). Fires a REAL stacking order —
    see MSNR_ADDON_ENABLED's own comment and execute_autotrade()'s own
    allow_stack docstring for the full context.
    Only runs if this symbol currently has an OPEN, autotrade-fired
    primary MSNR signal with no add-on yet. Scans MSNR_ADDON_TF (30m)
    candles for a fresh QM sweep+reject against that SAME level (via
    msnr_detect_addon_signals()) — if the latest closed add-on-TF
    candle produced one, stacks a real order onto the already-open
    position (execute_autotrade(..., allow_stack=True) — Gate merges
    same-direction orders on one contract into a single blended
    position, there's no such thing as two independently-tracked
    positions on one symbol there).
    SL handling: per direct user decision when the reference material
    didn't specify this (the strategy's own author manages "two
    positions" mentally/on paper, not through an exchange that merges
    them, so this mechanical question genuinely has no answer in the
    source) — the MORE CONSERVATIVE of the primary's own already-live
    SL and the add-on's own fresh SL governs the WHOLE merged position
    (further from price = wider stop), consistent with this exact
    module's own MSNR_SL_BUFFER_MULT lesson (v0.99.104: premature
    stop-outs on stops sitting too close to normal price noise). The
    primary's OLD SL trigger order is cancelled and replaced by a new
    one at the chosen final_sl — otherwise the narrower of the two
    could still fire first regardless of which one is meant to govern.
    TP is left untouched: primary and add-on share the exact same
    target (both aim at the same opposite Storyline level), so
    execute_autotrade() placing a second TP trigger at the same price
    is a harmless duplicate — whichever fires first closes the whole
    position, and reconcile_positions_and_orders() cleans up the
    orphaned remainder either way, same as any other TP/SL pair."""
    if not (MSNR_ENABLED and MSNR_ADDON_ENABLED and AUTOTRADE_ENABLED_MSNR):
        return
    try:
        with state_lock:
            primary = next((s for s in STATE["msnr_signals"]
                             if s["symbol"] == symbol and s.get("status") == "OPEN"
                             and s.get("autotrade_fired") and not s.get("addon_fired")), None)
        if primary is None:
            return
        addon_candles = get_candles(symbol, interval=MSNR_ADDON_TF, limit=MSNR_QM_LOOKBACK_BARS + 100)
        now = time.time()
        addon_interval_sec = INTERVAL_SECONDS.get(MSNR_ADDON_TF, 1800)
        addon_candles = [c for c in addon_candles if c["time"] + addon_interval_sec <= now]
        if len(addon_candles) < 10:
            return
        addon_sigs = msnr_detect_addon_signals(addon_candles, [primary])
        if not addon_sigs:
            return
        asig = addon_sigs[-1]
        if asig["index"] != len(addon_candles) - 1:
            return  # not off the latest closed add-on-TF candle — stale
        with _msnr_signal_cooldowns_lock:  # reusing the same lock, tiny bit of shared state
            if _msnr_addon_cooldowns.get(symbol) == asig["time"]:
                return
            _msnr_addon_cooldowns[symbol] = asig["time"]
        direction = primary["direction"]
        final_sl = min(primary["sl"], asig["sl"]) if direction == "LONG" else max(primary["sl"], asig["sl"])
        autotrade_result = execute_autotrade("msnr", symbol, direction, asig["entry"], final_sl, asig["tp"],
                                              extra={"is_addon": True, "primary_time": primary["time"]},
                                              allow_stack=True)
        order_opened = autotrade_result.get("status") in ("OPENED", "OPENED_TP_SL_FAILED")
        if not order_opened:
            # v0.99.134 — same cooldown-release-on-ERROR fix as every
            # other module's own real-order call site (see LSW's own
            # for the full incident): a bare network ERROR shouldn't
            # permanently burn this add-on's one-and-only chance.
            if autotrade_result.get("status") == "ERROR":
                with _msnr_signal_cooldowns_lock:
                    if _msnr_addon_cooldowns.get(symbol) == asig["time"]:
                        del _msnr_addon_cooldowns[symbol]
            return
        with state_lock:
            primary["addon_fired"] = True
        # v0.99.132 — BUG FOUND (per direct user report, "Не всё что
        # открывается на бирже у меня по автоторговле отображается в
        # симуляторе, только часть сделок"): every OTHER real-order call
        # site in this file pairs execute_autotrade() with a matching
        # sim_execute_trade() call, but this one — the MSNR add-on,
        # v0.99.126 — never had one at all. A real add-on stack opened
        # correctly on the exchange but was completely invisible to the
        # paper simulator. Reuses `primary` as the signal_record (it
        # already represents the WHOLE merged position from here on —
        # see this function's own docstring), and the same leverage/
        # size derivation the primary open itself uses, so the
        # simulator's own math stays consistent with what a real second
        # stack actually looks like size-wise.
        addon_leverage = msnr_symbol_optimal_leverage(symbol)
        addon_size = msnr_live_balance_for_symbol(symbol)
        sim_execute_trade("msnr", symbol, direction, asig["entry"], final_sl, asig["tp"],
                           addon_leverage, primary, size_mode="fixed", size_value=addon_size)
        old_sl_order_id = primary.get("sl_order_id")
        new_sl_order_id = autotrade_result.get("sl_order_id")
        if old_sl_order_id and old_sl_order_id != new_sl_order_id:
            try:
                cancel_price_order(old_sl_order_id)
            except Exception as e:
                log_error(f"msnr_scan_addon_live {symbol}: failed to cancel primary's old SL {old_sl_order_id} after add-on stacked — position may have TWO live SL orders now, check manually: {e}")
        with state_lock:
            primary["sl_order_id"] = new_sl_order_id
            primary["sl"] = final_sl  # this record now describes the WHOLE merged position's own governing stop
        arrow = "\u2b06\ufe0f LONG" if direction == "LONG" else "\u2b07\ufe0f SHORT"
        send_telegram(
            f"{arrow} {symbol} (MSNR ДОБІР — доложились к открытой позиции)\n"
            f"entry (add-on): {asig['entry']:.6g}\n"
            f"итоговый SL (на всю позицию): {final_sl:.6g}  TP: {asig['tp']:.6g}",
            category="msnr",
        )
    except Exception as e:
        log_error(f"msnr_scan_addon_live {symbol}: {e}")


def update_msnr_signal_outcomes():
    now = time.time()
    with state_lock:
        open_signals = [s for s in STATE["msnr_signals"] if s["status"] == "OPEN"]
    all_candles = fetch_candles_concurrent([(s["symbol"], MSNR_ENTRY_TF, 400) for s in open_signals])
    msnr_interval_sec = INTERVAL_SECONDS.get(MSNR_ENTRY_TF, 900)
    for sig, candles in zip(open_signals, all_candles):
        try:
            if candles is None:
                continue
            candles = [c for c in candles if c["time"] + msnr_interval_sec <= now]
            future = [c for c in candles if c["time"] > sig["time"]]
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
            with state_lock:
                if result:
                    sig["status"] = "CLOSED"
                    sig["result"] = result
                    sig["exit_price"] = exit_price
                    sig["exit_time"] = exit_time
            # v0.99.33, per direct user request: this signal's REAL
            # per-symbol live compounding balance only moves for a
            # signal an actual autotrade order was placed for — see
            # this record's own "autotrade_fired" flag, set at signal
            # time in msnr_scan_symbol_live(). Called OUTSIDE the
            # state_lock block above: msnr_update_live_balance() takes
            # its own lock internally, and state_lock isn't reentrant.
            if result and sig.get("autotrade_fired") and sig.get("leverage_used"):
                msnr_update_live_balance(sig["symbol"], result, sig["entry"], sig["sl"], sig["tp"],
                                          sig["leverage_used"])
        except Exception as e:
            log_error(f"msnr_outcome {sig['symbol']}: {e}")


def compute_msnr_signal_stats():
    with state_lock:
        signals = list(STATE["msnr_signals"])
    closed = [s for s in signals if s["status"] == "CLOSED" and s["result"] in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = sum(1 for s in closed if s["result"] == "LOSS")
    timeouts = sum(1 for s in signals if s.get("result") == "TIMEOUT")
    open_n = sum(1 for s in signals if s["status"] == "OPEN")
    total_closed = len(closed)
    winrate = round(wins / total_closed * 100, 1) if total_closed else None
    return {"total": len(signals), "wins": wins, "losses": losses, "timeouts": timeouts,
            "open": open_n, "winrate": winrate}


def msnr_build_backtest_universe():
    """Backtest-only universe: MSNR_SYMBOLS (the original gold-only live-
    scan list) UNION'd with every _USDT symbol clearing MIN_VOL_USD (the
    same liquidity floor used elsewhere in this app) — same get_tickers()
    fallback-field pattern already proven correct for VGI/FT5/Session.
    Explores whether this "Malaysian SNR" OCL/QM-sweep signal logic
    generalizes beyond gold, or is specific to gold's own price
    behavior. v0.99.17: a symbol from this wider exploration set that
    proves itself (see msnr_compute_live_universe() below) now DOES get
    promoted into live scanning, per direct follow-up request — this
    function's own job (which symbols get BACKTESTED) is unchanged,
    it's simply no longer true that live scanning stays gold-only
    forever regardless of what the backtest finds.
    v0.99.48, per direct user request ("может не выбирать топ 70
    ликвидных монет, а в целом выбирать из всех десятку лучших"):
    dropped the additional top-MSNR_BACKTEST_UNIVERSE_SIZE-by-volume
    slice that used to sit on top of the MIN_VOL_USD floor — every
    symbol clearing that floor is now backtested, not just the 70
    MOST liquid among them. The whole point of the top-10 ranking
    (msnr_rank_by_winrate_sample()) is to find the best-PERFORMING
    symbols; capping the candidate pool by liquidity rank first meant
    a symbol with a genuinely better score/compound_return_pct could
    never even be CONSIDERED just because ~70 other symbols happened
    to trade more volume that day — liquidity and signal quality are
    different things, and the cap was silently picking one as a proxy
    for the other. MSNR_BACKTEST_UNIVERSE_SIZE itself is left defined
    (unused by this function now) rather than deleted outright, in
    case a future session wants to reintroduce a cap deliberately —
    but nothing here reads it anymore.
    Trade-off worth knowing: this backtests noticeably MORE symbols
    per cycle now (every sufficiently-liquid _USDT pair — around 180+
    based on this app's own liquid-universe counts elsewhere, not the
    70-symbol cap this replaces), meaning a longer cycle duration and
    more aggregate Gate.io API load per cycle. Not reduced here on
    the assumption that's an acceptable trade for genuinely
    considering the full pool — GLOBAL_HTTP_SEMAPHORE/_global_rate_
    gate() (v0.99.37/38) already cap the aggregate request rate/
    concurrency app-wide regardless of how many symbols any one loop
    is working through, so this doesn't reopen the rate-limiting
    problem those fixes addressed, just makes MSNR's own cycle take
    longer to grind through a bigger list within that same budget."""
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
    top_liquid = [s[0] for s in ranked]
    combined = list(MSNR_SYMBOLS)
    for sym in top_liquid:
        if sym not in combined:
            combined.append(sym)
    return combined


def msnr_compute_live_universe(overrides, bounds=None):
    """v0.99.78, per direct user request ("Убери эту квалификацию с
    вирейтоп 50 и выборкой 40, что раз просил убрать это, технически"):
    the standalone MSNR_LIVE_PROMOTE_MIN_WINRATE/MIN_SAMPLE promotion
    rule is RETIRED — it was the exact mechanism behind the original
    live report this whole ranking redesign started from ("зелёные
    точки не могут стоять не в монетах не из топ 10, если не стоит
    галочка принудительно"): a symbol could earn the live-scan dot
    purely by clearing 50% winrate / 40 closed trades, with no top-10
    standing and no manual checkbox at all. v0.99.75 already removed
    gold's forced inclusion from this rule but left the rule itself
    still running — a symbol could (and, per the live TRX_USDT report,
    did) still get promoted through it alone. This time the rule itself
    is gone, not just gold's special case within it.
    Now simply delegates to msnr_autotrade_eligible_symbols() — the
    current top MSNR_AUTOTRADE_TOP_N by msnr_symbol_rank_score() (see
    that function's own docstring for the winrate/sample/доход
    geometric-mean ranking). A symbol earns the live-scan dot ONLY by
    landing in the top 10, or via msnr_effective_live_universe()'s own
    SEPARATE toggled-on union (v0.99.108 — auto-managed toggles only,
    manual toggling of non-top-10 symbols removed entirely) — exactly
    the two paths the original request described, nothing else.
    `bounds` (from msnr_compute_rank_bounds()) is passed through
    unchanged so this stays consistent with whatever else in the same
    request/cycle is using the same ranking — see msnr_compute_rank_
    bounds()'s own docstring for why sharing it matters."""
    return msnr_autotrade_eligible_symbols(overrides, bounds=bounds)


def msnr_compute_rank_bounds(overrides):
    """v0.99.76 — computes min/max bounds for winrate, raw_closed_n,
    and compound_return_pct across every non-errored symbol (the
    broadest sensible population — deliberately INCLUDING stress_test_
    failed symbols in the bounds computation itself, even though they
    get hard-excluded from actually ranking; excluding them here could
    skew the min/max away from the true observed range). This is the
    SINGLE canonical normalization reference — both msnr_rank_by_
    winrate_sample() (top-10 selection) and api_msnr_status()'s own
    overall table sort call this once and reuse the SAME bounds dict,
    rather than each independently normalizing over its own (different-
    sized) candidate subset. Computing separate bounds per view would
    let the exact same symbol's composite score DIFFER depending on
    which view asked for it — reintroducing the "не плавное убывание"
    discontinuity this whole ranking redesign (v0.99.75) exists to fix,
    just moved from "two different sort keys" to "two different
    normalizations of the same key."
    v0.99.94, per direct user report ("монета делает 3000% по ней,
    проходит следующий бэктест, монета даёт уже 10 процентов, улетает
    из топа"): доход's raw max is now WINSORIZED at the pool's own 90th
    percentile before being used as the normalization ceiling — a
    single symbol's compounding outlier (a rare, extreme-RR trade
    sequence one cycle, gone the next — the exact instability already
    flagged as a known open issue) was setting the ENTIRE POOL's income
    normalization ceiling, meaning that ONE symbol's noisy compounding
    result was silently compressing every OTHER symbol's normalized
    income toward 0 that cycle, then springing back the next cycle once
    the outlier faded — a systemic ranking instability affecting the
    whole pool, not just the volatile symbol's own score. Nothing below
    the 90th percentile is affected at all (msnr_symbol_rank_score()'s
    own _norm() already clamps any value ABOVE the (now-capped) ceiling
    to income_norm=1.0 rather than letting it exceed 1.0 — several
    genuinely-strong symbols tying at "very good" is the correct
    outcome, not a bug). Deliberately percentile-based rather than a
    fixed number (e.g. tied to MSNR_LIVE_BALANCE_MAX's own $40->$500
    growth ceiling) — self-adjusting to whatever the pool's overall
    performance level happens to be this cycle (bull/bear conditions,
    strategy-wide edge shifts) rather than a magic constant that would
    itself eventually need re-tuning.
    Returns {"winrate": (lo, hi), "sample": (lo, hi), "income": (lo,
    hi)} — a metric with zero symbols reporting it falls back to
    (0.0, 1.0), an arbitrary but harmless range (msnr_symbol_rank_
    score() only ever evaluates it against symbols that also lack the
    metric in that case, since nothing WITH it could exist and be
    excluded from these bounds)."""
    winrates, samples, incomes = [], [], []
    for ov in overrides.values():
        if not ov or ov.get("error"):
            continue
        if ov.get("winrate") is not None:
            winrates.append(ov["winrate"])
        raw_closed_n = ov.get("raw_closed_n")
        if raw_closed_n is None:
            raw_closed_n = (ov.get("wins", 0) or 0) + (ov.get("losses", 0) or 0)
        samples.append(raw_closed_n)
        if ov.get("compound_return_pct") is not None:
            incomes.append(ov["compound_return_pct"])

    def _bounds(vals):
        return (min(vals), max(vals)) if vals else (0.0, 1.0)

    income_bounds = (0.0, 1.0)
    if incomes:
        lo = min(incomes)
        hi_capped = _percentile(sorted(incomes), MSNR_RANK_INCOME_WINSORIZE_PCT)
        # a capped ceiling at or below the floor (tiny/degenerate pools,
        # or every value identical) would make _norm()'s own hi-lo<1e-12
        # branch return 0.5 for everyone — harmless, but fall back to
        # the true max in that case so a real, meaningful spread isn't
        # accidentally discarded for a pool too small to have a
        # sensible 90th percentile distinct from its own minimum.
        income_bounds = (lo, hi_capped) if hi_capped > lo else _bounds(incomes)

    return {"winrate": _bounds(winrates), "sample": _bounds(samples), "income": income_bounds}


def msnr_symbol_rank_score(ov, bounds):
    """v0.99.76, per direct user follow-up to v0.99.75's plain
    lexicographic tuple ("Так для того я и написал 3 параметра, чтобы
    на выборку и доход тоже учитывало" — "that's exactly why I wrote 3
    parameters, so sample size and income would ALSO be factored in"):
    a lexicographic sort checks its first key almost to the exclusion
    of the rest (the later keys only ever matter on an exact tie, rare
    with continuous values) — that's not "all three factors," that's
    "winrate alone in practice."
    v0.99.77, per direct further follow-up ("Все три компонента должны
    быть хорошими" — "all three components must be good"): a WEIGHTED
    ARITHMETIC sum (v0.99.76's own first attempt) doesn't actually
    guarantee that either — addition lets a large value on one metric
    COMPENSATE for a weak one on another; with an unbounded metric like
    доход (compound_return_pct has no natural ceiling the way winrate
    does), there's always some extreme-enough income figure that offsets
    a mediocre winrate/sample, no matter how the weights are tuned. What
    "all three must be good" actually calls for mathematically is a
    WEIGHTED GEOMETRIC MEAN (product, not sum) of the three normalized
    factors: winrate_norm^w1 * sample_norm^w2 * income_norm^w3 (weights
    still MSNR_RANK_WINRATE_WEIGHT/SAMPLE_WEIGHT/INCOME_WEIGHT, still
    summing to 1, still descending 0.5/0.3/0.2 by default, matching "эти
    параметре по убыванию главные"). A product structurally CANNOT be
    rescued by strength elsewhere: if any one normalized factor is 0,
    the whole composite is 0, full stop, regardless of how good the
    other two are — this is the actual mathematical shape of "must be
    good on all three," not something weight-tuning under addition could
    ever fully guarantee.
    Known, accepted consequence of switching to a product: min-max
    normalization gives the single WORST symbol in the current pool on
    any one metric an exact 0.0 on that term — under a product, that
    symbol's WHOLE composite collapses to 0 even if its other two
    metrics are otherwise fine, which can look harsh for a symbol that's
    only marginally the pool's worst on one axis (e.g. barely the
    lowest winrate in a tightly-clustered group). Left as-is rather than
    softening it (e.g. a floor above 0) — softening would just be a
    smaller-scale reintroduction of the same compensation this whole
    change exists to remove, and for RANKING purposes (only relative
    order matters, mainly who clears the top 10) collapsing the current
    worst-on-some-axis symbol toward the bottom is the intended
    behavior, not a bug.
    min-max normalizes winrate/raw_closed_n/compound_return_pct each to
    [0, 1] using msnr_compute_rank_bounds()'s own SHARED bounds (see
    that function's docstring for why shared, not per-view) exactly as
    before — only the combination step (product vs sum) changed.
    A symbol missing a given metric scores 0.0 (worst) on that metric's
    normalized term rather than being skipped or defaulting to the
    population average — "no data" isn't evidence of average quality,
    and under a product this now ALSO zeroes the whole composite,
    consistent with "all three must be good": a metric you can't even
    verify isn't "good."
    v0.99.80 — CRITICAL FIX, per direct user report with a live example
    (a symbol at 2% доход over 52 closed trades still scored ~0.49,
    nearly half the maximum possible, comfortably inside top-10):
    v0.99.76-79's DESCENDING weights (0.5/0.3/0.2) turned out to break
    "all three must be good" in a subtle way specific to geometric
    means — raising a value x∈[0,1] to a SMALL exponent w COMPRESSES it
    toward 1 no matter how bad x is (0.061^0.2 ≈ 0.57, nowhere near 0),
    so доход's low weight meant its badness barely dragged the
    composite down, even though that same low weight was ALSO meant to
    convey "доход matters less." A weight in a geometric mean sets both
    of those at once — how much a GOOD value on that factor helps AND
    how much a BAD value hurts — they can't be tuned independently, so
    "доход matters least" and "доход must still be good" were
    mathematically in tension the entire time, not just an edge case.
    Per direct user choice ("Равные веса — настоящее «all must be
    good», без приоритета") over adding a separate hard floor on
    доход: MSNR_RANK_WINRATE_WEIGHT/SAMPLE_WEIGHT/INCOME_WEIGHT are now
    all 1/3 — every factor punishes and rewards identically, restoring
    genuine "all three must be good" at the cost of the descending-
    priority ordering v0.99.76 had tried (and, per this report, failed)
    to express through weight alone.
    Returns a single float composite (higher = better), NOT a tuple —
    callers sort by this directly."""
    def _norm(val, lo, hi):
        if val is None:
            return 0.0
        if hi - lo < 1e-12:
            return 0.5
        return max(0.0, min(1.0, (val - lo) / (hi - lo)))

    raw_closed_n = ov.get("raw_closed_n")
    if raw_closed_n is None:
        raw_closed_n = (ov.get("wins", 0) or 0) + (ov.get("losses", 0) or 0)
    winrate_norm = _norm(ov.get("winrate"), *bounds["winrate"])
    sample_norm = _norm(raw_closed_n, *bounds["sample"])
    income_norm = _norm(ov.get("compound_return_pct"), *bounds["income"])
    return ((winrate_norm ** MSNR_RANK_WINRATE_WEIGHT) *
            (sample_norm ** MSNR_RANK_SAMPLE_WEIGHT) *
            (income_norm ** MSNR_RANK_INCOME_WEIGHT))


def msnr_rank_by_winrate_sample(overrides, exclude=None, bounds=None):
    """Ranks symbols (excluding `exclude`, if given) by msnr_symbol_
    rank_score() against `bounds` (from msnr_compute_rank_bounds()) —
    see those two functions' own docstrings for the exact weighted-
    composite design and why the bounds must be shared across every
    caller, not recomputed per view. `bounds` defaults to computing
    fresh from `overrides` itself when not given (a convenience for a
    caller — tests, mainly — that only needs this one ranking and
    doesn't already have bounds computed from a wider population);
    api_msnr_status() passes its own already-computed bounds explicitly
    so the overall table's sort and this function's top-10 selection
    are guaranteed to agree.
    v0.99.27, per direct user request ("просто не попадает в топ"):
    excludes any symbol with stress_test_failed=True (see msnr_
    optimize_symbol()'s own docstring) — a symbol whose own $
    compounding simulation lost money is unfit to rank/autotrade no
    matter how good its other numbers look; this is a hard gate, not
    part of the ranking score, so it can't be outweighed by strong
    winrate/sample/income values the way a mere penalty could be.
    v0.99.75 dropped the MSNR_AUTOTRADE_TOP_MIN_SAMPLE floor that used
    to sit here — per that same request's own "плавное убывание...
    продолжение вне списка": a hard sample-size exclusion would create
    a GAP in the ranking instead of a smooth decline, and sample size
    is now one of the ranking's own weighted factors anyway, so a thin
    sample naturally pulls a symbol's composite down rather than
    excluding it from the list outright.
    Returns a list of (symbol, override_dict) tuples, already sorted,
    highest-ranked first.
    v0.99.95, per direct user request ("сортировку msnr индикатора
    сделай только по депозиту, топ 10 с винрейтом не ниже 45"): ranking
    no longer uses msnr_symbol_rank_score()'s winrate/sample/доход
    geometric-mean composite. Candidates now need winrate >= 45 to even
    qualify (a hard gate, same treatment as the existing stress_test_
    failed exclusion), and among those that qualify the sort is purely
    by compound_return_pct (доход/deposit growth), descending — no
    blending with sample size or winrate beyond that 45 floor. `bounds`
    is accepted for call-signature compatibility with existing callers
    but is no longer read here."""
    exclude = exclude or set()
    candidates = [(sym, ov) for sym, ov in overrides.items()
                  if ov and not ov.get("error") and sym not in exclude
                  and not ov.get("stress_test_failed")
                  and (ov.get("winrate") or 0) >= 45]
    candidates.sort(key=lambda pair: (pair[1].get("compound_return_pct")
                                       if pair[1].get("compound_return_pct") is not None
                                       else float("-inf")),
                     reverse=True)
    return candidates


def msnr_autotrade_eligible_symbols(overrides, bounds=None):
    """The symbols eligible for an individual autotrade toggle: the
    current top MSNR_AUTOTRADE_TOP_N symbols by msnr_rank_by_winrate_
    sample() — see that function's own docstring, and msnr_symbol_
    rank_score()'s, for the exact ranking criteria. Per direct user
    request: "включать автоторговлю не только по золоту, но и по топ 3
    после сортировки не считая золота" (v0.99.18), raised to top 10 in
    v0.99.19.
    `bounds` (from msnr_compute_rank_bounds()) is passed through to
    msnr_rank_by_winrate_sample() unchanged — api_msnr_status() computes
    it once and passes the SAME dict here and to its own overall table
    sort, so a symbol's ranking is identical whichever one is asking;
    see msnr_compute_rank_bounds()'s own docstring for why that sharing
    matters. Defaults to None (fresh per-call bounds) for a caller that
    only needs this one ranking in isolation.
    v0.99.75, per direct user request ("золото принудительно пока
    убираем"): gold (MSNR_SYMBOLS) is no longer unconditionally
    prepended to this set regardless of its own numbers — it now
    competes for a top-10 slot on the exact same footing as every other
    symbol, via the same ranking. It can still end up in the top 10
    (or not) purely on its own merit; nothing about gold's own
    detection/backtesting changed, only this forced-inclusion special
    case.
    This set can change between backtest cycles as rankings shift — see
    _set_msnr_autotrade_symbol()'s own docstring for what happens to a
    symbol's saved toggle state when it falls out of the top N."""
    ranked = msnr_rank_by_winrate_sample(overrides, bounds=bounds)
    return [sym for sym, _ov in ranked[:MSNR_AUTOTRADE_TOP_N]]


def _msnr_backtest_one_symbol(symbol):
    """Fetch + optimize + summarize for a single symbol — factored out
    so msnr_backtest_loop() can run it concurrently across the whole
    backtest universe instead of sequentially, same reasoning (and the
    same real-world trigger — Gate.io rate-limit pressure under a
    sequential loop) as VGI's own v0.98.4 fix: with up to 30+ symbols
    now instead of 3, a sequential loop would be meaningfully slower
    and more exposed to exactly the 429 pile-up this session already
    diagnosed and fixed at the get_candles() retry level — concurrency
    here is the other half of that same fix, applied proactively rather
    than waiting for a live report to force it. Exceptions are caught
    here (not propagated) so one bad/slow symbol can't take down the
    whole batch, matching every other per-symbol worker in this app.
    v0.99.15: marks itself "in flight" in STATE for the duration of its
    own work, so the panel's progress bar can show which symbols are
    currently being fetched/optimized right now, not just a done/total
    count — per direct user request for visibility into exactly this
    kind of long-running cycle, after a report that a cycle appeared
    stuck with no way to tell what was actually happening."""
    with state_lock:
        STATE["msnr_backtest_in_flight"].append(symbol)
    try:
        override, results, raw_results = msnr_optimize_symbol(symbol)
        return symbol, override, results, raw_results, msnr_summarize_backtest(results)
    except Exception as e:
        log_error(f"msnr_backtest {symbol}: {e}")
        return None
    finally:
        with state_lock:
            if symbol in STATE["msnr_backtest_in_flight"]:
                STATE["msnr_backtest_in_flight"].remove(symbol)
            STATE["msnr_backtest_done"] += 1


def msnr_backtest_loop():
    while True:
        try:
            if not MSNR_ENABLED:
                time.sleep(60)
                continue
            t0 = time.time()
            universe = msnr_build_backtest_universe()
            results_by_symbol = {}
            raw_results_by_symbol = {}
            summary_by_symbol = {}
            overrides_by_symbol = {}
            with state_lock:
                STATE["msnr_backtest_total"] = len(universe)
                STATE["msnr_backtest_done"] = 0
                STATE["msnr_backtest_in_flight"] = []
                STATE["msnr_backtest_running"] = True
                STATE["msnr_backtest_started_at"] = t0
            try:
                # Autotune (v0.99.5): grid-search each symbol's own
                # (min_leg_atr, qm_zone_pct, qm_lookback) instead of always
                # backtesting the module-default params — see msnr_optimize_
                # symbol()'s own docstring. The winning combo's trades ARE
                # the backtest shown/drilled-into in the UI; no separate
                # un-tuned backtest run needed.
                with ThreadPoolExecutor(max_workers=min(WORKERS, len(universe) or 1)) as ex:
                    futs = [ex.submit(_msnr_backtest_one_symbol, s) for s in universe]
                    for fut in as_completed(futs):
                        res = fut.result()
                        if res is None:
                            continue
                        symbol, override, results, raw_results, summary = res
                        overrides_by_symbol[symbol] = override
                        results_by_symbol[symbol] = results
                        raw_results_by_symbol[symbol] = raw_results
                        summary_by_symbol[symbol] = summary
                with state_lock:
                    # v0.99.36 - CRITICAL FIX: this used to overwrite
                    # STATE["msnr_backtest_results"]/_raw/_summary/
                    # _symbol_overrides wholesale with only THIS cycle's
                    # results_by_symbol etc. _msnr_backtest_one_symbol()
                    # returns None on any exception (timeout, Gate.io
                    # 429, transient fetch failure) and such symbols are
                    # simply skipped when building results_by_symbol —
                    # they never make it in. Under a 200+ symbol universe
                    # scanned concurrently, some symbols hitting a
                    # transient error per cycle is close to guaranteed,
                    # so every cycle was silently dropping a chunk of
                    # PREVIOUSLY-successful backtest data (and, via
                    # msnr_compute_live_universe() being fed that same
                    # incomplete dict, dropping those symbols out of live
                    # scanning too) — from the outside this looked
                    # exactly like "выполнил бэктест, через час бэктест
                    # прогоняется заново и всё слетает, будто прогона не
                    # было", per direct user report.
                    # Fix: merge this cycle's results into the existing
                    # STATE dicts instead of replacing them, so a symbol
                    # that failed just THIS cycle keeps its last-known-
                    # good data. Only symbols no longer in the current
                    # `universe` (e.g. fell out of the top-liquid ranking)
                    # are actually dropped, not ones that merely errored.
                    merged_results = dict(STATE.get("msnr_backtest_results") or {})
                    merged_raw = dict(STATE.get("msnr_backtest_results_raw") or {})
                    merged_summary = dict(STATE.get("msnr_backtest_summary") or {})
                    merged_overrides = dict(STATE.get("msnr_symbol_overrides") or {})
                    merged_results.update(results_by_symbol)
                    merged_raw.update(raw_results_by_symbol)
                    merged_summary.update(summary_by_symbol)
                    merged_overrides.update(overrides_by_symbol)
                    universe_set = set(universe)
                    for d in (merged_results, merged_raw, merged_summary, merged_overrides):
                        for sym in list(d.keys()):
                            if sym not in universe_set:
                                del d[sym]
                    STATE["msnr_backtest_results"] = merged_results
                    STATE["msnr_backtest_results_raw"] = merged_raw
                    STATE["msnr_backtest_summary"] = merged_summary
                    STATE["msnr_symbol_overrides"] = merged_overrides
                    STATE["msnr_backtest_universe"] = universe
                    # v0.99.78 — bounds computed here (once, off the just-
                    # merged overrides) and threaded through so this
                    # cycle's live-universe promotion uses the SAME
                    # ranking reference api_msnr_status() will compute
                    # fresh for itself moments later — see msnr_compute_
                    # rank_bounds()'s own docstring for why sharing
                    # bounds (not just the formula) matters for staying
                    # consistent across callers.
                    msnr_rank_bounds = msnr_compute_rank_bounds(merged_overrides)
                    STATE["msnr_live_universe"] = msnr_compute_live_universe(merged_overrides, bounds=msnr_rank_bounds)
                    # v0.99.108, per direct user request ("монеты попавшие
                    # в топ список и винрейт больше 50 помечаются галочкой
                    # авто торговли, если потом такая монета вылетела из
                    # топа то галочку автоматом снимать"): auto-manages
                    # the per-symbol autotrade toggle for the top-N pool —
                    # auto-ON any symbol newly qualifying (in the eligible
                    # top-N AND win_rate > 50), auto-OFF any symbol that
                    # stops qualifying (either condition), but ONLY among
                    # symbols that were themselves part of the auto-
                    # managed pool as of the LAST cycle (msnr_autotrade_
                    # top_set) — critically, this scoping means a symbol
                    # the user manually toggled ON via msnr_manual_toggle_
                    # allowed_symbols()'s own broader "вне топ-10, на свой
                    # страх и риск" feature is NEVER touched by this auto-
                    # off logic, since it never enters msnr_autotrade_
                    # top_set unless it also separately earns a genuine
                    # top-N spot. Symmetric with the entry condition
                    # (falling below EITHER top-N membership or the >50%
                    # winrate bar turns it off, matching how it turned on)
                    # rather than only reacting to ranking changes.
                    eligible_now = set(msnr_autotrade_eligible_symbols(merged_overrides, bounds=msnr_rank_bounds))
                    prev_top_set = set(STATE.get("msnr_autotrade_top_set") or [])
                    autotrade_symbols = STATE["msnr_autotrade_symbols"]
                    for sym in eligible_now:
                        wr = (merged_summary.get(sym) or {}).get("win_rate")
                        if wr is not None and wr > 50 and not autotrade_symbols.get(sym):
                            autotrade_symbols[sym] = True
                    for sym in prev_top_set:
                        if not autotrade_symbols.get(sym):
                            continue
                        wr = (merged_summary.get(sym) or {}).get("win_rate")
                        still_qualifies = sym in eligible_now and wr is not None and wr > 50
                        if not still_qualifies:
                            autotrade_symbols[sym] = False
                    STATE["msnr_autotrade_top_set"] = sorted(eligible_now)
                    STATE["msnr_last_backtest_finished"] = time.time()
                    STATE["msnr_last_backtest_duration"] = round(time.time() - t0, 1)
            finally:
                # v0.99.15 — always clears "running" even if the cycle
                # above raised partway through (e.g. msnr_build_backtest_
                # universe() itself failing), per direct user request for
                # a progress indicator: a stale "running" flag left on
                # after a genuine failure would be worse than the
                # original "не завершился, no detail" problem it's meant
                # to fix — it would show 100% confident progress on a
                # cycle that already died.
                with state_lock:
                    STATE["msnr_backtest_running"] = False
                    STATE["msnr_backtest_in_flight"] = []
        except Exception as e:
            log_error(f"msnr_backtest_loop: {e}")
        # v0.99.40 — Event.wait(timeout=...) instead of a plain sleep:
        # blocks for the same max(300, MSNR_REFRESH_SEC) by default, but
        # api_reset_msnr() can now cut this short via MSNR_BACKTEST_
        # TRIGGER.set() instead of the loop being unreachable until the
        # full hour elapses. Cleared right after so the NEXT cycle's own
        # wait isn't pre-satisfied by a stale set() from this one.
        MSNR_BACKTEST_TRIGGER.wait(timeout=max(300, MSNR_REFRESH_SEC))
        MSNR_BACKTEST_TRIGGER.clear()


def msnr_backtest_watchdog():
    """v0.99.81, per direct user report ("термукс был жив, сигналы
    работали, но бэктест не выполнялся больше 5 часов"): diagnostics-
    only, per direct user choice ("Только диагностика... ничего не
    менять") — does NOT touch msnr_backtest_loop()'s own completion-
    waiting behavior, timeouts, or retry logic in any way. Runs as its
    own lightweight daemon thread, independent of the backtest loop
    itself (so it keeps checking in even if that loop really were stuck
    on something this watchdog can't see into). Every MSNR_BACKTEST_
    WATCHDOG_INTERVAL_SEC, checks whether a cycle has been running
    (STATE["msnr_backtest_running"]) longer than MSNR_BACKTEST_
    WATCHDOG_THRESHOLD_SEC — if so, logs the CURRENT STATE["msnr_
    backtest_in_flight"] list (the same field _msnr_backtest_one_
    symbol() already appends/removes itself from at start/end, no new
    tracking needed) plus done/total progress, so a repeat of this
    incident leaves a concrete trail of exactly which symbol(s) were
    still pending and how far the cycle had gotten — instead of
    another silent multi-hour gap with nothing to diagnose from
    afterward. Only logs ONCE per threshold-crossing per cycle (a
    symbol still stuck 5 minutes later doesn't need a second nearly-
    identical log line — `warned_this_cycle` resets the moment the
    loop next observes the cycle NOT running, i.e. it finished or gave
    up, ready to warn again on the next cycle if that one also runs
    long)."""
    warned_this_cycle = False
    while True:
        time.sleep(MSNR_BACKTEST_WATCHDOG_INTERVAL_SEC)
        try:
            with state_lock:
                running = STATE.get("msnr_backtest_running")
                started_at = STATE.get("msnr_backtest_started_at")
                in_flight = list(STATE.get("msnr_backtest_in_flight") or [])
                done = STATE.get("msnr_backtest_done")
                total = STATE.get("msnr_backtest_total")
            if not running or not started_at:
                warned_this_cycle = False
                continue
            elapsed = time.time() - started_at
            if elapsed > MSNR_BACKTEST_WATCHDOG_THRESHOLD_SEC and not warned_this_cycle:
                log_error(
                    f"msnr_backtest_watchdog: cycle running {round(elapsed / 60, 1)}min "
                    f"(done {done}/{total}), still in flight: {in_flight}"
                )
                warned_this_cycle = True
        except Exception as e:
            log_error(f"msnr_backtest_watchdog: {e}")


def msnr_live_loop():
    while True:
        try:
            if not MSNR_ENABLED:
                time.sleep(60)
                continue
            # v0.99.17: scans STATE["msnr_live_universe"] (MSNR_SYMBOLS
            # union'd with any backtest-qualifying symbol — see msnr_
            # compute_live_universe()), not the static MSNR_SYMBOLS
            # constant directly, per direct user request. Falls back to
            # MSNR_SYMBOLS itself if the backtest hasn't populated this
            # yet (e.g. right after a fresh restart) — gold is always
            # correct to scan regardless of backtest state, so this
            # fallback can't ever leave live scanning empty.
            with state_lock:
                live_universe = list(STATE["msnr_live_universe"]) or list(MSNR_SYMBOLS)
                autotrade_symbols = dict(STATE["msnr_autotrade_symbols"])
                overrides_snapshot = dict(STATE["msnr_symbol_overrides"])
            # v0.99.32, per direct user request ("топ 10 плюс галочка,
            # доп условий не нужно"): union in any symbol the person has
            # explicitly toggled autotrade ON for AND that's currently
            # autotrade-eligible (top-MSNR_AUTOTRADE_TOP_N by score, not
            # stress_test_failed) — msnr_live_universe above is a
            # SEPARATE, older promotion criterion (>50% winrate AND >40
            # closed trades, msnr_compute_live_universe()) that a
            # top-10-by-score symbol can easily fail even while ranking
            # well by score (score is a lower-confidence-bound on mean
            # R, not raw winrate — the two measure different things, so
            # nothing guarantees a symbol clearing one also clears the
            # other). Without this union, checking a top-10 symbol's own
            # autotrade box did literally nothing whenever that symbol's
            # winrate sat at or below 50%: msnr_scan_symbol_live() would
            # never even get CALLED for it — no signal recorded, no
            # Telegram notification, no order, ever, regardless of the
            # checkbox — which is exactly what a live report described
            # ("был сигнал, но ни уведомления, ни авто-открытия").
            # v0.99.35 — this union now lives in msnr_effective_live_
            # universe() (shared with api_msnr_status()'s own "live" dot,
            # which had drifted out of sync with this exact union — see
            # that function's own docstring) instead of being built
            # inline here a second time.
            live_universe = msnr_effective_live_universe(live_universe, overrides_snapshot, autotrade_symbols)
            with ThreadPoolExecutor(max_workers=min(WORKERS, len(live_universe) or 1)) as ex:
                futs = [ex.submit(msnr_scan_symbol_live, s) for s in live_universe]
                for _ in as_completed(futs):
                    pass
            # v0.99.126 — add-on ("добір") scan, AFTER the primary scan
            # above so a primary signal that just fired this exact cycle
            # is already in STATE["msnr_signals"] for msnr_scan_addon_
            # live() to find. Runs over the SAME live_universe — an
            # add-on can only ever fire for a symbol that already has an
            # open, autotrade-fired primary (checked inside the function
            # itself), so scanning symbols with no open primary is just
            # a cheap no-op there, not wasted real risk.
            if MSNR_ADDON_ENABLED:
                with ThreadPoolExecutor(max_workers=min(WORKERS, len(live_universe) or 1)) as ex:
                    futs = [ex.submit(msnr_scan_addon_live, s) for s in live_universe]
                    for _ in as_completed(futs):
                        pass
            update_msnr_signal_outcomes()
        except Exception as e:
            log_error(f"msnr_live_loop: {e}")
        # v0.99.152 — sync to candle close (same fix as lsw_live_loop)
        interval_sec = INTERVAL_SECONDS.get(MSNR_ENTRY_TF, 900)
        now = time.time()
        sleep_sec = (interval_sec - now % interval_sec) + 3
        time.sleep(sleep_sec)


# ============================================================================
# END EXPERIMENTAL: MSNR
# ============================================================================


# ============================================================================
# EXPERIMENTAL: FT5 — port of freqtrade-strategies' Strategy005 — loops
# ============================================================================
def ft5_backtest_loop():
    while True:
        try:
            if not FT5_ENABLED:
                time.sleep(60)
                continue
            t0 = time.time()
            universe = ft5_build_universe()
            with state_lock:
                STATE["ft5_universe"] = universe
                STATE["ft5_symbols_done"] = 0
            for symbol in universe:
                try:
                    result = ft5_optimize_symbol(symbol)
                    with state_lock:
                        STATE["ft5_symbol_overrides"][symbol] = result
                        STATE["ft5_symbols_done"] += 1
                except Exception as e:
                    log_error(f"ft5_optimize {symbol}: {e}")
            # Rank the full FT5_UNIVERSE_SIZE analysis pool by ft5_ranking_
            # score() (a lower-confidence-bound on the mean, v0.98.7 —
            # computed once per symbol in ft5_optimize_symbol()) and keep
            # only the best FT5_LIVE_TOP_N for live scanning — per direct
            # user request: analyze widely, trade narrowly. Went through
            # two fixes: raw avg_pnl_pct (v0.98.0) let a small lucky
            # sample rank above a symbol firing far more often at a
            # slightly lower average; sample-size shrinkage (v0.98.3)
            # fixed that but still let a combo with MORE losses outrank
            # one with fewer losses and a higher average, since it never
            # separately weighed loss frequency, only n. The confidence-
            # bound version naturally penalizes both small samples and
            # high-variance ones (frequent large losses inflate variance
            # directly) with one formula instead of two stacked ad-hoc
            # discounts. Symbols with no result, an error, or too few
            # backtested trades sort to the bottom and naturally never
            # make the live cut.
            with state_lock:
                overrides = dict(STATE["ft5_symbol_overrides"])
                ranked = sorted(
                    overrides.items(),
                    key=lambda kv: (kv[1].get("score") if kv[1] and not kv[1].get("error") else None) or -999,
                    reverse=True,
                )
                STATE["ft5_live_universe"] = [sym for sym, _ in ranked[:FT5_LIVE_TOP_N]]
                STATE["ft5_last_backtest_finished"] = time.time()
                STATE["ft5_last_backtest_duration"] = round(time.time() - t0, 1)
        except Exception as e:
            log_error(f"ft5_backtest_loop: {e}")
        time.sleep(max(3600, FT5_REFRESH_SEC))


def ft5_live_loop():
    while True:
        try:
            if not FT5_ENABLED:
                time.sleep(60)
                continue
            with state_lock:
                live_universe = list(STATE["ft5_live_universe"])
            if live_universe:
                with ThreadPoolExecutor(max_workers=min(WORKERS, len(live_universe))) as ex:
                    futs = [ex.submit(ft5_scan_symbol_live, s) for s in live_universe]
                    for _ in as_completed(futs):
                        pass
            update_ft5_signal_outcomes()
        except Exception as e:
            log_error(f"ft5_live_loop: {e}")
        time.sleep(max(60, FT5_SCAN_INTERVAL_SEC))


# ============================================================================
# END EXPERIMENTAL: FT5
# ============================================================================




# ============================================================================
# MIRROR — "зеркальный уровень" (support/resistance polarity-flip) reversal
# ----------------------------------------------------------------------------
# Built per direct user request after screenshots of a manual trader's
# methodology (Instagram, "bigtrader88"): a support or resistance level
# gets BROKEN, and on price's later RETURN to that same level, it flips to
# the OPPOSITE role — a broken support becomes resistance (SHORT setup) and
# a broken resistance becomes support (LONG setup). The moment this flip is
# confirmed by price touching back is what the trader calls "рождение
# зеркалки" ("birth of the mirror"). Entry is timed with one of several
# candlestick reversal patterns confirming rejection right at that level:
# "внутренний бар" (inside bar), "пинцет" (tweezers — matching wicks),
# "рельсы" (rails — two opposite-color candles with matching body size),
# and "поглощение на дожи" (engulfing off a doji). User chose to build all
# four patterns and the full module (backtest + live scan + autotrade) in
# one pass, per direct choice over a lighter detection-only first version.
# Deliberately HIGH/LOW-based pivots (not MSNR's own OCL/close-based
# pivots — a different, strategy-specific design choice there): a "mirror
# level" is a classic wick-based support/resistance concept, matching
# every example screenshot's own level lines sitting at candle wicks.
# ============================================================================
def mirror_is_inside_bar(c, prev_c):
    """"Внутренний бар" (inside bar) — the single most-used confirmation
    pattern across every example screenshot (used for both entries AND
    exits there). Current candle's full range sits entirely inside the
    previous candle's own range — a sharp contraction in range right at
    the level, read as a stall/reversal signal."""
    return c["high"] <= prev_c["high"] and c["low"] >= prev_c["low"]


def mirror_is_tweezers(c1, c2, direction, tolerance_pct=MIRROR_PATTERN_TOLERANCE_PCT):
    """"Пинцет" (tweezers) — two adjacent candles with matching wick
    extremes: matching HIGHS (tweezer top, bearish — direction "SHORT")
    or matching LOWS (tweezer bottom, bullish — direction "LONG").
    "Matching" is measured as a % of the larger candle's own RANGE (not
    absolute price), so the same tolerance is meaningful on both a
    $0.001 coin and a $100,000 one."""
    rng = max(c1["high"] - c1["low"], c2["high"] - c2["low"], 1e-12)
    if direction == "SHORT":
        return abs(c1["high"] - c2["high"]) / rng <= tolerance_pct / 100.0
    return abs(c1["low"] - c2["low"]) / rng <= tolerance_pct / 100.0


def mirror_is_rails(c1, c2, tolerance_pct=MIRROR_PATTERN_TOLERANCE_PCT):
    """"Рельсы" (rails) — two adjacent candles of OPPOSITE color with
    closely matching body sizes (like railway ties) — a sharp stall in
    directional momentum right at the level. Body size compared as a %
    of the LARGER of the two bodies, same scale-independence reasoning
    as tweezers above."""
    body1 = abs(c1["close"] - c1["open"])
    body2 = abs(c2["close"] - c2["open"])
    if body1 < 1e-12 or body2 < 1e-12:
        return False
    if (c1["close"] > c1["open"]) == (c2["close"] > c2["open"]):
        return False  # must be opposite colors
    return abs(body1 - body2) / max(body1, body2) <= tolerance_pct / 100.0


def mirror_is_engulfing_doji(doji_c, engulf_c, direction, doji_body_pct=10.0):
    """"Поглощение на дожи" (engulfing off a doji) — a doji (body no
    more than doji_body_pct of its own range — indecision) immediately
    followed by a candle, in the reversal direction, whose own body
    fully contains the doji's body."""
    doji_range = doji_c["high"] - doji_c["low"]
    if doji_range <= 0:
        return False
    if abs(doji_c["close"] - doji_c["open"]) / doji_range * 100.0 > doji_body_pct:
        return False
    engulf_up = engulf_c["close"] > engulf_c["open"]
    if direction == "LONG" and not engulf_up:
        return False
    if direction == "SHORT" and engulf_up:
        return False
    lo, hi = min(doji_c["open"], doji_c["close"]), max(doji_c["open"], doji_c["close"])
    e_lo, e_hi = min(engulf_c["open"], engulf_c["close"]), max(engulf_c["open"], engulf_c["close"])
    return e_lo <= lo and e_hi >= hi


def mirror_find_pivots(candles, left=None, right=None):
    """Standard fractal swing-high/low pivot detector — bar i is a
    confirmed swing HIGH once `right` more bars have printed and its OWN
    high is the unique max within [i-left, i+right]; symmetric for swing
    LOW. Ties (two bars sharing the exact same extreme) are deliberately
    NOT treated as a pivot — an ambiguous double-top/bottom shouldn't be
    silently resolved to whichever bar the loop happens to visit first.
    Returns a list of {"type": "high"|"low", "price": ..., "idx": i,
    "confirm_idx": i+right} oldest first — confirm_idx is the index at
    which this pivot becomes KNOWN. No lookahead: nothing before that
    bar's own close may treat this pivot as existing yet, same no-
    lookahead discipline every other pivot-based module in this app
    already follows (see msnr_build_pivots()'s own v0.99.42 fix)."""
    left = left if left is not None else MIRROR_PIVOT_LEFT
    right = right if right is not None else MIRROR_PIVOT_RIGHT
    n = len(candles)
    pivots = []
    for i in range(left, n - right):
        window_highs = [candles[j]["high"] for j in range(i - left, i + right + 1)]
        window_lows = [candles[j]["low"] for j in range(i - left, i + right + 1)]
        if candles[i]["high"] == max(window_highs) and window_highs.count(candles[i]["high"]) == 1:
            pivots.append({"type": "high", "price": candles[i]["high"], "idx": i, "confirm_idx": i + right})
        if candles[i]["low"] == min(window_lows) and window_lows.count(candles[i]["low"]) == 1:
            pivots.append({"type": "low", "price": candles[i]["low"], "idx": i, "confirm_idx": i + right})
    return pivots


def mirror_detect_signals(candles, pivot_left=None, pivot_right=None,
                           touch_tolerance_pct=None, pattern_tolerance_pct=None,
                           max_bars_to_return=None, rr=None, patterns=None):
    """Single walk-forward pass over `candles` (oldest first) implementing
    the full "mirror level" state machine described in this module's own
    header comment:
    1. mirror_find_pivots() finds every confirmed swing high/low.
    2. Each pivot becomes a WATCHED level the moment it's confirmed
       (confirm_idx) — no lookahead, same discipline as every other
       pivot-based module here.
    3. A watched level gets marked BROKEN the first time a bar's own
       CLOSE moves past it in the "invalidating" direction (a support/
       low level breaks on a close BELOW it; a resistance/high level
       breaks on a close ABOVE it) — using the close (not a wick) is
       deliberate: a single wick poking through and immediately
       reclaiming the level isn't the kind of break the source material
       treats as a genuine "зеркалка," only a real close through it is.
    4. Once broken, a level is watched for up to `max_bars_to_return`
       further bars for price to TOUCH back to it (within `touch_
       tolerance_pct` of price) from the other side — a level nobody
       returns to within that window goes stale and stops being
       watched, matching the source's own visible examples (the return
       always happens within a handful of bars, never many days later
       on the same timeframe).
    5. At the bar where price touches back, checks whichever of
       `patterns` (default: all four — inside_bar, tweezers, rails,
       engulfing_doji) confirm a reversal in the correct direction (a
       broken-support level implies a SHORT signal on return; a broken-
       resistance level implies LONG) — the FIRST pattern that matches,
       checked in the fixed order (inside_bar, tweezers, rails,
       engulfing_doji), wins; a level only ever fires ONE signal, then
       stops being watched (matches the source's own examples, which
       never re-trade the exact same level twice).
    Entry = the confirming bar's own close. Stop-loss = just beyond the
    pattern's own extreme in the trade's risk direction (the natural,
    pattern-defined stop the source material itself draws in every
    screenshot, not a fixed %/ATR multiple like this app's more
    mechanical indicators use) — see each pattern's own SL comment
    inline below. Take-profit = entry ± risk × rr (a fixed RR target;
    the source trader's OWN exits are discretionary — watching for
    ANOTHER reversal pattern at the next level rather than one fixed
    number — but a fixed RR is what a mechanical backtest/live-firing
    pipeline needs; MIRROR_RR defaults conservatively within the 1:3
    to 1:20 range the source material itself reports).
    Returns a list of signal dicts (oldest first): {"direction",
    "entry", "sl", "tp", "rr", "pattern", "level_price", "level_type",
    "entry_idx", "entry_time"}."""
    pivot_left = pivot_left if pivot_left is not None else MIRROR_PIVOT_LEFT
    pivot_right = pivot_right if pivot_right is not None else MIRROR_PIVOT_RIGHT
    touch_tolerance_pct = touch_tolerance_pct if touch_tolerance_pct is not None else MIRROR_TOUCH_TOLERANCE_PCT
    pattern_tolerance_pct = pattern_tolerance_pct if pattern_tolerance_pct is not None else MIRROR_PATTERN_TOLERANCE_PCT
    max_bars_to_return = max_bars_to_return if max_bars_to_return is not None else MIRROR_MAX_BARS_TO_RETURN
    rr = rr if rr is not None else MIRROR_RR
    patterns = patterns if patterns is not None else ("inside_bar", "tweezers", "rails", "engulfing_doji")

    pivots = mirror_find_pivots(candles, pivot_left, pivot_right)
    by_confirm_idx = {}
    for p in pivots:
        by_confirm_idx.setdefault(p["confirm_idx"], []).append(p)

    watched = []  # levels not yet broken
    broken = []  # levels broken, awaiting a return touch
    signals = []
    n = len(candles)

    for i in range(n):
        for p in by_confirm_idx.get(i, []):
            watched.append(dict(p))

        c = candles[i]
        still_watched = []
        for lvl in watched:
            if lvl["type"] == "low" and c["close"] < lvl["price"]:
                lvl["break_idx"] = i
                broken.append(lvl)
            elif lvl["type"] == "high" and c["close"] > lvl["price"]:
                lvl["break_idx"] = i
                broken.append(lvl)
            else:
                still_watched.append(lvl)
        watched = still_watched

        still_broken = []
        for lvl in broken:
            if i - lvl["break_idx"] > max_bars_to_return:
                continue  # gone stale, drop it silently
            price = lvl["price"]
            tol = price * touch_tolerance_pct / 100.0
            touched = (c["low"] <= price + tol) if lvl["type"] == "low" else (c["high"] >= price - tol)
            if not touched or i < 1:
                still_broken.append(lvl)
                continue
            direction = "SHORT" if lvl["type"] == "low" else "LONG"
            prev_c = candles[i - 1]
            matched_pattern = None
            sl = None
            if "inside_bar" in patterns and mirror_is_inside_bar(c, prev_c):
                matched_pattern = "inside_bar"
                sl = prev_c["high"] if direction == "SHORT" else prev_c["low"]
            elif "tweezers" in patterns and mirror_is_tweezers(prev_c, c, direction, pattern_tolerance_pct):
                matched_pattern = "tweezers"
                sl = max(prev_c["high"], c["high"]) if direction == "SHORT" else min(prev_c["low"], c["low"])
            elif "rails" in patterns and mirror_is_rails(prev_c, c, pattern_tolerance_pct):
                matched_pattern = "rails"
                sl = max(prev_c["high"], c["high"]) if direction == "SHORT" else min(prev_c["low"], c["low"])
            elif "engulfing_doji" in patterns and mirror_is_engulfing_doji(prev_c, c, direction):
                matched_pattern = "engulfing_doji"
                sl = c["high"] if direction == "SHORT" else c["low"]
            if matched_pattern is None:
                still_broken.append(lvl)  # no pattern yet this bar — keep watching (still within max_bars_to_return next time)
                continue
            entry = c["close"]
            risk = abs(entry - sl)
            if risk <= 0:
                continue  # degenerate — drop this level, don't emit a zero-risk signal
            tp = entry + risk * rr if direction == "LONG" else entry - risk * rr
            signals.append({
                "direction": direction, "entry": entry, "sl": sl, "tp": tp, "rr": rr,
                "pattern": matched_pattern, "level_price": price, "level_type": lvl["type"],
                "entry_idx": i, "entry_time": c["time"],
                # v0.99.98, per external code review batch 1 ("Трекать
                # свежесть возврата к уровню"): how many bars passed
                # between the level's own break and this signal's
                # confirming touch — pure data collection for now (no
                # filter applied yet), to judge on real distribution
                # data in a later pass whether stale returns (broken
                # long ago, touched only after many bars) perform worse
                # than fresh ones.
                "bars_since_break": i - lvl["break_idx"],
            })
        broken = still_broken

    return signals


def mirror_sl_bucket_stats(trades, bucket_scheme=None):
    """v0.99.92, per direct user request ("придумай лучший фильтр для
    этого типа торговли"): SL-width bucket stats for MIRROR's own
    signals, same shape as msnr_sl_bucket_stats() — buckets CLOSED
    trades (WIN/LOSS only) by their own SL distance as a % of entry
    price. Chosen as MIRROR's first real filter (over an RR-range or
    hours/volume filter, MSNR's other options) because SL width here is
    ENTIRELY pattern-derived, not a fixed %/ATR multiple — a tweezers
    with barely-matching wicks produces a tight stop, a rails pattern
    with two large opposite candles produces a wide one. A wide,
    sloppy-pattern stop is exactly the kind of "the pattern only
    loosely matched" case worth filtering out, the same reasoning
    msnr_symbol_sl_skip_min() already established for MSNR.
    Unlike MSNR's own version, no avg_rr per bucket is needed — every
    MIRROR signal shares the SAME fixed RR (MIRROR_RR), so the
    breakeven bar is one constant number, not something to track per
    bucket."""
    scheme = bucket_scheme if bucket_scheme is not None else MIRROR_SL_PCT_BUCKETS
    buckets = []
    for lo, hi in scheme:
        subset = []
        for t in trades:
            if t.get("result") not in ("WIN", "LOSS"):
                continue
            entry = t.get("entry")
            sl = t.get("sl")
            if not entry or entry <= 0 or sl is None:
                continue
            sl_pct = abs(entry - sl) / entry * 100
            if lo <= sl_pct < hi:
                subset.append(t)
        label = f"{lo}-{hi}" if hi != float("inf") else f"{lo}+"
        if not subset:
            buckets.append({"range": label, "lo": lo, "n": 0, "wins": 0, "losses": 0, "winrate": None})
            continue
        wins = sum(1 for t in subset if t["result"] == "WIN")
        n = len(subset)
        buckets.append({"range": label, "lo": lo, "n": n, "wins": wins,
                         "losses": n - wins, "winrate": round(wins / n * 100, 1)})
    return buckets


def mirror_symbol_sl_skip_min(trades, rr=None):
    """v0.99.92 — this symbol's own SL%-width floor: live signals whose
    OWN SL distance lands at or above it get skipped. Cascades MIRROR_
    SL_PCT_BUCKET_SCHEMES from finest to coarsest (same MSNR v0.99.89
    lesson applied from day one here, not discovered the same painful
    way later) so a modest sample doesn't leave every fine bucket under
    the significance bar. Breakeven is ONE constant (100/(1+rr)) since
    every MIRROR signal shares the same fixed RR — no per-bucket avg_rr
    needed the way MSNR's own RR-range filter requires."""
    rr = rr if rr is not None else MIRROR_RR
    breakeven = 100.0 / (1.0 + rr) if rr > 0 else 100.0
    for scheme in MIRROR_SL_PCT_BUCKET_SCHEMES:
        buckets = mirror_sl_bucket_stats(trades, bucket_scheme=scheme)
        failing_edges = [b["lo"] for b in buckets
                          if b["n"] >= MIRROR_SYMBOL_SKIP_MIN_SAMPLE and b["winrate"] is not None
                          and b["winrate"] < breakeven]
        if failing_edges:
            return min(failing_edges)
    return None


def mirror_symbol_pattern_skip(trades, rr=None):
    """v0.99.98, per external code review batch 1 ("Авто-гейт по
    паттерну"): this symbol's own set of statistically-failing
    confirmation patterns — a live signal whose OWN pattern is in this
    set gets skipped, same "trust this symbol's own bucket evidence"
    reasoning mirror_symbol_sl_skip_min() already applies to SL width.
    Same significance bar (MIRROR_SYMBOL_SKIP_MIN_SAMPLE) and breakeven
    threshold (100/(1+rr)) as that function — but deliberately NO
    granularity cascade here: unlike SL width (a continuous scale that
    can be coarsened into wider bins when a fine one lacks sample),
    pattern is a fixed 4-category field with no natural "coarser"
    grouping to fall back to — each of the 4 patterns either clears the
    sample bar on its own or it doesn't; there's nothing to merge it
    into. Returns a set of pattern names (possibly empty) — a symbol
    can end up with 0 to 4 patterns skipped depending on what its own
    history actually shows for each."""
    rr = rr if rr is not None else MIRROR_RR
    breakeven = 100.0 / (1.0 + rr) if rr > 0 else 100.0
    skip = set()
    for pattern in ("inside_bar", "tweezers", "rails", "engulfing_doji"):
        p_trades = [t for t in trades if t.get("pattern") == pattern and t.get("result") in ("WIN", "LOSS")]
        n = len(p_trades)
        if n < MIRROR_SYMBOL_SKIP_MIN_SAMPLE:
            continue
        wins = sum(1 for t in p_trades if t["result"] == "WIN")
        if wins / n * 100 < breakeven:
            skip.add(pattern)
    return skip


def _mirror_checkpoint(results, rr=None):
    """v0.99.92, per direct user request ("по статистике обязательно
    показывать до после как в msnr"): before/after filter diagnostics
    for MIRROR's own backtest pipeline, matching _msnr_filter_
    checkpoint() (v0.99.86). Unlike MSNR (variable per-trade RR, real
    compounding via a Kelly-optimized leverage search), every MIRROR
    signal shares the SAME fixed RR, so "income" is expressed here as
    R-expectancy — the expected R gained per trade at this checkpoint's
    own win rate — rather than a compounded %, a fair and honest proxy
    without inventing an unrelated leverage/compounding model MIRROR
    doesn't actually use."""
    rr = rr if rr is not None else MIRROR_RR
    closed = [r for r in results if r.get("result") in ("WIN", "LOSS")]
    n = len(closed)
    if not n:
        return {"n": 0, "winrate": None, "expectancy_r": None}
    wins = sum(1 for r in closed if r["result"] == "WIN")
    win_frac = wins / n
    return {"n": n, "winrate": round(win_frac * 100, 1),
            "expectancy_r": round(win_frac * rr - (1 - win_frac) * 1, 3)}


def mirror_build_universe():
    """Liquid-symbol pool, same top-by-24h-volume source/shape as ft5_
    build_universe() — capped to MIRROR_UNIVERSE_SIZE. A "mirror level"
    is a general price-action concept, not tied to one specific symbol
    the way XAU LG is to gold, so this scans a broad universe like
    MSNR/FT5 do, not a fixed symbol list."""
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
    return [s[0] for s in ranked[:MIRROR_UNIVERSE_SIZE]]


def mirror_track_outcome(candles, sig, max_wait_bars=MIRROR_MAX_WAIT_BARS):
    """Walks forward from sig['entry_idx']+1 looking for TP/SL touch —
    SL checked first on any bar covering both, same conservative
    convention track_session_outcome() and msnr_track_outcome() already use."""
    n = len(candles)
    for k in range(sig["entry_idx"] + 1, min(n, sig["entry_idx"] + 1 + max_wait_bars)):
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


def mirror_symbol_direction_skip(trades, rr=None):
    """v0.99.107, per direct user request ("если какая-то сторона
    подходит под авто торговлю то в ней ещё можно брать сторону,
    которая лучше по винрейту, а меньшую не торговать" — a live example
    given: LONG winrate 11% vs SHORT 45% on the same symbol): this
    symbol's own set of statistically-failing DIRECTIONS. Same
    significance bar (MIRROR_SYMBOL_SKIP_MIN_SAMPLE) and breakeven
    threshold (100/(1+rr)) as mirror_symbol_pattern_skip()'s own per-
    category check, same "no cascade" reasoning too — only 2
    categories (LONG/SHORT), nothing to coarsen into if one lacks
    sample. Returns a set containing 0, 1, or both of {"LONG", "SHORT"}.

    v0.99.110, per direct user follow-up ("а зачем вообще торговать
    например Лонг с 25% а не только шорт с 60 по одной монете при
    хорошей выборке и там и там, просто брать хорошую сторону и все"):
    a symbol failing on BOTH sides already gets caught by the overall
    winrate>MIRROR_LIVE_MIN_WINRATE gate in mirror_backtest_loop()
    separately — this function's own new, additional job is: even when
    BOTH directions individually clear breakeven (both "profitable" in
    isolation, with sufficient sample), only the STRICTLY BETTER one
    survives — concentrating risk on the stronger edge instead of
    diluting it across a comparatively weak side just because that
    side isn't outright losing money. Per direct, explicit user choice
    ("да, всегда берём строго лучшую сторону, даже если разница
    маленькая") this comparison has NO minimum-gap requirement — even
    a 1-point difference picks a winner, unlike every other significance-
    bar filter in this app. Two-stage logic: (1) the original absolute
    breakeven test, now `<=` instead of `<` — a side sitting EXACTLY at
    breakeven is genuinely break-even, not profit, and skipping it is
    the correct call (found as a live boundary bug while explaining
    this function's own mechanics, fixed in the same pass); (2) only
    among whatever SURVIVED stage 1 (i.e. is individually profitable),
    if BOTH directions survived, drop the weaker of the two — a symbol
    failing stage 1 on both sides is left to the overall winrate gate
    mentioned above, not force-traded on "the less-bad loser"."""
    rr = rr if rr is not None else MIRROR_RR
    breakeven = 100.0 / (1.0 + rr) if rr > 0 else 100.0
    winrates = {}
    for direction in ("LONG", "SHORT"):
        d_trades = [t for t in trades if t.get("direction") == direction and t.get("result") in ("WIN", "LOSS")]
        n = len(d_trades)
        if n < MIRROR_SYMBOL_SKIP_MIN_SAMPLE:
            continue
        wins = sum(1 for t in d_trades if t["result"] == "WIN")
        winrates[direction] = wins / n * 100
    skip = {d for d, wr in winrates.items() if wr <= breakeven}
    survivors = [d for d in winrates if d not in skip]
    if len(survivors) == 2:
        skip.add(min(survivors, key=lambda d: winrates[d]))
    return skip


def mirror_filter_by_volume(results, candles, lookback=None, mult=None):
    """v0.99.142 — same "genuine reversal should show real participation"
    reasoning as LSW's own volume filter (v0.99.139), adapted for
    Mirror: a UNIFORM threshold applied identically to every symbol
    (deliberately NOT another per-symbol auto-derived one like mirror_
    symbol_sl_skip_min/pattern_skip/direction_skip above). Mirror's own
    result dicts carry "time" but not a candle index, so this builds a
    time->index lookup against the SAME candles array the signal was
    detected from, then checks that candle's own volume against the
    average of the `lookback` bars before it (excluding itself). A
    result whose own time can't be matched, or with too little
    preceding history, is KEPT — nothing to judge isn't a reason to
    drop it, same convention as every other filter in this file."""
    lookback = lookback if lookback is not None else MIRROR_VOLUME_FILTER_LOOKBACK
    mult = mult if mult is not None else MIRROR_VOLUME_FILTER_MULT
    time_to_idx = {c["time"]: i for i, c in enumerate(candles)}
    kept = []
    for r in results:
        idx = time_to_idx.get(r["time"])
        if idx is None:
            kept.append(r)
            continue
        window = candles[max(0, idx - lookback):idx]
        if len(window) < max(3, lookback // 2):
            kept.append(r)
            continue
        avg_vol = sum(c["volume"] for c in window) / len(window)
        sig_vol = candles[idx]["volume"]
        if avg_vol <= 0 or sig_vol >= mult * avg_vol:
            kept.append(r)
    return kept


def mirror_filter_by_htf_trend(results, bias_series, htf_interval_sec):
    """v0.99.142 — same higher-timeframe trend concept as LSW's own
    (v0.99.121) and MSNR's own (v0.99.141), reused here via the shared
    lsw_htf_bias_at() lookup rather than a third copy of the EMA/bias
    logic: a LONG only survives if the HTF bias at its own entry time
    is UP or NEUTRAL, a SHORT only survives if it's DOWN or NEUTRAL. A
    result whose own HTF bar hadn't closed yet (bias is None) is
    dropped too — conservative, matching both other modules' versions."""
    kept = []
    for r in results:
        bias = lsw_htf_bias_at(bias_series, r["time"], htf_interval_sec)
        if bias is None:
            continue
        if r["direction"] == "LONG" and bias == "DOWN":
            continue
        if r["direction"] == "SHORT" and bias == "UP":
            continue
        kept.append(r)
    return kept


def mirror_autotune_tolerances(symbol, days=MIRROR_BACKTEST_DAYS):
    """v0.99.130 — per-symbol autotuning of MIRROR_TOUCH_TOLERANCE_PCT/
    MIRROR_PATTERN_TOLERANCE_PCT with a real walk-forward safeguard, per
    direct user question about whether this would be "дикая подгонка."
    Fetches the full MIRROR_BACKTEST_DAYS window ONCE, splits it by time
    into an earlier TRAIN slice (MIRROR_AUTOTUNE_TRAIN_FRACTION, default
    70%) and a later, held-out TEST slice (the remaining 30%) — the
    split direction matters: train is always the OLDER portion, test
    the NEWER, since the newer slice is the one closer to what live
    trading will actually see next.
    For each (touch, pattern) combo in the small MIRROR_AUTOTUNE_
    TOUCH_GRID x MIRROR_AUTOTUNE_PATTERN_GRID grid (deliberately coarse
    — 4x3=12 combos, not a fine continuous search, to limit how many
    chances there are for one to win purely by luck):
    1. Run mirror_detect_signals() + mirror_track_outcome() on the TRAIN
       slice alone. Skip the combo entirely if train sample < MIRROR_
       AUTOTUNE_MIN_TRAIN_SAMPLE or train winrate <= MIRROR_AUTOTUNE_
       MIN_WINRATE — not worth even checking against test.
    2. Only THEN run the same combo on the TEST slice (never touched
       during train-side selection). Skip if test sample < MIRROR_
       AUTOTUNE_MIN_TEST_SAMPLE or test winrate <= MIRROR_AUTOTUNE_
       MIN_WINRATE.
    Among combos that clear BOTH slices independently, picks the one
    with the highest TEST winrate (the honest, held-out estimate —
    ranking by train winrate here would just reintroduce the same in-
    sample bias this whole split exists to avoid), breaking ties by
    higher combined train+test sample. Returns None (use the plain
    module-wide defaults) if no combo clears both — same as if
    autotuning were off for that symbol.
    Returns {"touch_tolerance_pct", "pattern_tolerance_pct",
    "train_winrate", "train_n", "test_winrate", "test_n"} or None."""
    now = time.time()
    fetch_start = now - days * 86400
    candles = get_candles_range(symbol, MIRROR_INTERVAL, fetch_start, now)
    min_len = MIRROR_PIVOT_LEFT + MIRROR_PIVOT_RIGHT + 20
    if len(candles) < min_len * 2:
        return None  # not enough history to split into two independently-usable slices at all
    split_idx = int(len(candles) * MIRROR_AUTOTUNE_TRAIN_FRACTION)
    train_candles = candles[:split_idx]
    test_candles = candles[split_idx:]
    if len(train_candles) < min_len or len(test_candles) < min_len:
        return None

    def _winrate_and_n(cands, touch, pattern):
        sigs = mirror_detect_signals(cands, touch_tolerance_pct=touch, pattern_tolerance_pct=pattern)
        wins = losses = 0
        for sig in sigs:
            result, _exit_time = mirror_track_outcome(cands, sig)
            if result == "WIN":
                wins += 1
            elif result == "LOSS":
                losses += 1
        n = wins + losses
        wr = (wins / n * 100.0) if n else None
        return wr, n

    validated = []
    for touch in MIRROR_AUTOTUNE_TOUCH_GRID:
        for pattern in MIRROR_AUTOTUNE_PATTERN_GRID:
            train_wr, train_n = _winrate_and_n(train_candles, touch, pattern)
            if train_n < MIRROR_AUTOTUNE_MIN_TRAIN_SAMPLE or train_wr is None or train_wr <= MIRROR_AUTOTUNE_MIN_WINRATE:
                continue
            test_wr, test_n = _winrate_and_n(test_candles, touch, pattern)
            if test_n < MIRROR_AUTOTUNE_MIN_TEST_SAMPLE or test_wr is None or test_wr <= MIRROR_AUTOTUNE_MIN_WINRATE:
                continue
            validated.append({
                "touch_tolerance_pct": touch, "pattern_tolerance_pct": pattern,
                "train_winrate": round(train_wr, 1), "train_n": train_n,
                "test_winrate": round(test_wr, 1), "test_n": test_n,
            })
    if not validated:
        return None
    validated.sort(key=lambda c: (c["test_winrate"], c["train_n"] + c["test_n"]), reverse=True)
    return validated[0]


def mirror_backtest_symbol(symbol, days=MIRROR_BACKTEST_DAYS, touch_tolerance_pct=None, pattern_tolerance_pct=None):
    """Fetches MIRROR_BACKTEST_DAYS of MIRROR_INTERVAL history, runs the
    detector + outcome tracker over the whole window, then applies this
    symbol's own SL-width filter (mirror_symbol_sl_skip_min(), derived
    from the RAW unfiltered results — filtering first would shrink the
    very bucket evidence the threshold is judged from, same ordering
    MSNR's own filters always use), then this symbol's own pattern
    filter (mirror_symbol_pattern_skip(), v0.99.98 — derived off
    whatever survived the SL filter, extending the same evidence chain
    rather than starting over from raw), then this symbol's own
    direction filter (mirror_symbol_direction_skip(), v0.99.107 —
    derived off whatever survived the pattern filter, same evidence-
    chain discipline). Returns (filtered_results, meta) where meta =
    {"skip_sl_pct_min", "skip_pattern", "skip_direction", "checkpoints"}
    — checkpoints is a 4-entry before/after chain ("raw" -> "sl_filter"
    -> "pattern_filter" -> "direction_filter"), per direct user request
    ("по статистике обязательно показывать до после как в msnr")."""
    now = time.time()
    fetch_start = now - days * 86400
    candles = get_candles_range(symbol, MIRROR_INTERVAL, fetch_start, now)
    if len(candles) < MIRROR_PIVOT_LEFT + MIRROR_PIVOT_RIGHT + 20:
        return [], {"skip_sl_pct_min": None, "skip_pattern": [], "skip_direction": [], "checkpoints": []}
    sigs = mirror_detect_signals(candles, touch_tolerance_pct=touch_tolerance_pct, pattern_tolerance_pct=pattern_tolerance_pct)
    raw_results = []
    for sig in sigs:
        result, exit_time = mirror_track_outcome(candles, sig)
        raw_results.append({
            "time": sig["entry_time"], "direction": sig["direction"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"],
            "rr": sig.get("rr"), "pattern": sig.get("pattern"),
            "level_price": sig.get("level_price"), "level_type": sig.get("level_type"),
            "bars_since_break": sig.get("bars_since_break"),
            "result": result, "exit_time": exit_time,
        })
    checkpoints = [{"stage": "raw", **_mirror_checkpoint(raw_results)}]
    skip_sl_min = mirror_symbol_sl_skip_min(raw_results)
    if skip_sl_min is not None:
        filtered = [r for r in raw_results
                    if not r.get("entry") or r["entry"] <= 0 or r.get("sl") is None
                    or abs(r["entry"] - r["sl"]) / r["entry"] * 100 < skip_sl_min]
    else:
        filtered = raw_results
    checkpoints.append({"stage": "sl_filter", **_mirror_checkpoint(filtered)})
    # v0.99.98, per external code review batch 1 ("Авто-гейт по
    # паттерну"): same ordering reasoning as the SL-width filter above
    # — derive skip_pattern off whatever survived the SL filter (not
    # raw_results again), so a pattern's own winrate is judged on the
    # same evidence the symbol's final reported stats are, then apply
    # it as its own checkpoint stage, extending the raw -> sl_filter ->
    # pattern_filter chain.
    skip_pattern = mirror_symbol_pattern_skip(filtered)
    if skip_pattern:
        filtered = [r for r in filtered if r.get("pattern") not in skip_pattern]
    checkpoints.append({"stage": "pattern_filter", **_mirror_checkpoint(filtered)})
    # v0.99.107, per direct user report of a stark LONG/SHORT asymmetry
    # (11% vs 45% winrate on the same symbol): same ordering discipline
    # as the two filters above — derive off whatever survived the
    # pattern filter, extending the chain rather than restarting from
    # raw or from post-SL-only evidence.
    skip_direction = mirror_symbol_direction_skip(filtered)
    if skip_direction:
        filtered = [r for r in filtered if r.get("direction") not in skip_direction]
    checkpoints.append({"stage": "direction_filter", **_mirror_checkpoint(filtered)})
    # v0.99.142 — 2 new GLOBAL (not per-symbol-tuned, unlike every
    # filter above) optional stages. Their own solo checkpoint is
    # ALWAYS computed and appended (what this filter would do on top
    # of everything above), even while its own toggle is off — same
    # "let the person judge before enabling" principle as Sweep/MSNR's
    # own optional filters — but `filtered` is only actually narrowed
    # when the toggle is genuinely on.
    volume_candidates = mirror_filter_by_volume(filtered, candles)
    if MIRROR_VOLUME_FILTER_ENABLED:
        filtered = volume_candidates
        checkpoints.append({"stage": "volume_filter", **_mirror_checkpoint(filtered)})
    else:
        checkpoints.append({"stage": "volume_filter", **_mirror_checkpoint(volume_candidates)})
    htf_candles = None
    try:
        htf_interval_sec = INTERVAL_SECONDS.get(MIRROR_HTF_INTERVAL, 14400)
        htf_fetch_start = fetch_start - MIRROR_HTF_EMA_PERIOD * htf_interval_sec
        htf_candles = get_candles_range(symbol, MIRROR_HTF_INTERVAL, htf_fetch_start, now)
    except Exception as e:
        log_error(f"mirror_backtest_symbol {symbol}: HTF fetch for trend filter failed: {e}")
    if htf_candles and len(htf_candles) >= MIRROR_HTF_EMA_PERIOD:
        bias_series = lsw_htf_bias_series(htf_candles, period=MIRROR_HTF_EMA_PERIOD, buffer_pct=MIRROR_HTF_TREND_BUFFER_PCT)
        htf_candidates = mirror_filter_by_htf_trend(filtered, bias_series, htf_interval_sec)
    else:
        htf_candidates = filtered  # not enough HTF history to judge — informational preview only, matches "nothing to judge, keep" convention
    if MIRROR_HTF_FILTER_ENABLED:
        filtered = htf_candidates if (htf_candles and len(htf_candles) >= MIRROR_HTF_EMA_PERIOD) else []
        checkpoints.append({"stage": "htf_filter", **_mirror_checkpoint(filtered)})
    else:
        checkpoints.append({"stage": "htf_filter", **_mirror_checkpoint(htf_candidates)})
    return filtered, {"skip_sl_pct_min": skip_sl_min, "skip_pattern": sorted(skip_pattern),
                       "skip_direction": sorted(skip_direction), "checkpoints": checkpoints}


def mirror_summarize_backtest(results):
    total = len(results)
    if not total:
        return {"n": 0, "win_rate": None, "wins": 0, "losses": 0, "timeouts": 0,
                "by_direction": {"LONG": {"n": 0, "wins": 0, "losses": 0, "win_rate": None},
                                  "SHORT": {"n": 0, "wins": 0, "losses": 0, "win_rate": None}}}
    wins = sum(1 for r in results if r["result"] == "WIN")
    losses = sum(1 for r in results if r["result"] == "LOSS")
    timeouts = sum(1 for r in results if r["result"] == "TIMEOUT")
    closed = wins + losses
    win_rate = round(wins / closed * 100, 1) if closed else None
    # v0.99.98, per external code review batch 1 ("Разбивка статистики
    # по направлению"): LONG and SHORT come from structurally different
    # setups (broken support flipping to resistance vs broken resistance
    # flipping to support) — pooling them into one winrate could hide a
    # real asymmetry between the two. Same shape as compute_mirror_
    # signal_stats()'s own by_pattern, purely informational for now (no
    # gate applied), same batch-1 "collect, don't filter yet" scope as
    # bars_since_break above.
    by_direction = {}
    for d in ("LONG", "SHORT"):
        d_results = [r for r in results if r.get("direction") == d and r["result"] in ("WIN", "LOSS")]
        d_wins = sum(1 for r in d_results if r["result"] == "WIN")
        by_direction[d] = {
            "n": len(d_results), "wins": d_wins, "losses": len(d_results) - d_wins,
            "win_rate": round(d_wins / len(d_results) * 100, 1) if d_results else None,
        }
    return {"n": total, "win_rate": win_rate, "wins": wins, "losses": losses, "timeouts": timeouts,
            "by_direction": by_direction}


_mirror_signal_cooldowns = {}  # symbol -> last-signaled entry_time
_mirror_signal_cooldowns_lock = threading.Lock()
_mirror_filtered_signal_cooldowns = {}  # v0.99.114 — same dedup shape as _mirror_signal_cooldowns above, kept SEPARATE so a filtered-out signal's own cooldown never interferes with a real signal's (they're mutually exclusive per-scan anyway, but keeping them apart avoids any future confusion about which dict a given entry_time belongs to)
_mirror_filtered_signal_cooldowns_lock = threading.Lock()


def mirror_scan_symbol_live(symbol):
    """Live counterpart to mirror_backtest_symbol() — fetches recent
    history, runs the SAME detector, and fires only if the LAST candle
    produced a brand-new signal not already seen for this symbol.
    v0.99.92 — also applies THIS symbol's own SL-width floor (from its
    latest backtest, STATE["mirror_symbol_overrides"]) before firing:
    a live signal whose own SL distance lands in the same statistically-
    bad-width zone the backtest found for this symbol gets skipped,
    same "trust this symbol's own bucket evidence" reasoning MSNR's own
    skip_rr_min/skip_sl_pct_min live-firing checks already use.
    v0.99.107 — same reasoning extended to direction: a live signal
    whose own direction (LONG/SHORT) is the one this symbol's backtest
    found to be statistically failing gets skipped too, even if the
    OTHER direction is genuinely strong enough for the symbol overall
    to have qualified for live trading.
    v0.99.114, per direct user question ("может без применения фильтра
    было лучше, а после него стало хуже"): a fair, pointed critique —
    every "does this filter help" claim so far rested purely on the
    backtest's own retrospective self-consistency (the filter was
    DERIVED from, then judged against, the exact same historical data),
    which is exactly the kind of circular validation that's vulnerable
    to in-sample overfitting, especially with a modest per-bucket
    sample (MIRROR_SYMBOL_SKIP_MIN_SAMPLE=15) and a 3-stage chain where
    each filter narrows what the next one judges. Rather than argue
    this abstractly, a filtered-out signal now gets recorded (STATE
    ["mirror_filtered_signals"]) and tracked through the exact same
    WIN/LOSS/TIMEOUT outcome logic as a real signal — just never fired
    via execute_autotrade()/sim_execute_trade(), no Telegram alert.
    Real forward data, not backtest hindsight: over time, compare this
    pool's own winrate against the real, filter-approved signals' own
    winrate — if the filter is doing its job, the filtered-out pool
    should trade meaningfully worse; if it doesn't, that's genuine
    evidence the filter is net harmful and too aggressive, not just a
    hunch."""
    if not MIRROR_ENABLED:
        return
    try:
        candles = get_candles(symbol, interval=MIRROR_INTERVAL, limit=MIRROR_LOOKBACK)
        interval_sec = INTERVAL_SECONDS.get(MIRROR_INTERVAL, 3600)
        now = time.time()
        candles = [c for c in candles if c["time"] + interval_sec <= now]  # drop still-forming candle
        if len(candles) < MIRROR_PIVOT_LEFT + MIRROR_PIVOT_RIGHT + 20:
            return
        with state_lock:
            tuned = STATE["mirror_tuned_tolerances"].get(symbol)
        sigs = mirror_detect_signals(
            candles,
            touch_tolerance_pct=tuned["touch_tolerance_pct"] if tuned else None,
            pattern_tolerance_pct=tuned["pattern_tolerance_pct"] if tuned else None,
        )
        if not sigs:
            return
        sig = sigs[-1]
        if sig["entry_idx"] != len(candles) - 1:
            return  # most recent signal isn't off the latest closed candle — already stale/handled
        with state_lock:
            overrides = STATE["mirror_symbol_overrides"].get(symbol) or {}
            skip_sl_min = overrides.get("skip_sl_pct_min")
            skip_direction = set(overrides.get("skip_direction") or [])
        filter_reason = None
        if skip_sl_min is not None and sig["entry"]:
            sig_sl_pct = abs(sig["entry"] - sig["sl"]) / sig["entry"] * 100
            if sig_sl_pct >= skip_sl_min:
                filter_reason = "sl_width"  # this symbol's own backtest says SL this wide fails here
        if filter_reason is None and sig["direction"] in skip_direction:
            filter_reason = "direction"  # this symbol's own backtest says THIS direction fails here
        # v0.99.142 — 2 new GLOBAL (not per-symbol) checks, only run if
        # their own toggle is actually on (unlike the backtest's own
        # "always preview" solo checkpoints — a live scan shouldn't pay
        # an extra HTF fetch for a toggle that's off). Routed through
        # the SAME shadow-tracking "filtered signal" pool as the two
        # per-symbol checks above, just with their own filter_reason.
        if filter_reason is None and MIRROR_VOLUME_FILTER_ENABLED:
            idx = sig["entry_idx"]
            window = candles[max(0, idx - MIRROR_VOLUME_FILTER_LOOKBACK):idx]
            if len(window) >= max(3, MIRROR_VOLUME_FILTER_LOOKBACK // 2):
                avg_vol = sum(c["volume"] for c in window) / len(window)
                sig_vol = candles[idx]["volume"]
                if avg_vol > 0 and sig_vol < MIRROR_VOLUME_FILTER_MULT * avg_vol:
                    filter_reason = "volume"
        if filter_reason is None and MIRROR_HTF_FILTER_ENABLED:
            htf_interval_sec = INTERVAL_SECONDS.get(MIRROR_HTF_INTERVAL, 14400)
            htf_candles = get_candles(symbol, interval=MIRROR_HTF_INTERVAL, limit=MIRROR_HTF_EMA_PERIOD + 10)
            htf_now = time.time()
            htf_candles = [c for c in htf_candles if c["time"] + htf_interval_sec <= htf_now]
            if len(htf_candles) >= MIRROR_HTF_EMA_PERIOD:
                bias_series = lsw_htf_bias_series(htf_candles, period=MIRROR_HTF_EMA_PERIOD, buffer_pct=MIRROR_HTF_TREND_BUFFER_PCT)
                bias = lsw_htf_bias_at(bias_series, sig["entry_time"], htf_interval_sec)
                if bias is not None:
                    if sig["direction"] == "LONG" and bias == "DOWN":
                        filter_reason = "htf_trend"
                    elif sig["direction"] == "SHORT" and bias == "UP":
                        filter_reason = "htf_trend"
        if filter_reason is not None:
            with _mirror_filtered_signal_cooldowns_lock:
                if _mirror_filtered_signal_cooldowns.get(symbol) == sig["entry_time"]:
                    return
                _mirror_filtered_signal_cooldowns[symbol] = sig["entry_time"]
            filtered_record = {
                "symbol": symbol, "direction": sig["direction"],
                "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"], "rr": sig.get("rr"),
                "pattern": sig.get("pattern"), "level_price": sig.get("level_price"),
                "level_type": sig.get("level_type"), "time": sig["entry_time"],
                "bars_since_break": sig.get("bars_since_break"), "filter_reason": filter_reason,
                "detected_at": time.time(), "status": "OPEN", "result": None,
                "exit_price": None, "exit_time": None, "app_version": APP_VERSION,
                "mfe_r": 0.0, "mae_r": 0.0, "mfe_price": None, "mae_price": None,
                "mfe_r_at_close": None, "mae_r_at_close": None, "timeout_pnl_r": None,
            }
            with state_lock:
                STATE["mirror_filtered_signals"].appendleft(filtered_record)
            return
        with _mirror_signal_cooldowns_lock:
            if _mirror_signal_cooldowns.get(symbol) == sig["entry_time"]:
                return
            _mirror_signal_cooldowns[symbol] = sig["entry_time"]
        # v0.99.144 — BUG FOUND (per direct user report: 3 identical
        # ADA_USDT LONG "пинцет" rows back to back): same exact bug
        # class MSNR was already fixed for (see that function's own
        # comment above this same check — "TIA_USDT rows reported
        # live"), never carried over here. _mirror_signal_cooldowns is
        # a plain in-memory dict, reset to empty on every restart, while
        # STATE["mirror_signals"] itself (the actual persisted record
        # of what already fired) survives the restart intact. If the
        # same pattern is still the most recent qualifying signal right
        # after a restart, the freshly-empty cooldown has no record of
        # having already fired it, and it fires again — a genuine
        # duplicate OPEN record for a symbol that already has one.
        # has_open_signal_any_module() below doesn't catch this either:
        # it deliberately EXCLUDES mirror_signals from its own check
        # (each module is expected to check its own list itself — this
        # is only the cross-module veto), and Mirror never had that
        # self-check. Checking STATE directly (persisted) instead of
        # only the fragile in-memory cooldown closes the gap regardless
        # of why the time-based cooldown alone failed to catch it.
        with state_lock:
            if any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in STATE["mirror_signals"]):
                return
        if has_open_signal_any_module(symbol, exclude="mirror_signals"):
            return
        record = {
            "symbol": symbol, "direction": sig["direction"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"], "rr": sig.get("rr"),
            "pattern": sig.get("pattern"), "level_price": sig.get("level_price"),
            "level_type": sig.get("level_type"), "time": sig["entry_time"],
            "bars_since_break": sig.get("bars_since_break"),
            "detected_at": time.time(), "status": "OPEN", "result": None,
            "exit_price": None, "exit_time": None, "app_version": APP_VERSION,
            "mfe_r": 0.0, "mae_r": 0.0, "mfe_price": None, "mae_price": None,
            "mfe_r_at_close": None, "mae_r_at_close": None, "timeout_pnl_r": None,
        }
        with state_lock:
            STATE["mirror_signals"].appendleft(record)
        if AUTOTRADE_ENABLED_MIRROR:
            autotrade_result = execute_autotrade("mirror", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"])
            sim_execute_trade("mirror", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"],
                               AUTOTRADE_LEVERAGE_MIRROR, record)
            # v0.99.134 — same cooldown-release-on-ERROR fix as LSW's own
            # (see that call site's own comment for the full incident):
            # a bare network ERROR shouldn't permanently burn this
            # level's one-and-only signal.
            if autotrade_result and autotrade_result.get("status") == "ERROR":
                with _mirror_signal_cooldowns_lock:
                    if _mirror_signal_cooldowns.get(symbol) == sig["entry_time"]:
                        del _mirror_signal_cooldowns[symbol]
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        pattern_labels = {"inside_bar": "внутренний бар", "tweezers": "пинцет",
                           "rails": "рельсы", "engulfing_doji": "поглощение на дожи"}
        send_telegram(
            f"{arrow} {symbol} (рождение зеркалки \u2014 {pattern_labels.get(sig['pattern'], sig['pattern'])})\n"
            f"entry: {sig['entry']:.6g}\n"
            f"SL: {sig['sl']:.6g}  TP: {sig['tp']:.6g}",
            category="mirror",
        )
    except Exception as e:
        log_error(f"mirror_live {symbol}: {e}")


def _mirror_track_signal_outcomes(signal_key):
    """v0.99.114 — the shared MFE/MAE/WIN/LOSS/TIMEOUT tracking body,
    extracted from update_mirror_signal_outcomes() so the EXACT same
    logic runs for both STATE["mirror_signals"] (real, fired signals)
    and STATE["mirror_filtered_signals"] (signals the SL-width/direction
    filters blocked — see mirror_scan_symbol_live()'s own comment for
    why these are tracked at all). The only difference between the two
    pools is whether execute_autotrade()/sim_execute_trade()/Telegram
    fired at creation time — how each signal's own eventual outcome
    gets measured afterward is identical either way, so this one body
    serves both rather than duplicating it."""
    now = time.time()
    with state_lock:
        open_signals = [s for s in STATE[signal_key] if s["status"] == "OPEN"]
    all_candles = fetch_candles_concurrent([(s["symbol"], MIRROR_INTERVAL, 300) for s in open_signals])
    mirror_interval_sec = INTERVAL_SECONDS.get(MIRROR_INTERVAL, 3600)
    for sig, candles in zip(open_signals, all_candles):
        try:
            if candles is None:
                continue
            candles = [c for c in candles if c["time"] + mirror_interval_sec <= now]
            future = [c for c in candles if c["time"] > sig["time"]]
            direction = sig["direction"]
            entry = sig["entry"]
            risk = abs(entry - sig["sl"]) or 1e-9
            result = None
            exit_price = None
            exit_time = None
            bars_seen = 0
            for c in future:
                bars_seen += 1
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
                if direction == "LONG":
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
                if bars_seen >= MIRROR_MAX_WAIT_BARS:
                    # v0.99.99 — timed out without touching TP/SL this
                    # whole window: close on THIS bar's own close price
                    # (a real, honest number, not None) so the sign of
                    # the outcome is visible, not just an ambiguous
                    # "TIMEOUT" label with no P&L attached to it.
                    result = "TIMEOUT"
                    exit_price = c["close"]
                    exit_time = c["time"]
                    break
            with state_lock:
                if result:
                    sig["status"] = "CLOSED"
                    sig["result"] = result
                    sig["exit_price"] = exit_price
                    sig["exit_time"] = exit_time
                    sig["mfe_r_at_close"] = sig["mfe_r"]
                    sig["mae_r_at_close"] = sig["mae_r"]
                    if result == "TIMEOUT" and exit_price is not None:
                        pnl_r = (exit_price - entry) / risk if direction == "LONG" else (entry - exit_price) / risk
                        sig["timeout_pnl_r"] = round(pnl_r, 3)
        except Exception as e:
            log_error(f"mirror_outcome {sig['symbol']}: {e}")


def update_mirror_signal_outcomes():
    """Same MFE/MAE-tracking shape as update_scalp_signal_outcomes().
    v0.99.99, per direct user follow-up ("тайм аут тоже добавь но надо
    знать как закрылась сделка по таймауту в плюс или минус"): adds the
    TIMEOUT-closing branch after all, reversing v0.99.98's own decision
    to leave MIRROR without one (that version investigated the same
    request from an external code review and declined it specifically
    because every other module's live tracker had TIMEOUT deliberately
    REMOVED — flagged the conflict, and this direct follow-up is the
    user's explicit choice to diverge MIRROR from that convention on
    purpose, not an oversight being corrected). Closes with a REAL
    exit_price (the last known candle's own close, not None) so a
    timed-out trade's own plus/minus outcome is actually visible — the
    same profit/loss math WIN/LOSS already use (exit_price vs entry,
    direction-aware), just measured at a price that isn't the TP/SL
    level itself. Also stores timeout_pnl_r — the signed R-multiple at
    that exact moment — so the frontend can color/label it directly
    without re-deriving direction logic from a raw price comparison.
    Uses the SAME MIRROR_MAX_WAIT_BARS cutoff mirror_track_outcome()'s
    own backtest-side timeout already uses (now a shared constant, was
    a hardcoded 200 in that function alone) for genuine backtest/live
    parity in how long a signal gets before timing out.
    v0.99.114 — now also tracks STATE["mirror_filtered_signals"] (the
    filter-blocked pool) through _mirror_track_signal_outcomes(), the
    exact same logic extracted into its own function so both pools are
    tracked identically."""
    _mirror_track_signal_outcomes("mirror_signals")
    _mirror_track_signal_outcomes("mirror_filtered_signals")


def compute_mirror_filtered_signal_stats():
    """v0.99.114 — aggregate WIN/LOSS stats for STATE["mirror_filtered_
    signals"] (the pool the SL-width/direction filters blocked from
    ever firing), same basic n/wins/losses/win_rate shape as compute_
    mirror_signal_stats(), for direct comparison against the real,
    filter-approved signals' own winrate — see mirror_scan_symbol_
    live()'s own comment for the full reasoning behind tracking this
    pool at all. by_reason splits by WHICH filter blocked the signal
    (sl_width vs direction), since a filter that's net harmful might
    only be so for one of the two reasons, not both."""
    with state_lock:
        signals = list(STATE["mirror_filtered_signals"])
    closed = [s for s in signals if s["status"] == "CLOSED" and s["result"] in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = len(closed) - wins
    open_n = sum(1 for s in signals if s["status"] == "OPEN")
    total_closed = len(closed)
    winrate = round(wins / total_closed * 100, 1) if total_closed else None
    by_reason = {}
    for reason in ("sl_width", "direction"):
        r_closed = [s for s in closed if s.get("filter_reason") == reason]
        r_wins = sum(1 for s in r_closed if s["result"] == "WIN")
        by_reason[reason] = {
            "n": len(r_closed), "wins": r_wins, "losses": len(r_closed) - r_wins,
            "win_rate": round(r_wins / len(r_closed) * 100, 1) if r_closed else None,
        }
    return {"n": total_closed, "wins": wins, "losses": losses, "open": open_n,
            "win_rate": winrate, "by_reason": by_reason}


def compute_mirror_signal_stats():
    with state_lock:
        signals = list(STATE["mirror_signals"])
    closed = [s for s in signals if s["status"] == "CLOSED" and s["result"] in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = sum(1 for s in closed if s["result"] == "LOSS")
    open_n = sum(1 for s in signals if s["status"] == "OPEN")
    total_closed = len(closed)
    winrate = round(wins / total_closed * 100, 1) if total_closed else None
    # per-pattern breakdown — which of the 4 confirmation patterns is
    # actually pulling its weight, same motivation as Volume's own
    # per-reason (bounce/breakout) stats.
    by_pattern = {}
    for p in ("inside_bar", "tweezers", "rails", "engulfing_doji"):
        p_closed = [s for s in closed if s.get("pattern") == p]
        p_wins = sum(1 for s in p_closed if s["result"] == "WIN")
        by_pattern[p] = {
            "n": len(p_closed), "wins": p_wins, "losses": len(p_closed) - p_wins,
            "winrate": round(p_wins / len(p_closed) * 100, 1) if p_closed else None,
        }
    return {"total": len(signals), "wins": wins, "losses": losses,
            "open": open_n, "winrate": winrate, "by_pattern": by_pattern}


def mirror_backtest_loop():
    while True:
        try:
            if not MIRROR_ENABLED:
                time.sleep(60)
                continue
            t0 = time.time()
            universe = mirror_build_universe()
            results_by_symbol = {}
            summary_by_symbol = {}
            overrides_by_symbol = {}
            tuned_tolerances = {}
            live_universe = []

            def _backtest_one(s):
                # v0.99.130 — autotune (if enabled) BEFORE the real
                # backtest, so the symbol's own reported results/summary
                # already reflect whichever tolerances actually got used
                # for it, not the plain defaults followed by a separate,
                # inconsistent "what-if" run.
                tuned = mirror_autotune_tolerances(s) if MIRROR_AUTOTUNE_TOLERANCE_ENABLED else None
                if tuned:
                    results, meta = mirror_backtest_symbol(
                        s, touch_tolerance_pct=tuned["touch_tolerance_pct"],
                        pattern_tolerance_pct=tuned["pattern_tolerance_pct"])
                else:
                    results, meta = mirror_backtest_symbol(s)
                return results, meta, tuned

            with ThreadPoolExecutor(max_workers=min(WORKERS, len(universe) or 1)) as ex:
                futs = {ex.submit(_backtest_one, s): s for s in universe}
                for fut in as_completed(futs):
                    symbol = futs[fut]
                    try:
                        results, meta, tuned = fut.result()
                        results_by_symbol[symbol] = results
                        summary = mirror_summarize_backtest(results)
                        summary_by_symbol[symbol] = summary
                        overrides_by_symbol[symbol] = meta
                        if tuned:
                            tuned_tolerances[symbol] = tuned
                        # v0.99.92, per direct user request ("В живых
                        # сигналах использовать только бэктестовые
                        # монеты с винрейтом более 35%"): gated on the
                        # POST-filter winrate (summary, from the
                        # already-SL-filtered results) — the live
                        # scanner should trust a symbol only to the
                        # same extent its own backtest, filters
                        # included, actually earned that trust.
                        # v0.99.98, per external code review batch 1
                        # ("Мин. выборка на live-гейте"): winrate alone
                        # let a 2/2 or 3/3 symbol read as "100%" and
                        # qualify exactly like a genuinely-tested 40+
                        # trade symbol.
                        # v0.99.111, per direct user report ("у virtual
                        # n 15 всего, но она торгуется в топе"): the
                        # original fix above reused MIRROR_SYMBOL_SKIP_
                        # MIN_SAMPLE (a per-bucket significance bar
                        # meant for judging one SL-width/pattern/
                        # direction slice within a symbol's own data)
                        # as this whole-symbol floor too — 15 total
                        # trades is nowhere near enough to trust for
                        # live money regardless of winrate. Now uses
                        # the dedicated, higher MIRROR_LIVE_MIN_SAMPLE
                        # (see that constant's own comment for the full
                        # reasoning on why it's a separate bar).
                        closed_n = summary["wins"] + summary["losses"]
                        if (summary["win_rate"] is not None and summary["win_rate"] > MIRROR_LIVE_MIN_WINRATE
                                and closed_n >= MIRROR_LIVE_MIN_SAMPLE):
                            live_universe.append(symbol)
                    except Exception as e:
                        log_error(f"mirror_backtest {symbol}: {e}")
            with state_lock:
                STATE["mirror_backtest_results"] = results_by_symbol
                STATE["mirror_backtest_summary"] = summary_by_symbol
                STATE["mirror_symbol_overrides"] = overrides_by_symbol
                STATE["mirror_tuned_tolerances"] = tuned_tolerances
                STATE["mirror_live_universe"] = live_universe
                STATE["mirror_last_backtest_finished"] = time.time()
                STATE["mirror_last_backtest_duration"] = round(time.time() - t0, 1)
        except Exception as e:
            log_error(f"mirror_backtest_loop: {e}")
        time.sleep(max(300, MIRROR_REFRESH_SEC))


def mirror_live_loop():
    while True:
        try:
            if not MIRROR_ENABLED:
                time.sleep(60)
                continue
            # v0.99.93, per direct user follow-up ("бэктест быстро
            # проходит, так что лучше ждать, просто в сигналах живых
            # вижу сигнал не удовлетворяющие условию 35% винрейта"):
            # the v0.99.92 raw-universe fallback (before the first
            # backtest cycle completes) let unfiltered signals fire
            # live — exactly the kind of surprising gap MSNR's own
            # msnr_compute_live_universe() history already established
            # should be closed, not left as a "don't sit idle" trade-
            # off (v0.99.75-78 explicitly retired MSNR's equivalent
            # winrate-only fallback after a live report of the exact
            # same symptom: signals firing for symbols that never
            # earned it through the actual gate). Given the backtest
            # cycle itself is fast, there's no real cost to simply NOT
            # scanning for new signals until mirror_live_universe has
            # been populated at least once — update_mirror_signal_
            # outcomes() still runs regardless, so already-open trades
            # keep getting tracked even while new-signal scanning waits.
            with state_lock:
                live_universe = list(STATE.get("mirror_live_universe", []))
            if live_universe:
                with ThreadPoolExecutor(max_workers=min(WORKERS, len(live_universe))) as ex:
                    list(ex.map(mirror_scan_symbol_live, live_universe))
            update_mirror_signal_outcomes()
        except Exception as e:
            log_error(f"mirror_live_loop: {e}")
        # v0.99.152 — sync to candle close (same fix as lsw_live_loop)
        interval_sec = INTERVAL_SECONDS.get(MIRROR_INTERVAL, 3600)
        now = time.time()
        sleep_sec = (interval_sec - now % interval_sec) + 3
        time.sleep(sleep_sec)


# ============================================================================
# END MIRROR
# ============================================================================


# ============================================================================
# LSW ("Liquidity Sweep") — equal-highs/equal-lows liquidity-grab
# reversal: >=2 swing highs (or lows) clustering within LSW_EQUAL_
# TOLERANCE_PCT of each other are treated as one resting-liquidity level
# (the "equal highs/lows" stop cluster this style targets). A signal
# fires when a later candle's WICK pokes beyond that level but its CLOSE
# comes back inside it — a sweep, distinct from a genuine breakout (which
# closes through) — same "wick beyond, close back" definition used by
# every public SMC implementation reviewed before building this (see
# rafalsza/joshyattridge's smartmoneyconcepts package's own smc.liquidity()
# docstring). Direction is the reversal AWAY from the swept side: sweeping
# equal highs implies SHORT, sweeping equal lows implies LONG. Stop-loss
# sits just beyond the sweep candle's own wick extreme (LSW_SL_BUFFER_PCT);
# take-profit is a fixed RR off that risk (LSW_RR) — same "mechanical
# pipeline needs a fixed target even though real discretionary SMC traders
# often don't use one" reasoning as MIRROR_RR's own docstring.
# Deliberately simpler than MIRROR — no SL-width/pattern/direction filter
# chain yet (MIRROR only grew that after real backtest data justified it);
# this ships with just detection + backtest + live signals, same scope
# MIRROR itself started at.
# Shipped paper-only in v0.99.119; v0.99.120 wired real autotrade in (see
# AUTOTRADE_ENABLED_LSW's own comment at the top of this file).
# ============================================================================
def lsw_compute_ema(values, period):
    """Standard EMA, seeded with an SMA of the first `period` values —
    same seeding convention compute_rsi() and every other indicator in
    this file already use. Returns a list the same length as `values`,
    with None for indices before the EMA is defined."""
    n = len(values)
    if n < period:
        return [None] * n
    ema = [None] * (period - 1)
    sma = sum(values[:period]) / period
    ema.append(sma)
    k = 2.0 / (period + 1)
    prev = sma
    for v in values[period:]:
        prev = v * k + prev * (1 - k)
        ema.append(prev)
    return ema


def lsw_htf_bias_series(htf_candles, period=None, buffer_pct=None):
    """Turns a higher-timeframe candle list into a (time, bias) series,
    oldest first — bias is "UP" if that HTF bar's close cleared its own
    EMA by buffer_pct, "DOWN" if it sat that far below, else "NEUTRAL".
    `time` is each bar's own OPEN time, same convention every candle
    dict in this file already uses — lsw_htf_bias_at() is what accounts
    for a bar not actually being CLOSED (and therefore not a safe trend
    read) until its own open time + the HTF interval has passed."""
    period = period if period is not None else LSW_HTF_EMA_PERIOD
    buffer_pct = buffer_pct if buffer_pct is not None else LSW_HTF_TREND_BUFFER_PCT
    closes = [c["close"] for c in htf_candles]
    ema = lsw_compute_ema(closes, period)
    series = []
    for c, e in zip(htf_candles, ema):
        if e is None or e == 0:
            series.append((c["time"], None))
            continue
        dev_pct = (c["close"] - e) / e * 100.0
        if dev_pct > buffer_pct:
            bias = "UP"
        elif dev_pct < -buffer_pct:
            bias = "DOWN"
        else:
            bias = "NEUTRAL"
        series.append((c["time"], bias))
    return series


def lsw_htf_bias_at(bias_series, t, htf_interval_sec):
    """The bias of the most recent HTF bar that had ALREADY CLOSED by
    LTF time `t` — no lookahead: a still-forming HTF bar's own close
    isn't known yet at `t`, so it's excluded (bar_time + interval must
    be <= t). Returns None if no HTF bar had closed yet at all."""
    result = None
    for bar_time, bias in bias_series:
        if bar_time + htf_interval_sec <= t:
            result = bias
        else:
            break
    return result


def lsw_filter_signals_by_htf_trend(signals, bias_series, htf_interval_sec):
    """Rule #1 of the reference ICT "AMD + FVG" setup ("только по
    тренду, дневка вверх и часовик восходящий моментум"): a LONG
    (sweep of equal lows) only survives if the HTF bias at that
    signal's own entry_time is UP or NEUTRAL; a SHORT only survives if
    it's DOWN or NEUTRAL. A signal whose HTF bar hasn't closed yet
    (bias is None) is dropped too — no basis to judge trend alignment
    at all, and this is deliberately a conservative filter, not a
    permissive one."""
    kept = []
    for sig in signals:
        bias = lsw_htf_bias_at(bias_series, sig["entry_time"], htf_interval_sec)
        if bias is None:
            continue
        if sig["direction"] == "LONG" and bias == "DOWN":
            continue
        if sig["direction"] == "SHORT" and bias == "UP":
            continue
        kept.append(sig)
    return kept


def lsw_find_pivots(candles, left=None, right=None):
    """Same fractal swing-high/low pivot detector as mirror_find_pivots()
    — kept as its own copy (not a shared call) so LSW's own pivot_left/
    pivot_right can diverge from MIRROR's without any cross-module
    coupling, same "each module owns its own copy" pattern FT5/MSNR/
    MIRROR's own pivot-style detectors already use independently."""
    left = left if left is not None else LSW_PIVOT_LEFT
    right = right if right is not None else LSW_PIVOT_RIGHT
    n = len(candles)
    pivots = []
    for i in range(left, n - right):
        window_highs = [candles[j]["high"] for j in range(i - left, i + right + 1)]
        window_lows = [candles[j]["low"] for j in range(i - left, i + right + 1)]
        if candles[i]["high"] == max(window_highs) and window_highs.count(candles[i]["high"]) == 1:
            pivots.append({"type": "high", "price": candles[i]["high"], "idx": i, "confirm_idx": i + right})
        if candles[i]["low"] == min(window_lows) and window_lows.count(candles[i]["low"]) == 1:
            pivots.append({"type": "low", "price": candles[i]["low"], "idx": i, "confirm_idx": i + right})
    return pivots


def lsw_filter_signals_by_structural_cap(signals, candles, lookback=None, pivot_left=None, pivot_right=None):
    """Rule #4 of the reference "AMD + FVG" note ("торгуем не выше
    структурного максимума"): a LONG only survives if its own entry
    price sits BELOW the nearest significant structural high confirmed
    within `lookback` bars before it — i.e. there's still real room to
    run before hitting the last major resistance, not already chasing
    price past it. A SHORT mirrors this: entry must sit ABOVE the
    nearest significant structural low. Uses lsw_find_pivots() with a
    deliberately WIDER left/right (LSW_STRUCTURAL_CAP_PIVOT_LEFT/RIGHT,
    10/10 by default vs the 3/3 used for equal-highs/lows grouping) —
    a "structural" swing is a bigger, more significant move than the
    small pivots the sweep detector itself watches. A signal with no
    qualifying structural pivot in its own lookback window is KEPT
    (nothing to cap against, not a reason to block the trade)."""
    lookback = lookback if lookback is not None else LSW_STRUCTURAL_CAP_LOOKBACK
    pivot_left = pivot_left if pivot_left is not None else LSW_STRUCTURAL_CAP_PIVOT_LEFT
    pivot_right = pivot_right if pivot_right is not None else LSW_STRUCTURAL_CAP_PIVOT_RIGHT
    kept = []
    for sig in signals:
        idx = sig["entry_idx"]
        window_start = max(0, idx - lookback)
        window = candles[window_start:idx + 1]
        if len(window) < pivot_left + pivot_right + 1:
            kept.append(sig)
            continue
        pivots = lsw_find_pivots(window, pivot_left, pivot_right)
        if sig["direction"] == "LONG":
            highs = [p["price"] for p in pivots if p["type"] == "high"]
            if highs and sig["entry"] >= max(highs):
                continue  # already at/above the last major structural high — capped out
        else:
            lows = [p["price"] for p in pivots if p["type"] == "low"]
            if lows and sig["entry"] <= min(lows):
                continue  # already at/below the last major structural low — capped out
        kept.append(sig)
    return kept


def lsw_filter_signals_by_volume(signals, candles, lookback=None, mult=None):
    """v0.99.139 — a genuine liquidity sweep (a real stop cascade
    getting absorbed) should show elevated volume on the sweep candle
    itself relative to the bars right before it; a low-volume wick that
    merely pokes past a level without real participation behind it is
    a weaker signal. Keeps a signal only if its own sweep candle's
    volume is at least `mult` times the average volume of the
    `lookback` bars immediately before it (the sweep candle itself is
    excluded from that average — comparing it against itself would be
    circular). A signal with fewer than half of `lookback` preceding
    bars available, or a zero average (no real trading history to
    compare against), is KEPT — same "nothing to judge against isn't a
    reason to block the trade" convention lsw_filter_signals_by_
    structural_cap() already uses."""
    lookback = lookback if lookback is not None else LSW_VOLUME_FILTER_LOOKBACK
    mult = mult if mult is not None else LSW_VOLUME_FILTER_MULT
    kept = []
    for sig in signals:
        idx = sig["entry_idx"]
        window_start = max(0, idx - lookback)
        window = candles[window_start:idx]  # preceding bars only — NOT including the sweep candle itself
        if len(window) < max(3, lookback // 2):
            kept.append(sig)
            continue
        avg_vol = sum(c["volume"] for c in window) / len(window)
        sweep_vol = candles[idx]["volume"]
        if avg_vol <= 0 or sweep_vol >= mult * avg_vol:
            kept.append(sig)
        # else dropped — the sweep candle didn't show elevated volume, less likely a genuine stop-cascade/absorption event
    return kept


def lsw_filter_signals_by_fvg(signals, candles):
    """v0.99.140 — "always layer fair value gaps" / "wait for a
    pullback into the displacement candle's fair value gap" — the most
    commonly repeated confluence add-on for a bare liquidity sweep
    across independent sources searched. A fair value gap (imbalance)
    is a real, tradeable sign that the reversal candle itself displaced
    price hard enough to leave a gap behind, not just wiggled through
    the level. Deliberately checks BACKWARD only (the sweep candle
    itself vs. 2 bars before it), never forward — the standard 3-candle
    FVG definition only ever needs bars that have ALREADY closed by the
    time the sweep candle itself closes, so this stays exactly as
    usable live (at the moment a signal fires) as it is in backtest;
    checking for a gap using bars AFTER the sweep would need candles
    that don't exist yet at signal time. Bullish FVG (supports LONG):
    the bar 2 before the sweep candle's own high sits below the sweep
    candle's own low. Bearish FVG (supports SHORT): mirrors it. A
    signal without 2 prior bars is KEPT (nothing to judge, same
    convention as this module's other filters)."""
    kept = []
    for sig in signals:
        idx = sig["entry_idx"]
        if idx < 2:
            kept.append(sig)
            continue
        c_before, c_now = candles[idx - 2], candles[idx]
        if sig["direction"] == "LONG" and c_before["high"] < c_now["low"]:
            kept.append(sig)
        elif sig["direction"] == "SHORT" and c_before["low"] > c_now["high"]:
            kept.append(sig)
        # else dropped — no imbalance left behind by the sweep/reversal candle itself
    return kept


def lsw_filter_signals_by_session(signals, start_hour=None, end_hour=None):
    """v0.99.140 — "skip sweeps in dead sessions; focus high-probability
    ones with volatility". Keeps a signal only if its own entry_time
    (UTC hour) falls inside [start_hour, end_hour) — wraps past
    midnight correctly if start_hour > end_hour (e.g. a session that
    runs 22:00-04:00 UTC). Defaults (07:00-21:00 UTC) approximate the
    European+US session overlap, crypto's own usual higher-volume
    window — but this genuinely varies per symbol, which is exactly why
    it's backtestable/toggleable here rather than hardcoded assumption."""
    start_hour = start_hour if start_hour is not None else LSW_SESSION_START_HOUR_UTC
    end_hour = end_hour if end_hour is not None else LSW_SESSION_END_HOUR_UTC
    kept = []
    for sig in signals:
        hour = time.gmtime(sig["entry_time"]).tm_hour
        in_session = (start_hour <= hour < end_hour) if start_hour <= end_hour else (hour >= start_hour or hour < end_hour)
        if in_session:
            kept.append(sig)
    return kept


def lsw_filter_signals_by_min_touches(signals, min_touches=None):
    """v0.99.140 — "the more touches, the higher the chance of a
    sweep": the base detector already requires >=2 touches before
    calling something an "equal highs/lows" level at all (see lsw_
    detect_signals()'s own docstring) — this raises that bar further
    for symbols where more touches turns out to matter more than the
    base minimum. A signal with no recorded level_touches at all is
    KEPT (shouldn't normally happen given the base detector's own
    floor, but nothing to judge isn't a reason to block)."""
    min_touches = min_touches if min_touches is not None else LSW_MIN_TOUCHES
    return [s for s in signals if (s.get("level_touches") or 0) >= min_touches or not s.get("level_touches")]


def lsw_filter_signals_by_candle_structure(signals, candles, wick_body_ratio=None, wick_range_min_pct=None):
    """v0.99.149 — a genuine liquidity sweep rejection shows a large
    directional wick (price poked through the level and snapped back
    hard) against a small body (it CLOSED back inside, far from its
    open). A large body means price actually committed to moving — more
    of a breakout or impulse than a rejection. Two checks combined:
    (1) the directional wick is at least `wick_body_ratio` times the
    body size — strict ratio alone can pass doji candles with a tiny
    wick and a tinier body, so:
    (2) the directional wick covers at least `wick_range_min_pct` of
    the candle's total high-low range, ensuring some real structural
    presence.
    "Directional wick" is defined relative to the signal's own
    direction: for a LONG (equal-lows sweep), the relevant wick is the
    LOWER wick (price poked below, snapped back up); for a SHORT
    (equal-highs sweep), it's the UPPER wick. A signal with no
    entry_idx or a candle that's genuinely a doji (zero range) is KEPT
    — nothing to judge isn't a reason to block, same convention as
    every other filter in this file."""
    wick_body_ratio = wick_body_ratio if wick_body_ratio is not None else LSW_CANDLE_WICK_BODY_RATIO
    wick_range_min_pct = wick_range_min_pct if wick_range_min_pct is not None else LSW_CANDLE_WICK_RANGE_MIN_PCT
    kept = []
    for sig in signals:
        idx = sig.get("entry_idx")
        if idx is None or idx >= len(candles):
            kept.append(sig)
            continue
        c = candles[idx]
        total_range = c["high"] - c["low"]
        if total_range <= 0:
            kept.append(sig)  # doji with zero range — nothing to judge
            continue
        body = abs(c["close"] - c["open"])
        if sig["direction"] == "LONG":
            wick = min(c["open"], c["close"]) - c["low"]  # lower wick
        else:
            wick = c["high"] - max(c["open"], c["close"])  # upper wick
        if wick <= 0:
            continue  # no directional wick at all — dropped
        # Check 1: wick vs body ratio
        if body > 0 and wick < wick_body_ratio * body:
            continue
        # Check 2: wick covers enough of the total candle range
        if wick / total_range < wick_range_min_pct:
            continue
        kept.append(sig)
    return kept


def lsw_scan_5m_confirmation(candles_ltf, from_time, direction, max_bars=None,
                              pivot_left=None, pivot_right=None, wick_ratio=None):
    """Rule #3 of the reference note ("модели входа (5минутка):
    инверсия / BOS (слом структуры) / поглощение"). Scans `candles_ltf`
    (expected to be LSW_ENTRY_CONFIRM_INTERVAL, i.e. 5m, candles)
    starting at the first bar at/after `from_time` (the 1h sweep
    candle's own close) for up to `max_bars`, looking for the FIRST of:
    - BOS: a 5m close breaks the most recent 5m swing point (high for
      LONG, low for SHORT) confirmed before the scan window started —
      a genuine slom structury in the trade's own direction.
    - Поглощение (absorption): a 5m candle whose rejection wick against
      the trade direction covers at least `wick_ratio` of its own
      range, closing in the favorable part of that range — a rejection
      candle.
    - Инверсия (inversion): a mini version of the same liquidity-sweep
      idea at 5m resolution — a bar wicks past the recent few bars'
      own extreme (against the trade direction) but closes back beyond
      it in the trade's favor.
    Whichever fires on the EARLIEST bar wins. Returns
    {"method", "confirm_time", "entry", "sl_ref"} or None if nothing
    confirmed within the window — in which case the signal is dropped
    entirely (no confirmation, no trade), per the reference note
    treating these as required entry TRIGGERS, not optional extras."""
    max_bars = max_bars if max_bars is not None else LSW_ENTRY_CONFIRM_MAX_BARS
    pivot_left = pivot_left if pivot_left is not None else LSW_ENTRY_CONFIRM_PIVOT_LEFT
    pivot_right = pivot_right if pivot_right is not None else LSW_ENTRY_CONFIRM_PIVOT_RIGHT
    wick_ratio = wick_ratio if wick_ratio is not None else LSW_ENTRY_CONFIRM_WICK_RATIO

    start_idx = None
    for i, c in enumerate(candles_ltf):
        if c["time"] >= from_time:
            start_idx = i
            break
    if start_idx is None:
        return None
    window_end = min(len(candles_ltf), start_idx + max_bars)

    ref_price = None
    if start_idx >= pivot_left + pivot_right + 1:
        pivots = lsw_find_pivots(candles_ltf[:start_idx + 1], pivot_left, pivot_right)
        ref_type = "high" if direction == "LONG" else "low"
        ref_pivots = [p["price"] for p in pivots if p["type"] == ref_type]
        if ref_pivots:
            ref_price = ref_pivots[-1]

    for i in range(start_idx, window_end):
        c = candles_ltf[i]
        rng = c["high"] - c["low"]
        if rng <= 0:
            continue
        # BOS — slom structury in the trade's own direction
        if ref_price is not None:
            if direction == "LONG" and c["close"] > ref_price:
                sl_ref = min(cc["low"] for cc in candles_ltf[max(start_idx, i - pivot_left - pivot_right):i + 1])
                return {"method": "BOS", "confirm_time": c["time"], "entry": c["close"], "sl_ref": sl_ref}
            if direction == "SHORT" and c["close"] < ref_price:
                sl_ref = max(cc["high"] for cc in candles_ltf[max(start_idx, i - pivot_left - pivot_right):i + 1])
                return {"method": "BOS", "confirm_time": c["time"], "entry": c["close"], "sl_ref": sl_ref}
        # Поглощение — a rejection candle
        body_low, body_high = min(c["open"], c["close"]), max(c["open"], c["close"])
        lower_wick = body_low - c["low"]
        upper_wick = c["high"] - body_high
        if direction == "LONG" and lower_wick >= wick_ratio * rng and c["close"] >= c["low"] + wick_ratio * rng:
            return {"method": "ABSORPTION", "confirm_time": c["time"], "entry": c["close"], "sl_ref": c["low"]}
        if direction == "SHORT" and upper_wick >= wick_ratio * rng and c["close"] <= c["high"] - wick_ratio * rng:
            return {"method": "ABSORPTION", "confirm_time": c["time"], "entry": c["close"], "sl_ref": c["high"]}
        # Инверсия — a mini sweep of the last few bars' own extreme
        if i > start_idx:
            recent = candles_ltf[max(i - 3, start_idx):i]
            if not recent:
                continue
            if direction == "LONG":
                prev_extreme = min(cc["low"] for cc in recent)
                if c["low"] < prev_extreme and c["close"] > prev_extreme:
                    return {"method": "INVERSION", "confirm_time": c["time"], "entry": c["close"], "sl_ref": c["low"]}
            else:
                prev_extreme = max(cc["high"] for cc in recent)
                if c["high"] > prev_extreme and c["close"] < prev_extreme:
                    return {"method": "INVERSION", "confirm_time": c["time"], "entry": c["close"], "sl_ref": c["high"]}
    return None


def lsw_apply_entry_confirmation(signals, candles_ltf, max_bars=None, pivot_left=None,
                                  pivot_right=None, wick_ratio=None, sl_buffer_pct=None):
    """Runs lsw_scan_5m_confirmation() for every signal and replaces
    its entry/sl/tp with the confirmed values (recomputing tp at the
    SAME rr the signal already had) — drops the signal entirely if
    nothing confirmed within the window. Outcome tracking still walks
    the ORIGINAL 1h candles from the signal's own entry_idx afterward
    (lsw_track_outcome() isn't 5m-aware) — a deliberate simplification
    since confirmation only ever happens within LSW_ENTRY_CONFIRM_
    MAX_BARS x 5m (1h by default) of the sweep candle's own close, so
    the 1h bar immediately after it already covers the confirmation
    window in almost every case."""
    max_bars = max_bars if max_bars is not None else LSW_ENTRY_CONFIRM_MAX_BARS
    sl_buffer_pct = sl_buffer_pct if sl_buffer_pct is not None else LSW_SL_BUFFER_PCT
    result = []
    for sig in signals:
        conf = lsw_scan_5m_confirmation(candles_ltf, sig["entry_time"], sig["direction"],
                                         max_bars, pivot_left, pivot_right, wick_ratio)
        if conf is None:
            continue
        entry = conf["entry"]
        if sig["direction"] == "LONG":
            sl = conf["sl_ref"] * (1 - sl_buffer_pct / 100.0)
        else:
            sl = conf["sl_ref"] * (1 + sl_buffer_pct / 100.0)
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        rr = sig.get("rr") or LSW_RR
        tp = entry + risk * rr if sig["direction"] == "LONG" else entry - risk * rr
        new_sig = dict(sig)
        new_sig.update({"entry": entry, "sl": sl, "tp": tp, "confirm_method": conf["method"],
                         "confirm_time": conf["confirm_time"]})
        result.append(new_sig)
    return result


def lsw_detect_signals(candles, pivot_left=None, pivot_right=None, equal_tolerance_pct=None,
                        sl_buffer_pct=None, rr=None, max_bars_to_sweep=None):
    """Single walk-forward pass over `candles` (oldest first), no
    lookahead — a pivot only becomes a watchable level at its own
    confirm_idx, same discipline as mirror_detect_signals().
    1. lsw_find_pivots() finds every confirmed swing high/low.
    2. Each newly-confirmed pivot either MERGES into an existing
       same-type level within equal_tolerance_pct of its price (bumping
       that level's touch count), or starts a new candidate level.
    3. A level only becomes "watched" for a sweep once it has >=2
       touches — a single isolated swing isn't "equal highs/lows,"
       there's no real resting-stop cluster there yet.
    4. On each subsequent bar, a watched level fires the moment the
       bar's own WICK pokes beyond it but the CLOSE comes back inside
       (bar["high"] > level for a high-side level with close back below
       it; bar["low"] < level for a low-side level with close back
       above it) — a genuine sweep, not a breakout (which closes
       through and is deliberately NOT treated as a signal here).
       Fires once, then stops being watched. A level not swept within
       max_bars_to_sweep bars of its last touch goes stale and is
       dropped, same "watched levels expire" convention MIRROR's own
       broken-level tracking already uses.
    Entry = the sweep candle's own close. Stop-loss = the sweep
    candle's own wick extreme + a small buffer. Take-profit = entry ±
    risk × rr. Returns a list of signal dicts (oldest first):
    {"direction", "entry", "sl", "tp", "rr", "level_price",
    "level_type", "level_touches", "entry_idx", "entry_time"}."""
    pivot_left = pivot_left if pivot_left is not None else LSW_PIVOT_LEFT
    pivot_right = pivot_right if pivot_right is not None else LSW_PIVOT_RIGHT
    equal_tolerance_pct = equal_tolerance_pct if equal_tolerance_pct is not None else LSW_EQUAL_TOLERANCE_PCT
    sl_buffer_pct = sl_buffer_pct if sl_buffer_pct is not None else LSW_SL_BUFFER_PCT
    rr = rr if rr is not None else LSW_RR
    max_bars_to_sweep = max_bars_to_sweep if max_bars_to_sweep is not None else LSW_MAX_BARS_TO_SWEEP

    pivots = lsw_find_pivots(candles, pivot_left, pivot_right)
    by_confirm_idx = {}
    for p in pivots:
        by_confirm_idx.setdefault(p["confirm_idx"], []).append(p)

    levels = {"high": [], "low": []}  # each: {price, count, last_idx}
    signals = []
    n = len(candles)

    for i in range(n):
        for p in by_confirm_idx.get(i, []):
            typ = p["type"]
            tol = p["price"] * equal_tolerance_pct / 100.0
            merged = False
            for lvl in levels[typ]:
                if abs(lvl["price"] - p["price"]) <= tol:
                    lvl["count"] += 1
                    lvl["last_idx"] = i
                    merged = True
                    break
            if not merged:
                levels[typ].append({"price": p["price"], "count": 1, "last_idx": i})

        c = candles[i]
        for typ in ("high", "low"):
            still = []
            for lvl in levels[typ]:
                if i - lvl["last_idx"] > max_bars_to_sweep:
                    continue  # gone stale, drop it silently
                if lvl["count"] < 2:
                    still.append(lvl)  # not yet an "equal" level — keep accumulating touches
                    continue
                price = lvl["price"]
                swept = (c["high"] > price and c["close"] < price) if typ == "high" \
                    else (c["low"] < price and c["close"] > price)
                if not swept:
                    still.append(lvl)
                    continue
                direction = "SHORT" if typ == "high" else "LONG"
                extreme = c["high"] if typ == "high" else c["low"]
                sl = extreme * (1 + sl_buffer_pct / 100.0) if typ == "high" else extreme * (1 - sl_buffer_pct / 100.0)
                entry = c["close"]
                risk = abs(entry - sl)
                if risk > 0:
                    tp = entry - risk * rr if direction == "SHORT" else entry + risk * rr
                    signals.append({
                        "direction": direction, "entry": entry, "sl": sl, "tp": tp, "rr": rr,
                        "level_price": price, "level_type": typ, "level_touches": lvl["count"],
                        "entry_idx": i, "entry_time": c["time"],
                    })
                # level fires once, then stops being watched — dropped either way (degenerate zero-risk case too)
            levels[typ] = still

    return signals


def lsw_track_outcome(candles, sig, max_wait_bars=LSW_MAX_WAIT_BARS):
    """Walks forward from sig['entry_idx']+1 looking for TP/SL touch —
    SL checked first on any bar covering both, same conservative
    convention mirror_track_outcome()/msnr_track_outcome() already use."""
    n = len(candles)
    for k in range(sig["entry_idx"] + 1, min(n, sig["entry_idx"] + 1 + max_wait_bars)):
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


def lsw_build_universe():
    """Liquid-symbol pool, same top-by-24h-volume source/shape as
    ft5_build_universe()/mirror_build_universe() — capped to
    LSW_UNIVERSE_SIZE. A liquidity sweep is a general price-action
    concept, not tied to one symbol, so this scans a broad universe
    like FT5/MIRROR/MSNR do."""
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
    return [s[0] for s in ranked[:LSW_UNIVERSE_SIZE]]


def lsw_backtest_symbol(symbol, days=LSW_BACKTEST_DAYS):
    """Fetches LSW_BACKTEST_DAYS of LSW_INTERVAL history, runs the
    detector + outcome tracker over the whole window. v0.99.121: when
    LSW_HTF_FILTER_ENABLED, also fetches LSW_HTF_INTERVAL history over
    the SAME window and runs lsw_filter_signals_by_htf_trend() before
    tracking outcomes, so the backtest numbers reflect the filter
    exactly as live trading would apply it. v0.99.122 adds two more,
    same "reflect exactly what live would do" principle: when LSW_
    STRUCTURAL_CAP_ENABLED, lsw_filter_signals_by_structural_cap() runs
    directly against the already-fetched LSW_INTERVAL candles (no extra
    fetch needed — it's a single-timeframe check); when LSW_ENTRY_
    CONFIRM_ENABLED, fetches LSW_ENTRY_CONFIRM_INTERVAL (5m) history
    over the same window and runs lsw_apply_entry_confirmation(), which
    replaces each surviving signal's own entry/sl/tp or drops it if no
    5m confirmation ever fired. v0.99.139 adds a 4th, lsw_filter_
    signals_by_volume() (LSW_VOLUME_FILTER_ENABLED) — same single-
    timeframe, no-extra-fetch shape as structural cap. v0.99.140 adds
    3 more of the SAME no-extra-fetch shape: lsw_filter_signals_by_fvg()
    (LSW_FVG_FILTER_ENABLED), lsw_filter_signals_by_session()
    (LSW_SESSION_FILTER_ENABLED), lsw_filter_signals_by_min_touches()
    (LSW_MIN_TOUCHES_ENABLED). Filter order for the ACTUAL result: HTF
    trend -> structural cap -> volume -> min touches -> FVG -> session
    -> 5m entry confirmation — cheapest/coarsest checks first, so the
    (comparatively expensive) 5m confirmation only ever runs on signals
    that already passed everything else.
    v0.99.136, per direct user request ("хочу чтобы в sweep индикаторе
    каждая из галочек настроек показывала в таблице что стало после
    этого фильтра чтобы была оценка необходимости, вдруг она сделала
    хуже"): ALSO computes, independently of which toggles are currently
    on, what each filter would do ALONE against the raw signal pool —
    not chained through the others, so each filter's own individual
    contribution is visible without interaction effects. v0.99.139,
    per direct follow-up ("убери из отображения в столбцах... добавим
    ещё один"): the HTF trend and structural cap solo checkpoints are
    no longer computed at all (their own toggles and detection code
    stay fully usable in the ACTUAL chain below — only the extra solo-
    checkpoint work for the no-longer-displayed columns was dropped).
    Returns (results, meta) — results is the raw trades list using
    whichever filters are ACTUALLY enabled right now (unchanged
    behavior, still what live-eligibility/ranking is computed from);
    meta = {"checkpoints": {"raw", "entry_confirm", "volume_filter",
    "fvg_filter", "session_filter", "min_touches_filter"}}, each a
    _mirror_checkpoint()-shaped {n, winrate, expectancy_r} dict
    (reusing that exact helper — LSW shares the same fixed-RR-per-trade
    shape MIRROR's own checkpoint math already assumes) or None where
    there wasn't enough history to judge that filter at all."""
    now = time.time()
    fetch_start = now - days * 86400
    candles = get_candles_range(symbol, LSW_INTERVAL, fetch_start, now)
    if len(candles) < LSW_PIVOT_LEFT + LSW_PIVOT_RIGHT + 20:
        return [], {"checkpoints": {"raw": None, "entry_confirm": None, "volume_filter": None,
                                     "fvg_filter": None, "session_filter": None, "min_touches_filter": None,
                                     "candle_structure": None}}
    raw_sigs = lsw_detect_signals(candles)

    htf_interval_sec = INTERVAL_SECONDS.get(LSW_HTF_INTERVAL, 14400)
    htf_fetch_start = fetch_start - LSW_HTF_EMA_PERIOD * htf_interval_sec
    htf_candles = get_candles_range(symbol, LSW_HTF_INTERVAL, htf_fetch_start, now)
    confirm_candles = get_candles_range(symbol, LSW_ENTRY_CONFIRM_INTERVAL, fetch_start, now)

    def _track_all(sigs_list):
        out = []
        for sig in sigs_list:
            result, exit_time = lsw_track_outcome(candles, sig)
            out.append({
                "time": sig["entry_time"], "direction": sig["direction"],
                "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"], "rr": sig.get("rr"),
                "level_price": sig.get("level_price"), "level_type": sig.get("level_type"),
                "level_touches": sig.get("level_touches"), "confirm_method": sig.get("confirm_method"),
                "result": result, "exit_time": exit_time,
            })
        return out

    checkpoints = {"raw": _mirror_checkpoint(_track_all(raw_sigs), rr=LSW_RR)}

    if confirm_candles:
        confirm_solo_sigs = lsw_apply_entry_confirmation(raw_sigs, confirm_candles)
        checkpoints["entry_confirm"] = _mirror_checkpoint(_track_all(confirm_solo_sigs), rr=LSW_RR)
    else:
        checkpoints["entry_confirm"] = None

    volume_solo_sigs = lsw_filter_signals_by_volume(raw_sigs, candles)
    checkpoints["volume_filter"] = _mirror_checkpoint(_track_all(volume_solo_sigs), rr=LSW_RR)

    fvg_solo_sigs = lsw_filter_signals_by_fvg(raw_sigs, candles)
    checkpoints["fvg_filter"] = _mirror_checkpoint(_track_all(fvg_solo_sigs), rr=LSW_RR)

    session_solo_sigs = lsw_filter_signals_by_session(raw_sigs)
    checkpoints["session_filter"] = _mirror_checkpoint(_track_all(session_solo_sigs), rr=LSW_RR)

    touches_solo_sigs = lsw_filter_signals_by_min_touches(raw_sigs)
    checkpoints["min_touches_filter"] = _mirror_checkpoint(_track_all(touches_solo_sigs), rr=LSW_RR)

    structure_solo_sigs = lsw_filter_signals_by_candle_structure(raw_sigs, candles)
    checkpoints["candle_structure"] = _mirror_checkpoint(_track_all(structure_solo_sigs), rr=LSW_RR)

    # The ACTUAL result, using whichever filters are really toggled on right now — unchanged from before, chained in the same order.
    sigs = raw_sigs
    if LSW_HTF_FILTER_ENABLED and sigs:
        if len(htf_candles) >= LSW_HTF_EMA_PERIOD:
            bias_series = lsw_htf_bias_series(htf_candles)
            sigs = lsw_filter_signals_by_htf_trend(sigs, bias_series, htf_interval_sec)
        else:
            sigs = []  # not enough HTF history to judge trend at all — conservative: no signals rather than unfiltered ones
    if LSW_STRUCTURAL_CAP_ENABLED and sigs:
        sigs = lsw_filter_signals_by_structural_cap(sigs, candles)
    if LSW_VOLUME_FILTER_ENABLED and sigs:
        sigs = lsw_filter_signals_by_volume(sigs, candles)
    if LSW_MIN_TOUCHES_ENABLED and sigs:
        sigs = lsw_filter_signals_by_min_touches(sigs)
    if LSW_FVG_FILTER_ENABLED and sigs:
        sigs = lsw_filter_signals_by_fvg(sigs, candles)
    if LSW_SESSION_FILTER_ENABLED and sigs:
        sigs = lsw_filter_signals_by_session(sigs)
    if LSW_CANDLE_STRUCTURE_FILTER_ENABLED and sigs:
        sigs = lsw_filter_signals_by_candle_structure(sigs, candles)
    if LSW_ENTRY_CONFIRM_ENABLED and sigs:
        if confirm_candles:
            sigs = lsw_apply_entry_confirmation(sigs, confirm_candles)
        else:
            sigs = []  # no 5m history at all to confirm against
    results = _track_all(sigs)
    return results, {"checkpoints": checkpoints}

def lsw_summarize_backtest(results):
    total = len(results)
    if not total:
        return {"n": 0, "win_rate": None, "wins": 0, "losses": 0, "timeouts": 0,
                "by_direction": {"LONG": {"n": 0, "wins": 0, "losses": 0, "win_rate": None},
                                  "SHORT": {"n": 0, "wins": 0, "losses": 0, "win_rate": None}}}
    wins = sum(1 for r in results if r["result"] == "WIN")
    losses = sum(1 for r in results if r["result"] == "LOSS")
    timeouts = sum(1 for r in results if r["result"] == "TIMEOUT")
    closed = wins + losses
    win_rate = round(wins / closed * 100, 1) if closed else None
    by_direction = {}
    for d in ("LONG", "SHORT"):
        d_results = [r for r in results if r.get("direction") == d and r["result"] in ("WIN", "LOSS")]
        d_wins = sum(1 for r in d_results if r["result"] == "WIN")
        by_direction[d] = {
            "n": len(d_results), "wins": d_wins, "losses": len(d_results) - d_wins,
            "win_rate": round(d_wins / len(d_results) * 100, 1) if d_results else None,
        }
    return {"n": total, "win_rate": win_rate, "wins": wins, "losses": losses, "timeouts": timeouts,
            "by_direction": by_direction}


_lsw_signal_cooldowns = {}  # symbol -> last-signaled entry_time
_lsw_signal_cooldowns_lock = threading.Lock()


def lsw_scan_symbol_live(symbol):
    """Live counterpart to lsw_backtest_symbol() — fetches recent
    history, runs the SAME detector, and records a signal only if the
    LAST candle produced a brand-new one not already seen for this
    symbol.
    v0.99.120, per direct user request ("надо живые сигналы сделать и
    авто торговлю как и везде, тоже с риском 2%"): now fires real
    autotrade the exact same way every other module does — execute_
    autotrade("lsw", ...) when AUTOTRADE_ENABLED_LSW is on (same
    automatic risk-based leverage/sizing every module shares, 2% of
    confirmed equity per trade via AUTOTRADE_RISK_PCT_OF_BALANCE, no
    override here) plus sim_execute_trade() for the separate paper-
    balance simulator, plus a Telegram alert. v0.99.119 shipped this
    paper-only; that mode is what happens automatically whenever
    AUTOTRADE_ENABLED_LSW itself is off (still records to STATE[
    "lsw_signals"] and tracks WIN/LOSS/TIMEOUT either way — the toggle
    only controls whether a real/simulated order actually fires)."""
    if not LSW_ENABLED:
        return
    try:
        candles = get_candles(symbol, interval=LSW_INTERVAL, limit=LSW_LOOKBACK)
        interval_sec = INTERVAL_SECONDS.get(LSW_INTERVAL, 3600)
        now = time.time()
        candles = [c for c in candles if c["time"] + interval_sec <= now]  # drop still-forming candle
        if len(candles) < LSW_PIVOT_LEFT + LSW_PIVOT_RIGHT + 20:
            return
        sigs = lsw_detect_signals(candles)
        if not sigs:
            return
        if LSW_HTF_FILTER_ENABLED:
            htf_interval_sec = INTERVAL_SECONDS.get(LSW_HTF_INTERVAL, 14400)
            htf_candles = get_candles(symbol, interval=LSW_HTF_INTERVAL,
                                       limit=LSW_HTF_EMA_PERIOD + 10)
            htf_now = time.time()
            htf_candles = [c for c in htf_candles if c["time"] + htf_interval_sec <= htf_now]
            if len(htf_candles) < LSW_HTF_EMA_PERIOD:
                return  # not enough HTF history to judge trend — conservative: skip rather than fire unfiltered
            bias_series = lsw_htf_bias_series(htf_candles)
            sigs = lsw_filter_signals_by_htf_trend(sigs, bias_series, htf_interval_sec)
            if not sigs:
                return
        if LSW_STRUCTURAL_CAP_ENABLED:
            sigs = lsw_filter_signals_by_structural_cap(sigs, candles)
            if not sigs:
                return
        if LSW_VOLUME_FILTER_ENABLED:
            sigs = lsw_filter_signals_by_volume(sigs, candles)
            if not sigs:
                return
        if LSW_MIN_TOUCHES_ENABLED:
            sigs = lsw_filter_signals_by_min_touches(sigs)
            if not sigs:
                return
        if LSW_FVG_FILTER_ENABLED:
            sigs = lsw_filter_signals_by_fvg(sigs, candles)
            if not sigs:
                return
        if LSW_SESSION_FILTER_ENABLED:
            sigs = lsw_filter_signals_by_session(sigs)
            if not sigs:
                return
        if LSW_CANDLE_STRUCTURE_FILTER_ENABLED:
            sigs = lsw_filter_signals_by_candle_structure(sigs, candles)
            if not sigs:
                return
        if LSW_DIRECTION_FILTER_ENABLED:
            with state_lock:
                allowed_dirs = STATE["lsw_live_directions"].get(symbol)
            if allowed_dirs is not None:  # None = no per-direction data yet (fresh symbol) — don't block on that alone
                sigs = [s for s in sigs if s["direction"] in allowed_dirs]
                if not sigs:
                    return
        sig = sigs[-1]
        if sig["entry_idx"] != len(candles) - 1:
            return  # most recent signal isn't off the latest closed candle — already stale/handled
        with _lsw_signal_cooldowns_lock:
            if _lsw_signal_cooldowns.get(symbol) == sig["entry_time"]:
                return
            # v0.99.154 — when entry confirmation is enabled, do NOT set
            # the cooldown here yet: if BOS hasn't appeared yet this pass,
            # the next scan (5m later) must be able to retry the same
            # signal. The old code set cooldown unconditionally here, so a
            # first "no BOS yet" pass permanently blocked all retries —
            # the BOS that appeared 10 minutes later was never seen.
            # Cooldown is now set only when the trade actually opens (or
            # when confirm is OFF, where setting it here is still correct
            # to prevent duplicates across back-to-back scan passes).
            if not LSW_ENTRY_CONFIRM_ENABLED:
                _lsw_signal_cooldowns[symbol] = sig["entry_time"]
        # v0.99.144 — BUG FOUND (per direct user report: LSW fired BOTH
        # a LONG and a SHORT on the same symbol at once): v0.99.120's
        # own comment below says this "switched from an LSW-only
        # 'already open' check to has_open_signal_any_module()" — that
        # wording undersells what actually happened: it REPLACED the
        # self-check instead of keeping both, and has_open_signal_any_
        # module() deliberately EXCLUDES lsw_signals from its own check
        # (each module is expected to check its own list itself — see
        # that function's own docstring). LSW never had that self-check
        # again after this refactor, so nothing ever stopped it from
        # opening a SECOND real position (a different level, opposite
        # direction, sweeping equal highs vs equal lows — genuinely
        # independent detections) on a symbol that already had one
        # open. Same fix MSNR/Mirror already carry: check STATE
        # directly (persisted, survives restart too, unlike the
        # cooldown dict alone) before the cross-module veto below.
        with state_lock:
            if any(s["symbol"] == symbol and s.get("status") == "OPEN" for s in STATE["lsw_signals"]):
                return
        if has_open_signal_any_module(symbol, exclude="lsw_signals"):
            return
        if LSW_ENTRY_CONFIRM_ENABLED:
            # v0.99.122 — rule #3 of the reference note: entry itself
            # is gated on a 5m confirmation trigger (BOS/поглощение/
            # инверсия), not fired straight off the 1h sweep candle's
            # own close. The cooldown above is already set at this
            # point (keyed on the 1h sweep's own entry_time) even if
            # confirmation never arrives, so a sweep that fails to
            # confirm isn't re-attempted on every subsequent scan pass.
            confirm_candles = get_candles(symbol, interval=LSW_ENTRY_CONFIRM_INTERVAL,
                                           limit=LSW_ENTRY_CONFIRM_MAX_BARS + 30)
            confirm_now = time.time()
            confirm_interval_sec = INTERVAL_SECONDS.get(LSW_ENTRY_CONFIRM_INTERVAL, 300)
            confirm_candles = [c for c in confirm_candles if c["time"] + confirm_interval_sec <= confirm_now]
            confirmed = lsw_apply_entry_confirmation([sig], confirm_candles)
            if not confirmed:
                return  # no BOS/поглощение/инверсия within the window yet — retry next scan pass
            sig = confirmed[0]
        # v0.99.154 — when confirm is enabled, cooldown is set HERE
        # (after BOS found) instead of before the confirm check, so
        # retries work correctly across scan passes until BOS appears.
        if LSW_ENTRY_CONFIRM_ENABLED:
            with _lsw_signal_cooldowns_lock:
                if _lsw_signal_cooldowns.get(symbol) == sig["entry_time"]:
                    return  # already fired this confirmed signal (race between scan threads)
                _lsw_signal_cooldowns[symbol] = sig["entry_time"]
        record = {
            "symbol": symbol, "direction": sig["direction"],
            "entry": sig["entry"], "sl": sig["sl"], "tp": sig["tp"], "rr": sig.get("rr"),
            "level_price": sig.get("level_price"), "level_type": sig.get("level_type"),
            "level_touches": sig.get("level_touches"), "time": sig["entry_time"],
            "confirm_method": sig.get("confirm_method"),
            "detected_at": time.time(), "status": "OPEN", "result": None,
            "exit_price": None, "exit_time": None, "app_version": APP_VERSION,
            "mfe_r": 0.0, "mae_r": 0.0, "mfe_price": None, "mae_price": None,
            "mfe_r_at_close": None, "mae_r_at_close": None, "timeout_pnl_r": None,
        }
        with state_lock:
            STATE["lsw_signals"].appendleft(record)
        if AUTOTRADE_ENABLED_LSW:
            autotrade_result = execute_autotrade("lsw", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"])
            sim_execute_trade("lsw", symbol, sig["direction"], sig["entry"], sig["sl"], sig["tp"],
                               AUTOTRADE_LEVERAGE_LSW, record)
            # v0.99.134 — BUG FOUND (per direct user report: a real
            # order attempt failed with status ERROR — "HTTPSConnection
            # Pool... Read timed out" — and the trade never opened even
            # after the network recovered): the cooldown above is set
            # BEFORE this call, purely to stop the SAME signal firing
            # twice across scan cycles once it's genuinely handled — but
            # "handled" included a bare network ERROR, permanently
            # burning the one shot this signal ever gets (a level fires
            # once, then stops being watched — see mirror_/lsw_detect_
            # signals()'s own docstring) on nothing but a transient
            # connectivity blip. A real SKIP (already has a position) or
            # a real OPENED both still keep the cooldown — only ERROR
            # releases it, so the NEXT scan pass (LSW_SCAN_INTERVAL_SEC
            # later) gets a genuine second attempt while this exact
            # signal is still the latest one on the latest candle.
            if autotrade_result and autotrade_result.get("status") == "ERROR":
                with _lsw_signal_cooldowns_lock:
                    if _lsw_signal_cooldowns.get(symbol) == sig["entry_time"]:
                        del _lsw_signal_cooldowns[symbol]
        arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
        level_labels = {"high": "снятие хаёв", "low": "снятие лоу"}
        send_telegram(
            f"{arrow} {symbol} ({level_labels.get(sig['level_type'], sig['level_type'])}, "
            f"x{sig.get('level_touches')} касания)\n"
            f"entry: {sig['entry']:.6g}\n"
            f"SL: {sig['sl']:.6g}  TP: {sig['tp']:.6g}",
            category="lsw",
        )
    except Exception as e:
        log_error(f"lsw_scan_symbol_live {symbol}: {e}")


def _lsw_track_signal_outcomes():
    """Same shared MFE/MAE/WIN/LOSS/TIMEOUT tracking shape as
    _mirror_track_signal_outcomes() — LSW has just the one signal pool
    (no separate filtered/shadow pool like MIRROR's), whether or not
    AUTOTRADE_ENABLED_LSW actually fired a real order for any given
    signal; the outcome tracking itself is identical either way."""
    now = time.time()
    with state_lock:
        open_signals = [s for s in STATE["lsw_signals"] if s["status"] == "OPEN"]
    all_candles = fetch_candles_concurrent([(s["symbol"], LSW_INTERVAL, 300) for s in open_signals])
    interval_sec = INTERVAL_SECONDS.get(LSW_INTERVAL, 3600)
    for sig, candles in zip(open_signals, all_candles):
        try:
            if candles is None:
                continue
            candles = [c for c in candles if c["time"] + interval_sec <= now]
            future = [c for c in candles if c["time"] > sig["time"]]
            direction = sig["direction"]
            entry = sig["entry"]
            risk = abs(entry - sig["sl"]) or 1e-9
            result = None
            exit_price = None
            exit_time = None
            bars_seen = 0
            for c in future:
                bars_seen += 1
                if direction == "LONG":
                    fav, adv = c["high"] - entry, entry - c["low"]
                else:
                    fav, adv = entry - c["low"], c["high"] - entry
                fav_r, adv_r = fav / risk, adv / risk
                with state_lock:
                    if fav_r > sig["mfe_r"]:
                        sig["mfe_r"] = round(fav_r, 3)
                        sig["mfe_price"] = c["high"] if direction == "LONG" else c["low"]
                    if adv_r > sig["mae_r"]:
                        sig["mae_r"] = round(adv_r, 3)
                        sig["mae_price"] = c["low"] if direction == "LONG" else c["high"]
                if direction == "LONG":
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
                if bars_seen >= LSW_MAX_WAIT_BARS:
                    result = "TIMEOUT"
                    exit_price = c["close"]
                    exit_time = c["time"]
                    break
            with state_lock:
                if result:
                    sig["status"] = "CLOSED"
                    sig["result"] = result
                    sig["exit_price"] = exit_price
                    sig["exit_time"] = exit_time
                    sig["mfe_r_at_close"] = sig["mfe_r"]
                    sig["mae_r_at_close"] = sig["mae_r"]
                    if result == "TIMEOUT" and exit_price is not None:
                        pnl_r = (exit_price - entry) / risk if direction == "LONG" else (entry - exit_price) / risk
                        sig["timeout_pnl_r"] = round(pnl_r, 3)
        except Exception as e:
            log_error(f"lsw_outcome {sig['symbol']}: {e}")


def update_lsw_signal_outcomes():
    _lsw_track_signal_outcomes()


def compute_lsw_signal_stats():
    with state_lock:
        signals = list(STATE["lsw_signals"])
    closed = [s for s in signals if s["status"] == "CLOSED" and s["result"] in ("WIN", "LOSS")]
    wins = sum(1 for s in closed if s["result"] == "WIN")
    losses = sum(1 for s in closed if s["result"] == "LOSS")
    open_n = sum(1 for s in signals if s["status"] == "OPEN")
    total_closed = len(closed)
    winrate = round(wins / total_closed * 100, 1) if total_closed else None
    by_level_type = {}
    for lt in ("high", "low"):
        lt_closed = [s for s in closed if s.get("level_type") == lt]
        lt_wins = sum(1 for s in lt_closed if s["result"] == "WIN")
        by_level_type[lt] = {
            "n": len(lt_closed), "wins": lt_wins, "losses": len(lt_closed) - lt_wins,
            "winrate": round(lt_wins / len(lt_closed) * 100, 1) if lt_closed else None,
        }
    return {"total": len(signals), "wins": wins, "losses": losses,
            "open": open_n, "winrate": winrate, "by_level_type": by_level_type}


def _lsw_backtest_one(symbol):
    """Same in-flight/done tracking as _msnr_backtest_one()'s own
    (v0.99.15) — marks itself in-flight in STATE for the duration of
    its own work, so the panel's progress bar can show which symbols
    are currently being backtested right now, not just a done/total
    count. v0.99.137, per direct user request for the same visibility
    LSW never had ("хочу видеть процесс бэктеста тут так же, как уже
    мы делали полоской")."""
    with state_lock:
        STATE["lsw_backtest_in_flight"].append(symbol)
    try:
        return symbol, lsw_backtest_symbol(symbol)
    finally:
        with state_lock:
            if symbol in STATE["lsw_backtest_in_flight"]:
                STATE["lsw_backtest_in_flight"].remove(symbol)
            STATE["lsw_backtest_done"] += 1


def lsw_backtest_loop():
    while True:
        try:
            if not LSW_ENABLED:
                time.sleep(60)
                continue
            t0 = time.time()
            universe = lsw_build_universe()
            results_by_symbol = {}
            summary_by_symbol = {}
            checkpoints_by_symbol = {}
            live_universe = []
            live_directions = {}
            with state_lock:
                STATE["lsw_backtest_total"] = len(universe)
                STATE["lsw_backtest_done"] = 0
                STATE["lsw_backtest_in_flight"] = []
                STATE["lsw_backtest_running"] = True
                STATE["lsw_backtest_started_at"] = t0
            try:
                with ThreadPoolExecutor(max_workers=min(WORKERS, len(universe) or 1)) as ex:
                    futs = {ex.submit(_lsw_backtest_one, s): s for s in universe}
                    for fut in as_completed(futs):
                        symbol = futs[fut]
                        try:
                            _sym, (results, meta) = fut.result()
                            results_by_symbol[symbol] = results
                            checkpoints_by_symbol[symbol] = meta.get("checkpoints", {})
                            summary = lsw_summarize_backtest(results)
                            summary_by_symbol[symbol] = summary
                            closed_n = summary["wins"] + summary["losses"]
                            if not (summary["win_rate"] is not None and summary["win_rate"] > LSW_LIVE_MIN_WINRATE
                                    and closed_n >= LSW_LIVE_MIN_SAMPLE):
                                continue
                            live_universe.append(symbol)
                            if LSW_DIRECTION_FILTER_ENABLED:
                                # v0.99.123 — same threshold as the overall
                                # gate above, applied per-direction with its
                                # own smaller sample floor, NOT a per-symbol
                                # "pick the winning side" choice — see this
                                # constant's own comment for why that
                                # distinction matters.
                                allowed = []
                                bd = summary.get("by_direction") or {}
                                for d in ("LONG", "SHORT"):
                                    dd = bd.get(d) or {}
                                    if (dd.get("n", 0) >= LSW_DIRECTION_MIN_SAMPLE
                                            and dd.get("win_rate") is not None
                                            and dd["win_rate"] > LSW_LIVE_MIN_WINRATE):
                                        allowed.append(d)
                                live_directions[symbol] = allowed
                        except Exception as e:
                            log_error(f"lsw_backtest {symbol}: {e}")
                with state_lock:
                    STATE["lsw_backtest_results"] = results_by_symbol
                    STATE["lsw_backtest_summary"] = summary_by_symbol
                    STATE["lsw_filter_checkpoints"] = checkpoints_by_symbol
                    STATE["lsw_live_universe"] = live_universe
                    STATE["lsw_live_directions"] = live_directions
                    STATE["lsw_last_backtest_finished"] = time.time()
                    STATE["lsw_last_backtest_duration"] = round(time.time() - t0, 1)
            finally:
                # v0.99.137 — always clears "running" even if the cycle
                # above raised partway through, same reasoning as MSNR's
                # own identical finally block: a stale "running" flag
                # left on after a genuine failure would show 100%
                # confident progress on a cycle that already died.
                with state_lock:
                    STATE["lsw_backtest_running"] = False
                    STATE["lsw_backtest_in_flight"] = []
        except Exception as e:
            log_error(f"lsw_backtest_loop: {e}")
        # v0.99.137 — Event.wait(timeout=...) instead of a plain sleep,
        # same fix as MSNR's own v0.99.40: api_reset_lsw() can now cut
        # this short via LSW_BACKTEST_TRIGGER.set() instead of "Очистить
        # Sweep" doing nothing but wipe the display until the full
        # LSW_REFRESH_SEC (up to 1h) elapses on its own. Cleared right
        # after so the NEXT cycle's own wait isn't pre-satisfied by a
        # stale set() from this one.
        LSW_BACKTEST_TRIGGER.wait(timeout=max(300, LSW_REFRESH_SEC))
        LSW_BACKTEST_TRIGGER.clear()


def lsw_live_loop():
    while True:
        try:
            if not LSW_ENABLED:
                time.sleep(60)
                continue
            with state_lock:
                live_universe = list(STATE.get("lsw_live_universe", []))
            if live_universe:
                with ThreadPoolExecutor(max_workers=min(WORKERS, len(live_universe))) as ex:
                    list(ex.map(lsw_scan_symbol_live, live_universe))
            update_lsw_signal_outcomes()
        except Exception as e:
            log_error(f"lsw_live_loop: {e}")
        # v0.99.152 — sync to candle close instead of a fixed 300s sleep.
        # Previously the loop slept a flat 5 min between passes — if a
        # candle closed at 03:00:01, the next scan might not run until
        # 03:03-03:04 depending on where in the 300s cycle we were, and
        # after spending time processing all symbols the order could land
        # 1-2 minutes into the new candle — visually "one candle late".
        # Now: sleep until a few seconds AFTER the next LSW_INTERVAL
        # candle boundary, so every scan fires as close as possible to
        # the moment a new candle opens (= previous candle just closed).
        # Buffer of 3s gives Gate time to finalize the last candle.
        # v0.99.153 — when LSW_ENTRY_CONFIRM_ENABLED, the confirmation
        # check (5m BOS/absorption/inversion) needs to run more often
        # than once per 1h candle — otherwise the BOS that appears 10
        # minutes after the sweep candle is missed until the next 1h
        # boundary. Use the confirmation interval (5m) instead so the
        # loop wakes up each time a new 5m candle closes and can detect
        # the BOS promptly. When confirmation is off, keep syncing to
        # the main LSW_INTERVAL boundary so new sweep signals are caught
        # immediately after each candle closes.
        if LSW_ENTRY_CONFIRM_ENABLED:
            scan_interval_sec = INTERVAL_SECONDS.get(LSW_ENTRY_CONFIRM_INTERVAL, 300)
        else:
            scan_interval_sec = INTERVAL_SECONDS.get(LSW_INTERVAL, 3600)
        now = time.time()
        secs_into_interval = now % scan_interval_sec
        sleep_sec = (scan_interval_sec - secs_into_interval) + 3
        time.sleep(sleep_sec)


# ============================================================================
# END LSW
# ============================================================================


# ----------------------------------------------------------------------------
# API
# ----------------------------------------------------------------------------
@app.route("/api/overview")
def api_overview():
    """Compact win-rate summary across Volume Profile and Scalp, for the
    persistent header — one call instead of hitting separate endpoints on
    every poll regardless of which tab is open."""
    vp = compute_signal_stats()
    scalp = compute_scalp_signal_stats()
    return jsonify({
        "volume": {"winrate": vp["winrate"], "wins": vp["wins"], "losses": vp["losses"], "open": vp["open"],
                    "enabled": VOLUME_PROFILE_ENABLED},
        "scalp": {"winrate": scalp["win_rate"], "wins": scalp["wins"], "losses": scalp["losses"], "timeouts": scalp["timeouts"], "open": scalp["open"],
                   "enabled": SCALP_SIGNALS_ENABLED},
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
            "errors": list(STATE["errors"]),
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
    # v0.99.82, per direct user report with a screenshot ("volume криво
    # отображает график, точка входа не на графике, стопа или тейка не
    # видно тоже" — CHIP_USDT, a resolved/older signal): confirmed the
    # actual cause wasn't a rendering/scale bug at all — this endpoint
    # always fetched "the latest N candles" via get_candles(), with no
    # way to anchor to a SPECIFIC past signal's own time. Clicking an
    # older signal (especially one where price has since moved a lot)
    # showed TODAY's candles with that old trade's entry/sl/tp lines
    # overlaid — if price moved far enough, those levels genuinely sit
    # outside the displayed window entirely, exactly matching "точка
    # входа не на графике." Same class of bug already found and fixed
    # for MSNR's own chart (api_msnr_chart()'s docstring has the fuller
    # incident writeup) — re-deriving/re-fetching with CURRENT state
    # instead of anchoring to the historical moment being reviewed.
    # openChart()/the "Оптимизировать" re-fetch now pass `time` (the
    # clicked row's own signal time, already present on every row —
    # used elsewhere for fmtTime(r.time) in the same table) when
    # available. When given, candles are fetched via get_candles_range()
    # anchored around THAT time instead of "whatever's most recent" —
    # and the volume PROFILE itself is built only from candles AT OR
    # BEFORE the signal's own time, matching what the original trade's
    # own zones would actually have been computed from (no lookahead
    # into price action the trade couldn't have known about). Omitting
    # `time` (any other caller of this endpoint, if one exists) keeps
    # the original "latest N candles" behavior exactly as before —
    # fully backward compatible.
    sig_time = request.args.get("time")
    try:
        if sig_time:
            sig_time = float(sig_time)
            interval_sec = INTERVAL_SECONDS.get(interval, 300)
            fetch_start = sig_time - (lookback + 10) * interval_sec
            fetch_end = sig_time + 90 * interval_sec
            all_candles = get_candles_range(symbol, interval, fetch_start, fetch_end)
            profile_source = [c for c in all_candles if c["time"] <= sig_time]
            display_candles = all_candles
        else:
            all_candles = get_candles(symbol, interval=interval, limit=lookback + 5)
            profile_source = all_candles
            display_candles = all_candles[-lookback:]
        profile = build_profile_for_symbol(symbol, profile_source, lookback, segs=SEGS, interval=interval)
        if not profile:
            return jsonify({"error": "not enough data"}), 400
        zones = extract_hvn_zones(profile, top_n=hvn_top_n)
        strong_mids = {z["mid"] for z in eligible_zones(zones)}
        for z in zones:
            z["eligible"] = z["mid"] in strong_mids
        return jsonify({
            "symbol": symbol,
            "reason": reason,
            "candles": display_candles,
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






@app.route("/api/mirror/status")
def api_mirror_status():
    """See the MIRROR module's own header comment (near mirror_is_
    inside_bar())."""
    with state_lock:
        summary = dict(STATE["mirror_backtest_summary"])
        overrides = dict(STATE["mirror_symbol_overrides"])
        tuned_tolerances = dict(STATE["mirror_tuned_tolerances"])
        live_universe = list(STATE["mirror_live_universe"])
        last_backtest_finished = STATE["mirror_last_backtest_finished"]
        last_backtest_duration = STATE["mirror_last_backtest_duration"]
    # v0.99.92 — merge each symbol's summary with its own override meta
    # (skip_sl_pct_min, filter checkpoints) so the UI can render the
    # before/after picture per direct user request ("по статистике
    # обязательно показывать до после как в msnr") without a second
    # round-trip. v0.99.130 adds each symbol's own autotuned tolerance
    # combo (if any) the same way.
    ranked = [dict(s, symbol=sym, live=(sym in live_universe),
                   tuned_tolerance=tuned_tolerances.get(sym), **(overrides.get(sym) or {}))
              for sym, s in summary.items()]
    ranked.sort(key=lambda r: (r["win_rate"] or 0, r["n"]), reverse=True)
    return jsonify({
        "enabled": MIRROR_ENABLED,
        "last_backtest_finished": last_backtest_finished,
        "last_backtest_duration": last_backtest_duration,
        "signals_stats": compute_mirror_signal_stats(),
        "filtered_signals_stats": compute_mirror_filtered_signal_stats(),
        "live_universe": live_universe,
        "config": {
            "interval": MIRROR_INTERVAL, "pivot_left": MIRROR_PIVOT_LEFT, "pivot_right": MIRROR_PIVOT_RIGHT,
            "touch_tolerance_pct": MIRROR_TOUCH_TOLERANCE_PCT, "pattern_tolerance_pct": MIRROR_PATTERN_TOLERANCE_PCT,
            "rr": MIRROR_RR, "max_bars_to_return": MIRROR_MAX_BARS_TO_RETURN,
            "backtest_days": MIRROR_BACKTEST_DAYS, "universe_size": MIRROR_UNIVERSE_SIZE,
            "live_min_winrate": MIRROR_LIVE_MIN_WINRATE, "live_min_sample": MIRROR_LIVE_MIN_SAMPLE,
            "autotune_tolerance_enabled": MIRROR_AUTOTUNE_TOLERANCE_ENABLED,
            "volume_filter_enabled": MIRROR_VOLUME_FILTER_ENABLED,
            "htf_filter_enabled": MIRROR_HTF_FILTER_ENABLED, "htf_interval": MIRROR_HTF_INTERVAL,
        },
        "top": ranked,
    })


@app.route("/api/mirror/chart/<symbol>")
def api_mirror_chart(symbol):
    """Same "look up the signal's own already-recorded entry/sl/tp,
    don't re-derive with CURRENT live params" fix already applied to
    api_msnr_chart() (see its own docstring for
    the full incident this avoids) — MIRROR_RR/MIRROR_TOUCH_TOLERANCE_
    PCT/MIRROR_PATTERN_TOLERANCE_PCT could all drift between when a
    trade fired and when its chart is later opened."""
    try:
        sig_time = request.args.get("time")
        found_sig = None
        found_result = None
        found_exit_time = None
        found_exit_price = None
        if sig_time:
            target = float(sig_time)
            interval_sec = INTERVAL_SECONDS.get(MIRROR_INTERVAL, 3600)
            with state_lock:
                live_match = next((s for s in STATE["mirror_signals"]
                                    if s["symbol"] == symbol and abs(s["time"] - target) < interval_sec), None)
                bt_trades = list(STATE["mirror_backtest_results"].get(symbol, []))
            if live_match:
                found_sig = {"time": live_match["time"], "direction": live_match["direction"],
                              "entry": live_match["entry"], "sl": live_match["sl"], "tp": live_match["tp"],
                              "pattern": live_match.get("pattern"), "rr": live_match.get("rr"),
                              "level_price": live_match.get("level_price"), "level_type": live_match.get("level_type")}
                found_result = live_match.get("result")
                found_exit_time = live_match.get("exit_time")
                found_exit_price = live_match.get("exit_price")
            else:
                bt_match = next((t for t in bt_trades if abs(t["time"] - target) < interval_sec), None)
                if bt_match:
                    found_sig = {"time": bt_match["time"], "direction": bt_match["direction"],
                                  "entry": bt_match["entry"], "sl": bt_match["sl"], "tp": bt_match["tp"],
                                  "pattern": bt_match.get("pattern"), "rr": bt_match.get("rr"),
                                  "level_price": bt_match.get("level_price"), "level_type": bt_match.get("level_type")}
                    found_result = bt_match.get("result")
                    found_exit_time = bt_match.get("exit_time")
                    if found_result == "WIN":
                        found_exit_price = bt_match["tp"]
                    elif found_result == "LOSS":
                        found_exit_price = bt_match["sl"]
        if found_sig is None:
            return jsonify({"error": "сигнал не найден"}), 404
        interval_sec = INTERVAL_SECONDS.get(MIRROR_INTERVAL, 3600)
        fetch_start = found_sig["time"] - (MIRROR_LOOKBACK + MIRROR_PIVOT_LEFT + MIRROR_PIVOT_RIGHT) * interval_sec
        fetch_end = (found_exit_time + 6 * interval_sec) if found_exit_time else (found_sig["time"] + 200 * interval_sec)
        candles = get_candles_range(symbol, MIRROR_INTERVAL, fetch_start, fetch_end)
        return jsonify({
            "symbol": symbol, "candles": candles[-250:], "time": found_sig["time"],
            "direction": found_sig["direction"], "entry": found_sig["entry"],
            "sl": found_sig["sl"], "tp": found_sig["tp"], "rr": found_sig.get("rr"),
            "pattern": found_sig.get("pattern"),
            "level_price": found_sig.get("level_price"), "level_type": found_sig.get("level_type"),
            "result": found_result, "exit_time": found_exit_time, "exit_price": found_exit_price,
            "chart_source": "mirror",
        })
    except Exception as e:
        log_error(f"api_mirror_chart {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/mirror/signals")
def api_mirror_signals():
    with state_lock:
        return jsonify(list(STATE["mirror_signals"]))


@app.route("/api/lsw/status")
def api_lsw_status():
    """See the LSW module's own header comment (near lsw_find_pivots())."""
    with state_lock:
        summary = dict(STATE["lsw_backtest_summary"])
        live_universe = list(STATE["lsw_live_universe"])
        live_directions = dict(STATE["lsw_live_directions"])
        checkpoints = dict(STATE["lsw_filter_checkpoints"])
        last_backtest_finished = STATE["lsw_last_backtest_finished"]
        last_backtest_duration = STATE["lsw_last_backtest_duration"]
        backtest_total = STATE["lsw_backtest_total"]
        backtest_done = STATE["lsw_backtest_done"]
        backtest_in_flight = list(STATE["lsw_backtest_in_flight"])
        backtest_running = STATE["lsw_backtest_running"]
        backtest_started_at = STATE["lsw_backtest_started_at"]
    ranked = [dict(s, symbol=sym, live=(sym in live_universe),
                   live_directions=live_directions.get(sym),
                   filter_checkpoints=checkpoints.get(sym)) for sym, s in summary.items()]
    ranked.sort(key=lambda r: (r["win_rate"] or 0, r["n"]), reverse=True)
    return jsonify({
        "enabled": LSW_ENABLED,
        "last_backtest_finished": last_backtest_finished,
        "last_backtest_duration": last_backtest_duration,
        "backtest_running": backtest_running,
        "backtest_total": backtest_total,
        "backtest_done": backtest_done,
        "backtest_in_flight": backtest_in_flight,
        "backtest_started_at": backtest_started_at,
        "signals_stats": compute_lsw_signal_stats(),
        "live_universe": live_universe,
        "config": {
            "interval": LSW_INTERVAL, "pivot_left": LSW_PIVOT_LEFT, "pivot_right": LSW_PIVOT_RIGHT,
            "equal_tolerance_pct": LSW_EQUAL_TOLERANCE_PCT, "sl_buffer_pct": LSW_SL_BUFFER_PCT,
            "rr": LSW_RR, "max_bars_to_sweep": LSW_MAX_BARS_TO_SWEEP,
            "backtest_days": LSW_BACKTEST_DAYS, "universe_size": LSW_UNIVERSE_SIZE,
            "live_min_winrate": LSW_LIVE_MIN_WINRATE, "live_min_sample": LSW_LIVE_MIN_SAMPLE,
            "htf_filter_enabled": LSW_HTF_FILTER_ENABLED, "htf_interval": LSW_HTF_INTERVAL,
            "structural_cap_enabled": LSW_STRUCTURAL_CAP_ENABLED,
            "volume_filter_enabled": LSW_VOLUME_FILTER_ENABLED,
            "fvg_filter_enabled": LSW_FVG_FILTER_ENABLED,
            "session_filter_enabled": LSW_SESSION_FILTER_ENABLED,
            "min_touches_enabled": LSW_MIN_TOUCHES_ENABLED, "min_touches": LSW_MIN_TOUCHES,
            "candle_structure_filter_enabled": LSW_CANDLE_STRUCTURE_FILTER_ENABLED,
            "entry_confirm_enabled": LSW_ENTRY_CONFIRM_ENABLED, "entry_confirm_interval": LSW_ENTRY_CONFIRM_INTERVAL,
            "direction_filter_enabled": LSW_DIRECTION_FILTER_ENABLED,
        },
        "top": ranked,
    })


@app.route("/api/lsw/chart/<symbol>")
def api_lsw_chart(symbol):
    """Same "look up the signal's own already-recorded entry/sl/tp,
    don't re-derive with CURRENT live params" fix already applied to
    api_mirror_chart()/api_msnr_chart() — LSW_RR/LSW_EQUAL_TOLERANCE_PCT
    could drift between when a trade fired and when its chart is later
    opened."""
    try:
        sig_time = request.args.get("time")
        found_sig = None
        found_result = None
        found_exit_time = None
        found_exit_price = None
        if sig_time:
            target = float(sig_time)
            interval_sec = INTERVAL_SECONDS.get(LSW_INTERVAL, 3600)
            with state_lock:
                live_match = next((s for s in STATE["lsw_signals"]
                                    if s["symbol"] == symbol and abs(s["time"] - target) < interval_sec), None)
                bt_trades = list(STATE["lsw_backtest_results"].get(symbol, []))
            if live_match:
                found_sig = {"time": live_match["time"], "direction": live_match["direction"],
                              "entry": live_match["entry"], "sl": live_match["sl"], "tp": live_match["tp"],
                              "rr": live_match.get("rr"),
                              "level_price": live_match.get("level_price"), "level_type": live_match.get("level_type")}
                found_result = live_match.get("result")
                found_exit_time = live_match.get("exit_time")
                found_exit_price = live_match.get("exit_price")
            else:
                bt_match = next((t for t in bt_trades if abs(t["time"] - target) < interval_sec), None)
                if bt_match:
                    found_sig = {"time": bt_match["time"], "direction": bt_match["direction"],
                                  "entry": bt_match["entry"], "sl": bt_match["sl"], "tp": bt_match["tp"],
                                  "rr": bt_match.get("rr"),
                                  "level_price": bt_match.get("level_price"), "level_type": bt_match.get("level_type")}
                    found_result = bt_match.get("result")
                    found_exit_time = bt_match.get("exit_time")
                    if found_result == "WIN":
                        found_exit_price = bt_match["tp"]
                    elif found_result == "LOSS":
                        found_exit_price = bt_match["sl"]
        if found_sig is None:
            return jsonify({"error": "сигнал не найден"}), 404
        interval_sec = INTERVAL_SECONDS.get(LSW_INTERVAL, 3600)
        fetch_start = found_sig["time"] - (LSW_LOOKBACK + LSW_PIVOT_LEFT + LSW_PIVOT_RIGHT) * interval_sec
        fetch_end = (found_exit_time + 6 * interval_sec) if found_exit_time else (found_sig["time"] + 200 * interval_sec)
        candles = get_candles_range(symbol, LSW_INTERVAL, fetch_start, fetch_end)
        return jsonify({
            "symbol": symbol, "candles": candles[-250:], "time": found_sig["time"],
            "direction": found_sig["direction"], "entry": found_sig["entry"],
            "sl": found_sig["sl"], "tp": found_sig["tp"], "rr": found_sig.get("rr"),
            "level_price": found_sig.get("level_price"), "level_type": found_sig.get("level_type"),
            "result": found_result, "exit_time": found_exit_time, "exit_price": found_exit_price,
            "chart_source": "lsw",
        })
    except Exception as e:
        log_error(f"api_lsw_chart {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/lsw/signals")
def api_lsw_signals():
    with state_lock:
        return jsonify(list(STATE["lsw_signals"]))


@app.route("/api/reset/lsw", methods=["POST"])
def api_reset_lsw():
    try:
        with state_lock:
            STATE["lsw_backtest_results"] = {}
            STATE["lsw_backtest_summary"] = {}
            STATE["lsw_live_universe"] = []
            STATE["lsw_last_backtest_finished"] = None
            STATE["lsw_last_backtest_duration"] = None
            STATE["lsw_signals"].clear()
        # v0.99.137 — per direct user report ("нажал очистить sweep,
        # новый бэктест сразу начнется?"), same fix as api_reset_msnr()'s
        # own v0.99.40: wakes lsw_backtest_loop() immediately instead of
        # leaving it asleep for up to LSW_REFRESH_SEC (up to 1h default).
        LSW_BACKTEST_TRIGGER.set()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_lsw: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/reset/mirror", methods=["POST"])
def api_reset_mirror():
    try:
        with state_lock:
            STATE["mirror_backtest_results"] = {}
            STATE["mirror_backtest_summary"] = {}
            STATE["mirror_symbol_overrides"] = {}
            STATE["mirror_live_universe"] = []
            STATE["mirror_last_backtest_finished"] = None
            STATE["mirror_last_backtest_duration"] = None
            STATE["mirror_signals"].clear()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_mirror: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


def msnr_effective_live_universe(live_universe, overrides, autotrade_symbols):
    """v0.99.35, per direct user question after the green ● dot didn't
    line up with which symbols the checkbox/eligible list suggested
    were actually trading: the REAL set msnr_live_loop() scans is
    msnr_compute_live_universe()'s own promoted set (gold + winrate>
    MSNR_LIVE_PROMOTE_MIN_WINRATE with sample>MSNR_LIVE_PROMOTE_MIN_
    SAMPLE) UNION'd with whatever's toggled autotrade-ON. v0.99.32
    built the underlying union, but built it INLINE inside msnr_live_
    loop() itself rather than as a reusable function, so api_msnr_
    status()'s own "live" flag (the dot the person actually sees) kept
    reading the narrower msnr_live_universe alone. Pulled out into its
    own function so both call sites share one definition and can't
    drift apart on this again.
    v0.99.108, per direct user request ("Ручное управление можно
    убрать"): now unions against msnr_autotrade_eligible_symbols() (the
    NARROWER top-N set), not the old msnr_manual_toggle_allowed_symbols()
    — the toggle is now ONLY ever set by msnr_backtest_loop()'s own
    auto-management (top-N + win_rate>50), so it can never legitimately
    be True for a symbol outside the top-N in the first place; the
    broader set existed purely to support manual toggling of non-top-10
    symbols, which no longer exists."""
    allowed_now = msnr_autotrade_eligible_symbols(overrides)
    toggled_on_allowed = [sym for sym, on in autotrade_symbols.items() if on and sym in allowed_now]
    return list(dict.fromkeys(list(live_universe) + toggled_on_allowed))


@app.route("/api/msnr/status")
def api_msnr_status():
    """EXPERIMENTAL — see the MSNR module's own header comment."""
    with state_lock:
        overrides = dict(STATE["msnr_symbol_overrides"])
        backtest_universe = list(STATE["msnr_backtest_universe"])
        backtest_results_raw = dict(STATE["msnr_backtest_results_raw"])
        live_universe = list(STATE["msnr_live_universe"]) or list(MSNR_SYMBOLS)
        autotrade_symbols = dict(STATE["msnr_autotrade_symbols"])
        last_backtest_finished = STATE["msnr_last_backtest_finished"]
        last_backtest_duration = STATE["msnr_last_backtest_duration"]
        backtest_total = STATE["msnr_backtest_total"]
        backtest_done = STATE["msnr_backtest_done"]
        backtest_in_flight = list(STATE["msnr_backtest_in_flight"])
        backtest_running = STATE["msnr_backtest_running"]
        backtest_started_at = STATE["msnr_backtest_started_at"]
    # Ranked by msnr_ranking_score() (a lower-confidence-bound on mean R,
    # v0.99.5 — see msnr_ranking_score()'s own docstring), not raw
    # win-rate — same reasoning as FT5's api_ft5_status(): a lucky small
    # sample or unevenly-distributed wins/losses across RR shouldn't
    # outrank a larger, steadier combo just because its raw average
    # looks better. Symbols with an error or no result sort last.
    # v0.99.17: "live" now checks the DYNAMIC promoted set (live_universe),
    # not the static MSNR_SYMBOLS constant — a symbol can be live because
    # it's gold OR because it earned promotion via win-rate/sample.
    # v0.99.18: autotrade_eligible (exactly the 6 symbols — gold + current
    # top 3 by msnr_rank_by_winrate_sample()) and each entry's own
    # autotrade_on state, so the panel can render exactly 6 checkboxes,
    # correctly pre-checked, without a separate round-trip.
    # v0.99.76 — computed ONCE here and passed to both eligibility and
    # the overall table sort below, so a symbol's ranking is identical
    # whichever one reads it — see msnr_compute_rank_bounds()'s own
    # docstring for why that sharing matters.
    msnr_rank_bounds = msnr_compute_rank_bounds(overrides)
    autotrade_eligible = msnr_autotrade_eligible_symbols(overrides, bounds=msnr_rank_bounds)
    # v0.99.49, per direct user request ("хочу иметь возможность
    # автоторговли и не по топ-10, на свой страх и риск"): a SEPARATE,
    # v0.99.35 — the dot shown per row now uses the SAME effective set
    # msnr_live_loop() actually scans (msnr_effective_live_universe()),
    # not the narrower promoted-only live_universe — see that function's
    # own docstring for why those two had drifted apart since v0.99.32.
    effective_live_universe = msnr_effective_live_universe(live_universe, overrides, autotrade_symbols)
    ranked = [dict(v, symbol=sym, live=(sym in effective_live_universe),
                   autotrade_eligible=(sym in autotrade_eligible),
                   autotrade_on=bool(autotrade_symbols.get(sym)))
              for sym, v in overrides.items() if v and not v.get("error")]
    # v0.99.75/76, per direct user request ("плавное убывание в топ 10
    # и последующее продолжение убывание вне списка", then "чтобы на
    # выборку и доход тоже учитывало"): this table's own display order
    # uses the EXACT same msnr_symbol_rank_score() (against the SAME
    # msnr_rank_bounds computed once above) that msnr_rank_by_winrate_
    # sample() uses to pick the top 10 — before v0.99.75 these were two
    # DIFFERENT sorts (this one by `score` alone, top-10 membership by
    # a weighted income/score composite), which is exactly what
    # produced the discontinuity the request describes: a symbol's
    # position in the full table didn't necessarily track its own
    # top-10 standing. Now they're the same score computed against the
    # same bounds, so scrolling from #1 through #10 into "the rest" is
    # one continuous ordering, not two different ones stitched
    # together — see msnr_compute_rank_bounds()'s own docstring for why
    # sharing the bounds (not just the formula) matters just as much.
    # v0.99.27, per direct user request ("просто не попадает в топ"):
    # stress_test_failed symbols (see msnr_optimize_symbol()'s own
    # docstring — a losing $ compound simulation) still sort BELOW every
    # symbol that passed, regardless of rank score — `not stress_test_
    # failed` stays the primary grouping (True > False, so passing
    # symbols come first under reverse=True), msnr_symbol_rank_score()
    # is the secondary key within each group. A hard sort-order gate,
    # not part of the ranking score itself — msnr_rank_by_winrate_
    # sample() (autotrade eligibility) already excludes these outright;
    # this keeps the general table's own visual order consistent with
    # that instead of a failed symbol still floating near the top on
    # winrate alone.
    # v0.99.95, per direct user request ("сортировку msnr индикатора
    # сделай только по депозиту"): table order now sorts purely by
    # compound_return_pct (доход/deposit growth) instead of msnr_
    # symbol_rank_score()'s winrate/sample/доход composite. The
    # stress_test_failed grouping stays — that's a hard pass/fail gate,
    # independent of whatever metric ranks the passing symbols.
    ranked.sort(key=lambda r: (not r.get("stress_test_failed"),
                                r.get("compound_return_pct") if r.get("compound_return_pct") is not None else float("-inf")),
                reverse=True)
    # v0.99.11: RR-bucket win-rate, pooled across every symbol's own
    # backtest trades — per direct user observation (SPCX: rr>6 trades
    # consistently hit stop) that a pooled avg/median RR can't reveal
    # this kind of pattern on its own. Same pooling MSNR_MAX_RR's own
    # autotune rule uses, so what's displayed matches what's actually
    # driving the cap. v0.99.23: reads msnr_backtest_results_raw (pre-
    # skip-filter), not msnr_backtest_results — the latter now has each
    # symbol's own skip_rr_min-failing trades already removed, which
    # would silently understate exactly the badness this pooled bucket
    # view exists to surface.
    pooled_trades = [t for sym_trades in backtest_results_raw.values() for t in sym_trades]
    rr_buckets = msnr_rr_bucket_stats(pooled_trades)
    return jsonify({
        "enabled": MSNR_ENABLED,
        "symbols": MSNR_SYMBOLS,
        "live_universe": live_universe,
        "autotrade_eligible": autotrade_eligible,
        "backtest_universe_size": len(backtest_universe),
        "last_backtest_finished": last_backtest_finished,
        "last_backtest_duration": last_backtest_duration,
        "backtest_running": backtest_running,
        "backtest_total": backtest_total,
        "backtest_done": backtest_done,
        "backtest_in_flight": backtest_in_flight,
        "backtest_started_at": backtest_started_at,
        "signals_stats": compute_msnr_signal_stats(),
        "rr_buckets": rr_buckets,
        "config": {
            "structure_tf": MSNR_STRUCTURE_TF, "entry_tf": MSNR_ENTRY_TF,
            "pivot_left": MSNR_PIVOT_LEFT, "pivot_right": MSNR_PIVOT_RIGHT,
            "min_leg_atr": MSNR_MIN_LEG_ATR, "qm_zone_pct": MSNR_QM_ZONE_PCT,
            "qm_lookback_bars": MSNR_QM_LOOKBACK_BARS, "backtest_days": MSNR_BACKTEST_DAYS,
            "max_rr": MSNR_MAX_RR,
            "grid_min_leg_atr": MSNR_PARAM_GRID_MIN_LEG_ATR, "grid_qm_zone_pct": MSNR_PARAM_GRID_QM_ZONE_PCT,
            "grid_qm_lookback": MSNR_PARAM_GRID_QM_LOOKBACK,
            "compound_start_balance": MSNR_COMPOUND_START_BALANCE, "compound_leverage": AUTOTRADE_LEVERAGE_MSNR,
            "refresh_sec": MSNR_REFRESH_SEC,
            "min_rr_filter_enabled": MSNR_MIN_RR_FILTER_ENABLED, "min_rr_filter": MSNR_MIN_RR_FILTER,
            "htf_filter_enabled": MSNR_HTF_FILTER_ENABLED, "htf_interval": MSNR_HTF_INTERVAL,
        },
        "top": ranked,
    })


@app.route("/api/msnr/signals")
def api_msnr_signals():
    with state_lock:
        return jsonify(list(STATE["msnr_signals"]))


@app.route("/api/msnr/backtest/<symbol>")
def api_msnr_backtest_trades(symbol):
    """Full per-trade backtest list for one symbol (the summary table only
    shows aggregates) — each trade's `time` can be fed straight into
    /api/msnr/chart/<symbol>?time=... to see exactly how that A/V pair
    and QM trigger were derived.
    v0.99.25, per direct user request after noticing a symbol that
    compounds to $0 (APR_USDT) still ranked near the top of the table
    by score: each trade is now also annotated with the compounding
    balance immediately before/after it (msnr_compound_trail()), so
    the "доход" figure in the summary row can be checked trade-by-
    trade instead of trusted as a single opaque number — exactly what
    was asked for, before deciding whether/how the ranking itself
    needs to account for this kind of blow-up risk. Matched to each
    trade by `time` (the trail is computed in chronological order,
    this endpoint's own list is sorted newest-first for display, so a
    plain zip() would pair the wrong rows). TIMEOUT trades and any
    trade after the account already hit $0 have no trail entry —
    balance_before/after come back None for those, same "wasn't
    actually reached" reasoning the compounding functions use."""
    with state_lock:
        trades = list(STATE["msnr_backtest_results"].get(symbol, []))
        optimal_leverage = (STATE["msnr_symbol_overrides"].get(symbol) or {}).get("optimal_leverage")
    # v0.99.25: keyed by (time, direction), not time alone — an A-shape
    # and a V-shape level can structurally both resolve on the exact
    # same entry candle (rare, but msnr_detect_signals() checks them in
    # separate if-blocks, not elif), which would collide on a time-only
    # key and silently misattribute one trade's balance to the other.
    # v0.99.47: passes this symbol's own Kelly-optimal leverage through
    # so the trail's per-trade pnl_pct matches what the summary row's
    # own "доход" figure was computed with (msnr_optimize_symbol() now
    # resolves the SAME value for its own msnr_compound_return() call)
    # — leaving this at the flat default would make the expanded
    # per-trade view silently disagree with the summary above it.
    trail_by_key = {(row["time"], row.get("direction")): row
                     for row in msnr_compound_trail(trades, leverage=optimal_leverage)}
    for t in trades:
        row = trail_by_key.get((t["time"], t.get("direction")))
        t["compound_balance_before"] = row["balance_before"] if row else None
        t["compound_balance_after"] = row["balance_after"] if row else None
        t["compound_pnl_pct"] = row["pnl_pct"] if row else None
        t["compound_leverage"] = row["leverage"] if row else None
    trades.sort(key=lambda t: t["time"], reverse=True)
    return jsonify(trades)


@app.route("/api/msnr/chart/<symbol>")
def api_msnr_chart(symbol):
    """Draws a signal — backtest trade or live signal — using its OWN
    already-recorded entry/sl/tp/direction/level data directly when
    `time` matches one, rather than blindly re-deriving via a fresh
    msnr_detect_signals() call with the symbol's CURRENT live params.
    v0.99.10: that re-derivation was the original design (still used as
    the fallback below, for browsing the current live Storyline with no
    specific historical signal in mind) — but it broke for backtest
    trades specifically, confirmed from a direct user report (chart for
    a QQQX_USDT backtest trade said "нет подтверждённого QM-сигнала").
    Root cause: msnr_symbol_params(symbol) fetches the CURRENT override
    — if a newer backtest/autotune cycle has run since the clicked
    trade was originally found (very plausible right after v0.99.9
    expanded MSNR to 30+ symbols, meaning fresh optimize passes for
    many of them), the winning (min_leg_atr, qm_zone_pct, qm_lookback)
    combo can differ from whatever combo actually produced that trade —
    different params can easily fail to re-detect the same signal
    entirely. Since every stored trade (msnr_run_backtest()'s own
    return shape) and every live signal record already carries its own
    complete entry/sl/tp/direction/level/result/exit_time, there was
    never a need to re-derive anything for an already-known signal —
    same principle FT5's api_ft5_chart() already uses its own stored
    trade data for, rather than re-deriving with live-mutable params."""
    try:
        sig_time = request.args.get("time")
        now = time.time()
        found_sig = None
        found_result = None
        found_exit_time = None
        found_exit_price = None
        if sig_time:
            target = float(sig_time)
            e_interval_sec = INTERVAL_SECONDS.get(MSNR_ENTRY_TF, 900)
            with state_lock:
                live_match = next((s for s in STATE["msnr_signals"]
                                    if s["symbol"] == symbol and abs(s["time"] - target) < e_interval_sec), None)
                bt_trades = list(STATE["msnr_backtest_results"].get(symbol, []))
            if live_match:
                found_sig = {"time": live_match["time"], "direction": live_match["direction"],
                              "entry": live_match["entry"], "sl": live_match["sl"], "tp": live_match["tp"],
                              "level": live_match["level"], "level_type": live_match["level_type"],
                              "opposite_level": live_match.get("opposite_level")}
                found_result = live_match.get("result")
                found_exit_time = live_match.get("exit_time")
                found_exit_price = live_match.get("exit_price")
            else:
                bt_match = next((t for t in bt_trades if abs(t["time"] - target) < e_interval_sec), None)
                if bt_match:
                    found_sig = {"time": bt_match["time"], "direction": bt_match["direction"],
                                  "entry": bt_match["entry"], "sl": bt_match["sl"], "tp": bt_match["tp"],
                                  "level": bt_match["level"], "level_type": bt_match["level_type"],
                                  "opposite_level": bt_match.get("opposite_level")}
                    found_result = bt_match.get("result")
                    found_exit_time = bt_match.get("exit_time")
                    if found_result == "WIN":
                        found_exit_price = bt_match["tp"]
                    elif found_result == "LOSS":
                        found_exit_price = bt_match["sl"]

        anchor = float(sig_time) if sig_time else now
        e_interval_sec = INTERVAL_SECONDS.get(MSNR_ENTRY_TF, 900)
        s_interval_sec = INTERVAL_SECONDS.get(MSNR_STRUCTURE_TF, 3600)
        entry_end = min(now, anchor + 60 * e_interval_sec)
        entry_start = anchor - 220 * e_interval_sec
        structure_start = anchor - 260 * s_interval_sec
        structure_end = min(now, anchor + 60 * e_interval_sec)
        entry_candles = get_candles_range(symbol, MSNR_ENTRY_TF, entry_start, entry_end)

        if found_sig:
            structure_candles = get_candles_range(symbol, MSNR_STRUCTURE_TF, structure_start, structure_end)
            params = msnr_symbol_params(symbol)
            _sigs, pivots = msnr_detect_signals(structure_candles, entry_candles, **params)
            window_start = entry_candles[0]["time"] if entry_candles else structure_start
            visible_pivots = [p for p in pivots if p["confirm_time"] >= window_start - 30 * s_interval_sec]
            return jsonify({
                "symbol": symbol, "candles": entry_candles, "pivots": visible_pivots,
                "signal": found_sig, "result": found_result, "exit_time": found_exit_time,
                "exit_price": found_exit_price, "chart_source": "msnr",
            })

        # Fallback: no stored signal/trade matched `time` (or none was
        # given at all) — browse the CURRENT live Storyline instead,
        # same behavior this endpoint always had for that case.
        params = msnr_symbol_params(symbol)
        structure_candles = get_candles_range(symbol, MSNR_STRUCTURE_TF, structure_start, structure_end)
        sigs, pivots = msnr_detect_signals(structure_candles, entry_candles, **params)
        sig = None
        if sig_time:
            target = float(sig_time)
            sig = next((s for s in sigs if abs(s["time"] - target) < e_interval_sec), None)
        elif sigs:
            sig = sigs[-1]
        result = None
        exit_time = None
        exit_price = None
        if sig:
            result, exit_time = msnr_track_outcome(entry_candles, sig)
            if result == "WIN":
                exit_price = sig["tp"]
            elif result == "LOSS":
                exit_price = sig["sl"]
        # Only pivots confirmed within the returned entry-candle window are
        # worth drawing — older ones would just be off-screen level clutter.
        window_start = entry_candles[0]["time"] if entry_candles else structure_start
        visible_pivots = [p for p in pivots if p["confirm_time"] >= window_start - 30 * s_interval_sec]
        return jsonify({
            "symbol": symbol, "candles": entry_candles, "pivots": visible_pivots,
            "signal": sig, "result": result, "exit_time": exit_time, "exit_price": exit_price,
            "chart_source": "msnr",
        })
    except Exception as e:
        log_error(f"api_msnr_chart {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset/msnr", methods=["POST"])
def api_reset_msnr():
    try:
        with state_lock:
            STATE["msnr_backtest_results"] = {}
            STATE["msnr_backtest_results_raw"] = {}
            STATE["msnr_backtest_summary"] = {}
            STATE["msnr_symbol_overrides"] = {}
            STATE["msnr_live_universe"] = []  # v0.99.18: stale derived data, same reasoning as clearing overrides above — msnr_live_loop() falls back to MSNR_SYMBOLS (gold) until the next backtest cycle repopulates it
            STATE["msnr_last_backtest_finished"] = None
            STATE["msnr_last_backtest_duration"] = None
            STATE["msnr_signals"].clear()
        # v0.99.40 — per direct user report ("жму очистить msnr и заново
        # бэктэст не запускается, час ждать что-ли"): wakes msnr_
        # backtest_loop() immediately instead of leaving it asleep for
        # up to MSNR_REFRESH_SEC (1h default) — see MSNR_BACKTEST_
        # TRIGGER's own docstring. Clearing the display without also
        # kicking off a fresh cycle was the actual bug; this makes
        # "Очистить MSNR" mean "clear AND re-run now", matching what the
        # button visibly implies.
        MSNR_BACKTEST_TRIGGER.set()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_msnr: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ft5/status")
def api_ft5_status():
    """EXPERIMENTAL — port of freqtrade-strategies' Strategy005, see
    that module's own header comment for the full source-skepticism
    reasoning."""
    with state_lock:
        overrides = dict(STATE["ft5_symbol_overrides"])
        universe = list(STATE["ft5_universe"])
        live_universe = list(STATE["ft5_live_universe"])
        symbols_done = STATE["ft5_symbols_done"]
        last_backtest_finished = STATE["ft5_last_backtest_finished"]
        last_backtest_duration = STATE["ft5_last_backtest_duration"]
    ranked = [dict(v, symbol=sym) for sym, v in overrides.items() if v and not v.get("error")]
    ranked.sort(key=lambda r: (r.get("score") or -999), reverse=True)
    return jsonify({
        "enabled": FT5_ENABLED,
        "universe_size": len(universe),
        "live_universe": live_universe,
        "live_top_n": FT5_LIVE_TOP_N,
        "symbols_done": symbols_done,
        "last_backtest_finished": last_backtest_finished,
        "last_backtest_duration": last_backtest_duration,
        "signals_stats": compute_ft5_signal_stats(),
        "config": {
            "tf": FT5_TF, "stoploss_pct": FT5_STOPLOSS_PCT,
            "roi_ladder": FT5_ROI_LADDER, "backtest_days": FT5_BACKTEST_DAYS,
            "grid_buy_rsi": FT5_PARAM_GRID_BUY_RSI, "grid_buy_fisher": FT5_PARAM_GRID_BUY_FISHER,
            "grid_sell_rsi": FT5_PARAM_GRID_SELL_RSI, "invert_signals": FT5_INVERT_SIGNALS,
            "htf_filter_enabled": FT5_HTF_FILTER_ENABLED, "htf_interval": FT5_HTF_INTERVAL,
            "session_filter_enabled": FT5_SESSION_FILTER_ENABLED,
        },
        "top": ranked,
    })


@app.route("/api/ft5/signals")
def api_ft5_signals():
    with state_lock:
        return jsonify(list(STATE["ft5_signals"]))


@app.route("/api/ft5/chart/<symbol>")
def api_ft5_chart(symbol):
    """Re-derives a specific FT5 trade by re-running ft5_run_backtest()
    on an appropriate window with that trade's OWN recorded params —
    deterministic, so it reproduces the identical entry, same principle
    update_ft5_signal_outcomes() already uses. entry_time identifies
    which trade (a symbol can have many over time, same reasoning
    api_session_chart uses session_open to disambiguate)."""
    try:
        entry_time = float(request.args.get("entry_time"))
        with state_lock:
            sig = next((s for s in STATE["ft5_signals"]
                        if s["symbol"] == symbol and s["entry_time"] == entry_time), None)
        if sig is None:
            return jsonify({"error": "signal not found"}), 404
        interval_sec = INTERVAL_SECONDS.get(FT5_TF, 300)
        warmup_bars = max(FT5_SMA_PERIOD, FT5_VOLUME_AVG_PERIOD) + 100
        fetch_start = entry_time - warmup_bars * interval_sec
        fetch_end = sig["exit_time"] + 6 * 3600 if sig.get("exit_time") else time.time()
        candles = get_candles_range(symbol, FT5_TF, fetch_start, fetch_end)
        trades, open_position = ft5_run_backtest(
            candles, buy_rsi=sig["buy_rsi"], buy_fisher=sig["buy_fisher"], sell_rsi=sig["sell_rsi"])
        matched = next((t for t in trades if t["entry_time"] == entry_time), None)
        direction = sig.get("direction", "LONG")
        sl_price = sig["entry"] * (1 + FT5_STOPLOSS_PCT) if direction == "SHORT" else sig["entry"] * (1 - FT5_STOPLOSS_PCT)
        return jsonify({
            "symbol": symbol, "candles": candles, "entry_time": entry_time,
            "entry": sig["entry"], "sl": sl_price, "direction": direction,
            "result": sig.get("result"), "exit_time": sig.get("exit_time"),
            "exit_price": sig.get("exit_price"), "exit_reason": sig.get("exit_reason"),
            "pnl_pct": sig.get("pnl_pct"), "rr": sig.get("rr"),
            "matched_trade": matched,
        })
    except Exception as e:
        log_error(f"api_ft5_chart {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset/ft5", methods=["POST"])
def api_reset_ft5():
    try:
        with state_lock:
            STATE["ft5_universe"] = []
            STATE["ft5_symbol_overrides"] = {}
            STATE["ft5_symbols_done"] = 0
            STATE["ft5_last_backtest_finished"] = None
            STATE["ft5_last_backtest_duration"] = None
            STATE["ft5_signals"].clear()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_ft5: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/scalp/chart/<symbol>")
def api_scalp_chart(symbol):
    """Same response shape as api_vgi_chart (entry/sl/tp/rr/exit/candles)
    per direct user request to add graphical display for Scalp signals
    — Scalp's own record shape (fixed entry/target_price/sl_price) is
    structurally identical to VGI's, so the frontend reuses the same
    chart modal (openVgiChart/drawVgiChart) via an endpoint parameter
    rather than duplicating ~90 lines of canvas drawing code, matching
    the reuse-when-genuinely-identical judgment call already applied to
    Session NY's chart in v0.94.0. interval is required in addition to
    time to disambiguate — a symbol can have open scalp signals on
    multiple timeframes (SCALP_INTERVALS) at once, unlike VGI/FT5 which
    only ever run one timeframe."""
    try:
        interval = request.args.get("interval", "")
        sig_time = float(request.args.get("time"))
        with state_lock:
            sig = next((s for s in STATE["scalp_signals"]
                        if s["symbol"] == symbol and s["interval"] == interval and s["time"] == sig_time), None)
        if sig is None:
            return jsonify({"error": "signal not found"}), 404
        interval_sec = INTERVAL_SECONDS.get(interval, 300)
        lookback_bars = 150
        fetch_start = sig_time - lookback_bars * interval_sec
        fetch_end = (sig["exit_time"] + 6 * interval_sec) if sig.get("exit_time") else time.time()
        candles = get_candles_range(symbol, interval, fetch_start, fetch_end)
        rr = round(sig["target_pct"] / sig["sl_pct"], 3) if sig.get("sl_pct") else None
        return jsonify({
            "symbol": symbol, "candles": candles[-150:], "time": sig_time,
            "direction": sig["direction"], "entry": sig["entry"],
            "tp": sig["target_price"], "sl": sig["sl_price"],
            "result": sig.get("result"), "exit_time": sig.get("exit_time"), "exit_price": sig.get("exit_price"),
            "rr": rr,
            "chart_source": "scalp",
        })
    except Exception as e:
        log_error(f"api_scalp_chart {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset/risk_autotune", methods=["POST"])
def api_reset_risk_autotune():
    """Resets every parameter risk_autotune_pass() touches back to its
    own code-level default (the fallback value in each constant's own
    os.environ.get(...) call — hardcoded here as literals since by the
    time this runs the live globals may already be tuned away from
    them, which is exactly the state this button exists to undo), and
    clears the tuning log + every cooldown timestamp so the very next
    pass re-evaluates fresh rather than slowly re-converging from
    wherever settings.json happened to be.
    Concrete motivation, not just a "just in case": this exact scenario
    already happened earlier this session — the v0.95.3/v0.95.4/v0.95.6
    fixes all corrected a tuning FORMULA after bad values had already
    been computed and persisted by the old, buggy one. Without this
    button those stale values would only limp back toward correct over
    several more cooldown-gated passes (6-24h apart) instead of
    restarting clean immediately after a fix like that."""
    try:
        _set_scalp_min_rr(0.5)
        _set_scalp_sl_buffer_mult(0.25)
        _set_ft5_invert(False)
        _set_msnr_max_rr(8.0)
        with state_lock:
            STATE["risk_autotune_log"].clear()
            STATE["risk_autotune_last_change"] = {}
        save_state()
        return jsonify({"ok": True})
    except Exception as e:
        log_error(f"api_reset_risk_autotune: {e}")
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
            "scalp": AUTOTRADE_ENABLED_SCALP,
            "ft5": AUTOTRADE_ENABLED_FT5,
            "msnr": AUTOTRADE_ENABLED_MSNR,
            "mirror": AUTOTRADE_ENABLED_MIRROR,
            "lsw": AUTOTRADE_ENABLED_LSW,
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


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Wipe everything — both volume-profile and divergence state. Kept
    for backward compatibility; the header now has two separate buttons
    that call the scoped endpoints above instead."""
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
  #resetVolumeBtn, #resetScalpBtn, #resetMsnrBtn, #resetFt5Btn, #resetMirrorBtn, #resetRiskAutotuneBtn, #resetSimulatorBtn { background:#3a1e22; border:none; color:#ff9b9b; padding:6px 12px; border-radius:8px; font-size:12px; white-space:nowrap; }
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
  #msnrModal { position:fixed; inset:0; background:#05070c; display:none; z-index:999; }
  #msnrModal.open { display:flex; flex-direction:column; }
  #msnrModalHeader { padding:12px; display:flex; justify-content:space-between; align-items:flex-start; }
  #msnrModalHeader h2 { font-size:15px; margin:0; }
  #msnrCloseBtn { background:#1e2a3f; border:none; color:#fff; padding:6px 12px; border-radius:8px; font-size:13px; }
  #msnrChartWrap { flex:1; overflow:hidden; padding:0 8px 8px; }
  #ft5Modal { position:fixed; inset:0; background:#05070c; display:none; z-index:999; }
  #ft5Modal.open { display:flex; flex-direction:column; }
  #ft5ModalHeader { padding:12px; display:flex; justify-content:space-between; align-items:flex-start; }
  #ft5ModalHeader h2 { font-size:15px; margin:0; }
  #ft5CloseBtn { background:#1e2a3f; border:none; color:#fff; padding:6px 12px; border-radius:8px; font-size:13px; }
  #ft5ChartWrap { flex:1; overflow:hidden; padding:0 8px 8px; }
  #vgiModal { position:fixed; inset:0; background:#05070c; display:none; z-index:999; }
  #vgiModal.open { display:flex; flex-direction:column; }
  #vgiModalHeader { padding:12px; display:flex; justify-content:space-between; align-items:flex-start; }
  #vgiModalHeader h2 { font-size:15px; margin:0; }
  #vgiCloseBtn { background:#1e2a3f; border:none; color:#fff; padding:6px 12px; border-radius:8px; font-size:13px; }
  #vgiChartWrap { flex:1; overflow:hidden; padding:0 8px 8px; }
  .dim { color:#8b98ab; }
  .empty { padding:30px 14px; text-align:center; color:#6b7688; font-size:13px; }

  /* Mobile layout, v0.89.0 — per direct user request after a live
     screenshot showed the header button row wrapping across ~4 lines
     (eating most of the visible screen before any actual data) and the
     12-column tables (EMA's, worst case) rendering all columns crushed
     into unreadable widths on a narrow phone viewport.
     v0.99.31: this rule used to put `display:block; overflow-x:auto`
     directly ON every <table> element itself, applying to any table on
     the page — present now or injected later — without needing to
     touch each render function. That worked fine for the 4 tables that
     had NO other scroll container of their own (the 3 static signals/
     div/ema tables, and loadMsnrTrades()'s per-trade table), but every
     OTHER dynamically-built table (MSNR backtest, session, ft5, vgi,
     etc — 17 of them, all already wrapped in their own `<div style=
     "overflow-x:auto;">`) ended up with TWO independent horizontal
     scroll containers nested inside each other: the div wrapper AND
     the table itself. Per direct user report ("шапка относительно
     таблицы съезжает" — the header sliding out of sync with the body
     as you scroll): that double-nesting is exactly what broke it —
     v0.99.30's `position:sticky` sticks relative to whichever scroll
     container is NEAREST, and with two nested ones per table, which
     one actually ends up "nearest" (and therefore what the sticky
     column sticks against) can end up being the WRONG one relative to
     where the visible scroll offset actually lives, and `display:block`
     on <table> also breaks the browser's native guarantee that thead
     and tbody share one column grid (each can end up auto-sizing
     independently), which is its own separate source of drift.
     Fixed at the root instead of patching around it: <table> no longer
     overrides its own display or becomes its own scroll container at
     all (keeps native `display:table`, so thead/tbody column widths
     stay a single shared grid, and sticky has exactly ONE scroll
     ancestor to resolve against, never two) — ALL scrolling now goes
     through the div wrapper alone. Added a wrapper to the 4 tables
     that didn't have one (signals/div/ema tables in the static HTML
     skeleton, and loadMsnrTrades()'s per-trade table) instead of
     relying on the table-level rule for them specifically. The
     `div[style*="overflow-x:auto"]` selector below (an attribute
     substring match, not a class) reaches every existing wrapper div
     without needing to touch 17+ render functions just to add a
     shared class name to each one's already-consistent inline style. */
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
    table { white-space:nowrap; }
    div[style*="overflow-x:auto"] { -webkit-overflow-scrolling:touch; max-width:100%; }
    /* v0.99.28, per direct user request after a live portrait-mode
       screenshot of the MSNR backtest table: cells were still padded/
       sized for a desktop-width table, wasting horizontal space that
       matters far more on a narrow phone than the extra tap-target
       size does — shrunk from the original 6px 8px / 12px (already a
       reduction from the 8px 10px / 13px desktop default) to fit
       meaningfully more columns before horizontal scroll kicks in.
       Applies to every table on the page (same "one CSS-only rule,
       works for both static and dynamically-injected tables" reasoning
       v0.89.0 already established above) — the dense multi-column
       backtest tables (MSNR/FT5/VGI/session/etc, all built the same
       way) are the ones that actually needed it, but a uniformly
       tighter mobile table is a reasonable default everywhere, not
       just there. */
    th, td { padding:4px 4px; font-size:10.5px; }
    /* v0.99.62, per direct user report (Huawei MatePad 12.2, landscape
       — "все не влазит, надо скролить, немного буквально"): horizontal
       cell padding trimmed 6px -> 4px per side (vertical unchanged) —
       a small, uniform width saving across every column of every table
       this same global rule already covers, rather than touching any
       one table's own layout specifically. */
    /* v0.99.30, per direct user request ("давай закрепим"): pin the
       first column (Symbol, in every one of these tables) so it stays
       visible while swiping through the rest — now that v0.99.29 fixed
       scroll position actually surviving a refresh, sitting on a
       stable horizontal scroll for a few seconds without knowing which
       ROW you're looking at was the next obvious friction point.
       position:sticky sticks relative to the nearest scrolling
       ancestor — v0.99.31 made that ALWAYS the div wrapper now (never
       the table itself), so there's exactly one unambiguous scroll
       container per table for this to resolve against. Needs an
       explicit background (not "transparent", the actual body
       background color) since a sticky cell that's otherwise
       transparent lets every OTHER column's text scroll visibly
       underneath it instead of being hidden by it — defeats the
       purpose. Scoped to mobile only: on desktop these tables
       generally fit without horizontal scroll in the first place, so
       there's nothing to pin against. */
    th:first-child, td:first-child { position:sticky; left:0; z-index:2; background:#0b0e14; }
    tr:active td:first-child { background:#182036; }
    /* v0.99.49, per direct user request ("галочку как и имя монеты
       сделай фиксированным при скролле"): pin the SECOND column too,
       but only for the MSNR backtest table (.msnr-bt-table) — its
       2nd column is the autotrade checkbox, which is exactly what
       needs to stay visible alongside the pinned Symbol name while
       swiping through the rest of that specific table's many columns.
       Not applied globally like the first-column rule above: other
       tables' 2nd column varies a lot in width (Dir/Reason/etc), and
       forcing a second sticky column everywhere would need a matching
       fixed width for column 1 in EVERY table to avoid column 2
       overlapping it — only .msnr-bt-table's first column (short
       ticker symbols) is narrow and predictable enough to give a safe
       fixed width to. */
    .msnr-bt-table th:first-child, .msnr-bt-table td:first-child { width:92px; min-width:92px; max-width:92px; overflow:hidden; text-overflow:ellipsis; }
    .msnr-bt-table th:nth-child(2), .msnr-bt-table td:nth-child(2) { position:sticky; left:92px; z-index:2; background:#0b0e14; }
    .msnr-bt-table tr:active td:nth-child(2) { background:#182036; }
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
      <button id="resetScalpBtn">Очистить скальпинг</button>
      <button id="resetMsnrBtn">Очистить MSNR</button>
      <button id="resetFt5Btn">Очистить FT5</button>
      <button id="resetMirrorBtn">Очистить Зеркало</button>
      <button id="resetLswBtn">Очистить Sweep</button>
      <button id="resetSimulatorBtn">Сбросить симулятор</button>
      <button id="resetRiskAutotuneBtn">Сбросить авто-тюнинг</button>
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
  <div class="tab active" data-tab="msnr">MSNR</div>
  <div class="tab" data-tab="signals">Volume</div>
  <div class="tab" data-tab="scalp">Скальпинг</div>
  <div class="tab" data-tab="ft5" style="color:#e0a030;">FT5 ⚠️</div>
  <div class="tab" data-tab="mirror">Зеркало</div>
  <div class="tab" data-tab="lsw">Sweep</div>
  <div class="tab" data-tab="autotrade">Автоторговля</div>
  <div class="tab" data-tab="simulator">Симулятор</div>
</div>
<div class="panel">
  <div id="tuningPanel" style="display:none;padding:10px 4px;font-size:13px;"></div>
  <div style="overflow-x:auto;">
  <table id="signalsTable" style="display:none">
    <thead><tr><th>Symbol</th><th>Dir</th><th>Reason</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>MFE(R)</th><th>MAE(R)</th><th>Status</th><th>Time</th></tr></thead>
    <tbody></tbody>
  </table>
  </div>
  <div id="scalpPanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
  <div id="msnrPanel" style="display:block;padding:8px 4px;font-size:12px;"></div>
  <div id="ft5Panel" style="display:none;padding:8px 4px;font-size:12px;"></div>
  <div id="mirrorPanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
  <div id="lswPanel" style="display:none;padding:8px 4px;font-size:12px;"></div>
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

<div id="msnrModal">
  <div id="msnrModalHeader">
    <div>
      <h2 id="msnrModalTitle">-</h2>
      <div id="msnrModalParams" class="dim" style="font-size:11px;margin-top:2px;"></div>
    </div>
    <button id="msnrCloseBtn">Закрыть</button>
  </div>
  <div id="msnrChartWrap"><canvas id="msnrChartCanvas"></canvas></div>
</div>

<div id="ft5Modal">
  <div id="ft5ModalHeader">
    <div>
      <h2 id="ft5ModalTitle">-</h2>
      <div id="ft5ModalParams" class="dim" style="font-size:11px;margin-top:2px;"></div>
    </div>
    <button id="ft5CloseBtn">Закрыть</button>
  </div>
  <div id="ft5ChartWrap"><canvas id="ft5ChartCanvas"></canvas></div>
</div>

<div id="vgiModal">
  <div id="vgiModalHeader">
    <div>
      <h2 id="vgiModalTitle">-</h2>
      <div id="vgiModalParams" class="dim" style="font-size:11px;margin-top:2px;"></div>
    </div>
    <button id="vgiCloseBtn">Закрыть</button>
  </div>
  <div id="vgiChartWrap"><canvas id="vgiChartCanvas"></canvas></div>
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
      <div class="settingsGroupTitle" style="color:#e0a030;">MSNR ⚠️ Экспериментально</div>
      <div class="settingRow">
        <div>
          <div class="label">Сканирование (только золото)</div>
          <div class="sub">Malaysian SNR / Storyline — см. предупреждение на вкладке. Автоторговля выключена по умолчанию.</div>
        </div>
        <label class="switch"><input type="checkbox" id="setMsnr"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Добор (add-on) <span style="color:#e0a030;">⚠️ реальный ордер</span></div>
          <div class="sub">вторая доливка к уже открытой позиции при свежем QM на M30 по тому же уровню (h1/m30 SBR &gt; m1 QM + m30 добір). На Gate это сливается в одну позицию с усреднённой ценой — итоговый стоп берётся более консервативный (дальше от цены) из старого и нового</div>
        </div>
        <label class="switch"><input type="checkbox" id="setMsnrAddon"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Минимальный RR (глобальный)</div>
          <div class="sub">единый порог 1:2 для всех монет одинаково — не подбирается индивидуально под каждую (в отличие от остальных фильтров выше), поэтому результат честнее проверяет саму идею, а не удачную подгонку под конкретную монету</div>
        </div>
        <label class="switch"><input type="checkbox" id="setMsnrMinRrFilter"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Фильтр по тренду (4ч, глобальный)</div>
          <div class="sub">LONG только если тренд на 4ч вверх/нейтральный, SHORT только если вниз/нейтральный — та же логика, что у Sweep, единая для всех монет</div>
        </div>
        <label class="switch"><input type="checkbox" id="setMsnrHtfFilter"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="settingsGroup">
      <div class="settingsGroupTitle" style="color:#e0a030;">FT5 ⚠️ Экспериментально</div>
      <div class="settingRow">
        <div>
          <div class="label">Сканирование</div>
          <div class="sub">порт Strategy005 (freqtrade) — свой перебор параметров на реальных данных, сигналы информационные (не подключены к автоторговле)</div>
        </div>
        <label class="switch"><input type="checkbox" id="setFt5"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Реверс сигналов</div>
          <div class="sub">та же точка входа, но SHORT вместо LONG — выход только по стопу/лесенке (сигнальный выход не зеркалится, см. вкладку)</div>
        </div>
        <label class="switch"><input type="checkbox" id="setFt5Invert"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Фильтр по тренду (4ч, глобальный)</div>
          <div class="sub">LONG только если тренд на 4ч вверх/нейтральный, SHORT только если вниз/нейтральный — единый для всех монет, как у Sweep/MSNR/Зеркала</div>
        </div>
        <label class="switch"><input type="checkbox" id="setFt5HtfFilter"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Фильтр по сессии (глобальный)</div>
          <div class="sub">торговать только в часы 07:00–21:00 UTC — вне этого окна сигналы пропускаются как "мёртвая" сессия</div>
        </div>
        <label class="switch"><input type="checkbox" id="setFt5SessionFilter"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="settingsGroup">
      <div class="settingsGroupTitle">Зеркало</div>
      <div class="settingRow">
        <div>
          <div class="label">Сканирование</div>
          <div class="sub">"зеркальный уровень" — пробитая поддержка/сопротивление меняет роль при возврате цены; вход на паттерне разворота (внутренний бар/пинцет/рельсы/поглощение на дожи)</div>
        </div>
        <label class="switch"><input type="checkbox" id="setMirror"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ RR (тейк-профит)</div>
          <div class="sub">фиксированное соотношение тейк:стоп от найденного стопа паттерна</div>
        </div>
        <input type="number" id="setMirrorRR" min="0.5" max="20" step="0.5" style="width:60px;background:#0d1220;border:1px solid #1c2433;color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;">
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Автотюнинг допусков</div>
          <div class="sub">подбирает допуск касания и допуск паттерна отдельно для каждой монеты — только если комбинация проходит проверку на ДВУХ независимых кусках истории (сначала подбор на первых 70% данных, потом обязательная проверка на отложенных последних 30%, которые в подборе не участвовали). Если ни одна комбинация не прошла обе проверки — монета торгуется с обычными общими допусками</div>
        </div>
        <label class="switch"><input type="checkbox" id="setMirrorAutotuneTolerance"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Фильтр по объёму (глобальный)</div>
          <div class="sub">единый порог 1.5× среднего объёма для всех монет — свеча паттерна должна показать реальное участие толпы, а не быть тихим фитилём</div>
        </div>
        <label class="switch"><input type="checkbox" id="setMirrorVolumeFilter"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Фильтр по тренду (4ч, глобальный)</div>
          <div class="sub">LONG только если тренд на 4ч вверх/нейтральный, SHORT только если вниз/нейтральный — единый для всех монет, как у Sweep и MSNR</div>
        </div>
        <label class="switch"><input type="checkbox" id="setMirrorHtfFilter"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="settingsGroup">
      <div class="settingsGroupTitle">Sweep (Liquidity Sweep)</div>
      <div class="settingRow">
        <div>
          <div class="label">Сканирование</div>
          <div class="sub">снятие ликвидности с равных хаёв/лоу (2+ близких свинга) — вход на развороте после того, как фитиль пробил уровень, а закрытие вернулось обратно. Автоторговля включается отдельным переключателем ниже (группа «Автоторговля»)</div>
        </div>
        <label class="switch"><input type="checkbox" id="setLsw"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ RR (тейк-профит)</div>
          <div class="sub">фиксированное соотношение тейк:стоп от стопа за экстремумом свипа</div>
        </div>
        <input type="number" id="setLswRR" min="0.5" max="20" step="0.5" style="width:60px;background:#0d1220;border:1px solid #1c2433;color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;">
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Фильтр по тренду (4ч)</div>
          <div class="sub">снятие равных лоу → LONG только если тренд на 4ч вверх/нейтральный; снятие равных хаёв → SHORT только если вниз/нейтральный. Отсекает сделки против старшего тренда</div>
        </div>
        <label class="switch"><input type="checkbox" id="setLswHtfFilter"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Структурный кэп</div>
          <div class="sub">не входить LONG выше последнего значимого структурного максимума / SHORT ниже структурного минимума — не гнаться за ценой, когда некуда бежать</div>
        </div>
        <label class="switch"><input type="checkbox" id="setLswStructuralCap"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Подтверждение входа (5м)</div>
          <div class="sub">вход не сразу по закрытию часовой свечи снятия, а только после подтверждения на 5м: слом структуры (BOS), поглощение или мини-снятие (инверсия) в течение часа. Если подтверждения нет — сделка не открывается</div>
        </div>
        <label class="switch"><input type="checkbox" id="setLswEntryConfirm"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Фильтр по объёму</div>
          <div class="sub">свеча снятия должна показать объём минимум в 1.5× выше среднего за предыдущие 20 баров — отсекает низкообъёмные фитили без реального участия толпы (не настоящий каскад стопов)</div>
        </div>
        <label class="switch"><input type="checkbox" id="setLswVolumeFilter"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Фильтр по FVG</div>
          <div class="sub">свеча снятия должна оставить за собой ценовой разрыв (fair value gap) — знак, что движение было достаточно резким, а не просто фитиль без импульса</div>
        </div>
        <label class="switch"><input type="checkbox" id="setLswFvgFilter"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Фильтр по сессии</div>
          <div class="sub">торговать только в часы 07:00–21:00 UTC (примерно пересечение европейской и американской сессий) — вне этого окна сигналы пропускаются как "мёртвая" сессия</div>
        </div>
        <label class="switch"><input type="checkbox" id="setLswSessionFilter"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Минимум касаний уровня</div>
          <div class="sub">торговать только уровни с 3+ касаниями вместо базовых 2 — больше касаний, по опыту, повышают шанс на реальное снятие ликвидности</div>
        </div>
        <label class="switch"><input type="checkbox" id="setLswMinTouches"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Структура свечи снятия</div>
          <div class="sub">фитиль свечи снятия должен быть минимум в 2× длиннее тела И покрывать не менее 30% полного диапазона hi-lo — настоящее снятие: большой фитиль (резкий отскок) + маленькое тело (закрылась внутри уровня). Большое тело — это уже импульс, а не снятие</div>
        </div>
        <label class="switch"><input type="checkbox" id="setLswCandleStructureFilter"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Фильтр по направлению</div>
          <div class="sub">⚠️ мягкий подгон под прошлые данные — риск переоценить случайную разницу на малой выборке. Тот же порог винрейта, что и у общего допуска, применяется к LONG и SHORT каждой монеты отдельно; если сторона не набрала нужный винрейт и объём сделок — она не торгуется живьём (не выбор "победившей" стороны задним числом, а единый порог для всех)</div>
        </div>
        <label class="switch"><input type="checkbox" id="setLswDirectionFilter"><span class="switchSlider"></span></label>
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
          <div class="label">↳ Алерты MSNR</div>
          <div class="sub">живые QM-сигналы по золоту</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegramMsnr"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Алерты FT5 ⚠️</div>
          <div class="sub">экспериментально — открытие и закрытие сигналов</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegramFt5"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Алерты Зеркала</div>
          <div class="sub">открытие и закрытие сигналов</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegramMirror"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Алерты Sweep</div>
          <div class="sub">открытие и закрытие сигналов</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegramLsw"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Нестабильность сети</div>
          <div class="sub">разово, когда за 10 минут накопилось 5+ сетевых ошибок (Read timed out / ConnectionError) — не про открытые позиции, только про сбор данных</div>
        </div>
        <label class="switch"><input type="checkbox" id="setTelegramNetwork"><span class="switchSlider"></span></label>
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
          <div class="label">Риск на сделку</div>
          <div class="sub">% от общего баланса счёта, который теряется при срабатывании стопа — общий для всех модулей с реальной автоторговлей (MSNR, Зеркало, Sweep, Скальпинг). Плечо на каждую сделку подбирается автоматически под этот риск и стоп конкретного сигнала</div>
        </div>
        <input type="number" id="setAutotradeRiskPct" min="0.1" max="50" step="0.5" style="width:60px;background:#0d1220;border:1px solid #1c2433;color:#fff;padding:6px 8px;border-radius:6px;font-size:12px;">
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Bounce</div>
        </div>
        <label class="switch"><input type="checkbox" id="setAutotradeBounce"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Breakout</div>
        </div>
        <label class="switch"><input type="checkbox" id="setAutotradeBreakout"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Скальпинг</div>
        </div>
        <label class="switch"><input type="checkbox" id="setAutotradeScalp"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳↳ Мартингейл после стопа ⚠️</div>
          <div class="sub">после стопа следующая сделка по ТОЙ ЖЕ монете риском ×2, снова стоп — ×4, ×8 (потолок, дальше не растёт) — победа сбрасывает обратно к базовому риску. Реальный риск потери денег растёт экспоненциально при серии стопов подряд</div>
        </div>
        <label class="switch"><input type="checkbox" id="setScalpMartingaleEnabled"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ MSNR ⚠️</div>
          <div class="sub">общий рубильник поверх переключателей по каждой монете (вкладка MSNR, колонка «Авто») — выключен здесь, значит не торгует НИКТО, даже если у монеты своя галочка стоит</div>
        </div>
        <label class="switch"><input type="checkbox" id="setAutotradeMsnr"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Зеркало</div>
        </div>
        <label class="switch"><input type="checkbox" id="setAutotradeMirror"><span class="switchSlider"></span></label>
      </div>
      <div class="settingRow">
        <div>
          <div class="label">↳ Sweep</div>
          <div class="sub">риск 2% от баланса на сделку, тот же автоматический расчёт плеча/размера позиции, что и у остальных режимов</div>
        </div>
        <label class="switch"><input type="checkbox" id="setAutotradeLsw"><span class="switchSlider"></span></label>
      </div>
    </div>

    <div class="dim" style="font-size:12px;margin-top:16px;">Изменения применяются сразу, без перезапуска, и сохраняются на диск. Здесь только общие переключатели — детальные параметры (RR, буферы, пороги фильтров) настраиваются через переменные окружения при запуске.</div>
  </div>
</div>

<script>
const fmt = (n, d=6) => n === null || n === undefined ? '-' : Number(n).toPrecision(d).replace(/\\.?0+$/,'').replace(/\\.$/, '');
const fmtTime = (t) => t ? new Date(t*1000).toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'}) : '-';
const fmtDateTime = (t) => t ? new Date(t*1000).toLocaleString('ru-RU', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}) : '-';  // date+time, not just time — Session's own open time is the SAME 10:00 every day by design, so time-only gives no way to tell which day's session a row belongs to

let activeTab = 'msnr';
document.querySelectorAll('.tab').forEach(el => {
  el.onclick = () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    activeTab = el.dataset.tab;
    document.getElementById('signalsTable').style.display = activeTab === 'signals' ? 'table' : 'none';
    document.getElementById('tuningPanel').style.display = activeTab === 'signals' ? 'block' : 'none';
    document.getElementById('scalpPanel').style.display = activeTab === 'scalp' ? 'block' : 'none';
    document.getElementById('msnrPanel').style.display = activeTab === 'msnr' ? 'block' : 'none';
    document.getElementById('ft5Panel').style.display = activeTab === 'ft5' ? 'block' : 'none';
    document.getElementById('mirrorPanel').style.display = activeTab === 'mirror' ? 'block' : 'none';
    document.getElementById('lswPanel').style.display = activeTab === 'lsw' ? 'block' : 'none';
    document.getElementById('autotradePanel').style.display = activeTab === 'autotrade' ? 'block' : 'none';
    document.getElementById('simulatorPanel').style.display = activeTab === 'simulator' ? 'block' : 'none';
    if (activeTab === 'signals') refreshTuning();
    if (activeTab === 'scalp') refreshScalp();
    if (activeTab === 'msnr') refreshMsnr();
    if (activeTab === 'ft5') refreshFt5();
    if (activeTab === 'mirror') refreshMirror();
    if (activeTab === 'lsw') refreshLsw();
    if (activeTab === 'autotrade') refreshAutotrade();
    if (activeTab === 'simulator') refreshSimulator();
  };
});

// v0.99.29, per direct user report: swiping right on a wide table (the
// MSNR backtest table, in this case) kept snapping back to the left
// every refresh cycle — because every refresh* function below rebuilds
// its ENTIRE panel via `panel.innerHTML = ...`, which tears down and
// recreates every DOM element inside it, discarding whatever scrollLeft
// the person had mid-swipe. Every module panel (session/session_ny/
// xau_lg/msnr/ft5/vgi/autotrade/simulator) rebuilds the exact same way
// on the same refreshAll() timer, so this wasn't an MSNR-only bug —
// grepped every `panel.innerHTML =` call site and applied the same fix
// at each one that can contain a scrollable table (refreshDivergence
// and refreshEma were checked and excluded: their panels are plain
// stat divs, no <table> at all, nothing to preserve).
// Positional matching (the Nth scrollable element before the rebuild
// gets its scrollLeft restored onto the Nth scrollable element after)
// rather than any kind of ID-based matching: the HTML is rebuilt from
// scratch every cycle with no stable element ids to match against, but
// which tables appear and in what order is stable cycle-to-cycle in
// the overwhelmingly common case (same symbols, same sort order), so
// position is a reliable-enough proxy without threading ids through
// every render function in the app.
function setPanelHtml(panel, html) {
  const scrollable = el => el.scrollWidth > el.clientWidth;
  const before = Array.from(panel.querySelectorAll('*')).filter(scrollable).map(el => el.scrollLeft);
  // v0.99.51, per direct user report ("сброс видимого окна при
  // скролле и масштабировании, когда смотрю сделки и листаю список
  // монет"): also save/restore the PAGE's own vertical scroll
  // (window.scrollY) around the rebuild — v0.99.29 only preserved
  // horizontal scrollLeft inside individual tables, never how far
  // DOWN the page itself the person had scrolled. A full panel.
  // innerHTML rebuild briefly changes the document's total height
  // (an expanded coin's trade table collapses back to a "загрузка..."
  // placeholder before loadMsnrTrades() re-fetches and repopulates
  // it — see restoreMsnrExpansion()), and that height change during
  // the rebuild is exactly what makes the visible viewport appear to
  // jump even when window.scrollY itself never numerically changed:
  // the same pixel offset now points at different content until
  // layout settles back to its old shape. Explicitly restoring it
  // right after the rebuild (rather than trusting the browser to
  // leave it alone) also guards against the pinch-zoom level getting
  // reset on some mobile browsers, which tends to happen together
  // with an unexpected scroll jump on a large synchronous DOM
  // replacement like this one.
  const scrollY = window.scrollY;
  panel.innerHTML = html;
  if (before.length) {
    const after = Array.from(panel.querySelectorAll('*')).filter(scrollable);
    before.forEach((sl, i) => { if (after[i]) after[i].scrollLeft = sl; });
  }
  window.scrollTo(window.scrollX, scrollY);
}

async function refreshStatus() {
  try {
    const s = await (await fetch('/api/status')).json();
    const vpTabs = ['signals'].map(t => document.querySelector(`.tab[data-tab="${t}"]`));
    vpTabs.forEach(el => { el.style.display = s.volume_profile_enabled === false ? 'none' : ''; });
    const el = document.getElementById('status');
    const fetchErrTxt = s.excluded_fetch_error ? `, ${s.excluded_fetch_error} сетевых сбоев` : '';
    const scanTxt = s.last_scan_finished ? `скан ${s.last_scan_duration}s, ${s.universe_size} пар (искл. ${s.excluded_low_quality||0} неликвид${fetchErrTxt})` : 'сканирование...';
    el.textContent = `v${s.version} · ${scanTxt}`;
    const ra = s.risk_autotune;
    const raBox = document.getElementById('riskAutotuneBox');
    if (ra && ra.log && ra.log.length) {
      raBox.style.display = 'block';
      const paramLabels = {scalp_min_rr: 'Скальп мин.RR', scalp_sl_buffer_mult: 'Скальп SL-буфер',
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
    // v0.99.115, per broader module-removal cleanup: this function was
    // silently, completely broken — o.divergence/o.ema/o.session are
    // ALL undefined now that api_overview() only returns volume/scalp
    // (divergence/ema removed well before this session, session removed
    // in this same pass), and `if (o.divergence.enabled)` threw on the
    // very FIRST reference, right at the top, before scalp or anything
    // else ever ran. The surrounding try/catch swallowed the error every
    // single time, so the overview bar simply never updated at all — no
    // visible crash, just permanently stale/blank, since at least
    // whenever divergence/ema were removed. Now matches api_overview()'s
    // own actual current response exactly: volume and scalp only.
    if (o.volume.enabled) parts.push(`<b>Volume</b> ${wr(o.volume)} (${wl(o.volume.wins, o.volume.losses)}) ${openTxt(o.volume.open)}`);
    if (o.scalp.enabled) {
      const scalpWrClass = (o.scalp.winrate === null || o.scalp.winrate === undefined) ? 'dim' : (o.scalp.winrate >= 50 ? 'win' : 'loss');
      const scalpWr = `<span class="${scalpWrClass}">${o.scalp.winrate !== null && o.scalp.winrate !== undefined ? o.scalp.winrate+'%' : '-'}</span>`;
      parts.push(`<b>Скальп</b> ${scalpWr} (<span class="win">${o.scalp.wins}W</span>/<span class="loss">${o.scalp.losses}L</span>/<span class="status-timeout">${o.scalp.timeouts}T</span>) ${openTxt(o.scalp.open)}`);
    }
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
      <td class="dim">${r.rr !== undefined && r.rr !== null ? r.rr : '-'}</td>
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
  const wr = st.winrate !== null && st.winrate !== undefined ? `<span class="${st.winrate >= 50 ? 'win' : 'loss'}">${st.winrate}%</span>` : '<span class="dim">-</span>';
  const at = s.auto_tune || {};
  const atTxt = at.enabled
    ? `автотюнинг: ${at.tuned_symbols}/${s.universe_size} монет уже подобрано (обновление каждые ${at.refresh_hours}ч, +${at.per_cycle}/скан)`
    : 'автотюнинг выключен';
  const br = st.by_reason || {};
  // v0.99.67, per direct user report ("возле сделок я не вижу rr, я
  // не вижу средний rr по всем сделкам, я вижу просто в тексте rr2"):
  // each reason's own real avg RR (from actual closed trades, now that
  // scan_symbol()'s record finally stores "rr" — see that fix's own
  // comment) folded right into the existing bounce/breakout summary,
  // replacing the flat single "RR ${s.config.rr}" that used to sit at
  // the end of this line and never reflected the real per-symbol-
  // tuned values at all.
  const bounceRrTxt = br.bounce && br.bounce.rr ? ` · RR ${br.bounce.rr.avg}` : '';
  const breakoutRrTxt = br.breakout && br.breakout.rr ? ` · RR ${br.breakout.rr.avg}` : '';
  const bounceTxt = br.bounce && br.bounce.total ? `bounce ${br.bounce.winrate}% (${br.bounce.total})${bounceRrTxt}` : 'bounce -';
  const breakoutTxt = br.breakout && br.breakout.total ? `breakout ${br.breakout.winrate}% (${br.breakout.total})${breakoutRrTxt}` : 'breakout -';
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
      <b>Volume</b> · Винрейт: ${wr} (${st.wins||0}W / ${st.losses||0}L, timeout ${st.timeouts||0}) · ${bounceTxt} · ${breakoutTxt} · открытых: ${st.open||0}<br>
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
  const ssWr = ss.win_rate !== null && ss.win_rate !== undefined ? `<span class="${ss.win_rate >= 50 ? 'win' : 'loss'}">${ss.win_rate}%</span>` : '<span class="dim">-</span>';
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
      ~ рядом с плечом = макс. плечо биржи для монеты не подтверждено, используется дефолт ${cfg.default_max_leverage}x — проверь реальный лимит на бирже перед входом<br>
      Клик по строке живого сигнала открывает график входа/выхода.</span>
    </div>
    ${mfeMaeHtml}`;
  const signalsRows = signals.map(s => {
    const dirClass = s.direction === 'LONG' ? 'long' : 'short';
    let statusHtml;
    if (s.status === 'OPEN') statusHtml = '<span class="status-open">OPEN</span>';
    else if (s.result === 'WIN') statusHtml = `<span class="win">WIN @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else if (s.result === 'LOSS') statusHtml = `<span class="loss">LOSS @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else statusHtml = '<span class="status-timeout">TIMEOUT</span>';
    // v0.99.109, per direct user request ("нужны пометки рядом с живым
    // сигналом"): shows the Martingale multiplier this SPECIFIC signal
    // actually traded at (frozen at creation time, not a live-updating
    // value — a past signal's own badge should never change after the
    // fact as later trades on other symbols resolve). Only shown when
    // above base (1x) — a base-risk signal has nothing to flag.
    const mult = s.martingale_multiplier;
    const martingaleTag = (mult && mult > 1)
      ? ` <span class="loss" title="Мартингейл после стопа: риск ×${mult} от базового">×${mult}</span>`
      : '';
    return `<tr data-signal-symbol="${s.symbol}" data-signal-interval="${s.interval}" data-signal-time="${s.time}" style="cursor:pointer;">
      <td>${s.symbol}</td><td class="${dirClass}">${s.direction}${martingaleTag}</td><td class="dim">${s.interval}</td>
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
    setPanelHtml(panel, headerHtml + signalsTableHtml + '<div class="dim">Пока нет рекомендаций — либо ещё считается, либо ни одна монета не прошла проверку безопасности при текущих настройках.</div>');
    document.querySelectorAll('#scalpPanel tbody tr[data-signal-time]').forEach(tr => {
      tr.onclick = () => openScalpChart(tr.dataset.signalSymbol, tr.dataset.signalInterval, tr.dataset.signalTime);
    });
    return;
  }
  const rows = status.top.map((r, i) => fmtScalpRow(r, i + 1)).join('');
  setPanelHtml(panel, headerHtml + signalsTableHtml + `
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
    <div id="scalpDetail" style="margin-top:12px;"></div>`);
  document.querySelectorAll('#scalpPanel tbody tr[data-symbol]').forEach(tr => {
    tr.onclick = () => openScalpDetail(tr.dataset.symbol);
  });
  document.querySelectorAll('#scalpPanel tbody tr[data-signal-time]').forEach(tr => {
    tr.onclick = () => openScalpChart(tr.dataset.signalSymbol, tr.dataset.signalInterval, tr.dataset.signalTime);
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

// ---------------- MSNR — Malaysian SNR / Storyline gold strategy (EXPERIMENTAL, v0.99.0) ----------------
// v0.99.18: sort state for the backtest leaderboard table — lives
// OUTSIDE refreshMsnr() for the same reason _msnrExpanded does (survives
// the panel's full re-render on every auto-refresh tick). Switches to
// winrate or trades(n) on header click, per direct user request:
// "сделай сортировку по винрейту и количеству сигналов бектеста."
// v0.99.75, per direct user request ("плавное убывание в топ 10 и
// последующее продолжение убывание вне списка"): default changed from
// 'score' to null ("no column override — trust the backend's own
// order"). The backend's /api/msnr/status now already returns `top`
// pre-sorted by msnr_symbol_rank_score() (a weighted blend of winrate,
// raw_closed_n, and доход — the exact same score that decides top-10
// membership), so a client-side re-sort by a DIFFERENT single field
// (score) by default was silently undoing that continuity the moment
// the table rendered — exactly what produced the "не плавное
// убывание" the request describes. Clicking a column header still
// overrides with a single-field sort as before (see the comparator
// below) — this only changes what happens with NO click yet.
let _msnrSortKey = null;
let _msnrSortDir = -1;  // -1 = descending (best first), 1 = ascending
function msnrSortBy(key) {
  if (_msnrSortKey === key) { _msnrSortDir *= -1; } else { _msnrSortKey = key; _msnrSortDir = -1; }
  refreshMsnr();
}

async function refreshMsnr() {
  const status = await (await fetch('/api/msnr/status')).json();
  const signals = await (await fetch('/api/msnr/signals')).json();
  const panel = document.getElementById('msnrPanel');
  const cfg = status.config || {};
  const ss = status.signals_stats || {};
  const ssWr = ss.winrate !== null && ss.winrate !== undefined ? `<span class="${ss.winrate >= 50 ? 'win' : 'loss'}">${ss.winrate}%</span>` : '<span class="dim">-</span>';
  const buildTxt = status.backtest_running
    ? `бэктест выполняется: ${status.backtest_done||0}/${status.backtest_total||'?'} монет${status.backtest_started_at ? ' · идёт ' + Math.round((Date.now()/1000 - status.backtest_started_at)) + 'с' : ''}`
    : (status.last_backtest_finished
      ? `последний бэктест: ${fmtTime(status.last_backtest_finished)} (${status.last_backtest_duration}s)`
      : 'бэктест ещё не запускался');
  // v0.99.58, per direct user report ("ночью несколько часов прошло а
  // ребэктеста не было давно" — the exact scenario this session's own
  // earlier watchdog discussion predicted, at the time left unfixed
  // per direct user choice): a prominent warning when the last
  // completed cycle is much older than a normal gap between cycles
  // should ever be. Threshold is 2.5x MSNR_REFRESH_SEC (via cfg.
  // refresh_sec) with a 1h floor — generous enough that one genuinely
  // slow cycle (this app's own backtest universe grew substantially in
  // v0.99.48, dropping the old 70-symbol cap) doesn't false-positive,
  // but still catches a multi-hour stall like the one reported. This
  // is detection, not a fix — the app can't restart its own OS process
  // from inside itself, and the most likely real cause (Android
  // suspending/killing the background Termux process during idle
  // screen-off time) isn't something code here can prevent; this at
  // least makes the person SEE it happened instead of discovering it
  // by chance days later.
  const staleSec = (!status.backtest_running && status.last_backtest_finished)
    ? (Date.now()/1000 - status.last_backtest_finished) : null;
  const staleThresholdSec = Math.max(3600, (cfg.refresh_sec || 3600) * 2.5);
  const staleWarnHtml = (staleSec !== null && staleSec > staleThresholdSec) ? `
    <div style="background:#3a1414;border:1px solid #e05050;border-radius:8px;padding:8px 12px;margin-bottom:10px;">
      <b style="color:#ff8080;">\u26a0\ufe0f \u041f\u043e\u0441\u043b\u0435\u0434\u043d\u0438\u0439 \u0431\u044d\u043a\u0442\u0435\u0441\u0442 \u0431\u044b\u043b ${Math.round(staleSec/3600*10)/10} \u0447 \u043d\u0430\u0437\u0430\u0434</b><br>
      <span style="font-size:11px;color:#e0a0a0;">\u0426\u0438\u043a\u043b \u043c\u043e\u0433 \u0437\u0430\u0432\u0438\u0441\u043d\u0443\u0442\u044c \u0438\u043b\u0438 \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0431\u044b\u043b\u043e \u043f\u0440\u0438\u043e\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e (\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440, Android \u043c\u043e\u0433 \u0443\u0431\u0438\u0442\u044c \u0444\u043e\u043d\u043e\u0432\u044b\u0439 Termux \u043f\u0440\u0438 \u043f\u0440\u043e\u0441\u0442\u043e\u0435 \u0441 \u0432\u044b\u043a\u043b\u044e\u0447\u0435\u043d\u043d\u044b\u043c \u044d\u043a\u0440\u0430\u043d\u043e\u043c). \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435, \u0447\u0442\u043e \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435 \u0436\u0438\u0432\u043e, \u0438\u043b\u0438 \u043e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0437\u0430\u043d\u043e\u0432\u043e.</span>
    </div>` : '';
  const progressPct = status.backtest_total ? Math.round((status.backtest_done||0) / status.backtest_total * 100) : 0;
  const progressBarHtml = status.backtest_running ? `
    <div style="margin:6px 0 8px;">
      <div style="background:#1c2433;border-radius:6px;height:8px;overflow:hidden;">
        <div style="background:#3ddc97;height:100%;width:${progressPct}%;transition:width 0.4s;"></div>
      </div>
      <div class="dim" style="font-size:11px;margin-top:3px;">
        ${progressPct}% · сейчас: ${(status.backtest_in_flight||[]).slice(0,6).join(', ') || '—'}${(status.backtest_in_flight||[]).length > 6 ? ` +${status.backtest_in_flight.length-6}` : ''}
      </div>
    </div>` : '';
  // v0.99.58, per direct user request ("актуализировать описание,
  // сделать его коротким содержательным и более тезисным"): replaced
  // the old two-paragraph prose block (methodology + full config
  // dump in running sentences) with a short bulleted list — same
  // facts, none of the connective-tissue wording. Also fixed a stale
  // framing bug while rewriting: "топ-N ликвидных монет" implied a
  // liquidity-rank CUTOFF still exists, but v0.99.48 removed that cap
  // — every symbol clearing MIN_VOL_USD gets backtested now, not just
  // the top N by volume, so this now says "N ликвидных монет" without
  // the misleading "топ-" prefix. The live-scan symbol list is
  // truncated to the first 8 with a "+N ещё" tail (same pattern the
  // progress bar's own in-flight list already used above) since it
  // can grow arbitrarily long as more symbols qualify.
  const liveSymbols = status.live_universe || status.symbols || [];
  const liveSymbolsTxt = liveSymbols.slice(0, 8).join(', ') + (liveSymbols.length > 8 ? ` +${liveSymbols.length - 8}` : '');
  const warnHtml = `
    <div class="dim" style="font-size:12px;margin-bottom:10px;">
      <b>MSNR / Malaysian SNR</b> (@xaubymedovyk): OCL-уровни по закрытиям, A/V-shape пивоты, вход — QM (ложный вынос + возврат), тейк — противоположный уровень (высокий R:R от природы паттерна). Бэктест честный, без заглядывания вперёд.
    </div>`;
  const headerHtml = `
    <div class="dim" style="margin-bottom:8px;font-size:12px;">
      <ul style="margin:0 0 6px 18px;padding:0;">
        <li>Живой скан: квалифицированные монеты (${liveSymbolsTxt || '—'}) — золото больше не форсируется, ранжируется наравне со всеми (эксперимент)</li>
        <li>Квалификация в живой скан: только топ-10 по совместной оценке (винрейт, выборка, доход) или ручная галочка — старое правило «винрейт&gt;50%/выборка&gt;40» убрано</li>
        <li>Бэктест: ${status.backtest_universe_size || '?'} ликвидных монет · структура ${cfg.structure_tf} (L${cfg.pivot_left}/R${cfg.pivot_right}) · вход ${cfg.entry_tf}</li>
        <li>Параметры (импульс/QM-зона/окно) автотюнятся отдельно на каждую монету — см. «Параметры» в таблице</li>
        <li>TP всегда реальный уровень пары (без потолка RR) — двусторонний фильтр по RR (снизу и сверху) на каждую монету отдельно, по её собственной статистике</li>
        <li>Автоторговля (если включена в настройках) — по всем монетам живого скана</li>
      </ul>
      <div class="dim" style="font-size:11px;margin:0 0 6px 0;">Топ-10 и таблица ниже отсортированы одной и той же оценкой — произведением нормализованных винрейта/выборки(до фильтров)/дохода с равными весами: слабость по любому из трёх параметров обнуляет итог, сильные стороны не компенсируют — без разрыва между топ-10 и остальными.</div>
      ${staleWarnHtml}
      ${buildTxt}<br>
      ${progressBarHtml}
      <b>Живые сигналы</b>: ${ssWr} (${ss.wins||0}W/${ss.losses||0}L, timeout ${ss.timeouts||0}) · открытых: ${ss.open||0} · всего: ${ss.total||0} · клик по строке — график
    </div>`;
  const rrBuckets = status.rr_buckets || [];
  const rrBucketRows = rrBuckets.map(b => {
    const wrClass = b.winrate === null ? 'dim' : (b.winrate >= 50 ? 'win' : 'loss');
    return `<tr>
      <td>${b.range}</td>
      <td class="${wrClass}">${b.winrate !== null ? b.winrate + '%' : '-'}</td>
      <td class="dim">n=${b.n}</td>
      <td class="win">${b.wins}W</td>
      <td class="loss">${b.losses}L</td>
    </tr>`;
  }).join('');
  const rrBucketsHtml = rrBuckets.some(b => b.n > 0) ? `
    <div class="dim" style="margin:8px 0 6px;"><b>Винрейт по диапазонам RR</b> (все монеты вместе, по факту закрытых сделок) — здесь видно, если один диапазон RR систематически проваливается, даже если пул усреднённых цифр этого не показывает:</div>
    <div style="overflow-x:auto;margin-bottom:14px;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>RR</th><th>Win-rate</th><th>n</th><th>W</th><th>L</th></tr></thead>
      <tbody>${rrBucketRows}</tbody>
    </table>
    </div>` : '';
  const signalsRows = signals.map((s, idx) => {
    const dirClass = s.direction === 'LONG' ? 'long' : 'short';
    let statusHtml;
    // v0.99.73, per direct live user alarm ("какого фига по ней
    // открылась сделка?" — TRX_USDT, no autotrade checkbox, green
    // "in live scan" dot lit): confirmed by re-reading the actual
    // record-construction code that "OPEN" here NEVER meant a real
    // position — record["status"]="OPEN" is set unconditionally the
    // moment ANY signal is detected, before the autotrade-eligibility
    // check even runs, specifically so a symbol's own track record
    // keeps accumulating (win-rate/RR/hour/volume stats) whether or
    // not it's currently toggled for real trading — see the record's
    // own comment for why msnr_update_live_balance() needs autotrade_
    // fired=False signals to NOT move real money either. The green dot
    // means "in the live SCAN universe" (getting checked for signals
    // at all), never "being traded" — those are different questions,
    // and the wording alone didn't make that obvious. Now says "OPEN
    // (сигнал)" instead of a bare "OPEN" specifically when autotrade_
    // fired is false, so a signal that never risked real money doesn't
    // read as one that did — s.autotrade_fired itself is untouched,
    // this is display-only.
    if (s.status === 'OPEN') statusHtml = s.autotrade_fired ? '<span class="status-open">OPEN</span>' : '<span class="status-open" title="сигнал отслеживается для статистики — реальная сделка не открыта (нет галочки/не в топ-10)">OPEN (сигнал)</span>';
    else if (s.result === 'WIN') statusHtml = `<span class="win">WIN @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else if (s.result === 'LOSS') statusHtml = `<span class="loss">LOSS @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else statusHtml = '<span class="status-timeout">TIMEOUT</span>';
    const levelTxt = s.level_type === 'A' ? 'A-shape' : 'V-shape';
    // v0.99.33, per direct user request: real per-symbol compounding
    // margin ($40 first trade, then whatever the previous trade's own
    // result left the balance at, capped at MSNR_LIVE_BALANCE_MAX) —
    // only shown for signals an actual order was placed for
    // (autotrade_fired), since a signal nobody traded never had a
    // real margin behind it at all.
    // v0.99.69, per direct user report (screenshot: a live OPEN
    // signal showing "15x" while the backtest table's own "плечо
    // ... (Kelly-оптимум)" for the same symbol showed 19.5x — looked
    // like a bug, isn't one): leverage_used is frozen at the moment
    // THIS signal fired (an already-placed order's leverage can't
    // retroactively change), while the backtest table's Kelly value
    // is the CURRENT recommendation — it keeps updating every
    // backtest cycle, so it can genuinely move between when a still-
    // open signal fired and now. It can also differ for a second,
    // separate reason even at the SAME instant: msnr_scan_symbol_
    // live()'s own liquidation-safety check walks leverage DOWN from
    // the Kelly value for a trade whose specific SL width would
    // otherwise breach the buffer — so a live value below the
    // current Kelly number is expected either way, never a display
    // bug. Tooltip added so this isn't confusing again without
    // needing to re-explain it from scratch each time.
    const sizeTxt = s.autotrade_fired
      ? `<span title="\u043f\u043b\u0435\u0447\u043e \u043d\u0430 \u043c\u043e\u043c\u0435\u043d\u0442 \u0441\u0440\u0430\u0431\u0430\u0442\u044b\u0432\u0430\u043d\u0438\u044f \u044d\u0442\u043e\u0433\u043e \u0441\u0438\u0433\u043d\u0430\u043b\u0430 \u2014 \u043c\u043e\u0433\u043b\u043e \u043e\u0442\u043b\u0438\u0447\u0430\u0442\u044c\u0441\u044f \u043e\u0442 \u0442\u0435\u043a\u0443\u0449\u0435\u0439 Kelly-\u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0430\u0446\u0438\u0438 \u0432 \u0442\u0430\u0431\u043b\u0438\u0446\u0435 \u043d\u0438\u0436\u0435 \u2014 \u043e\u043d\u0430 \u043e\u0431\u043d\u043e\u0432\u043b\u044f\u0435\u0442\u0441\u044f \u043a\u0430\u0436\u0434\u044b\u0439 \u0446\u0438\u043a\u043b, \u0438\u043b\u0438 \u0435\u0451 \u0441\u043f\u0435\u0446\u0438\u0430\u043b\u044c\u043d\u043e \u0434\u043e\u0436\u0430\u043b\u0438 \u0432\u043d\u0438\u0437 \u0438\u0437-\u0437\u0430 \u0448\u0438\u0440\u0438\u043d\u044b \u0441\u0442\u043e\u043f\u0430 \u044d\u0442\u043e\u0439 \u0441\u0434\u0435\u043b\u043a\u0438">$${s.live_size_usd}${s.leverage_used ? ' @ '+s.leverage_used+'x' : ''}</span>`
      : '<span class="dim">\u2014</span>';
    return `<tr onclick="openMsnrChart('${s.symbol}', ${s.time})" style="cursor:pointer;">
      <td>${s.symbol}</td><td class="${dirClass}">${s.direction}</td><td class="dim">${levelTxt}</td>
      <td>${fmt(s.entry)}</td><td class="dim">${fmt(s.sl)}</td><td class="dim">${fmt(s.tp)}</td>
      <td class="dim">${sizeTxt}</td>
      <td>${statusHtml}</td><td class="dim" title="время свечи сигнала: ${fmtDateTime(s.time)}">${s.detected_at ? fmtDateTime(s.detected_at) : fmtDateTime(s.time)}${s.detected_at && Math.abs(s.detected_at - s.time) > 120 ? ` <span style="opacity:0.5;font-size:10px;">(свеча ${fmtTime(s.time)})</span>` : ''}</td>
    </tr>`;
  }).join('');
  const signalsTableHtml = signals.length ? `
    <div style="overflow-x:auto;margin-bottom:14px;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>Dir</th><th>Уровень</th><th>Entry</th><th>SL</th><th>TP</th><th>Размер</th><th>Status</th><th>Время</th></tr></thead>
      <tbody>${signalsRows}</tbody>
    </table>
    </div>` : '<div class="dim" style="margin-bottom:14px;">Живых сигналов пока нет.</div>';
  const btRows = [...(status.top || [])].sort((a, b) => {
    // v0.99.19: autotrade-eligible rows (the ones with a checkbox) are
    // grouped to the TOP of the table first, regardless of the active
    // sort key — per direct user report that checked/eligible coins
    // were scattered throughout the list, easy to lose track of among
    // dozens of backtest-only rows. Within each group (eligible /
    // not-eligible), the normal sort key still applies.
    if (a.autotrade_eligible !== b.autotrade_eligible) return a.autotrade_eligible ? -1 : 1;
    // v0.99.27, per direct user request ("просто не попадает в топ"):
    // stress_test_failed rows (a losing $ compound simulation, see
    // msnr_optimize_symbol()'s own docstring) sink BELOW every row
    // that passed, regardless of the active sort key — same reasoning
    // as the eligible/not-eligible split above, one tier lower. Can't
    // collide with the eligible check: msnr_rank_by_winrate_sample()
    // already excludes stress_test_failed symbols from eligibility
    // entirely, so this only ever matters within the non-eligible
    // group, which is exactly where it needs to matter.
    if (!!a.stress_test_failed !== !!b.stress_test_failed) return a.stress_test_failed ? 1 : -1;
    // v0.99.75 — null means "no column clicked yet, trust the backend's
    // own already-sorted order" (see _msnrSortKey's own comment above).
    // Returning 0 here preserves the array's existing order rather than
    // comparing a field that isn't being overridden to anything.
    if (_msnrSortKey === null) return 0;
    const av = a[_msnrSortKey], bv = b[_msnrSortKey];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    return av < bv ? -_msnrSortDir : (av > bv ? _msnrSortDir : 0);
  }).map((r, idx, arr) => {
    const wrClass = (r.winrate === null || r.winrate === undefined) ? 'dim' : (r.winrate >= 50 ? 'win' : 'loss');
    const expClass = (r.expectancy_r === null || r.expectancy_r === undefined) ? 'dim' : (r.expectancy_r > 0 ? 'win' : 'loss');
    // v0.99.86 — skip_rr_max (the new floor side) shown alongside the
    // existing ceiling; both share rr_filtered_count since a single
    // combined pass removes trades on either side (see msnr_optimize_
    // symbol()'s own rr_range filtering step).
    const skipTxt = (r.skip_rr_min !== null && r.skip_rr_min !== undefined) ? ` \u00b7 <span class="loss">skip rr\u2265${r.skip_rr_min}${r.rr_filtered_count ? ` (${r.rr_filtered_count})` : ''}</span>` : '';
    const skipRrMaxTxt = (r.skip_rr_max !== null && r.skip_rr_max !== undefined) ? ` \u00b7 <span class="loss">skip rr<${r.skip_rr_max}</span>` : '';
    const skipSlTxt = (r.skip_sl_pct_min !== null && r.skip_sl_pct_min !== undefined) ? ` \u00b7 <span class="loss">skip SL\u2265${r.skip_sl_pct_min}%${r.sl_filtered_count ? ` (${r.sl_filtered_count})` : ''}</span>` : '';
    // v0.99.86, per direct user request ("хочу видеть... винрейт и
    // доход до и после [фильтров], чтобы понимать эффективность
    // фильтров"): a compact before->after summary built from best_
    // results' own filter_checkpoints chain — the "raw" (pre-filter)
    // checkpoint vs the FINAL checkpoint (after every filter that
    // actually ran), since a per-stage breakdown for every row would
    // be too dense for this already-packed cell; the full chain is
    // still available in r.filter_checkpoints for anyone who wants the
    // per-stage detail (e.g. via the browser console) even though this
    // summary line doesn't render every stage individually.
    let filterImpactTxt = '';
    if (r.filter_checkpoints && r.filter_checkpoints.length > 1) {
      const before = r.filter_checkpoints[0];
      const after = r.filter_checkpoints[r.filter_checkpoints.length - 1];
      const fmtWr = v => (v === null || v === undefined) ? '?' : `${v}%`;
      const fmtInc = v => (v === null || v === undefined) ? '?' : `${v > 0 ? '+' : ''}${v}%`;
      filterImpactTxt = ` \u00b7 <span class="dim" title="винрейт/доход до всех фильтров \u2192 после">фильтры: ${before.n}\u2192${after.n} \u00b7 WR ${fmtWr(before.winrate)}\u2192${fmtWr(after.winrate)} \u00b7 доход ${fmtInc(before.income_pct)}\u2192${fmtInc(after.income_pct)}</span>`;
    }
    // v0.99.56, per direct user request ("какой фильтр сигналов был
    // бы самым эффективным"): shows the specific bad UTC hours (if
    // any) this symbol's own history flagged — same loss-red styling
    // as the other skip indicators, kept short (just the hour list,
    // no "UTC" repeated per-hour) since a symbol can have several.
    // v0.99.57: each skip indicator above now also shows the COUNT of
    // trades it actually excluded, in parens — per direct user request
    // ("просто писать сколько сделок отмечено по такой-то причине")
    // after noticing the sample-size gate itself was being unfairly
    // shrunk by these same filters (see msnr_optimize_symbol()'s own
    // docstring) — the gate is fixed at raw_closed_n now, this is
    // purely the informational breakdown of why the DISPLAYED n is
    // smaller than that.
    const skipHoursTxt = (r.skip_hours && r.skip_hours.length)
      ? ` \u00b7 <span class="loss">skip \u0447\u0430\u0441\u044b(UTC) ${r.skip_hours.join(',')}${r.hours_filtered_count ? ` (${r.hours_filtered_count})` : ''}</span>`
      : '';
    // v0.99.59, per direct user request ("второй фильтр" — volume
    // confirmation on the sweep): shows the volume-ratio FLOOR (below
    // which this symbol's history says a sweep is unreliable), same
    // count-in-parens pattern as the other skip indicators.
    const skipVolumeTxt = (r.skip_volume_below !== null && r.skip_volume_below !== undefined)
      ? ` \u00b7 <span class="loss">skip \u043e\u0431\u044a\u0451\u043c<${r.skip_volume_below}${r.volume_filtered_count ? ` (${r.volume_filtered_count})` : ''}</span>`
      : '';
    const liqTxt = r.liquidation_filtered_count ? ` \u00b7 <span class="loss">${r.liquidation_filtered_count} \u0437\u0430 \u043b\u0438\u043a\u0432\u0438\u0434\u0430\u0446\u0438\u0435\u0439</span>` : '';
    // v0.99.47, per direct user follow-up to v0.99.46 ("чёт лучше не
    // стало, будто даже хуже" -> Kelly/optimal-f search): leverage is
    // back to ONE flat value per symbol — msnr_optimal_leverage_for_
    // symbol()'s own choice, maximizing long-run compounded growth
    // against this symbol's own trade history, not a stop-width-
    // derived value. Shown plainly, with a "Kelly-оптимум" note only
    // when it's ABOVE the configured default (meaning the symbol's own
    // history justified more than the default, not just hitting the
    // floor). The exchange-cap note is now separate from the leverage
    // value itself — msnr_optimal_leverage_for_symbol() already search-
    // bounds against leverage_ceiling internally, so a low exchange cap
    // shows up as optLev sitting at or near it, but the raw ceiling is
    // still useful context on its own (this symbol simply can't ever
    // exceed it, regardless of what the optimizer would otherwise pick).
    const defLev = cfg.compound_leverage;
    const optLev = r.optimal_leverage;
    const ceilLev = r.leverage_ceiling;
    let levTxt = '';
    if (optLev !== null && optLev !== undefined) {
      levTxt = ` \u00b7 <span class="dim">\u043f\u043b\u0435\u0447\u043e ${optLev}x${optLev > defLev ? ' (Kelly-\u043e\u043f\u0442\u0438\u043c\u0443\u043c)' : ''}</span>`;
    }
    if (ceilLev !== null && ceilLev !== undefined && ceilLev < defLev) {
      levTxt += ` \u00b7 <span class="dim">\u043b\u0438\u043c\u0438\u0442 \u0431\u0438\u0440\u0436\u0438 ${ceilLev}x</span>`;
    }
    const compClass = (r.compound_return_pct === null || r.compound_return_pct === undefined) ? 'dim' : (r.compound_return_pct > 0 ? 'win' : 'loss');
    const compBlownTxt = r.compound_blown_at ? ` (\u0441\u043b\u0438\u0432 \u043d\u0430 #${r.compound_blown_at})` : '';
    const compTxt = (r.compound_return_pct !== null && r.compound_return_pct !== undefined)
      ? ` \u00b7 <span class="${compClass}">\u0434\u043e\u0445\u043e\u0434 ${r.compound_return_pct > 0 ? '+' : ''}${r.compound_return_pct}% ($${cfg.compound_start_balance}\u2192$${r.compound_final_balance})${compBlownTxt}</span>`
      : '';
    const paramsTxt = `${r.min_leg_atr}\u00d7ATR / ${(r.qm_zone_pct*100).toFixed(2)}% / ${r.qm_lookback_bars}\u0431${skipTxt}${skipRrMaxTxt}${skipSlTxt}${skipHoursTxt}${skipVolumeTxt}${liqTxt}${levTxt}${compTxt}${filterImpactTxt}`;
    const noteTxt = r.note ? ` \u26a0\ufe0f ${r.note}` : '';
    // v0.99.49, per direct user request ("хочу иметь возможность
    // автоторговли и не по топ-10, на свой страх и риск как
    // эксперимент"): checkbox now renders for every manual_toggle_
    // allowed row, not just the auto-ranked top-10 (autotrade_
    // eligible) — a manually-checked row outside the top-10 gets a
    // distinct orange outline + warning title so it's visually clear
    // this one isn't auto-ranked, it's a deliberate manual pick.
    // stress_test_failed rows still get no checkbox at all (excluded
    // from manual_toggle_allowed too — see that function's own
    // docstring for why that particular gate isn't bypassable here).
    // v0.99.108, per direct user request ("Ручное управление можно
    // убрать"): now purely a read-only indicator, not a clickable
    // control — autotrade state for the top-N pool is fully automatic
    // (msnr_backtest_loop() auto-toggles based on top-N membership +
    // win_rate > 50, see that loop's own comment). The old "manual,
    // outside top-10, на свой страх и риск" feature is gone entirely
    // along with the click handler — a symbol either currently
    // qualifies (shown checked/green) or it doesn't (shown unchecked/
    // dim), nothing left to click.
    const autotradeCell = r.autotrade_eligible
      ? `<span class="${r.autotrade_on ? 'win' : 'dim'}" style="font-size:14px;" title="${r.autotrade_on ? 'авто-включено: в топе и WR>50%' : 'в топе, но WR не выше 50% — авто-выключено'}">${r.autotrade_on ? '\u2713' : '\u2014'}</span>`
      : '<span class="dim" style="font-size:10px;">\u2014</span>';
    // v0.99.19: a visible separator row exactly at the eligible/rest
    // boundary — the sort above already groups eligible rows first,
    // this makes that grouping obvious at a glance instead of relying
    // on the reader to notice checkboxes stop appearing partway down.
    // v0.99.49: wording updated — autotrade is no longer unavailable
    // past this line, just not auto-ranked; a checkbox still renders
    // for any manual_toggle_allowed row below it.
    const separatorHtml = (idx > 0 && arr[idx - 1].autotrade_eligible && !r.autotrade_eligible)
      ? `<tr><td colspan="11" class="dim" style="font-size:10px;padding:4px 0;border-top:1px solid #1c2433;">\u2014 \u043e\u0441\u0442\u0430\u043b\u044c\u043d\u044b\u0435 (\u0432\u043d\u0435 \u0442\u043e\u043f-10, \u0430\u0432\u0442\u043e\u0442\u043e\u0440\u0433\u043e\u0432\u043b\u044f \u0432\u0440\u0443\u0447\u043d\u0443\u044e \u2014 \u043d\u0430 \u0441\u0432\u043e\u0439 \u0440\u0438\u0441\u043a) \u2014</td></tr>`
      : '';
    // v0.99.27, per direct user request: same idea, one tier lower —
    // a visible separator exactly where stress_test_failed rows begin
    // (they're already sunk to the bottom by the sort above), so it's
    // obvious at a glance that everything past this line failed its
    // own $ compounding simulation and is excluded from ranking/
    // autotrade entirely, not just scored lower.
    const stressSeparatorHtml = (idx > 0 && !arr[idx - 1].stress_test_failed && r.stress_test_failed)
      ? `<tr><td colspan="11" class="loss" style="font-size:10px;padding:4px 0;border-top:1px solid #1c2433;">\u2014 \u043f\u0440\u043e\u0432\u0430\u043b\u0438\u043b\u0438 $-\u0441\u0438\u043c\u0443\u043b\u044f\u0446\u0438\u044e \u0434\u0435\u043f\u043e\u0437\u0438\u0442\u0430 (\u0434\u043e\u0445\u043e\u0434 \u2264 0%), \u0438\u0441\u043a\u043b\u044e\u0447\u0435\u043d\u044b \u0438\u0437 \u0442\u043e\u043f\u0430/\u0430\u0432\u0442\u043e\u0442\u043e\u0440\u0433\u043e\u0432\u043b\u0438 \u2014</td></tr>`
      : '';
    // v0.99.141 — solo-checkpoint columns for the 2 new GLOBAL filters
    // (see MSNR_MIN_RR_FILTER_ENABLED's own comment), reading them by
    // "stage" name out of the SAME filter_checkpoints chain the compact
    // filterImpactTxt summary above already draws from — matching
    // Sweep's own fmtCheckpoint style (isolated solo result + delta vs
    // the "raw" pre-filter checkpoint, not vs the final chained result).
    const fcList = r.filter_checkpoints || [];
    const rawCp = fcList.find(c => c.stage === 'raw');
    const fmtMsnrSolo = (stage, enabled) => {
      const cp = fcList.find(c => c.stage === stage);
      if (!cp || !cp.n) return '<span class="dim">нет данных</span>';
      let deltaTxt = '';
      if (rawCp && rawCp.winrate !== null && rawCp.winrate !== undefined && cp.winrate !== null && cp.winrate !== undefined) {
        const delta = Math.round((cp.winrate - rawCp.winrate) * 10) / 10;
        const deltaCls = delta > 0 ? 'win' : (delta < 0 ? 'loss' : 'dim');
        deltaTxt = ` <span class="${deltaCls}">(${delta > 0 ? '+' : ''}${delta}%)</span>`;
      }
      const onOff = enabled ? '' : ' <span class="dim">[выкл]</span>';
      return `<span class="dim" title="если применить ТОЛЬКО этот фильтр поверх остальных, без него">${cp.winrate}% (n=${cp.n})${deltaTxt}${onOff}</span>`;
    };
    const minRrSoloTxt = fmtMsnrSolo('min_rr', cfg.min_rr_filter_enabled);
    const htfSoloTxt = fmtMsnrSolo('htf_trend', cfg.htf_filter_enabled);
    return separatorHtml + stressSeparatorHtml + `<tr onclick="toggleMsnrBacktestTrades('${r.symbol}')" style="cursor:pointer;">
      <td>${_msnrExpanded.has(r.symbol) ? '\u25be' : '\u25b8'} ${r.symbol}${r.live ? ' <span style="color:#3ddc97;" title="торгуется вживую">\u25cf</span>' : ' <span class="dim" title="только бэктест, не торгуется">\u25cb</span>'}</td>
      <td onclick="event.stopPropagation();">${autotradeCell}</td>
      <td class="${wrClass}">${r.winrate !== null && r.winrate !== undefined ? r.winrate+'%' : '-'}</td>
      <td class="dim">n=${r.trades}${(r.raw_closed_n !== null && r.raw_closed_n !== undefined && r.raw_closed_n > r.trades) ? ` <span title="исходная выборка до фильтров — именно её смотрит отбор в топ/live">(было ${r.raw_closed_n})</span>` : ''}</td>
      <td class="dim"><span class="win">${r.wins}W</span>/<span class="loss">${r.losses}L</span>/<span class="status-timeout">${r.timeouts}T</span></td>
      <td class="dim" title="med ${r.median_rr ?? '-'}R">avg ${r.avg_rr ?? '-'}R</td>
      <td class="${expClass}">${r.expectancy_r !== null && r.expectancy_r !== undefined ? (r.expectancy_r > 0 ? '+' : '') + r.expectancy_r + 'R' : '-'}</td>
      <td class="dim">${r.score !== null && r.score !== undefined ? r.score : '-'}</td>
      <td>${minRrSoloTxt}</td>
      <td>${htfSoloTxt}</td>
      <td class="dim" style="white-space:normal;min-width:220px;">${paramsTxt}${noteTxt}</td>
    </tr>
    <tr id="msnrTrades_${r.symbol}" style="display:none;"><td colspan="11" style="padding:0;"><div id="msnrTradesBody_${r.symbol}" class="dim" style="padding:6px 0;">\u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0430...</div></td></tr>`;
  }).join('');
  const btTableHtml = (status.top || []).length ? `
    <div class="dim" style="margin-bottom:6px;"><b>\u0410\u0432\u0442\u043e\u0442\u044e\u043d\u0438\u043d\u0433 \u043f\u043e \u043c\u043e\u043d\u0435\u0442\u0430\u043c</b> (${cfg.backtest_days} \u0434\u043d\u0435\u0439 \u0438\u0441\u0442\u043e\u0440\u0438\u0438, \u043f\u0435\u0440\u0435\u0431\u043e\u0440 ${cfg.grid_min_leg_atr.length}\u00d7${cfg.grid_qm_zone_pct.length}\u00d7${cfg.grid_qm_lookback.length}=${cfg.grid_min_leg_atr.length*cfg.grid_qm_zone_pct.length*cfg.grid_qm_lookback.length} \u043a\u043e\u043c\u0431\u0438\u043d\u0430\u0446\u0438\u0439 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u043e\u0432 \u043d\u0430 \u0441\u0438\u043c\u0432\u043e\u043b \u2014 \u043c\u0438\u043d. \u0438\u043c\u043f\u0443\u043b\u044c\u0441 (\u00d7ATR) / QM-\u0437\u043e\u043d\u0430 (%) / \u043e\u043a\u043d\u043e QM (\u0431\u0430\u0440\u044b), \u0442\u0430\u0431\u043b\u0438\u0446\u0430 \u043f\u043e\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442 \u0443\u0436\u0435 \u043b\u0443\u0447\u0448\u0438\u0439 \u043d\u0430\u0439\u0434\u0435\u043d\u043d\u044b\u0439 \u043a\u043e\u043c\u0431\u043e \u043f\u043e \u043a\u0430\u0436\u0434\u043e\u043c\u0443 \u0441\u0438\u043c\u0432\u043e\u043b\u0443) \u00b7 <b>score</b> \u2014 \u043d\u0438\u0436\u043d\u044f\u044f \u0434\u043e\u0432\u0435\u0440\u0438\u0442\u0435\u043b\u044c\u043d\u0430\u044f \u0433\u0440\u0430\u043d\u0438\u0446\u0430 \u0441\u0440\u0435\u0434\u043d\u0435\u0433\u043e R (\u043f\u043e \u043d\u0435\u0439 \u0438 \u0432\u044b\u0431\u0438\u0440\u0430\u0435\u0442\u0441\u044f \u043b\u0443\u0447\u0448\u0438\u0439 \u043a\u043e\u043c\u0431\u043e, \u0430 \u043d\u0435 \u043f\u043e \u0441\u044b\u0440\u043e\u043c\u0443 expectancy \u2014 \u0447\u0442\u043e\u0431\u044b \u043c\u0430\u043b\u0435\u043d\u044c\u043a\u0430\u044f \u0432\u044b\u0431\u043e\u0440\u043a\u0430 \u0441 \u0432\u0435\u0437\u0435\u043d\u0438\u0435\u043c \u043d\u0435 \u043f\u043e\u0431\u0435\u0436\u0434\u0430\u043b\u0430 \u0431\u043e\u043b\u044c\u0448\u0443\u044e \u0441\u0442\u0430\u0431\u0438\u043b\u044c\u043d\u0443\u044e) \u00b7 \u043a\u043b\u0438\u043a \u043f\u043e \u0441\u0442\u0440\u043e\u043a\u0435 \u2014 \u0440\u0430\u0441\u043a\u0440\u044b\u0442\u044c \u0441\u0434\u0435\u043b\u043a\u0438:</div>
    <div style="overflow-x:auto;">
    <table class="msnr-bt-table" style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>Авто</th><th style="cursor:pointer;" onclick="msnrSortBy('winrate')">WR${_msnrSortKey==='winrate' ? (_msnrSortDir===-1?' \u25be':' \u25b4') : ''}</th><th style="cursor:pointer;" onclick="msnrSortBy('trades')">n${_msnrSortKey==='trades' ? (_msnrSortDir===-1?' \u25be':' \u25b4') : ''}</th><th>W/L/T</th><th>RR</th><th>Exp</th><th>Score</th><th>Мин.RR≥${cfg.min_rr_filter} (соло)</th><th>Тренд 4ч (соло)</th><th>\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b</th></tr></thead>
      <tbody>${btRows}</tbody>
    </table>
    </div>` : '<div class="dim">\u0411\u044d\u043a\u0442\u0435\u0441\u0442 \u0435\u0449\u0451 \u043d\u0435 \u0433\u043e\u0442\u043e\u0432.</div>';
  setPanelHtml(panel, warnHtml + headerHtml + rrBucketsHtml + signalsTableHtml + btTableHtml);
  restoreMsnrExpansion();
}

// Expanded-row state lives OUTSIDE refreshMsnr()'s panel.innerHTML rebuild
// on purpose — the whole panel gets re-rendered from scratch on every
// auto-refresh tick, which was wiping out both which rows were open AND
// the stale-fetch guard (that guard used to live keyed off a flag that
// survived the rebuild while the DOM/content didn't, so a re-opened row
// after a refresh tick would skip fetching entirely and hang on
// "загрузка..." forever). _msnrExpanded is the single source of truth
// for "should this row be open", restoreMsnrExpansion() re-applies it
// (and re-fetches, since the row's body content is always fresh
// "загрузка..." right after a rebuild) after every refreshMsnr() call.
const _msnrExpanded = new Set();

function toggleMsnrBacktestTrades(symbol) {
  const row = document.getElementById(`msnrTrades_${symbol}`);
  if (!row) return;
  if (_msnrExpanded.has(symbol)) {
    _msnrExpanded.delete(symbol);
    row.style.display = 'none';
  } else {
    _msnrExpanded.add(symbol);
    row.style.display = 'table-row';
    loadMsnrTrades(symbol);
  }
}

function restoreMsnrExpansion() {
  for (const symbol of _msnrExpanded) {
    const row = document.getElementById(`msnrTrades_${symbol}`);
    if (!row) continue;  // symbol no longer in the (re-rendered) top list
    row.style.display = 'table-row';
    loadMsnrTrades(symbol);
  }
}

async function loadMsnrTrades(symbol) {
  const body = document.getElementById(`msnrTradesBody_${symbol}`);
  if (!body) return;
  // v0.99.51, per direct user report ("сброс видимого окна при
  // скролле и масштабировании, когда смотрю сделки и листаю список
  // монет"): only show the "загрузка..." placeholder the FIRST time
  // this coin is expanded (body still empty). restoreMsnrExpansion()
  // re-calls this for every already-expanded coin on EVERY 15s
  // refresh tick — unconditionally blanking an already-populated
  // trade table back to one short line of text before the fetch
  // resolves made the page's total height oscillate on every single
  // tick, which is exactly what made the visible viewport look like
  // it kept "resetting" even after setPanelHtml() started restoring
  // window.scrollY (restoring a scroll position doesn't help if the
  // content AT that position keeps disappearing and reappearing).
  // Keeping the OLD table visible while the new one loads in the
  // background removes that height flicker entirely for the by-far
  // most common case — a routine refresh of an already-expanded coin.
  const hasContent = body.querySelector('table') !== null;
  if (!hasContent) body.textContent = 'загрузка...';
  try {
    const trades = await (await fetch(`/api/msnr/backtest/${symbol}`)).json();
    if (!trades.length) { body.textContent = 'сделок нет'; return; }
    const rows = trades.map(t => {
      const dirClass = t.direction === 'LONG' ? 'long' : 'short';
      const resClass = t.result === 'WIN' ? 'win' : (t.result === 'LOSS' ? 'loss' : 'status-timeout');
      const levelTxt = t.level_type === 'A' ? 'A-shape' : 'V-shape';
      // v0.99.25, per direct user request: show the compounding balance
      // right next to each trade, not just the summary "доход" figure —
      // so the compounding math can be checked trade-by-trade. Null
      // means this trade was never reached by the simulation (a
      // TIMEOUT, or the account already hit $0 on an earlier trade —
      // see msnr_compound_trail()'s own docstring), shown as a dim
      // dash rather than a misleading $0.
      const compTxt = (t.compound_balance_after !== null && t.compound_balance_after !== undefined)
        ? `<span class="${t.compound_pnl_pct >= 0 ? 'win' : 'loss'}">$${t.compound_balance_after} (${t.compound_pnl_pct >= 0 ? '+' : ''}${t.compound_pnl_pct}%)</span>`
        : '<span class="dim">\u2014</span>';
      // v0.99.46, per direct user request ("рядом с каждой монетой ещё
      // и вычислять плечо"): this specific trade's OWN resolved
      // leverage (msnr_leverage_for_stop(), scaled up from the default
      // for a tight stop) — same null-means-unreached reasoning as
      // compTxt above, since a trade with no trail entry never had a
      // leverage resolved for it either.
      const levTxt = (t.compound_leverage !== null && t.compound_leverage !== undefined)
        ? `${t.compound_leverage}x`
        : '<span class="dim">\u2014</span>';
      return `<tr onclick="event.stopPropagation(); openMsnrChart('${symbol}', ${t.time})" style="cursor:pointer;">
        <td class="dim">${fmtDateTime(t.time)}</td>
        <td class="${dirClass}">${t.direction}</td>
        <td class="dim">${levelTxt}</td>
        <td>${fmt(t.entry)}</td><td class="dim">${fmt(t.sl)}</td><td class="dim">${fmt(t.tp)}</td>
        <td class="dim">${t.rr ?? '-'}R</td>
        <td class="dim">${levTxt}</td>
        <td class="${resClass}">${t.result}</td>
        <td>${compTxt}</td>
      </tr>`;
    }).join('');
    body.innerHTML = `<div style="overflow-x:auto;"><table style="font-size:11px;white-space:nowrap;width:100%;">
      <thead><tr><th>Время</th><th>Dir</th><th>Уровень</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>Плечо</th><th>Result</th><th>Баланс</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
  } catch (e) {
    body.textContent = 'ошибка загрузки';
    console.error(e);
  }
}

let currentMsnrData = null;

async function openMsnrChart(symbol, sigTime) {
  document.getElementById('msnrModalTitle').textContent = symbol;
  document.getElementById('msnrModalParams').textContent = 'загрузка...';
  msnrModal.classList.add('open');
  try {
    const q = sigTime ? `?time=${sigTime}` : '';
    const data = await (await fetch(`/api/msnr/chart/${symbol}${q}`)).json();
    if (data.error) { document.getElementById('msnrModalParams').textContent = data.error; return; }
    currentMsnrData = data;
    const sig = data.signal;
    if (!sig) {
      document.getElementById('msnrModalParams').textContent = 'подтверждённого QM-сигнала в этом окне нет — показан текущий Storyline';
    } else {
      const resTxt = data.result ? ` · ${data.result}${data.exit_price ? ' @ '+fmtNum(data.exit_price) : ''}` : '';
      const levelTxt = sig.level_type === 'A' ? 'A-shape (resist)' : 'V-shape (support)';
      document.getElementById('msnrModalParams').textContent =
        `${fmtDateTime(sig.time)} · ${sig.direction} от ${levelTxt} · entry ${fmtNum(sig.entry)} · SL ${fmtNum(sig.sl)} · TP ${fmtNum(sig.tp)}${resTxt}`;
    }
    drawMsnrChart(data);
  } catch (e) {
    console.error(e);
  }
}

function drawMsnrChart(data) {
  const canvas = document.getElementById('msnrChartCanvas');
  const wrap = document.getElementById('msnrChartWrap');
  const dpr = window.devicePixelRatio || 1;
  const W = wrap.clientWidth, H = wrap.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const candles = data.candles || [];
  if (!candles.length) return;
  const sig = data.signal;
  const pivots = data.pivots || [];

  const padRight = 54;
  const chartW = W - padRight;
  const n = candles.length;
  const slot = chartW / n;
  const bodyW = Math.max(1, slot * 0.6);
  const xAt = (i) => i * slot + slot / 2;

  const entry = sig ? sig.entry : undefined;
  const sl = sig ? sig.sl : undefined;
  const tp = sig ? sig.tp : undefined;
  // computeYRangeSimple() only reads entry/sl/tp — A-shape/V-shape levels
  // can sit well outside that (this chart's whole point is to show price
  // traveling from one back to the other), so the range is built by hand
  // here rather than reusing it, to guarantee both pivot lines stay
  // on-screen even for a signal-less "current Storyline" view.
  let hi = Math.max(...candles.map(c => c.high));
  let lo = Math.min(...candles.map(c => c.low));
  [entry, sl, tp, ...pivots.map(p => p.price)].forEach(v => {
    if (v !== undefined && v !== null) { hi = Math.max(hi, v); lo = Math.min(lo, v); }
  });
  const range0 = (hi - lo) || (hi * 0.02) || 1;
  const pad = range0 * 0.05;
  hi += pad; lo -= pad;
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

  // A-shape / V-shape structure levels (OCL) — orange for A (resistance),
  // teal for V (support), so the pair reads at a glance like the source's
  // own red-line slide diagrams. MSNR routinely has several close-together
  // levels plus entry/SL/TP all in a narrow band (unlike the other tabs'
  // 2-3 well-spaced lines), so the shared drawLevelLine() — which prints
  // each label right at its own line's y — was stacking text on top of
  // text. Lines are drawn immediately at their true y; labels are
  // collected and spread apart afterward via layoutMsnrLabels() instead.
  const msnrLabels = [];
  const drawMsnrDashedLine = (yy, color) => {
    ctx.setLineDash([2, 4]);
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = color;
    ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(chartW, yy); ctx.stroke();
    ctx.setLineDash([]);
  };

  pivots.forEach(p => {
    const color = p.type === 'A' ? '#e8b93d' : '#3ddc97';
    const yy = yP(p.price);
    drawMsnrDashedLine(yy, color);
    msnrLabels.push({ y: yy, text: (p.type === 'A' ? 'A-shape ' : 'V-shape ') + fmtNum(p.price), color });
  });

  if (sig) {
    drawMsnrDashedLine(yP(sig.entry), '#5aa8ff');
    drawMsnrDashedLine(yP(sig.sl), '#ff6b6b');
    drawMsnrDashedLine(yP(sig.tp), '#3ddc97');
    msnrLabels.push({ y: yP(sig.entry), text: 'ENTRY ' + fmtNum(sig.entry), color: '#5aa8ff' });
    msnrLabels.push({ y: yP(sig.sl), text: 'SL ' + fmtNum(sig.sl), color: '#ff6b6b' });
    msnrLabels.push({ y: yP(sig.tp), text: 'TP ' + fmtNum(sig.tp), color: '#3ddc97' });
    const entryIdx = findCandleIndex(candles, sig.time);
    if (entryIdx >= 0) {
      drawEntryMarker(ctx, entryIdx * slot + slot / 2, yP(sig.entry), '#5aa8ff');
    }
    // Exit marker — a dot at the SL or TP price, on the candle where the
    // trade actually closed, colored by outcome (green WIN / red LOSS).
    // Same shared drawEntryMarker() shape as the entry dot above, just at
    // a different point — matches the exit-marker pattern VGI's own
    // chart already uses (openVgiChart/drawVgiChart).
    if (data.exit_time && data.exit_price !== null && data.exit_price !== undefined) {
      const exitIdx = findCandleIndex(candles, data.exit_time);
      if (exitIdx >= 0) {
        const exitColor = data.result === 'WIN' ? '#3ddc97' : (data.result === 'LOSS' ? '#ff6b6b' : '#e0a030');
        drawEntryMarker(ctx, exitIdx * slot + slot / 2, yP(data.exit_price), exitColor);
      }
    }
  }

  layoutMsnrLabels(ctx, msnrLabels);
}

function layoutMsnrLabels(ctx, labels) {
  // Greedy top-to-bottom separation so close levels (very common here —
  // e.g. two A-shape pivots a few dollars apart, or entry sitting right
  // next to an A-shape it just rejected off) get readable, non-
  // overlapping text instead of drawing on top of each other. Lines
  // themselves were already drawn at their true y — this only moves text.
  const minGap = 12;
  const sorted = [...labels].sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].y - sorted[i - 1].y < minGap) {
      sorted[i].y = sorted[i - 1].y + minGap;
    }
  }
  ctx.font = 'bold 10px sans-serif';
  sorted.forEach(l => {
    ctx.fillStyle = l.color;
    ctx.fillText(l.text, 4, l.y - 4);
  });
}

// ---------------- FT5 — port of freqtrade Strategy005 (EXPERIMENTAL, v0.96.0) ----------------
async function refreshFt5() {
  const status = await (await fetch('/api/ft5/status')).json();
  const signals = await (await fetch('/api/ft5/signals')).json();
  const panel = document.getElementById('ft5Panel');
  const cfg = status.config || {};
  const ss = status.signals_stats || {};
  const ssWr = ss.winrate !== null && ss.winrate !== undefined ? `<span class="${ss.winrate >= 50 ? 'win' : 'loss'}">${ss.winrate}%</span>` : '<span class="dim">-</span>';
  const avgPnlTxt = ss.avg_pnl_pct !== null && ss.avg_pnl_pct !== undefined ? `${ss.avg_pnl_pct > 0 ? '+' : ''}${ss.avg_pnl_pct}%` : '-';
  const rrTxt = ss.rr_avg !== null && ss.rr_avg !== undefined
    ? `реализ. RR ср. ${ss.rr_avg>0?'+':''}${ss.rr_avg} (медиана ${ss.rr_median>0?'+':''}${ss.rr_median})`
    : 'реализ. RR ещё нет данных';
  // Плановое соотношение тейк:стоп — НЕ одно число, как у EMA/Дивергенции/
  // Сессии, потому что тейк здесь не фиксированная цена, а лесенка по
  // времени (см. предупреждение ниже): чем дольше сделка открыта, тем
  // меньше прибыли требуется для автозакрытия. Каждая ступень лесенки
  // делённая на фиксированный стоп даёт свой RR — показываем весь
  // диапазон, а не выдумываем одну усреднённую цифру.
  const roiLadder = cfg.roi_ladder || [];
  const stoplossPct = cfg.stoploss_pct || 0;
  const roiRrRange = stoplossPct > 0 && roiLadder.length
    ? roiLadder.map(r => r[1] / stoplossPct)
    : [];
  const plannedRrTxt = roiRrRange.length
    ? `план. тейк:стоп (лесенка) ${Math.min(...roiRrRange).toFixed(2)}\u2013${Math.max(...roiRrRange).toFixed(2)}`
    : '';
  const buildTxt = status.last_backtest_finished
    ? `последний перебор параметров: ${fmtTime(status.last_backtest_finished)} (${status.last_backtest_duration}s) · анализ: ${status.symbols_done}/${status.universe_size} монет · живой скан: топ-${status.live_top_n} (${(status.live_universe||[]).join(', ') || 'ещё не выбраны'})`
    : `перебор параметров ещё не завершился (${status.symbols_done}/${status.universe_size || '?'}) — живой скан начнётся после первого прохода`;
  const warnHtml = `
    <div style="background:#2a1f0e;border:1px solid #e0a030;border-radius:10px;padding:10px 14px;margin-bottom:12px;">
      <b style="color:#e0a030;">⚠️ Экспериментально</b><br>
      <span style="font-size:12px;color:#d9c08a;">Портирована структура Strategy005 (github.com/freqtrade/freqtrade-strategies, автор Gerald Lonlas) — 6 индикаторов (MACD, Minus DI, RSI+Fisher, Stochastic, SAR, SMA) + лесенка тейка по времени + фикс. стоп -10%. Оригинальные hyperopt-параметры взяты из бэктеста на 20 днях 2018 года — почти наверняка переподогнаны под тот период, поэтому НЕ скопированы напрямую: здесь свой перебор параметров на реальных данных этой биржи. Автоторговля и общий симулятор сознательно НЕ подключены — у стратегии нет единого фиксированного тейка (выход по времени/сигналу/стопу), а вся текущая инфраструктура рассчитана на пару SL/TP. Сигналы ниже — информационные. Соотношение тейк:стоп здесь не одно число: тейк — лесенка по времени (5%→1%), стоп фиксирован (10%), поэтому ниже показан и плановый диапазон (лесенка/стоп), и реализованный RR по факту закрытых сделок. В реверс-режиме — та же точка входа, но SHORT со стопом/лесенкой зеркально; сигнальный выход (RSI/MACD/MinusDI/SAR) не зеркалится и для реверс-сделок не используется.</span>
    </div>`;
  const headerHtml = `
    <div class="dim" style="margin-bottom:8px;">
      ТФ ${cfg.tf} · стоп ${(cfg.stoploss_pct*100).toFixed(0)}% · ${plannedRrTxt} · перебор: buy_rsi${JSON.stringify(cfg.grid_buy_rsi)} × buy_fisher${JSON.stringify(cfg.grid_buy_fisher)} × sell_rsi${JSON.stringify(cfg.grid_sell_rsi)}${cfg.invert_signals ? ` · <span style="color:#ffcc55;font-weight:bold;">РЕВЕРС ВКЛЮЧЁН</span>` : ''}<br>
      ${buildTxt}<br>
      <b>Живые сигналы</b>: ${ssWr} (${ss.wins||0}W/${ss.losses||0}L, timeout ${ss.timeouts||0}) · средний P&L/сделку: ${avgPnlTxt} · ${rrTxt} · открытых: ${ss.open||0} · всего: ${ss.total||0}<br>
      <span style="font-size:11px;">Клик по строке сигнала открывает график входа/выхода.</span>
    </div>
    ${(ss.wins || ss.losses) ? `
    <div style="margin-bottom:8px;"><b>MFE/MAE (R) на закрытии</b> — сколько реально было хода в плюс/минус к моменту исхода (${ss.wins||0}W/${ss.losses||0}L):<br>
      <span class="win">WIN MFE: ${fmtStat(ss.mfe_r_wins_at_close)}</span><br>
      <span class="win">WIN MAE: ${fmtStat(ss.mae_r_wins_at_close)}</span><br>
      <span class="loss">LOSS MFE: ${fmtStat(ss.mfe_r_losses_at_close)}</span><br>
      <span class="loss">LOSS MAE: ${fmtStat(ss.mae_r_losses_at_close)}</span><br>
      <span class="dim" style="font-size:11px;">Эти цифры питают авто-тюнинг решения о реверсе.</span>
    </div>` : ''}`;
  const signalsRows = signals.map(s => {
    let statusHtml;
    if (s.status === 'OPEN') statusHtml = '<span class="status-open">OPEN</span>';
    else if (s.result === 'WIN') statusHtml = `<span class="win">WIN (${s.exit_reason}) ${s.pnl_pct>0?'+':''}${s.pnl_pct}%</span>`;
    else if (s.result === 'LOSS') statusHtml = `<span class="loss">LOSS (${s.exit_reason}) ${s.pnl_pct}%</span>`;
    else statusHtml = '<span class="status-timeout">TIMEOUT</span>';
    const rrTd = s.rr !== null && s.rr !== undefined ? `<td class="${s.rr>=0?'win':'loss'}">${s.rr>0?'+':''}${s.rr}</td>` : '<td class="dim">-</td>';
    const dirClass = s.direction === 'SHORT' ? 'short' : 'long';
    return `<tr data-symbol="${s.symbol}" data-entry-time="${s.entry_time}" style="cursor:pointer;">
      <td>${s.symbol}</td><td class="${dirClass}">${s.direction || 'LONG'}</td><td>${fmt(s.entry)}</td>
      <td class="dim">rsi${s.buy_rsi}/fish${s.buy_fisher}/sell${s.sell_rsi}</td>
      <td>${statusHtml}</td>${rrTd}<td class="dim">${fmtDateTime(s.entry_time)}</td>
    </tr>`;
  }).join('');
  const signalsTableHtml = signals.length ? `
    <div style="overflow-x:auto;margin-bottom:14px;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>Параметры</th><th>Status</th><th>RR (факт)</th><th>Время входа</th></tr></thead>
      <tbody>${signalsRows}</tbody>
    </table>
    </div>` : '<div class="dim" style="margin-bottom:14px;">Живых сигналов пока нет.</div>';
  const btRows = (status.top || []).map(r => {
    const pnlClass = (r.avg_pnl_pct || 0) >= 0 ? 'win' : 'loss';
    const rr = r.avg_pnl_pct !== null && r.avg_pnl_pct !== undefined && cfg.stoploss_pct ? Math.round((r.avg_pnl_pct / (cfg.stoploss_pct*100)) * 100) / 100 : null;
    const inLive = (status.live_universe || []).includes(r.symbol);
    // v0.99.143 — solo-checkpoint columns for the 2 new GLOBAL filters,
    // reading them by "stage" out of filter_checkpoints — same style
    // as Sweep/MSNR/Mirror's own fmtCheckpoint columns (isolated solo
    // result + delta vs "raw", not the final chained result).
    const fcList = r.filter_checkpoints || [];
    const rawCp = fcList.find(c => c.stage === 'raw');
    const fmtFt5Solo = (stage, enabled) => {
      const cp = fcList.find(c => c.stage === stage);
      if (!cp || !cp.n) return '<span class="dim">нет данных</span>';
      let deltaTxt = '';
      if (rawCp && rawCp.winrate !== null && rawCp.winrate !== undefined && cp.winrate !== null && cp.winrate !== undefined) {
        const delta = Math.round((cp.winrate - rawCp.winrate) * 10) / 10;
        const deltaCls = delta > 0 ? 'win' : (delta < 0 ? 'loss' : 'dim');
        deltaTxt = ` <span class="${deltaCls}">(${delta > 0 ? '+' : ''}${delta}%)</span>`;
      }
      const onOff = enabled ? '' : ' <span class="dim">[выкл]</span>';
      return `<span class="dim" title="если применить ТОЛЬКО этот фильтр поверх остального, без него">${cp.winrate}% (n=${cp.n})${deltaTxt}${onOff}</span>`;
    };
    const htfSoloTxt = fmtFt5Solo('htf_trend', cfg.htf_filter_enabled);
    const sessionSoloTxt = fmtFt5Solo('session', cfg.session_filter_enabled);
    return `<tr>
      <td>${r.symbol}${inLive ? ' <span style="color:#3ddc97;" title="в живом скане">●</span>' : ''}</td>
      <td class="dim">rsi${r.buy_rsi}/fish${r.buy_fisher}/sell${r.sell_rsi}</td>
      <td class="${pnlClass}">${r.avg_pnl_pct>0?'+':''}${r.avg_pnl_pct}%</td>
      <td class="dim">${r.score !== null && r.score !== undefined ? r.score : '-'}</td>
      <td class="${pnlClass}">${rr !== null ? (rr>0?'+':'')+rr : '-'}</td>
      <td class="dim">n=${r.trades}</td>
      <td class="win">${r.wins}W</td>
      <td class="loss">${r.losses}L</td>
      <td>${htfSoloTxt}</td>
      <td>${sessionSoloTxt}</td>
    </tr>`;
  }).join('');
  const btTableHtml = (status.top || []).length ? `
    <div class="dim" style="margin-bottom:6px;"><b>Перебор параметров по монетам</b> (${cfg.backtest_days} дней истории, отбор по score — нижней доверительной границе среднего P&L: чем меньше выборка ИЛИ чем больше разброс (частые крупные лоссы вперемешку с выигрышами) — тем сильнее штраф, независимо от n). Зелёная точка — монета сейчас в живом скане (топ-${status.live_top_n}). Последние 2 колонки — что даёт КАЖДЫЙ новый глобальный фильтр САМ ПО СЕБЕ, поверх остального:</div>
    <div style="overflow-x:auto;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>Параметры</th><th>Avg P&L</th><th>Score</th><th>RR (факт)</th><th>n</th><th>W</th><th>L</th><th>Тренд 4ч (соло)</th><th>Сессия (соло)</th></tr></thead>
      <tbody>${btRows}</tbody>
    </table>
    </div>` : '<div class="dim">Перебор параметров ещё не готов.</div>';
  setPanelHtml(panel, warnHtml + headerHtml + signalsTableHtml + btTableHtml);
  panel.querySelectorAll('tbody tr[data-entry-time]').forEach(tr => {
    tr.onclick = () => openFt5Chart(tr.dataset.symbol, tr.dataset.entryTime);
  });
}

async function refreshMirror() {
  const status = await (await fetch('/api/mirror/status')).json();
  const signals = await (await fetch('/api/mirror/signals')).json();
  const panel = document.getElementById('mirrorPanel');
  const cfg = status.config || {};
  const ss = status.signals_stats || {};
  const ssWr = ss.winrate !== null && ss.winrate !== undefined ? `<span class="${ss.winrate >= 50 ? 'win' : 'loss'}">${ss.winrate}%</span>` : '<span class="dim">-</span>';
  // v0.99.114, per direct user question ("может без применения фильтра
  // было лучше, а после него стало хуже"): the filter-blocked pool,
  // tracked through the SAME outcome logic as real signals but never
  // actually traded — direct, real forward-data comparison against
  // ssWr above, not a backtest's own retrospective self-consistency.
  const fss = status.filtered_signals_stats || {};
  const fssWr = fss.win_rate !== null && fss.win_rate !== undefined ? `<span class="${fss.win_rate >= 50 ? 'win' : 'loss'}">${fss.win_rate}%</span>` : '<span class="dim">-</span>';
  const filterReasonLabels = {sl_width: 'широкий стоп', direction: 'слабое направление'};
  const byReasonTxt = Object.entries(fss.by_reason || {}).map(([reason, s]) => {
    const wr = s.win_rate !== null && s.win_rate !== undefined ? `${s.win_rate}%` : '-';
    return `${filterReasonLabels[reason] || reason}: ${wr} (n=${s.n})`;
  }).join(' · ');
  const patternLabels = {inside_bar: 'внутренний бар', tweezers: 'пинцет', rails: 'рельсы', engulfing_doji: 'поглощение+дожи'};
  const byPatternTxt = Object.entries(ss.by_pattern || {}).map(([p, s]) => {
    const wr = s.winrate !== null && s.winrate !== undefined ? `${s.winrate}%` : '-';
    return `${patternLabels[p] || p}: ${wr} (n=${s.n})`;
  }).join(' · ');
  const buildTxt = status.last_backtest_finished
    ? `последний бэктест: ${fmtTime(status.last_backtest_finished)} (${status.last_backtest_duration}s) · в живом скане: ${(status.live_universe||[]).length}/${(status.top||[]).length} монет (винрейт > ${cfg.live_min_winrate}%)`
    : 'бэктест ещё не завершился — живой скан новых сигналов на паузе, чтобы не стрелять неотфильтрованными монетами';
  const headerHtml = `
    <div class="dim" style="margin-bottom:8px;">
      «Зеркальный уровень» — пробитый уровень поддержки/сопротивления при возврате цены меняет роль на противоположную; вход на одном из 4 разворотных паттернов на уровне. Стоп по каждой монете дополнительно фильтруется по ширине (см. таблицу ниже — «до» и «после» фильтра).<br>
      ТФ ${cfg.interval} · RR ${cfg.rr} · допуск касания ${cfg.touch_tolerance_pct}% · допуск паттерна ${cfg.pattern_tolerance_pct}% · ${buildTxt}<br>
      <b>Живые сигналы</b>: ${ssWr} (${ss.wins||0}W/${ss.losses||0}L) · открытых: ${ss.open||0} · всего: ${ss.total||0}<br>
      ${byPatternTxt ? `<span style="font-size:11px;">По паттернам: ${byPatternTxt}</span><br>` : ''}
      <b>Отсеянные фильтром</b> <span class="dim" style="font-size:11px;">(не торговались, только для проверки — стоило ли их пропускать)</span>: ${fssWr} (${fss.wins||0}W/${fss.losses||0}L) · открытых: ${fss.open||0} · всего: ${fss.n||0}<br>
      ${byReasonTxt ? `<span style="font-size:11px;">По причине отсева: ${byReasonTxt}</span><br>` : ''}
      <span style="font-size:11px;">Зелёная точка — монета сейчас в живом скане. Клик по строке сигнала открывает график входа/выхода.</span>
    </div>`;
  const signalsRows = signals.map(s => {
    let statusHtml;
    if (s.status === 'OPEN') statusHtml = '<span class="status-open">OPEN</span>';
    else if (s.result === 'WIN') statusHtml = `<span class="win">WIN @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else if (s.result === 'LOSS') statusHtml = `<span class="loss">LOSS @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else if (s.result === 'TIMEOUT') {
      // v0.99.99, per direct user follow-up ("тайм аут тоже добавь но
      // надо знать как закрылась сделка по таймауту в плюс или минус"):
      // timeout_pnl_r is the signed R at the moment of timeout — color
      // and sign it the same way WIN/LOSS already are, instead of a
      // flat neutral label with no P&L information.
      const r = s.timeout_pnl_r;
      const rCls = (r === null || r === undefined) ? 'status-timeout' : (r >= 0 ? 'win' : 'loss');
      const rTxt = (r === null || r === undefined) ? '' : ` (${r > 0 ? '+' : ''}${r}R)`;
      statusHtml = `<span class="${rCls}">TIMEOUT @ ${fmt(s.exit_price)}${rTxt}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    } else statusHtml = '<span class="status-timeout">TIMEOUT</span>';
    const dirClass = s.direction === 'SHORT' ? 'short' : 'long';
    return `<tr data-symbol="${s.symbol}" data-time="${s.time}" style="cursor:pointer;">
      <td>${s.symbol}</td><td class="${dirClass}">${s.direction}</td>
      <td class="dim">${patternLabels[s.pattern] || s.pattern}</td>
      <td>${fmt(s.entry)}</td><td>${fmt(s.sl)}</td><td>${fmt(s.tp)}</td>
      <td>${s.rr}</td><td>${statusHtml}</td><td class="dim" title="время свечи сигнала: ${fmtDateTime(s.time)}">${s.detected_at ? fmtDateTime(s.detected_at) : fmtDateTime(s.time)}${s.detected_at && Math.abs(s.detected_at - s.time) > 120 ? ` <span style="opacity:0.5;font-size:10px;">(свеча ${fmtTime(s.time)})</span>` : ''}</td>
    </tr>`;
  }).join('');
  const signalsTableHtml = signals.length ? `
    <div style="overflow-x:auto;margin-bottom:14px;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>Dir</th><th>Паттерн</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>Status</th><th>Время</th></tr></thead>
      <tbody>${signalsRows}</tbody>
    </table>
    </div>` : '<div class="dim" style="margin-bottom:14px;">Живых сигналов пока нет.</div>';
  const btRows = (status.top || []).map(r => {
    const wrClass = (r.win_rate || 0) >= 50 ? 'win' : 'loss';
    const liveDot = r.live ? ' <span style="color:#3ddc97;" title="в живом скане">●</span>' : '';
    const skipTxt = (r.skip_sl_pct_min !== null && r.skip_sl_pct_min !== undefined)
      ? `<span class="loss">skip SL≥${r.skip_sl_pct_min}%</span>` : '<span class="dim">-</span>';
    // v0.99.98, per external code review batch 1 ("Авто-гейт по
    // паттерну"): shows which of the 4 confirmation patterns this
    // symbol's own history says fail breakeven — same skip mechanism
    // as the SL-width one above, just per-pattern instead of per-width.
    const skipPatternTxt = (r.skip_pattern && r.skip_pattern.length)
      ? `<span class="loss">skip: ${r.skip_pattern.map(p => patternLabels[p] || p).join(', ')}</span>` : '<span class="dim">-</span>';
    // v0.99.92, per direct user request ("по статистике обязательно
    // показывать до после как в msnr"): "до" — raw checkpoint (перед
    // любым фильтром), "после" — итоговая стадия ПОСЛЕ обоих фильтров
    // (ширина стопа + паттерн, v0.99.98). Оба сохранены в r.checkpoints
    // по mirror_backtest_symbol() — see that function's own docstring.
    const cps = r.checkpoints || [];
    const before = cps.find(c => c.stage === 'raw') || {};
    const after = cps.length ? cps[cps.length - 1] : {};
    const fmtWr = v => (v === null || v === undefined) ? '?' : `${v}%`;
    const fmtExp = v => (v === null || v === undefined) ? '?' : `${v > 0 ? '+' : ''}${v}R`;
    const beforeAfterTxt = cps.length
      ? `<span class="dim" title="винрейт/ожидание до всех фильтров → после">${before.n||0}→${after.n||0} · WR ${fmtWr(before.winrate)}→${fmtWr(after.winrate)} · ${fmtExp(before.expectancy_r)}→${fmtExp(after.expectancy_r)}</span>`
      : '<span class="dim">-</span>';
    // v0.99.98, per external code review batch 1 ("Разбивка статистики
    // по направлению"): LONG/SHORT breakdown, informational only for
    // now (batch 2 decides whether/how to gate on it).
    const bd = r.by_direction || {};
    const byDirTxt = (bd.LONG || bd.SHORT)
      ? `<span class="dim" title="винрейт по направлению">L: ${fmtWr(bd.LONG && bd.LONG.win_rate)} (n=${bd.LONG ? bd.LONG.n : 0}) · S: ${fmtWr(bd.SHORT && bd.SHORT.win_rate)} (n=${bd.SHORT ? bd.SHORT.n : 0})</span>`
      : '<span class="dim">-</span>';
    const tt = r.tuned_tolerance;
    const tunedTxt = tt
      ? `<span class="win" title="подобрано: train ${tt.train_winrate}% (n=${tt.train_n}) → test ${tt.test_winrate}% (n=${tt.test_n})">касание ${tt.touch_tolerance_pct}% / паттерн ${tt.pattern_tolerance_pct}%</span>`
      : '<span class="dim">общие</span>';
    // v0.99.142 — solo-checkpoint columns for the 2 new GLOBAL filters,
    // reading them by "stage" out of the SAME checkpoints chain
    // beforeAfterTxt above already draws from — matching Sweep/MSNR's
    // own fmtCheckpoint style (isolated solo result + delta vs "raw").
    const rawCp = cps.find(c => c.stage === 'raw');
    const fmtMirrorSolo = (stage, enabled) => {
      const cp = cps.find(c => c.stage === stage);
      if (!cp || !cp.n) return '<span class="dim">нет данных</span>';
      let deltaTxt = '';
      if (rawCp && rawCp.winrate !== null && rawCp.winrate !== undefined && cp.winrate !== null && cp.winrate !== undefined) {
        const delta = Math.round((cp.winrate - rawCp.winrate) * 10) / 10;
        const deltaCls = delta > 0 ? 'win' : (delta < 0 ? 'loss' : 'dim');
        deltaTxt = ` <span class="${deltaCls}">(${delta > 0 ? '+' : ''}${delta}%)</span>`;
      }
      const onOff = enabled ? '' : ' <span class="dim">[выкл]</span>';
      return `<span class="dim" title="если применить ТОЛЬКО этот фильтр поверх остальных, без него">${cp.winrate}% (n=${cp.n})${deltaTxt}${onOff}</span>`;
    };
    const volumeSoloTxt = fmtMirrorSolo('volume_filter', cfg.volume_filter_enabled);
    const htfSoloTxt = fmtMirrorSolo('htf_filter', cfg.htf_filter_enabled);
    return `<tr>
      <td>${r.symbol}${liveDot}</td>
      <td class="${wrClass}">${r.win_rate !== null && r.win_rate !== undefined ? r.win_rate+'%' : '-'}</td>
      <td class="dim">n=${r.n}</td>
      <td class="win">${r.wins}W</td>
      <td class="loss">${r.losses}L</td>
      <td class="dim">${r.timeouts}T</td>
      <td>${skipTxt}</td>
      <td>${skipPatternTxt}</td>
      <td>${byDirTxt}</td>
      <td>${beforeAfterTxt}</td>
      <td>${tunedTxt}</td>
      <td>${volumeSoloTxt}</td>
      <td>${htfSoloTxt}</td>
    </tr>`;
  }).join('');
  const btTableHtml = (status.top || []).length ? `
    <div class="dim" style="margin-bottom:6px;"><b>Бэктест по монетам</b> (${cfg.backtest_days} дней истории) — итоговый винрейт/n уже ПОСЛЕ обоих фильтров (ширина стопа + паттерн)${cfg.autotune_tolerance_enabled ? ', допуски автотюнинга — по колонке справа' : ''}. Последние 2 колонки — что даёт КАЖДЫЙ новый глобальный фильтр САМ ПО СЕБЕ, поверх остальных (не в связке с ними чем нибудь ещё):</div>
    <div style="overflow-x:auto;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>WR</th><th>n</th><th>W</th><th>L</th><th>T</th><th>Фильтр SL</th><th>Фильтр паттерна</th><th>По направлению</th><th>До → После</th><th>Допуски</th><th>Объём (соло)</th><th>Тренд 4ч (соло)</th></tr></thead>
      <tbody>${btRows}</tbody>
    </table>
    </div>` : '<div class="dim">Бэктест ещё не готов.</div>';
  setPanelHtml(panel, headerHtml + signalsTableHtml + btTableHtml);
  panel.querySelectorAll('tbody tr[data-time]').forEach(tr => {
    tr.onclick = () => openMirrorChart(tr.dataset.symbol, tr.dataset.time);
  });
}

async function refreshLsw() {
  const status = await (await fetch('/api/lsw/status')).json();
  const signals = await (await fetch('/api/lsw/signals')).json();
  const panel = document.getElementById('lswPanel');
  const cfg = status.config || {};
  const ss = status.signals_stats || {};
  const ssWr = ss.winrate !== null && ss.winrate !== undefined ? `<span class="${ss.winrate >= 50 ? 'win' : 'loss'}">${ss.winrate}%</span>` : '<span class="dim">-</span>';
  const levelTypeLabels = {high: 'снятие хаёв', low: 'снятие лоу'};
  const byLevelTxt = Object.entries(ss.by_level_type || {}).map(([lt, s]) => {
    const wr = s.winrate !== null && s.winrate !== undefined ? `${s.winrate}%` : '-';
    return `${levelTypeLabels[lt] || lt}: ${wr} (n=${s.n})`;
  }).join(' · ');
  const buildTxt = status.backtest_running
    ? `бэктест выполняется (начат ${status.backtest_started_at ? fmtTime(status.backtest_started_at) : '?'}): ${status.backtest_done||0}/${status.backtest_total||'?'} монет${status.backtest_started_at ? ' · идёт ' + Math.round((Date.now()/1000 - status.backtest_started_at)) + 'с' : ''}`
    : status.last_backtest_finished
    ? `последний бэктест: ${fmtTime(status.last_backtest_finished)} (${status.last_backtest_duration}s) · в живом скане: ${(status.live_universe||[]).length}/${(status.top||[]).length} монет (винрейт > ${cfg.live_min_winrate}%)`
    : 'бэктест ещё не завершился — живой скан новых сигналов на паузе, чтобы не показывать неотфильтрованные монеты';
  const progressPct = status.backtest_total ? Math.round((status.backtest_done||0) / status.backtest_total * 100) : 0;
  const progressBarHtml = status.backtest_running ? `
    <div style="margin:6px 0 8px;">
      <div style="background:#1c2433;border-radius:6px;height:8px;overflow:hidden;">
        <div style="background:#3ddc97;height:100%;width:${progressPct}%;transition:width 0.4s;"></div>
      </div>
      <div class="dim" style="font-size:11px;margin-top:3px;">
        ${progressPct}% · сейчас: ${(status.backtest_in_flight||[]).slice(0,6).join(', ') || '—'}${(status.backtest_in_flight||[]).length > 6 ? ` +${status.backtest_in_flight.length-6}` : ''}
      </div>
    </div>` : '';
  const headerHtml = `
    <div class="dim" style="margin-bottom:8px;">
      <b>Liquidity Sweep</b> — снятие ликвидности с равных хаёв/лоу (2+ близких максимума/минимума считаются одним уровнем); сигнал — когда свеча фитилём пробивает уровень, но закрывается обратно внутри (не пробой, а именно снятие стопов). Автоторговля и её риск настраиваются в общей вкладке «Автоторговля».<br>
      ТФ ${cfg.interval} · RR ${cfg.rr} · допуск равенства уровней ${cfg.equal_tolerance_pct}% · буфер стопа ${cfg.sl_buffer_pct}% · ${buildTxt}<br>
      ${progressBarHtml}
      Фильтр по тренду (${cfg.htf_interval}): <span class="${cfg.htf_filter_enabled ? 'win' : 'dim'}">${cfg.htf_filter_enabled ? 'включён' : 'выключен'}</span> ·
      Структурный кэп: <span class="${cfg.structural_cap_enabled ? 'win' : 'dim'}">${cfg.structural_cap_enabled ? 'включён' : 'выключен'}</span> ·
      Подтверждение (${cfg.entry_confirm_interval}): <span class="${cfg.entry_confirm_enabled ? 'win' : 'dim'}">${cfg.entry_confirm_enabled ? 'включено' : 'выключено'}</span> ·
      Фильтр по объёму: <span class="${cfg.volume_filter_enabled ? 'win' : 'dim'}">${cfg.volume_filter_enabled ? 'включён' : 'выключен'}</span> ·
      FVG: <span class="${cfg.fvg_filter_enabled ? 'win' : 'dim'}">${cfg.fvg_filter_enabled ? 'включён' : 'выключен'}</span> ·
      Сессия: <span class="${cfg.session_filter_enabled ? 'win' : 'dim'}">${cfg.session_filter_enabled ? 'включена' : 'выключена'}</span> ·
      Мин. касаний: <span class="${cfg.min_touches_enabled ? 'win' : 'dim'}">${cfg.min_touches_enabled ? 'включён' : 'выключен'}</span> ·
      Фильтр по направлению: <span class="${cfg.direction_filter_enabled ? 'win' : 'dim'}">${cfg.direction_filter_enabled ? 'включён' : 'выключен'}</span><br>
      <b>Живые сигналы</b>: ${ssWr} (${ss.wins||0}W/${ss.losses||0}L) · открытых: ${ss.open||0} · всего: ${ss.total||0}<br>
      ${byLevelTxt ? `<span style="font-size:11px;">По типу уровня: ${byLevelTxt}</span><br>` : ''}
      <span style="font-size:11px;">Зелёная точка — монета сейчас в живом скане. Клик по строке сигнала открывает график входа/выхода.</span>
    </div>`;
  const signalsRows = signals.map(s => {
    let statusHtml;
    if (s.status === 'OPEN') statusHtml = '<span class="status-open">OPEN</span>';
    else if (s.result === 'WIN') statusHtml = `<span class="win">WIN @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else if (s.result === 'LOSS') statusHtml = `<span class="loss">LOSS @ ${fmt(s.exit_price)}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    else if (s.result === 'TIMEOUT') {
      const r = s.timeout_pnl_r;
      const rCls = (r === null || r === undefined) ? 'status-timeout' : (r >= 0 ? 'win' : 'loss');
      const rTxt = (r === null || r === undefined) ? '' : ` (${r > 0 ? '+' : ''}${r}R)`;
      statusHtml = `<span class="${rCls}">TIMEOUT @ ${fmt(s.exit_price)}${rTxt}${s.exit_time ? ' ('+fmtTime(s.exit_time)+')' : ''}</span>`;
    } else statusHtml = '<span class="status-timeout">TIMEOUT</span>';
    const dirClass = s.direction === 'SHORT' ? 'short' : 'long';
    const confirmLabels = {BOS: 'BOS', ABSORPTION: 'поглощение', INVERSION: 'инверсия'};
    const confirmTxt = s.confirm_method ? (confirmLabels[s.confirm_method] || s.confirm_method) : '-';
    return `<tr data-symbol="${s.symbol}" data-time="${s.time}" style="cursor:pointer;">
      <td>${s.symbol}</td><td class="${dirClass}">${s.direction}</td>
      <td class="dim">${levelTypeLabels[s.level_type] || s.level_type} (x${s.level_touches||'?'})</td>
      <td class="dim">${confirmTxt}</td>
      <td>${fmt(s.entry)}</td><td>${fmt(s.sl)}</td><td>${fmt(s.tp)}</td>
      <td>${s.rr}</td><td>${statusHtml}</td><td class="dim" title="время свечи сигнала: ${fmtDateTime(s.time)}">${s.detected_at ? fmtDateTime(s.detected_at) : fmtDateTime(s.time)}${s.detected_at && Math.abs(s.detected_at - s.time) > 120 ? ` <span style="opacity:0.5;font-size:10px;">(свеча ${fmtTime(s.time)})</span>` : ''}</td>
    </tr>`;
  }).join('');
  const signalsTableHtml = signals.length ? `
    <div style="overflow-x:auto;margin-bottom:14px;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>Dir</th><th>Уровень</th><th>Модель входа</th><th>Entry</th><th>SL</th><th>TP</th><th>RR</th><th>Status</th><th>Время</th></tr></thead>
      <tbody>${signalsRows}</tbody>
    </table>
    </div>` : '<div class="dim" style="margin-bottom:14px;">Живых сигналов пока нет.</div>';
  const btRows = (status.top || []).map(r => {
    const wrClass = (r.win_rate || 0) >= 50 ? 'win' : 'loss';
    const liveDot = r.live ? ' <span style="color:#3ddc97;" title="в живом скане">●</span>' : '';
    const bd = r.by_direction || {};
    const fmtWr = v => (v === null || v === undefined) ? '?' : `${v}%`;
    const byDirTxt = (bd.LONG || bd.SHORT)
      ? `<span class="dim" title="винрейт по направлению">L: ${fmtWr(bd.LONG && bd.LONG.win_rate)} (n=${bd.LONG ? bd.LONG.n : 0}) · S: ${fmtWr(bd.SHORT && bd.SHORT.win_rate)} (n=${bd.SHORT ? bd.SHORT.n : 0})</span>`
      : '<span class="dim">-</span>';
    let dirFilterTxt = '';
    if (cfg.direction_filter_enabled && r.live_directions) {
      const labels = {LONG: 'только LONG', SHORT: 'только SHORT'};
      dirFilterTxt = r.live_directions.length === 2 ? ' <span class="dim">(обе стороны)</span>'
        : r.live_directions.length === 1 ? ` <span class="win">(${labels[r.live_directions[0]]})</span>`
        : ' <span class="loss">(ни одна сторона)</span>';
    }
    const fc = r.filter_checkpoints || {};
    const fmtCheckpoint = (cp, filterEnabled) => {
      if (!cp || cp.n === 0 || cp.winrate === null || cp.winrate === undefined) {
        return '<span class="dim">нет данных</span>';
      }
      const raw = fc.raw;
      let deltaTxt = '';
      if (raw && raw.winrate !== null && raw.winrate !== undefined) {
        const delta = Math.round((cp.winrate - raw.winrate) * 10) / 10;
        const deltaCls = delta > 0 ? 'win' : (delta < 0 ? 'loss' : 'dim');
        deltaTxt = ` <span class="${deltaCls}">(${delta > 0 ? '+' : ''}${delta}%)</span>`;
      }
      const onOff = filterEnabled ? '' : ' <span class="dim">[выкл]</span>';
      return `<span class="dim" title="если применить ТОЛЬКО этот фильтр к сырым сигналам, без остальных">${cp.winrate}% (n=${cp.n})${deltaTxt}${onOff}</span>`;
    };
    const confirmTxt2 = fmtCheckpoint(fc.entry_confirm, cfg.entry_confirm_enabled);
    const volumeTxt = fmtCheckpoint(fc.volume_filter, cfg.volume_filter_enabled);
    const fvgTxt = fmtCheckpoint(fc.fvg_filter, cfg.fvg_filter_enabled);
    const sessionTxt = fmtCheckpoint(fc.session_filter, cfg.session_filter_enabled);
    const touchesTxt = fmtCheckpoint(fc.min_touches_filter, cfg.min_touches_enabled);
    const structureTxt = fmtCheckpoint(fc.candle_structure, cfg.candle_structure_filter_enabled);
    return `<tr>
      <td>${r.symbol}${liveDot}${dirFilterTxt}</td>
      <td class="${wrClass}">${r.win_rate !== null && r.win_rate !== undefined ? r.win_rate+'%' : '-'}</td>
      <td class="dim">n=${r.n}</td>
      <td class="win">${r.wins}W</td>
      <td class="loss">${r.losses}L</td>
      <td class="dim">${r.timeouts}T</td>
      <td>${byDirTxt}</td>
      <td>${confirmTxt2}</td>
      <td>${volumeTxt}</td>
      <td>${fvgTxt}</td>
      <td>${sessionTxt}</td>
      <td>${touchesTxt}</td>
      <td>${structureTxt}</td>
    </tr>`;
  }).join('');
  const btTableHtml = (status.top || []).length ? `
    <div class="dim" style="margin-bottom:6px;"><b>Бэктест по монетам</b> (${cfg.backtest_days} дней истории). Последние 6 колонок показывают, что даёт КАЖДЫЙ фильтр САМ ПО СЕБЕ на сырых (нефильтрованных) сигналах монеты — не в связке с остальными фильтрами. В скобках — разница с винрейтом на тех же сырых сигналах без единого фильтра (это не то же самое, что колонка WR слева, там уже применены реально включённые фильтры). Пометка [выкл] — фильтр сейчас не участвует в реальной торговле, это просто оценка "а что если включить". Тренд-фильтр и структурный кэп по-прежнему доступны в настройках, просто убраны отсюда, чтобы не мозолить глаза:</div>
    <div style="overflow-x:auto;">
    <table style="font-size:11px;white-space:nowrap;">
      <thead><tr><th>Symbol</th><th>WR</th><th>n</th><th>W</th><th>L</th><th>T</th><th>По направлению</th><th>Подтверждение (соло)</th><th>Объём (соло)</th><th>FVG (соло)</th><th>Сессия (соло)</th><th>Касания≥${cfg.min_touches} (соло)</th><th>Структура свечи (соло)</th></tr></thead>
      <tbody>${btRows}</tbody>
    </table>
    </div>` : '<div class="dim">Бэктест ещё не готов.</div>';
  setPanelHtml(panel, headerHtml + signalsTableHtml + btTableHtml);
  panel.querySelectorAll('tbody tr[data-time]').forEach(tr => {
    tr.onclick = () => openLswChart(tr.dataset.symbol, tr.dataset.time);
  });
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
  const modeLabels = {bounce: 'Bounce', breakout: 'Breakout', scalp: 'Скальпинг', ft5: 'FT5', msnr: 'MSNR', mirror: 'Зеркало', lsw: 'Sweep'};
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

  const statusRu = {
    OPENED: 'Открыта',
    OPENED_TP_SL_FAILED: 'Открыта (стоп не встал)',
    DRY_RUN: 'Dry-run',
    SKIPPED: 'Пропущена',
    ERROR: 'Ошибка',
  };
  const rows = log.map(e => {
    const dirClass = e.direction === 'LONG' ? 'long' : (e.direction === 'SHORT' ? 'short' : 'dim');
    const statusClass = {OPENED: 'win', OPENED_TP_SL_FAILED: 'loss', DRY_RUN: 'status-open', SKIPPED: 'dim', ERROR: 'loss'}[e.status] || 'dim';
    return `<tr>
      <td class="dim">${fmtTime(e.time)}</td><td>${modeLabels[e.mode] || e.mode}</td><td>${e.symbol}</td>
      <td class="${dirClass}">${e.direction || '-'}</td>
      <td class="${statusClass}">${statusRu[e.status] || e.status}</td>
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

  setPanelHtml(panel, headerHtml + tableHtml);
}

async function refreshSimulator() {
  const [status, trades, autotradeStatus] = await Promise.all([
    (await fetch('/api/simulator/status')).json(),
    (await fetch('/api/simulator/trades')).json(),
    (await fetch('/api/autotrade/status')).json(),
  ]);
  const panel = document.getElementById('simulatorPanel');
  const modeLabels = {bounce: 'Bounce', breakout: 'Breakout', scalp: 'Скальпинг', ft5: 'FT5', msnr: 'MSNR', mirror: 'Зеркало', lsw: 'Sweep'};

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
      ? '<span class="status-open">В позиции</span>'
      : (t.result === 'WIN' ? '<span class="win">Профит</span>' : (t.result === 'LOSS' ? '<span class="loss">Стоп</span>' : '<span class="status-timeout">Таймаут</span>'));
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

  setPanelHtml(panel, headerHtml + tableHtml);
}

async function refreshAll() {
  await refreshStatus();
  await refreshOverview();
  await refreshAutotradeBanner();
  await refreshSignals();
  if (activeTab === 'signals') await refreshTuning();
  if (activeTab === 'scalp') await refreshScalp();
  if (activeTab === 'msnr') await refreshMsnr();
  if (activeTab === 'ft5') await refreshFt5();
  if (activeTab === 'mirror') await refreshMirror();
  if (activeTab === 'lsw') await refreshLsw();
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
  'Удалить статистику и подобранные параметры Volume Profile (Сигналы/Watchlist/Тюнинг)? Это необратимо.',
  'Очистить объём');
wireResetButton('resetScalpBtn', '/api/reset/scalp',
  'Удалить накопленную статистику скальпинга (вселенная, данные по монетам, рекомендации)? Остальное не тронет. Это необратимо.',
  'Очистить скальпинг');
wireResetButton('resetMsnrBtn', '/api/reset/msnr',
  'Удалить накопленный бэктест и сигналы MSNR? Остальное не тронет. Это необратимо.',
  'Очистить MSNR');
wireResetButton('resetFt5Btn', '/api/reset/ft5',
  'Удалить накопленный анализ параметров и сигналы экспериментального FT5? Остальное не тронет. Это необратимо.',
  'Очистить FT5');
wireResetButton('resetMirrorBtn', '/api/reset/mirror',
  'Удалить накопленный бэктест и сигналы Зеркала? Остальное не тронет. Это необратимо.',
  'Очистить Зеркало');
wireResetButton('resetLswBtn', '/api/reset/lsw',
  'Удалить накопленный бэктест и сигналы Sweep? Остальное не тронет. Это необратимо.',
  'Очистить Sweep');
wireResetButton('resetRiskAutotuneBtn', '/api/reset/risk_autotune',
  'Сбросить все параметры авто-тюнинга риска (EMA/Скальпинг/Сессия) к значениям по умолчанию из кода, очистить лог и cooldown? Сами сигналы и статистику не тронет. Это необратимо.',
  'Сбросить авто-тюнинг');
wireResetButton('resetSimulatorBtn', '/api/simulator/reset',
  'Сбросить симулятор баланса к стартовому значению и удалить всю историю сделок? Это необратимо.',
  'Сбросить симулятор');

// ---------------- Settings modal ----------------
const settingsModal = document.getElementById('settingsModal');
const setInputs = {
  volume_profile_enabled: document.getElementById('setVolumeProfile'),
  bounce_enabled: document.getElementById('setBounce'),
  breakout_enabled: document.getElementById('setBreakout'),
  scalp_enabled: document.getElementById('setScalp'),
  scalp_signals_enabled: document.getElementById('setScalpSignals'),
  msnr_enabled: document.getElementById('setMsnr'),
  msnr_addon_enabled: document.getElementById('setMsnrAddon'),
  msnr_min_rr_filter_enabled: document.getElementById('setMsnrMinRrFilter'),
  msnr_htf_filter_enabled: document.getElementById('setMsnrHtfFilter'),
  ft5_enabled: document.getElementById('setFt5'),
  ft5_invert_signals: document.getElementById('setFt5Invert'),
  ft5_htf_filter_enabled: document.getElementById('setFt5HtfFilter'),
  ft5_session_filter_enabled: document.getElementById('setFt5SessionFilter'),
  mirror_enabled: document.getElementById('setMirror'),
  mirror_autotune_tolerance_enabled: document.getElementById('setMirrorAutotuneTolerance'),
  mirror_volume_filter_enabled: document.getElementById('setMirrorVolumeFilter'),
  mirror_htf_filter_enabled: document.getElementById('setMirrorHtfFilter'),
  lsw_enabled: document.getElementById('setLsw'),
  lsw_htf_filter_enabled: document.getElementById('setLswHtfFilter'),
  lsw_structural_cap_enabled: document.getElementById('setLswStructuralCap'),
  lsw_volume_filter_enabled: document.getElementById('setLswVolumeFilter'),
  lsw_fvg_filter_enabled: document.getElementById('setLswFvgFilter'),
  lsw_session_filter_enabled: document.getElementById('setLswSessionFilter'),
  lsw_min_touches_enabled: document.getElementById('setLswMinTouches'),
  lsw_candle_structure_filter_enabled: document.getElementById('setLswCandleStructureFilter'),
  lsw_entry_confirm_enabled: document.getElementById('setLswEntryConfirm'),
  lsw_direction_filter_enabled: document.getElementById('setLswDirectionFilter'),
  telegram_enabled: document.getElementById('setTelegram'),
  telegram_alerts_vp: document.getElementById('setTelegramVp'),
  telegram_alerts_hourly: document.getElementById('setTelegramHourly'),
  telegram_alerts_msnr: document.getElementById('setTelegramMsnr'),
  telegram_alerts_ft5: document.getElementById('setTelegramFt5'),
  telegram_alerts_mirror: document.getElementById('setTelegramMirror'),
  telegram_alerts_lsw: document.getElementById('setTelegramLsw'),
  telegram_alerts_network: document.getElementById('setTelegramNetwork'),
  autotrade_dry_run: document.getElementById('setAutotradeDryRun'),
  autotrade_bounce: document.getElementById('setAutotradeBounce'),
  autotrade_breakout: document.getElementById('setAutotradeBreakout'),
  autotrade_scalp: document.getElementById('setAutotradeScalp'),
  scalp_martingale_enabled: document.getElementById('setScalpMartingaleEnabled'),
  // v0.99.105 — see this same key's own note in Python's apply_settings():
  // AUTOTRADE_ENABLED_MSNR is a genuine master switch layered ON TOP of the
  // 6 individual per-symbol toggles in the MSNR panel itself, not a
  // replacement for them (v0.99.18 removed the checkbox HERE specifically
  // because the constant wasn't checked anywhere in the real firing
  // decision back then — now it is, so the checkbox is back and genuinely
  // functional, not decorative).
  autotrade_msnr: document.getElementById('setAutotradeMsnr'),
  autotrade_mirror: document.getElementById('setAutotradeMirror'),
  autotrade_lsw: document.getElementById('setAutotradeLsw'),
};

const setValueInputs = {
  mirror_rr: document.getElementById('setMirrorRR'),
  lsw_rr: document.getElementById('setLswRR'),
  autotrade_risk_pct: document.getElementById('setAutotradeRiskPct'),
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
    // v0.99.82 — pass this signal's own time (already on every row —
    // see fmtTime(r.time) in the same table) so the backend anchors
    // candles/profile to THIS historical moment instead of always
    // "whatever's most recent" — see api_profile()'s own docstring for
    // the full incident this fixes.
    const timeParam = row.time !== undefined && row.time !== null ? `&time=${row.time}` : '';
    const data = await (await fetch(`/api/profile/${row.symbol}?reason=${reason}${timeParam}`)).json();
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
      // v0.99.82 — same anchoring as openChart() above, same reasoning:
      // stay consistent with whichever candle window is already shown
      // (this signal's own historical time) rather than switching to
      // "latest" just because the params were re-optimized.
      const timeParam = currentRow.time !== undefined && currentRow.time !== null ? `&time=${currentRow.time}` : '';
      const data = await (await fetch(`/api/profile/${currentRow.symbol}?reason=${reason}${timeParam}`)).json();
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

// ---------------- MSNR chart modal ----------------
const msnrModal = document.getElementById('msnrModal');
document.getElementById('msnrCloseBtn').onclick = () => msnrModal.classList.remove('open');

// ---------------- FT5 chart modal ----------------
// Own modal/canvas rather than reusing Session's — FT5's shape is
// meaningfully different (no session range box, no single fixed TP;
// instead entry/stoploss lines plus the actual realized exit point),
// so force-reusing drawSessionChart would either draw a meaningless
// empty range box or need extra branching inside a function this app
// already has working for Session/Session NY. A new, small, self-
// contained function is safer than complicating a working one.
const ft5Modal = document.getElementById('ft5Modal');
document.getElementById('ft5CloseBtn').onclick = () => ft5Modal.classList.remove('open');

async function openFt5Chart(symbol, entryTime) {
  document.getElementById('ft5ModalTitle').textContent = symbol;
  document.getElementById('ft5ModalParams').textContent = 'загрузка...';
  ft5Modal.classList.add('open');
  try {
    const data = await (await fetch(`/api/ft5/chart/${symbol}?entry_time=${entryTime}`)).json();
    if (data.error) { document.getElementById('ft5ModalParams').textContent = data.error; return; }
    const resTxt = data.result ? ` · ${data.result}${data.exit_reason ? ' ('+data.exit_reason+')' : ''}${data.pnl_pct !== null && data.pnl_pct !== undefined ? ' ' + (data.pnl_pct>0?'+':'') + data.pnl_pct + '%' : ''}${data.rr !== null && data.rr !== undefined ? ' · RR ' + (data.rr>0?'+':'') + data.rr : ''}` : ' · OPEN';
    document.getElementById('ft5ModalParams').textContent =
      `${fmtDateTime(entryTime)} · LONG · entry ${fmtNum(data.entry)} · SL ${fmtNum(data.sl)}${resTxt}`;
    drawFt5Chart(data);
  } catch (e) {
    document.getElementById('ft5ModalParams').textContent = `ошибка загрузки: ${e}`;
  }
}

function drawFt5Chart(data) {
  const canvas = document.getElementById('ft5ChartCanvas');
  const wrap = document.getElementById('ft5ChartWrap');
  const dpr = window.devicePixelRatio || 1;
  const W = wrap.clientWidth, H = wrap.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const candles = data.candles || [];
  if (!candles.length) return;
  const entry = data.entry, sl = data.sl;
  const exitPrice = data.exit_price;

  const padRight = 54;
  const chartW = W - padRight;
  const n = candles.length;
  const slot = chartW / n;
  const bodyW = Math.max(1, slot * 0.6);
  const xAt = (i) => i * slot + slot / 2;

  // computeYRangeSimple wants (entry, sl, tp) as its 3 reference prices —
  // FT5 has no single tp, so the exit price (if closed) fills that slot;
  // while still open, pass entry twice so the range still includes SL.
  const { hi, lo } = computeYRangeSimple(candles, entry, sl, exitPrice !== null && exitPrice !== undefined ? exitPrice : entry);
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

  const drawLevelLine = (price, color, label) => {
    const yy = yP(price);
    ctx.strokeStyle = color;
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(chartW, yy); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = color;
    ctx.font = 'bold 10px sans-serif';
    ctx.fillText(label, 4, yy - 3);
  };
  drawLevelLine(entry, '#5a9fff', 'ENTRY');
  drawLevelLine(sl, '#ff6b6b', 'SL');

  const entryIdx = candles.findIndex(c => c.time === data.entry_time);
  if (entryIdx >= 0) {
    const ex = xAt(entryIdx);
    ctx.fillStyle = '#5a9fff';
    ctx.beginPath(); ctx.arc(ex, yP(entry), 4, 0, Math.PI * 2); ctx.fill();
  }
  if (data.exit_time && exitPrice !== null && exitPrice !== undefined) {
    const exitIdx = candles.findIndex(c => c.time === data.exit_time);
    if (exitIdx >= 0) {
      const exx = xAt(exitIdx);
      ctx.fillStyle = data.result === 'WIN' ? '#3ddc97' : (data.result === 'LOSS' ? '#ff6b6b' : '#e0a030');
      ctx.beginPath(); ctx.arc(exx, yP(exitPrice), 4, 0, Math.PI * 2); ctx.fill();
    }
  }
}

// ---------------- VGI chart modal ----------------
// Own modal/canvas, same reasoning as FT5's — but VGI's shape is actually
// simpler and closer to Session's original (one fixed entry/sl/tp triple
// per signal, no ROI ladder, no missing-TP case), just kept separate
// rather than force-reusing drawSessionChart to avoid any risk to a
// function already working for two other modules.
const vgiModal = document.getElementById('vgiModal');
document.getElementById('vgiCloseBtn').onclick = () => vgiModal.classList.remove('open');

async function openVgiChart(symbol, sigTime, endpoint, extraQuery = '') {
  // v0.99.83, per direct user request ("удалить все что связано с
  // дивергенцией, ема, сессия, сессия ny, xau lg, vgi... будто и не
  // было"): VGI itself is gone, but this modal/canvas is now genuinely
  // SHARED infrastructure — openScalpChart()/openXauLgChart() below
  // both still call it, always with their OWN explicit endpoint (never
  // relying on a default). `endpoint` lost its old '/api/vgi/chart'
  // default value, which pointed at a now-deleted route — no default
  // at all now, so a future caller that forgets to pass one gets an
  // immediate, obvious error instead of silently hitting a 404. Not
  // renamed away from "Vgi" in the function/element names themselves
  // (vgiModal, drawVgiChart, etc.) — cosmetic only, a bigger and
  // riskier touch than this removal pass needs; the underlying DOM/
  // canvas machinery works exactly the same regardless of what it's
  // called.
  document.getElementById('vgiModalTitle').textContent = symbol;
  document.getElementById('vgiModalParams').textContent = 'загрузка...';
  vgiModal.classList.add('open');
  try {
    const data = await (await fetch(`${endpoint}/${symbol}?time=${sigTime}${extraQuery}`)).json();
    if (data.error) { document.getElementById('vgiModalParams').textContent = data.error; return; }
    const resTxt = data.result ? ` · ${data.result}${data.exit_price !== null && data.exit_price !== undefined ? ' @ '+fmtNum(data.exit_price) : ''}` : ' · OPEN';
    // v0.99.103 — pattern name, MIRROR-only field (harmlessly absent
    // for every other chart type this same function draws), matching
    // the RU labels already used on the Зеркало tab itself.
    const mirrorPatternLabels = {inside_bar: 'внутренний бар', tweezers: 'пинцет', rails: 'рельсы', engulfing_doji: 'поглощение на дожи'};
    const patternTxt = data.pattern ? ` · ${mirrorPatternLabels[data.pattern] || data.pattern}` : '';
    // v0.99.148 — source-specific context in the params line
    let sourceTxt = '';
    if (data.chart_source === 'mirror' && data.level_price) {
      const isLow = data.level_type === 'low';
      sourceTxt = ` · уровень зеркала ${fmtNum(data.level_price)} (${isLow ? 'быв.подд.→сопр.' : 'быв.сопр.→подд.'})`;
    } else if (data.chart_source === 'lsw' && data.level_price) {
      const isHigh = data.level_type === 'high';
      sourceTxt = ` · уровень снятия ${fmtNum(data.level_price)} (${isHigh ? 'равные хаи' : 'равные лоу'}${data.level_touches ? ', ' + data.level_touches + ' кас.' : ''})`;
    }
    document.getElementById('vgiModalParams').textContent =
      `${fmtDateTime(sigTime)} · ${data.direction} · entry ${fmtNum(data.entry)} · SL ${fmtNum(data.sl)} · TP ${fmtNum(data.tp)} · RR ${data.rr}${patternTxt}${sourceTxt}${resTxt}`;
    drawVgiChart(data);
  } catch (e) {
    document.getElementById('vgiModalParams').textContent = `ошибка загрузки: ${e}`;
  }
}

function openScalpChart(symbol, interval, sigTime) {
  // Thin wrapper, not a duplicate — Scalp's signal shape (fixed entry/
  // target_price/sl_price) is structurally identical to VGI's, so this
  // reuses the exact same modal/canvas (openVgiChart/drawVgiChart)
  // rather than duplicating ~90 lines of canvas drawing code. Same
  // reuse-when-genuinely-identical judgment call already applied to
  // Session NY's chart in v0.94.0.
  return openVgiChart(symbol, sigTime, '/api/scalp/chart', `&interval=${interval}`);
}

function openMirrorChart(symbol, sigTime) {
  // Same reuse judgment as openScalpChart/openXauLgChart above —
  // MIRROR's own signal shape (fixed entry/sl/tp/direction/rr) is
  // structurally identical to VGI's.
  return openVgiChart(symbol, sigTime, '/api/mirror/chart', '');
}

function openLswChart(symbol, sigTime) {
  // Same reuse judgment as openMirrorChart above — LSW's own signal
  // shape (fixed entry/sl/tp/direction/rr) is structurally identical too.
  return openVgiChart(symbol, sigTime, '/api/lsw/chart', '');
}

function drawVgiChart(data) {
  const canvas = document.getElementById('vgiChartCanvas');
  const wrap = document.getElementById('vgiChartWrap');
  const dpr = window.devicePixelRatio || 1;
  const W = wrap.clientWidth, H = wrap.clientHeight;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const candles = data.candles || [];
  if (!candles.length) return;
  const entry = data.entry, sl = data.sl, tp = data.tp;
  const exitPrice = data.exit_price;

  const padRight = 54;
  const chartW = W - padRight;
  const n = candles.length;
  const slot = chartW / n;
  const bodyW = Math.max(1, slot * 0.6);
  const xAt = (i) => i * slot + slot / 2;

  const { hi, lo } = computeYRangeSimple(candles, entry, sl, tp);
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

  const drawLevelLine = (price, color, label) => {
    const yy = yP(price);
    ctx.strokeStyle = color;
    ctx.setLineDash([5, 4]);
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, yy); ctx.lineTo(chartW, yy); ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = color;
    ctx.font = 'bold 10px sans-serif';
    ctx.fillText(label, 4, yy - 3);
  };
  drawLevelLine(entry, '#5a9fff', 'ENTRY');
  drawLevelLine(sl, '#ff6b6b', 'SL');
  drawLevelLine(tp, '#3ddc97', 'TP');
  // v0.99.148 — chart_source-aware extra level line: each module
  // draws its own meaningful context line instead of every chart always
  // showing "ЗЕРКАЛО", per direct user report ("на всех графиках линия
  // зеркала всегда видна, то есть на всех индикаторах"). Mirror: the
  // broken support/resistance level the price is returning to (same as
  // before, just now gated on chart_source). LSW: the equal-highs/lows
  // level that was swept. Scalp, MSNR: no extra level (MSNR has its
  // own separate pivot rendering path; Scalp doesn't carry one).
  const src = data.chart_source;
  if (data.level_price !== undefined && data.level_price !== null) {
    if (src === 'mirror') {
      const isLow = data.level_type === 'low';
      drawLevelLine(data.level_price, '#c792ea', isLow ? 'ЗЕРКАЛО (быв. подд. → сопр.)' : 'ЗЕРКАЛО (быв. сопр. → подд.)');
    } else if (src === 'lsw') {
      const isHigh = data.level_type === 'high';
      drawLevelLine(data.level_price, '#f0a030', isHigh ? 'УРОВЕНЬ (равные хаи → снятие)' : 'УРОВЕНЬ (равные лоу → снятие)');
    }
    // scalp / msnr / unknown: no extra level line — MSNR has its own
    // pivot rendering path; scalp doesn't carry a named level at all
  }

  const sigIdx = candles.findIndex(c => c.time === data.time);
  if (sigIdx >= 0) {
    const sx = xAt(sigIdx);
    ctx.fillStyle = '#5a9fff';
    ctx.beginPath(); ctx.arc(sx, yP(entry), 4, 0, Math.PI * 2); ctx.fill();
  }
  if (data.exit_time && exitPrice !== null && exitPrice !== undefined) {
    const exitIdx = candles.findIndex(c => c.time === data.exit_time);
    if (exitIdx >= 0) {
      const exx = xAt(exitIdx);
      ctx.fillStyle = data.result === 'WIN' ? '#3ddc97' : '#ff6b6b';
      ctx.beginPath(); ctx.arc(exx, yP(exitPrice), 4, 0, Math.PI * 2); ctx.fill();
    }
  }
}

window.addEventListener('resize', () => {
  if (modal.classList.contains('open') && currentData) {
    drawChart(currentData, currentRow);
  }
  if (msnrModal.classList.contains('open') && currentMsnrData) {
    drawMsnrChart(currentMsnrData);
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
    threading.Thread(target=msnr_backtest_loop, daemon=True).start()
    threading.Thread(target=msnr_live_loop, daemon=True).start()
    threading.Thread(target=msnr_backtest_watchdog, daemon=True).start()
    threading.Thread(target=ft5_backtest_loop, daemon=True).start()
    threading.Thread(target=ft5_live_loop, daemon=True).start()
    threading.Thread(target=mirror_backtest_loop, daemon=True).start()
    threading.Thread(target=mirror_live_loop, daemon=True).start()
    threading.Thread(target=lsw_backtest_loop, daemon=True).start()
    threading.Thread(target=lsw_live_loop, daemon=True).start()
    threading.Thread(target=reconcile_loop, daemon=True).start()
    threading.Thread(target=risk_autotune_loop, daemon=True).start()
    port = int(os.environ.get("VP_PORT", 8080))
    tg_status = "настроен" if (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID) else "не настроен"
    print(f"VP-POC Screener v{APP_VERSION} — http://127.0.0.1:{port} — Telegram: {tg_status}")
    app.run(host="0.0.0.0", port=port, threaded=True)
