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
"""

import os
import json
import time
import threading
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, jsonify, request, Response

APP_VERSION = "0.1.2"

# ----------------------------------------------------------------------------
# Config (env-overridable, no secrets required for base functionality)
# ----------------------------------------------------------------------------
GATE_BASE = "https://api.gateio.ws/api/v4"

SEGS = int(os.environ.get("VP_SEGS", 100))                # grid levels in profile
LOOKBACK = int(os.environ.get("VP_LOOKBACK", 100))        # candles used to build profile
INTERVAL = os.environ.get("VP_INTERVAL", "5m")            # candle timeframe
HVN_TOP_N = int(os.environ.get("VP_HVN_TOP_N", 6))        # top bins considered "high volume"
MIN_VOL_USD = float(os.environ.get("VP_MIN_VOL_USD", 500000))  # min 24h quote volume filter
MAX_SYMBOLS = int(os.environ.get("VP_MAX_SYMBOLS", 150))  # universe cap
SCAN_INTERVAL_SEC = int(os.environ.get("VP_SCAN_INTERVAL", 45))
COOLDOWN_SEC = int(os.environ.get("VP_COOLDOWN", 900))    # per symbol+zone re-alert cooldown
WORKERS = int(os.environ.get("VP_WORKERS", 8))
SIGNAL_HISTORY = 200
RR = float(os.environ.get("VP_RR", 1.5))                  # take-profit distance as a multiple of risk
ZONE_BUFFER_PCT = float(os.environ.get("VP_ZONE_BUFFER_PCT", 0.15))  # stop sits this far beyond the zone edge (fraction of zone height)
SIGNAL_TIMEOUT_SEC = int(os.environ.get("VP_SIGNAL_TIMEOUT", 6 * 3600))  # close as TIMEOUT if neither TP/SL hit

TELEGRAM_BOT_TOKEN = os.environ.get("VP_TG_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("VP_TG_CHAT", "")

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
    "last_scan_started": None,
    "last_scan_finished": None,
    "last_scan_duration": None,
    "errors": deque(maxlen=30),
}
_cooldowns = {}  # (symbol, zone_key) -> last_alert_ts


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


def get_candles(symbol, interval=INTERVAL, limit=LOOKBACK + 5):
    r = requests.get(
        f"{GATE_BASE}/futures/usdt/candlesticks",
        params={"contract": symbol, "interval": interval, "limit": limit},
        timeout=HTTP_TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()
    # Gate.io returns oldest->newest already; fields: t,v,c,h,l,o,sum (varies by version)
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


def get_tickers():
    r = requests.get(f"{GATE_BASE}/futures/usdt/tickers", timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return r.json()


def build_universe():
    # Volume fields (volume_24h_quote/_settle/_base) live on the /tickers
    # endpoint, not /contracts — /contracts has no volume data at all.
    tickers = get_tickers()
    scored = []
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
        scored.append((name, vol))
    scored.sort(key=lambda x: -x[1])
    return [s[0] for s in scored[:MAX_SYMBOLS]]


# ----------------------------------------------------------------------------
# Volume profile (fixed range, bar-level proportional overlap)
# Mirrors the Pine Script logic: split [lowest_low, highest_high] into SEGS
# bins, then for every candle in the lookback window distribute its volume
# across the bins it overlaps, weighted by the fraction of the candle's
# high-low range inside each bin.
# ----------------------------------------------------------------------------
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
    bin_vols = [0.0] * segs

    for c in window:
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

    return {"borders": borders, "bin_vols": bin_vols, "hh": hh, "ll": ll, "inc": inc}


def extract_hvn_zones(profile, top_n=HVN_TOP_N):
    """Take the top_n highest-volume bins and merge adjacent ones into
    contiguous high-volume-node zones."""
    borders = profile["borders"]
    bin_vols = profile["bin_vols"]
    segs = len(bin_vols)
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
        vol = sum(bin_vols[lo:hi + 1])
        zones.append({"top": top, "bottom": bottom, "mid": (top + bottom) / 2, "volume": vol})

    zones.sort(key=lambda z: -z["volume"])
    return zones


def poc_zone(zones):
    return zones[0] if zones else None


# ----------------------------------------------------------------------------
# Signal detection: bounce / rejection off an HVN zone
# ----------------------------------------------------------------------------
def detect_signal(candles, zones):
    if len(candles) < 3 or not zones:
        return None
    prev, last = candles[-2], candles[-1]
    for zone in zones:
        top, bottom = zone["top"], zone["bottom"]
        touched = last["low"] <= top and last["high"] >= bottom
        if not touched:
            continue
        if prev["close"] > top and last["close"] > top:
            return {"direction": "LONG", "zone": zone, "price": last["close"], "time": last["time"]}
        if prev["close"] < bottom and last["close"] < bottom:
            return {"direction": "SHORT", "zone": zone, "price": last["close"], "time": last["time"]}
    return None


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


def compute_tp_sl(direction, entry, zone):
    """Stop sits just beyond the far edge of the HVN zone (the level that,
    if broken, invalidates the bounce). Take-profit is RR multiples of that
    risk distance."""
    zone_height = max(zone["top"] - zone["bottom"], entry * 0.0005)
    buffer = max(zone_height * ZONE_BUFFER_PCT, entry * 0.0005)
    if direction == "LONG":
        sl = zone["bottom"] - buffer
        risk = entry - sl
        tp = entry + risk * RR
    else:
        sl = zone["top"] + buffer
        risk = sl - entry
        tp = entry - risk * RR
    return sl, tp, risk


# ----------------------------------------------------------------------------
# Telegram
# ----------------------------------------------------------------------------
def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=HTTP_TIMEOUT,
        )
    except Exception as e:
        log_error(f"telegram send failed: {e}")


# ----------------------------------------------------------------------------
# Per-symbol scan
# ----------------------------------------------------------------------------
def scan_symbol(symbol):
    try:
        candles = get_candles(symbol)
        if len(candles) < 20:
            return
        profile = compute_profile(candles)
        if not profile:
            return
        zones = extract_hvn_zones(profile)
        if not zones:
            return
        price = candles[-1]["close"]
        nz, dist = nearest_zone_distance(price, zones)
        poc = poc_zone(zones)

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

        sig = detect_signal(candles, zones)
        if sig:
            zone_key = round(sig["zone"]["mid"], 6)
            key = (symbol, zone_key)
            now = time.time()
            last_ts = _cooldowns.get(key, 0)
            if now - last_ts >= COOLDOWN_SEC:
                _cooldowns[key] = now
                sl, tp, risk = compute_tp_sl(sig["direction"], sig["price"], sig["zone"])
                record = {
                    "symbol": symbol,
                    "direction": sig["direction"],
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
                }
                with state_lock:
                    STATE["signals"].appendleft(record)
                arrow = "\u2b06\ufe0f LONG" if sig["direction"] == "LONG" else "\u2b07\ufe0f SHORT"
                send_telegram(
                    f"{arrow} {symbol}\n"
                    f"entry: {sig['price']:.6g}\n"
                    f"SL: {sl:.6g}  TP: {tp:.6g}  (RR {RR:g})\n"
                    f"HVN zone: {sig['zone']['bottom']:.6g} - {sig['zone']['top']:.6g}\n"
                    f"reason: bounce off high-volume node"
                )
    except Exception as e:
        log_error(f"{symbol}: {e}")


def close_signal(sig, result, exit_price):
    with state_lock:
        sig["status"] = "CLOSED"
        sig["result"] = result
        sig["exit_price"] = exit_price
        sig["closed_at"] = time.time()
    if result in ("WIN", "LOSS"):
        arrow = "\u2705" if result == "WIN" else "\u274c"
        send_telegram(f"{arrow} {sig['symbol']} {sig['direction']} closed: {result} @ {exit_price:.6g}")


def update_signal_outcomes():
    with state_lock:
        open_signals = [s for s in STATE["signals"] if s.get("status") == "OPEN"]
    for sig in open_signals:
        try:
            candles = get_candles(sig["symbol"], interval=INTERVAL, limit=200)
            relevant = [c for c in candles if c["time"] >= sig["time"]]
            hit = False
            for c in relevant:
                if sig["direction"] == "LONG":
                    if c["low"] <= sig["sl"]:
                        close_signal(sig, "LOSS", sig["sl"])
                        hit = True
                        break
                    if c["high"] >= sig["tp"]:
                        close_signal(sig, "WIN", sig["tp"])
                        hit = True
                        break
                else:
                    if c["high"] >= sig["sl"]:
                        close_signal(sig, "LOSS", sig["sl"])
                        hit = True
                        break
                    if c["low"] <= sig["tp"]:
                        close_signal(sig, "WIN", sig["tp"])
                        hit = True
                        break
            if not hit and time.time() - sig["detected_at"] > SIGNAL_TIMEOUT_SEC:
                last_price = candles[-1]["close"] if candles else sig["entry"]
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
    return {
        "open": open_count, "wins": wins, "losses": losses,
        "timeouts": timeouts, "winrate": winrate, "closed_total": total,
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
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                futs = [ex.submit(scan_symbol, s) for s in universe]
                for _ in as_completed(futs):
                    pass
            update_signal_outcomes()
            t1 = time.time()
            with state_lock:
                STATE["last_scan_finished"] = t1
                STATE["last_scan_duration"] = round(t1 - t0, 1)
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
        return jsonify({
            "version": APP_VERSION,
            "universe_size": STATE["universe_size"],
            "last_scan_started": STATE["last_scan_started"],
            "last_scan_finished": STATE["last_scan_finished"],
            "last_scan_duration": STATE["last_scan_duration"],
            "errors": list(STATE["errors"])[-10:],
            "stats": stats,
            "config": {
                "segs": SEGS, "lookback": LOOKBACK, "interval": INTERVAL,
                "hvn_top_n": HVN_TOP_N, "min_vol_usd": MIN_VOL_USD,
                "max_symbols": MAX_SYMBOLS, "scan_interval": SCAN_INTERVAL_SEC,
                "cooldown": COOLDOWN_SEC, "rr": RR,
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


@app.route("/api/profile/<symbol>")
def api_profile(symbol):
    interval = request.args.get("interval", INTERVAL)
    try:
        candles = get_candles(symbol, interval=interval, limit=LOOKBACK + 5)
        profile = compute_profile(candles, segs=SEGS, lookback=LOOKBACK)
        if not profile:
            return jsonify({"error": "not enough data"}), 400
        zones = extract_hvn_zones(profile)
        return jsonify({
            "symbol": symbol,
            "candles": candles[-LOOKBACK:],
            "borders": profile["borders"],
            "bin_vols": profile["bin_vols"],
            "zones": zones,
        })
    except Exception as e:
        log_error(f"api_profile {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


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
  #modal { position:fixed; inset:0; background:rgba(5,7,12,.92); display:none; z-index:20; }
  #modal.open { display:flex; flex-direction:column; }
  #modalHeader { padding:12px; display:flex; justify-content:space-between; align-items:center; }
  #modalHeader h2 { font-size:15px; margin:0; }
  #closeBtn { background:#1e2a3f; border:none; color:#fff; padding:6px 12px; border-radius:8px; font-size:13px; }
  #chartWrap { flex:1; overflow:hidden; padding:0 8px 8px; }
  canvas { width:100%; height:100%; display:block; background:#0d1017; border-radius:8px; }
  .dim { color:#8b98ab; }
  .empty { padding:30px 14px; text-align:center; color:#6b7688; font-size:13px; }
</style>
</head>
<body>
<header>
  <h1>VP-POC Screener</h1>
  <div id="status">загрузка...</div>
  <div id="stats" class="dim" style="margin-top:2px;font-size:11px;"></div>
</header>
<div class="tabs">
  <div class="tab active" data-tab="signals">Сигналы</div>
  <div class="tab" data-tab="watch">Watchlist</div>
</div>
<div class="panel">
  <table id="signalsTable" style="display:table">
    <thead><tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>Status</th><th>Time</th></tr></thead>
    <tbody></tbody>
  </table>
  <table id="watchTable" style="display:none">
    <thead><tr><th>Symbol</th><th>Price</th><th>Nearest zone</th><th>Dist %</th></tr></thead>
    <tbody></tbody>
  </table>
  <div class="empty" id="emptyMsg" style="display:none">Пока нет данных</div>
</div>

<div id="modal">
  <div id="modalHeader">
    <h2 id="modalTitle">-</h2>
    <button id="closeBtn">Закрыть</button>
  </div>
  <div id="chartWrap"><canvas id="chartCanvas"></canvas></div>
</div>

<script>
const fmt = (n, d=6) => n === null || n === undefined ? '-' : Number(n).toPrecision(d).replace(/\\.?0+$/,'').replace(/\\.$/, '');
const fmtTime = (t) => t ? new Date(t*1000).toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'}) : '-';

let activeTab = 'signals';
document.querySelectorAll('.tab').forEach(el => {
  el.onclick = () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    activeTab = el.dataset.tab;
    document.getElementById('signalsTable').style.display = activeTab === 'signals' ? 'table' : 'none';
    document.getElementById('watchTable').style.display = activeTab === 'watch' ? 'table' : 'none';
  };
});

async function refreshStatus() {
  try {
    const s = await (await fetch('/api/status')).json();
    const el = document.getElementById('status');
    const scanTxt = s.last_scan_finished ? `скан ${s.last_scan_duration}s, ${s.universe_size} пар` : 'сканирование...';
    el.textContent = `v${s.version} · ${scanTxt}`;
    const st = s.stats || {};
    const wr = st.winrate !== null && st.winrate !== undefined ? `${st.winrate}%` : '-';
    document.getElementById('stats').textContent =
      `Винрейт: ${wr} (${st.wins||0}W / ${st.losses||0}L, timeout ${st.timeouts||0}) · открытых: ${st.open||0} · RR ${s.config ? s.config.rr : ''}`;
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
    if (r.status === 'OPEN') {
      statusHtml = `<span class="status-open">OPEN</span>`;
    } else if (r.result === 'WIN') {
      statusHtml = `<span class="win">WIN @ ${fmt(r.exit_price)}</span>`;
    } else if (r.result === 'LOSS') {
      statusHtml = `<span class="loss">LOSS @ ${fmt(r.exit_price)}</span>`;
    } else {
      statusHtml = `<span class="status-timeout">TIMEOUT</span>`;
    }
    tr.innerHTML = `<td>${r.symbol}</td>
      <td class="${r.direction==='LONG'?'long':'short'}">${r.direction}</td>
      <td>${fmt(r.entry)}</td>
      <td class="dim">${fmt(r.sl)}</td>
      <td class="dim">${fmt(r.tp)}</td>
      <td>${statusHtml}</td>
      <td class="dim">${fmtTime(r.time)}</td>`;
    tr.onclick = () => openChart(r.symbol);
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
    tr.onclick = () => openChart(r.symbol);
    tbody.appendChild(tr);
  }
}

async function refreshAll() {
  await refreshStatus();
  await refreshSignals();
  await refreshWatch();
}
refreshAll();
setInterval(refreshAll, 15000);

// ---------------- Chart modal ----------------
const modal = document.getElementById('modal');
document.getElementById('closeBtn').onclick = () => modal.classList.remove('open');

async function openChart(symbol) {
  document.getElementById('modalTitle').textContent = symbol;
  modal.classList.add('open');
  try {
    const data = await (await fetch(`/api/profile/${symbol}`)).json();
    drawChart(data);
  } catch (e) {
    console.error(e);
  }
}

function drawChart(data) {
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

  let hi = Math.max(...candles.map(c => c.high));
  let lo = Math.min(...candles.map(c => c.low));
  const range = hi - lo || 1;
  const y = (price) => padTop + (hi - price) / range * chartH;

  const n = candles.length;
  const slot = chartW / n;
  const bodyW = Math.max(1, slot * 0.6);

  // HVN zones (background bands)
  for (const z of (data.zones || [])) {
    ctx.fillStyle = 'rgba(80,160,255,0.10)';
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

  // zone edges
  ctx.setLineDash([4, 3]);
  for (const z of (data.zones || [])) {
    ctx.strokeStyle = 'rgba(255,200,80,0.6)';
    ctx.beginPath(); ctx.moveTo(0, y(z.mid)); ctx.lineTo(px + profileW, y(z.mid)); ctx.stroke();
  }
  ctx.setLineDash([]);
}

function fmtNum(n) {
  return Number(n).toPrecision(6).replace(/\\.?0+$/,'').replace(/\\.$/, '');
}

window.addEventListener('resize', () => {
  if (modal.classList.contains('open')) {
    const title = document.getElementById('modalTitle').textContent;
    openChart(title);
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
    t = threading.Thread(target=scan_loop, daemon=True)
    t.start()
    port = int(os.environ.get("VP_PORT", 8080))
    print(f"VP-POC Screener v{APP_VERSION} — http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
