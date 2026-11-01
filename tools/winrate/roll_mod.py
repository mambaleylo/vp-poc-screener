"""the retrain schedule on every module (the user: "проверь, не лучше ли плавающее годовое окно обучения для каждого
последующего месяца… полностью на всех индикаторах"): each module's verified recipe (its *_repro.py / export), its events and
label, retrained by VAR — Y: all history once a year, Q: all history every 3 months, M0: all history every month, M12 / M24:
the last 12 / 24 months every month, Q24: the last 24 months every 3 months (P/R's way now) — the out-of-sample scores
2022-01 .. 2026-09 -> roll_<MOD>_<VAR>.npz (SC; INS = the first period's model on the year before, for its threshold).
usage: roll_mod.py MOD VAR   (MOD: ema, cfl, smc, htf, prv, rbs)"""
import sys; AV = list(sys.argv)
import os, glob, json, re, calendar, numpy as np, lightgbm as lgb, warnings; warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.join(HERE, "..", "..")
sys.path.insert(0, HERE); sys.path.insert(1, os.path.join(HERE, "..", "new_ind")); sys.path += [os.path.join(HERE, "..", "zones_model"), os.path.join(HERE, "..", "neuro_model")]
import types; sys.modules.setdefault("nx_h", types.SimpleNamespace(pain=None))
ST = os.environ.get("LABSTORE", "/home/user/vp-lab-store"); ts = lambda y, m=1, d=1: calendar.timegm((y, m, d, 0, 0, 0))
END = ts(2026, 10)


def data(mod):
    """-> dict T, X, y (the training label), R (the judged R), groups [(name, train mask, eval mask, threshold universe mask)],
    unseen (mask of the coins never trained on, or None), q (or thr), gap (days), pr (LightGBM params)"""
    if mod == "ema":
        import pandas as pd
        D_ = os.path.join(HERE, "..", "ema_model"); m0 = json.load(open(os.path.join(REPO, "vp_ema_model.json"))); LAB = m0["lab"]
        d = pd.read_parquet(f"{D_}/er_all.parquet", columns=["t", "side", "tf_s"] + [c for c in m0["feats"] if c != "side"] + [LAB])
        pen = pd.read_parquet(f"{D_}/er_pen.parquet").pen.values
        T = d.t.values.astype(np.int64); X = d[m0["feats"]].values.astype(np.float32); r = d[LAB].values
        ev = (d.side.values > 0) & (d.tf_s.values != "4h") & (pen >= 0.1) & np.isfinite(r)
        allm = np.ones(len(T), bool)
        return dict(T=T, X=X, y=np.nan_to_num(r, nan=0.0).clip(-1.5, 5.0), R=r, groups=[("все", allm, ev, allm)], unseen=None, q=0.96, gap=4,
                    pr=dict(n_estimators=500, learning_rate=0.02, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1, colsample_bytree=0.6, reg_lambda=5.0, verbose=-1, n_jobs=4))
    pr_lv = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=300, subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1, n_jobs=4)
    if mod == "cfl":
        sys.argv = ["x"]
        from lv_wf import load_dir
        import ev3_engine as E3, ev2_engine as E2
        Dd = load_dir("ev3", E3.FNAMES); T, SIDE, BOT, F = Dd["T"], Dd["SIDE"], Dd["BOT"], Dd["F"]
        m0 = json.load(open(os.path.join(REPO, "vp_cfl_model.json"))); F[:, [E2.FNAMES.index(c) for c in m0["zero"]]] = 0.0
        RF = np.load("fc_RF.npz")["RF"]; M = T >= ts(2021)
        return dict(T=T, X=F, y=np.nan_to_num(RF, nan=0.0).clip(-1.2, 6.0), R=RF, groups=[("лонги против медвежьих", M & BOT, M & (SIDE < 0) & np.isfinite(RF), M & BOT)],
                    unseen=~BOT, q=0.997, gap=14, pr=pr_lv)
    if mod in ("smc", "htf"):
        from lv_wf import load_dir
        import lv_engine as LE
        Dd = load_dir("lv2", LE.FNAMES); F = Dd["F"]; fam = F[:, 0].astype(int); T, SIDE, BOT = Dd["T"], Dd["SIDE"], Dd["BOT"]
        if mod == "smc":
            r = Dd["R"][2]; S = fam >= 33
            return dict(T=T, X=F, y=np.nan_to_num(r, nan=0.0).clip(-1.2, 6.0), R=r, groups=[("касания SMC", S & BOT, S & np.isfinite(r), S & BOT)], unseen=~BOT, q=0.993, gap=14, pr=pr_lv)
        import htf_repro_rl as HR   # the long HTF touches' traded exit (htf_repro.py's RL), cached
        RL = HR.rl(Dd, T, SIDE, fam)
        L_ = (fam <= 22) & (SIDE > 0) & (T >= ts(2019)) & np.isfinite(RL)
        return dict(T=T, X=F, y=np.nan_to_num(RL, nan=0.0).clip(-1.2, 6.0), R=RL, groups=[("длинные касания HTF", L_ & BOT, L_, L_ & BOT)], unseen=~BOT, q=0.995, gap=14, pr=pr_lv)
    if mod == "prv":
        sys.path.insert(0, os.path.join(HERE, "..", "prv_audit"))
        from prv_ev import STOPS, TAKES
        src = open(os.path.join(REPO, "vp_poc_screener.py")).read()
        C127 = re.search(r'RESEARCH_COINS_127 = tuple\("""(.*?)"""', src, re.S).group(1).split()
        syms = sorted({x for c in C127 for x in (c.replace("_USDT", "") + "USDT", "1000" + c.replace("_USDT", "") + "USDT") if os.path.exists(f"{ST}/prv_ev/{x}.npz")})
        Xs, Ys, Ts = [], [], []
        for s in syms:
            z = np.load(f"{ST}/prv_ev/{s}.npz")
            if len(z["t"]): Xs.append(z["X"]); Ys.append(z["Y"]); Ts.append(z["t"])
        X = np.concatenate(Xs); Y = np.concatenate(Ys); T = np.concatenate(Ts).astype(np.int64)
        Y = np.where(np.abs(Y) > 20, np.nan, Y); lab = Y[:, STOPS.index(1.5), TAKES.index(3.0)]; SD = X[:, 1].astype(int); ok = np.isfinite(lab)
        return dict(T=T, X=X.astype(np.float32), y=np.nan_to_num(lab, nan=0.0).clip(-1.5, 4.0), R=lab, unseen=None, q=0.99, gap=10,
                    groups=[("лонги", (SD == 1) & ok, (SD == 1) & ok, SD == 1), ("шорты", (SD == -1) & ok, (SD == -1) & ok, SD == -1)],
                    pr=dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=1000, subsample=0.7, subsample_freq=1, colsample_bytree=0.5, reg_lambda=10.0, verbose=-1, n_jobs=4))
    if mod == "rbs":
        import rbs_ml as ML
        z = dict(np.load(f"{ST}/wf/rbs_4.npz")); X = np.load(f"{ST}/wf/rbs_4_X.npz")["X"]
        r = z["y"][:, ML.STOPS.index(1.5), ML.EXITS.index("t2"), ML.HOLDS.index(2), 0]; ok = np.isfinite(r)
        return dict(T=z["t"].astype(np.int64), X=X, y=np.nan_to_num(r).clip(-1.5, 4.0), R=r, groups=[("пробои 4ч", ok, ok, ok)], unseen=None, thr=0.8, gap=2,
                    pr=dict(ML.P, num_threads=4))
    raise SystemExit(f"unknown {mod}")


