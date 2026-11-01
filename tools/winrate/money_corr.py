"""the drawdown by the side (the user: "2 и 3"): the open risk capped a side ("sh") or the long-short difference ("net")
instead of / with the total; and the fees: BNB (-10%) and the other modules' takes as a limit (0.02% instead of 0.05%).
The bundle ⚡ + P/R + SMC + EMA + HTF by the strictest money at the bot's settings, 144 windows x 2 seeds"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X, money_params as MP, money_rbx as RB
from multiprocessing import Pool
F = RB.F; SEEDS = (1, 2)
VARS = {"сейчас (лимит 100%)": (F, "-"),
        **{f"на сторону {x}%": (F + f"|sh={x / 100:g}", "-") for x in (50, 60, 70, 80)},
        **{f"перекос {x}%": (F + f"|net={x / 100:g}", "-") for x in (40, 50, 60)},
        "общий 120% + на сторону 70%": (F.replace("heat=1.0", "heat=1.2") + "|sh=0.7", "-"),
        "общий 120% + перекос 60%": (F.replace("heat=1.0", "heat=1.2") + "|net=0.6", "-"),
        "комиссии в BNB": (F, "bnb"), "BNB + тейк лимиткой": (F, "bnb_tm")}


def others(fee):
    """M.build's P/R / SMC / EMA / HTF with the fees changed (the list's R had 0.1% a round trip, takers both ways)"""
    L = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json")); out = []
    for mod in ("prv", "smc", "emx", "htf"):
        for t in L[mod]:
            sym = M.bn(t["s"])
            if not sym: continue
            scl = 1000.0 if sym.startswith("1000") and not t["s"].startswith("1000") else 1.0
            st = max(0.002, abs(t["e"] - t["sl"]) / t["e"]); sth = max(st, abs(t["e"] - t.get("hs", t["sl"])) / t["e"])
            d = 0.0
            if fee in ("bnb", "bnb_tm"): d += 0.1 * 0.001 / st
            if fee == "bnb_tm" and t.get("k") == "take": d += 0.9 * 0.0003 / st
            out.append({"t0": int(t["t"]), "t1": int(t["x"]), "r": float(t["r"]) - 0.03 + d, "st": st, "sth": sth, "mod": mod, "sym": sym, "side": t["d"],
                        "e": t["e"] * scl, "stream": None})
    return sorted(out, key=lambda v: v["t0"])


def dlm_fee(OR):
    """⚡ with BNB: its maker entry + maker take (0.02% each) or taker stop (0.05%) -10%"""
    return [dict(o, r=o["r"] + 0.1 * (0.0002 + (0.0002 if o["r"] > 0 else 0.0005)) / o["st"]) if o["filled"] else o for o in OR]


_D = {}
def _init(D): _D.update(D)
def job(a):
    v, sd, A = a
    rule, fee = VARS[v]
    return v, sd, A, MA2.run(_D["or_bnb"] if fee != "-" else _D["or"], _D["ot_" + fee], A, A + 365 * 86400, rule, sd)


if __name__ == "__main__":
    OR = MA2.orders()
    D = {"or": OR, "or_bnb": dlm_fee(OR), "ot_-": others("-"), "ot_bnb": others("bnb"), "ot_bnb_tm": others("bnb_tm")}
    b0 = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]
    print(f"проверка списков: {len(b0)} = {len(D['ot_-'])}, R {np.mean([v['r'] for v in b0]):.4f} = {np.mean([v['r'] for v in D['ot_-']]):.4f}; "
          f"BNB +{np.mean([v['r'] for v in D['ot_bnb']]) - np.mean([v['r'] for v in D['ot_-']]):.4f}R, +тейк {np.mean([v['r'] for v in D['ot_bnb_tm']]) - np.mean([v['r'] for v in D['ot_-']]):.4f}R; "
          f"⚡ BNB +{np.mean([o['r'] for o in D['or_bnb'] if o['filled']]) - np.mean([o['r'] for o in OR if o['filled']]):.4f}R", flush=True)
    jobs = [(v, sd, A) for v in VARS for sd in SEEDS for A in X.STARTS]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=8)
    R = {}
    for v, sd, A, x in res: R.setdefault(v, {}).setdefault(A, []).append(x)
    b = np.array([np.mean([x[0] for x in R["сейчас (лимит 100%)"][A]]) for A in X.STARTS])
    print("вариант | обычный год | плохой год | просадка медиана | просадка в плохом окне (1 из 10) | лучше нынешнего", flush=True)
    for v in VARS:
        E = np.array([np.mean([x[0] for x in R[v][A]]) for A in X.STARTS]); dd = np.array([np.mean([x[1] for x in R[v][A]]) for A in X.STARTS])
        print(f"{v} | ${np.median(E):,.0f} | ${np.percentile(E, 10):,.0f} | {np.median(dd) * 100:.0f}% | {np.percentile(dd, 90) * 100:.0f}% | {int((E > b * 1.001).sum())}/{len(b)}", flush=True)
    print("money corr done", flush=True)
