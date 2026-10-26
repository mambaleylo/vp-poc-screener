"""the new levels (lv5_engine): raw per family, then the yearly walk-forward model (lv_wf.scores, BOT coins only,
the threshold from the previous year's out-of-sample scores) per group — the volume profile / the Fibonacci / both —
selected at q 0.99 / 0.995, cap 12 a side: R by year on the bot coins (time out of sample) and on the 84 check coins
(never trained on) — the SMC research's judging"""
import sys, numpy as np, warnings; warnings.filterwarnings("ignore")
from lv_wf import load_dir, scores, select, ts
import lv8_engine as LE
Dd = load_dir("lv8", LE.FNAMES); F = Dd["F"]; fam = F[:, 0].astype(int); T = Dd["T"]
yr = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T]); Dd["YR"] = yr
print("events", len(T), "bot", int(Dd["BOT"].sum()), "check", int((~Dd["BOT"]).sum()), flush=True)
for e, nm in ((0, "E0 EMA-выход"), (2, "E2 стоп 1 dATR, тейк 3R, 72ч")):
    R = Dd["R"][e]
    print(f"== {nm}: сырые (все касания)", flush=True)
    for f, fn in enumerate(LE.FAMS):
        m = (fam == f) & (T >= ts(2022))
        print(f"   {fn:8s} n{m.sum():6d} ср.R {np.nanmean(R[m]):+.3f}  WR {(R[m] > 0).mean()*100:.0f}%", flush=True)
for grp, gm in (("SMC 2h", fam <= 5), ("SMC 8h+12h", (fam >= 6) & (fam <= 17)), ("SMC 3d", fam >= 18), ("SMC все ТФ", fam >= 0)):
    for e in (2, 0):
        SC, THR = scores(Dd, e, mask=gm, seeds=2)
        for q in (0.99, 0.995):
            line = []
            for sub_nm, sub in (("бот", Dd["BOT"]), ("проверка", ~Dd["BOT"])):
                s = select(Dd, e, SC, THR, q, 12, gm & sub)
                s = s[T[s] >= ts(2022)]
                r = Dd["R"][e][s]
                by = " ".join(f"{Y % 100}:{r[yr[s] == Y].mean():+.2f}({(yr[s] == Y).sum()})" for Y in range(2022, 2027) if (yr[s] == Y).any())
                line.append(f"{sub_nm} n{len(s)} ср.R {r.mean() if len(r) else 0:+.3f} WR {(r > 0).mean()*100 if len(r) else 0:.0f}% [{by}]")
            print(f"{grp:15s} E{e} q{q}: " + " | ".join(line), flush=True)