def periods(var):
    step = {"Y": 12, "Q": 3, "Q24": 3}.get(var, 1); out = []; yy, mm = 2022, 1
    while ts(yy, mm) < END:
        a = ts(yy, mm); k = mm - 1 + step; yy2, mm2 = yy + k // 12, k % 12 + 1; out.append((a, min(ts(yy2, mm2), END))); yy, mm = yy2, mm2
    return out


if __name__ == "__main__":
    MOD, VAR = AV[1], AV[2]
    W = {"M12": 12, "M24": 24, "Q24": 24}.get(VAR, 0)
    d = data(MOD); T, X, y = d["T"], d["X"], d["y"]
    SC = np.full(len(T), np.nan); INS = np.full(len(T), np.nan)
    for gname, trm, evm, thm in d["groups"]:
        for k, (a, b) in enumerate(periods(VAR)):
            cut = a - d["gap"] * 86400
            tr = trm & (T < cut)
            if W: tr &= T >= cut - W * 30.4 * 86400
            tr = np.flatnonzero(tr)
            te = np.flatnonzero((evm | thm) & (T >= a) & (T < b))
            if len(tr) < 5000 or not len(te): continue
            m = lgb.LGBMRegressor(random_state=0, **d["pr"]).fit(X[tr], y[tr])
            SC[te] = m.predict(X[te])
            if k == 0:
                ref = np.flatnonzero(thm & (T >= a - 365 * 86400) & (T < a)); INS[ref] = m.predict(X[ref])
            print(f"{MOD} {VAR} {gname} {np.datetime64(a, 's')}: обучено на {len(tr)}", flush=True)
    np.savez(f"roll_{MOD}_{VAR}.npz", SC=SC, INS=INS)
    print("roll mod done", MOD, VAR, flush=True)
