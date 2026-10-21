"""Portfolio check: the EMA touches (harness version) alone vs EMA + the new levels as a second module (each with its
own selection and cap), growth at an equal 1-in-10 drawdown on the bot coins (45%) and the check coins (50%)."""
import sys, numpy as np, warnings; warnings.filterwarnings("ignore")
from lv_wf import *
import lv_engine as LE
Dd = load_dir("lv2", LE.FNAMES)
env = {nm: Dd["F"][:, k] for k, nm in enumerate(LE.FNAMES)}
e = 2
ema_m = (env["fam"] >= 23) & (env["fam"] < 33) & (env["side"] > 0)
new_m = env["fam"] >= 33
S1, T1 = scores(Dd, e, mask=ema_m)
S2, T2 = scores(Dd, e, mask=new_m)
for q1, q2, cap in ((0.98, 0.99, 12), (0.98, 0.98, 12), (0.99, 0.99, 12), (0.98, 0.99, 6)):
    for nm, sub, tg in (("бот", Dd["BOT"], 0.45), ("проверка", ~Dd["BOT"], 0.50)):
        a = select(Dd, e, S1, T1, q1, cap, ema_m & sub)
        b = select(Dd, e, S2, T2, q2, cap, new_m & sub)
        ja = judge(Dd, e, a, tg); jb = judge(Dd, e, b, tg); jab = judge(Dd, e, np.concatenate([a, b]), tg)
        print(f"q{q1}/{q2} cap{cap} {nm:9s} EMA: {ja['n']} {ja['wk']:.1f}/нед {ja['R']:+.2f}R x{ja['xy']:.2f}/год | SMC: {jb['n']} {jb['wk']:.1f}/нед {jb['R']:+.2f}R x{jb['xy']:.2f}/год | EMA+SMC: {jab['n']} {jab['wk']:.1f}/нед {jab['R']:+.2f}R x{jab['xy']:.2f}/год", flush=True)
