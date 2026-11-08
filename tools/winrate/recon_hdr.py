"""HANDOFF 2а (the user picked it): the header vs the top-ups tool. The bot as it trades now (v0.99.781+), a year from $100, the
same noise runs (K, ⚡ by rng(300+k), the others by the trade's hash): (A) money_hdr2's rule (no top-ups) and (B)
money_dep_months' rule with N=0 top-ups — on the same 34 monthly starts; (A) also on the header's 144 weekly starts. Equal tools
-> (A) = (B) on the same starts; the gap between the monthly and the weekly starts = only which starts.
usage: ALLSUF=_clr recon_hdr.py [K]"""
import sys, os, json, zlib, calendar, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
K = int(ARGV[0]) if ARGV else 4
BASE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|path=1"
RISK = "dlm=4|prv=3.75|smc=3.125|emx=3.75|htf=2.5|cfl=2|cflheat=0.45"
RA = f"{BASE}|{RISK}"; RB = f"{BASE}|dep=100/30/0|{RISK}"
SM = [calendar.timegm((y, m, 1, 0, 0, 0)) for y in (2023, 2024, 2025) for m in range(1, 13) if (y, m) <= (2025, 10)]
_D = {}
def _init(D): _D.update(D)
def job(a):
    tag, k, A = a
    return tag, k, A, MA2.run(_D[("or", k)], _D[("ot", k)], A, A + 365 * 86400, RA if tag[0] == "A" else RB, 1)[:2]
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf_cfl"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k); D[("or", k)] = sorted([o for o in base + o2 if rng.random() >= 0.05], key=lambda o: o["t"])
        D[("ot", k)] = [v for v in OT if zlib.crc32(f"{k}|{v['mod']}|{v['sym']}|{v['side']}|{v['t0']}".encode()) % 100 >= 5]
    jobs = [("Am", k, A) for k in range(K) for A in SM] + [("Bm", k, A) for k in range(K) for A in SM] + [("Aw", k, A) for k in range(K) for A in X.STARTS]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, jobs, chunksize=4)
    R = {}
    for tag, k, A, r in res: R.setdefault(tag, {}).setdefault(k, []).append((A, r[0], r[1]))
    out = {}
    for tag, nm in (("Am", "(А) правило шапки, 34 месячных старта"), ("Bm", "(Б) инструмент пополнений, 0 пополнений, те же 34"), ("Aw", "(А) правило шапки, 144 недельных старта (как шапка)")):
        p10, p50, p90, dd = [], [], [], []
        for k in range(K):
            e = np.array([x[1] for x in sorted(R[tag][k])]); d_ = np.array([x[2] for x in sorted(R[tag][k])])
            p10.append(np.percentile(e, 10)); p50.append(np.median(e)); p90.append(np.percentile(e, 90)); dd.append(np.median(d_))
        out[tag] = {"p10": float(np.median(p10)), "p50": float(np.median(p50)), "p90": float(np.median(p90)), "dd": float(np.median(dd)), "p50_runs": [round(float(x)) for x in p50]}
        print(f"{nm}: плохой ${out[tag]['p10']:,.0f} · обычный ${out[tag]['p50']:,.0f} (прогоны {out[tag]['p50_runs']}) · хороший ${out[tag]['p90']:,.0f} · просадка {out[tag]['dd'] * 100:.0f}%", flush=True)
    same = all(abs(a - b) < 1 for a, b in zip([x[1] for k in range(K) for x in sorted(R["Am"][k])], [x[1] for k in range(K) for x in sorted(R["Bm"][k])]))
    print("(А) и (Б) на одних стартах совпадают до доллара:", same, flush=True)
    json.dump(out, open(f"{M.ST}/wf/recon_hdr.json", "w"), indent=1)
    print("recon done", flush=True)
