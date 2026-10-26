"""quiet1.py's judge for the bot's own modules outside the Binance bundle: 📈 Breakout (rbx, 1d / 12h) and 🌊 Cascade (cas)
from vp_bt_trades.json, as a 6th module; also both together"""
import numpy as np, json
exec(open("quiet1.py").read().split("for nm, dr, eng, mexpr, scf in CANDS:")[0])
BB = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
def lst(k):
    out = []
    for t in BB[k]:
        if t.get("r") is None or not t.get("x") or not t.get("e") or not t.get("sl"): continue
        st_ = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); out.append((float(t.get("f") or t["t"]), float(t["x"]), float(t["r"]), st_, st_, 1.5, 5, cid(t["s"]), 1.0, 1e18))
    return np.array(out, float)
for nm, X in (("📈 Пробой", lst("rbx")), ("🌊 Каскад", lst("cas")), ("Пробой+Каскад", np.vstack([lst("rbx"), lst("cas")]))):
    r23 = X[(X[:, 0] >= ts(2023)) & (X[:, 0] < ts(2024)), 2]
    print(f"{nm}: сделок {len(X)}, ср.R {X[:, 2].mean():+.2f}, в 2023: {len(r23)} ср.R {r23.mean():+.2f}, стоп медиана {np.median(X[:, 3])*100:.1f}%", flush=True)
    for rk in (1.0, 2.0, 3.0):
        y, d = go(np.vstack([B, X]), [4.5, 3, 2.5, 2, 2.0, rk]); show(f"+ {nm} {rk}%", y, d, ref)
