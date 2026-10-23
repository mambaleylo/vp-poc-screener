"""lab after v0.99.689: a BTC panic filter for the deployed 4h wick + 2h close pool — an order is cancelled (never fills)
when, at the open of the bar it would fill in, BTC has moved against its side by more than k x BTC's 1h ATR over the
last 1h / 4h / 24h (causal: known at that bar's open). The pool as the bot trades it, money at 20 positions x 4%"""
exec(open("pool3s.py").read().split("\nroll = np.arange")[0].replace('C3 = {', 'C3_ = {'))
from common import load as load1h
B = load1h("BTCUSDT"); BT = np.array([c["time"] for c in B], np.int64); BC = np.array([c["close"] for c in B])
BH = np.array([c["high"] for c in B]); BL = np.array([c["low"] for c in B])
BA = E_w = None
import s21h2_engine as _E; BA = _E.wilder(BH, BL, BC, 14)
def btc_move(t, h):   # BTC's close-to-close move over the h hours before t (the last closed 1h bar before t), in BTC 1h ATRs
    j = int(np.searchsorted(BT, t)) - 1   # the bar opening before t ... its close is at BT[j]+3600 <= t when BT[j] <= t-3600
    while j >= 0 and BT[j] + 3600 > t: j -= 1
    if j - h < 0 or not BA[j] > 0: return 0.0
    return (BC[j] - BC[j - h]) / BA[j]
EV = [(e, 0) for e in W4] + [(e, 1) for e in C2]
MV = {h: np.array([btc_move(e[1], h) for e, _ in EV]) for h in (1, 4, 24)}
SIDE = np.array([e[4] for e, _ in EV]); R_ = np.array([e[6] for e, _ in EV])
def pool_side(evs):
    ev = sorted(evs, key=lambda x: (x[1], x[2], x[0])); busy, act, P = {}, [], []
    for t, ft, nsc, sym, s, end, R, st in ev:
        if busy.get((sym, s), 0) > ft: continue
        act = [x for x in act if x[0] > ft]
        if sum(1 for x in act if x[1] == s) >= 20: continue
        busy[(sym, s)] = end; act.append((end, s)); P.append((ft, end, R, st))
    P.sort(key=lambda x: x[0]); return np.array(P, float)
roll = np.arange(ts(2024), ts(2025, 10) + 1, 7 * 86400.0)
def show(nm, keep):
    P = pool_side([e for (e, _), k in zip(EV, keep) if k]); t0, t1, R, STv = P[:, 0], P[:, 1], P[:, 2], P[:, 3]
    y = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.025) for s_ in roll])
    yh = np.array([sim(t0, t1, R, STv, int(np.searchsorted(t0, s_)), s_ + 365 * 86400.0, 20, 0.04, -0.04)[0] for s_ in roll])
    cut = ~keep; cr = R_[cut].mean() if cut.any() else 0
    print(f"{nm:34s} убрано {cut.sum():5d} (их {cr:+.2f}R) | пул n{len(R)} {R.mean():+.3f}R | медиана ${np.median(y[:, 0]):,.0f} 10% ${np.percentile(y[:, 0], 10):,.0f} "
          f"просадка {np.median(y[:, 1])*100:.0f}%/{np.percentile(y[:, 1], 90)*100:.0f}%/макс {y[:, 1].max()*100:.0f}% | жёстко ${np.median(yh):,.0f}", flush=True)
show("без фильтра (сейчас)", np.ones(len(EV), bool))
for h, ks in ((1, (2, 3, 4)), (4, (3, 4, 6, 8)), (24, (6, 8, 10, 14))):
    for k in ks:
        show(f"BTC за {h}ч против стороны > {k} ATR", ~(SIDE * MV[h] < -k))
for h, ks in ((4, (4, 6)), (24, (8, 12))):   # the other way: only when BTC moved WITH the side (a squeeze)
    for k in ks:
        show(f"BTC за {h}ч в сторону > {k} ATR", ~(SIDE * MV[h] > k))
