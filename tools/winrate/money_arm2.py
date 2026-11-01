"""the bot's ⚡ limits hour by hour with EVERY order (dlm_allorders.py: the filled and the never-filled ones): an order lives
4 bars of its chart; it goes on the exchange (holding its risk and a place) when an hour's candle comes within 1 ATR of it,
off again when an hour closes 1.6 ATR away; one limit / position a coin; positions + armed limits <= 20; the price reaching
it while it waits for room -> no trade; filled -> the trade (fill_walk's R / exit). The room rules: "A" the bot's (random
among the ones wanting it in an hour) / "Bn" the score over its stream's threshold first, an armed lower one taken off when
there is no room. P/R, SMC, EMA, HTF at the market as money_multi. A year from $100, 144 weekly windows, 5 seeds.
usage: money_arm2.py [rules] -> the table (+ <LABSTORE>/wf/money_arm2.json)"""
import sys, os, json, bisect, collections, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE, money_multi as M, money_expect as X, money_osc as O, money_params as MP
from multiprocessing import Pool
ARM, DISARM = 1.0, 1.6
RULES = sys.argv[1].split(",") if len(sys.argv) > 1 else ["A", "Bn"]; SEEDS = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "1,2,3").split(",")]
STEP = int(sys.argv[3]) if len(sys.argv) > 3 else 1   # every STEP-th window (a quick screen)
MF = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json")); SS = {s["name"]: s for s in MF["streams"]}
def orders(suf=None):
    out = []
    for st in ("wick4h", "close2h"):
        z0 = np.load(f"{M.ST}/wf/allorders_{st}{os.environ.get('ALLSUF', '') if suf is None else suf}.npz", allow_pickle=True); z = {k: z0[k] for k in z0.files}; bs = DE.STREAMS[st]["hh"] * 3600; sa, ha = SS[st]["stop_atr"], SS[st]["hard_stop_atr"]
        for k in range(len(z["t"])):
            lv, a = float(z["lv"][k]), float(z["atr"][k]); f = bool(z["filled"][k]); e = float(z["fill"][k]) if f else lv
            out.append({"coin": str(z["coin"][k]), "sym": M.bn(str(z["coin"][k])), "t": int(z["t"][k]), "until": int(z["t"][k]) + 4 * bs, "side": int(z["side"][k]),
                        "lv": lv, "atr": a, "prio": float(z["score"][k]) / float(z["thr"][k]), "filled": f, "t1h": int(z["t1h"][k]), "e": e,
                        "r": float(z["R"][k]), "t1": int(z["tout"][k]), "st": sa * a / e, "sth": ha * a / e, "stream": st, "mod": "dlm"})
    if os.environ.get("PLUSNEW") and suf is None:   # + the new coins' ⚡ orders (dlm_allorders.py with COINS=new, OUTSUF=_newc)
        out += orders("_newc")
    out.sort(key=lambda o: o["t"]); return out
EXITS = {}
def orders_exits(OR, take, soft, hard=3.0):
    """the same orders walked with other exits (dlm_engine.fill_walk on the 1h candles)"""
    out = []; by = {}
    for o in OR: by.setdefault((o["coin"], o["stream"]), []).append(o)
    for (c, st), xs in by.items():
        if c not in H1: H1[c] = DE.load1h(c)
        T1, O1, Hh, Ll, C1, V1 = H1[c]; p = DE.STREAMS[st]; bs = p["hh"] * 3600
        fl, t1h, fill, R, kind, tout = DE.fill_walk(T1, O1, Hh, Ll, C1, np.array([x["t"] for x in xs], np.int64), np.array([x["side"] for x in xs], np.int64),
                                                    np.array([x["lv"] for x in xs]), np.array([x["atr"] for x in xs]), bs, p["ch"], DE.ALIVE, DE.HOLD, take, soft, hard,
                                                    DE.FEE_IN, DE.FEE_TAKE, DE.FEE_OUT, DE.FUND)
        for k, x in enumerate(xs):
            f = bool(fl[k]); e = float(fill[k]) if f else x["lv"]
            out.append(dict(x, filled=f, t1h=int(t1h[k]), e=e, r=float(R[k]), t1=int(tout[k]), st=soft * x["atr"] / e, sth=hard * x["atr"] / e))
    out.sort(key=lambda o: o["t"]); return out
VOPEN = None
def virt_open():
    """the bot's virtual ⚡ trades open at each hour (dlm_load_mult counts them): the pool's trades (dlm_pool's rules)"""
    global VOPEN
    if VOPEN is None:
        P = json.load(open(f"{M.ST}/wf/pool_base.json")); ev = sorted([(x["t1h"] + 3600, 1) for x in P] + [(x["tout"], -1) for x in P])
        VOPEN = (np.array([e[0] for e in ev]), np.cumsum([e[1] for e in ev]))
    return VOPEN
