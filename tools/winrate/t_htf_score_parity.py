"""decision parity: the bot's own code (smc_candidates with the HTF families, the exported trees via zm_tree_pred,
htf_pick) on the bars closed before each touch hour of 2026 vs the research's walk-forward scores / percentiles:
the backtest's 2026 trades must be picked, and the decision must agree on a random sample of other long touches"""
import sys, math, time, bisect, calendar, json, numpy as np
src = open("/home/user/vp-poc-screener/vp_poc_screener.py").read()
exec(src[src.index("SMC_FAMS = ["):src.index("def smc_model():")])
exec(src[src.index("def zm_tree_pred(trees, x):"):src.index("def zm_model():")])
exec(src[src.index("def htf_scores(m, f):"):src.index("def htf_arm(late=False):")])
import lv_engine as LE
from bt_trades import gate_sym
M = json.load(open("/home/user/vp-poc-screener/vp_htf_model.json"))
sp = json.load(open("lv/split.json"))
zo = np.load("div_lv2_1537_sc.npz", allow_pickle=True); zn = np.load("htf_long_sc.npz", allow_pickle=True)
from lv_wf import load_dir
Dd = load_dir("lv2", LE.FNAMES); T = Dd["T"]; fam = Dd["F"][:, 0].astype(int); SIDE = Dd["SIDE"]
SCo, SCn = zo["SC"], zn["SC"]
names = Dd["names"]; SYMI = Dd["SYM"]
BT = {(x["s"], x["t"], x["lvl"]) for x in json.load(open("htf_bt_v1.json")) if x["t"] >= 1767225600}
def bars(sym):
    T_, O, H, L, C, V = LE.load_np(sym)
    return [{"time": int(t), "open": o, "high": h, "low": l, "close": c, "volume": v} for t, o, h, l, c, v in zip(T_, O, H, L, C, V)]
def agg(h, sec):
    out = []
    for c in h:
        ps = c["time"] // sec * sec
        if not out or out[-1]["time"] != ps: out.append(dict(c, time=ps))
        else:
            b_ = out[-1]; b_["high"] = max(b_["high"], c["high"]); b_["low"] = min(b_["low"], c["low"]); b_["close"] = c["close"]; b_["volume"] += c["volume"]
    return out
B = bars("BTCUSDT"); BTT = [c["time"] for c in B]; Bd = agg(B, 86400)
rng = np.random.default_rng(3)
bot = set(sp["bot"])
m26 = (T >= 1767225600) & (fam <= 22) & (SIDE > 0) & np.isfinite(SCo) & np.isfinite(SCn)
idx_all = np.flatnonzero(m26 & np.isin(np.array(names)[SYMI], list(bot)))
sel = [i for i in idx_all if (gate_sym(names[SYMI[i]])[0], int(T[i]), LE.FAMS[fam[i]]) in BT]
rnd = list(rng.choice(idx_all, 400, replace=False))
print("2026 backtest trades found", len(sel), "of", len(BT), flush=True)
cache = {}
res = {"sel": [0, 0, 0, 0.0, 0.0], "rnd": [0, 0, 0, 0.0, 0.0]}   # n, missing level, decision differs, max|so diff|, max|sn diff|
thr_o, thr_n = float(M["thr_o"]), float(M["thr_n"])
for kind, lst in (("sel", sel), ("rnd", rnd)):
    for i in lst:
        sym = names[SYMI[i]]
        if sym not in cache:
            h = bars(sym); cache.clear(); cache[sym] = (h, [c["time"] for c in h], agg(h, 86400), agg(h, 14400))
        h, hT, d, h4 = cache[sym]
        t = int(T[i]); J = bisect.bisect_left(hT, t); bj = bisect.bisect_left(BTT, t)
        cs = smc_candidates(h[max(0, J - 1000):J], [c for c in h4 if c["time"] + 14400 <= t][-1000:], [c for c in d if c["time"] + 86400 <= t],
                            B[max(0, bj - 1000):bj], [c for c in Bd if c["time"] + 86400 <= t], t, want=set(M["htf_fams"]))
        c = next((c for c in cs if c["fam"] == LE.FAMS[fam[i]] and c["side"] == 1), None)
        r = res[kind]; r[0] += 1
        if not c:
            r[1] += 1; continue
        so, sn = htf_scores(M, c["f"])
        r[3] = max(r[3], abs(so - SCo[i])); r[4] = max(r[4], abs(sn - SCn[i]))
        bot_pick = htf_pick(M, so, sn) != ""
        res_pick = (SCo[i] > thr_o) or (SCn[i] > thr_n)
        if bot_pick != res_pick:
            r[2] += 1; print("DECISION", kind, sym, t, LE.FAMS[fam[i]], "bot", round(so, 4), round(sn, 4), "research", round(float(SCo[i]), 4), round(float(SCn[i]), 4), flush=True)
        if kind == "sel" and not bot_pick:
            print("SEL NOT PICKED", sym, t, LE.FAMS[fam[i]], flush=True)
for k, r in res.items():
    print(f"== {k}: событий {r[0]}, уровень не найден {r[1]}, решение разошлось {r[2]}, max|оценка o − исследование| {r[3]:.5f}, n {r[4]:.5f}")
