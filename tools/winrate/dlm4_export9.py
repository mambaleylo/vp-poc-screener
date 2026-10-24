"""⚡ v0.99.694 export: the stop on the close of the chart's own candle (4h stream: a 4h close, 2h: a 2h close; closetf693.py /
closeft2.py / closetf3.py / rule694_1m.py), the rest as v0.99.692. The v0.99.692 one (the user wants a high win rate; wrfront.py / wrfront2.py / wrfront3.py — the honest grids):
the take 1.1 ATR (a reduce-only limit); the stop at a 1h CLOSE beyond 2 ATR (61% of the 2 ATR stops were wicks, the hour
closing back — wickstat.py), an emergency stop on the exchange at 3 ATR; the position sized by the 2 ATR; out after 32
bars of the order's chart. The trades walked on the 1h candles from the touch hour (the emergency stop first in an hour,
no take in the touch hour, the close checked at each hour's close); the pool in the honest order (the touch's 1h bar,
the nearer level first, busy per coin & side, 20 a side). The same models (v0.99.689); the model file gets the rule in
each stream and the research numbers; the backtest list 2025 on."""
import os, json
exec(open("wrfront.py").read().split("EVQ = {}")[0])
from bt_trades import gate_sym
@njit
def walk5(T, O, H, L, C, i1, end_t, s, fill, a, tk, soft, hard, kh, size_by):
    risk = size_by * a; hsl = fill - s * hard * a; ssl = fill - s * soft * a; tp1 = fill + s * tk * a
    b = i1
    while b < len(C) and T[b] < end_t:
        q = b - i1
        if (s > 0 and L[b] <= hsl) or (s < 0 and H[b] >= hsl):
            x = O[b] if (q > 0 and ((s > 0 and O[b] <= hsl) or (s < 0 and O[b] >= hsl))) else hsl
            return (s * (x - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 0, T[b] + 3600
        if q > 0 and ((s > 0 and H[b] >= tp1) or (s < 0 and L[b] <= tp1)):
            return (s * (tp1 - fill) - (0.0004 + 0.0003 * (q + 1) / 24) * fill) / risk, 1, T[b] + 3600
        if (T[b] + 3600) % (kh * 3600) == 0 and ((s > 0 and C[b] <= ssl) or (s < 0 and C[b] >= ssl)):
            return (s * (C[b] - fill) - (0.0007 + 0.0003 * (q + 1) / 24) * fill) / risk, 4, T[b] + 3600
        b += 1
    b = min(b, len(C)) - 1
    return (s * (C[b] - fill) - (0.0007 + 0.0003 * (b - i1 + 1) / 24) * fill) / risk, 3, T[b] + 3600
import sys
TK, SOFT, HARD = 1.1, 2.0, float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
def unseen_set(dr):
    syms = [os.path.basename(f)[:-4] for f in sorted(glob.glob(f"{dr}/*.npz"))]
    return set(syms[2::3]) | {os.path.basename(f)[:-4] for f in glob.glob(f"{dr}x/*.npz")}
UN = {"wick4h": unseen_set("s23_4h"), "close2h": unseen_set("s21h2")}
ROWS = []
for st_name, args in (("wick4h", ("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, 0.99)),
                      ("close2h", ("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, 0.99))):
    for e in events2(*args):
        T, O, H, L, C = h1c(e["sym"])
        R, k, te = walk5(T, O, H, L, C, e["i1"], e["end_t"], e["s"], e["fill"], e["a"], TK, SOFT, HARD, args[4], SOFT)
        # the exit price / kind again for the list
        s, f, a = e["s"], e["fill"], e["a"]
        b = int(np.searchsorted(T, te - 3600)); kind = {0: "stop", 4: "stop", 1: "take", 3: "time"}[int(k)]
        if kind == "take": xp = f + s * TK * a
        elif kind == "stop":
            hsl = f - s * HARD * a
            xp = hsl if int(k) == 0 else float(C[b])
            if xp == hsl and b > e["i1"] and ((O[b] <= hsl) if s > 0 else (O[b] >= hsl)): xp = float(O[b])
        else: xp = float(C[b])
        ROWS.append(dict(e, st=st_name, tfh=args[4], R=float(R), kind=kind, te=int(te), xp=xp, un=e["sym"] in UN[st_name],
                         stp=float(np.clip(SOFT * a / f, 0.002, 0.5))))
# v0.99.694 — the money with the bot's leverage: the liquidation BUF x the emergency stop's distance (sim2, closetf4.py)
BUF = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5
@njit
def sim2(BUF_, t0, t1, R, ST, STH, i0, tend, maxpos, rk, shift):
    eq = 1.0; peak = 1.0; mdd = 0.0; deps = 1.0
    po_t = np.zeros(maxpos); po_r = np.zeros(maxpos); po_m = np.zeros(maxpos); po_u = np.zeros(maxpos); on = np.zeros(maxpos, np.bool_)
    j = i0
    while j < len(t0) and t0[j] < tend:
        for k in range(maxpos):
            if on[k] and po_t[k] <= t0[j]:
                eq += po_u[k] * (po_r[k] + shift); on[k] = False
                if eq > peak: peak = eq
                dd = 1 - eq / peak
                if dd > mdd: mdd = dd
        if eq < 0.1:
            eq = 1.0; peak = 1.0; deps += 1.0
            for k in range(maxpos): on[k] = False
        slot = -1; used = 0.0
        for k in range(maxpos):
            if on[k]: used += po_m[k]
            elif slot < 0: slot = k
        if slot >= 0:
            st = ST[j]; lev = min(20.0, np.floor(1.0 / (BUF_ * STH[j] + 0.0105)))
            if lev < 1.0:   # the bot: no safe leverage at the emergency stop -> skipped
                j += 1
                continue
            ru = eq * rk; m = ru / st / lev; free = (eq - used) * 0.9
            if m > free:
                if free <= 0.0: ru = 0.0
                else: ru *= free / m; m = free
            if ru > 0:
                on[slot] = True; po_t[slot] = t1[j]; po_r[slot] = R[j]; po_m[slot] = m; po_u[slot] = ru
        j += 1
    for k in range(maxpos):
        if on[k]: eq += po_u[k] * (po_r[k] + shift)
    if eq < 0: eq = 0.0
    return (eq - deps) * 100 + 100, mdd
def sim(t0, t1, R, ST, i0, tend, maxpos, rk, shift):
    return sim2(BUF, t0, t1, R, ST, ST * HARD / SOFT, i0, tend, maxpos, rk, shift)
ROWS.sort(key=lambda e: e["key"]); busy, act, pool = {}, [], []
for e in ROWS:
    ft = e["key"][0]
    if busy.get((e["sym"], e["s"]), 0) > ft: continue
    act = [x for x in act if x[0] > ft]
    if sum(1 for x in act if x[1] == e["s"]) >= 20: continue
    busy[(e["sym"], e["s"])] = e["te"]; act.append((e["te"], e["s"])); pool.append(e)
P = np.array(sorted((e["key"][0], e["te"], e["R"], e["stp"]) for e in pool), float); t0, t1, R, STv = P.T
np.save("pool694.npy", P)
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
m6 = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 182 * 86400.0, 20, 0.04, -0.025)[0] for s_ in roll])
l12 = sim(t0, t1, R, STv, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
money = {"pos": 20, "risk": 4.0, "liq_buf": BUF, "year_median": int(np.median(y[:, 0])), "year_p10": int(np.percentile(y[:, 0], 10)), "harsh_median": int(np.median(yh)),
         "dd": int(round(np.median(y[:, 1]) * 100)), "m6_below": int(round((m6 < 100).mean() * 100)), "m6_median": int(np.median(m6)), "last12": int(l12[0])}
W = lambda e: e["kind"] == "take"
years = {}
for e in pool:
    part = "unseen" if e["un"] else "train"; Y = str(1970 + e["key"][0] // 31557600)
    d = years.setdefault(part, {}).setdefault(Y, {"n": 0, "sum": 0.0, "w": 0, "st": {}}); d["n"] += 1; d["sum"] += e["R"]; d["w"] += W(e)
    d["st"][e["st"]] = d["st"].get(e["st"], 0) + 1
for part in years:
    for Y, d in years[part].items():
        mo = ((ts(int(Y) + 1) if int(Y) < 2026 else ts(2026, 10)) - ts(int(Y))) / (30.4 * 86400)
        years[part][Y] = {"n": d["n"], "avg": round(d["sum"] / d["n"], 3), "wr": round(d["w"] / d["n"] * 100, 1), "pm": round(d["n"] / mo, 1), "streams": d["st"]}
un = [e for e in pool if e["un"]]; h = [e for e in un if e["key"][0] >= ts(2025, 10)]
out = []
for e in pool:
    if e["key"][0] < ts(2025): continue
    gs, scl = gate_sym(e["sym"]); s, a, f = e["s"], e["a"], e["fill"]
    out.append({"s": gs, "d": s, "c": f"{e['tfh']}h", "st": e["st"], "t": e["key"][3] + e["tfh"] * 3600, "lv": round(e["lv"] / scl, 10) if "lv" in e else None,
                "e": round(f / scl, 10), "sl": round((f - s * SOFT * a) / scl, 10), "sl2": round((f - s * HARD * a) / scl, 10),
                "tp": round((f + s * TK * a) / scl, 10), "f": e["key"][0], "x": e["te"], "xp": round(e["xp"] / scl, 10), "r": round(e["R"], 3),
                "k": e["kind"], "chk": e["un"]})
out.sort(key=lambda x: x["t"])
json.dump(out, open("dlm_bt_v694.json", "w"), separators=(",", ":"))
M = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json"))
for S_ in M["streams"]:
    for k_ in ("far_take_atr", "pull_atr"): S_.pop(k_, None)
    S_.update({"take_atr": TK, "stop_atr": SOFT, "hard_stop_atr": HARD, "stop_mode": "close1h", "close_h": int(S_["bar_sec"]) // 3600})
M["research"].update({"years": years, "money": money, "order": "1h_near", "exit": {"take_atr": TK, "stop_close_atr": SOFT, "hard_stop_atr": HARD, "close": "chart"},
                      "unseen": {"wr": round(np.mean([W(e) for e in un]) * 100), "avg": round(float(np.mean([e["R"] for e in un])), 3),
                                 "last12_wr": round(np.mean([W(e) for e in h]) * 100), "last12_avg": round(float(np.mean([e["R"] for e in h])), 3)}})
M["research"].pop("m1", None)
M["liq_buf"] = BUF   # v0.99.694 — the bot's ⚡ leverage: the liquidation BUF x the emergency stop (_dlm_liq_buf)
json.dump(M, open(f"vp_dlm_model_v694_{BUF}.json", "w"), separators=(",", ":"))
print("pool", len(pool), f"{R.mean():+.3f}R WR {np.mean([W(e) for e in pool])*100:.0f}%", json.dumps(money), "bt list", len(out),
      "avg", round(np.mean([x["r"] for x in out]), 3), "wr", round(np.mean([x["k"] == "take" for x in out]) * 100, 1))
print(json.dumps(M["research"]["unseen"]), json.dumps(years.get("unseen")))
