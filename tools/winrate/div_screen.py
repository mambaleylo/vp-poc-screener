"""diversifier screen: the bundle's monthly result (the deployed rows, risk-weighted R by the exit month: ⚡4.5 P/R3
SMC2.5 EMA2, no caps -- a ranking proxy), its worst quarter of months; each candidate family group's walk-forward trades
(E2, q 0.995, cap 12 a side, every coin; the model as lv_wf): R in the bundle's bad months vs elsewhere, the monthly
correlation"""
import sys, os, numpy as np, warnings, importlib; warnings.filterwarnings("ignore")
exec(open("port_be5d.py").read())
from lv_wf import load_dir, scores, select
t0_, t1_, r__, st__, sth_, buf_, md_, ci_, wg_, tbr_ = A_.T; md_ = md_.astype(int)
RK = np.array([4.5, 3, 2.5, 2.0])
def mon(t): return ((np.asarray(t, np.int64).astype("datetime64[s]").astype("datetime64[M]").astype(int)))
M0, M1 = mon([ts(2022, 1)])[0], mon([ts(2026, 10)])[0]
NM = M1 - M0
bm = np.zeros(NM)
mm = mon(t1_) - M0; ok = (mm >= 0) & (mm < NM)
np.add.at(bm, mm[ok], (RK[md_] * wg_ * r__)[ok])
bad = bm <= np.quantile(bm[12:], 0.25)   # from 2023 (the bundle's modules all live)
bad[:12] = False
print("связка по месяцам (% прибли.):", " ".join(f"{str(np.datetime64(int(M0 + k), 'M'))[2:]}:{bm[k]:+.0f}" for k in range(NM)), flush=True)
print("худшие месяцы:", [str(np.datetime64(int(M0 + k), 'M')) for k in np.where(bad)[0]], flush=True)
CANDS = [
    ("iFVG", "lv7", "lv7_engine", "(fam % 6 == 2) | (fam % 6 == 3)", "ifvg_sc.npz"),
    ("SMC 8h/12h", "lv8", "lv8_engine", "(fam >= 6) & (fam <= 17)", "SMC8h12h_sc.npz"),
    ("деривативы (OI/фандинг/LS)", "ev2", "ev2_engine", "fam >= 0", None),
    ("GitHub-индикаторы ev4", "ev4", "ev4_engine", "fam >= 0", None),
    ("классика ev3", "ev3", "ev3_engine", "fam >= 0", None),
    ("Фибоначчи", "lv5", "lv5_engine", "fam >= 6", None),
    ("профиль объёма", "lv5", "lv5_engine", "fam <= 5", None),
    ("Lorentzian", "ev5", "ev5_engine", "fam >= 0", None),
    ("HTF-уровни (PDH/PWH/SMA/BB)", "lv2", "lv_engine", "fam <= 22", None),
]
DC = {}
for nm, dr, eng, mexpr, scf in CANDS:
    try:
        LX = importlib.import_module(eng)
        if dr not in DC:
            DC.clear(); DC[dr] = load_dir(dr, LX.FNAMES)
        Dd = DC[dr]; fam = Dd["F"][:, 0].astype(int); gm = eval(mexpr)
        scf = scf or f"div_{dr}_{abs(hash(mexpr)) % 10000}_sc.npz"
        if os.path.exists(scf):
            z = np.load(scf, allow_pickle=True); SC = z["SC"]; THR = z["THR"].item()
        else:
            SC, THR = scores(Dd, 2, mask=gm, seeds=2); np.savez(scf, SC=SC, THR=np.array(THR, dtype=object))
        s = select(Dd, 2, SC, THR, 0.995, 12, gm); s = s[Dd["T"][s] >= ts(2023)]
        R = Dd["R"][2][s]; tx = Dd["T"][s] + Dd["K"][2][s] * 3600
        m = mon(tx) - M0; okk = (m >= 0) & (m < NM)
        cm = np.zeros(NM); np.add.at(cm, m[okk], R[okk])
        inbad = bad[np.clip(m, 0, NM - 1)] & okk
        live = np.arange(NM) >= 12
        cor = np.corrcoef(cm[live], bm[live])[0, 1]
        print(f"{nm:28s} сделок {len(s):4d} ср.R {R.mean():+.2f} | в худшие месяцы связки: {inbad.sum():3d} сделок, ср.R {R[inbad].mean() if inbad.any() else 0:+.2f}, сумма {R[inbad].sum():+.1f}R"
              f" | в остальные: ср.R {R[~inbad].mean():+.2f} | корр. по месяцам {cor:+.2f}", flush=True)
    except Exception as ex:
        print(nm, "ошибка", repr(ex)[:200], flush=True)
