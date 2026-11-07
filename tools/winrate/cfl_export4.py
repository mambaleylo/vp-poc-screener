"""🔄 Классика наоборот v0.99.777 (the user: "Количество сделок и винрейт продолжаем улучшать, тейки стопы все пересматривает и
проверяем" -> "Да, лимит 35%"): v0.99.776's rule (the drought 14 d -> q 0.99, the 210 coins, the threshold of the 127's scores) with
the exits of cfl_var.py's rounds 3–5: the stop 0.5 dATR at the 4h close (was 0.75 at the 1d close), the emergency 1.0 dATR (2x),
the take 6R (was 4R), <= 30 at once (was 20); the money (money_cfl.py, run_cfl5.sh): on its own room of 35% of the equity (was 25%)
the bundle with HTF — the usual year $115k vs $69.6k, the bad $27.6k vs $21.8k, the last 12 months $608k vs $491k, 6 of 6 paired runs.
The backtest list = cfl_var.py's "dr14+c210+cap30+s0.5t6+ctf4" with the exit kind / price (the bot's _cs_walk).
-> vp_bt_trades.json "cfl", vp_cfl_model.json (rule stop_datr / stop_close_h / hard_x / take_r / side_cap, research). Run in tools/winrate."""
import os, sys, json, numpy as np
sys.argv = ["x"]
exec(open("cfl_var.py").read().rsplit('if __name__ == "__main__":', 1)[0])
ROOT = os.path.join(os.path.dirname(os.path.abspath("cfl_var.py")), "..", "..")
def gate_sym(sym):   # = tools/adaptation/bt_trades.py
    b = sym[:-4]
    return (b[4:] if b.startswith("1000") else b) + "_USDT", (1000.0 if b.startswith("1000") else 1.0)
def walk_kind(Tb, O, H, L, C, jE, s, fill, risk, hard_d, take, hold, ctf):
    """the bot's _cs_walk (no break-even): -> (kind, exit price, bars)"""
    hs = fill - s * hard_d; sl = fill - s * risk; tp = fill + s * take * risk; e = min(len(C), jE + hold)
    for q in range(e - jE):
        b = jE + q
        if (s > 0 and L[b] <= hs) or (s < 0 and H[b] >= hs):
            gap = (s > 0 and O[b] <= hs) or (s < 0 and O[b] >= hs); return "hard", (O[b] if (gap and q > 0) else hs), q + 1
        if q > 0 and ((s > 0 and H[b] >= tp) or (s < 0 and L[b] <= tp)): return "take", tp, q + 1
        if (Tb[b] + 3600) % (ctf * 3600) == 0 and ((s > 0 and C[b] <= sl) or (s < 0 and C[b] >= sl)): return "stop", C[b], q + 1
    return "time", C[e - 1], e - jE
NM = "dr14+c210+cap30+s0.5t6+ctf4"; SK, HD, TK, CTF, CAP = 0.5, 1.0, 6.0, 4, 30
p = dict(BASE)
for part in NM.split("+"): p = merge(p, VARS[part])
assert (p["ex"]["sk"], p["ex"]["hard"], p["ex"]["take"], p["ex"]["ctf"], p["cap"]) == (SK, HD, TK, CTF, CAP), p
L = build(p)
idx = {(Dd["names"][SYM[i]], int(T[i])): i for i in range(len(T))}
out, bad = [], 0
for x in L:
    i = next(j for j in [idx.get((x["sym"], x["t0"] - 3600)), idx.get((x["sym"], x["t0"] - 4 * 3600))] if j is not None) if False else None
    # find the event: the one whose entry (the next hour's open) is t0 and whose side is the trade's opposite
    EXK = tuple(sorted(p["ex"].items()))
    cand = [k for k in np.flatnonzero((SYM == Dd["names"].index(x["sym"])) & (-SIDE == x["side"])) if RC.get((k, EXK)) and RC[(k, EXK)][2] == x["t0"]]
    i = cand[0]
    Tb, O, H, Lw, C_, V = bars(SYM[i]); jE = int(J[i]) + 1; s = x["side"]; fill = float(O[jE]); risk = fill * SK * float(DA[i]) / 100; hd = fill * HD * float(DA[i]) / 100
    kind, ex, k_ = walk_kind(Tb, O, H, Lw, C_, jE, s, fill, risk, hd, TK, 96, CTF)
    r_chk = s * (ex - fill) / risk - (0.001 + 0.0003 * k_ / 24) * fill / risk
    bad += abs(r_chk - x["r"]) > 1e-6
    gs, scl = gate_sym(x["sym"]); fm = E3.FAMS[int(FAM[i])] if hasattr(E3, "FAMS") else str(int(FAM[i]))
    out.append({"s": gs, "d": s, "c": "1h", "tf": "4h" if fm.endswith("_4h") else "1d", "lvl": fm, "t": x["t0"], "e": round(fill / scl, 10),
                "sl": round((fill - s * risk) / scl, 10), "hs": round((fill - s * hd) / scl, 10), "tp": round((fill + s * TK * risk) / scl, 10),
                "x": x["t1"], "xp": round(float(ex) / scl, 10), "r": round(x["r"], 3), "k": kind})
out.sort(key=lambda y: y["t"])
print("сделок", len(out), "R не совпал у", bad, flush=True)
assert bad == 0
END = int(max(T)) + 3600
rr = np.array([y["r"] for y in out]); tt = np.array([y["t"] for y in out]); years = {}
for Y in range(2023, 2027):
    m = (tt >= ts(Y)) & (tt < ts(Y + 1))
    if m.any(): years[str(Y)] = {"n": int(m.sum()), "avg": round(float(rr[m].mean()), 3), "wr": round(float((rr[m] > 0).mean() * 100), 1), "sum": round(float(rr[m].sum()), 1)}
print(years, flush=True)
bt = json.load(open(f"{ROOT}/vp_bt_trades.json")); bt["cfl"] = out
json.dump(bt, open(f"{ROOT}/vp_bt_trades.json", "w"), separators=(",", ":"))
M = json.load(open(f"{ROOT}/vp_cfl_model.json"))
M["rule"].update({"stop_datr": SK, "stop_close_h": CTF, "hard_x": round(HD / SK, 6), "take_r": TK, "side_cap": CAP})
im, gap = idle([{"t0": y["t"]} for y in out])
M["research"].update({"years": years, "avg": round(float(rr.mean()), 3), "wr": round(float((rr > 0).mean() * 100), 1), "n": len(out),
                      "idle_months": im, "longest_pause_d": gap, "coins_n": len(M["coins"])})
json.dump(M, open(f"{ROOT}/vp_cfl_model.json", "w"), separators=(",", ":"))
print("правило", M["rule"], "| пустых месяцев", im, "пауза", gap, flush=True)
