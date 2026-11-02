"""v0.99.765 — the shifted 4h ⚡ stream (wick4h_o2: bars 02-06, 06-10 … UTC) in the bot vs the lab (tools/winrate dlm_engine,
what the models were trained and the money checked on), on the lab-store's Binance 1h candles:
 1) the bot's shifted bars (_dlm_chart: two 2h bars each) = the engine's chart on the shifted grid;
 2) the bot's limits (dlm_candidates4 on _dlm_shift'ed bars, its 3000-bar window) = the engine's events: the same bars, sides,
    levels and 33 features (the window's start decayed: 1e-3); no limit the engine did not have;
 3) the bot's virtual trade of an order (_dlm_hit on the shifted grid, _dlm_open_trade, _dlm_walk_1h with the close stop at
    the shifted 4h closes) = the engine's walk with the bot's exits: the fill, the exit, R;
 4) the grid helpers and the scan schedule (02, 06 … UTC)"""
import os, sys, bisect, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import V
import dlm_engine as DE
OFF, BS = 7200, 14400
ST = {"name": "wick4h_o2", "tf": "4h", "bar_sec": BS, "off": OFF, "anchor": "wick", "depth_atr": 1.0, "fam": 2.0, "alive_bars": 4,
      "take_atr": 1.2, "stop_atr": 1.75, "hard_stop_atr": 3.0, "hold_bars": 32, "stop_mode": "close1h", "close_h": 4}
H1 = {}
def h1(bsym):
    if bsym not in H1: H1[bsym] = DE.load1h(bsym)
    return H1[bsym]
def bars2h(bsym):
    T, O, H, L, C, Vv = h1(bsym); blk = T // 7200; out = []
    st = np.r_[0, np.flatnonzero(blk[1:] != blk[:-1]) + 1]; en = np.r_[st[1:], len(T)]
    for s_, e_ in zip(st, en):
        if e_ - s_ == 2:
            out.append({"time": int(blk[s_] * 7200), "open": O[s_], "high": H[s_:e_].max(), "low": L[s_:e_].min(), "close": C[e_ - 1], "volume": Vv[s_:e_].sum(), "bn": 1})
    return out
B2 = {}
GS = lambda sym: sym.replace("_USDT", "USDT")   # the bot's names -> Binance's (the test coins have no 1000-prefix)
def fake_closed(sym, tf, sec, n, now):
    assert tf == "2h", tf
    b = sym if sym.endswith("USDT") and "_" not in sym else GS(sym)
    if b not in B2: B2[b] = bars2h(b)
    a = B2[b]; j = bisect.bisect_right([x["time"] for x in a], now - sec)
    return a[max(0, j - n):j]
V._dlm_closed = fake_closed
def fake_1h(sym, start, now):
    T, O, H, L, C, Vv = h1(GS(sym)); i = bisect.bisect_left(T, start); j = bisect.bisect_right(T, now - 3600)
    return [{"time": int(T[k]), "open": O[k], "high": H[k], "low": L[k], "close": C[k]} for k in range(i, j)]
