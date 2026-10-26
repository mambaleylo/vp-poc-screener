import numpy as np, warnings; warnings.filterwarnings("ignore")
from lv_wf import load_dir, select, ts
import lv_engine as LE
Dd = load_dir("lv2", LE.FNAMES); F = Dd["F"]; fam = F[:, 0].astype(int); T = Dd["T"]
yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T]); Dd["YR"] = yr
z = np.load("div_lv2_1537_sc.npz", allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
gm = fam <= 22
for q in (0.99, 0.995, 0.997):
    line = []
    for nm, sub in (("бот", Dd["BOT"]), ("проверка", ~Dd["BOT"])):
        s = select(Dd, 2, SC, THR, q, 12, gm & sub); s = s[T[s] >= ts(2022)]; r = Dd["R"][2][s]
        by = " ".join(f"{Y % 100}:{r[yr[s] == Y].mean():+.2f}({(yr[s] == Y).sum()})" for Y in range(2022, 2027) if (yr[s] == Y).any())
        line.append(f"{nm} n{len(s)} {r.mean():+.3f}R WR {(r > 0).mean()*100:.0f}% [{by}]")
    print(f"HTF E2 q{q}: " + " | ".join(line), flush=True)
s = select(Dd, 2, SC, THR, 0.995, 12, gm); s = s[T[s] >= ts(2022)]
for f in sorted(set(fam[s])):
    m = fam[s] == f; print(f"   {LE.FAMS[f]:9s} {m.sum():4d} {Dd['R'][2][s][m].mean():+.2f}R")
print("лонгов", int((Dd["SIDE"][s] > 0).sum()), "шортов", int((Dd["SIDE"][s] < 0).sum()))
