"""the drawdowns of the bot as it trades (the user: "просадка 81% это было раз в год условно, или раз в несколько лет, или такое
регулярно происходит?"): one continuous account from $100 on 2023-01-01 to 2026-10-01 with the final config (money_hdr2's: 3
streams, the liquidity cut, the impact), K runs dropping 5% (the noise); every drawdown episode deeper than 30% from a peak:
its start, the trough's date and depth, the days to the trough and to recover the peak, the open positions at the trough
(⚡ longs / shorts / the others). usage: ALLSUF=_clr dd_episodes.py [K]"""
import sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ARGV, sys.argv = sys.argv[1:], sys.argv[:1]
import money_arm2 as MA2, money_multi as M, money_expect as X
from multiprocessing import Pool
RULE = "Bn|arm=0.6|oth=1|dis=1.0|heat=1.0|cap=125|slip=1|liq=4:0.5/8:0.25/12:0|curve=1"; K = int(ARGV[0]) if ARGV else 4
A, B = M.ts(2023, 1, 1), M.ts(2026, 10, 1)
_D = {}
def _init(D): _D.update(D)
def job(k): return k, MA2.run(_D[(k, "or")], _D[(k, "ot")], A, B, RULE, 1)
if __name__ == "__main__":
    base = MA2.orders(); o2 = [dict(o, xm=0.75) for o in MA2.stream_orders("wick4h_o2", "") if o["prio"] >= 1.05]
    OT = [v for v in M.build("base") if v["mod"] in X.KINDS["bundle_htf"] - {"dlm"}]; D = {}
    for k in range(K):
        rng = np.random.default_rng(300 + k)
        D[(k, "or")] = sorted([o for o in base + o2 if rng.random() >= 0.05], key=lambda o: o["t"]); D[(k, "ot")] = [v for v in OT if rng.random() >= 0.05]
    with Pool(4, initializer=_init, initargs=(D,)) as Pl:
        res = Pl.map(job, range(K))
    dt = lambda t: str(np.datetime64(int(t), "s"))[:10]; out = []
    for k, r in res:
        cv = r[-1]; T = np.array([c[0] for c in cv]); E = np.array([c[1] for c in cv])
        print(f"\nпрогон {k + 1}: со $100 к 1.10.2026 ${r[0]:,.0f}, макс. просадка {r[1] * 100:.0f}%", flush=True)
        i, n = 0, len(E); peak_i = 0; eps = []
        while i < n:
            if E[i] >= E[peak_i]: peak_i = i; i += 1; continue
            j = i; tr = i
            while j < n and E[j] < E[peak_i]:
                if E[j] < E[tr]: tr = j
                j += 1
            depth = 1 - E[tr] / E[peak_i]
            if depth >= 0.30:
                eps.append((T[peak_i], T[tr], depth, T[j] if j < n else None, cv[tr][2], cv[tr][3], cv[tr][4]))
            peak_i = j if j < n else peak_i; i = j
        for p0, t0, d, t1, nl, ns, no in eps:
            print(f"  с {dt(p0)}: дно {dt(t0)} −{d * 100:.0f}% (за {(t0 - p0) / 86400:.0f} дн), восстановление {('за ' + str(int((t1 - t0) / 86400)) + ' дн') if t1 else 'не успело'}"
                  f" · на дне открыто ⚡ лонгов {nl}, шортов {ns}, других {no}", flush=True)
        out.append({"final": r[0], "mdd": r[1], "eps": [[int(a), int(b), float(c), int(e) if e else None, int(f), int(g), int(h)] for a, b, c, e, f, g, h in eps]})
    json.dump(out, open(f"{M.ST}/wf/dd_episodes.json", "w"))
    print("dd done", flush=True)
