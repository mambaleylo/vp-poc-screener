"""the opposite side of a tested family: every event's side flipped (a level touch -> the break through it; an indicator
signal -> the fade), the E2 exit (stop 1 dATR, take 3R, 72 h, the same fill / entry bar as the original) re-walked on the
1h bars; the control: the unflipped re-walk == the stored E2 R. Then the raw means (all events), and the family's own
walk-forward model on the flipped label (lv_wf.scores, the original features), q 0.995, cap 12 a side, every coin
(lv_wf.select, as div_screen.py did for the original side) -> R by year, bot / check coins.
argv: <dir> <engine> <name> <mask expr on fam>"""
import sys, numpy as np, importlib, warnings, glob, os; warnings.filterwarnings("ignore")
A = sys.argv[1:]; DR, ENG, NM, MX = A[0], A[1], A[2], A[3]
sys.argv = ["x"]
from numba import njit
import lv_engine as LE
from lv_wf import load_dir, scores, select, ts
LX = importlib.import_module(ENG)
Dd = load_dir(DR, LX.FNAMES); fam = Dd["F"][:, 0].astype(int); T, SIDE, SYM, BOT = Dd["T"], Dd["SIDE"], Dd["SYM"], Dd["BOT"]
J, LVv, DA = [], [], []
for fn in sorted(glob.glob(f"{DR}/*.npz")):
    z = np.load(fn)
    if len(z["t"]) == 0: continue
    J.append(z["j"]); DA.append(z["datr"]); LVv.append(z["lv"] if "lv" in z.files else np.full(len(z["t"]), np.nan))
J, DA, LVv = np.concatenate(J).astype(np.int64), np.concatenate(DA), np.concatenate(LVv)
ISLV = DR.startswith("lv")
M = eval(MX) & (T >= ts(2021))
idx = np.where(M)[0]
RF = np.full(len(T), np.nan, np.float32); KF = np.zeros(len(T), np.int32); RC = np.full(len(T), np.nan)
for k in sorted(set(SYM[idx])):
    Tb, O, H, L, C, V = LE.load_np(Dd["names"][k])
    for i in idx[SYM[idx] == k]:
        jE = int(J[i]) if ISLV else int(J[i]) + 1
        if jE >= len(C): continue
        fill = float(LVv[i]) if ISLV else float(O[jE])
        RF[i], KF[i] = LE.simp(O, H, L, C, jE, -int(SIDE[i]), fill, float(DA[i]), 1.0, 3.0, 72, 0.0, 0.0)
        if i % 50 == 0: RC[i] = LE.simp(O, H, L, C, jE, int(SIDE[i]), fill, float(DA[i]), 1.0, 3.0, 72, 0.0, 0.0)[0]
cm = np.isfinite(RC); e2 = Dd["R"].shape[0] - 1 if not ISLV else 2
diff = np.nanmax(np.abs(RC[cm] - Dd["R"][2][cm])) if cm.any() else np.nan
print(f"== {NM} ({DR}, {MX}): событий {len(idx)} | контроль прямой стороны: max|Δ| {diff:.4f} на {int(cm.sum())}", flush=True)
ro = Dd["R"][2][idx]; rf = RF[idx]
print(f"   все события: прямая {np.nanmean(ro):+.3f}R | обратная {np.nanmean(rf):+.3f}R", flush=True)
Dd["R"] = np.vstack([Dd["R"], RF[None, :]]); Dd["K"] = np.vstack([Dd["K"], KF[None, :]]); ef = Dd["R"].shape[0] - 1
SC, THR = scores(Dd, ef, mask=M, seeds=2)
np.savez(f"flip_{DR}_{NM}_sc.npz", SC=SC, THR=np.array(THR, dtype=object))
for q in (0.995, 0.99):
    s = select(Dd, ef, SC, THR, q, 12, M); s = s[T[s] >= ts(2023)]
    r = Dd["R"][ef][s]; b = BOT[s]; y = np.array([int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970) for t in T[s]])
    print(f"   обратная, модель q{q}: сделок {len(s)} {r.mean():+.3f}R WR {np.mean(r > 0)*100:.0f}% | бота {r[b].mean():+.2f}({b.sum()}) контр. {r[~b].mean():+.2f}({(~b).sum()}) | "
          + " ".join(f"{Y % 100}:{r[y == Y].mean():+.2f}({(y == Y).sum()})" for Y in range(2023, 2027) if (y == Y).any()), flush=True)
