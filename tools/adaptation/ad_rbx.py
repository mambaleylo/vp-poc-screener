"""📈 range breakout trades (the bot's rule, cap 6 per side, strongest first) -> ad/rbx_<tf>.json for ad_gate.py"""
import glob, pickle, json, os, numpy as np, importlib
from mk import ts
from common import D
for TFH, N0, K0 in ((24, 20, 2.5), (12, 30, 4.0)):
    os.environ["TFH"] = str(TFH)
    import rb_tf; importlib.reload(rb_tf)
    ev = []
    for k, fn in enumerate(sorted(glob.glob(f"{D}/rbtf{TFH}/*.pkl"))):
        for t, s, f, x, y in pickle.load(open(fn, "rb")):
            if f["N"] == N0 and f["rg"] < K0 and f["own200"]:
                ev.append((t, k, s, f["brk"], y))
    si, xi = rb_tf.STOPS.index(1.5), rb_tf.EXITS.index("dc20")
    ev.sort(key=lambda e: (e[0], -e[3]))
    busy, act, out = {}, [], []
    for t, k, s, brk, y in ev:
        r, j = float(y[si, xi, 0]), y[si, xi, 1]
        if r != r or t < ts(2021):
            continue
        if busy.get((k, s), 0) > t:
            continue
        act = [a for a in act if a[0] > t]
        if sum(1 for a in act if a[1] == s) >= 6:
            continue
        end = int(t + int(j) * TFH * 3600); busy[(k, s)] = end; act.append((end, s))
        out.append((int(t), end, r, k, int(s)))
    json.dump({"summary": {}, "trades": out}, open(f"{D}/ad/rbx_{TFH}.json", "w"))
    print(TFH, len(out), round(np.mean([o[2] for o in out]), 3))
