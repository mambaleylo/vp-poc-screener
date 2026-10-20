"""EMA v4 (v0.99.644) / v5 (v0.99.645: + BTC above its daily EMA50): the same model (vp_ema_model.json ver 3), new trading rule from the hypothesis study
(ema_hyp*.py): longs only, no entry when the price is >= 10 daily ATR above the daily EMA200, a 4h touch only with
a score >= the threshold + 0.1, take 3R (stop 0.75 daily ATR, 72 h). Writes the model ver 4 (rule + filters + the
yearly walk-forward stats) and the backtest trades ("emx") into vp_bt_trades.json."""
import json, numpy as np, pandas as pd
import ema_h as E
from mk import ts
from bt_trades import gate_sym
d = E.d
SIDES, MAX_E200, MARGIN4H, STOP, TAKE, HOLD = (1,), 10.0, 0.1, 0.75, 3.0, 72
side, tf, e200 = d.side.values, d.tf_s.values, d.s_d_ema200.values
thr = np.array([E.THR[y][0.97] if y in E.THR else np.inf for y in E.YR]); rel = E.SC - thr
bema = pd.read_parquet(f"{E.D}/er_all.parquet", columns=["s_b_ema50"]).s_b_ema50.values
mask = np.isin(side, SIDES) & (e200 < MAX_E200) & ((tf != "4h") | (rel >= MARGIN4H)) & (bema > 0)
idx = E.cand(0.97, mask)
R, K, KD = E.outcomes(idx, a=STOP, take=TAKE, hold=HOLD)
tr = E.replay(idx, R, K)
years = {}
for Y in (2022, 2023, 2024, 2025):
    m = E.YR[tr] == Y; rs = R[tr[m]]
    o = tr[m][np.argsort(E.T[tr[m]] + K[tr[m]] * 3600)]; c = np.cumsum(R[o])
    dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c]))
    wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / 604800
    years[str(Y)] = {"n": int(m.sum()), "avg": round(float(rs.mean()), 3), "wk": round(float(m.sum() / wk), 1), "sum": round(float(rs.sum()), 1),
                     "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1)}
    print(Y, years[str(Y)], flush=True)
# the trades for the tab (exit price re-derived the same way as ema_h.sim1)
KIND = {0: "stop", 2: "take", 3: "time"}
out = []
for i in tr:
    O, H, L, C = E.bars(d.sym.values[i]); j = int(d.j.values[i]); s = int(side[i]); fill = float(d.lv.values[i])
    risk = fill * STOP * float(d.datr.values[i]) / 100; sl = fill - s * risk; tp = fill + s * TAKE * risk
    k = int(K[i]) - 1; b = j + k
    if KD[i] == 0:
        gap = (O[b] <= sl) if s > 0 else (O[b] >= sl)
        ex = O[b] if (gap and k > 0) else sl
    elif KD[i] == 2:
        ex = tp
    else:
        ex = C[b]
    gs, sc = gate_sym(d.sym.values[i])
    out.append({"s": gs, "d": s, "c": "1h", "tf": str(tf[i]), "n": int(d.n_i.values[i]), "t": int(E.T[i]), "e": round(fill / sc, 10),
                "sl": round(sl / sc, 10), "tp": round(tp / sc, 10), "x": int(E.T[i] + K[i] * 3600), "xp": round(float(ex) / sc, 10),
                "r": round(float(R[i]), 3), "k": KIND.get(int(KD[i]), "time")})
bt = json.load(open(f"{E.D}/vp_bt_trades.json")); bt["emx"] = out
json.dump(bt, open(f"{E.D}/vp_bt_trades.json", "w"), separators=(",", ":"))
m = json.load(open(f"{E.D}/vp_ema_model.v3.json"))
m.update({"ver": 5, "btc_ema50": True, "rule": {"stop_datr": STOP, "take_r": TAKE, "hold_h": HOLD}, "sides": list(SIDES), "max_d_ema200": MAX_E200,
          "tf_margin": {"4h": MARGIN4H}})
m["research"]["years"] = years
m["research"]["filters"] = "лонги при BTC выше EMA50 дня, цена < 10 дн. ATR над EMA200 дня, 4ч с запасом +0.1, тейк 3R"
json.dump(m, open(f"{E.D}/vp_ema_model.json", "w"), separators=(",", ":"))
r = R[tr]
print("trades", len(out), "avg", round(float(r.mean()), 3), "wr", round(float((r > 0).mean()) * 100, 1), "kinds", {v: sum(1 for t in out if t["k"] == v) for v in ("stop", "take", "time")})
