"""the ⚡ fill cluster as a BTC signal: k fills of one side within W hours (each known at its 15m bar's close) -> BTC that
side at that bar's close, out after H hours; vs BTC's own drift (all 15m starts of the year), by year"""
import numpy as np
z = np.load("dlm_fills.npz"); TE, SD = z["te"], z["side"]
a = np.loadtxt("data/15m/BTCUSDT.csv", delimiter=",", ndmin=2); BT = a[:, 0].astype(np.int64); BC = a[:, 4]; BH = a[:, 2]; BL = a[:, 3]
pos = {int(t): i for i, t in enumerate(BT)}
def ret(t, h, s):   # entry: the close of the 15m bar ending at t; exit: the close h hours later
    i = pos.get(int(t) - 900)
    if i is None or i + h * 4 >= len(BC): return None
    return s * (BC[i + h * 4] / BC[i] - 1)
yr = lambda t: int(np.datetime64(int(t), "s").astype("datetime64[Y]").astype(int) + 1970)
o = np.argsort(TE); TE, SD = TE[o], SD[o]
for W in (2, 4):
    for k in (3, 5, 8):
        for s in (1, -1):
            last = -1e18; ev = []
            ts_ = TE[SD == s]
            for j, t in enumerate(ts_):
                n = np.sum((ts_ > t - W * 3600) & (ts_ <= t))
                if n >= k and t - last > 24 * 3600:
                    ev.append(t); last = t
            for H in (4, 12, 24):
                rs = [(yr(t), ret(t, H, s)) for t in ev]; rs = [(y, r) for y, r in rs if r is not None]
                if len(rs) < 15: continue
                R_ = np.array([r for _, r in rs]); Y_ = np.array([y for y, _ in rs])
                # the baseline: the same side, every 15m start of those years
                by = " ".join(f"{y}:{R_[Y_ == y].mean()*100:+.2f}%({(Y_ == y).sum()})" for y in sorted(set(Y_)))
                print(f"W{W}h k{k} {'лонг' if s > 0 else 'шорт'} H{H}h: n {len(R_)} avg {R_.mean()*100:+.2f}% med {np.median(R_)*100:+.2f}% WR {np.mean(R_ > 0)*100:.0f}% | {by}", flush=True)
# the baseline drift per year (long, H 12h)
for H in (4, 12, 24):
    b = BC[H * 4:] / BC[:-H * 4] - 1; yy = (BT[:-H * 4].astype("datetime64[s]").astype("datetime64[Y]").astype(int) + 1970)
    print(f"baseline long H{H}h: " + " ".join(f"{y}:{b[yy == y].mean()*100:+.2f}%" for y in range(2022, 2027)))