H1 = {}
def bar(coin, h):
    if coin not in H1: H1[coin] = DE.load1h(coin)
    T, O_, H, L, C, V = H1[coin]; i = np.searchsorted(T, h)
    return (H[i], L[i], C[i]) if i < len(T) and T[i] == h else None
def run(OR, OT, A, B, rule, seed, cap=14.0, heat=0.95, rk=MP.rk(emx=3.0), eq0=100.0, maxpos=20):
    rng = np.random.default_rng(seed)
    kw = dict(x.split("=") for x in rule.split("|")[1:]); rule = rule.split("|")[0]   # "A|arm=0.5|hf=0.5|cnt=0"
    arm_d = float(kw.get("arm", ARM)); hf = float(kw.get("hf", 1.0)); cnt = kw.get("cnt", "1") == "1"
    if "dlm" in kw: rk = dict(rk, dlm=float(kw["dlm"]))
    if "k" in kw: rk = {m_: v_ * float(kw["k"]) for m_, v_ in rk.items()}   # every module's risk x k
    for m_ in ("prv", "smc", "emx", "htf"):
        if m_ in kw: rk = dict(rk, **{m_: float(kw[m_])})
    if rk["dlm"] <= 0: OR = []   # ⚡ off
    if "mp" in kw: maxpos = int(kw["mp"])
    if "cap" in kw: cap = float(kw["cap"])
    disarm = float(kw.get("dis", DISARM))
    minn = float(kw.get("minn", 0)); vload = kw.get("vload") == "1"
    # drawdown protection: "ddc=X/K/Y" — from X below the peak every risk x K until back within Y of it; "pz=D/X" — the
    # equity X below its level D days ago -> no new trades for D days
    ddc = tuple(float(x) for x in kw["ddc"].split("/")) if "ddc" in kw else None; cut_on = False
    pz = tuple(float(x) for x in kw["pz"].split("/")) if "pz" in kw else None; pause_to = 0; eqh = collections.deque()
    ld = tuple(float(x) for x in kw.get("ld", "0.625/1.25/5").split("/"))   # the load multiplier: below n x lo, else x hi
    WF = {"osc": O.W_OSC, "nocut": lambda v: O.W_OSC(v) / M.W2S(v), "w2s": M.W2S,
          "oldwt": lambda v: M.W2S(v) * ((1.25 if O.wt_x(v) <= -3 else (0.85 if O.wt_x(v) >= 22 else 1.0)) if v["mod"] == "dlm" else 1.0)}[kw.get("wf", "osc")]
    if "ex" in kw: OR = EXITS[kw["ex"]]
    if "pm" in kw: OR = [o for o in OR if o["prio"] >= float(kw["pm"])]   # a stricter threshold: the score >= pm x the year's
    if "life" in kw: OR = [dict(o, until=o["t"] + int((o["until"] - o["t"]) * float(kw["life"]) / 4)) for o in OR]   # the limit's life in bars (4)
    if "heat" in kw: heat = float(kw["heat"])
    oth = kw.get("oth") == "1"; ma = int(kw.get("ma", 999))   # the other modules take an armed ⚡ limit's room; at most `ma` armed ⚡ limits
    # the open risk a side: "sh=X" — the longs' (the shorts') losses at their stops <= X of the equity; "net=X" — the one side's
    # minus the other's <= X (the alts fall with BTC together: the drawdown is the side's, not the total's)
    sh = float(kw.get("sh", 0)); net = float(kw.get("net", 0))
    nomg = kw.get("nomg") == "1"
    cash = eq0; pos = []; armed = {}; peak = eq0; mdd = 0.0; done = set(); n_fill = n_skip = 0
    OR = [o for o in OR if A - 64 * 3600 <= o["t"] < B]; io = 0; act = []
    OT = sorted(OT, key=lambda v: v["t0"]); jo = bisect.bisect_left([v["t0"] for v in OT], A)
    def rd_of(v, eq):
        r = rk[v["mod"]] / 100 * (ddc[1] if cut_on else 1.0)
        if v["mod"] == "dlm":
            if vload:
                T_, N_ = virt_open(); j_ = np.searchsorted(T_, v.get("t0") or v["t"] + 3600, side="right") - 1; n_ = int(N_[j_]) if j_ >= 0 else 0
            else:
                n_ = sum(1 for o in pos if o["mod"] == "dlm") + len(armed)
            r *= ld[0] if n_ < ld[2] else ld[1]
            v = dict(v, t0=v.get("t0") or v["t"] + 3600)
        return eq * r * WF(v)
    def used(): return sum(o["heat"] for o in pos) + hf * sum(o["heat"] for o in armed.values())
    def sused(s): return sum(o["heat"] for o in pos if o["side"] == s) + hf * sum(a["heat"] for a in armed.values() if a["o"]["side"] == s)
    def fit(v, eq, extra=0.0):
        rd = rd_of(v, eq); hn = rd * v["sth"] / v["st"]; room = heat * eq - used() + extra
        if sh: room = min(room, sh * eq - sused(v["side"]) + extra)
        if net: room = min(room, net * eq - (sused(v["side"]) - sused(-v["side"])) + extra)
        if hn > room:
            if room < hn * 0.1: return None, hn, room
            rd *= room / hn
        notional = rd / v["st"]
        if notional < minn: return None, hn, room   # under Binance's minimum order: not opened
        mg = notional / M.lev_real(v["sym"], notional, cap); free = eq - sum(o["mg"] for o in pos) - sum(o["mg"] for o in armed.values())
        if nomg: mg = 0.0   # "nomg=1": the margin never short (what the free margin costs)
        if mg > 0.9 * free:
            if free <= 1: return None, hn, room
            q = 0.9 * free / mg; rd *= q; notional *= q; mg *= q
            if notional < minn: return None, hn, room
        return {"rd": rd, "heat": rd * v["sth"] / v["st"], "mg": mg, "notional": notional}, hn, room
    for h in range(A, B, 3600):
        for o in [o for o in pos if o["t1"] <= h]:
            cash += o["rd"] * o["r"]; pos.remove(o)
        upnl = 0.0
        for o in pos:
            p = M.px_at(o["sym"], h)
            if p: upnl += o["side"] * (p - o["e"]) / o["e"] * o["notional"]
        eq = cash + upnl
        if eq <= 0: return 0.0, 1.0, n_fill, n_skip
        peak = max(peak, eq); mdd = max(mdd, 1 - eq / peak)
        if ddc:
            if not cut_on and eq < peak * (1 - ddc[0]): cut_on = True
            elif cut_on and eq >= peak * (1 - ddc[2]): cut_on = False
        if pz:
            eqh.append((h, eq))
            while eqh and eqh[0][0] < h - pz[0] * 86400: eqh.popleft()
            if eq < eqh[0][1] * (1 - pz[1]): pause_to = h + int(pz[0] * 86400)
        paused = h < pause_to
        while jo < len(OT) and OT[jo]["t0"] <= h:   # the other modules at the market
            v = OT[jo]; jo += 1
            if paused or v["t0"] < h - 3600 or any(o["sym"] == v["sym"] for o in pos) or any(a["sym"] == v["sym"] for a in armed.values()): continue
            s_, hn, room = fit(v, eq)
            if oth and armed and (s_ is None or s_["rd"] < rd_of(v, eq) * 0.999):   # no room: the armed ⚡ limits (the lowest priority first) make way
                freed = 0.0
                for k2, a in sorted(armed.items(), key=lambda x: x[1]["o"]["prio"]):
                    if room + freed >= hn: break
                    if (sh or net) and a["o"]["side"] != v["side"]: continue   # the other side's limit frees nothing of this side
                    del armed[k2]; freed += hf * a["heat"]
                s_, hn, room = fit(v, eq)
            if s_: pos.append(dict(v, **s_))
        while io < len(OR) and OR[io]["t"] <= h:
            act.append(OR[io]); io += 1
        act = [o for o in act if o["until"] > h and id(o) not in done]
        for k_ in [k_ for k_, a in armed.items() if a["o"]["until"] <= h]: del armed[k_]   # expired: off
        want = []
        for o in act:
            b = bar(o["coin"], h)
            if b is None: continue
            hi, lo, cl = b; s = o["side"]
            near = ((lo - o["lv"]) if s > 0 else (o["lv"] - hi)) / o["atr"] <= arm_d
            touch = (lo <= o["lv"]) if s > 0 else (hi >= o["lv"])
            far = s * (cl - o["lv"]) / o["atr"] > disarm
            k_ = id(o)
            if k_ in armed:
                if touch:   # filled: the trade
                    a = armed.pop(k_); done.add(k_)
                    if o["filled"] and o["t1h"] == h: pos.append(dict(o, **{x: a[x] for x in ("rd", "heat", "mg", "notional")})); n_fill += 1
                elif far: del armed[k_]
            elif near:
                want.append((o, touch, s * (cl - o["lv"]) / o["atr"], cl))
        order = sorted(want, key=lambda w: -w[0]["prio"]) if rule in ("Bn", "Bq") else [want[i] for i in rng.permutation(len(want))]
        if rule in ("A", "Ac"): order.sort(key=lambda w: w[2])   # the bot arms the nearest first (random among the same distance)
        for o, touch, d_o, cl in ([] if paused else order):
            k_ = id(o)
            if k_ in done or k_ in armed: continue
            busy = any(p_["sym"] == o["sym"] for p_ in pos)
            if not busy:   # the bot: one limit a coin on the exchange — the nearer one (DLM_SWAP_ATR 0.25): a farther armed one comes off
                for k2, a in [(k2, a) for k2, a in armed.items() if a["o"]["sym"] == o["sym"]]:
                    ao = a["o"]
                    if touch or ao["side"] * (cl - ao["lv"]) / ao["atr"] > d_o + 0.25: del armed[k2]
                    else: busy = True
            nd = sum(1 for p_ in pos if p_["mod"] == "dlm") + (len(armed) if cnt else 0)
            s_, hn, room = (None, 0, 0) if busy or nd >= maxpos else fit(o, eq)
            if rule == "Ac" and s_ and s_["rd"] < rd_of(o, eq) * 0.999: s_ = None   # no scaled-down crumbs
            if rule == "Bn" and not busy and (s_ is None or s_["rd"] < rd_of(o, eq) * 0.999 or nd >= maxpos):
                low = sorted([(k2, a) for k2, a in armed.items() if a["o"]["prio"] < o["prio"] and not ((sh or net) and a["o"]["side"] != o["side"])], key=lambda x: x[1]["o"]["prio"])
                freed = 0.0; n2 = nd
                for k2, a in low:
                    if n2 < maxpos and room + freed >= hn and hn > 0: break
                    del armed[k2]; freed += hf * a["heat"]; n2 -= cnt
                if freed or n2 < nd:
                    nd = n2; s_, hn, room = fit(o, eq) if nd < maxpos else (None, 0, 0)
            if s_ and not touch and len(armed) >= ma: s_ = None   # the armed limits' own cap
            if s_ and nd < maxpos:
                if touch:   # reached this hour: filled at once
                    done.add(k_)
                    if o["filled"] and o["t1h"] == h: pos.append(dict(o, **s_)); n_fill += 1
                else:
                    armed[k_] = dict(s_, o=o, sym=o["sym"])
            elif touch:
                done.add(k_); n_skip += o["filled"] and o["t1h"] == h
    upnl = 0.0
    for o in pos:
        p = M.px_at(o["sym"], B)
        if p: upnl += o["side"] * (p - o["e"]) / o["e"] * o["notional"]
    return cash + upnl, mdd, n_fill, n_skip
