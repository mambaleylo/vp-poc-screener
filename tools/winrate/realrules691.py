"""v0.99.691 rules. the audit, part 2: the bot's REAL-mode rules (vp_poc_screener.py dlm_scan / dlm_real_place / dlm_bn_tick) on every
order its scans made in 2026 (replay690_*.json, the filled and the unfilled ones), vs the research pool. Each order's fill
and exit from its chart's bars (the bot's virtual walk: the stop first, the 2 / 1 ATR take). Rules, as coded:
  scan:  no order while a trade (real or virtual) of the coin & side is open; no real placing when the side has >= 20
         open trades (real + virtual);
  place: none while a real position of the coin is open (any side); none while a live real limit of the coin stands on
         the other side or of the same stream; none at >= 20 real positions or >= 26 real limits + positions;
         an order not placed stays virtual (it fills virtually, its trade blocks the coin & side and counts in the side);
  tick:  a live real limit whose coin got a position (any side) before it filled is cancelled.
Money: 20 positions x 4% from $100, 12 months from 2025-10-20 .. (the 2026 part), cautious."""
import os, json, glob, numpy as np
os.environ["TFH"] = "4"
exec(open("best_money.py").read().split("za = np.load")[0])
import s23_engine as E4, s21h2_engine as E2
from numba import njit
exec("@njit\ndef ex" + open("tkext.py").read().split("@njit\ndef ex")[1].split("\ndef run")[0])
def bname(gs):
    b = gs.replace("_USDT", "")
    for c, scl in ((b + "USDT", 1.0), ("1000" + b + "USDT", 1000.0)):
        if os.path.exists(f"s23_4h/{c}.npz") or os.path.exists(f"s23_4hx/{c}.npz"): return c, scl
BARS = {}
def bars(gs, bs):
    if (gs, bs) not in BARS:
        c, scl = bname(gs); T, O, H, L, C, Vv = (E2 if bs == 7200 else E4).load15(c)
        BARS[(gs, bs)] = (T.astype(np.int64), O / scl, H / scl, L / scl, C / scl)
    return BARS[(gs, bs)]
OR = []
for f in sorted(glob.glob("replay691_[0-9].json")):
    d_ = json.load(open(f)); OR += [o for o in d_["orders"] if d_["from"] <= o["t0"] < d_["to"]]
OR = [o for o in OR if o["t0"] >= 1780272000]   # 2026-06-01 on
print("orders", len(OR), flush=True)
for o in OR:   # the fill and the exit on the order's chart
    T, O, H, L, C = bars(o["symbol"], o["bs"]); s, lv, a = o["side"], o["lv"], o["atr"]
    i = int(np.searchsorted(T, o["t0"])); fb = -1
    for b in range(i, len(T)):
        if T[b] >= o["until"]: break
        if (L[b] <= lv) if s > 0 else (H[b] >= lv): fb = b; break
    o["fb"] = fb
    if fb < 0: continue
    fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
    R, k, kk = ex(O, H, L, C, fb, s, fill, a, 0.4, 1.0, 0, o["bs"] // 3600)
    o.update(ft=int(T[fb]), end=int(T[min(len(T) - 1, fb + kk)]) + o["bs"], R=float(R), stp=float(np.clip(2 * a / fill, 0.002, 0.5)))
filled = [o for o in OR if o["fb"] >= 0]
print("filled", len(filled), f"({len(filled) / len(OR) * 100:.0f}%)", flush=True)
# ---- the research pool (dlm4_export5 / the backtest list): by the fill, busy per coin & side, 20 a side
def pool_research(orders):
    ev = sorted(orders, key=lambda o: (o["ft"], -o["score"], o["t0"])); busy, act, P = {}, [], []
    for o in ev:
        if busy.get((o["symbol"], o["side"]), 0) > o["ft"]: continue
        act = [x for x in act if x[0] > o["ft"]]
        if sum(1 for x in act if x[1] == o["side"]) >= 20: continue
        busy[(o["symbol"], o["side"])] = o["end"]; act.append((o["end"], o["side"])); P.append(o)
    return P
# ---- the bot's real mode (v0.99.691): every order is made; placed now or, while it waits, at any later moment if the
# price has not reached it; blocked by: a real position of the coin, a live real limit of the coin on the other side,
# 20 real positions, 26 real limits + positions, 20 real positions on the side
import heapq
def bot_real(orders, live_cap=26, pos_cap=20, side_cap=20, other_side=True):
    ev = []
    for o in orders:
        ev.append((o["t0"], 2, -o["score"], id(o), "new", o))
        if o["fb"] >= 0: ev.append((o["ft"], 1, -o["score"], id(o), "touch", o))
        else: ev.append((o["until"], 0, 0, id(o), "expire", o))
    heapq.heapify(ev)
    live, real_tr, virt_tr, wait, out, lost = [], [], [], [], [], {}
    def bump(k): lost[k] = lost.get(k, 0) + 1
    def can_place(o):
        if any(x["symbol"] == o["symbol"] for x in real_tr): return "по монете позиция"
        if other_side and any(x["symbol"] == o["symbol"] and x["side"] != o["side"] for x in live): return "по монете лимитка в другую сторону"
        if len(real_tr) >= pos_cap: return "20 позиций"
        if len(live) + len(real_tr) >= live_cap: return "26 лимиток+позиций"
        if sum(1 for x in real_tr if x["side"] == o["side"]) >= side_cap: return "20 в эту сторону"
        return None
    def retry():
        for o in sorted(wait, key=lambda o: -o["score"]):
            if can_place(o) is None:
                wait.remove(o); live.append(o)
    while ev:
        t, pr, _, _, kind, o = heapq.heappop(ev)
        if kind == "exit_real": real_tr[:] = [x for x in real_tr if x is not o]; retry(); continue
        if kind == "exit_virt": virt_tr[:] = [x for x in virt_tr if x is not o]; continue
        if kind == "expire":
            live[:] = [x for x in live if x is not o]; wait[:] = [x for x in wait if x is not o]; retry(); continue
        if kind == "new":
            if can_place(o) is None: live.append(o)
            else: wait.append(o)
            continue
        # a touch: the order fills
        if any(x is o for x in live):
            live[:] = [x for x in live if x is not o]
            if any(x["symbol"] == o["symbol"] for x in real_tr): bump("отменена: по монете уже позиция"); retry(); continue
            real_tr.append(o); out.append(o); heapq.heappush(ev, (o["end"], 0, 0, id(o), "exit_real", o))
            for x in [x for x in live if x["symbol"] == o["symbol"]]:
                live[:] = [y for y in live if y is not x]; bump("отменена: исполнилась другая лимитка монеты")
            continue
        if any(x is o for x in wait):   # never placed: the virtual trade (the research's rule) — the real account misses it
            wait[:] = [x for x in wait if x is not o]
            if any(x["symbol"] == o["symbol"] and x["side"] == o["side"] for x in real_tr + virt_tr): continue
            if sum(1 for x in real_tr + virt_tr if x["side"] == o["side"]) >= side_cap: continue
            bump("не поставлена: " + (can_place(o) or "?")); virt_tr.append(o); heapq.heappush(ev, (o["end"], 0, 0, id(o), "exit_virt", o))
    return out, lost
def money(lst, nm, extra=""):
    P = np.array(sorted((o["ft"], o["end"], o["R"], o["stp"]) for o in lst), float); t0, t1, R, STv = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
    v = sim(t0, t1, R, STv, 0, ts(2026, 10), 20, 0.04, -0.025)
    y3 = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 91 * 86400.0, 20, 0.04, -0.025)[0] for s_ in np.arange(ts(2026, 6), ts(2026, 7) + 1, 3 * 86400.0)])
    print(f"{nm:44s} сделок {len(R):4d} {R.mean():+.3f}R WR {np.mean(R > 0)*100:.0f}% | с 1 июня $100 → ${v[0]:,.0f} (просадка {v[1]*100:.0f}%) | 3 мес медиана ${np.median(y3):,.0f} {extra}", flush=True)
