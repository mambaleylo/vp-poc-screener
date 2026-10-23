"""the pool streams on the 83 extra coins too (the 127's yearly models applied unchanged, USDC dropped); money sims
on: 127 check coins, 83 new coins, all unseen (check + new), all 210; several stream sets and position modes"""
import sys; AV = list(sys.argv)
import numpy as np, pickle, os, warnings; warnings.filterwarnings("ignore")
import pool as PL
from s15_wf import load, select
from mk import ts
import importlib
def stream_x(mod, dr, fam, scfile, e, q, tk, hold, bar_s, fund_div):
    E = importlib.import_module(mod); fams = E.FAMS
    npy = f"{dr}x_sc_{fam}_{e}.npy"
    if not os.path.exists(npy): return None
    U = load(dr + "x", [fams.index(fam)]); SC = np.load(npy); THR = np.load(scfile, allow_pickle=True)["THR"].item()
    ok = np.array([U["names"][k] != "USDCUSDT" for k in U["sym"]])
    s_ = select(U, e, SC, THR, q, 12, ok); s_ = s_[U["t"][s_] >= ts(2022)]
    by = {}; out = []
    for i in s_: by.setdefault(U["sym"][i], []).append(i)
    for k, idx in by.items():
        Tb, O, H, L, C, V = E.load15(U["names"][k]); atr = E.wilder(H, L, C, 14); a28 = E.wilder(H, L, C, 28); pos = {int(t): j for j, t in enumerate(Tb)}
        for ev in idx:
            s = int(U["side"][ev]); i = pos[int(U["t"][ev])]; a = float(atr[i]); lv = PL.level(fam, C, L, H, atr, a28, i, s)
            fb = next((b for b in range(i + 1, min(i + 5, len(C))) if ((L[b] <= lv) if s > 0 else (H[b] >= lv))), -1)
            if fb < 0: continue
            fill = min(lv, O[fb]) if s > 0 else max(lv, O[fb])
            r, kk, w = PL.sim(O, H, L, C, fb, s, fill, a, tk, 2.0, hold, fund_div)
            out.append((int(Tb[fb]), int(Tb[fb]) + kk * bar_s, float(r), 2 * a / fill, "new", w))
    return out
if __name__ == "__main__":
    X = pickle.load(open("pool_x.pkl", "rb")) if os.path.exists("pool_x.pkl") else {}
    for nm, sp in PL.SPEC.items():
        if nm in X and X[nm] is not None: continue
        X[nm] = stream_x(*sp)
        if X[nm] is not None: print(nm, "new", len(X[nm]), f"WR {np.mean([r[5] for r in X[nm]])*100:.0f}% {np.mean([r[2] for r in X[nm]]):+.3f}R", flush=True)
    pickle.dump(X, open("pool_x.pkl", "wb"))
    MODES = PL.MODES + [(12, 0.05, False, "до 12 по 5%"), (8, 0.10, False, "до 8 по 10%")]
    SETS = {"пул (1ч+4ч+30м+2ч)": ['1ч 2×ATR28 т1.5', '4ч тень т1', '30м 2×ATR28 т1', '2ч 2ATR т1'],
            "без 30м (1ч+4ч+2ч)": ['1ч 2×ATR28 т1.5', '4ч тень т1', '2ч 2ATR т1'],
            "только 4ч тень т1": ['4ч тень т1'],
            "4ч+2ч": ['4ч тень т1', '2ч 2ATR т1']}
    for sn, sel in SETS.items():
        if any(X.get(nm) is None for nm in sel): print(sn, "— нет данных по новым монетам"); continue
        print(f"\n### {sn}")
        parts = {"127 пров": [r for nm in sel for r in PL.P[nm] if r[4] == "check"],
                 "83 новые": [r for nm in sel for r in X[nm]],
                 "невиданные 125": [r for nm in sel for r in PL.P[nm] if r[4] == "check"] + [r for nm in sel for r in X[nm]],
                 "все 210": [r for nm in sel for r in PL.P[nm]] + [r for nm in sel for r in X[nm]]}
        for pn, rows in parts.items():
            print(f"  {pn:15s} n {len(rows):5d} ({len(rows)/58:.0f}/мес) WR {np.mean([r[5] for r in rows])*100:.0f}% {np.mean([r[2] for r in rows]):+.3f}R", flush=True)
            for md in MODES:
                b = PL.money(rows, md, 0.0, 300); c = PL.money(rows, md, -0.025, 300); h = PL.money(rows, md, -0.04, 300)
                print(f"     {md[3]:14s} бэктест ${b[0]:8.0f} ({b[1]*100:.0f}%) · осторожно ${c[0]:7.0f} ({c[1]*100:.0f}%) · жёстко ${h[0]:7.0f} ({h[1]*100:.0f}%)", flush=True)