_D = {}
def _init(D): _D.update(D)
def job(a):
    rule, sd, A = a
    if "ex=" in rule and not EXITS:
        EXITS["old"] = orders_exits(_D["or"], 1.1, 2.0)
    return rule, sd, A, run(_D["or"], _D["ot"], A, A + 365 * 86400, rule, sd)
if __name__ == "__main__":
    D = {"or": orders(), "ot": [v for v in M.build("base") if v["mod"] != "dlm"]}
    print("⚡ orders", len(D["or"]), "filled", sum(o["filled"] for o in D["or"]), flush=True)
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, [(r, sd, A) for r in RULES for sd in SEEDS for A in X.STARTS[::STEP] + [X.LAST]], chunksize=6)
    R = {}
    for r, sd, A, v in res: R.setdefault((r, sd), {})[A] = v
    out = {}
    for r in RULES:
        E = [np.array([R[(r, sd)][A][0] for A in X.STARTS[::STEP]]) for sd in SEEDS]; b = [np.array([R[(RULES[0], sd)][A][0] for A in X.STARTS[::STEP]]) for sd in SEEDS]
        o = {"p10": float(np.mean([np.percentile(e, 10) for e in E])), "p50": float(np.mean([np.median(e) for e in E])), "p90": float(np.mean([np.percentile(e, 90) for e in E])),
             "dd": float(np.mean([np.median([R[(r, sd)][A][1] for A in X.STARTS[::STEP]]) for sd in SEEDS]) * 100), "last12": float(np.mean([R[(r, sd)][X.LAST][0] for sd in SEEDS])),
             "fills": float(np.mean([np.mean([R[(r, sd)][A][2] for A in X.STARTS[::STEP]]) for sd in SEEDS])), "skips": float(np.mean([np.mean([R[(r, sd)][A][3] for A in X.STARTS[::STEP]]) for sd in SEEDS])),
             "better": float(np.mean([(e > bb * 1.001).sum() for e, bb in zip(E, b)]))}
        out[r] = o
        print(f"{r:22s} плохой ${o['p10']:>7,.0f} обычный ${o['p50']:>7,.0f} хороший ${o['p90']:>9,.0f} просадка {o['dd']:.0f}% посл.12 ${o['last12']:>8,.0f} | сделок ⚡ за год {o['fills']:.0f}, пропущено {o['skips']:.0f} | лучше {RULES[0]} в {o['better']:.0f}/{len(X.STARTS[::STEP])}", flush=True)
    json.dump(out, open(f"{M.ST}/wf/money_arm2.json", "w"), indent=1)