import s19h_engine as E1
H1 = {}
def touch1h(gs, ft, bs, s_, lv):
    if gs not in H1:
        c, scl = bname(gs); T, O, H, L, C, V_ = E1.load15(c); H1[gs] = (T, H / scl, L / scl)
    T, H, L = H1[gs]; i = int(np.searchsorted(T, ft)); j = int(np.searchsorted(T, ft + bs))
    for b in range(i, j):
        if (L[b] <= lv) if s_ > 0 else (H[b] >= lv): return int(T[b])
    return ft
for o in filled: o["ft"] = touch1h(o["symbol"], o["ft"], o["bs"], o["side"], o["lv"])   # the touch's 1h bar (pool1h.py)
PR = pool_research(filled); money(PR, "бэктест (как список бэктеста)")
BR, lost = bot_real(OR); money(BR, "бот, реальная торговля v0.99.691")
print("исполнившиеся сделки бэктеста, которых нет на реальном счёте, по причинам:", json.dumps(lost, ensure_ascii=False))
ip = {id(o) for o in PR}; ib = {id(o) for o in BR}
print(f"в бэктесте и у бота {len(ip & ib)}, только в бэктесте {len(ip - ib)}, только у бота {len(ib - ip)}")
for kw, nm in ((dict(live_cap=999), "без лимита 26"), (dict(other_side=False), "лимитка в другую сторону не мешает (нельзя: одна позиция на монету)"),
               (dict(live_cap=40), "лимит 40"), (dict(pos_cap=30, live_cap=40), "30 позиций, лимит 40")):
    b, l = bot_real(OR, **kw); money(b, "  " + nm, json.dumps(l, ensure_ascii=False)[:200])
# ---- the target: the decision at the touch (the bot arms a limit only when the price comes near — v0.99.691 plan)
def bot_touch(orders, pos_cap=20, side_cap=20):
    ev = sorted([(o["ft"], -o["score"], id(o), o) for o in orders if o["fb"] >= 0])
    real_tr, out = [], []
    for t, _, _, o in ev:
        real_tr[:] = [x for x in real_tr if x["end"] > t]
        if any(x["symbol"] == o["symbol"] for x in real_tr): continue   # one position a coin (Binance one-way)
        if len(real_tr) >= pos_cap or sum(1 for x in real_tr if x["side"] == o["side"]) >= side_cap: continue
        real_tr.append(o); out.append(o)
    return out
money(bot_touch(OR), "решение в момент касания (цель)")
money(bot_touch(OR, pos_cap=999), "  то же без общего лимита 20 (сим. денег ограничит)")
