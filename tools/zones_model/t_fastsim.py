# the numpy replay must equal the bot's zone_ladder_sim on the same bars
import random, numpy as np
from common import V, load
from fastsim import ladder
cs = load("SOLUSDT")
random.seed(3)
bad = n = 0
for _ in range(3000):
    i = random.randrange(5000, len(cs) - 400)
    fut = cs[i:i + 336]
    px = cs[i - 1]["close"]
    side = random.choice(["long", "short"])
    s = 1 if side == "long" else -1
    a = px * (1 - s * random.uniform(0.005, 0.15))
    w = px * random.uniform(0.003, 0.05)
    lo, hi = (a - w, a) if s > 0 else (a, a + w)
    tp = random.choice([3.0, 5.0, 8.0, 12.0, 20.0])
    g = [{"id": "x", "side": side, "levels": sorted([lo, hi], reverse=(s > 0))}]
    r1 = V.zone_ladder_sim(fut, g, tp, fut[0]["time"], fut[-1]["time"] + 3600)
    O = np.array([c["open"] for c in fut]); H = np.array([c["high"] for c in fut]); L = np.array([c["low"] for c in fut]); C = np.array([c["close"] for c in fut])
    near, far = (hi, lo) if s > 0 else (lo, hi)
    r2 = ladder(O, H, L, C, s, near, far, V.ZONES_LIMIT_OFF, V.ZONES_STOP_BUF, "pct", tp)
    n += 1
    if (r1 is None) != (r2 is None) or (r1 and (abs(r1["r"] - r2[0]) > 1e-3 or r1["result"][0] != r2[2])):
        bad += 1
        if bad < 5:
            print("MISMATCH", side, tp, r1 and (r1["r"], r1["result"], r1["filled"]), r2)
print("checked", n, "mismatches", bad)