V._dlm_1h = fake_1h
V.DLM_BINANCE = False   # _dlm_hit's 1h candles: the Gate branch (get_candles_range) replaced below
V.get_candles_range = lambda sym, tf, a, b: fake_1h(sym, a, b + 3600) if tf == "1h" else []
V._DLM["model"] = {"streams": [ST], "side_cap": 20}
ok = True
# 4) the grid
assert V._dlm_grid(1790812800 + 3 * 3600, BS, OFF) == 1790812800 + 7200 and V._dlm_grid(1790812800 + 3600, BS, OFF) == 1790812800 - 7200
assert V._dlm_ch_close({"ch": 4, "off": OFF}, {"time": 1790812800 + 5 * 3600}) and not V._dlm_ch_close({"ch": 4, "off": OFF}, {"time": 1790812800 + 3 * 3600})
assert V._dlm_ch_close({"ch": 4}, {"time": 1790812800 + 3 * 3600})   # the UTC grid unchanged
rng = np.random.default_rng(7); n_ev = n_tr = 0; worst = 0.0; extra = 0; bad_tr = []
for bsym in ("SOLUSDT", "DOGEUSDT", "ARBUSDT", "LINKUSDT"):
    gsym = bsym.replace("USDT", "_USDT")
    ev = DE.features(bsym, "wick4h_o2", DE.btc_ctx("wick4h_o2"))
    # 1) the bars
    T1, O1, Hh, Ll, C1, V1 = DE.shift(h1(bsym), 2); cT, cO, cH, cL, cC, cV = DE.chart(T1, O1, Hh, Ll, C1, V1, 4)
    bb = V._dlm_chart(gsym, ST, 100000, int(cT[-1]) + OFF + BS + 1)
    m = {b["time"]: b for b in bb}; d_ = 0.0
    for k in range(0, len(cT), 97):
        b = m.get(int(cT[k]) + OFF); assert b is not None, (bsym, cT[k])
        d_ = max(d_, abs(b["open"] - cO[k]), abs(b["high"] - cH[k]), abs(b["low"] - cL[k]), abs(b["close"] - cC[k]), abs(b["volume"] - cV[k]) / max(1, cV[k]))
    assert d_ < 1e-9, (bsym, "bars", d_)
    # 2) the limits
    sel = rng.choice(np.flatnonzero(ev["t"] >= 1735689600), 25, replace=False)
    for k in sel:
        t_close = int(ev["t"][k]) + BS
        w = V._dlm_chart(gsym, ST, 3000, t_close); wb = V._dlm_chart("BTC_USDT", ST, 3000, t_close)
        assert w[-1]["time"] == int(ev["t"][k]), (bsym, w[-1]["time"], ev["t"][k])
        cs = V.dlm_candidates4(V._dlm_shift(w, OFF), V._dlm_shift(wb, OFF), streams=[ST])
        same = [c for c in cs if c["side"] == int(ev["side"][k])]
        n_ev += 1
        if not same or abs(same[0]["lv"] - ev["lv"][k]) > 1e-9 * abs(ev["lv"][k]):
            ok = False; print("НЕТ заявки", bsym, ev["t"][k], ev["side"][k]); continue
        worst = max(worst, float(np.max(np.abs(np.array(same[0]["f"]) - ev["f"][k]))))
        evs = {int(s_) for t_, s_ in zip(ev["t"], ev["side"]) if t_ == ev["t"][k]}
        extra += sum(1 for c in cs if c["side"] not in evs)
        # 3) the virtual trade of the order (the bot's exits) vs the engine's walk
        o = {"id": f"x{bsym}{k}", "symbol": gsym, "side": int(ev["side"][k]), "lv": float(ev["lv"][k]), "atr": float(ev["atr"][k]), "score": 1.0,
             "bs": BS, "st": "wick4h_o2", "off": OFF, "t0": t_close, "until": t_close + 4 * BS, "status": "OPEN", "real": None}
        fl, t1h, fill, R, kind, tout = DE.walk("wick4h_o2", h1(bsym), [t_close], [o["side"]], [o["lv"]], [o["atr"]], 1.2, 1.75, 3.0)
        now = t_close + 40 * BS
        h = V._dlm_hit(o, now)
        if not fl[0]:
            if h: ok = False; bad_tr.append((bsym, k, "бот исполнил, лаба нет"))
            continue
        if not h or h[0] != int(t1h[0]) or abs(h[3] - fill[0]) > 1e-9 * fill[0]:
            ok = False; bad_tr.append((bsym, k, "исполнение", h, int(t1h[0]), float(fill[0]))); continue
        with V._dlm_lock: V._DLM["trades"] = []
        t = V._dlm_open_trade(o, h[2], h[3], t1h=h[0])
        res = V._dlm_walk_1h(t, now); n_tr += 1
        r_ = V._dlm_r_h(t, res[1], res[2], res[0]) if res else None
        if not res or abs(r_ - float(R[0])) > 2e-3 or res[3] != int(tout[0]):
            ok = False; bad_tr.append((bsym, k, "сделка", res, r_, float(R[0]), int(tout[0])))
print(f"бары совпали; заявок сверено {n_ev}, худшая разница признаков {worst:.2e}, лишних заявок у бота {extra}; сделок сверено {n_tr}, расхождений {len(bad_tr)}")
for x in bad_tr[:8]: print(" ", x)
ok = ok and worst < 1e-3 and extra == 0 and not bad_tr
print("t_dlm_o2 OK" if ok else "t_dlm_o2 FAIL"); sys.exit(0 if ok else 1)
