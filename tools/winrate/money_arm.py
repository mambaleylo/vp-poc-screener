"""the bot's arming in the money sim: a ⚡ limit goes on the exchange (and holds its risk in the open-risk cap) once the
price is within DLM_ARM_ATR (1 ATR) of it — before it fills; positions + armed limits <= 20, one per coin; a limit the price
reaches while it waits for room is no trade. Two rules for the room: "A" the bot's (the first come — the order the
price nears them, random inside an hour) and "B" the score's priority (no room -> an armed, not filled limit of a lower
score comes off for a higher one; the waiting ones armed by score). Only the pool's filled orders are known (the ones
that never filled would hold room too — in both rules). The bundle's money as money_expect2.py.
usage: money_arm.py -> the table"""
import sys, os, bisect, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_exits as DX, dlm_engine as DE, money_multi as M, money_expect as X, money_osc as O, money_params as MP, money_order as MOR
from multiprocessing import Pool
ARM = 1.0; SEEDS = [1, 2, 3, 4, 5]
def arm_time(x):
    T1, O1, H1, L1, C1, V1 = DX.H1.get(x["coin"]) or DX.H1.setdefault(x["coin"], DE.load1h(x["coin"]))
    i = np.searchsorted(T1, x["t0"]); j = np.searchsorted(T1, x["t1h"])
    s, lv, a = x["side"], x["lv"], x["atr"]
    for k in range(i, j + 1):
        if (L1[k] <= lv + ARM * a) if s > 0 else (H1[k] >= lv - ARM * a): return int(T1[k])
    return int(x["t1h"])
THR = {}
def _thr(st, t):
    if st not in THR:
        z = np.load(f"{M.ST}/wf/scores_{st}.npz", allow_pickle=True); y = z["t"].astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970
        THR[st] = {int(v): float(z["thr"][y == v][0]) for v in np.unique(y)}
    return THR[st][int(np.datetime64(t, "s").astype("datetime64[Y]").astype(int) + 1970)]
def dlm_events(Pw):
    rr = np.random.default_rng(99)
    return [{"rel": x["score"] / _thr(x["st"], x["t0"]), "rnd": float(rr.random()), "stw": (1.0 if x["st"] == "wick4h" else 0.0) + float(rr.random()) * 0.5, "ta": arm_time(x), "tf": x["t1h"], "t0": x["t1h"] + 3600, "t1": x["tout"], "r": x["R"], "st": abs(x["fill"] - x["sl"]) / x["fill"],
             "sth": abs(x["fill"] - x["hsl"]) / x["fill"], "mod": "dlm", "sym": M.bn(x["coin"]), "side": x["side"], "e": x["fill"], "stream": x["st"],
             "score": x["score"]} for x in Pw]
