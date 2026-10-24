"""⚡ v0.99.692 export (the user wants a high win rate; wrfront.py / wrfront2.py / wrfront3.py — the honest grids):
the take 1.1 ATR (a reduce-only limit); the stop at a 1h CLOSE beyond 2 ATR (61% of the 2 ATR stops were wicks, the hour
closing back — wickstat.py), an emergency stop on the exchange at 3 ATR; the position sized by the 2 ATR; out after 32
bars of the order's chart. The trades walked on the 1h candles from the touch hour (the emergency stop first in an hour,
no take in the touch hour, the close checked at each hour's close); the pool in the honest order (the touch's 1h bar,
the nearer level first, busy per coin & side, 20 a side). The same models (v0.99.689); the model file gets the rule in
each stream and the research numbers; the backtest list 2025 on."""
import os, json
exec(open("wrfront.py").read().split("EVQ = {}")[0])
from bt_trades import gate_sym
TK, SOFT, HARD = 1.1, 2.0, 3.0
def unseen_set(dr):
    syms = [os.path.basename(f)[:-4] for f in sorted(glob.glob(f"{dr}/*.npz"))]
    return set(syms[2::3]) | {os.path.basename(f)[:-4] for f in glob.glob(f"{dr}x/*.npz")}
UN = {"wick4h": unseen_set("s23_4h"), "close2h": unseen_set("s21h2")}
ROWS = []
for st_name, args in (("wick4h", ("s23_4h", 2, "s26_s23_4h_w1_0.npz", "s23_engine", 4, "wick", 1.0, 0.99)),
                      ("close2h", ("s21h2", 0, "s26_s21h2_d2_1.npz", "s21h2_engine", 2, "close", 2.0, 0.99))):
    for e in events2(*args):
        T, O, H, L, C = h1c(e["sym"])
        R, k, te = walk3(T, O, H, L, C, e["i1"], e["end_t"], e["s"], e["fill"], e["a"], TK, 0, 0, SOFT, HARD, True)
        # the exit price / kind again for the list
        s, f, a = e["s"], e["fill"], e["a"]
        b = int(np.searchsorted(T, te - 3600)); kind = {0: "stop", 1: "take", 3: "time"}[int(k)]
        if kind == "take": xp = f + s * TK * a
        elif kind == "stop":
            hsl = f - s * HARD * a
            xp = hsl if ((L[b] <= hsl) if s > 0 else (H[b] >= hsl)) else float(C[b])
            if xp == hsl and b > e["i1"] and ((O[b] <= hsl) if s > 0 else (O[b] >= hsl)): xp = float(O[b])
        else: xp = float(C[b])
        ROWS.append(dict(e, st=st_name, tfh=args[4], R=float(R), kind=kind, te=int(te), xp=xp, un=e["sym"] in UN[st_name],
                         stp=float(np.clip(SOFT * a / f, 0.002, 0.5))))
ROWS.sort(key=lambda e: e["key"]); busy, act, pool = {}, [], []
for e in ROWS:
    ft = e["key"][0]
    if busy.get((e["sym"], e["s"]), 0) > ft: continue
    act = [x for x in act if x[0] > ft]
    if sum(1 for x in act if x[1] == e["s"]) >= 20: continue
    busy[(e["sym"], e["s"])] = e["te"]; act.append((e["te"], e["s"])); pool.append(e)
P = np.array(sorted((e["key"][0], e["te"], e["R"], e["stp"]) for e in pool), float); t0, t1, R, STv = P.T
np.save("pool692.npy", P)
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
m6 = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 182 * 86400.0, 20, 0.04, -0.025)[0] for s_ in roll])
l12 = sim(t0, t1, R, STv, int(np.searchsorted(t0, ts(2025, 10))), ts(2026, 10), 20, 0.04, -0.025)
money = {"pos": 20, "risk": 4.0, "year_median": int(np.median(y[:, 0])), "year_p10": int(np.percentile(y[:, 0], 10)), "harsh_median": int(np.median(yh)),
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
json.dump(out, open("dlm_bt_v692.json", "w"), separators=(",", ":"))
M = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json"))
for S_ in M["streams"]:
    for k_ in ("far_take_atr", "pull_atr"): S_.pop(k_, None)
    S_.update({"take_atr": TK, "stop_atr": SOFT, "hard_stop_atr": HARD, "stop_mode": "close1h"})
M["research"].update({"years": years, "money": money, "order": "1h_near", "exit": {"take_atr": TK, "stop_close_atr": SOFT, "hard_stop_atr": HARD},
                      "unseen": {"wr": round(np.mean([W(e) for e in un]) * 100), "avg": round(float(np.mean([e["R"] for e in un])), 3),
                                 "last12_wr": round(np.mean([W(e) for e in h]) * 100), "last12_avg": round(float(np.mean([e["R"] for e in h])), 3)}})
M["research"].pop("m1", None)
json.dump(M, open("vp_dlm_model_v692.json", "w"), separators=(",", ":"))
print("pool", len(pool), f"{R.mean():+.3f}R WR {np.mean([W(e) for e in pool])*100:.0f}%", json.dumps(money), "bt list", len(out),
      "avg", round(np.mean([x["r"] for x in out]), 3), "wr", round(np.mean([x["k"] == "take" for x in out]) * 100, 1))
print(json.dumps(M["research"]["unseen"]), json.dumps(years.get("unseen")))
