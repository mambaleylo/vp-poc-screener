"""⚡ labels for the model file's exits (the models learnt R of the 2 / 1.1 ATR exits; the bot trades 1.75 / 1.2 since
v0.99.750): every filled order of <LABSTORE>/feat/<stream>/<coin>.npz re-walked on the 1h candles with the exits given
(dlm_engine.fill_walk; the fill is the same — the level and the life), R / kind / tout replaced.
-> <LABSTORE>/feat_<tag>/<stream>/<coin>.npz. usage: dlm_relabel.py TAG TAKE SOFT [HARD]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store")
TAG, TAKE, SOFT = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]); HARD = float(sys.argv[4]) if len(sys.argv) > 4 else 3.0
C = json.load(open(f"{ST}/feat_coins.json"))
for st in ("wick4h", "close2h"):
    os.makedirs(f"{ST}/feat_{TAG}/{st}", exist_ok=True); p = DE.STREAMS[st]; bs = p["hh"] * 3600; n = 0
    for c in C["base"] + C["new"]:
        fo = f"{ST}/feat_{TAG}/{st}/{c}.npz"
        if os.path.exists(fo): continue
        z0 = np.load(f"{ST}/feat/{st}/{c}.npz"); z = {k: z0[k] for k in z0.files}
        if len(z["t"]):
            T1, O1, H1, L1, C1, V1 = DE.load1h(c)
            fl, t1h, fill, R, kind, tout = DE.fill_walk(T1, O1, H1, L1, C1, z["t"].astype(np.int64), z["side"].astype(np.int64), z["lv"], z["atr"], bs, p["ch"],
                                                        DE.ALIVE, DE.HOLD, TAKE, SOFT, HARD, DE.FEE_IN, DE.FEE_TAKE, DE.FEE_OUT, DE.FUND)
            keep = fl
            z = {k: (v[keep] if hasattr(v, "__len__") and len(v) == len(fl) else v) for k, v in z.items()}
            z.update(R=R[keep].astype(np.float32), kind=kind[keep].astype(np.int8), tout=tout[keep], t1h=t1h[keep], fill=fill[keep])
        np.savez_compressed(fo + ".tmp.npz", **z); os.replace(fo + ".tmp.npz", fo); n += 1
    print(st, "relabelled", n, flush=True)
print("relabel done", flush=True)
