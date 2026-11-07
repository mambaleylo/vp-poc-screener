"""the bot's ⚡ limits hour by hour with EVERY order (dlm_allorders.py: the filled and the never-filled ones): an order lives
4 bars of its chart; it goes on the exchange (holding its risk and a place) when an hour's candle comes within 1 ATR of it,
off again when an hour closes 1.6 ATR away; one limit / position a coin; positions + armed limits <= 20; the price reaching
it while it waits for room -> no trade; filled -> the trade (fill_walk's R / exit). The room rules: "A" the bot's (random
among the ones wanting it in an hour) / "Bn" the score over its stream's threshold first, an armed lower one taken off when
there is no room. P/R, SMC, EMA, HTF at the market as money_multi. A year from $100, 144 weekly windows, 5 seeds.
usage: money_arm2.py [rules] -> the table (+ <LABSTORE>/wf/money_arm2.json)"""
import sys, os, json, bisect, collections, itertools, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dlm_engine as DE, money_multi as M, money_expect as X, money_osc as O, money_params as MP
from multiprocessing import Pool
ARM, DISARM = 1.0, 1.6
RULES = sys.argv[1].split(",") if len(sys.argv) > 1 else ["A", "Bn"]; SEEDS = [int(x) for x in (sys.argv[2] if len(sys.argv) > 2 else "1,2,3").split(",")]
STEP = int(sys.argv[3]) if len(sys.argv) > 3 else 1   # every STEP-th window (a quick screen)
MF = json.load(open("/home/user/vp-poc-screener/vp_dlm_model.json")); SS = {s["name"]: s for s in MF["streams"]}
def stream_orders(st, suf=""):
    """one stream's orders (<LABSTORE>/wf/allorders_<st><suf>.npz) as the money's dicts; a new chart (not in the model file)
    with the wick4h stream's exits"""
    out = []; ss = SS.get(st, SS["wick4h"])
    z0 = np.load(f"{M.ST}/wf/allorders_{st}{suf}.npz", allow_pickle=True); z = {k: z0[k] for k in z0.files}; bs = DE.STREAMS[st]["hh"] * 3600; sa, ha = ss["stop_atr"], ss["hard_stop_atr"]
    for k in range(len(z["t"])):
        lv, a = float(z["lv"][k]), float(z["atr"][k]); f = bool(z["filled"][k]); e = float(z["fill"][k]) if f else lv
        out.append({"coin": str(z["coin"][k]), "sym": M.bn(str(z["coin"][k])), "t": int(z["t"][k]), "until": int(z["t"][k]) + 4 * bs, "side": int(z["side"][k]),
                    "lv": lv, "atr": a, "prio": float(z["score"][k]) / float(z["thr"][k]), "filled": f, "t1h": int(z["t1h"][k]), "e": e,
                    "r": float(z["R"][k]), "t1": int(z["tout"][k]), "st": sa * a / e, "sth": ha * a / e, "stream": st, "mod": "dlm",
                    "mkt": 0 if int(z["kind"][k]) == 1 else 1})   # "mkt": the market fills of the trade (a take is a limit: 0)
    return out
_VOL = {}
def btc_vol_ratio(h):
    """the user's drawdown round: BTC's mean |hourly log return| of the last 24 h / of the last 30 days, at the hour h"""
    if "T" not in _VOL:
        T, C = M.h1("BTCUSDT"); r = np.abs(np.diff(np.log(C), prepend=np.log(C[0]))); cs = np.cumsum(r)
        s24 = (cs - np.r_[np.zeros(24), cs[:-24]]) / 24; s720 = (cs - np.r_[np.zeros(720), cs[:-720]]) / 720
        _VOL.update(T=T, ratio=np.where(s720 > 0, s24 / s720, 1.0))
    i = np.searchsorted(_VOL["T"], h - 3600, side="right") - 1
    return float(_VOL["ratio"][i]) if i >= 720 else 1.0
