import os; os.environ["TFH"] = "4"
import numpy as np, warnings; warnings.filterwarnings("ignore")
exec(open("s25_money.py").read().split("roll = ")[0])
from s15_wf import report, fmt
za = np.load("s25_sc_4h_w1_0_A_base.npz", allow_pickle=True); zb = np.load("s25_sc_4h_w1_0_A_0-1-2-5-8.npz", allow_pickle=True)
ta, tb_ = za["THR"].item(), zb["THR"].item()
SC = (za["SC"] + zb["SC"]) / 2; THR = {Y: (ta[Y] + tb_[Y]) / 2 for Y in ta}
n0 = int((~D["new"]).sum())
np.savez("s25_mix_127.npz", SC=SC[:n0], THR=np.array({Y: v for Y, v in THR.items()}, dtype=object))   # the 127 part (THR = train coins = 127 only)
for q in (0.985, 0.99):
    for nm, sub in (("пров42", D["chk"]), ("новые83", D["new"] & ~D["usdc"]), ("обуч85", ~D["chk"] & ~D["new"])):
        print(f"mix q{q} {nm:8s}: {fmt(report(D, 0, select(D, 0, SC, THR, q, 20, sub)))}")
