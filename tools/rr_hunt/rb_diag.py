import numpy as np
import rb_h as B
R, H = B.lab()
S = B.SD.astype(float)
feats = {"BTC 24ч (по стороне)": S * B.F["b_r24"], "BTC 7д (по стороне)": S * B.F["b_r168"], "BTC vs EMA50 (по стороне)": S * B.F["b_e50"],
         "монета vs EMA200 дня (по стороне)": S * B.F["dd_e200"], "ADX": B.F["adx"], "объём (vol_z)": B.F["vol_z"], "сила пробоя (ATR)": B.BRK,
         "ширина коридора (ATR100)": B.RG, "RSI14 (по стороне от 50)": S * (B.F["rsi14"] - 50), "ATR ratio": B.F["atr_ratio"], "фандинг (по стороне)": S * B.F["fund"],
         "монета 24ч (по стороне)": S * B.F["roc24"]}
for nm, m in (("бот", B.BOT), ("контрольная", B.CHECK)):
    tr = B.replay(m, R, H); r = R[tr]
    print(f"\n== {nm}: {len(tr)} сделок")
    for fn, v in feats.items():
        v = v[tr]; qs = np.nanquantile(v, [0.2, 0.4, 0.6, 0.8]); e = [-np.inf, *qs, np.inf]
        print(f"  {fn:34s} " + " | ".join(f"{np.nanmean(r[(v >= a) & (v < b)]):+.2f}/{np.mean(r[(v >= a) & (v < b)] > 0)*100:2.0f}%" for a, b in zip(e[:-1], e[1:])) + "   (квинтили: R/WR)")
