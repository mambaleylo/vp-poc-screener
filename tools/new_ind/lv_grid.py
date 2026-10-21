import sys, numpy as np
ARGS = sys.argv[1:]
from lv_wf import *
import lv_engine as LE
Dd = load_dir("lv", LE.FNAMES)
env = {nm: Dd["F"][:, k] for k, nm in enumerate(LE.FNAMES)}
for e in map(int, ARGS[0].split(",")):
    for mexp in ARGS[1].split(";"):
        mask = eval(mexp, {"np": np}, env) if mexp else np.ones(len(Dd["T"]), bool)
        SC, THR = scores(Dd, e, mask=mask)
        for q in (0.98, 0.99, 0.995):
            for cap in (6, 12):
                a = judge(Dd, e, select(Dd, e, SC, THR, q, cap, mask & Dd["BOT"]), 0.45)
                b = judge(Dd, e, select(Dd, e, SC, THR, q, cap, mask & ~Dd["BOT"]), 0.50)
                print(fmt(f"E{e} q{q} cap{cap} {mexp}", a, b), flush=True)
