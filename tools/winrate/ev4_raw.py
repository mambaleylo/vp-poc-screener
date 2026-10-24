"""raw table of the ev4 families: every event (no model), per exit — trades, avg R (fees in), WR, by year 2022..2026"""
import numpy as np, warnings; warnings.filterwarnings("ignore")
from lv_wf import load_dir
import ev4_engine as E
Dd = load_dir("ev4", E.FNAMES)
fam = Dd["F"][:, 0].astype(int); T = Dd["T"]
yr = (T.astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
print("events", len(T), "exits", Dd["R"].shape[0])
EXN = ["E0 стоп .75dATR тейк 4R 72ч ч1/3", "E1 .5dATR 3R 48ч", "E2 1dATR 3R 72ч", "E3 1.5ATR1h 3R 48ч"]
rows = []
for f in sorted(set(fam)):
    m = fam == f
    for e in range(Dd["R"].shape[0]):
        R = np.nan_to_num(Dd["R"][e][m]); y = yr[m]
        by = [R[y == Y].mean() if (y == Y).sum() >= 30 else np.nan for Y in range(2022, 2027)]
        rows.append((E.FAMS[f], e, m.sum(), R.mean(), (R > 0).mean(), by, np.nanmin(by)))
rows.sort(key=lambda r: -r[3])
for nm, e, n, a, wr, by, mn in rows[:60]:
    print(f"{nm:14s} E{e} {n:7d} {a:+.3f}R WR {wr*100:3.0f}% | " + " ".join(f"{b:+.2f}" if b == b else "  —  " for b in by) + f" | худший год {mn:+.2f}")
