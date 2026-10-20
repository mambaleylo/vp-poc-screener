"""📈 v0.99.647: the stop 2 ATR + the exit channel 15 after +4R — the bot's research stats (RBX_RESEARCH / _MONTHS) and
the backtest list ("rbx" in vp_bt_trades.json), from rb_sim2's re-simulated exits."""
import json, datetime as dt, numpy as np
import rb_h as B, rb_sim2 as S2
from mk import ts
from bt_trades import gate_sym
STOP, TR, NE2 = 2.0, 4.0, 15
out, lst = {}, []
for tfh in (24, 12):
    for mode, half in (("dc20", 0.0), ("half2dc20", 2.0)):
        M = B.BOT & (B.TF == tfh)
        R, H = S2.outcomes(M, stop_k=STOP, tight_r=TR, ne2=NE2, half=half); EX = S2.outcomes.EX; tr = B.replay(M, R, H)
        yrs = {}
        for Y in (2021, 2022, 2023, 2024, 2025):
            m = B.YR[tr] == Y; rs = R[tr[m]]; o = tr[m][np.argsort(B.T[tr[m]] + H[tr[m]] * tfh * 3600)]; c = np.cumsum(R[o])
            dd = float(np.max(np.maximum.accumulate(np.r_[0, c]) - np.r_[0, c])) if len(c) else 0.0
            wk = ((ts(Y + 1) if Y < 2025 else ts(2026, 10)) - ts(Y)) / 604800
            yrs[str(Y)] = {"n": int(m.sum()), "avg": round(float(rs.mean()), 2), "wk": round(float(m.sum() / wk), 1), "sum": round(float(rs.sum()), 1),
                           "dd": round(dd, 1), "wr": round(float((rs > 0).mean() * 100), 1), "days": round(float(np.mean(H[tr[m]]) * tfh / 24), 0), "best": round(float(rs.max()), 1)}
        o = tr[np.argsort(B.T[tr] + H[tr] * tfh * 3600)]; run = w = 0
        for i in o: run = run + 1 if R[i] < 0 else 0; w = max(w, run)
        out[f"{tfh}_{mode}"] = {"years": yrs, "max_losing_streak": w}
        print(tfh, mode, {y: (v["n"], v["avg"], v["wr"]) for y, v in yrs.items()}, "streak", w, flush=True)
        if mode == "dc20":
            if tfh == 24:
                mon = {}
                for i in tr:
                    k = dt.datetime.fromtimestamp(int(B.T[i] + H[i] * tfh * 3600), dt.timezone.utc).strftime("%Y-%m")
                    a = mon.setdefault(k, [0, 0.0]); a[0] += 1; a[1] += R[i]
                allm = [f"{y}-{m:02d}" for y in range(2021, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]
                months = {"months": [[k, mon[k][0], round(mon[k][1], 1)] for k in sorted(mon) if k >= "2025-01"],
                          "pos_months": sum(1 for k in allm if mon.get(k, [0, 0])[1] > 0), "all_months": len(allm)}
            n0 = B.CH[tfh][0]
            for i in tr:
                O, Hb, L, C, T, atr, LO, HI, _ = S2.bars(B.SYM[i], tfh); j = int(np.searchsorted(T, B.T[i])); s = int(B.SD[i])
                e = O[j + 1]; sl = e - s * STOP * atr[j]; xb = min(len(T) - 1, j + int(H[i]))
                gs, sc = gate_sym(B.SYM[i])
                kind = "stop" if R[i] < 0 and abs(EX[i] - sl) < 1e-12 else ("time" if int(H[i]) >= (180 if tfh == 24 else 360) else "trend")
                lst.append({"s": gs, "d": s, "c": "1d" if tfh == 24 else "12h", "t": int(T[j]), "e": round(e / sc, 10), "sl": round(sl / sc, 10), "x": int(T[xb]),
                            "xp": round(float(EX[i]) / sc, 10), "r": round(float(R[i]), 3), "k": kind, "hh": round(float(Hb[j - n0:j].max()) / sc, 10),
                            "ll": round(float(L[j - n0:j].min()) / sc, 10), "n": n0, "t0": int(T[j - n0] - tfh * 3600)})
json.dump({"research": out, "months": months}, open(f"{B.D}/rbx_research_v647.json", "w"), separators=(",", ":"))
bt = json.load(open(f"{B.D}/vp_bt_trades.json")); bt["rbx"] = sorted(lst, key=lambda x: x["t"])
json.dump(bt, open(f"{B.D}/vp_bt_trades.json", "w"), separators=(",", ":"))
print("bt rbx", len(lst), "avg", round(float(np.mean([x["r"] for x in lst])), 3))
