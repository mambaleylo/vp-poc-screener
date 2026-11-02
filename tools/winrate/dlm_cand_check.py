"""the ⚡ 4h candidate (vp_dlm_model_lab_4h.json) vs the deployed on the CHECK coins (never trained on by either) — 2026's
orders: over each one's threshold, the fills and their R with the bot's exits; and the order count a month"""
import os, sys, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE
from dlm_allorders_dep import walk, pack   # the numba trees
from common import V
ST = "/home/user/vp-lab-store"; C = json.load(open(f"{ST}/feat_coins.json"))
def bn(gs):
    b = gs.replace("_USDT", "")
    for c in (b + "USDT", "1000" + b + "USDT"):
        if c in C["base"] or c in C["new"]: return c
r127 = sorted({bn(c) for c in V.RESEARCH_COINS_127 if bn(c)}); check = r127[2::3]
A0 = 1767225600
for nm, fn in (("бот", "/home/user/vp-poc-screener/vp_dlm_model.json"), ("кандидат", f"{ST}/wf/vp_dlm_model_lab_4h.json")):
    S = [s for s in json.load(open(fn))["streams"] if s["name"] == "wick4h"][0]; P = pack(S["models"]); p = DE.STREAMS["wick4h"]; bs = 14400; B = DE.btc_ctx("wick4h")
    n = 0; Rs = []
    for c in check:
        h1 = DE.load1h(c); ev = DE.features(c, "wick4h", B, h1)
        if ev is None: continue
        tsc = ev["t"] + bs; ii = np.flatnonzero(tsc >= A0)
        if not len(ii): continue
        sc = walk(np.ascontiguousarray(ev["f"][ii].astype(np.float64)), *P[:7], P[7], 0); ii = ii[sc >= S["thr"]]; n += len(ii)
        if not len(ii): continue
        T1, O1, H1, L1, C1, V1 = h1
        fl, _, _, R, _, _ = DE.fill_walk(T1, O1, H1, L1, C1, tsc[ii], ev["side"][ii].astype(np.int64), ev["lv"][ii], ev["atr"][ii], bs, p["ch"], DE.ALIVE, DE.HOLD,
                                         S["take_atr"], S["stop_atr"], S["hard_stop_atr"], DE.FEE_IN, DE.FEE_TAKE, DE.FEE_OUT, DE.FUND)
        Rs += list(R[fl & np.isfinite(R)])
    print(f"{nm}: 2026, {len(check)} проверочных монет — ордеров {n} ({n / 10:.0f}/мес), исполнено {len(Rs)}, R {np.mean(Rs):+.3f}, сумма {np.sum(Rs):+.0f}R", flush=True)
