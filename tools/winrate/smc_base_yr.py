import numpy as np, warnings; warnings.filterwarnings("ignore")
from lv_wf import load_dir, select, ts
import lv_engine as LE
Dd = load_dir("lv2", LE.FNAMES); F = Dd["F"]; fam = F[:, 0].astype(int); T = Dd["T"]; e = 2
z = np.load("smc_sc.npz", allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T]); Dd["YR"] = yr
gm = fam >= 33
for q in (0.99, 0.995):
    line = []
    for sub_nm, sub in (("бот", Dd["BOT"]), ("проверка", ~Dd["BOT"])):
        s = select(Dd, e, SC, THR, q, 12, gm & sub); s = s[T[s] >= ts(2022)]; r = Dd["R"][e][s]
        by = " ".join(f"{Y % 100}:{r[yr[s] == Y].mean():+.2f}({(yr[s] == Y).sum()})" for Y in range(2022, 2027) if (yr[s] == Y).any())
        line.append(f"{sub_nm} n{len(s)} ср.R {r.mean():+.3f} WR {(r > 0).mean()*100:.0f}% [{by}]")
    print(f"SMC(база) E2 q{q}: " + " | ".join(line), flush=True)
