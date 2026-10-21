"""usage: ev_grid.py DIR ENGINE_MODULE EXITS "mask;mask" [q-list] [cap-list]"""
import sys, importlib, numpy as np
ARGS = sys.argv[1:]
import warnings; warnings.filterwarnings("ignore")
from lv_wf import *
dr, modn = ARGS[0], ARGS[1]
FN = importlib.import_module(modn).FNAMES
Dd = load_dir(dr, FN)
env = {nm: Dd["F"][:, k] for k, nm in enumerate(FN)}
QS = tuple(map(float, ARGS[4].split(","))) if len(ARGS) > 4 else (0.95, 0.98, 0.99)
CAPS = tuple(map(int, ARGS[5].split(","))) if len(ARGS) > 5 else (6, 12)
for e in map(int, ARGS[2].split(",")):
    for mexp in ARGS[3].split(";"):
        mask = eval(mexp, {"np": np}, env) if mexp else np.ones(len(Dd["T"]), bool)
        SC, THR = scores(Dd, e, mask=mask)
        for q in QS:
            for cap in CAPS:
                a = judge(Dd, e, select(Dd, e, SC, THR, q, cap, mask & Dd["BOT"]), 0.45)
                b = judge(Dd, e, select(Dd, e, SC, THR, q, cap, mask & ~Dd["BOT"]), 0.50)
                print(fmt(f"{dr} E{e} q{q} cap{cap} {mexp}", a, b), flush=True)