_FUND = {}
def funding_at(sym, t):
    """the coin's last funding rate settled at or before t (<LABSTORE>/data/funding), None when unknown"""
    if sym not in _FUND:
        fn = f"{M.ST}/data/funding/{sym}.csv"
        a = np.loadtxt(fn, delimiter=",", ndmin=2) if os.path.exists(fn) else np.zeros((0, 2))
        _FUND[sym] = (a[:, 0].astype(np.int64), a[:, 1]) if len(a) else None
    z = _FUND[sym]
    if z is None: return None
    i = np.searchsorted(z[0], t, side="right") - 1
    return float(z[1][i]) if i >= 0 and t - z[0][i] < 12 * 3600 else None
_BTR = {}
def btc_above_ema50(t):
    """BTC's last closed day above its daily EMA50 at t"""
    if "d" not in _BTR:
        T, C = M.h1("BTCUSDT"); d = T // 86400; last = np.r_[np.flatnonzero(d[1:] != d[:-1]), len(d) - 1]
        dc = C[last]; e = np.empty(len(dc)); e[0] = dc[0]
        for k in range(1, len(dc)): e[k] = e[k - 1] + 2 / 51 * (dc[k] - e[k - 1])
        _BTR.update(d=d[last], up=dc > e)
    i = np.searchsorted(_BTR["d"], t // 86400, side="left") - 1   # the last day closed before t's day
    return bool(_BTR["up"][i]) if i >= 50 else True
_HMM = {}
def hmm_p(h, which):
    """hmm_regime.py's filtered probability at h (the last 4 h bar closed by h): "p" = panic, "a" = active + panic"""
    if "T" not in _HMM:
        z = np.load(f"{M.ST}/wf/hmm_regime.npz"); _HMM.update(T=z["T"], p=np.nan_to_num(z["p_panic"]), a=np.nan_to_num(z["p_panic"] + z["p_act"]))
    i = np.searchsorted(_HMM["T"], h, side="right") - 1
    return float(_HMM[which][i]) if i >= 0 else 0.0
_SIG = {}
def sig_ratio(sym, h):
    """a coin's std of hourly log returns over the 30 days before the day of h / BTC's (a beta proxy), cached a day"""
    key = (sym, h // 86400)
    if key not in _SIG:
        def sd(s_):
            T, C = M.h1(s_); j = np.searchsorted(T, (h // 86400) * 86400, side="right")
            c = C[max(0, j - 721):j]
            return float(np.std(np.diff(np.log(c)))) if len(c) > 50 else None
        a, b = sd(sym), sd("BTCUSDT")
        if len(_SIG) > 200000: _SIG.clear()
        _SIG[key] = (a / b) if (a and b) else 1.5
    return _SIG[key]
def orders(suf=None):
    out = []
    for st in ("wick4h", "close2h"):
        out += stream_orders(st, os.environ.get('ALLSUF', '') if suf is None else suf)
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
# the liquidity (the user: "гибкую систему, с разным шагом урезания… универсальным модулем"): the coin's hourly turnover ($, the
# median of the 24 h before) and its daily volatility (the std of the daily log returns of the 30 days before), from the
# lab-store's 1h candles
LQ = {}
def liq_data(sym):
    if sym not in LQ:
        fn = os.path.join(M.ST, "data", "1h", f"{sym}.csv.gz")
        if not os.path.exists(fn):
            LQ[sym] = None; return None
        a = np.loadtxt(fn, delimiter=",", ndmin=2, usecols=(0, 4, 5)); T = a[:, 0].astype(np.int64); C = a[:, 1]; Q = a[:, 2]
        from numpy.lib.stride_tricks import sliding_window_view
        med = np.full(len(Q), np.nan)
        if len(Q) > 24: med[24:] = np.median(sliding_window_view(Q, 24), axis=1)[:-1]
        d = T // 86400; st_ = np.flatnonzero(np.r_[True, d[1:] != d[:-1]]); dc = C[np.r_[st_[1:] - 1, len(C) - 1]]
        lr = np.diff(np.log(np.maximum(dc, 1e-12))); sig = np.full(len(dc), np.nan)
        if len(lr) > 30: sig[31:] = np.std(sliding_window_view(lr, 30), axis=1)[:-1] if len(lr) > 30 else np.nan
        LQ[sym] = (T, med, d[st_], sig)
    return LQ[sym]
def liq_at(sym, t):
    """(the hourly turnover $, the daily volatility) at t, or (None, None)"""
    L = liq_data(sym)
    if L is None: return None, None
    T, med, D, sig = L; i = bisect.bisect_right(T, t) - 1; j = bisect.bisect_right(D, t // 86400) - 1
    v = float(med[i]) if i >= 0 and np.isfinite(med[i]) and med[i] > 0 else None
    s = float(sig[j]) if j >= 0 and np.isfinite(sig[j]) else None
    return v, s
def liq_steps(spec):
    """"1:0.5/2:0.25/4:0" -> [(0.01, 0.5), (0.02, 0.25), (0.04, 0.0)]: above each share of the hourly turnover the position grows
    at that rate (0 = no more)"""
    return [(float(a) / 100, float(b)) for a, b in (x.split(":") for x in spec.split("/"))] if spec else []
def liq_g(p, steps):
    """the position's share of the hourly turnover after the cut (continuous, monotone): slope 1 up to the first step"""
    out, prev, slope = 0.0, 0.0, 1.0
    for th, sl in steps:
        if p <= th: return out + (p - prev) * slope
        out += (th - prev) * slope; prev, slope = th, sl
    return out + (p - prev) * slope
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
    for m_ in ("prv", "smc", "emx", "htf", "cfl"):
        if m_ in kw: rk = dict(rk, **{m_: float(kw[m_])})
    rk = dict(rk); rk.setdefault("cfl", 1.0)   # 🔄 Классика (the bot's BN_OTHERS_RISK 1%)
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
    # top-ups: "dep=AMT/DAYS/N" — AMT added every DAYS days, N times (the first one DAYS after the start); the drawdown is
    # measured on the account's unit value (a top-up after a fall does not hide it)
    dep = tuple(float(x) for x in kw["dep"].split("/")) if "dep" in kw else None; ndep = 0; units = 1.0
    # the liquidity: "liq=1:0.5/2:0.25/4:0" the cut of a position by its share of the coin's hourly turnover (liq_g); "slip=Y" the
    # square-root impact of every market fill: Y x the daily volatility x sqrt(the position / the daily turnover), off the trade's R
    LS = liq_steps(kw.get("liq", "")); SLIP = float(kw.get("slip", 0)); n_cut = 0
    # "add=wick4h_o2" (the user: "для 4ч со сдвигом сделать исключение и добирать позицию"): that stream's limit may fill on a
    # coin already held by ⚡ on the same side (a separate leg with its own exits); "addon=wick4h" — only onto that stream's
    # position; another module's position or the other side still blocks it
    ADD = set(kw["add"].split("+")) if "add" in kw else set(); ADDON = set(kw["addon"].split("+")) if "addon" in kw else None
    # the drawdown hypotheses (the user: "снизить просадки без особого ущерба для дохода"): "sidecap=N" at most N ⚡ positions + armed
    # limits a side; "btcshock=X" no new ⚡ short after BTC rose > X (a fraction) in 24 h, no long after it fell > X; "burst=N" at
    # most N new ⚡ positions a side in 24 h
    SC = int(kw.get("sidecap", 0)); BSH = float(kw.get("btcshock", 0)); BUR = int(kw.get("burst", 0)); opens = collections.deque()
    # "fuse=W/X": no new ⚡ on a side while its ⚡ trades closed in the last W hours sum to -X R or worse (the side's fuse)
    FUSE = tuple(float(x) for x in kw["fuse"].split("/")) if "fuse" in kw else None; closed_dlm = collections.deque()
    def blocked(o, h):
        if FUSE:
            while closed_dlm and closed_dlm[0][0] < h - FUSE[0] * 3600: closed_dlm.popleft()
            if sum(r_ for _, sd, r_ in closed_dlm if sd == o["side"]) <= -FUSE[1]:
                return True
        if SC and sum(1 for p_ in pos if p_["mod"] == "dlm" and p_["side"] == o["side"]) + sum(1 for a in armed.values() if a["o"]["side"] == o["side"]) >= SC:
            return True
        if BSH:
            b0, b1 = M.px_at("BTCUSDT", h - 86400), M.px_at("BTCUSDT", h)
            if b0 and b1 and ((o["side"] < 0 and b1 / b0 - 1 > BSH) or (o["side"] > 0 and b1 / b0 - 1 < -BSH)):
                return True
        if BUR:
            while opens and opens[0][0] < h - 86400: opens.popleft()
            if sum(1 for _, sd in opens if sd == o["side"]) >= BUR:
                return True
        return False
    # "hedge=N/F": while N+ ⚡ positions are open on one side, a BTC perpetual the other way at F x their notional (re-sized every
    # hour, 0.05% a side on the change, its margin at 20x counted)
    HLOSS = float(kw.get("hloss", 0))   # "hloss=X": the hedge only while the side's open ⚡ are down X R a position on average (unrealized)
    HSIDE = int(kw.get("hside", 0))   # "hside=1": hedge only the crowd of ⚡ longs (BTC short), -1 only the shorts' (BTC long)
    HG = tuple(float(x) for x in kw["hedge"].split("/")) if "hedge" in kw else None; HDG = {"n": 0.0, "px": None}   # (a dict: fit() reads it)
    # the user's drawdown round (v0.99.776): "bstop=X/H" — the open ⚡ of a side together down more than X of the equity -> all
    # closed at the hour's price, no new ⚡ on that side for H hours; "vol=Z/m" — BTC's last-24h volatility over Z x its 30-day
    # level -> every new trade's risk x m; "conf=N/X" — with N+ ⚡ open on a side, a new one there only while their average
    # unrealized R is above -X; "beta=B" — the open notional of a side weighted by each coin's volatility / BTC's at most B x the
    # equity; "hcap=N" — at most N new HTF trades an hour
    BST = tuple(float(x) for x in kw["bstop"].split("/")) if "bstop" in kw else None; cool = {}
    VOL = tuple(float(x) for x in kw["vol"].split("/")) if "vol" in kw else None
    CONF = tuple(float(x) for x in kw["conf"].split("/")) if "conf" in kw else None
    BETA = float(kw.get("beta", 0)); HCAP = int(kw.get("hcap", 0))
    # round 3 (v0.99.776): "fund=X" — no new ⚡ on a side whose crowd pays the funding above X (side x rate > X: crowded);
    # "btrend=1" — ⚡ longs only while BTC is above its daily EMA50, shorts only below; "cprio=N/P" — with N+ ⚡ open on a side,
    # a new one there needs its score >= P x the threshold; "hburst=N" — at most N new ⚡ a side an hour; "noc2hs=1" — no 2h
    # shorts; "noo2=1" — no shifted 4h stream
    FUNDX = float(kw.get("fund", 0)); BTREND = kw.get("btrend") == "1"; CPRIO = tuple(float(x) for x in kw["cprio"].split("/")) if "cprio" in kw else None
    HBUR = int(kw.get("hburst", 0))
    HMMR = (float(kw["hmm"].split("/")[0]), float(kw["hmm"].split("/")[1]), kw["hmm"].split("/")[2], kw["hmm"].split("/")[3] if kw["hmm"].count("/") > 2 else "all") if "hmm" in kw else None
    # "hmm=P/m/w[/dlm]": while hmm_regime's probability (w: "p" panic, "a" active + panic) is above P, the new trades' risk x m (m 0: none)
    if kw.get("noc2hs") == "1": OR = [o for o in OR if not (o["stream"] == "close2h" and o["side"] < 0)]
    if kw.get("noo2") == "1": OR = [o for o in OR if o["stream"] != "wick4h_o2"]
    curve = [] if kw.get("curve") == "1" else None   # "curve=1": (hour, equity, open ⚡ longs, shorts, others) every 6 h, the last value
    path = [] if kw.get("path") == "1" else None   # "path=1": the balance at every 30 days (before that day's top-up) + the end, a 5th value
    cash = eq0; pos = []; armed = {}; peak = eq0; mdd = 0.0; done = set(); n_fill = n_skip = 0
    # the reserve (the user: "резерв для восстановления после просадки"): "res=F/t/P" — F of the capital kept off the trading account,
    # every P days the two brought back to (1-F) / F (the reserve refills the account after a fall, takes the profit after a rise);
    # "res=F/b/P" — only when the account strays more than P (a fraction) from its share. Only the account's free cash moves out.
    # The money and the drawdown are the whole capital's (the account + the reserve)
    RS = (float(kw["res"].split("/")[0]), kw["res"].split("/")[1], float(kw["res"].split("/")[2])) if "res" in kw else None
    RES = 0.0
    if RS: RES = eq0 * RS[0]; cash = eq0 - RES
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
        if VOL and btc_vol_ratio(int(v.get("t0") or v["t"] + 3600)) > VOL[0]: r *= VOL[1]
        if HMMR and (HMMR[3] == "all" or v["mod"] == "dlm") and hmm_p(int(v.get("t0") or v["t"] + 3600), HMMR[2]) > HMMR[0]: r *= HMMR[1]
        return eq * r * WF(v) * v.get("xm", 1.0)   # "xm": a per-trade risk multiplier (money_wk.py), 1 = as the bot
    def used(): return sum(o["heat"] for o in pos) + hf * sum(o["heat"] for o in armed.values())
    def sused(s): return sum(o["heat"] for o in pos if o["side"] == s) + hf * sum(a["heat"] for a in armed.values() if a["o"]["side"] == s)
    def fit(v, eq, extra=0.0):
        rd = rd_of(v, eq); hn = rd * v["sth"] / v["st"]; room = heat * eq - used() + extra
        if rd <= 0: return None, 0.0, room   # a zero risk (hmm=…/0): no trade
        if sh: room = min(room, sh * eq - sused(v["side"]) + extra)
        if net: room = min(room, net * eq - (sused(v["side"]) - sused(-v["side"])) + extra)
        if hn > room:
            if room < hn * 0.1: return None, hn, room
            rd *= room / hn
        notional = rd / v["st"]
        if LS or SLIP:
            V_, s_ = liq_at(v["sym"], v.get("t0") or v["t"])
            if V_ and LS:
                p_ = notional / V_; q_ = liq_g(p_, LS)
                if q_ < p_ * 0.999:
                    k_ = q_ / p_; rd *= k_; notional *= k_
            imp = (SLIP * s_ * (notional / (24 * V_)) ** 0.5) if (SLIP and V_ and s_) else 0.0
        else:
            imp = 0.0
        if BETA:
            t_ = int(v.get("t0") or v["t"] + 3600)
            ex = sum(o["notional"] * sig_ratio(o["sym"], t_) for o in pos if o["side"] == v["side"]) + \
                 sum(a["notional"] * sig_ratio(a["sym"], t_) for a in armed.values() if a["o"]["side"] == v["side"])
            need = notional * sig_ratio(v["sym"], t_); rb = BETA * eq - ex
            if need > rb:
                if rb <= need * 0.1: return None, hn, room
                q = rb / need; rd *= q; notional *= q
        if notional < minn: return None, hn, room   # under Binance's minimum order: not opened
        mg = notional / M.lev_real(v["sym"], notional, cap); free = eq - sum(o["mg"] for o in pos) - sum(o["mg"] for o in armed.values()) - abs(HDG["n"]) / 20
        if nomg: mg = 0.0   # "nomg=1": the margin never short (what the free margin costs)
        if mg > 0.9 * free:
            if free <= 1: return None, hn, room
            q = 0.9 * free / mg; rd *= q; notional *= q; mg *= q
            if notional < minn: return None, hn, room
        return {"rd": rd, "heat": rd * v["sth"] / v["st"], "mg": mg, "notional": notional, "imp": imp}, hn, room
    for h in range(A, B, 3600):
        for o in [o for o in pos if o["t1"] <= h]:
            if FUSE and o["mod"] == "dlm": closed_dlm.append((o["t1"], o["side"], o["r"]))
            nm_ = o["mkt"] if "mkt" in o else 1 + (o["r"] < 0)   # the market fills: ⚡ its exit unless a take; the others the entry + a stop
            cash += o["rd"] * (o["r"] - nm_ * o.get("imp", 0.0) / o["st"]); pos.remove(o)
        upnl = 0.0
        for o in pos:
            p = M.px_at(o["sym"], h)
            if p: upnl += o["side"] * (p - o["e"]) / o["e"] * o["notional"]
        if HG:   # the BTC hedge: its hour's PnL, then re-sized to the open ⚡ sides
            bp = M.px_at("BTCUSDT", h)
            if bp and HDG["px"] and HDG["n"]: cash += HDG["n"] * (bp / HDG["px"] - 1)
            if bp:
                HDG["px"] = bp; tgt = 0.0
                for sd in ((HSIDE,) if HSIDE else (1, -1)):
                    side_pos = [o for o in pos if o["mod"] == "dlm" and o["side"] == sd]
                    if len(side_pos) >= HG[0]:
                        if HLOSS:
                            pl = 0.0
                            for o in side_pos:
                                p_ = M.px_at(o["sym"], h)
                                if p_: pl += o["side"] * (p_ - o["e"]) / o["e"] * o["notional"]
                            if pl > -HLOSS * sum(o["rd"] for o in side_pos):   # the side's average unrealized R above -X: no hedge
                                continue
                        tgt -= sd * HG[1] * sum(o["notional"] for o in side_pos)
                cash -= abs(tgt - HDG["n"]) * 0.0005; HDG["n"] = tgt
        eq = cash + upnl
        if eq <= 0 and not RES: return (0.0, 1.0, n_fill, n_skip) + ((path + [0.0] * (13 - len(path)),) if path is not None else ())
        if eq <= 0:   # the account wiped: the reserve refills it
            cash += RES - eq; RES = 0.0; pos = []; armed = {}; eq = cash
        if RS:
            tot = eq + RES; tgt = (1 - RS[0]) * tot
            due = ((h - A) % int(RS[2] * 86400) == 0 and h > A) if RS[1] == "t" else (eq < tgt * (1 - RS[2]) or eq > tgt * (1 + RS[2]))
            if due:
                d_ = tgt - eq
                if d_ > 0: tr = min(d_, RES)
                else: tr = -min(-d_, max(0.0, cash - sum(o["mg"] for o in pos) - sum(a["mg"] for a in armed.values())))
                cash += tr; RES -= tr; eq += tr
        if path is not None and h >= A + (len(path) + 1) * 30 * 86400: path.append(eq + RES)
        if dep and ndep < dep[2] and h >= A + (ndep + 1) * dep[1] * 86400:
            units += dep[0] / (eq / units); cash += dep[0]; eq += dep[0]; ndep += 1
        nav = (eq + RES) / units; peak = max(peak, nav); mdd = max(mdd, 1 - nav / peak)
        if curve is not None and h % 21600 == 0:
            curve.append((h, round(nav, 4), sum(1 for o in pos if o["mod"] == "dlm" and o["side"] > 0), sum(1 for o in pos if o["mod"] == "dlm" and o["side"] < 0),
                          sum(1 for o in pos if o["mod"] != "dlm")))
        if BST:
            for sd in (1, -1):
                sp = [o for o in pos if o["mod"] == "dlm" and o["side"] == sd]
                if len(sp) < 2: continue
                pxs = [M.px_at(o["sym"], h) for o in sp]
                pl = sum(o["side"] * (p_ - o["e"]) / o["e"] * o["notional"] for o, p_ in zip(sp, pxs) if p_)
                if pl < -BST[0] * eq:
                    for o, p_ in zip(sp, pxs):
                        if not p_: continue
                        r_ = o["side"] * (p_ - o["e"]) / o["e"] / o["st"] - 0.001 / o["st"]
                        cash += o["rd"] * (r_ - o.get("imp", 0.0) / o["st"]); pos.remove(o)
                    cool[sd] = h + int(BST[1] * 3600)
        if ddc:
            if not cut_on and nav < peak * (1 - ddc[0]): cut_on = True
            elif cut_on and nav >= peak * (1 - ddc[2]): cut_on = False
        if pz:
            eqh.append((h, eq + RES))
            while eqh and eqh[0][0] < h - pz[0] * 86400: eqh.popleft()
            if eq + RES < eqh[0][1] * (1 - pz[1]): pause_to = h + int(pz[0] * 86400)
        paused = h < pause_to
        while jo < len(OT) and OT[jo]["t0"] <= h:   # the other modules at the market
            v = OT[jo]; jo += 1
            if paused or v["t0"] < h - 3600 or any(o["sym"] == v["sym"] for o in pos) or any(a["sym"] == v["sym"] for a in armed.values()): continue
            if HCAP and v["mod"] == "htf" and sum(1 for o in pos if o["mod"] == "htf" and o["t0"] >= h - 3600) >= HCAP: continue
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
                    if o["filled"] and o["t1h"] == h: pos.append(dict(o, **{x: a[x] for x in ("rd", "heat", "mg", "notional", "imp")})); n_fill += 1; opens.append((h, o["side"]))
                elif far: del armed[k_]
            elif near:
                want.append((o, touch, s * (cl - o["lv"]) / o["atr"], cl))
        order = sorted(want, key=lambda w: -w[0]["prio"]) if rule in ("Bn", "Bq") else [want[i] for i in rng.permutation(len(want))]
        if rule in ("A", "Ac"): order.sort(key=lambda w: w[2])   # the bot arms the nearest first (random among the same distance)
        for o, touch, d_o, cl in ([] if paused else order):
            k_ = id(o)
            if k_ in done or k_ in armed: continue
            held = [p_ for p_ in pos if p_["sym"] == o["sym"]]
            busy = bool(held)
            if busy and o["stream"] in ADD and all(p_["mod"] == "dlm" and p_["side"] == o["side"] and p_.get("stream") != o["stream"]
                                                   and (ADDON is None or p_.get("stream") in ADDON) for p_ in held):
                busy = False   # a leg on top of the same side's ⚡ position
            if not busy:   # the bot: one limit a coin on the exchange — the nearer one (DLM_SWAP_ATR 0.25): a farther armed one comes off
                for k2, a in [(k2, a) for k2, a in armed.items() if a["o"]["sym"] == o["sym"]]:
                    ao = a["o"]
                    if touch or ao["side"] * (cl - ao["lv"]) / ao["atr"] > d_o + 0.25: del armed[k2]
                    else: busy = True
            if BST and cool.get(o["side"], 0) > h: busy = True
            if FUNDX and not busy:
                fr = funding_at(o["sym"], h)
                if fr is not None and o["side"] * fr > FUNDX: busy = True
            if BTREND and not busy and (btc_above_ema50(h) != (o["side"] > 0)): busy = True
            if CPRIO and not busy and o["prio"] < CPRIO[1] and sum(1 for p_ in pos if p_["mod"] == "dlm" and p_["side"] == o["side"]) >= CPRIO[0]: busy = True
            if HBUR and not busy and sum(1 for t_, sd in itertools.takewhile(lambda x: x[0] >= h, reversed(opens)) if sd == o["side"]) >= HBUR: busy = True
            if CONF and not busy:
                same = [p_ for p_ in pos if p_["mod"] == "dlm" and p_["side"] == o["side"]]
                if len(same) >= CONF[0]:
                    ur = [p_["side"] * (px_ - p_["e"]) / p_["e"] / p_["st"] for p_ in same for px_ in [M.px_at(p_["sym"], h)] if px_]
                    if ur and np.mean(ur) < -CONF[1]: busy = True
            nd = sum(1 for p_ in pos if p_["mod"] == "dlm") + (len(armed) if cnt else 0)
            blk = (SC or BSH or BUR or FUSE) and not busy and blocked(o, h)
            busy = busy or bool(blk)
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
                    if o["filled"] and o["t1h"] == h: pos.append(dict(o, **s_)); n_fill += 1; opens.append((h, o["side"]))
                else:
                    armed[k_] = dict(s_, o=o, sym=o["sym"])
            elif touch:
                done.add(k_); n_skip += o["filled"] and o["t1h"] == h
    upnl = 0.0
    for o in pos:
        p = M.px_at(o["sym"], B)
        if p: upnl += o["side"] * (p - o["e"]) / o["e"] * o["notional"]
    return (cash + upnl + RES, mdd, n_fill, n_skip) + ((path + [cash + upnl + RES],) if path is not None else ()) + ((curve,) if curve is not None else ())
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
