"""🚀 the 4h breakout picked by a model -> the bot: vp_rbs_model.json (the final model on every event 2021-2026, the rule,
the research's years) and vp_bt_trades.json["rbs"] (the walk-forward trades 2023-2026: each year's model trained on the
years before, the score > the threshold, one trade a coin at a time). The rule: money_rbs.py's A — a close out of a range
(N 20 / 30 / 50 bars < 4 x ATR100) with the chart's EMA200, the entry at the next 4h open, the stop 1.5 ATR, the take 2R,
out at the 12th bar's close (48 h)."""
import sys, os, json, time, numpy as np, lightgbm as lgb
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rbs_ml as ML, rbs_feat as RF
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "zones_model"))
import lgbpure
REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
SK, XN, HD, THR, TFH = 1.5, "t2", 2, 0.8, 4
FEE, FUND = 0.001, 0.0003
VER = 1


def export(booster, feats):
    """lgbpure.export without its 7-digit rounding: a threshold like -1e-35 (the split between the negatives and the zeros of
    a count / a sign feature) rounded to 0.0 sends the zeros the other way (the score off by 0.03 on the check)"""
    def conv(n):
        if "leaf_value" in n:
            return float(n["leaf_value"])
        assert n["decision_type"] == "<=", n["decision_type"]
        assert n.get("missing_type", "None") in ("None", "NaN"), n.get("missing_type")
        return [n["split_feature"], float(n["threshold"]), 1 if n.get("default_left", True) else 0, conv(n["left_child"]), conv(n["right_child"])]
    return {"feats": feats, "trees": [conv(t["tree_structure"]) for t in booster.dump_model()["tree_info"]]}


def gate(bsym, names):
    b = bsym[:-4]
    for sym, scl in ((b + "_USDT", 1.0), (b[4:] + "_USDT", 1000.0) if b.startswith("1000") else (None, None)):
        if sym and sym in names:
            return sym, scl
    return (b[4:] + "_USDT", 1000.0) if b.startswith("1000") else (b + "_USDT", 1.0)


if __name__ == "__main__":
    z = dict(np.load(f"{ML.ST}/wf/rbs_{TFH}.npz")); X = np.load(f"{ML.ST}/wf/rbs_{TFH}_X.npz")["X"]
    si, xi, hi = ML.STOPS.index(SK), ML.EXITS.index(XN), ML.HOLDS.index(HD)
    r = z["y"][:, si, xi, hi, 0]; b = z["y"][:, si, xi, hi, 1]; t = z["t"]; ok = np.isfinite(r); yr = ML.year(t)
    P = dict(ML.P, num_threads=4)
    pred = np.full(len(t), np.nan)
    for Y in ML.TEST:
        tr = ok & (t < ML.ystart(Y) - HD * 86400); te = ok & (yr == Y)
        pred[te] = lgb.train(P, lgb.Dataset(X[tr], np.clip(r[tr], -1.5, 4.0)), num_boost_round=300).predict(X[te])
    sel = np.flatnonzero(ok & np.isfinite(pred) & (pred > THR))
    sel = sel[ML.dedupe(z["sym"][sel], t[sel], b[sel], TFH)]
    sel = sel[np.argsort(t[sel])]
    src = open(os.path.join(REPO, "vp_poc_screener.py")).read()
    import re
    names = set(re.search(r'RESEARCH_COINS_127 = tuple\("""(.*?)"""', src, re.S).group(1).split()) | set(
        re.search(r'RESEARCH_COINS_211 = RESEARCH_COINS_127 \+ tuple\("""(.*?)"""', src, re.S).group(1).split())
    bt = []
    for k in sel:
        sym, scl = gate(str(z["sym"][k]), names)
        s = int(z["side"][k]); e = float(z["e"][k]); risk = SK * float(z["atr"][k]); j = int(b[k]) - 1
        fee = (e * FEE + e * FUND * (j + 1) * TFH / 24) / risk; raw = float(r[k]) + fee
        kind = "stop" if abs(raw + 1) < 1e-6 else ("take" if abs(raw - 2) < 1e-6 else "TIME")
        bt.append({"s": sym, "d": s, "c": "4h", "n": int(z["N"][k]), "t": int(t[k]), "e": round(e / scl, 10), "sl": round((e - s * risk) / scl, 10),
                   "tp": round((e + s * 2 * risk) / scl, 10), "x": int(t[k] + b[k] * TFH * 3600), "xp": round((e + s * raw * risk) / scl, 10),
                   "r": round(float(r[k]), 3), "k": kind, "sc": round(float(pred[k]), 3)})
    years = {}
    for Y in ML.TEST:
        rs = [x["r"] for x in bt if ML.year(np.array([x["t"]]))[0] == Y]
        if rs:
            years[str(Y)] = {"n": len(rs), "avg": round(float(np.mean(rs)), 3), "wr": round(100 * float(np.mean(np.array(rs) > 0)), 1), "sum": round(float(np.sum(rs)), 1),
                             "all_avg": round(float(r[ok & (yr == Y)].mean()), 3)}
    rs = np.array([x["r"] for x in bt])
    # the final model: every event
    m = lgb.train(P, lgb.Dataset(X[ok], np.clip(r[ok], -1.5, 4.0)), num_boost_round=300)
    ex = export(m, list(RF.NAMES))
    # the exported trees score as LightGBM does (the bot's own predictor)
    smp = np.flatnonzero(ok)[::97][:400]
    d = max(abs(lgbpure.predict(ex, [float(v) for v in X[k]]) - m.predict(X[k:k + 1])[0]) for k in smp)
    assert d < 1e-4, d
    coins = sorted(set(str(s) for s in z["sym"]))
    model = {"ver": VER, "feats": list(RF.NAMES), "coins": coins, "trained_to": int(t[ok].max()), "made": int(time.time()),
             "rule": {"tf": "4h", "ns": [20, 30, 50], "kmax": 4.0, "stop_atr": SK, "take_r": 2.0, "hold_bars": 12, "thr": THR, "fee": FEE, "fund": FUND},
             "research": {"years": years, "n": len(bt), "avg": round(float(rs.mean()), 3), "wr": round(100 * float((rs > 0).mean()), 1),
                          "per_week": round(len(bt) / (3.83 * 52), 1), "days_med": round(float(np.median([(x["x"] - x["t"]) / 86400 for x in bt])), 2),
                          "money": {"base": 28918, "with": 49391, "with_ddc": 37306, "dd_base": 66, "dd_with": 70}},
             "models": [ex["trees"]]}
    json.dump(model, open(os.path.join(REPO, "vp_rbs_model.json"), "w"), separators=(",", ":"))
    fn = os.path.join(REPO, "vp_bt_trades.json"); D = json.load(open(fn)); D["rbs"] = bt; D["made"] = int(time.time())
    json.dump(D, open(fn, "w"), separators=(",", ":"))
    print(f"model: {len(ex['trees'])} trees, {os.path.getsize(os.path.join(REPO, 'vp_rbs_model.json')) // 1024} KB, parity {d:.2e}; bt {len(bt)} trades {rs.mean():+.3f}R; years {years}")
    print("export done")
