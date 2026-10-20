"""'a run of takes, a stop — start again with $30': one trade at a time (the next signal after the previous closed),
the size so that a take = +X% of the deposit; an attempt ends at the first losing trade (restart with a new $30) or at
the target (cash out). From the bot's backtest lists (2023–26), chronological, attempts started at random points."""
import json, numpy as np
B = json.load(open("/home/user/vp-poc-screener/vp_bt_trades.json"))
def seq_of(mods):
    tr = sorted([dict(x, m=m) for m in mods for x in B[m] if x["t"] >= 1672531200], key=lambda x: x["t"])
    out, free = [], 0
    for x in tr:
        if x["t"] < free: continue
        out.append(x); free = x["x"]
    return out
def take_r(m):
    return {"prv": 0.73, "cas": 1.80, "emx": 3.0, "rbx": None}[m]
rng = np.random.default_rng(7)
for name, mods in (("P/R", ["prv"]), ("каскад", ["cas"]), ("P/R + каскад", ["prv", "cas"])):
    seq = seq_of(mods); n = len(seq)
    weeks = (seq[-1]["x"] - seq[0]["t"]) / 604800; per_m = n / weeks * 4.35
    r = np.array([x["r"] for x in seq]); wr = np.mean(r > 0)
    print(f"\n=== {name}: по одной сделке {n} сделок за {weeks:.0f} нед (~{per_m:.1f} в месяц), WR {wr*100:.0f}%")
    for pct in (0.5, 0.7, 1.0):
        res = {}
        for target in (10, 100):
            succ, att_l, trades_l = 0, [], []
            for _ in range(20000):
                i = rng.integers(0, n); eq = 30.0; k = 0
                while True:
                    x = seq[(i + k) % n]; f = pct / take_r(x["m"])
                    eq *= max(0.0, 1 + f * x["r"]); k += 1
                    if eq >= 30 * target: succ += 1; trades_l.append(k); break
                    if x["r"] < 0 or k > 200: att_l.append(k); break
            p = succ / 20000
            avg_tr_fail = np.mean(att_l) if att_l else 0
            # attempts until a success ~ 1/p; trades spent ~ (1/p - 1) * failed-attempt length + success length
            tr_needed = (1 / p - 1) * avg_tr_fail + (np.mean(trades_l) if trades_l else 0) if p else float("inf")
            res[target] = (p, 1 / p if p else float("inf"), tr_needed / per_m if p else float("inf"))
        print(f"  тейк = +{pct*100:.0f}%: ×10 — {res[10][0]*100:.1f}% на попытку (~{res[10][1]:.0f} попыток, ~{res[10][1]*30:,.0f}$, ~{res[10][2]:.0f} мес) · "
              f"×100 — {res[100][0]*100:.2f}% (~{res[100][1]:.0f} попыток, ~{res[100][1]*30:,.0f}$, ~{res[100][2]:.0f} мес)")
