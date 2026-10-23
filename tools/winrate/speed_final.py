import os; os.environ["TFH"] = "4"
import numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("s25_money.py").read().split("roll = ")[0])
za = np.load("s25_sc_4h_w1_0_A_base.npz", allow_pickle=True); zb = np.load("s25_sc_4h_w1_0_A_0-1-2-5-8.npz", allow_pickle=True)
ta, tb_ = za["THR"].item(), zb["THR"].item()
VARS = {"новая (20 моделей, q0.99)": ((za["SC"] + zb["SC"]) / 2, {Y: (ta[Y] + tb_[Y]) / 2 for Y in ta}), "без дневных (q0.99)": (za["SC"], ta)}
for nm, (SC, THR) in VARS.items():
    sel = select(D, 0, SC, THR, 0.99, 20, ~D["usdc"]); sel = sel[D["t"][sel] >= ts(2022)]
    t0 = D["t"][sel].astype(float); o = np.argsort(t0); sel = sel[o]; t0 = t0[o]
    t1 = t0 + D["K"][0][sel] * 3600.0; R = D["R"][0][sel].astype(float); ST = np.clip(2 * D["F"][sel, 2].astype(float) / 100, 0.002, 0.5)
    for rk in (0.02, 0.03, 0.04):
        for sh, lab in ((-0.025, "осторожно"), (-0.04, "жёстко")):
            cells = []
            for mo in (1, 3, 6, 9, 12):
                starts = np.arange(ts(2024), ts(2026, 10) - mo * 30.4 * 86400, 7 * 86400.0)
                v = np.array([PL.multi(t0, t1, R, ST, int(np.searchsorted(t0, s)), s + mo * 30.4 * 86400, 20, rk, False, sh) for s in starts]) + 100
                cells.append(f"{mo}м ${np.median(v):,.0f} (10%: ${np.percentile(v, 10):,.0f}, <$100 {np.mean(v < 100) * 100:.0f}%)")
            print(f"{nm} {rk*100:.0f}% {lab}: " + " | ".join(cells), flush=True)