def run_arm(DL, OT, A, B, policy, seed, cap=14.0, wf=O.W_OSC, heat=0.95, rk_=MP.rk(emx=3.0), eq0=100.0, maxpos=20):
    rng = np.random.default_rng(seed)
    pk = {"B": "score", "B1": "score", "Bn": "rel", "Br": "rnd", "Bs": "stw"}.get(policy)
    bumps = policy in ("B", "Bn", "Br", "Bs")
    cash = eq0; pos = []; armed = []; wait = []; skip = 0; peak = eq0; mdd = 0.0
    DL = sorted([d for d in DL if A - 32 * 7200 <= d["tf"] < B], key=lambda d: d["ta"]); ia = 0
    OT = sorted(OT, key=lambda v: v["t0"]); io = bisect.bisect_left([v["t0"] for v in OT], A)
    def size(v, eq, extra=0.0):
        rk = rk_[v["mod"]] / 100
        if v["mod"] == "dlm":
            n = sum(1 for o in pos + armed if o["mod"] == "dlm")
            rk *= 0.625 if n < 5 else 1.25
        rk *= wf(v)
        rd = eq * rk; hn = rd * v["sth"] / v["st"]; room = heat * eq - sum(o["heat"] for o in pos + armed) + extra
        return rd, hn, room
    def take(v, eq, rd, hn, room):
        if hn > room:
            if room < hn * 0.1: return None
            rd *= room / hn
        notional = rd / v["st"]; mg = notional / M.lev_real(v["sym"], notional, cap); free = eq - sum(o["mg"] for o in pos + armed)
        if mg > 0.9 * free:
            if free <= 1: return None
            k = 0.9 * free / mg; rd *= k; notional *= k; mg *= k
        return dict(v, rd=rd, heat=rd * v["sth"] / v["st"], mg=mg, notional=notional)
    for h in range(A, B, 3600):
        for o in [o for o in pos if o["t1"] <= h]:
            cash += o["rd"] * o["r"]; pos.remove(o)
        upnl = 0.0
        for o in pos:
            p = M.px_at(o["sym"], h)
            if p: upnl += o["side"] * (p - o["e"]) / o["e"] * o["notional"]
        eq = cash + upnl
        if eq <= 0: return 0.0, skip, 1.0
        peak = max(peak, eq); mdd = max(mdd, 1 - eq / peak)
        for o in [o for o in armed if o["t0"] <= h]:   # the armed limit filled in the hour before: a position
            armed.remove(o); pos.append(o)
        for o in [o for o in wait if o["t0"] <= h]:   # reached while waiting for room: no trade
            wait.remove(o); skip += 1
        while io < len(OT) and OT[io]["t0"] <= h:   # P/R, SMC, EMA, HTF at the market on the touch
            v = OT[io]; io += 1
            if v["t0"] < h - 3600 or any(o["sym"] == v["sym"] for o in pos + armed): continue
            rd, hn, room = size(v, eq); t = take(v, eq, rd, hn, room)
            if t: pos.append(t)
        while ia < len(DL) and DL[ia]["ta"] <= h:   # the price came within 1 ATR: wants to go on the exchange
            if DL[ia]["t0"] > h: wait.append(DL[ia])
            ia += 1
        order = sorted(wait, key=lambda v: -v[pk]) if pk else [wait[i] for i in rng.permutation(len(wait))]
        for v in order:
            if any(o["sym"] == v["sym"] for o in pos + armed): continue
            if sum(1 for o in pos + armed if o["mod"] == "dlm") >= maxpos and not (bumps and any(o[pk] < v[pk] for o in armed)): continue
            rd, hn, room = size(v, eq); t = take(v, eq, rd, hn, room)
            if (t is None or t["rd"] < rd * 0.999 or sum(1 for o in pos + armed if o["mod"] == "dlm") >= maxpos) and bumps:
                low = sorted([o for o in armed if o[pk] < v[pk]], key=lambda o: o[pk])
                freed = 0.0; bump = []
                for o in low:
                    if room + freed >= hn and sum(1 for q in pos + armed if q["mod"] == "dlm") - len(bump) < maxpos: break
                    bump.append(o); freed += o["heat"]
                if bump:
                    for o in bump: armed.remove(o); wait.append({k: o[k] for k in v.keys()})
                    rd, hn, room = size(v, eq); t = take(v, eq, rd, hn, room)
            if t and sum(1 for o in pos + armed if o["mod"] == "dlm") < maxpos:
                wait.remove(v); armed.append(t)
    upnl = 0.0
    for o in pos:
        p = M.px_at(o["sym"], B)
        if p: upnl += o["side"] * (p - o["e"]) / o["e"] * o["notional"]
    return cash + upnl, skip, mdd
_D = {}
def _init(D): _D.update(D)
def job(a):
    pol, sd, A = a
    if pol == "lab":
        return pol, sd, A, M.run(_D["ev"][sd], A, A + 365 * 86400, 14.0, O.W_OSC, eq0=100.0, heat=0.95, rk_=MP.rk(emx=3.0))[::3]
    return pol, sd, A, run_arm(_D["dl"], _D["ot"], A, A + 365 * 86400, pol, sd)
POLS = sys.argv[1].split(",") if len(sys.argv) > 1 else ["lab", "A", "B"]
if __name__ == "__main__":
    st0 = DX.json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json"))["streams"][0]
    Pw = DX.walk(DX.pool_lv(), take=st0["take_atr"], soft=st0["stop_atr"], hard=st0["hard_stop_atr"])
    D = {"dl": dlm_events(Pw), "ot": [v for v in M.build("base") if v["mod"] != "dlm"], "ev": {sd: MOR.events(Pw, sd) for sd in SEEDS}}
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(pol, sd, A) for pol in POLS for sd in SEEDS for A in X.STARTS], chunksize=12)
    R = {}
    for pol, sd, A, r in res: R.setdefault((pol, sd), {})[A] = r
    nm = {"lab": "лаба без выставления заранее", "A": "А: как сейчас (первый пришёл)", "B": "Б: приоритет по оценке", "B1": "Б без снятия (только очередь)",
          "Bn": "Б по оценке/порог потока", "Br": "снятие по случайному приоритету", "Bs": "снятие: 4ч-поток важнее"}
    for pol in POLS:
        E = [np.array([R[(pol, sd)][A][0] for A in X.STARTS]) for sd in SEEDS]
        dd = np.mean([np.median([R[(pol, sd)][A][-1] for A in X.STARTS]) for sd in SEEDS]) * 100
        bA = [np.array([R[("A", sd)][A][0] for A in X.STARTS]) for sd in SEEDS]
        print(f"{nm[pol]:32s} плохой ${np.mean([np.percentile(e, 10) for e in E]):>7,.0f} обычный ${np.mean([np.median(e) for e in E]):>7,.0f} "
              f"хороший ${np.mean([np.percentile(e, 90) for e in E]):>8,.0f} просадка {dd:.0f}% | лучше А в {np.mean([(e > b * 1.001).sum() for e, b in zip(E, bA)]):.0f}/144", flush=True)
