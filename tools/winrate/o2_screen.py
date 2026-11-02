"""the shifted 4h stream (wick4h_o2) — the user: "поинтереснее гипотезы… фильтры, разные тейки стопы для 4ч со сдвигом": its
orders (allorders_wick4h_o2.npz, the lab's yearly walk-forward) re-walked on the 1h candles with other exits (take x stop x
hold), then filters on the deployed exits: the same coin & side's standard-grid 4h order 2 h before (a repeat), the bar's
closing hour, the side, the score over the threshold, the ATR %. Picked on 2023-2024, checked on 2025-2026 (a rule counts only
if it holds in both); per cell: trades, R a trade, R a year. usage: o2_screen.py"""
import os, sys, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE
ST = "/home/user/vp-lab-store"; ts = lambda y: int(np.datetime64(f"{y}-01-01", "s").astype(int))
MF = {s["name"]: s for s in json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json"))["streams"]}; S4 = MF["wick4h"]
z = np.load(f"{ST}/wf/allorders_wick4h_o2.npz", allow_pickle=True); Z = {k: z[k] for k in z.files}
Z["coin"] = Z["coin"].astype(str); m = Z["t"] >= ts(2023); Z = {k: v[m] for k, v in Z.items()}
H = {(ts(2023), ts(2025)): "2023-24", (ts(2025), ts(2027)): "2025-26"}
def cell(R, t, sel):
    out = []
    for (a, b), nm in H.items():
        x = R[sel & np.isfinite(R) & (t >= a) & (t < b)]; yrs = (min(b, ts(2026) + 273 * 86400) - a) / (365 * 86400)
        out.append(f"{len(x):5d} {x.mean() if len(x) else 0:+.3f} {x.sum() / yrs:+5.0f}/г")
    return " | ".join(out)
coins = sorted(set(Z["coin"])); H1 = {c: DE.load1h(c) for c in coins}
def rewalk(take, soft, hold):
    R = np.full(len(Z["t"]), np.nan)
    for c in coins:
        i = np.flatnonzero(Z["coin"] == c)
        fl, _, _, r, _, _ = DE.walk("wick4h_o2", H1[c], Z["t"][i], Z["side"][i], Z["lv"][i], Z["atr"][i], take, soft, S4["hard_stop_atr"], hold)
        R[i] = np.where(fl, r, np.nan)
    return R
t = Z["t"]; ALL = np.ones(len(t), bool)
print(f"выходы бота (тейк {S4['take_atr']}, стоп {S4['stop_atr']}, 32 свечи): {cell(Z['R'].astype(float), t, Z['filled'].astype(bool))}", flush=True)
print("\nВЫХОДЫ: тейк × стоп × удержание | 2023-24: сделок, R, R в год | 2025-26", flush=True)
for hold in (16, 32, 48):
    for take in (1.0, 1.2, 1.5, 2.0):
        for soft in (1.5, 1.75, 2.25):
            print(f"тейк {take} стоп {soft} свечей {hold} | {cell(rewalk(take, soft, hold), t, ALL)}", flush=True)
R = Z["R"].astype(float); F = Z["filled"].astype(bool)
# the standard grid's order of the same coin & side 2 h before (alive then: within 4 of its bars)
s4 = np.load(f"{ST}/wf/allorders_wick4h_clr.npz", allow_pickle=True); key = {}
for c, tt, sd in zip(s4["coin"].astype(str), s4["t"], s4["side"]): key.setdefault((c, int(sd)), []).append(int(tt))
for k_ in key: key[k_] = np.array(sorted(key[k_]))
rep = np.array([bool(len(key.get((c, int(sd)), [])) and ((key[(c, int(sd))] <= tt) & (key[(c, int(sd))] > tt - 4 * 4 * 3600)).any())
                for c, tt, sd in zip(Z["coin"], t, Z["side"])])
pr = Z["score"] / Z["thr"]; atrp = Z["atr"] / Z["lv"] * 100; hr = (t // 3600) % 24
print("\nФИЛЬТРЫ (выходы бота) | 2023-24 | 2025-26", flush=True)
for nm, sel in [("все", F), ("заявка обычного 4ч уже стоит (повтор)", F & rep), ("без повтора", F & ~rep), ("лонги", F & (Z["side"] > 0)), ("шорты", F & (Z["side"] < 0))] + \
        [(f"закрытие свечи {h:02d} UTC", F & (hr == h)) for h in (2, 6, 10, 14, 18, 22)] + \
        [(f"оценка/порог {a}–{b}", F & (pr >= a) & (pr < b)) for a, b in ((1.0, 1.05), (1.05, 1.15), (1.15, 1.3), (1.3, 9))] + \
        [(f"ATR {a}–{b}% цены", F & (atrp >= a) & (atrp < b)) for a, b in ((0, 1), (1, 1.5), (1.5, 2.5), (2.5, 99))]:
    print(f"{nm} | {cell(R, t, sel)}", flush=True)
print("o2 screen done", flush=True)
