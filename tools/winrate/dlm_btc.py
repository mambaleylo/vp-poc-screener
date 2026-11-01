"""⚡ trades by BTC's state at the touch: BTC's last closed day vs its daily EMA50 (above / below) and its 7-day move, x the
trade's side; R by year on the bot's / check / new coins' pools. -> the table"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE, money_osc as O
T, Op, H, L, C, V = DE.load1h("BTCUSDT")
d = T // 86400; u, i0 = np.unique(d, return_index=True); DC = C[np.r_[i0[1:] - 1, len(C) - 1]]
E50 = O.ema(DC, 50)
def state(t, side):
    j = np.searchsorted(u, t // 86400) - 1
    if j < 60: return None
    above = DC[j] > E50[j]; r7 = DC[j] / DC[j - 7] - 1
    return ("BTC выше EMA50" if above else "BTC ниже EMA50"), ("BTC за 7д вверх" if r7 > 0 else "BTC за 7д вниз"), r7 * side
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
for grp in ("base", "check", "new"):
    P = json.load(open(f"{ST}/wf/pool_{grp}.json"))
    rows = []
    for x in P:
        s = state(x["t1h"], x["side"])
        if s: rows.append((("лонг" if x["side"] > 0 else "шорт"), s[0], s[1], s[2], x["R"], int(np.datetime64(x["t1h"], "s").astype("datetime64[Y]").astype(int) + 1970)))
    print(f"== {grp}: {len(rows)} сделок, средний R {np.mean([r[4] for r in rows]):+.3f}")
    for side in ("лонг", "шорт"):
        for k in ("BTC выше EMA50", "BTC ниже EMA50"):
            s = [r for r in rows if r[0] == side and r[1] == k]
            if not s: continue
            ys = " ".join(f"{y}:{np.mean([r[4] for r in s if r[5] == y]):+.2f}({sum(1 for r in s if r[5] == y)})" for y in (2023, 2024, 2025, 2026) if any(r[5] == y for r in s))
            print(f"   {side} · {k}: {len(s)} сд. {np.mean([r[4] for r in s]):+.3f}R | {ys}")
        for k in ("BTC за 7д вверх", "BTC за 7д вниз"):
            s = [r for r in rows if r[0] == side and r[2] == k]
            ys = " ".join(f"{y}:{np.mean([r[4] for r in s if r[5] == y]):+.2f}" for y in (2023, 2024, 2025, 2026) if any(r[5] == y for r in s))
            print(f"   {side} · {k}: {len(s)} сд. {np.mean([r[4] for r in s]):+.3f}R | {ys}")
