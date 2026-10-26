"""Lorentzian Classification events (ev5): raw per family, then lv_sel-style walk-forward per group"""
import numpy as np, warnings; warnings.filterwarnings("ignore")
from lv_wf import load_dir, scores, select, ts
import ev5_engine as E5, ev2_engine as E2
Dd = load_dir("ev5", E2.FNAMES); F = Dd["F"]; fam = F[:, 0].astype(int); T = Dd["T"]
yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T]); Dd["YR"] = yr
print("events", len(T), "bot", int(Dd["BOT"].sum()), "check", int((~Dd["BOT"]).sum()), flush=True)
for e in (0, 2, 3):
    R = Dd["R"][e]; print(f"== E{e} сырые", flush=True)
    for f, fn in enumerate(E5.FAMS):
        m = (fam == f) & (T >= ts(2022))
        if m.any(): print(f"   {fn:8s} n{m.sum():6d} ср.R {np.nanmean(R[m]):+.3f}  WR {(R[m] > 0).mean()*100:.0f}%", flush=True)
for grp, gm in (("1h", fam <= 1), ("4h+1d", fam >= 2), ("все", fam >= 0)):
    for e in (2, 0, 3):
        SC, THR = scores(Dd, e, mask=gm, seeds=2)
        for q in (0.99, 0.995):
            line = []
            for sub_nm, sub in (("бот", Dd["BOT"]), ("проверка", ~Dd["BOT"])):
                s = select(Dd, e, SC, THR, q, 12, gm & sub); s = s[T[s] >= ts(2022)]
                r = Dd["R"][e][s]
                by = " ".join(f"{Y % 100}:{r[yr[s] == Y].mean():+.2f}({(yr[s] == Y).sum()})" for Y in range(2022, 2027) if (yr[s] == Y).any())
                line.append(f"{sub_nm} n{len(s)} ср.R {r.mean() if len(r) else 0:+.3f} WR {(r > 0).mean()*100 if len(r) else 0:.0f}% [{by}]")
            print(f"{grp:6s} E{e} q{q}: " + " | ".join(line), flush=True)
