"""look-ahead + parity: the BOT's own smc_candidates (vp_poc_screener.py, want = the HTF families 0..22) given ONLY the
bars closed before the touch hour vs the research's lv2 levels and features of the HTF long events: every trade of the
deployed rule (OR of the two models at q0.995, htfS_ИЛИ_q0.995.json) + a random sample of other long events. A level /
feature that needs a later bar cannot be reproduced from the truncated bars -> a mismatch is printed."""
import sys, math, time, bisect, calendar, json, numpy as np
src = open("/home/user/vp-poc-screener/vp_poc_screener.py").read()
a = src.index("SMC_FAMS = ["); b = src.index("def smc_model():")
exec(src[a:b])
import lv_engine as LE
from bt_trades import gate_sym
assert SMC_FAMS == LE.FAMS
sp = json.load(open("lv/split.json"))
SEL = {(x["s"], x["t"]) for x in json.load(open("htfS_ИЛИ_q0.995.json"))}
def bars(sym):
    T, O, H, L, C, V = LE.load_np(sym)
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v} for t, o, h, l, c, v in zip(T, O, H, L, C, V)]
def agg(h, sec):
    out = []
    for c in h:
        ps = c["time"] // sec * sec
        if not out or out[-1]["time"] != ps: out.append(dict(c, time=ps))
        else:
            b_ = out[-1]; b_["high"] = max(b_["high"], c["high"]); b_["low"] = min(b_["low"], c["low"]); b_["close"] = c["close"]; b_["volume"] += c["volume"]
    return out
B = bars("BTCUSDT"); BT = [c["time"] for c in B]; Bd = agg(B, 86400)
rng = np.random.default_rng(1)
WANT = set(range(23))
res = {"sel": [0, 0, np.zeros(29)], "rnd": [0, 0, np.zeros(29)]}
nsel_found = 0
for sym in sp["bot"]:
    try:
        z = np.load(f"lv2/{sym}.npz")
    except FileNotFoundError:
        continue
    gs, scl = gate_sym(sym)
    idx = np.flatnonzero((z["fam"] <= 22) & (z["side"] > 0) & (z["t"] >= 1672531200))
    if not len(idx): continue
    sel = [i for i in idx if (gs, int(z["t"][i])) in SEL]
    nsel_found += len(sel)
    rnd = list(rng.choice(idx, min(4, len(idx)), replace=False))
    if not sel and not rnd: continue
    h = bars(sym); hT = [c["time"] for c in h]; d = agg(h, 86400); h4 = agg(h, 14400)
    for kind, lst in (("sel", sel), ("rnd", rnd)):
        for i in lst:
            t = int(z["t"][i]); J = bisect.bisect_left(hT, t)
            h1c = h[max(0, J - 1000):J]
            d1c = [c for c in d if c["time"] + 86400 <= t]
            h4c = [c for c in h4 if c["time"] + 14400 <= t][-1000:]
            bj = bisect.bisect_left(BT, t)
            cands = smc_candidates(h1c, h4c, d1c, B[max(0, bj - 1000):bj], [c for c in Bd if c["time"] + 86400 <= t], t, want=WANT)
            fam = SMC_FAMS[int(z["fam"][i])]
            m = [c for c in cands if c["fam"] == fam and c["side"] == 1]
            r = res[kind]; r[0] += 1
            if not m or abs(m[0]["lv"] / float(z["lv"][i]) - 1) > 1e-6:
                r[1] += 1
                if r[1] <= 6: print("MISS", kind, sym, t, fam, float(z["lv"][i]), [(c["fam"], c["side"], round(c["lv"], 8)) for c in cands if c["fam"] == fam])
                continue
            r[2] = np.maximum(r[2], np.abs(np.array(m[0]["f"]) - z["F"][i].astype(float)))
print("сделок правила найдено в lv2:", nsel_found, "из", len(SEL))
for kind in ("sel", "rnd"):
    r = res[kind]
    print(f"== {kind}: событий {r[0]}, не совпал уровень {r[1]}")
    for k, nm in enumerate(LE.FNAMES): print(f"   {nm:10s} max|diff| {r[2][k]:.5f}")
